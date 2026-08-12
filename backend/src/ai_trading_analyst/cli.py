"""Kommandozeile fuer den manuellen Lauf gegen die TWS.

Zweck ist die Inbetriebnahme und die Fehlersuche am realen Anbieter: Sie
beantwortet die Frage "kommen ueber IBKR verwertbare Kerzen an, und was sagt
der Screener dazu" **ohne Datenbank, ohne API und ohne Scheduler**. Der
regulaere, persistierte Lauf laeuft weiterhin ueber
``RunAnalysisUseCase``.

Es wird ausschliesslich gelesen -- kein Schreibzugriff auf die Datenbank,
keine ordererzeugende Schnittstelle.

Liegt wie ``bootstrap.py`` bewusst ausserhalb der vier Schichten: Sie
verdrahtet Konfiguration, Infrastruktur und Domain und ist damit selbst eine
Composition Root.

Beispiele::

    python -m ai_trading_analyst.cli watchlist
    python -m ai_trading_analyst.cli screen --provider ibkr --symbols AAPL,MSFT --no-pacing
    python -m ai_trading_analyst.cli screen --provider ibkr --limit 5
    python -m ai_trading_analyst.cli screen --provider ibkr
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ai_trading_analyst.bootstrap import build_market_data_provider, project_root
from ai_trading_analyst.config.loader import load_config
from ai_trading_analyst.config.settings import LoggingConfig
from ai_trading_analyst.domain.analysis import (
    MarketDataProvider,
    MarketDataProviderError,
    Stock,
)
from ai_trading_analyst.domain.screening import (
    CandidateRuleParameters,
    ScreeningStatus,
    evaluate_candidate,
)
from ai_trading_analyst.infrastructure.ibkr import ContractSpec, IbkrMarketDataProvider
from ai_trading_analyst.infrastructure.watchlists import (
    WatchlistError,
    describe_sources,
    load_watchlist_directory,
)
from ai_trading_analyst.observability.logging_setup import configure_logging

PACING_FREE_LIMIT = 20
"""So viele Symbole duerfen ohne Mindestabstand abgefragt werden -- deutlich
unter IBKRs Grenze von 60 Anfragen je zehn Minuten."""


@dataclass(frozen=True, slots=True)
class SymbolOutcome:
    """Was bei einer Aktie herauskam -- Ergebnis oder Fehler, nie beides."""

    symbol: str
    candles: int = 0
    last_candle: datetime | None = None
    status: ScreeningStatus | None = None
    reason: str | None = None
    signals: tuple[str, ...] = ()
    error: str | None = None


def _watchlist_path(config_path: Path) -> Path:
    loaded = load_config(config_path)
    return project_root(loaded.source_path) / loaded.config.market_data.ibkr.watchlist_directory


def _screen_symbol(
    provider: MarketDataProvider, stock: Stock, rule: CandidateRuleParameters
) -> SymbolOutcome:
    try:
        series = provider.get_candle_series(stock)
    except MarketDataProviderError as error:
        return SymbolOutcome(symbol=stock.symbol, error=str(error))

    result = evaluate_candidate(series, len(series) - 1, rule)
    return SymbolOutcome(
        symbol=stock.symbol,
        candles=len(series),
        last_candle=series.candle(len(series) - 1).timestamp,
        status=result.status,
        reason=result.reason,
        signals=tuple(sorted(signal.value for signal in result.fired_signal_types)),
    )


def _print_outcome(index: int, total: int, outcome: SymbolOutcome) -> None:
    prefix = f"[{index:>3}/{total}] {outcome.symbol:<8}"
    if outcome.error is not None:
        print(f"{prefix} FEHLER   {outcome.error}", flush=True)
        return
    last = outcome.last_candle.isoformat() if outcome.last_candle else "-"
    signals = ", ".join(outcome.signals) if outcome.signals else "-"
    status = outcome.status.value if outcome.status else "-"
    detail = f" ({outcome.reason})" if outcome.reason else ""
    print(
        f"{prefix} {status:<24}{detail:<28} Kerzen={outcome.candles:<5} "
        f"letzte={last}  Signale={signals}",
        flush=True,
    )


def _print_summary(outcomes: Sequence[SymbolOutcome], started: datetime) -> None:
    counted: dict[str, int] = {}
    for outcome in outcomes:
        key = "FEHLER" if outcome.error is not None else str(outcome.status)
        counted[key] = counted.get(key, 0) + 1

    duration = (datetime.now(UTC) - started).total_seconds()
    print(f"\n{len(outcomes)} Aktien in {duration:.0f} s")
    for key in sorted(counted):
        print(f"  {key:<28} {counted[key]}")

    candidates = [item.symbol for item in outcomes if item.status is ScreeningStatus.CANDIDATE]
    if candidates:
        print(f"\nKandidaten: {', '.join(candidates)}")


def command_watchlist(args: argparse.Namespace) -> int:
    """Zeigt, was gescreent wuerde -- ohne jede Verbindung zur TWS."""
    directory = _watchlist_path(args.config)
    contracts = load_watchlist_directory(directory)
    print(f"Verzeichnis: {directory}")
    print(f"Dateien:     {', '.join(describe_sources(directory))}")
    print(f"Symbole:     {len(contracts)} (Mehrfachnennungen zusammengefasst)\n")
    for contract in contracts:
        print(f"  {contract.symbol:<8} {contract.primary_exchange or '(ohne Heimatboerse)'}")
    return 0


def command_screen(args: argparse.Namespace) -> int:
    loaded = load_config(args.config)
    config = loaded.config
    indicators = config.require_indicators()

    # Lesbare Zeilen statt JSON: Diese Ausgabe liest ein Mensch waehrend des
    # Laufs. Sichtbar wird dadurch unter anderem, an welchen Tagen die Sitzung
    # frueher endete und deshalb nur eine Kerze entstand.
    configure_logging(LoggingConfig(level="INFO", format="console"))

    if args.provider is not None:
        market_data = config.market_data.model_copy(update={"provider": args.provider})
        config = config.model_copy(update={"market_data": market_data})

    if config.market_data.provider != "ibkr":
        print(
            "market_data.provider steht auf "
            f"'{config.market_data.provider}'. Fuer einen Lauf gegen die TWS entweder "
            "'--provider ibkr' angeben oder die Konfiguration umstellen.",
            file=sys.stderr,
        )
        return 2

    if args.no_pacing:
        ibkr = config.market_data.ibkr.model_copy(
            update={"minimum_request_interval_seconds": 0.0}
        )
        market_data = config.market_data.model_copy(update={"ibkr": ibkr})
        config = config.model_copy(update={"market_data": market_data})

    watchlist: tuple[ContractSpec, ...] | None = None
    if args.symbols is not None:
        watchlist = tuple(
            ContractSpec(symbol=symbol.strip().upper())
            for symbol in args.symbols.split(",")
            if symbol.strip()
        )
        if not watchlist:
            # Sonst laeuft ein Screening ueber null Aktien durch und meldet
            # Erfolg -- dieselbe Falle, die der Watchlist-Import ausschliesst.
            print(f"--symbols enthaelt kein Symbol: '{args.symbols}'", file=sys.stderr)
            return 2

    provider = build_market_data_provider(
        config, indicators, project_root(loaded.source_path), watchlist
    )
    rule = CandidateRuleParameters(
        required_signal_count=config.screening.required_signal_count,
        signal_lookback_previous_candles=config.screening.signal_lookback_previous_candles,
        warmup_candles=indicators.warmup_candles,
    )

    stocks = list(provider.list_stocks())
    if args.limit is not None:
        stocks = stocks[: args.limit]

    interval = config.market_data.ibkr.minimum_request_interval_seconds
    if interval <= 0 and len(stocks) > PACING_FREE_LIMIT:
        # Ohne Abstand loest ein solcher Lauf genau die Sperre aus, gegen die
        # der Abstand eingebaut wurde -- und trifft dann auch die parallel
        # laufende Fremdanwendung an derselben TWS.
        print(
            f"--no-pacing ist fuer {len(stocks)} Aktien nicht zulaessig: IBKR sperrt die "
            f"Verbindung ab 60 Anfragen je zehn Minuten. Hoechstens {PACING_FREE_LIMIT} "
            "Symbole (--symbols oder --limit) oder den Lauf mit Abstand starten.",
            file=sys.stderr,
        )
        return 2

    print(
        f"{len(stocks)} Aktien, TWS {config.market_data.ibkr.host}:"
        f"{config.market_data.ibkr.port} (Client-ID {config.market_data.ibkr.client_id}), "
        f"Historie {config.market_data.ibkr.history_duration}, Abstand {interval:g} s\n"
    )

    started = datetime.now(UTC)
    outcomes: list[SymbolOutcome] = []
    abgebrochen = False
    try:
        for index, stock in enumerate(stocks, start=1):
            outcome = _screen_symbol(provider, stock, rule)
            outcomes.append(outcome)
            _print_outcome(index, len(stocks), outcome)
    except KeyboardInterrupt:
        abgebrochen = True
        print("\nAbgebrochen -- die bis dahin geprueften Aktien stehen oben.", file=sys.stderr)
    finally:
        if isinstance(provider, IbkrMarketDataProvider):
            provider.close()

    _print_summary(outcomes, started)

    # Der Rueckgabewert muss unterscheidbar machen, ob der Lauf durchlief:
    # Bei nicht gestarteter TWS scheitern alle Aktien, und ein Skript, das
    # nur auf den Rueckgabewert schaut, haette das sonst nicht bemerkt.
    if abgebrochen:
        return 130
    return 1 if any(outcome.error is not None for outcome in outcomes) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai_trading_analyst.cli",
        description="Manueller Lauf gegen die IBKR-TWS, ohne Datenbank.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Pfad zu einer Konfigurationsdatei (Standard: config/default.yaml).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    watchlist = subparsers.add_parser(
        "watchlist", help="Zeigt die eingelesene Watchlist, ohne die TWS zu kontaktieren."
    )
    watchlist.set_defaults(handler=command_watchlist)

    screen = subparsers.add_parser("screen", help="Screent die Watchlist gegen die TWS.")
    screen.add_argument(
        "--provider",
        choices=("fixture", "ibkr"),
        default=None,
        help=(
            "Uebersteuert market_data.provider nur fuer diesen Lauf. Die Konfiguration "
            "steht bewusst auf 'fixture', damit API und Tests ohne TWS auskommen."
        ),
    )
    screen.add_argument(
        "--symbols",
        default=None,
        help="Kommagetrennte Symbole statt der Watchlist -- fuer eine gezielte Einzelpruefung.",
    )
    screen.add_argument(
        "--limit", type=int, default=None, help="Nur die ersten N Aktien der Watchlist."
    )
    screen.add_argument(
        "--no-pacing",
        action="store_true",
        help=(
            "Ohne Mindestabstand zwischen den Anfragen. Nur fuer wenige Symbole -- "
            "IBKR sperrt die Verbindung bei mehr als 60 Anfragen in zehn Minuten."
        ),
    )
    screen.set_defaults(handler=command_screen)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        exit_code: int = args.handler(args)
    except WatchlistError as error:
        print(f"Watchlist: {error}", file=sys.stderr)
        return 2
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
