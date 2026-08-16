"""Kommandozeile fuer den manuellen Lauf gegen die TWS.

Zweck ist die Inbetriebnahme und die Fehlersuche am realen Anbieter: Sie
beantwortet die Frage "kommen ueber IBKR verwertbare Kerzen an, und was sagt
der Screener dazu" **ohne API und ohne Scheduler**. Der regulaere,
persistierte Lauf laeuft weiterhin ueber ``RunAnalysisUseCase``.

Die Datenbank braucht nur, wer sie braucht: ``watchlist`` und
``screen --source live`` kommen ohne aus. ``backfill`` legt Bars ab,
``screen --source stored`` liest sie.

Keine ordererzeugende Schnittstelle -- die Sicherheitsgrenze aus ADR 0014
gilt hier wie im Adapter.

Liegt wie ``bootstrap.py`` bewusst ausserhalb der vier Schichten: Sie
verdrahtet Konfiguration, Infrastruktur und Domain und ist damit selbst eine
Composition Root.

Beispiele::

    python -m ai_trading_analyst.cli watchlist
    python -m ai_trading_analyst.cli screen --provider ibkr --symbols AAPL,MSFT --no-pacing
    python -m ai_trading_analyst.cli screen --provider ibkr --limit 5
    python -m ai_trading_analyst.cli screen --provider ibkr
    python -m ai_trading_analyst.cli research --provider anthropic --symbol AAPL
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy.engine import Engine
from sqlalchemy.exc import ArgumentError

from ai_trading_analyst.application.backfill_history import (
    BackfillHistoryUseCase,
    SymbolBackfill,
)
from ai_trading_analyst.application.run_backtest import BacktestUseCase, StockBacktest
from ai_trading_analyst.bootstrap import (
    build_backtest_params,
    build_ibkr_bar_source,
    build_market_data_provider,
    build_research_provider,
    project_root,
)
from ai_trading_analyst.config.loader import load_config
from ai_trading_analyst.config.settings import AppConfig, LoggingConfig, MissingSecretError, Secrets
from ai_trading_analyst.domain.analysis import (
    MarketDataProvider,
    MarketDataProviderError,
    ResearchProviderError,
    Stock,
    UnitOfWork,
)
from ai_trading_analyst.domain.backtesting import BacktestConfidence
from ai_trading_analyst.domain.research import ResearchReport
from ai_trading_analyst.domain.screening import (
    CandidateRuleParameters,
    IndicatorValues,
    ScreeningStatus,
    SignalType,
    evaluate_candidate,
)
from ai_trading_analyst.infrastructure.ibkr import (
    ContractSpec,
    IbkrMarketDataProvider,
    duration_in_days,
)
from ai_trading_analyst.infrastructure.persistence.session import (
    DatabaseUnavailableError,
    build_engine,
    build_session_factory,
    verify_connection,
)
from ai_trading_analyst.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from ai_trading_analyst.infrastructure.watchlists import (
    WatchlistError,
    describe_sources,
    load_watchlist_directory,
)
from ai_trading_analyst.observability.logging_setup import configure_logging

PACING_FREE_LIMIT = 20
"""So viele Symbole duerfen ohne Mindestabstand abgefragt werden -- deutlich
unter IBKRs Grenze von 60 Anfragen je zehn Minuten."""


def _positive_count(value: str) -> int:
    """``--limit`` als Anzahl, nicht als Slice-Grenze.

    Ohne diese Pruefung schnitte ``--limit -1`` ueber ``watchlist[:-1]``
    stillschweigend die *letzte* Aktie weg, statt die erste zu nehmen.
    """
    zahl = int(value)
    if zahl < 1:
        raise argparse.ArgumentTypeError(f"muss mindestens 1 sein, ist aber {zahl}")
    return zahl


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
    close: float | None = None
    indicators: IndicatorValues | None = None


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

    letzter = len(series) - 1
    result = evaluate_candidate(series, letzter, rule)
    return SymbolOutcome(
        symbol=stock.symbol,
        candles=len(series),
        last_candle=series.candle(letzter).timestamp,
        status=result.status,
        reason=result.reason,
        signals=tuple(sorted(signal.value for signal in result.fired_signal_types)),
        close=series.candle(letzter).close,
        indicators=series.indicator(letzter),
    )


def _format_value(value: float | None) -> str:
    """Ungerundete Werte sind die Rechengrundlage (G1-Pruefvorlage 1.4).

    Vier Nachkommastellen reichen fuer den Abgleich mit einem Chart und
    zeigen zugleich, dass hier nicht auf zwei Stellen gerundet gerechnet wird.
    """
    return "-" if value is None else f"{value:.4f}"


def _print_outcome(index: int, total: int, outcome: SymbolOutcome, details: bool) -> None:
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
    if details and outcome.indicators is not None:
        werte = outcome.indicators
        print(
            f"{'':>10} Schluss={_format_value(outcome.close)}  "
            f"RSI={_format_value(werte.rsi)}  RSI-MA={_format_value(werte.rsi_ma)}  "
            f"EMA5={_format_value(werte.ema5)}  EMA20={_format_value(werte.ema20)}",
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


def _watchlist_from(
    args: argparse.Namespace, config: AppConfig, config_path: Path
) -> tuple[ContractSpec, ...] | None:
    """Symbole aus ``--symbols`` oder aus den Watchlist-Dateien.

    ``None`` heisst: ``--symbols`` wurde angegeben, enthielt aber kein Symbol.
    Ohne diese Unterscheidung liefe ein Screening ueber null Aktien durch und
    meldete Erfolg.
    """
    if args.symbols is None:
        return tuple(
            load_watchlist_directory(
                project_root(config_path) / config.market_data.ibkr.watchlist_directory
            )
        )
    gewaehlt = tuple(
        ContractSpec(symbol=symbol.strip().upper())
        for symbol in args.symbols.split(",")
        if symbol.strip()
    )
    if not gewaehlt:
        print(f"--symbols enthaelt kein Symbol: '{args.symbols}'", file=sys.stderr)
        return None
    return gewaehlt


def _print_backfill_progress(index: int, total: int, ergebnis: SymbolBackfill) -> None:
    prefix = f"[{index:>3}/{total}] {ergebnis.symbol:<8}"
    if ergebnis.failed:
        print(f"{prefix} FEHLER   {ergebnis.error}", flush=True)
        return
    print(
        f"{prefix} {ergebnis.received_bars:>5} Bars empfangen, "
        f"{ergebnis.stored_bars:>5} neu  ({ergebnis.requested_days} Tage)",
        flush=True,
    )


def _open_database() -> Engine | None:
    """Engine samt Anklopfversuch.

    ``None`` heisst: Die Meldung ist bereits ausgegeben, der Aufrufer bricht
    mit Rueckgabewert 2 ab. Die Datenbank-Adresse selbst steht in keiner der
    Meldungen -- in ihr steht das Passwort.
    """
    try:
        engine = build_engine(Secrets().require("database_url"))
        verify_connection(engine)
    except MissingSecretError as error:
        print(f"Datenbank: {error}", file=sys.stderr)
        return None
    except (ArgumentError, ValueError) as error:
        # Unlesbare Adresse, unbekannter Treiber, kein numerischer Port:
        # ohne diesen Zweig ein Traceback statt einer Meldung.
        print(f"ATA_DATABASE_URL ist keine gueltige Adresse: {error}", file=sys.stderr)
        return None
    except DatabaseUnavailableError as error:
        # Vor dem Lauf, nicht waehrend: Sonst quittiert jede der 192 Aktien
        # denselben Fehler.
        print(
            f"Datenbank nicht erreichbar: {error}\n"
            "Geprueft wird ATA_DATABASE_URL aus der Umgebung oder aus der .env "
            "im Projektwurzelverzeichnis.",
            file=sys.stderr,
        )
        return None
    return engine


def command_backfill(args: argparse.Namespace) -> int:
    """Fuellt den Bestand an nativen Bars auf.

    Das einzige Kommando, das etwas dauerhaft ablegt -- und neben
    ``screen --source stored``, das aus dem Bestand liest, eines von zweien,
    die eine Datenbank brauchen.
    """
    loaded = load_config(args.config)
    config = loaded.config
    configure_logging(LoggingConfig(level="INFO", format="console"))

    if args.provider is not None:
        market_data = config.market_data.model_copy(update={"provider": args.provider})
        config = config.model_copy(update={"market_data": market_data})

    if config.market_data.provider != "ibkr":
        # Ohne diese Pruefung baute der Backfill mit dem ausgelieferten
        # Standard 'fixture' trotzdem eine TWS-Verbindung auf.
        print(
            "market_data.provider steht auf "
            f"'{config.market_data.provider}'. Der Backfill holt Daten von der TWS -- "
            "entweder '--provider ibkr' angeben oder die Konfiguration umstellen.",
            file=sys.stderr,
        )
        return 2

    try:
        standardzeitraum = duration_in_days(config.market_data.ibkr.history_duration)
    except ValueError as error:
        # Vor allem anderen: Ein Tippfehler in der Konfiguration soll nicht
        # erst nach dem Verbindungsaufbau auffallen.
        print(f"market_data.ibkr.history_duration: {error}", file=sys.stderr)
        return 2

    if args.no_pacing:
        ibkr = config.market_data.ibkr.model_copy(update={"minimum_request_interval_seconds": 0.0})
        market_data = config.market_data.model_copy(update={"ibkr": ibkr})
        config = config.model_copy(update={"market_data": market_data})

    if args.from_date is not None and args.from_date > datetime.now(UTC).date():
        # Sonst wuerde daraus stillschweigend "ein Tag": Ein Tippfehler in der
        # Jahreszahl machte aus dem Reparaturlauf einen Leerlauf.
        print(f"--from {args.from_date.isoformat()} liegt in der Zukunft.", file=sys.stderr)
        return 2

    watchlist = _watchlist_from(args, config, loaded.source_path)
    if watchlist is None:
        return 2
    if args.limit is not None:
        watchlist = watchlist[: args.limit]

    interval = config.market_data.ibkr.minimum_request_interval_seconds
    if interval <= 0 and len(watchlist) > PACING_FREE_LIMIT:
        print(
            f"--no-pacing ist fuer {len(watchlist)} Aktien nicht zulaessig: IBKR sperrt die "
            f"Verbindung ab 60 Anfragen je zehn Minuten. Hoechstens {PACING_FREE_LIMIT} "
            "Symbole (--symbols oder --limit) oder den Lauf mit Abstand starten.",
            file=sys.stderr,
        )
        return 2

    engine = _open_database()
    if engine is None:
        return 2
    session_factory = build_session_factory(engine)

    def uow_factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    bar_source = build_ibkr_bar_source(config)
    use_case = BackfillHistoryUseCase(
        bar_source,
        uow_factory,
        from_date=args.from_date,
        default_days=standardzeitraum,
    )

    print(
        f"{len(watchlist)} Aktien, TWS {config.market_data.ibkr.host}:"
        f"{config.market_data.ibkr.port} (Client-ID {config.market_data.ibkr.client_id}), "
        f"Abstand {interval:g} s\n"
    )
    started = datetime.now(UTC)
    try:
        bericht = use_case.execute(watchlist, on_progress=_print_backfill_progress)
    except KeyboardInterrupt:
        # Der Bestand ist bis hierher geschrieben; ein erneuter Lauf setzt
        # genau dort an. Aufzuraeumen gibt es nichts.
        print(
            "\nAbgebrochen -- der bisherige Bestand bleibt erhalten, "
            "ein erneuter Lauf setzt dort an.",
            file=sys.stderr,
        )
        return 130
    finally:
        bar_source.close()

    dauer = (datetime.now(UTC) - started).total_seconds()
    print(f"\n{len(bericht.results)} Aktien in {dauer:.0f} s")
    print(f"  neue Bars                    {bericht.stored_bars}")
    print(f"  Fehler                       {len(bericht.failures)}")
    if bericht.failures:
        print(f"\nFehlgeschlagen: {', '.join(item.symbol for item in bericht.failures)}")
    if bericht.empty:
        # Ohne diese Zeile bliebe eine Aktie, fuer die gar nichts ankam, in
        # der Bilanz unsichtbar: Sie ist weder Fehler noch Kuerzung.
        print(
            f"\nKeine Bars erhalten ({len(bericht.empty)}): "
            + ", ".join(item.symbol for item in bericht.empty[:10])
        )
        print("  An einem Feiertag erwartbar. Sonst kennt IBKR das Symbol nicht.")
    if bericht.gaps:
        print(
            f"\nLuecke zum vorhandenen Bestand ({len(bericht.gaps)}): "
            + ", ".join(item.symbol for item in bericht.gaps[:10])
        )
        print(
            "  Die Antwort beginnt spaeter als der letzte gespeicherte Bar. Der Zeitraum "
            "dazwischen wird nie von allein nachgeholt -- mit '--from JJJJ-MM-TT' holen."
        )
    if bericht.truncated:
        # Kein Fehler: Eine Neuemission hat schlicht keine laengere Historie.
        # Bei einem lange notierten Titel ist es dagegen der Hinweis darauf,
        # dass IBKR die Antwort gekuerzt hat -- dann mit "--from" nachholen.
        print(
            "\nDeutlich weniger Historie als angefragt "
            f"({len(bericht.truncated)}): "
            + ", ".join(
                f"{item.symbol} ({item.covered_days} statt {item.requested_days} Tage)"
                for item in bericht.truncated[:10]
            )
        )
        print(
            "  Bei einer Neuemission ist das erwartbar. Sonst hat die Gegenstelle "
            "gekuerzt -- dann mit '--from JJJJ-MM-TT' erneut holen."
        )
    return 1 if bericht.failures else 0


def command_screen(args: argparse.Namespace) -> int:
    loaded = load_config(args.config)
    config = loaded.config
    indicators = config.require_indicators()

    # Lesbare Zeilen statt JSON: Diese Ausgabe liest ein Mensch waehrend des
    # Laufs. Sichtbar wird dadurch unter anderem, an welchen Tagen die Sitzung
    # frueher endete und deshalb nur eine Kerze entstand.
    configure_logging(LoggingConfig(level="INFO", format="console"))

    uebersteuert: dict[str, str] = {}
    if args.provider is not None:
        uebersteuert["provider"] = args.provider
    if args.source is not None:
        uebersteuert["source"] = args.source
    if uebersteuert:
        market_data = config.market_data.model_copy(update=uebersteuert)
        config = config.model_copy(update={"market_data": market_data})

    if config.market_data.provider != "ibkr":
        # Auch fuer '--source stored': Die 195-Minuten-Kerzen entstehen im
        # IbkrMarketDataProvider, unabhaengig davon, woher seine Bars kommen.
        # Kontaktiert wird die TWS dabei nicht.
        print(
            "market_data.provider steht auf "
            f"'{config.market_data.provider}'. Fuer einen IBKR-Lauf entweder "
            "'--provider ibkr' angeben oder die Konfiguration umstellen.",
            file=sys.stderr,
        )
        return 2

    if args.no_pacing:
        ibkr = config.market_data.ibkr.model_copy(update={"minimum_request_interval_seconds": 0.0})
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

    uow_factory: Callable[[], UnitOfWork] | None = None
    if config.market_data.source == "stored":
        engine = _open_database()
        if engine is None:
            return 2
        session_factory = build_session_factory(engine)

        def uow_factory() -> UnitOfWork:
            return SqlAlchemyUnitOfWork(session_factory)

    provider = build_market_data_provider(
        config,
        indicators,
        project_root(loaded.source_path),
        watchlist,
        uow_factory=uow_factory,
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
    # Aus dem Bestand gelesen gibt es keine Anfrage an die TWS und damit
    # nichts zu drosseln -- die Sperre waere hier nur im Weg.
    if config.market_data.source == "live" and interval <= 0 and len(stocks) > PACING_FREE_LIMIT:
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
        if config.market_data.source == "live"
        else f"{len(stocks)} Aktien aus dem gespeicherten Bestand -- ohne TWS\n"
    )

    started = datetime.now(UTC)
    outcomes: list[SymbolOutcome] = []
    abgebrochen = False
    try:
        for index, stock in enumerate(stocks, start=1):
            outcome = _screen_symbol(provider, stock, rule)
            outcomes.append(outcome)
            _print_outcome(index, len(stocks), outcome, args.details)
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


def _format_combination(signal_types: frozenset[SignalType]) -> str:
    return "+".join(sorted(signal_type.value for signal_type in signal_types))


def _print_backtest_summary(stock: StockBacktest) -> None:
    auswertbar = sum(
        1
        for result in stock.results
        for horizon in result.horizons
        if horizon.confidence is not BacktestConfidence.INSUFFICIENT_DATA
    )
    print(
        f"{stock.symbol}: {auswertbar} auswertbare Horizonte "
        f"von {len(stock.results)} Kombinationen"
    )


def _print_backtest_details(stock: StockBacktest) -> None:
    print(f"{stock.symbol}:")
    for result in stock.results:
        print(f"  {_format_combination(result.signal_types)}")
        for horizon in result.horizons:
            if horizon.confidence is BacktestConfidence.INSUFFICIENT_DATA:
                print(
                    f"    {horizon.horizon:>3} Kerzen: zu wenig Daten "
                    f"({horizon.deduplicated_event_count} Ereignisse)"
                )
                continue
            assert horizon.hit_rate is not None
            assert horizon.median_return is not None
            assert horizon.held_above_entry_rate is not None
            print(
                f"    {horizon.horizon:>3} Kerzen: Trefferquote {horizon.hit_rate:.0%}, "
                f"dauerhaft oberhalb {horizon.held_above_entry_rate:.0%}, "
                f"Median {horizon.median_return:+.2%}, n={horizon.deduplicated_event_count} "
                f"({horizon.confidence.value})"
            )


def _print_backtest_result(stock: StockBacktest, details: bool) -> None:
    if stock.failed:
        print(f"{stock.symbol}: FEHLER -- {stock.error}")
        return
    if details:
        _print_backtest_details(stock)
    else:
        _print_backtest_summary(stock)


def command_backtest(args: argparse.Namespace) -> int:
    """Historische Signalpruefung ueber den gespeicherten Bestand.

    Braucht immer den Bestand, nie die TWS -- ein Backtest ueber eine live
    abgerufene Kerzenserie ergibt keinen Sinn (G1-Pruefvorlage Abschnitt 4).
    """
    loaded = load_config(args.config)
    config = loaded.config
    indicators = config.require_indicators()
    configure_logging(LoggingConfig(level="INFO", format="console"))

    if args.provider is not None:
        market_data = config.market_data.model_copy(update={"provider": args.provider})
        config = config.model_copy(update={"market_data": market_data})

    if config.market_data.provider != "ibkr":
        # Anders als 'source' (unten) wird 'provider' nicht stillschweigend
        # uebersteuert: Ein Backtest gegen den Fixture-Anbieter wuerde
        # Aktien-IDs aus einem anderen UUID-Namensraum verwenden als der
        # IBKR-Bestand -- die Fremdschluesselbeziehung auf 'stocks' schluege
        # dann erst beim Speichern fehl, weit weg von dieser Meldung.
        print(
            "market_data.provider steht auf "
            f"'{config.market_data.provider}'. Der Backtest braucht den ueber IBKR "
            "gefuellten Bestand -- entweder market_data.provider auf 'ibkr' stellen "
            "oder zuerst 'backfill' laufen lassen.",
            file=sys.stderr,
        )
        return 2

    market_data = config.market_data.model_copy(update={"source": "stored"})
    config = config.model_copy(update={"market_data": market_data})

    engine = _open_database()
    if engine is None:
        return 2
    session_factory = build_session_factory(engine)

    def uow_factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    provider = build_market_data_provider(
        config, indicators, project_root(loaded.source_path), uow_factory=uow_factory
    )
    rule = CandidateRuleParameters(
        required_signal_count=config.screening.required_signal_count,
        signal_lookback_previous_candles=config.screening.signal_lookback_previous_candles,
        warmup_candles=indicators.warmup_candles,
    )
    backtest_params = build_backtest_params(config)

    try:
        stocks = list(provider.list_stocks())
        if args.symbols is not None:
            wanted = {
                symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()
            }
            stocks = [stock for stock in stocks if stock.symbol in wanted]
            fehlend = wanted - {stock.symbol for stock in stocks}
            if fehlend:
                # Nicht in der Watchlist gefunden ist etwas anderes als ein
                # Tippfehler ganz ohne Treffer -- beides soll aber sichtbar
                # sein, nicht nur die Aktien, die zufaellig passten.
                print(
                    f"Nicht in der Watchlist gefunden: {', '.join(sorted(fehlend))}",
                    file=sys.stderr,
                )
            if not stocks:
                print(
                    f"--symbols enthaelt kein bekanntes Symbol: '{args.symbols}'", file=sys.stderr
                )
                return 2
        if args.limit is not None:
            stocks = stocks[: args.limit]

        print(f"{len(stocks)} Aktien aus dem gespeicherten Bestand -- ohne TWS\n")

        use_case = BacktestUseCase(provider, uow_factory, rule, backtest_params)
        started = datetime.now(UTC)
        report = use_case.execute(stocks)
    finally:
        if isinstance(provider, IbkrMarketDataProvider):
            provider.close()

    for stock in report.stocks:
        _print_backtest_result(stock, args.details)

    dauer = (datetime.now(UTC) - started).total_seconds()
    print(f"\n{len(report.stocks)} Aktien in {dauer:.0f} s, {len(report.failures)} Fehler")
    if report.failures:
        print(f"Fehlgeschlagen: {', '.join(item.symbol for item in report.failures)}")
    return 1 if report.failures else 0


def _print_research_report(symbol: str, report: ResearchReport) -> None:
    print(f"{symbol}: {report.status.value}")
    if report.reason:
        print(f"  Grund: {report.reason}")
    if report.model:
        print(f"  Modell: {report.model} (Prompt-Version {report.prompt_version})")
    if report.confidence is not None:
        print(f"  Confidence: {report.confidence:.2f}")
    if report.summary:
        print(f"  Zusammenfassung: {report.summary}")
    for label, factors in (
        ("Positive Faktoren", report.positive_factors),
        ("Negative Faktoren", report.negative_factors),
        ("Risiken", report.risks),
    ):
        if factors:
            print(f"  {label}:")
            for factor in factors:
                print(f"    - {factor}")
    if report.citations:
        print("  Zitate:")
        for citation in report.citations:
            print(f"    - [{citation.license_class.value}] {citation.title} ({citation.url})")
            if citation.cited_text:
                print(f'      "{citation.cited_text}"')


def command_research(args: argparse.Namespace) -> int:
    """Manueller Probelauf des Research Agent fuer ein einzelnes Symbol.

    Braucht weder Datenbank noch Marktdatenanbieter -- anders als
    'backtest' liest der Research Agent keinen eigenen Kursbestand.
    Ein echter Aufruf gegen 'anthropic' kostet Geld (ADR 0021/0022
    Budget), deshalb keine automatische Uebersteuerung: 'fixture' bleibt
    Standard, bis ausdruecklich '--provider anthropic' gesetzt wird.
    """
    loaded = load_config(args.config)
    config = loaded.config
    configure_logging(LoggingConfig(level="INFO", format="console"))

    if args.provider is not None:
        research = config.research.model_copy(update={"provider": args.provider})
        config = config.model_copy(update={"research": research})

    try:
        provider = build_research_provider(config, Secrets())
    except MissingSecretError as error:
        print(f"Research: {error}", file=sys.stderr)
        return 2

    stock = Stock(id=uuid4(), symbol=args.symbol.upper(), exchange=args.exchange)

    try:
        report = provider.research(stock)
    except ResearchProviderError as error:
        print(f"Research fuer '{stock.symbol}' fehlgeschlagen: {error}", file=sys.stderr)
        return 2

    _print_research_report(stock.symbol, report)
    return 0


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
        "--limit",
        type=_positive_count,
        default=None,
        help="Nur die ersten N Aktien der Watchlist.",
    )
    screen.add_argument(
        "--details",
        action="store_true",
        help=(
            "Zeigt zusaetzlich Schlusskurs und Indikatorwerte der letzten Kerze -- "
            "zum Abgleich mit dem Chart."
        ),
    )
    screen.add_argument(
        "--source",
        choices=("live", "stored"),
        default=None,
        help=(
            "Uebersteuert market_data.source nur fuer diesen Lauf. 'live' fragt bei "
            "jedem Lauf die TWS -- rund 20 s je Aktie. 'stored' rechnet auf dem "
            "Bestand, den 'backfill' angelegt hat: ohne TWS, ohne Pacing, und bei "
            "wiederholtem Lauf mit demselben Ergebnis."
        ),
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

    backfill = subparsers.add_parser(
        "backfill",
        help="Historische Bars in die Datenbank holen -- nur, was seit dem letzten Lauf fehlt.",
    )
    backfill.add_argument(
        "--provider",
        choices=("fixture", "ibkr"),
        default=None,
        help=(
            "Uebersteuert market_data.provider nur fuer diesen Lauf. Die Konfiguration "
            "steht bewusst auf 'fixture' und wird auf dem Server nicht veraendert, "
            "damit 'git pull' keinen lokalen Diff vorfindet."
        ),
    )
    backfill.add_argument(
        "--symbols",
        default=None,
        help="Kommagetrennte Symbole statt der Watchlist.",
    )
    backfill.add_argument(
        "--limit",
        type=_positive_count,
        default=None,
        help="Nur die ersten N Aktien der Watchlist.",
    )
    backfill.add_argument(
        "--from",
        dest="from_date",
        type=date.fromisoformat,
        default=None,
        help=(
            "Ab diesem Datum (JJJJ-MM-TT) holen, statt am letzten gespeicherten Bar "
            "anzusetzen. Der Weg, eine Luecke zu fuellen, die der Bestand von sich aus "
            "nie wieder anfragen wuerde -- er kennt nur seinen juengsten Bar. "
            "Bereits gespeicherte Bars bleiben unveraendert."
        ),
    )
    backfill.add_argument(
        "--no-pacing",
        action="store_true",
        help=(
            "Ohne Mindestabstand zwischen den Anfragen. Nur fuer wenige Symbole -- "
            "IBKR sperrt die Verbindung bei mehr als 60 Anfragen in zehn Minuten."
        ),
    )
    backfill.set_defaults(handler=command_backfill)

    backtest = subparsers.add_parser(
        "backtest",
        help="Historische Signalpruefung ueber den gespeicherten Bestand (Doc 07).",
    )
    backtest.add_argument(
        "--provider",
        choices=("fixture", "ibkr"),
        default=None,
        help=(
            "Uebersteuert market_data.provider nur fuer diesen Lauf. Der Backtest "
            "braucht 'ibkr' -- ohne laufende TWS, aber mit gefuelltem Bestand."
        ),
    )
    backtest.add_argument(
        "--symbols",
        default=None,
        help="Kommagetrennte Symbole statt der Watchlist -- fuer eine gezielte Einzelpruefung.",
    )
    backtest.add_argument(
        "--limit",
        type=_positive_count,
        default=None,
        help="Nur die ersten N Aktien der Watchlist.",
    )
    backtest.add_argument(
        "--details",
        action="store_true",
        help="Zeigt je Aktie alle Signalkombinationen und Horizonte einzeln.",
    )
    backtest.set_defaults(handler=command_backtest)

    research = subparsers.add_parser(
        "research",
        help="Manueller Probelauf des Research Agent fuer ein einzelnes Symbol (ADR 0021/0022).",
    )
    research.add_argument(
        "--provider",
        choices=("fixture", "anthropic"),
        default=None,
        help=(
            "Uebersteuert research.provider nur fuer diesen Lauf. 'anthropic' loest "
            "einen echten, kostenpflichtigen API-Aufruf aus."
        ),
    )
    research.add_argument("--symbol", required=True, help="Das zu recherchierende Symbol.")
    research.add_argument(
        "--exchange",
        default="NASDAQ",
        help="Nur fuer die Anfrage an das Sprachmodell relevant, nicht persistiert.",
    )
    research.set_defaults(handler=command_research)
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
