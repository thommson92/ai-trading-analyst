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
import csv
import json
import statistics
import sys
import uuid
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.engine import Engine
from sqlalchemy.exc import ArgumentError

from ai_trading_analyst.application.backfill_history import (
    BackfillHistoryUseCase,
    SymbolBackfill,
)
from ai_trading_analyst.application.deepen_history import (
    FENSTERGROESSE_HANDELSTAGE,
    DeepenHistoryUseCase,
    DeepeningReport,
    DeepenOutcome,
    SymbolDeepening,
)
from ai_trading_analyst.application.dispatch_daily_run import (
    DispatchDailyRunUseCase,
    DispatchOutcome,
)
from ai_trading_analyst.application.measure_history_depth import (
    FENSTERGROESSE_TAGE,
    HOECHSTZAHL_FENSTER,
    DepthLimit,
    HistoryDepthReport,
    MeasureHistoryDepthUseCase,
    SymbolDepth,
)
from ai_trading_analyst.application.run_analysis import RunAnalysisUseCase
from ai_trading_analyst.application.run_backtest import BacktestUseCase, StockBacktest
from ai_trading_analyst.bootstrap import (
    app_version,
    build_agent_concurrency,
    build_analyst_recommendations_provider,
    build_backtest_params,
    build_earnings_filter_params,
    build_earnings_provider,
    build_fundamental_data_provider,
    build_ibkr_bar_source,
    build_market_data_provider,
    build_options_provider,
    build_repeat_suppression_params,
    build_research_provider,
    build_scoring_params,
    build_session_parameters,
    build_technical_analysis_params,
    build_technical_interpreter,
    build_watchlist,
    project_root,
)
from ai_trading_analyst.config.loader import ConfigError, LoadedConfig, load_config
from ai_trading_analyst.config.settings import (
    AppConfig,
    GateNotClearedError,
    LoggingConfig,
    MissingSecretError,
    Secrets,
)
from ai_trading_analyst.domain.analysis import (
    AnalysisRunSummary,
    AnalystRecommendationsProviderError,
    FundamentalDataProviderError,
    MarketDataProvider,
    MarketDataProviderError,
    OptionsDataProviderError,
    ResearchProviderError,
    Stock,
    TechnicalInterpreter,
    TechnicalInterpreterError,
    UnitOfWork,
)
from ai_trading_analyst.domain.analysts import AnalystRecommendations
from ai_trading_analyst.domain.backtesting import BacktestConfidence
from ai_trading_analyst.domain.fundamentals import (
    FundamentalSnapshot,
    Metric,
    MetricBasis,
    MetricName,
    MetricUnit,
)
from ai_trading_analyst.domain.options import OptionsAnalysis
from ai_trading_analyst.domain.research import ResearchReport
from ai_trading_analyst.domain.scheduling import (
    DispatchDecision,
    SchedulerParameters,
    TradingCalendarError,
    TradingSession,
)
from ai_trading_analyst.domain.scoring import ANALYST_BUY_SHARE_LABEL, analyst_buy_share
from ai_trading_analyst.domain.screening import (
    CandidateRuleParameters,
    IndicatorValues,
    IntradayBar,
    ScreeningStatus,
    SignalType,
    evaluate_candidate,
)
from ai_trading_analyst.domain.technical import (
    TechnicalAssessment,
    TechnicalAssessmentStatus,
    TechnicalSnapshot,
    TechnicalStatus,
    compute_technical_snapshot,
)
from ai_trading_analyst.infrastructure.anthropic.technical_interpreter import render_snapshot
from ai_trading_analyst.infrastructure.ibkr import (
    ContractSpec,
    IbkrMarketDataProvider,
    duration_in_days,
)
from ai_trading_analyst.infrastructure.ibkr.calendar import IbkrTradingCalendar
from ai_trading_analyst.infrastructure.ibkr.chain_recorder import (
    RecordingOptionChainSource,
    RohNotierungenSammler,
)
from ai_trading_analyst.infrastructure.ibkr.option_chain import OptionChainSource
from ai_trading_analyst.infrastructure.notifications import (
    NotificationChannelNotConfiguredError,
    build_notifier,
)
from ai_trading_analyst.infrastructure.persistence.dispatcher_runs import (
    SqlAlchemyDispatcherRunRepository,
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
from ai_trading_analyst.observability.logging_setup import configure_logging, get_logger
from ai_trading_analyst.presentation.report_text import render_run
from ai_trading_analyst.presentation.validation_chart import (
    build_chart_payload,
    render_chart_html,
)

_logger_cli = get_logger(__name__)

PACING_FREE_LIMIT = 20
"""So viele Symbole duerfen ohne Mindestabstand abgefragt werden -- deutlich
unter IBKRs Grenze von 60 Anfragen je zehn Minuten."""

UEBERTRAGUNG_JE_JAHRESFENSTER_SEKUNDEN = 30.0
"""Wie lange ein Jahresfenster ueber die TWS-Verbindung braucht -- gemessen.

Der erste Messlauf (ADR 0028) hat fuer 36 Anfragen ueber rund 20 Minuten
gebraucht, bei 11 Sekunden Pacing also etwa 30 Sekunden Uebertragung je
Anfrage. Ein Jahresfenster in 15-Minuten-Aufloesung sind knapp 9.500 Bars;
die wollen erst einmal ueber die Leitung.

Die Zahl ist eine Groessenordnung, keine Zusage -- sie geht ausschliesslich
in die Laufzeitvorschau ein. Ohne sie nannte die Vorschau nur die
Pacing-Pausen und war damit um den Faktor drei zu optimistisch.
"""


def _laufzeitschaetzung(anfragen: int, interval: float) -> str:
    """Wie lange der Lauf voraussichtlich dauert.

    Pacing **und** Uebertragung. Die erste Fassung dieser Vorschau zaehlte nur
    die Pausen und versprach sieben Minuten fuer einen Lauf, der zwanzig
    brauchte.
    """
    sekunden = anfragen * (interval + UEBERTRAGUNG_JE_JAHRESFENSTER_SEKUNDEN)
    if sekunden < 3600:
        return f"Laufzeit grob {sekunden / 60:.0f} Minuten, wenn jede Aktie alle Fenster nutzt."
    return f"Laufzeit grob {sekunden / 3600:.1f} Stunden, wenn jede Aktie alle Fenster nutzt."


STANDARD_TITEL_TIEFENMESSUNG = 3
"""Wieviele Titel die Tiefenmessung aus der **Watchlist** nimmt.

Die Frage nach der Anbietertiefe beantworten wenige Titel so gut wie alle,
und die ganze Watchlist kostete unter Pacing Stunden. Gilt nur fuer die
Watchlist: Ausdruecklich genannte Symbole werden nie gekuerzt."""


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


_offene_engines: list[Engine] = []
"""Die in diesem Aufruf geoeffneten Engines, damit ``main`` sie wieder
schliessen kann.

Neun Kommandos oeffnen eine Datenbankverbindung, und ihre Rumpfe haben je ein
Dutzend Ruecksprungpunkte -- ein ``with`` je Kommando haette jeden davon
umschliessen muessen. Das Ende des Kommandos ist die eine Stelle, an der die
Verbindung sicher nicht mehr gebraucht wird.

Im echten Aufruf loest das Prozessende das ohnehin. Bemerkbar wird es dort,
wo viele Kommandos in **einem** Interpreter laufen: in der Testsuite, die
seit dem strengen Warnungsfilter genau darueber stolpert."""


def _alle_engines_schliessen() -> None:
    while _offene_engines:
        _offene_engines.pop().dispose()


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
    _offene_engines.append(engine)
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


_VERTIEFUNG_TEXT = {
    DeepenOutcome.TARGET_REACHED: "Ziel erreicht",
    DeepenOutcome.ALREADY_DEEP_ENOUGH: "war schon tief genug",
    DeepenOutcome.PROVIDER_EXHAUSTED: "IBKR gab nicht mehr her",
    DeepenOutcome.WINDOW_LIMIT: "Fensterobergrenze erreicht",
    DeepenOutcome.ERROR: "FEHLER",
}


def _print_deepen_progress(index: int, total: int, ergebnis: SymbolDeepening) -> None:
    prefix = f"[{index:>3}/{total}] {ergebnis.symbol:<8}"
    if ergebnis.failed:
        print(f"{prefix} FEHLER   {ergebnis.error}", flush=True)
        return
    if ergebnis.outcome is DeepenOutcome.ALREADY_DEEP_ENOUGH:
        print(f"{prefix} uebersprungen -- war schon tief genug", flush=True)
        return
    zurueck = ergebnis.earliest_after.date().isoformat() if ergebnis.earliest_after else "--"
    print(
        f"{prefix} zurueck bis {zurueck}  ({ergebnis.windows} Fenster, "
        f"{ergebnis.stored_bars} neue Bars)  {_VERTIEFUNG_TEXT[ergebnis.outcome]}",
        flush=True,
    )


def _print_deepen_report(bericht: DeepeningReport, jetzt: datetime, dauer: float) -> None:
    print(f"\n{len(bericht.results)} Aktien in {dauer / 60:.0f} min")
    print(f"  neue Bars                    {bericht.stored_bars}")
    print(f"  bereits tief genug           {len(bericht.untouched)}")
    print(f"  Fehler                       {len(bericht.failures)}")

    if bericht.failures:
        print(f"\nFehlgeschlagen: {', '.join(item.symbol for item in bericht.failures)}")
        print("  Ein erneuter Lauf setzt bei jeder dieser Aktien dort an, wo er aufhoerte.")

    zu_kurz = tuple(
        item for item in bericht.short_of_target if item.outcome is not DeepenOutcome.ERROR
    )
    if zu_kurz:
        # Kein Fehler, aber auch kein erfuellter Anspruch -- und genau das
        # darf nicht in einer Gesamtzahl untergehen.
        print(f"\nUnter dem Zielzeitraum ({len(zu_kurz)}):")
        for item in zu_kurz[:20]:
            tage = item.depth_days(jetzt)
            jahre = f"{tage / 365:.1f} Jahre" if tage is not None else "keine Bars"
            print(f"  {item.symbol:<8} {jahre:<12} {_VERTIEFUNG_TEXT[item.outcome]}")
        if len(zu_kurz) > 20:
            print(f"  ... und {len(zu_kurz) - 20} weitere")
        print(
            "  Bei einer Neuemission ist das erwartbar und kein Fehler: Die Kennzahlen\n"
            "  dieser Aktien tragen ihren tatsaechlichen history_start."
        )
    if not zu_kurz and not bericht.failures:
        print(f"\nAlle Aktien decken {bericht.target_years} Jahre ab.")
    elif not zu_kurz:
        # Ueber eine gescheiterte Aktie ist nichts bekannt -- ein
        # "alle decken ab" stuende sonst unmittelbar unter der Liste der
        # Fehlschlaege und widerspraeche ihr.
        print(
            f"\nAlle **durchgelaufenen** Aktien decken {bericht.target_years} Jahre ab. "
            f"Ueber die {len(bericht.failures)} fehlgeschlagenen sagt der Lauf nichts."
        )


def command_deepen_history(args: argparse.Namespace) -> int:
    """Fuellt den Bestand rueckwaerts auf ``backtesting.history_years`` auf.

    Der Batch aus ADR 0014 (E3), beschlossen mit ADR 0028. Laeuft fuer eine
    volle Watchlist stundenlang und ist genau dafuer gebaut: Jedes Fenster
    wird sofort abgelegt, ein Abbruch kostet nichts, ein erneuter Start setzt
    dort an, wo der letzte aufhoerte.
    """
    loaded = load_config(args.config)
    config = loaded.config
    configure_logging(LoggingConfig(level="INFO", format="console"))

    if args.provider is not None:
        market_data = config.market_data.model_copy(update={"provider": args.provider})
        config = config.model_copy(update={"market_data": market_data})

    if config.market_data.provider != "ibkr":
        print(
            "market_data.provider steht auf "
            f"'{config.market_data.provider}'. Der Tiefen-Backfill holt Daten von der TWS -- "
            "entweder '--provider ibkr' angeben oder die Konfiguration umstellen.",
            file=sys.stderr,
        )
        return 2

    zieljahre = args.years if args.years is not None else config.backtesting.history_years

    watchlist = _watchlist_from(args, config, loaded.source_path)
    if watchlist is None:
        return 2
    if args.limit is not None:
        watchlist = watchlist[: args.limit]

    if args.no_pacing:
        ibkr = config.market_data.ibkr.model_copy(update={"minimum_request_interval_seconds": 0.0})
        market_data = config.market_data.model_copy(update={"ibkr": ibkr})
        config = config.model_copy(update={"market_data": market_data})

    engine = _open_database()
    if engine is None:
        return 2
    session_factory = build_session_factory(engine)

    def uow_factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    bar_source = build_ibkr_bar_source(config)
    use_case = DeepenHistoryUseCase(
        bar_source,
        uow_factory,
        target_years=zieljahre,
        window_trading_days=args.window_days,
    )

    interval = config.market_data.ibkr.minimum_request_interval_seconds
    anfragen = len(watchlist) * use_case.maximum_windows
    if interval <= 0 and anfragen > PACING_FREE_LIMIT:
        print(
            f"--no-pacing ist hier nicht zulaessig: {len(watchlist)} Aktien mal hoechstens "
            f"{use_case.maximum_windows} Fenster sind bis zu {anfragen} Anfragen, IBKR sperrt "
            f"die Verbindung ab 60 je zehn Minuten. Hoechstens {PACING_FREE_LIMIT} Anfragen "
            "ohne Abstand.",
            file=sys.stderr,
        )
        bar_source.close()
        return 2

    print(
        f"{len(watchlist)} Aktien auf {zieljahre} Jahre, hoechstens "
        f"{use_case.maximum_windows} Fenster je {args.window_days} Handelstage, "
        f"TWS {config.market_data.ibkr.host}:{config.market_data.ibkr.port} "
        f"(Client-ID {config.market_data.ibkr.client_id}), Abstand {interval:g} s\n"
    )
    print(
        f"Bis zu {anfragen} Anfragen. {_laufzeitschaetzung(anfragen, interval)}\n"
        "Ein Abbruch ist unkritisch -- jedes Fenster ist sofort abgelegt, ein erneuter\n"
        "Lauf setzt dort an, wo dieser aufhoert.\n"
    )

    started = datetime.now(UTC)
    try:
        bericht = use_case.execute(watchlist, on_progress=_print_deepen_progress)
    except KeyboardInterrupt:
        print(
            "\nAbgebrochen -- der bisherige Bestand bleibt erhalten, "
            "ein erneuter Lauf setzt dort an.",
            file=sys.stderr,
        )
        return 130
    finally:
        bar_source.close()

    _print_deepen_report(bericht, datetime.now(UTC), (datetime.now(UTC) - started).total_seconds())
    return 1 if bericht.failures else 0


def export_bars_to_csv(
    ziel: Path, symbol: str, bars: Sequence[IntradayBar], since: date | None
) -> Path | None:
    """Schreibt die Bars einer Aktie und liefert die angelegte Datei.

    ``None`` heisst: Nach ``since`` blieb nichts uebrig, also wurde nichts
    geschrieben. Die Reihenfolge ist wesentlich -- **erst filtern, dann auf
    Leere pruefen.** Andersherum entstuende bei einem Zeitraum ohne Bars eine
    Datei mit nichts als der Kopfzeile; der Golden Master naehme sie als
    Fall an und scheiterte an der leeren Kerzenreihe.
    """
    if since is not None:
        grenze = datetime.combine(since, time.min, tzinfo=UTC)
        bars = [bar for bar in bars if bar.start >= grenze]
    if not bars:
        return None
    datei = ziel / f"{symbol.lower()}.bars.csv"
    zeilen = ["start,open,high,low,close,volume"]
    zeilen.extend(
        f"{bar.start.isoformat()},{bar.open:.4f},{bar.high:.4f},"
        f"{bar.low:.4f},{bar.close:.4f},{bar.volume:.0f}"
        for bar in bars
    )
    datei.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    return datei


def command_export_bars(args: argparse.Namespace) -> int:
    """Schreibt gespeicherte Bars als CSV heraus.

    Gedacht fuer den Golden Master (``tests/golden``): Dessen eingefrorene
    Reihen sind erzeugt, nicht gemessen, weil der reale Bestand nur auf dem
    Server liegt. Mit diesem Kommando laesst sich dort ein echter Ausschnitt
    ziehen und danebenlegen -- das Format ist dasselbe, und der Golden
    Master nimmt jede weitere ``*.bars.csv`` von allein als Fall auf.

    Liest nur; der Bestand bleibt unveraendert.
    """
    load_config(args.config)
    configure_logging(LoggingConfig(level="INFO", format="console"))

    symbole = tuple(symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip())
    if not symbole:
        print(f"--symbols enthaelt kein Symbol: '{args.symbols}'", file=sys.stderr)
        return 2

    ziel = Path(args.output)
    if not ziel.is_dir():
        print(f"--output ist kein Verzeichnis: {ziel}", file=sys.stderr)
        return 2

    engine = _open_database()
    if engine is None:
        return 2
    session_factory = build_session_factory(engine)

    geschrieben = 0
    for symbol in symbole:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            bars = uow.intraday_bars.list_for(symbol)
        datei = export_bars_to_csv(ziel, symbol, bars, args.since)
        if datei is None:
            print(
                f"{symbol}: keine gespeicherten Bars im gewaehlten Zeitraum -- "
                "keine Datei angelegt",
                file=sys.stderr,
            )
            continue
        print(f"{symbol}: {datei}")
        geschrieben += 1

    return 0 if geschrieben else 1


_GRENZE_TEXT = {
    DepthLimit.PROVIDER_EXHAUSTED: "IBKR gab nichts mehr her -- gemessene Tiefe",
    DepthLimit.NO_PROGRESS: "IBKR kam nicht weiter zurueck -- gemessene Tiefe",
    DepthLimit.WINDOW_LIMIT: "Fensterobergrenze erreicht -- mindestens",
    DepthLimit.ERROR: "abgebrochen -- mindestens",
}


def _print_depth_progress(index: int, total: int, ergebnis: SymbolDepth) -> None:
    prefix = f"[{index:>3}/{total}] {ergebnis.symbol:<8}"
    if ergebnis.failed:
        print(f"{prefix} FEHLER  {ergebnis.error}", flush=True)
        return
    aeltester = ergebnis.earliest.date().isoformat() if ergebnis.earliest else "keine Bars"
    print(
        f"{prefix} zurueck bis {aeltester}  "
        f"({ergebnis.windows} Fenster, {ergebnis.received_bars} Bars)",
        flush=True,
    )


def _print_depth_report(bericht: HistoryDepthReport, anspruch_jahre: int) -> None:
    """Der Bericht, aus dem die Entscheidung zu E2 gefaellt wird.

    Ausgewiesen wird, was ankam -- und ob es eine gemessene Tiefe oder nur
    eine Untergrenze ist. Die Zusammenfassung nennt bewusst die **flachste**
    Aktie: Sie bestimmt, ab wann eine Kennzahl ueber die Watchlist hinweg
    vergleichbar ist.
    """
    jetzt = bericht.measured_at
    print(
        f"\nTiefenmessung {bericht.bar_minutes}-Minuten-Bars, "
        f"Fenster je {bericht.window_days} Tage, {jetzt.date().isoformat()}\n"
    )
    print(f"{'Symbol':<8} {'aeltester Bar':<14} {'Tage':>6} {'Jahre':>6}  Grenze")
    for ergebnis in bericht.results:
        tage = ergebnis.depth_days(jetzt)
        aeltester = ergebnis.earliest.date().isoformat() if ergebnis.earliest else "--"
        tage_text = str(tage) if tage is not None else "--"
        jahre_text = f"{tage / 365:.1f}" if tage is not None else "--"
        print(
            f"{ergebnis.symbol:<8} {aeltester:<14} {tage_text:>6} {jahre_text:>6}  "
            f"{_GRENZE_TEXT[ergebnis.limit]}"
        )
        if ergebnis.error is not None:
            print(f"{'':<8} {ergebnis.error}")

    flachste = bericht.shallowest
    tage = flachste.depth_days(jetzt) if flachste is not None else None
    if flachste is None or tage is None:
        print("\nKeine einzige Aktie hat Bars geliefert -- die Messung sagt nichts aus.")
        return

    print(
        f"\nFlachste **gemessene** Historie: {flachste.symbol} mit {tage} Tagen "
        f"({tage / 365:.1f} Jahre), Grenze {flachste.limit.value}."
    )
    if any(ergebnis.is_lower_bound for ergebnis in bericht.results):
        print(
            "Mindestens ein Ergebnis ist nur eine **Untergrenze** (Fensterobergrenze "
            "oder Fehler). Die tatsaechliche Tiefe kann groesser sein."
        )
    ohne_messung = bericht.unmeasured
    if ohne_messung:
        # Ohne diese Zeile stuetzte ein Titel, fuer den nichts ankam, ein
        # Urteil ueber die Watchlist, an dem er nicht beteiligt war.
        print(
            f"\nOhne einen einzigen Bar ({len(ohne_messung)}): "
            + ", ".join(ergebnis.symbol for ergebnis in ohne_messung)
            + "\n  Ueber ihre Tiefe sagt die Messung nichts. Das Urteil unten gilt nur "
            "fuer die gemessenen Titel."
        )
    anspruch_tage = anspruch_jahre * 365
    if tage < anspruch_tage:
        print(
            f"\nDer Anspruch aus backtesting.history_years ({anspruch_jahre} Jahre = "
            f"{anspruch_tage} Tage) wird von dieser Messung **nicht** gedeckt."
        )
    elif ohne_messung:
        print(
            f"\nDie gemessenen Titel decken {anspruch_jahre} Jahre ab. Ob der Anspruch "
            "insgesamt haelt, ist damit **nicht** beantwortet -- erst sind die Titel "
            "ohne Bars zu klaeren."
        )
    else:
        print(f"\nDer Anspruch von {anspruch_jahre} Jahren ist erreichbar.")
    print(
        "\nDie Messung hat nichts abgelegt. Ueber E2 (Backfill vertiefen oder Anspruch "
        "senken) entscheidet dieser Bericht, nicht dieses Kommando."
    )


def command_history_depth(args: argparse.Namespace) -> int:
    """Misst, wie weit IBKR die Historie einer Aktie hergibt (E2).

    Schreibt nichts und braucht deshalb keine Datenbank. Das Kommando
    beantwortet eine offene Frage, es holt keinen Bestand -- siehe
    ``MeasureHistoryDepthUseCase``.
    """
    loaded = load_config(args.config)
    config = loaded.config
    configure_logging(LoggingConfig(level="INFO", format="console"))

    if args.provider is not None:
        market_data = config.market_data.model_copy(update={"provider": args.provider})
        config = config.model_copy(update={"market_data": market_data})

    if config.market_data.provider != "ibkr":
        print(
            "market_data.provider steht auf "
            f"'{config.market_data.provider}'. Die Tiefenmessung fragt die TWS -- "
            "entweder '--provider ibkr' angeben oder die Konfiguration umstellen.",
            file=sys.stderr,
        )
        return 2

    watchlist = _watchlist_from(args, config, loaded.source_path)
    if watchlist is None:
        return 2
    if args.limit is not None:
        watchlist = watchlist[: args.limit]
    elif args.symbols is None:
        # Nur die Watchlist wird gekuerzt. Wer Symbole ausdruecklich nennt,
        # bekommt sie alle gemessen -- eine stille Kuerzung entschiede
        # hinter dem Ruecken des Nutzers mit, welche Aktie am Ende die
        # "flachste Historie" des Berichts stellt.
        watchlist = watchlist[:STANDARD_TITEL_TIEFENMESSUNG]

    interval = config.market_data.ibkr.minimum_request_interval_seconds
    if args.no_pacing:
        ibkr = config.market_data.ibkr.model_copy(update={"minimum_request_interval_seconds": 0.0})
        market_data = config.market_data.model_copy(update={"ibkr": ibkr})
        config = config.model_copy(update={"market_data": market_data})
        interval = 0.0

    # Anders als beim Backfill haengt die Zahl der Anfragen nicht an der Zahl
    # der Symbole allein: Jede Aktie kostet bis zu '--max-windows' Anfragen.
    anfragen = len(watchlist) * args.max_windows
    if interval <= 0 and anfragen > PACING_FREE_LIMIT:
        print(
            f"--no-pacing ist hier nicht zulaessig: {len(watchlist)} Aktien mal hoechstens "
            f"{args.max_windows} Fenster sind bis zu {anfragen} Anfragen, IBKR sperrt die "
            f"Verbindung ab 60 je zehn Minuten. Hoechstens {PACING_FREE_LIMIT} Anfragen "
            "ohne Abstand.",
            file=sys.stderr,
        )
        return 2

    bar_source = build_ibkr_bar_source(config)
    use_case = MeasureHistoryDepthUseCase(
        bar_source,
        window_days=args.window_days,
        maximum_windows=args.max_windows,
    )

    print(
        f"{len(watchlist)} Aktien, hoechstens {args.max_windows} Fenster je "
        f"{args.window_days} Tage, TWS {config.market_data.ibkr.host}:"
        f"{config.market_data.ibkr.port} (Client-ID {config.market_data.ibkr.client_id}), "
        f"Abstand {interval:g} s\n"
    )
    print(f"Bis zu {anfragen} Anfragen. {_laufzeitschaetzung(anfragen, interval)}\n")
    try:
        bericht = use_case.execute(
            watchlist,
            config.market_data.ibkr.native_bar_minutes,
            on_progress=_print_depth_progress,
        )
    except KeyboardInterrupt:
        print("\nAbgebrochen -- die Messung legt nichts ab, es bleibt nichts zurueck.")
        return 130
    finally:
        bar_source.close()

    _print_depth_report(bericht, config.backtesting.history_years)
    return 1 if bericht.failures else 0


def boersentag(jetzt: datetime, timezone: str) -> date:
    """Der Handelstag, in dem ein Zeitpunkt liegt.

    Nicht ``jetzt.date()``: Das waere das UTC-Datum. Ein Lauf um 22:30 New
    Yorker Zeit liegt bereits im naechsten UTC-Tag -- ein kuenftiger
    Handelstag fiele dadurch aus der Zaehlung, und genau an der Fenstergrenze
    kippt das Ergebnis. Der Fehler ist einseitig: UTC liegt gegenueber New
    York nie zurueck, also wird immer zu **wenig** gezaehlt.

    Steht als eigene Funktion da, weil der Unterschied sich sonst nur zu
    bestimmten Tageszeiten zeigt -- ein Test durch das ganze Kommando waere
    stundenabhaengig gruen.
    """
    return jetzt.astimezone(ZoneInfo(timezone)).date()


def erforderliche_handelstage(fenster_kerzen: int, kerzen_je_tag: int) -> int:
    """Wie weit ein Kalender reichen muss, um das Ausschlussfenster zu
    entscheiden.

    Nicht ``ceil(kerzen / je_tag)``, sondern eine Stelle mehr. Der Filter
    schliesst aus bei ``trading_days * je_tag <= fenster_kerzen``
    (``domain/earnings/filter.py``); "nicht ausgeschlossen" beginnt also erst
    beim naechsten Handelstag danach. Ein Kalender, der nur bis
    ``fenster_kerzen // je_tag`` reicht, kann den Grenzfall nicht
    unterscheiden -- er sieht jeden Termin als "im Fenster".

    Mit den Vorgabewerten (20 Kerzen, 2 je Tag) sind das **11**, nicht 10.
    ``ceil`` faellt nur bei ungeraden Fenstern zufaellig richtig aus, was den
    Fehler tarnt.
    """
    if kerzen_je_tag < 1:
        raise ValueError(f"kerzen_je_tag ({kerzen_je_tag}) muss mindestens 1 sein")
    return fenster_kerzen // kerzen_je_tag + 1


def command_calendar_reach(args: argparse.Namespace) -> int:
    """Misst, wie weit der TWS-Kalender in die Zukunft reicht (E4).

    Der Earnings-Filter zaehlt Handelstage bis zum naechsten Termin heute
    ueber eine Wochentagsnaeherung: Montag bis Freitag gelten als
    Handelstage, Feiertage bleiben unberuecksichtigt (ADR 0020, L2/L3). Die
    Naeherung zaehlt damit **zu hoch** -- der Termin erscheint weiter weg,
    und der Filter schliesst seltener aus als er sollte.

    Ob der echte Kalender sie ersetzen kann, haengt an einer Zahl: Reicht
    ``liquidHours`` so weit voraus wie das Ausschlussfenster? Diese Frage
    beantwortet dieses Kommando. Es entscheidet sie nicht -- das tut ein ADR.

    Schreibt nichts und braucht keine Datenbank.
    """
    loaded = load_config(args.config)
    config = loaded.config
    configure_logging(LoggingConfig(level="INFO", format="console"))

    if args.provider is not None:
        market_data = config.market_data.model_copy(update={"provider": args.provider})
        config = config.model_copy(update={"market_data": market_data})

    if config.market_data.provider != "ibkr":
        print(
            "market_data.provider steht auf "
            f"'{config.market_data.provider}'. Die Kalenderreichweite fragt die TWS -- "
            "entweder '--provider ibkr' angeben oder die Konfiguration umstellen.",
            file=sys.stderr,
        )
        return 2

    watchlist = _watchlist_from(args, config, loaded.source_path)
    if watchlist is None:
        return 2
    referenz = watchlist[0]

    bar_source = build_ibkr_bar_source(config)
    try:
        sitzungen = IbkrTradingCalendar(bar_source, referenz).sessions()
    except TradingCalendarError as error:
        print(f"Handelszeiten nicht lesbar: {error}", file=sys.stderr)
        return 1
    finally:
        bar_source.close()

    return _print_calendar_reach(
        sitzungen,
        symbol=referenz.symbol,
        fenster_kerzen=config.earnings_filter.configured_exclusion_candles,
        kerzen_je_tag=build_session_parameters(config).candles_per_day,
        vorlauf_kalendertage=config.earnings_filter.lookahead_calendar_days,
        heute=boersentag(datetime.now(UTC), config.market.timezone),
    )


def _print_calendar_reach(
    sitzungen: Mapping[date, TradingSession | None],
    *,
    symbol: str,
    fenster_kerzen: int,
    kerzen_je_tag: int,
    vorlauf_kalendertage: int,
    heute: date,
) -> int:
    """Getrennt vom Kommando, damit die Ausgabe ohne TWS pruefbar ist.

    Nimmt die Sitzungen als einfache Abbildung statt des Kalenderobjekts:
    Damit ist strukturell sichtbar, dass die Ausgabe keine offene Verbindung
    mehr braucht -- ``bar_source`` ist zu diesem Zeitpunkt schon geschlossen.

    ``heute`` wird hereingereicht statt hier gelesen. Sonst haengt das
    Ergebnis der Tests am Kalenderdatum ihres Laufs, und ein Testfall mit
    festen Daten faellt Monate spaeter still um.

    Alles nach den Sitzungen ist benannt zu uebergeben: Drei aufeinander
    folgende ``int`` liessen sich sonst vertauschen, ohne dass mypy es merkt.
    """
    tage = sorted(sitzungen)
    benoetigt = erforderliche_handelstage(fenster_kerzen, kerzen_je_tag)
    kuenftig = [tag for tag in tage if tag > heute]
    handelstage = [tag for tag in kuenftig if sitzungen[tag] is not None]
    ruhetage = [tag for tag in kuenftig if sitzungen[tag] is None]

    print(f"Kalenderreichweite ueber {symbol} (Referenzkontrakt der Watchlist)\n")
    print(f"  Abgedeckt:              {tage[0].isoformat()} bis {tage[-1].isoformat()}")
    print(f"  Tage insgesamt:         {len(tage)}")
    print(f"  Bezugstag (Boerse):     {heute.isoformat()}")
    print(f"  Kuenftige Handelstage:  {len(handelstage)}")
    if ruhetage:
        print(f"  Kuenftige Ruhetage:     {', '.join(tag.isoformat() for tag in ruhetage)}")
    else:
        print("  Kuenftige Ruhetage:     keine im abgedeckten Fenster")

    print(
        f"\n  Gebraucht werden {benoetigt} Handelstage: Der Filter schliesst aus bis "
        f"einschliesslich {fenster_kerzen} Kerzen ({kerzen_je_tag} je Tag), "
        "die Entscheidung faellt also erst einen Handelstag danach."
    )

    if len(handelstage) < benoetigt:
        print(
            f"\n  ERGEBNIS: Der Kalender reicht NICHT weit genug "
            f"({len(handelstage)} von {benoetigt} Handelstagen). "
            "Die Wochentagsnaeherung bleibt -- ADR zu E4 auf diesem Befund, nicht "
            "auf der Konservativitaets-Annahme des Audits."
        )
        return 0

    print(
        "\n  ERGEBNIS: Der Kalender reicht fuer die Ausschlussentscheidung. Die "
        "Wochentagsnaeherung laesst sich dafuer durch die echten Nichthandelstage "
        "ersetzen (E4, Weg c)."
    )
    if len(handelstage) < vorlauf_kalendertage:
        print(
            f"\n  ABER: Das Feld 'candles_until_earnings' wird auch fuer nicht "
            f"ausgeschlossene Titel gespeichert, und Termine werden bis "
            f"{vorlauf_kalendertage} Kalendertage voraus geholt "
            "(earnings_filter.lookahead_calendar_days). So weit reicht der "
            "Kalender nicht. Fuer die gespeicherte Zahl bliebe die Naeherung -- das "
            "gehoert in das ADR, nicht in dieses Kommando."
        )
    return 0


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
        required_crossing_signals=config.screening.required_crossing_signals,
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
        f"{stock.symbol}: {auswertbar} auswertbare Horizonte von {len(stock.results)} Kombinationen"
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
        required_crossing_signals=config.screening.required_crossing_signals,
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
        # Beide Versionen, nicht nur die des Prompts: Die Abdeckungsstufe
        # entsteht aus der Verfahrensversion, und ohne sie laesst sich ein
        # gemeldetes BROAD nicht der Regel zuordnen, unter der es entstand.
        verfahren = report.analysis_version or "unbekannt"
        print(
            f"  Modell: {report.model} (Prompt-Version {report.prompt_version}, "
            f"Verfahren {verfahren})"
        )
    if report.confidence is not None:
        print(f"  Confidence: {report.confidence:.2f}")
    if report.coverage is not None:
        print(f"  Abdeckung: {report.coverage.value}")
    if report.evidence is not None:
        evidence = report.evidence
        print(
            f"  Belege: {evidence.distinct_sources} Quellen, "
            f"{evidence.successful_fetches} Abrufe, "
            f"{evidence.rejected_tool_calls} abgelehnte Werkzeugaufrufe, "
            f"{evidence.dropped_citations} verworfene Zitate"
        )
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
            rang = citation.source_rank.value
            alter = f", Alter laut Anbieter: {citation.source_age}" if citation.source_age else ""
            print(
                f"    - [{rang} / {citation.license_class.value}] "
                f"{citation.title} ({citation.url}){alter}"
            )
            if citation.cited_text:
                print(f'      "{citation.cited_text}"')


def _format_optional(value: float | None, *, digits: int = 2, suffix: str = "") -> str:
    """Fehlende Werte bleiben als solche sichtbar.

    Ein Strich statt einer 0,00: Der Unterschied zwischen 'nicht berechenbar'
    und 'berechnet und null' darf in der Ausgabe nicht verschwinden
    (CLAUDE.md: keine erfundenen Werte).
    """
    return "--" if value is None else f"{value:.{digits}f}{suffix}"


def _print_technical_snapshot(symbol: str, snapshot: TechnicalSnapshot) -> None:
    print(f"{symbol}: {snapshot.status.value} (Verfahren {snapshot.analysis_version})")
    if snapshot.reason:
        print(f"  Grund: {snapshot.reason}")
    if snapshot.status is not TechnicalStatus.COMPLETED:
        return

    if snapshot.parameters is not None:
        # Wer die Parameter nach Doc 14 nachzieht, soll in derselben Ausgabe
        # sehen, welche gerade gewirkt haben.
        print(
            "  Zonenparameter: "
            f"Toleranz {snapshot.parameters['zone_tolerance_pct'] * 100:.2f} %, "
            f"Reichweite {snapshot.parameters['pivot_reach']:.0f}, "
            f"min. {snapshot.parameters['min_touches']:.0f} Beruehrungen, "
            f"Fenster {snapshot.parameters['history_candles']:.0f} Kerzen"
        )
    if snapshot.candle_timestamp is not None:
        print(f"  Entscheidungskerze: {snapshot.candle_timestamp.isoformat()}")
    print(f"  Schlusskurs: {_format_optional(snapshot.close)}")
    trend = "--" if snapshot.trend is None else snapshot.trend.value
    print(f"  Trend: {trend}")
    print(f"  RSI: {_format_optional(snapshot.rsi, digits=1)}")
    print(
        f"  EMA5: {_format_optional(snapshot.ema5)} "
        f"({_format_optional(_as_percent(snapshot.distance_to_ema5_pct), digits=2, suffix=' %')})"
    )
    print(
        f"  EMA20: {_format_optional(snapshot.ema20)} "
        f"({_format_optional(_as_percent(snapshot.distance_to_ema20_pct), digits=2, suffix=' %')})"
    )
    print(
        f"  ATR: {_format_optional(snapshot.atr)} "
        f"({_format_optional(_as_percent(snapshot.atr_pct), digits=2, suffix=' %')})"
    )
    if snapshot.recent_high_at is not None and snapshot.recent_low_at is not None:
        print(
            f"  Juengstes Hoch: {_format_optional(snapshot.recent_high)} "
            f"am {snapshot.recent_high_at.date().isoformat()}"
        )
        print(
            f"  Juengstes Tief: {_format_optional(snapshot.recent_low)} "
            f"am {snapshot.recent_low_at.date().isoformat()}"
        )

    _print_chance_risk(snapshot)

    if not snapshot.zones:
        print("  Zonen: keine mehrfach getestete Preisregion im Fenster")
        return
    print("  Zonen (nach Abstand zum Kurs):")
    for zone in snapshot.zones:
        print(
            f"    {zone.kind.value:<13} {zone.lower:.2f} - {zone.upper:.2f}  "
            f"{zone.strength.value:<8} "
            f"{_plural(zone.touch_count, 'Beruehrung', 'Beruehrungen')} aus "
            f"{_plural(zone.pivot_count, 'Wendepunkt', 'Wendepunkten')}, zuletzt "
            f"{zone.last_confirmed_at.date().isoformat()}, "
            f"Abstand {zone.distance_pct * 100:.2f} %"
        )


def _print_chance_risk(snapshot: TechnicalSnapshot) -> None:
    """Weg nach unten, Weg nach oben und ihr Verhaeltnis (ADR 0026).

    Steht bewusst *vor* der Zonenliste: Es ist die Zusammenfassung, aus der
    die Liste darunter die Herleitung liefert.
    """
    print(
        "  Bis zur naechsten Unterstuetzung: "
        f"{_format_optional(_as_percent(snapshot.downside_to_support_pct), digits=2, suffix=' %')}"
    )
    print(
        "  Bis zum naechsten Widerstand:     "
        f"{_format_optional(_as_percent(snapshot.upside_to_resistance_pct), digits=2, suffix=' %')}"
    )
    if snapshot.chance_risk_ratio is None:
        # Kein Ersatzwert: Fehlt eine der beiden Seiten, gibt es kein
        # Verhaeltnis -- und eine Null saehe wie ein sehr schlechtes Setup aus.
        print("  Chance/Risiko:                   -- (eine Seite ohne Zone)")
    else:
        print(f"  Chance/Risiko:                   {snapshot.chance_risk_ratio:.2f}")


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _as_percent(value: float | None) -> float | None:
    return None if value is None else value * 100


def _print_technical_assessment(
    symbol: str, assessment: TechnicalAssessment, snapshot: TechnicalSnapshot | None = None
) -> None:
    """Die KI-Einordnung (ADR 0026), im Anschluss an den Snapshot.

    Eingerueckt unter demselben Symbol, damit beim Gegenpruefen sichtbar
    bleibt, worauf sie sich bezieht -- und damit auffaellt, wenn die Worte
    nicht zu den Zahlen darueber passen.
    """
    # Auch die Verfahrensversion, aus demselben Grund wie beim Research-Bericht:
    # Die eingeordneten Zahlen stammen aus einem bestimmten Stand der
    # deterministischen Auswertung. Ohne ihn laesst sich eine Einordnung
    # spaeter nicht mehr dem Verfahren zuordnen, auf dem sie beruht.
    verfahren = assessment.interpreted_analysis_version or "unbekannt"
    herkunft = (
        ""
        if assessment.model is None
        else f" -- {assessment.model}, Prompt {assessment.prompt_version}, Verfahren {verfahren}"
    )
    print(f"  Einordnung: {assessment.status.value}{herkunft}")
    if assessment.reason:
        print(f"    Grund: {assessment.reason}")
    if assessment.status is not TechnicalAssessmentStatus.COMPLETED:
        return

    def _stufe(bezeichnung: str, wert: object, zusatz: str = "") -> None:
        gezeigt = "--" if wert is None else getattr(wert, "value", wert)
        print(f"    {bezeichnung:<24} {gezeigt}{zusatz}")

    _stufe("Trendstaerke:", assessment.trend_strength)
    _stufe("Breakout:", assessment.breakout_quality)
    _stufe("Momentum:", assessment.momentum_state)
    _stufe("Fehlsignalrisiko:", assessment.false_signal_risk)
    # Die berechnete Zahl daneben: Steht dort nur "--", laesst sich nicht
    # unterscheiden, ob das Verhaeltnis fehlte oder ob das Modell nichts dazu
    # gesagt hat -- und genau das war beim ersten Lauf der Fall.
    gerechnet = None if snapshot is None else snapshot.chance_risk_ratio
    zusatz = "" if gerechnet is None else f"  (berechnet: {gerechnet:.2f})"
    _stufe("Chance/Risiko:", assessment.risk_reward_rating, zusatz)
    _stufe("Swing-Einstieg:", assessment.swing_entry_plausibility)
    if assessment.confidence is not None:
        print(f"    {'Konfidenz:':<24} {assessment.confidence:.2f}")
    if assessment.summary:
        print(f"    Fazit: {assessment.summary}")
    for risiko in assessment.false_signal_risks:
        print(f"    Risiko: {risiko}")


def command_chart(args: argparse.Namespace) -> int:
    """Schreibt den Validierungschart als HTML-Datei.

    Braucht wie der Backtest den gespeicherten Bestand: Der Chart soll den
    Verlauf zeigen, auf dem auch gerechnet wurde, nicht einen frisch
    abgerufenen.
    """
    loaded = load_config(args.config)
    config = loaded.config
    indicators = config.require_indicators()
    configure_logging(LoggingConfig(level="INFO", format="console"))

    if args.provider is not None:
        market_data = config.market_data.model_copy(update={"provider": args.provider})
        config = config.model_copy(update={"market_data": market_data})

    market_data = config.market_data.model_copy(update={"source": "stored"})
    config = config.model_copy(update={"market_data": market_data})

    ziel = Path(args.output)
    ziel.mkdir(parents=True, exist_ok=True)

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
        required_crossing_signals=config.screening.required_crossing_signals,
        signal_lookback_previous_candles=config.screening.signal_lookback_previous_candles,
        warmup_candles=indicators.warmup_candles,
    )

    gewuenscht = {
        symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()
    }
    if not gewuenscht:
        print(f"--symbols enthaelt kein Symbol: '{args.symbols}'", file=sys.stderr)
        return 2

    geschrieben: list[Path] = []
    try:
        stocks = [stock for stock in provider.list_stocks() if stock.symbol in gewuenscht]
        fehlend = gewuenscht - {stock.symbol for stock in stocks}
        if fehlend:
            print(
                f"Nicht in der Watchlist gefunden: {', '.join(sorted(fehlend))}",
                file=sys.stderr,
            )
        if not stocks:
            return 2

        for stock in stocks:
            try:
                series = provider.get_candle_series(stock)
            except MarketDataProviderError as fehler:
                print(f"{stock.symbol}: {fehler}", file=sys.stderr)
                continue
            payload = build_chart_payload(stock.symbol, series, rule)
            datei = ziel / f"signalchart-{stock.symbol.lower()}.html"
            datei.write_text(render_chart_html(payload), encoding="utf-8")
            geschrieben.append(datei)
            print(
                f"{stock.symbol}: {len(series)} Kerzen, "
                f"{payload['entscheidungspunkte']} Entscheidungspunkte, "
                f"{payload['treffer']} Treffer in {payload['episoden']} Episoden, "
                f"{payload['verworfen']} an einer Torbedingung verworfen "
                f"-> {datei}"
            )
    finally:
        if isinstance(provider, IbkrMarketDataProvider):
            provider.close()

    return 0 if geschrieben else 1


def command_technical(args: argparse.Namespace) -> int:
    """Deterministische Chartauswertung eines Symbols aus dem Bestand.

    Gedacht zum Gegenpruefen am echten Chart: Die Zonen sind der Teil des
    Verfahrens, dessen Parameter sich nur an realen Kursverlaeufen beurteilen
    lassen (ADR 0025). Wie 'backtest' rechnet das Kommando ausschliesslich auf
    dem gespeicherten Bestand und nie gegen die TWS -- damit dieselbe Frage
    zweimal dieselbe Antwort ergibt. Und wie dort wird 'provider' nicht
    stillschweigend uebersteuert: Der Fixture-Anbieter kennt nur seine eigenen
    Kunstsymbole, eine Auswertung von AAPL gaebe es dort gar nicht.
    """
    loaded = load_config(args.config)
    config = loaded.config
    indicators = config.require_indicators()
    configure_logging(LoggingConfig(level="INFO", format="console"))

    if args.provider is not None:
        market_data = config.market_data.model_copy(update={"provider": args.provider})
        config = config.model_copy(update={"market_data": market_data})

    if config.market_data.provider != "ibkr":
        # Muster 'backtest': Der Fixture-Anbieter kennt nur seine eigenen
        # Kunstsymbole. Ohne diese Pruefung meldete das Kommando fuer jedes
        # echte Symbol "Nicht in der Watchlist gefunden" -- eine Meldung, die
        # auf die Watchlist zeigt, waehrend der Anbieter das Problem ist.
        print(
            "market_data.provider steht auf "
            f"'{config.market_data.provider}'. Die Chartauswertung braucht den ueber "
            "IBKR gefuellten Bestand -- entweder '--provider ibkr' setzen, "
            "market_data.provider auf 'ibkr' stellen oder zuerst 'backfill' laufen "
            "lassen.",
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
    params = build_technical_analysis_params(config)

    interpreter: TechnicalInterpreter | None = None
    if args.interpret:
        if args.agent_provider is not None:
            agent = config.technical_agent.model_copy(update={"provider": args.agent_provider})
            config = config.model_copy(update={"technical_agent": agent})
        try:
            interpreter = build_technical_interpreter(config, Secrets())
        except MissingSecretError as error:
            # Frueh und mit klarer Meldung, statt erst nach dem Laden der
            # Kerzenserien (Muster 'dispatch').
            print(f"Konfiguration: {error}", file=sys.stderr)
            return 2

    wanted = {symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()}
    if not wanted:
        print(f"--symbols enthaelt kein Symbol: '{args.symbols}'", file=sys.stderr)
        return 2

    verfuegbar = list(provider.list_stocks())
    stocks = [stock for stock in verfuegbar if stock.symbol in wanted]
    fehlend = wanted - {stock.symbol for stock in stocks}
    if fehlend:
        print(f"Nicht in der Watchlist gefunden: {', '.join(sorted(fehlend))}", file=sys.stderr)
    if not stocks:
        # Passte kein einziges Symbol, ist die Watchlist selbst die naechste
        # Frage. Sie hier zu zeigen erspart den Umweg ueber 'watchlist'.
        namen = sorted(stock.symbol for stock in verfuegbar)
        gezeigt = ", ".join(namen[:20]) + (" ..." if len(namen) > 20 else "")
        print(
            f"Die Watchlist enthaelt {len(namen)} Symbole: {gezeigt}"
            if namen
            else "Die Watchlist ist leer.",
            file=sys.stderr,
        )
        return 2

    fehler = 0
    for stock in stocks:
        try:
            series = provider.get_candle_series(stock)
        except MarketDataProviderError as error:
            print(f"{stock.symbol}: {error}", file=sys.stderr)
            fehler += 1
            continue
        snapshot = compute_technical_snapshot(series, len(series) - 1, params, datetime.now(UTC))
        _print_technical_snapshot(stock.symbol, snapshot)
        if args.show_prompt:
            # Bewusst unabhaengig von --interpret: "zeig mir, was gesendet
            # wuerde, ohne dass es etwas kostet" ist der nuetzlichste Fall.
            # Die Zusage "das Modell sieht nur den Snapshot" laesst sich sonst
            # nicht nachpruefen, sondern nur behaupten.
            print("  Modelleingabe:")
            for zeile in render_snapshot(stock, snapshot).splitlines():
                print(f"    {zeile}")
        if interpreter is not None:
            try:
                _print_technical_assessment(
                    stock.symbol, interpreter.interpret(stock, snapshot), snapshot
                )
            except TechnicalInterpreterError as error:
                print(f"{stock.symbol}: {error}", file=sys.stderr)
                fehler += 1
        print()
    return 1 if fehler else 0


def command_fundamental(args: argparse.Namespace) -> int:
    """Deterministische Fundamentalanalyse eines Symbols (ADR 0032).

    Gedacht zum Gegenpruefen an echten Einreichungen: Welche XBRL-Tags ein
    Emittent verwendet, laesst sich nur an seinen tatsaechlichen Filings
    beurteilen -- ADR 0032 L1 fuehrt die Abdeckung der Tag-Listen ausdruecklich
    als ungemessen.

    Braucht weder Datenbank noch Marktdatenanbieter. Der Kurs ist die
    optionale, nicht blockierende Eingabe aus ADR 0032 und wird hier von Hand
    uebergeben, damit sich das Kommando ohne gefuellten Bestand ausfuehren
    laesst -- ohne ihn fehlen genau die vier bewertungsabhaengigen Kennzahlen.
    """
    loaded = load_config(args.config)
    config = loaded.config
    configure_logging(LoggingConfig(level="INFO", format="console"))

    if args.provider is not None:
        section = config.fundamentals.model_copy(update={"provider": args.provider})
        config = config.model_copy(update={"fundamentals": section})

    try:
        provider = build_fundamental_data_provider(config, Secrets())
    except (ConfigError, MissingSecretError) as error:
        print(f"Konfiguration: {error}", file=sys.stderr)
        return 2

    if bool(args.watchlist) == bool(args.symbols):
        print(
            "Entweder --symbols oder --watchlist angeben, nicht beides und nicht keines.",
            file=sys.stderr,
        )
        return 2

    if args.watchlist:
        vertraege = build_watchlist(config, project_root(loaded.source_path))
        wanted = sorted({vertrag.symbol for vertrag in vertraege})
        if not wanted:
            print("Die Watchlist ist leer.", file=sys.stderr)
            return 2
    else:
        wanted = [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()]
        if not wanted:
            print(f"--symbols enthaelt kein Symbol: '{args.symbols}'", file=sys.stderr)
            return 2
    if args.price is not None and len(wanted) > 1:
        # Ein Kurs gilt fuer ein Papier. Auf mehrere angewendet bewertete er
        # jedes zum Kurs des ersten -- und das Kommando existiert gerade zum
        # Gegenpruefen, waere also in genau seiner Aufgabe irrefuehrend.
        print(
            f"--price gilt fuer ein Symbol, angegeben sind {len(wanted)}. "
            "Entweder ein einzelnes Symbol abfragen oder --price weglassen; "
            "ohne Kurs entfallen nur die vier bewertungsabhaengigen Kennzahlen.",
            file=sys.stderr,
        )
        return 2

    if args.price is not None and args.price_from_bars:
        print(
            "--price und --price-from-bars schliessen sich aus: Der eine setzt den "
            "Kurs von Hand, der andere nimmt ihn aus dem Bestand.",
            file=sys.stderr,
        )
        return 2

    ziel = Path(args.output) if args.output is not None else None
    if ziel is not None:
        # Vor dem ersten Abruf, nicht nach dem letzten: Ein Lauf ueber die
        # Watchliste laedt rund 800 MB und dauert Minuten. Ein fehlendes
        # Verzeichnis erst beim Schreiben zu bemerken, warf all das weg.
        try:
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.touch()
        except OSError as error:
            print(f"--output nicht beschreibbar: {error}", file=sys.stderr)
            return 2

    kurse: dict[str, float] = {}
    kurs_stempel: dict[str, datetime] = {}
    if args.price_from_bars:
        if args.market_data_provider is not None:
            market_data = config.market_data.model_copy(
                update={"provider": args.market_data_provider}
            )
            config = config.model_copy(update={"market_data": market_data})
        ergebnis = _kurse_aus_dem_bestand(loaded, config, wanted)
        if ergebnis is None:
            return 2
        kurse, kurs_stempel, ohne_bestand = ergebnis
        for symbol, grund in ohne_bestand:
            # Kein Ersatzwert und keine stille Auslassung: Die Aktie wird
            # ausgewertet, nur eben ohne die vier bewertungsabhaengigen
            # Kennzahlen -- genau wie ein Lauf ohne Kurs (ADR 0032).
            print(f"{symbol}: {grund}, rechnet ohne Kurs.", file=sys.stderr)
        _print_kursherkunft(kurs_stempel, len(wanted))

    fehler: list[tuple[str, str]] = []
    ergebnisse: list[FundamentalSnapshot] = []
    for symbol in wanted:
        stock = Stock(id=uuid4(), symbol=symbol, exchange=args.exchange)
        kurs = kurse.get(symbol, args.price)
        try:
            snapshot = provider.fundamentals(stock, price=kurs)
        except FundamentalDataProviderError as error:
            fehler.append((symbol, str(error)))
            print(f"{symbol}: {error}", file=sys.stderr)
            continue
        ergebnisse.append(snapshot)
        if args.summary:
            _print_fundamental_summary_line(snapshot)
        else:
            _print_fundamental_snapshot(snapshot)
            print()

    # Erst schreiben, dann zusammenfassen: Die Sammelausgabe ist lang, und
    # was in ihr scheitert, darf nicht die Einzelwerte des ganzen Laufs
    # mitnehmen.
    if ziel is not None:
        _write_fundamental_csv(ziel, ergebnisse)
        print(f"Einzelwerte geschrieben nach {ziel}")
    if args.summary:
        _print_fundamental_aggregate(
            ergebnisse,
            fehler,
            # Nur wenn JEDE Aktie einen Kurs hatte. Bei fuenf von hundert
            # gilt der Hinweis fuer die anderen fuenfundneunzig weiter --
            # sonst saehe ihre gedrueckte Abdeckung wieder wie ein Mangel
            # der Tag-Listen aus.
            mit_kurs=args.price is not None or len(kurse) == len(wanted),
        )
    return 1 if fehler else 0


def quintilgrenzen(werte: Sequence[float]) -> tuple[float, ...]:
    """Die vier Schnittpunkte der Fuenftel, aufsteigend.

    Bewusst **verteilungsfrei**: Kein Mittelwert, keine Standardabweichung.
    Die Verteilungen sind stark schief -- ein KGV von 4368 (CRWD) und eine
    Eigenkapitalrendite von 13587 % (GDDY, Eigenkapital nahe null) verschoeben
    jeden Mittelwert, lassen aber die Rangfolge unberuehrt.

    ``statistics.quantiles`` mit ``method="inclusive"`` interpoliert zwischen
    den Datenpunkten und behandelt die Stichprobe als Grundgesamtheit -- und
    das ist sie hier: Die Watchliste ist nicht Stichprobe eines groesseren
    Marktes, sie **ist** der Vergleichsraum (ADR 0032 L5).
    """
    if len(werte) < 5:
        # Weniger als fuenf Werte koennen keine Fuenftel bilden. Kein
        # Ersatzwert: Die Kennzahl bekommt in diesem Lauf keine Schwellen.
        raise ValueError(f"Fuenftel brauchen mindestens fuenf Werte, gegeben sind {len(werte)}")
    # Ohne eigenes sorted(): ``statistics.quantiles`` sortiert selbst. Der
    # Test auf die Reihenfolgeunabhaengigkeit bleibt trotzdem stehen -- er
    # haelt die Zusicherung fest, nicht ihre heutige Herkunft.
    grenzen = statistics.quantiles(werte, n=5, method="inclusive")
    return tuple(grenzen)


def command_calibrate_scores(args: argparse.Namespace) -> int:
    """Die Verteilung je Kennzahl ueber die Watchliste.

    Das Muster von ``history-depth`` und ``calendar-reach``: messen, ausgeben,
    nichts ablegen. Die Schwellen selbst entscheidet ein ADR -- dieses
    Kommando liefert die Zahlen, auf denen es steht.
    """
    quelle = Path(args.input)
    try:
        zeilen = quelle.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        print(f"--input nicht lesbar: {error}", file=sys.stderr)
        return 2

    reader = csv.DictReader(zeilen)
    werte: dict[str, list[float]] = defaultdict(list)
    symbole: set[str] = set()
    ohne_kennzahlen: set[str] = set()
    for zeile in reader:
        symbol = (zeile.get("symbol") or "").strip()
        if not symbol:
            continue
        symbole.add(symbol)
        name = (zeile.get("kennzahl") or "").strip()
        roh = (zeile.get("wert") or "").strip()
        if not name or not roh:
            # Eine Aktie ohne jede Kennzahl steht mit leeren Feldern in der
            # CSV (INSUFFICIENT_DATA). Sie zaehlt bei der Abdeckung mit,
            # liefert aber keinen Wert.
            ohne_kennzahlen.add(symbol)
            continue
        try:
            werte[name].append(float(roh))
        except ValueError:
            print(f"{symbol}/{name}: '{roh}' ist keine Zahl.", file=sys.stderr)

    if not werte:
        print(f"{quelle} enthaelt keine auswertbaren Kennzahlen.", file=sys.stderr)
        return 2

    _print_kalibrierung(werte, len(symbole), sorted(ohne_kennzahlen))
    return 0


def _print_kalibrierung(
    werte: Mapping[str, Sequence[float]], aktien: int, ohne_kennzahlen: Sequence[str]
) -> None:
    """Je Kennzahl: Abdeckung, Fuenftelgrenzen, Spannweite.

    Die Spannweite steht daneben, weil sie zeigt, **warum** die Grenzen aus
    Quantilen kommen und nicht aus Mittelwerten.
    """
    print()
    print(f"=== Verteilung ueber {aktien} Aktien ===")
    if ohne_kennzahlen:
        print(
            f"Ohne jede Kennzahl: {len(ohne_kennzahlen)} "
            f"({', '.join(ohne_kennzahlen)})"
        )
    print()
    kopf = f"{'Kennzahl':30} {'n':>4} {'20%':>12} {'40%':>12} {'60%':>12} {'80%':>12}"
    print(kopf)
    print("-" * len(kopf))
    for name in sorted(werte):
        reihe = werte[name]
        try:
            grenzen = quintilgrenzen(reihe)
        except ValueError:
            print(f"{name:30} {len(reihe):>4}   zu wenige Werte fuer Fuenftel")
            continue
        spalten = " ".join(f"{grenze:>12.4f}" for grenze in grenzen)
        print(f"{name:30} {len(reihe):>4} {spalten}")

    print()
    print(f"{'Kennzahl':30} {'n':>4} {'kleinster':>16} {'groesster':>16}")
    print("-" * 70)
    for name in sorted(werte):
        reihe = sorted(werte[name])
        print(f"{name:30} {len(reihe):>4} {reihe[0]:>16.4f} {reihe[-1]:>16.4f}")


def _kurse_aus_dem_bestand(
    loaded: LoadedConfig,
    config: AppConfig,
    wanted: Sequence[str],
    *,
    abhilfe: str = (
        "Entweder '--market-data-provider ibkr' setzen oder den Schalter weglassen. "
        "'--provider' uebersteuert bei diesem Unterbefehl die Fundamentalquelle, "
        "nicht die Marktdatenquelle."
    ),
) -> tuple[dict[str, float], dict[str, datetime], list[tuple[str, str]]] | None:
    """Schlusskurse der letzten abgeschlossenen Kerze je Symbol.

    **Dieselbe Regel wie im Tageslauf** (``RunAnalysisUseCase``, ADR 0035
    Entscheidung 2): der Schluss der letzten abgeschlossenen Kerze, nicht ein
    Live-Kurs. Die Fundamentalanalyse beschafft weiterhin keinen Kurs selbst;
    sie bekommt ihn gereicht (ADR 0032, CLAUDE.md).

    Liefert Kurse, deren Kerzenzeitpunkte und die Symbole ohne Kurs mit dem
    jeweiligen Grund.
    ``None`` heisst: Die Vorbedingungen stimmen nicht, der Aufrufer bricht ab.
    """
    if config.market_data.provider != "ibkr":
        # Muster 'technical': Der Fixture-Anbieter kennt nur seine
        # Kunstsymbole. Ohne diese Pruefung meldete das Kommando fuer jedes
        # echte Symbol "keine Kerzen im Bestand" -- eine Meldung, die auf den
        # Bestand zeigt, waehrend der Anbieter das Problem ist.
        print(
            "Die Kurse kommen aus dem ueber IBKR gefuellten Bestand, "
            f"market_data.provider steht aber auf '{config.market_data.provider}'. "
            + abhilfe,
            file=sys.stderr,
        )
        return None

    market_data = config.market_data.model_copy(update={"source": "stored"})
    config = config.model_copy(update={"market_data": market_data})

    engine = _open_database()
    if engine is None:
        return None
    session_factory = build_session_factory(engine)

    def uow_factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    indicators = config.require_indicators()
    provider = build_market_data_provider(
        config, indicators, project_root(loaded.source_path), uow_factory=uow_factory
    )

    bekannt = {stock.symbol: stock for stock in provider.list_stocks()}
    kurse: dict[str, float] = {}
    stempel: dict[str, datetime] = {}
    ohne_bestand: list[tuple[str, str]] = []
    for symbol in wanted:
        stock = bekannt.get(symbol)
        if stock is None:
            ohne_bestand.append((symbol, "nicht im Bestand"))
            continue
        try:
            series = provider.get_candle_series(stock)
        except MarketDataProviderError as error:
            # Die Ursache mitnehmen, nicht verschlucken (Muster
            # 'technical'): Eine weggebrochene Datenbank und eine
            # lueckenhafte Historie melden sich beide hier. Unter der
            # Sammelmeldung "nicht im Bestand" saehen sie aus wie ein
            # fehlender Backfill -- und der Leser suchte an der falschen
            # Stelle.
            ohne_bestand.append((symbol, str(error)))
            continue
        if not series.candles:
            ohne_bestand.append((symbol, "keine Kerzen"))
            continue
        letzte = series.candles[-1]
        kurse[symbol] = letzte.close
        stempel[symbol] = letzte.timestamp
    engine.dispose()
    return kurse, stempel, ohne_bestand


def _print_kursherkunft(kurs_stempel: Mapping[str, datetime], gesamt: int) -> None:
    """Woher die Kurse stammen und wie alt sie sind.

    **Unabhaengig von ``--summary``.** Ein veralteter Bestand rechnet sonst
    still falsche Bewertungskennzahlen: Ein KGV aus dem Gewinn von heute und
    dem Kurs von vor drei Wochen sieht aus wie ein KGV. Der Tageslauf hat
    dafuer ``_require_expected_candle``; dieses Kommando laeuft bewusst auch
    auf aelterem Bestand und weist ihn deshalb aus, statt ihn abzulehnen.
    """
    if not kurs_stempel:
        print("Kein einziger Kurs aus dem Bestand -- alle Aktien rechnen ohne.")
        return
    zeitpunkte = sorted(kurs_stempel.values())
    print(
        f"Kurse aus dem Bestand fuer {len(kurs_stempel)} von {gesamt} Aktien: "
        f"aelteste Kerze {zeitpunkte[0].isoformat()}, "
        f"neueste {zeitpunkte[-1].isoformat()}"
    )


def _print_fundamental_summary_line(snapshot: FundamentalSnapshot) -> None:
    """Eine Zeile je Aktie -- fuer Laeufe ueber die ganze Watchlist.

    Der volle Block je Aktie waere bei rund hundert Titeln laenger als der
    Puffer der PowerShell; was oben herausscrollt, ist verloren.
    """
    zwoelf = sum(
        1 for m in snapshot.metrics.values() if m.basis is MetricBasis.TRAILING_TWELVE_MONTHS
    )
    fehlend = ", ".join(name.value for name in snapshot.missing_metrics)
    print(
        f"{snapshot.symbol:8} {snapshot.status.value:17} {snapshot.coverage:4.0%} "
        f"{zwoelf:2}x12M {len(snapshot.tag_conflicts):3} Widerspr.  {fehlend}"
    )


def _print_fundamental_aggregate(
    ergebnisse: Sequence[FundamentalSnapshot],
    fehler: Sequence[tuple[str, str]],
    *,
    mit_kurs: bool,
) -> None:
    """Die Auswertung, um die es beim Watchlist-Lauf geht (ADR 0032 L1).

    Die Frage ist nicht, wie eine einzelne Aktie aussieht, sondern **wie oft
    eine Kennzahl fehlt**. Von Hand gepflegte Tag-Listen decken nicht jeden
    Emittenten ab; wie gut sie es tun, war bislang an sieben Titeln geschaetzt.
    """
    print()
    print(f"=== {len(ergebnisse)} Aktien ausgewertet, {len(fehler)} Fehlschlaege ===")
    if not ergebnisse:
        return

    abdeckungen = sorted(snapshot.coverage for snapshot in ergebnisse)
    mitte = abdeckungen[len(abdeckungen) // 2]
    print(
        f"Abdeckung: niedrigste {abdeckungen[0]:.0%}, Median {mitte:.0%}, "
        f"hoechste {abdeckungen[-1]:.0%}"
    )

    if not mit_kurs:
        print(
            "Ohne Kurs entfallen die vier bewertungsabhaengigen Kennzahlen bei "
            "JEDER Aktie -- das drueckt die Abdeckung um rund 22 Prozentpunkte."
        )

    print()
    print("Je Kennzahl, wie oft sie fehlt:")
    for name in MetricName:
        fehlt = sum(1 for snapshot in ergebnisse if name in snapshot.missing_metrics)
        if fehlt:
            anteil = fehlt / len(ergebnisse)
            print(f"  {name.value:28} {fehlt:3} von {len(ergebnisse)}  ({anteil:.0%})")

    zwoelf_je_aktie = [
        sum(1 for m in snapshot.metrics.values() if m.basis is MetricBasis.TRAILING_TWELVE_MONTHS)
        for snapshot in ergebnisse
    ]
    ohne_zwoelf = [
        snapshot.symbol for snapshot, anzahl in zip(ergebnisse, zwoelf_je_aktie, strict=True)
        if anzahl == 0
    ]
    print()
    print(f"Ohne einen einzigen Zwoelfmonatswert: {len(ohne_zwoelf)} Aktien")
    if ohne_zwoelf:
        print(f"  {', '.join(ohne_zwoelf)}")

    mit_widerspruch = [s for s in ergebnisse if s.tag_conflicts]
    print(f"Mit gemeldeten Tag-Widerspruechen: {len(mit_widerspruch)} Aktien")
    for snapshot in mit_widerspruch[:10]:
        groesste = max(
            snapshot.tag_conflicts,
            key=lambda k: k.relative_deviation if k.relative_deviation is not None else 0.0,
        )
        abweichung = groesste.relative_deviation
        print(
            f"  {snapshot.symbol:8} {len(snapshot.tag_conflicts):3}  groesste: "
            f"{groesste.figure.value} "
            + (f"{abweichung:.0%}" if abweichung is not None else "unbestimmt")
        )
    if len(mit_widerspruch) > 10:
        print(f"  ... und {len(mit_widerspruch) - 10} weitere")

    if fehler:
        print()
        print("Fehlschlaege:")
        for symbol, meldung in fehler:
            print(f"  {symbol:8} {meldung}")


def _write_fundamental_csv(pfad: Path, ergebnisse: Sequence[FundamentalSnapshot]) -> None:
    """Alle Einzelwerte in eine Datei -- der Terminalpuffer reicht nicht.

    Bewusst je Kennzahl eine Zeile und nicht eine Spalte je Kennzahl: So
    laesst sich die Datei auch dann lesen, wenn spaeter Kennzahlen dazu-
    kommen, und Basis und Zeitraum stehen an jedem Wert statt in der
    Kopfzeile.
    """
    with pfad.open("w", encoding="utf-8", newline="") as datei:
        schreiber = csv.writer(datei)
        schreiber.writerow(
            ["symbol", "status", "abdeckung", "kennzahl", "wert", "einheit", "basis",
             "zeitraum_ende", "quelle_tags", "quelle_formulare", "quelle_eingereicht"]
        )
        for snapshot in ergebnisse:
            if not snapshot.metrics:
                schreiber.writerow(
                    [snapshot.symbol, snapshot.status.value, f"{snapshot.coverage:.4f}",
                     "", "", "", "", "", "", "", ""]
                )
            for name, metric in snapshot.metrics.items():
                # **Alle** Quellen, nicht nur die erste: Eine Marge steht auf
                # zwei Tags, der freie Cashflow ebenfalls. Die Datei entsteht,
                # um die Tag-Abdeckung auszuwerten -- mit nur einer Quelle je
                # Kennzahl fehlte darin jeder Nenner und jeder
                # Investitionstag, also genau das, was gemessen werden soll.
                schreiber.writerow(
                    [snapshot.symbol, snapshot.status.value, f"{snapshot.coverage:.4f}",
                     name.value, f"{metric.value:.6f}", metric.unit.value, metric.basis.value,
                     metric.period_end.isoformat(),
                     " ".join(quelle.tag for quelle in metric.sources),
                     " ".join(sorted({quelle.form for quelle in metric.sources})),
                     max(quelle.filed for quelle in metric.sources).isoformat()]
                )


def _print_fundamental_snapshot(snapshot: FundamentalSnapshot) -> None:
    """Kennzahlen, Herkunft und ausdruecklich das Fehlende.

    Die fehlenden Kennzahlen werden **aufgezaehlt** und nicht bloss
    weggelassen: Ein Bericht, aus dem eine Kennzahl still verschwindet, sieht
    aus wie einer, in dem sie nie vorgesehen war (CLAUDE.md).
    """
    print(f"{snapshot.symbol}: {snapshot.status.value} (Verfahren {snapshot.analysis_version})")
    if snapshot.reason:
        print(f"  Grund: {snapshot.reason}")
    if snapshot.fiscal_years:
        print(
            f"  Geschaeftsjahre: {snapshot.fiscal_years[0]}-{snapshot.fiscal_years[-1]} "
            f"({len(snapshot.fiscal_years)})"
        )
    print(f"  Abdeckung: {snapshot.coverage:.0%}", end="")
    print(
        f"  Kurs: {snapshot.price_used:.2f}"
        if snapshot.price_used is not None
        else "  Kurs: nicht uebergeben -- Bewertungskennzahlen entfallen"
    )

    for name, metric in snapshot.metrics.items():
        print(
            f"  {name.value:28} {_format_metric(metric):>18}   "
            f"{_BASISKUERZEL[metric.basis]} bis {metric.period_end}"
        )

    if snapshot.missing_metrics:
        print(f"  Nicht verfuegbar: {', '.join(name.value for name in snapshot.missing_metrics)}")

    for konflikt in snapshot.tag_conflicts:
        abweichung = konflikt.relative_deviation
        print(
            f"  WIDERSPRUCH {konflikt.figure.value} {konflikt.period_end}: "
            f"{konflikt.chosen_tag}={konflikt.chosen_value:,.0f} gegen "
            f"{konflikt.other_tag}={konflikt.other_value:,.0f}"
            + (f" ({abweichung:.1%})" if abweichung is not None else "")
        )

    quellen = {source.url for metric in snapshot.metrics.values() for source in metric.sources}
    for url in sorted(quellen)[:3]:
        print(f"  Quelle: {url}")
    if len(quellen) > 3:
        print(f"  ... und {len(quellen) - 3} weitere Einreichungen")


_BASISKUERZEL = {
    MetricBasis.TRAILING_TWELVE_MONTHS: "12M",
    MetricBasis.FISCAL_YEAR: "GJ ",
    MetricBasis.POINT_IN_TIME: "Stg",
}
"""Ein Zwoelfmonatsfenster und ein Geschaeftsjahr sind beide rund 365 Tage
lang -- am Zeitraum allein waeren sie nicht zu unterscheiden. Ohne dieses
Kuerzel liesse sich Einschraenkung L2 aus ADR 0033 im Bericht nicht
aufloesen: Zwei Kennzahlen desselben Berichts koennen verschiedene
Zeitbezuege haben."""


def _format_metric(metric: Metric) -> str:
    """Eine Kennzahl in der Einheit, die sie traegt.

    Der Grund fuer die getrennten Einheiten FRACTION und RATIO: Eine Marge
    von 0,25 heisst 25 Prozent, ein KGV von 0,25 heisst 0,25. Dieselbe
    Formatierung fuer beide waere in jeder zweiten Zeile falsch.
    """
    if metric.unit is MetricUnit.CURRENCY:
        return f"{metric.value / 1e6:,.1f} Mio {metric.currency}"
    if metric.unit is MetricUnit.FRACTION:
        return f"{metric.value:.2%}"
    if metric.unit is MetricUnit.SHARES:
        return f"{metric.value:,.0f}"
    return f"{metric.value:.2f}"


def command_options(args: argparse.Namespace) -> int:
    """Optionsanalyse -- Einzelprobe oder Messlauf ueber die Watchliste (ADR 0048).

    Die Einzelprobe beantwortet die Frage, an der die ganze Stufe haengt:
    Liefert IBKR **nach Boersenschluss** noch modellierte Greeks? Der
    Tageslauf beginnt mit dem Schluss der zweiten 195-Minuten-Kerze -- also
    zum Boersenschluss -- und erreicht die Optionen erst nach dem
    Kerzen-Backfill. Der Marktdatenmodus steht deshalb in der Konfiguration
    (``options.market_data_type``) und laesst sich hier uebersteuern.

    ``--watchlist --output`` liefert die Verteilung der annualisierten Rendite
    ueber die volle Watchliste. Die Datei traegt dieselben Spalten wie die der
    Fundamentalanalyse und laesst sich deshalb **ohne neuen Auswertebefehl**
    an 'calibrate-scores' weiterreichen (Muster ADR 0045: messen, dann
    festlegen).

    Gerechnet wird ueber **denselben Codepfad wie im Tageslauf** -- dieselbe
    Verfallsterminwahl, dasselbe Strike-Band, derselbe Delta-Filter, dieselbe
    Renditeformel. Zwei Formeln haetten Schwellen ergeben, die zu den
    gemessenen Werten nicht passen (die Lehre aus ADR 0046).

    **Mit einer benannten Ausnahme:** Der Berichtstermin geht nicht ein, weil
    dieses Kommando ihn nicht abruft. Im Tageslauf schliesst er Verfaelle
    danach aus; hier sollen die Schwellen auf der unbeschraenkten Verteilung
    stehen (ADR 0048, Konsequenzen). Aus demselben Grund fehlen die Zonen:
    Sie fuellen ein Feld am Vorschlag und gehen in keine Kennzahl ein.
    """
    loaded = load_config(args.config)
    config = loaded.config
    configure_logging(LoggingConfig(level="INFO", format="console"))

    ueberschreibungen: dict[str, object] = {}
    if args.provider is not None:
        ueberschreibungen["provider"] = args.provider
    if args.market_data_type is not None:
        ueberschreibungen["market_data_type"] = args.market_data_type
    if ueberschreibungen:
        config = config.model_copy(
            update={"options": config.options.model_copy(update=ueberschreibungen)}
        )

    if bool(args.watchlist) == bool(args.symbol):
        print(
            "Entweder --symbol oder --watchlist angeben, nicht beides und nicht keines.",
            file=sys.stderr,
        )
        return 2

    if args.watchlist:
        vertraege = build_watchlist(config, project_root(loaded.source_path))
        wanted = sorted({vertrag.symbol for vertrag in vertraege})
        if not wanted:
            print("Die Watchlist ist leer.", file=sys.stderr)
            return 2
    else:
        wanted = [args.symbol.upper()]

    if args.record is not None:
        if args.watchlist:
            print(
                "--record zeichnet eine Kette auf, nicht die ganze Watchliste. "
                "Mit --symbol aufrufen.",
                file=sys.stderr,
            )
            return 2
        if config.options.provider != "ibkr":
            print(
                "--record braucht '--provider ibkr': Der Fixture-Anbieter hat keine "
                "TWS-Antwort, die sich aufzeichnen liesse.",
                file=sys.stderr,
            )
            return 2

    if args.price is not None and len(wanted) > 1:
        print(
            f"--price gilt fuer ein Symbol, angegeben sind {len(wanted)}. "
            "Ohne den Schalter kommt der Kurs aus dem Bestand -- derselbe "
            "Schlusskurs, auf dem auch der Tageslauf rechnet.",
            file=sys.stderr,
        )
        return 2

    ziel = Path(args.output) if args.output is not None else None
    if ziel is not None:
        # Vor dem ersten Abruf, nicht nach dem letzten -- dieselbe Lehre wie
        # bei 'fundamental' und 'ratings'.
        try:
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.touch()
        except OSError as error:
            print(f"--output nicht beschreibbar: {error}", file=sys.stderr)
            return 2

    mitschnittsziel = Path(args.record) if args.record is not None else None
    if mitschnittsziel is not None:
        try:
            mitschnittsziel.parent.mkdir(parents=True, exist_ok=True)
            mitschnittsziel.touch()
        except OSError as error:
            print(f"--record nicht beschreibbar: {error}", file=sys.stderr)
            return 2

    kurse: dict[str, float] = {}
    stichtage: dict[str, date] = {}
    if args.price is not None:
        kurse[wanted[0]] = args.price
        # Ohne Kerze gibt es keinen Kerzentag. Der heutige Handelstag in
        # Boersenzeit ist die einzige ehrliche Naeherung -- und sie steht in
        # der Ausgabe, damit niemand sie fuer einen Kerzenzeitpunkt haelt.
        stichtage[wanted[0]] = datetime.now(ZoneInfo(config.market.timezone)).date()
    else:
        if args.market_data_provider is not None:
            config = config.model_copy(
                update={
                    "market_data": config.market_data.model_copy(
                        update={"provider": args.market_data_provider}
                    )
                }
            )
        ergebnis = _kurse_aus_dem_bestand(
            loaded,
            config,
            wanted,
            abhilfe=(
                "Entweder '--market-data-provider ibkr' setzen oder mit '--price' einen "
                "Kurs von Hand uebergeben. '--provider' uebersteuert bei diesem "
                "Unterbefehl die Optionsquelle, nicht die Marktdatenquelle."
            ),
        )
        if ergebnis is None:
            return 2
        kurse, kurs_stempel, ohne_bestand = ergebnis
        stichtage = {symbol: stempel.date() for symbol, stempel in kurs_stempel.items()}
        for symbol, grund in ohne_bestand:
            # Anders als bei der Fundamentalanalyse ist der Kurs hier
            # **blockierend**: Ohne ihn gibt es kein Strike-Band, also nichts
            # abzufragen (ADR 0048).
            print(f"{symbol}: {grund}, ohne Kurs keine Optionsauswahl.", file=sys.stderr)
        _print_kursherkunft(kurs_stempel, len(wanted))

    # Der Sammler entsteht **vor** der Quelle, die Quelle vor dem Mitschnitt:
    # Der Mitschnitt umschliesst die Quelle, und die Quelle braucht den
    # Sammler. Umgekehrt waere es ein Kreis.
    aufzeichnen = mitschnittsziel is not None and config.options.provider == "ibkr"
    rohe = RohNotierungenSammler() if aufzeichnen else None
    quelle = (
        build_ibkr_bar_source(config, on_option_tickers=rohe)
        if config.options.provider == "ibkr"
        else None
    )

    # Der Mitschnitt haengt sich **zwischen** Adapter und TWS, nicht hinter das
    # Ergebnis: Aufgehoben wird, was der Anbieter geantwortet hat, nicht was
    # daraus wurde (A2-M7).
    mitschnitt: RecordingOptionChainSource | None = None
    kette: OptionChainSource | None = quelle
    if mitschnittsziel is not None and quelle is not None and wanted[0] in kurse:
        mitschnitt = RecordingOptionChainSource(
            quelle,
            mitschnittsziel,
            price=kurse[wanted[0]],
            as_of=stichtage[wanted[0]],
            market_data_type=config.options.market_data_type,
            rohe=rohe,
        )
        kette = mitschnitt

    try:
        provider = build_options_provider(config, project_root(loaded.source_path), kette)
    except ValueError as error:
        print(f"Konfiguration: {error}", file=sys.stderr)
        return 2

    ergebnisse: list[tuple[str, OptionsAnalysis]] = []
    fehler: list[tuple[str, str]] = []
    try:
        for symbol in wanted:
            kurs = kurse.get(symbol)
            if kurs is None:
                continue
            stock = Stock(id=uuid4(), symbol=symbol, exchange=args.exchange)
            try:
                analyse = provider.options(
                    stock, price=kurs, as_of=stichtage[symbol]
                )
            except OptionsDataProviderError as error:
                # Ein Ausfall bei einer Aktie kostet nicht den Messlauf.
                fehler.append((symbol, str(error)))
                print(f"{symbol}: {error}", file=sys.stderr)
                continue
            ergebnisse.append((symbol, analyse))
            if len(wanted) == 1:
                _print_options_analysis(symbol, analyse)
            else:
                _print_options_summary_line(symbol, analyse)
    finally:
        # Erst schreiben, dann die Verbindung schliessen -- und auch dann,
        # wenn der Abruf mittendrin abgebrochen ist: Eine halbe Aufzeichnung
        # sagt, wie weit es kam.
        #
        # Das Schreiben steht in einem eigenen ``try``: Scheitert es (Ziel
        # entfernt, Laufwerk voll), darf das nicht das Trennen der Verbindung
        # verhindern -- IBKR laesst je Client-ID nur eine, und eine offen
        # gebliebene kostet den naechsten Lauf.
        try:
            if mitschnitt is not None:
                mitschnitt.write()
                print(f"\nMitschnitt der Optionskette geschrieben: {mitschnittsziel}")
        except OSError as error:
            print(f"Mitschnitt nicht geschrieben: {error}", file=sys.stderr)
        finally:
            if quelle is not None:
                quelle.close()

        # Ohne Mitschnitt bleibt sonst die leere Datei aus dem
        # Beschreibbarkeitstest liegen -- und sieht im Verzeichnis aus wie
        # eine frische Aufzeichnung.
        if mitschnitt is None and mitschnittsziel is not None:
            with suppress(OSError):
                if mitschnittsziel.stat().st_size == 0:
                    mitschnittsziel.unlink()
            print(
                "Kein Mitschnitt entstanden -- ohne Kurs gibt es keine Abfrage, "
                "die sich aufzeichnen liesse.",
                file=sys.stderr,
            )

    if ziel is not None:
        _write_options_csv(ziel, ergebnisse)
        print(f"\nCSV geschrieben: {ziel}")
    if len(wanted) > 1:
        _print_options_uebersicht(ergebnisse, fehler, len(wanted))

    if not ergebnisse:
        return 2
    return 0


def _print_options_analysis(symbol: str, analyse: OptionsAnalysis) -> None:
    """Der volle Block fuer die Einzelprobe -- samt der Rohwerte.

    Bewusst ausfuehrlich: Dieses Kommando existiert zum Gegenpruefen. Wer
    wissen will, ob nach Boersenschluss noch Greeks kommen, muss Delta und
    implizite Volatilitaet sehen und nicht nur ein Ergebnis, das sie
    voraussetzt.
    """
    print(f"\n{symbol}  {analyse.status.value}  ({analyse.analysis_version})")
    print(f"  Kurs:            {_options_zahl(analyse.underlying_price)}")
    print(f"  Verfallstermin:  {analyse.expiration.isoformat() if analyse.expiration else '--'}")
    if analyse.reason is not None:
        print(f"  Grund:           {analyse.reason}")
    for rang, strategie in enumerate(analyse.strategies, start=1):
        print(
            f"\n  {rang}. Strike {strategie.strike:g}  "
            f"({strategie.days_to_expiration} Tage, "
            f"{strategie.distance_to_price_pct:.1%} unter dem Kurs)"
        )
        print(
            f"     Delta {_options_zahl(strategie.delta, 4)}"
            f"   IV {_options_zahl(strategie.implied_volatility, 4)}"
            f"   Bid {_options_zahl(strategie.bid)}"
            f"   Ask {_options_zahl(strategie.ask)}"
            f"   Mid {_options_zahl(strategie.mid)}"
        )
        print(
            f"     Praemie {strategie.premium:.2f}"
            f"   Break-even {strategie.break_even:.2f}"
            f"   Kapital {strategie.capital_at_risk:.0f}"
        )
        print(
            f"     Rendite {strategie.simple_return:.2%}"
            f"   annualisiert {strategie.annualized_return:.2%}"
        )
        print(
            f"     Liquiditaet {strategie.liquidity.value}"
            f"   OI {strategie.open_interest if strategie.open_interest is not None else '--'}"
            f"   Volumen {strategie.volume if strategie.volume is not None else '--'}"
        )
        if strategie.liquidity_warnings:
            print(f"     Warnungen: {', '.join(strategie.liquidity_warnings)}")


def _options_zahl(wert: float | None, stellen: int = 2) -> str:
    """``--`` statt ``0.00``: Ein fehlender Wert ist keine Null."""
    return "--" if wert is None else f"{wert:.{stellen}f}"


def _print_options_summary_line(symbol: str, analyse: OptionsAnalysis) -> None:
    """Eine Zeile je Aktie -- der volle Block laeuft bei zweihundert Titeln
    aus dem Terminalpuffer (Muster ``_print_analyst_summary_line``)."""
    beste = analyse.strategies[0] if analyse.strategies else None
    print(
        f"  {symbol:<8}{analyse.status.value:<20}"
        f"{(f'{beste.annualized_return:.1%}' if beste is not None else '--'):>9}"
        f"{(f'{beste.delta:.2f}' if beste is not None and beste.delta is not None else '--'):>7}"
        f"  {analyse.expiration.isoformat() if analyse.expiration else ''}"
    )


_OPTIONS_KENNZAHL = "OPTIONS_ANNUALIZED_RETURN"
"""Der Name, unter dem die annualisierte Rendite in der Mess-CSV steht --
derselbe, den ``ComponentName.OPTIONS_ATTRACTIVENESS`` spaeter bewertet."""


def _write_options_csv(pfad: Path, ergebnisse: Sequence[tuple[str, OptionsAnalysis]]) -> None:
    """Die Verteilung der annualisierten Rendite als CSV.

    Die ersten vier Spalten sind die, die 'calibrate-scores' liest. Der Rest
    steht daneben, damit sich ein auffaelliger Wert nachvollziehen laesst,
    ohne den Lauf zu wiederholen -- eine Rendite von 300 Prozent ist eher ein
    Kontrakt mit einem Geldkurs von einem Cent als eine Gelegenheit.

    Eine Aktie ohne Vorschlag steht mit leeren Feldern in der Datei: Sie
    zaehlt bei der Abdeckung mit und liefert keinen Wert.
    """
    with pfad.open("w", encoding="utf-8", newline="") as datei:
        writer = csv.writer(datei)
        writer.writerow(
            [
                "symbol",
                "status",
                "kennzahl",
                "wert",
                "verfall",
                "strike",
                "delta",
                "praemie",
                "liquiditaet",
                "abgerufen",
            ]
        )
        for symbol, analyse in ergebnisse:
            beste = analyse.strategies[0] if analyse.strategies else None
            if beste is None:
                writer.writerow(
                    [symbol, analyse.status.value, "", "", "", "", "", "", "", ""]
                )
                continue
            writer.writerow(
                [
                    symbol,
                    analyse.status.value,
                    _OPTIONS_KENNZAHL,
                    f"{beste.annualized_return:.6f}",
                    beste.expiration.isoformat(),
                    f"{beste.strike:g}",
                    "" if beste.delta is None else f"{beste.delta:.4f}",
                    f"{beste.premium:.2f}",
                    beste.liquidity.value,
                    analyse.evaluated_at.isoformat(),
                ]
            )


def _print_options_uebersicht(
    ergebnisse: Sequence[tuple[str, OptionsAnalysis]],
    fehler: Sequence[tuple[str, str]],
    angefragt: int,
) -> None:
    mit_vorschlag = [analyse for _, analyse in ergebnisse if analyse.strategies]
    print(f"\n{angefragt} Aktien angefragt, {len(mit_vorschlag)} mit mindestens einem Vorschlag.")
    if fehler:
        print(f"{len(fehler)} Anbieterfehler: {', '.join(symbol for symbol, _ in fehler)}")
    ohne = [
        (symbol, analyse.reason or "ohne Grund")
        for symbol, analyse in ergebnisse
        if not analyse.strategies
    ]
    if ohne:
        # Die Gruende zaehlen, nicht auflisten: Bei zweihundert Titeln ist
        # "keine Notierung lieferte ein Delta, 190-mal" die Aussage, und
        # zweihundert Einzelzeilen verdecken sie.
        haeufigkeit = Counter(grund for _, grund in ohne)
        print(f"{len(ohne)} ohne Vorschlag:")
        for grund, anzahl in haeufigkeit.most_common():
            print(f"  {anzahl:>4}x  {grund}")


def command_report(args: argparse.Namespace) -> int:
    """Die gespeicherten Analyseberichte eines Laufs (Doc 10, Paragraph 6.12).

    Liest nur -- die Berichte entstehen im Tageslauf, nicht hier. Ein Befehl,
    der sie neu bauen wuerde, ergaebe fuer einen alten Lauf einen anderen
    Bericht als den gespeicherten (ADR 0039, Entscheidung 4).
    """
    configure_logging(LoggingConfig(level="WARNING", format="console"))

    try:
        lauf_id = uuid.UUID(args.run)
    except ValueError:
        print(f"--run ist keine Lauf-ID: '{args.run}'", file=sys.stderr)
        return 2

    # Vor dem ersten Datenbankzugriff: Ein nicht beschreibbares Ziel soll
    # sofort auffallen und nicht erst, wenn alles gelesen ist.
    ziel = Path(args.output) if args.output is not None else None
    neu_angelegt = False
    if ziel is not None:
        try:
            ziel.parent.mkdir(parents=True, exist_ok=True)
            neu_angelegt = not ziel.exists()
            ziel.touch()
        except OSError as error:
            print(f"--output nicht beschreibbar: {error}", file=sys.stderr)
            return 2

    def ohne_ergebnis(code: int) -> int:
        """Bricht ab, ohne eine leere Datei zurueckzulassen.

        Die Probe oben legt das Ziel an, damit ein nicht beschreibbarer Pfad
        vor dem ersten Datenbankzugriff auffaellt. Bleibt sie liegen, sieht
        ein leerer Bericht aus wie ein Bericht ohne Inhalt -- und ueberschriebe
        beim zweiten Versuch stillschweigend nichts.
        """
        if ziel is not None and neu_angelegt:
            ziel.unlink(missing_ok=True)
        return code

    engine = _open_database()
    if engine is None:
        return 2
    session_factory = build_session_factory(engine)

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        # Erst nachsehen, ob es den Lauf ueberhaupt gibt: "keine Berichte"
        # heisst bei einem vorhandenen Lauf "keine Kandidaten", bei einer
        # falschen ID aber etwas ganz anderes. Beides gleich zu melden
        # verschickte einen Tippfehler als Ergebnis.
        lauf = uow.analysis_runs.get(lauf_id)
        berichte = list(uow.stock_reports.list_for_run(lauf_id))

    if lauf is None:
        print(f"Kein Lauf mit der ID {lauf_id}", file=sys.stderr)
        return ohne_ergebnis(1)

    if args.symbol is not None:
        gesucht = args.symbol.strip().upper()
        berichte = [bericht for bericht in berichte if bericht.symbol == gesucht]
        if not berichte:
            print(f"Kein Bericht zu '{gesucht}' in Lauf {lauf_id}", file=sys.stderr)
            return ohne_ergebnis(1)

    if not berichte:
        print(
            f"Keine Berichte zu Lauf {lauf_id} ({lauf.status.value}) -- "
            f"{lauf.candidates_found} Kandidaten."
        )
        return ohne_ergebnis(0)

    if args.format == "json":
        ausgabe = json.dumps(
            [bericht.document for bericht in berichte], ensure_ascii=False, indent=2
        )
    else:
        ausgabe = render_run([(bericht.symbol, bericht.document) for bericht in berichte])

    if ziel is not None:
        ziel.write_text(ausgabe + "\n", encoding="utf-8")
        print(f"{len(berichte)} Bericht(e) geschrieben nach {ziel}")
    else:
        print(ausgabe)
    return 0


def command_research(args: argparse.Namespace) -> int:
    """Manueller Probelauf des Research Agent fuer ein einzelnes Symbol.

    Braucht weder Datenbank noch Marktdatenanbieter -- anders als
    'backtest' liest der Research Agent keinen eigenen Kursbestand.
    Ein echter Aufruf gegen 'anthropic' kostet Geld (ADR 0021/0023
    Budget), deshalb keine automatische Uebersteuerung: 'fixture' bleibt
    Standard, bis ausdruecklich '--provider anthropic' gesetzt wird.
    '--max-searches'/'--max-fetches' druecken das Budget fuer einen
    einzelnen Probelauf zusaetzlich, damit sich die Kette fuer wenige Cent
    pruefen laesst.
    """
    loaded = load_config(args.config)
    config = loaded.config
    configure_logging(LoggingConfig(level="INFO", format="console"))

    overrides: dict[str, object] = {}
    if args.provider is not None:
        overrides["provider"] = args.provider
    if args.max_searches is not None:
        overrides["max_searches"] = args.max_searches
    if args.max_fetches is not None:
        overrides["max_fetches"] = args.max_fetches
    if overrides:
        research = config.research.model_copy(update=overrides)
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


def command_ratings(args: argparse.Namespace) -> int:
    """Analystenempfehlungen -- Einzelprobe oder Messlauf ueber die Watchliste.

    Braucht weder Datenbank noch Marktdatenanbieter: Der Endpunkt kennt nur
    das Symbol. Anders als 'research' kostet ein echter Aufruf **nichts**, er
    liegt in Finnhubs Gratis-Stufe; 'fixture' bleibt trotzdem Standard, damit
    der Befehl ohne Zugangsschluessel laeuft.

    ``--watchlist --output`` liefert die Verteilung des Kauf-Anteils ueber die
    volle Watchliste. Die Datei traegt dieselben Spalten wie die der
    Fundamentalanalyse und laesst sich deshalb **ohne neuen Auswertebefehl**
    an 'calibrate-scores' weiterreichen (Muster ADR 0045: messen, dann
    festlegen).
    """
    loaded = load_config(args.config)
    config = loaded.config
    configure_logging(LoggingConfig(level="INFO", format="console"))

    if args.provider is not None:
        section = config.analyst_ratings.model_copy(update={"provider": args.provider})
        config = config.model_copy(update={"analyst_ratings": section})

    try:
        provider = build_analyst_recommendations_provider(config, Secrets())
    except MissingSecretError as error:
        print(f"Analystenempfehlungen: {error}", file=sys.stderr)
        return 2

    if bool(args.watchlist) == bool(args.symbol):
        print(
            "Entweder --symbol oder --watchlist angeben, nicht beides und nicht keines.",
            file=sys.stderr,
        )
        return 2

    if args.watchlist:
        vertraege = build_watchlist(config, project_root(loaded.source_path))
        wanted = sorted({vertrag.symbol for vertrag in vertraege})
        if not wanted:
            print("Die Watchlist ist leer.", file=sys.stderr)
            return 2
    else:
        wanted = [args.symbol.upper()]

    ziel = Path(args.output) if args.output is not None else None
    if ziel is not None:
        # Vor dem ersten Abruf, nicht nach dem letzten -- dieselbe Lehre wie
        # bei 'fundamental': Ein fehlendes Verzeichnis erst beim Schreiben zu
        # bemerken, warf den ganzen Lauf weg.
        try:
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.touch()
        except OSError as error:
            print(f"--output nicht beschreibbar: {error}", file=sys.stderr)
            return 2

    # Derselbe Massstab wie im Scoring: Wuerde der Messlauf Staende
    # mitzaehlen, die das Scoring spaeter verwirft, passten die Schwellen
    # nicht zu den Werten, gegen die sie angewandt werden.
    max_age_days = config.scoring.analyst_max_age_days

    ergebnisse: list[tuple[str, AnalystRecommendations]] = []
    fehler: list[tuple[str, str]] = []
    for symbol in wanted:
        stock = Stock(id=uuid4(), symbol=symbol, exchange=args.exchange)
        try:
            empfehlungen = provider.recommendations(stock)
        except AnalystRecommendationsProviderError as error:
            # Ein Ausfall bei einer Aktie kostet nicht den Messlauf: Bei
            # zweihundert Symbolen waere das die teuerste denkbare Reaktion
            # auf den haeufigsten Fehler.
            fehler.append((symbol, str(error)))
            print(f"{symbol}: {error}", file=sys.stderr)
            continue
        ergebnisse.append((symbol, empfehlungen))
        if len(wanted) == 1:
            _print_analyst_recommendations(symbol, empfehlungen)
        else:
            _print_analyst_summary_line(symbol, empfehlungen, max_age_days)

    if ziel is not None:
        _write_ratings_csv(ziel, ergebnisse, max_age_days)
        print(f"\nCSV geschrieben: {ziel}")
    if len(wanted) > 1:
        _print_ratings_uebersicht(ergebnisse, fehler, len(wanted), max_age_days)

    if not ergebnisse:
        return 2
    # Fehlende Abdeckung ist kein Fehler des Befehls -- er hat sauber
    # geantwortet, dass es nichts gibt (ADR 0043).
    return 0


def _print_analyst_summary_line(
    symbol: str, empfehlungen: AnalystRecommendations, max_age_days: int
) -> None:
    """Eine Zeile je Aktie -- der volle Block laeuft bei zweihundert Titeln
    aus dem Terminalpuffer (Muster ``_print_fundamental_summary_line``)."""
    anteil = analyst_buy_share(empfehlungen, max_age_days=max_age_days)
    stand = empfehlungen.latest
    print(
        f"  {symbol:<8}{empfehlungen.status.value:<18}"
        f"{(f'{anteil:.1%}' if anteil is not None else '--'):>8}"
        f"{(stand.total if stand is not None else 0):>7} Voten"
        f"  {stand.period.isoformat() if stand is not None else ''}"
    )


def _write_ratings_csv(
    pfad: Path, ergebnisse: Sequence[tuple[str, AnalystRecommendations]], max_age_days: int
) -> None:
    """Der Kauf-Anteil je Aktie, in den Spalten der Fundamental-CSV.

    ``symbol``, ``kennzahl`` und ``wert`` sind die drei, die
    'calibrate-scores' liest -- deshalb heissen sie hier genauso. Die uebrigen
    Spalten belegen den Wert: Ohne den Monatsstand und die Zahl der Voten
    liesse sich ein Anteil von 1,0 aus drei Voten nicht von einem aus vierzig
    unterscheiden.

    Eine Aktie ohne Anteil steht mit leeren Feldern in der Datei und nicht
    gar nicht: 'calibrate-scores' zaehlt sie dann bei der Abdeckung mit und
    weist sie aus.
    """
    with pfad.open("w", encoding="utf-8", newline="") as datei:
        schreiber = csv.writer(datei)
        schreiber.writerow(
            ["symbol", "status", "kennzahl", "wert", "monatsstand", "voten", "quelle", "abgerufen"]
        )
        for symbol, empfehlungen in ergebnisse:
            anteil = analyst_buy_share(empfehlungen, max_age_days=max_age_days)
            stand = empfehlungen.latest
            schreiber.writerow(
                [
                    symbol,
                    empfehlungen.status.value,
                    ANALYST_BUY_SHARE_LABEL if anteil is not None else "",
                    f"{anteil:.6f}" if anteil is not None else "",
                    stand.period.isoformat() if stand is not None else "",
                    stand.total if stand is not None else "",
                    empfehlungen.source or "",
                    empfehlungen.retrieved_at.isoformat()
                    if empfehlungen.retrieved_at is not None
                    else "",
                ]
            )


def _print_ratings_uebersicht(
    ergebnisse: Sequence[tuple[str, AnalystRecommendations]],
    fehler: Sequence[tuple[str, str]],
    gesamt: int,
    max_age_days: int,
) -> None:
    """Wofuer es einen Anteil gibt und wofuer nicht -- ausdruecklich."""
    mit_anteil = [
        symbol
        for symbol, empfehlungen in ergebnisse
        if analyst_buy_share(empfehlungen, max_age_days=max_age_days) is not None
    ]
    ohne_anteil = [
        symbol
        for symbol, empfehlungen in ergebnisse
        if analyst_buy_share(empfehlungen, max_age_days=max_age_days) is None
    ]
    print(f"\n{gesamt} Aktien, {len(mit_anteil)} mit Kauf-Anteil.")
    if ohne_anteil:
        print(f"  Ohne Anteil: {len(ohne_anteil)} ({', '.join(sorted(ohne_anteil))})")
    if fehler:
        print(f"  Abruf fehlgeschlagen: {len(fehler)}")
        for symbol, meldung in fehler:
            print(f"    {symbol:<8}{meldung}")


def _print_analyst_recommendations(symbol: str, empfehlungen: AnalystRecommendations) -> None:
    print(f"\n{symbol} -- Analystenempfehlungen ({empfehlungen.analysis_version})")
    print(f"  Status:  {empfehlungen.status.value}")
    print(f"  Quelle:  {empfehlungen.source or '--'}")
    if empfehlungen.retrieved_at is not None:
        print(f"  Abruf:   {empfehlungen.retrieved_at.isoformat()}")
    if empfehlungen.reason is not None:
        print(f"  Grund:   {empfehlungen.reason}")

    if not empfehlungen.periods:
        print("\n  Keine Monatsstaende.")
        return

    print(f"\n  {'Monat':<12}{'S-Buy':>7}{'Buy':>7}{'Hold':>7}{'Sell':>7}{'S-Sell':>8}{'Summe':>8}")
    for stand in empfehlungen.periods:
        print(
            f"  {stand.period.isoformat():<12}"
            f"{stand.strong_buy:>7}{stand.buy:>7}{stand.hold:>7}"
            f"{stand.sell:>7}{stand.strong_sell:>8}{stand.total:>8}"
        )
    # Ausdruecklich keine Konsenszahl: Wie aus der Verteilung ein Teilwert
    # wird, entscheidet das Scoring (ADR 0043). Eine hier gebildete Kennzahl
    # waere eine zweite, abweichende Rechnung.
    print("\n  Kursziele: dauerhaft zurueckgestellt (ADR 0043).")


def require_complete_enough(zusammenfassung: AnalysisRunSummary, minimum: float) -> None:
    """Hat der Lauf genug Aktien gerechnet, um als erledigt zu gelten?

    Der Analyse-Lauf isoliert Fehler je Aktie und wirft deshalb nicht: Reisst
    die Verbindung nach der ersten Aktie ab, kommt eine Zusammenfassung mit
    einem Ergebnis und 191 Fehlern zurueck. Ohne diese Pruefung haette der
    Dispatcher den Abend als erledigt vermerkt -- und ein erledigter Lauf wird
    weder wiederholt noch nach Fristablauf gemeldet. Der Handelstag waere
    still verlorengegangen.

    Der Fehler geht denselben Weg wie ein TWS-Ausfall: Der Lauf gilt als
    gescheitert, der naechste Start versucht es erneut.
    """
    anteil = zusammenfassung.completion_ratio
    if anteil >= minimum:
        return
    gesamt = len(zusammenfassung.outcomes) + len(zusammenfassung.errors)
    raise MarketDataProviderError(
        f"Nur {len(zusammenfassung.outcomes)} von {gesamt} Aktien gerechnet "
        f"({anteil:.0%}, verlangt sind mindestens {minimum:.0%}). Der Lauf gilt "
        "nicht als erledigt."
    )


DISPATCH_EXIT_CODES = {
    DispatchDecision.RUN: 0,
    DispatchDecision.TOO_EARLY: 0,
    DispatchDecision.NO_TRADING_DAY: 0,
    DispatchDecision.ALREADY_DONE: 0,
    DispatchDecision.IN_PROGRESS: 0,
    DispatchDecision.TOO_LATE: 1,
}
"""Was die Aufgabenplanung zu sehen bekommt.

"Nichts zu tun" ist bewusst 0: Bei einem Start alle 15 Minuten waere alles
andere ein Protokoll voller Fehlschlaege, in dem der echte nicht mehr
auffiele. Nur ein *versuchter und gescheiterter* Lauf ergibt 1 -- und der
abgelaufene Nachholzeitraum, weil dann tatsaechlich etwas ausgefallen ist.
"""


def command_dispatch(args: argparse.Namespace) -> int:
    """Der Einstieg fuer die Aufgabenplanung (ADR 0019).

    Faellt fast immer sofort wieder heraus. Nur wenn die Zielkerze
    geschlossen, der Sicherheitspuffer abgelaufen und der Lauf noch nicht
    erledigt ist, holt er Daten und rechnet.
    """
    try:
        loaded = load_config(args.config)
        config = loaded.config
        indicators = config.require_indicators()
    except (ConfigError, GateNotClearedError) as error:
        # Rueckgabewert 2, nicht 1: Ein erneuter Start in 15 Minuten aendert
        # daran nichts, und die Aufgabenplanung soll das unterscheiden koennen.
        print(f"Konfiguration: {error}", file=sys.stderr)
        return 2
    configure_logging(LoggingConfig(level="INFO", format="console"))

    if args.provider is not None:
        market_data = config.market_data.model_copy(update={"provider": args.provider})
        config = config.model_copy(update={"market_data": market_data})
    if config.market_data.provider != "ibkr":
        print(
            "market_data.provider steht auf "
            f"'{config.market_data.provider}'. Der taegliche Lauf holt Daten von der "
            "TWS -- entweder '--provider ibkr' angeben oder die Konfiguration umstellen.",
            file=sys.stderr,
        )
        return 2

    # Alle sechs Analyseanbieter stehen ausgeliefert auf 'fixture', damit Start
    # und Tests ohne Zugangsdaten auskommen. Der produktive Schalter gehoert
    # deshalb hierher und nicht in config/default.yaml: Die Aufgabenplanung
    # traegt ihn in ihren Argumenten, und ein 'git pull' auf dem Server findet
    # keinen lokalen Diff vor -- dieselbe Begruendung wie bei '--provider
    # ibkr'.
    #
    # Es muessen **alle sechs** sein. Fehlte auch nur einer, bliebe sein
    # Abschnitt im Bericht bei den Fixture-Werten stehen -- und die sehen dort
    # wie ein Ergebnis aus, nicht wie eine Luecke. Der Ausweg waere dann, die
    # ausgelieferte Konfiguration auf dem Server zu editieren; genau das
    # schliesst Doc 14 aus.
    #
    # Fuer die zwei LLM-Agenten gibt es als dritten Wert 'none': der ehrliche
    # Aus-Schalter fuer einen Scharfbetrieb, der den Agenten nicht bezahlen
    # will -- UNAVAILABLE mit Grund statt eines Fixture-Schein-Ergebnisses.
    for argument, abschnitt in (
        (args.earnings_provider, "earnings_filter"),
        (args.research_provider, "research"),
        (args.fundamentals_provider, "fundamentals"),
        (args.ratings_provider, "analyst_ratings"),
        (args.technical_agent_provider, "technical_agent"),
        (args.options_provider, "options"),
    ):
        if argument is None:
            continue
        aktuell = getattr(config, abschnitt)
        config = config.model_copy(
            update={abschnitt: aktuell.model_copy(update={"provider": argument})}
        )
    if args.notification_channel is not None or args.telegram_chat_id is not None:
        aenderung: dict[str, object] = {}
        if args.notification_channel is not None:
            aenderung["channel"] = args.notification_channel
        if args.telegram_chat_id is not None:
            aenderung["telegram"] = config.notifications.telegram.model_copy(
                update={"chat_id": args.telegram_chat_id}
            )
        notifications = config.notifications.model_copy(update=aenderung)
        config = config.model_copy(update={"notifications": notifications})

    # Vor dem Lauf, nicht in der Analyse: Ein fehlendes Geheimnis ist ein
    # Konfigurationsfehler und kein voruebergehender Ausfall. Erst hinter dem
    # Backfill bemerkt, haette er 192 Symbole lang gewartet, Rueckgabewert 1
    # ergeben -- "versuch's in 15 Minuten" -- und am Ende als "die TWS laeuft
    # nicht" gemeldet. Derselbe Grund gilt fuer den Benachrichtigungskanal
    # (ADR 0024): eine unvollstaendige Einstellung soll sofort auffallen.
    secrets = Secrets()
    try:
        standardzeitraum = duration_in_days(config.market_data.ibkr.history_duration)
        notifier = build_notifier(config.notifications, secrets)
        earnings_provider = build_earnings_provider(config, secrets)
        research_provider = build_research_provider(config, secrets)
        technical_interpreter = build_technical_interpreter(config, secrets)
        # Ebenfalls hier und nicht erst in 'analyse': Der Bau braucht seit
        # ATA_EDGAR_CONTACT ein Geheimnis, und 'analyse' laeuft hinter dem
        # halbstuendigen Backfill. Dort bemerkt, waere es genau der Fall, den
        # der Kommentar oben beschreibt.
        fundamental_provider = build_fundamental_data_provider(config, secrets)
        # Aus demselben Grund: 'finnhub' verlangt den Zugangsschluessel, und
        # der fehlt entweder von Anfang an oder gar nicht.
        ratings_provider = build_analyst_recommendations_provider(config, secrets)
    except (ValueError, NotificationChannelNotConfiguredError, MissingSecretError) as error:
        print(f"Konfiguration: {error}", file=sys.stderr)
        return 2

    watchlist = tuple(build_watchlist(config, project_root(loaded.source_path)))
    if not watchlist:
        print("Die Watchlist ist leer -- es gibt nichts zu rechnen.", file=sys.stderr)
        return 2

    engine = _open_database()
    if engine is None:
        return 2
    session_factory = build_session_factory(engine)

    def uow_factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    bar_source = build_ibkr_bar_source(config)
    runs = SqlAlchemyDispatcherRunRepository(session_factory(), engine)

    def backfill() -> None:
        bericht = BackfillHistoryUseCase(
            bar_source, uow_factory, default_days=standardzeitraum
        ).execute(watchlist, on_progress=_print_backfill_progress)
        if bericht.failures:
            # Einzelne Ausfaelle sind hingenommen -- faellt aber *alles* aus,
            # ist die TWS weg, und daraus darf kein Analyse-Lauf entstehen.
            if len(bericht.failures) == len(bericht.results):
                raise MarketDataProviderError(
                    f"Keine einzige Aktie konnte geholt werden ({len(bericht.failures)} "
                    f"Ausfaelle), zuerst: {bericht.failures[0].error}"
                )
            _logger_cli.warning(
                "%d von %d Aktien ohne neue Daten -- der Lauf geht trotzdem weiter.",
                len(bericht.failures),
                len(bericht.results),
            )

    def analyse(erwartete_kerze: datetime) -> None:
        provider = build_market_data_provider(
            config,
            indicators,
            project_root(loaded.source_path),
            watchlist,
            # Ausdruecklich dieselbe Quelle: Bei 'source: live' entstuende
            # sonst eine zweite TWS-Verbindung mit derselben Client-ID,
            # waehrend die erste noch haengt -- IBKR laesst nur eine zu.
            bar_source=None if config.market_data.source == "stored" else bar_source,
            uow_factory=uow_factory,
        )
        rule = CandidateRuleParameters(
            required_crossing_signals=config.screening.required_crossing_signals,
            signal_lookback_previous_candles=config.screening.signal_lookback_previous_candles,
            warmup_candles=indicators.warmup_candles,
        )
        zusammenfassung = RunAnalysisUseCase(
            provider,
            earnings_provider,
            research_provider,
            technical_interpreter,
            fundamental_provider,
            ratings_provider,
            # Dieselbe TWS-Anbindung wie der Backfill -- IBKR laesst je
            # Client-ID nur eine Verbindung zu (ADR 0048).
            build_options_provider(config, project_root(loaded.source_path), bar_source),
            uow_factory,
            rule,
            build_earnings_filter_params(config),
            build_technical_analysis_params(config),
            build_backtest_params(config),
            build_scoring_params(config),
            expected_last_candle=erwartete_kerze,
            agent_concurrency=build_agent_concurrency(config),
            app_version=app_version(),
            # Nur im Tageslauf, nicht bei einem manuellen 'screen': Eine
            # Push-Nachricht auf Zuruf waere ueberraschend (ADR 0040).
            notifier=notifier,
            notify_without_candidates=config.notifications.send_when_no_candidates,
            market_timezone=config.market.timezone,
            # Nur im Tageslauf: Ein manueller 'screen' kennt keine Sperre --
            # dort entscheidet der Mensch, was er sehen will (ADR 0054).
            repeat_suppression=build_repeat_suppression_params(config),
        ).execute()
        kandidaten = [
            ergebnis.stock.symbol
            for ergebnis in zusammenfassung.outcomes
            if ergebnis.result.status is ScreeningStatus.CANDIDATE
        ]
        print(
            f"Analyse-Lauf {zusammenfassung.run.id}: {len(zusammenfassung.outcomes)} Aktien, "
            f"{len(kandidaten)} Kandidaten, {len(zusammenfassung.errors)} Fehler"
        )
        if kandidaten:
            print(f"Kandidaten: {', '.join(kandidaten)}")

        require_complete_enough(zusammenfassung, config.scheduler.minimum_completion_ratio)

    def latest_stored_bar() -> datetime | None:
        with uow_factory() as uow:
            return uow.intraday_bars.latest_start_overall()

    use_case = DispatchDailyRunUseCase(
        calendar=IbkrTradingCalendar(bar_source, watchlist[0]),
        runs=runs,
        parameters=SchedulerParameters(
            timeframe_minutes=config.market.timeframe_minutes,
            daily_candle_index=config.market.daily_candle_index,
            safety_buffer_seconds=config.scheduler.safety_buffer_seconds,
            max_catch_up_seconds=config.scheduler.max_catch_up_seconds,
            timezone=config.market.timezone,
            session_open=config.market.session_open_time(),
            session_minutes=config.market.regular_session_minutes,
        ),
        backfill=backfill,
        analyse=analyse,
        latest_stored_bar=latest_stored_bar,
        notifier=notifier,
        native_bar_minutes=config.market_data.ibkr.native_bar_minutes,
    )

    try:
        ergebnis = use_case.execute()
    except KeyboardInterrupt:
        print("\nAbgebrochen.", file=sys.stderr)
        return 130
    finally:
        bar_source.close()

    _print_dispatch(ergebnis)
    if ergebnis.failed:
        return 1
    return DISPATCH_EXIT_CODES[ergebnis.decision]


def _print_dispatch(ergebnis: DispatchOutcome) -> None:
    zeitpunkt = ergebnis.scheduled.candle_close.isoformat() if ergebnis.scheduled else "unbestimmt"
    if ergebnis.error is not None:
        print(f"Lauf fuer {zeitpunkt} gescheitert: {ergebnis.error}", file=sys.stderr)
        return
    texte = {
        DispatchDecision.RUN: f"Lauf fuer {zeitpunkt} abgeschlossen.",
        DispatchDecision.TOO_EARLY: f"Noch zu frueh -- Kerze {zeitpunkt}.",
        DispatchDecision.NO_TRADING_DAY: "Kein Handelstag.",
        DispatchDecision.ALREADY_DONE: f"Bereits erledigt -- Kerze {zeitpunkt}.",
        DispatchDecision.IN_PROGRESS: "Ein vorheriger Start arbeitet noch.",
        DispatchDecision.TOO_LATE: f"Nachholfrist fuer {zeitpunkt} abgelaufen.",
    }
    print(texte[ergebnis.decision])


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

    calibrate = subparsers.add_parser(
        "calibrate-scores",
        help=(
            "Misst die Verteilung der Fundamentalkennzahlen ueber die Watchliste "
            "(Grundlage der Score-Schwellen, ADR 0041). Liest die CSV von "
            "'fundamental --output', legt nichts ab und braucht kein Netz."
        ),
    )
    calibrate.add_argument(
        "--input",
        required=True,
        help="Die CSV aus 'fundamental --watchlist --price-from-bars --output'.",
    )
    calibrate.set_defaults(handler=command_calibrate_scores)

    depth = subparsers.add_parser(
        "history-depth",
        help=(
            "Misst, wie weit IBKR die Historie hergibt (offene Entscheidung E2). "
            "Legt nichts ab und braucht keine Datenbank."
        ),
    )
    depth.add_argument(
        "--provider",
        choices=("fixture", "ibkr"),
        default=None,
        help="Uebersteuert market_data.provider nur fuer diesen Lauf.",
    )
    depth.add_argument(
        "--symbols",
        default=None,
        help="Kommagetrennte Symbole statt der Watchlist.",
    )
    depth.add_argument(
        "--limit",
        type=_positive_count,
        default=None,
        help=(
            f"Nur die ersten N Aktien. Ohne Angabe werden aus der Watchlist die ersten "
            f"{STANDARD_TITEL_TIEFENMESSUNG} genommen -- die Messung kostet je Aktie "
            "mehrere Anfragen. Ausdruecklich genannte '--symbols' werden ohne diese "
            "Angabe nie gekuerzt."
        ),
    )
    depth.add_argument(
        "--window-days",
        type=_positive_count,
        default=FENSTERGROESSE_TAGE,
        help=(
            f"Groesse eines Fensters in Tagen (Standard {FENSTERGROESSE_TAGE}). Ein Jahr "
            "ist als Anfragegroesse belegt -- es ist der Zeitraum des taeglichen Backfills."
        ),
    )
    depth.add_argument(
        "--max-windows",
        type=_positive_count,
        default=HOECHSTZAHL_FENSTER,
        help=(
            f"Reissleine: hoechstens so viele Fenster je Aktie (Standard "
            f"{HOECHSTZAHL_FENSTER}). Wird sie erreicht, weist der Bericht die Tiefe "
            "als Untergrenze aus."
        ),
    )
    depth.add_argument(
        "--no-pacing",
        action="store_true",
        help=(
            "Ohne Mindestabstand zwischen den Anfragen. Nur fuer eine kurze Messung -- "
            "IBKR sperrt die Verbindung bei mehr als 60 Anfragen in zehn Minuten."
        ),
    )
    depth.set_defaults(handler=command_history_depth)

    deepen = subparsers.add_parser(
        "deepen-history",
        help=(
            "Einmaliger Tiefen-Backfill: fuellt den Bestand rueckwaerts auf "
            "backtesting.history_years auf (ADR 0028). Laeuft stundenlang, ist "
            "abbrechbar und setzt beim naechsten Start dort an."
        ),
    )
    deepen.add_argument(
        "--provider",
        choices=("fixture", "ibkr"),
        default=None,
        help="Uebersteuert market_data.provider nur fuer diesen Lauf.",
    )
    deepen.add_argument(
        "--symbols",
        default=None,
        help="Kommagetrennte Symbole statt der Watchlist.",
    )
    deepen.add_argument(
        "--limit",
        type=_positive_count,
        default=None,
        help="Nur die ersten N Aktien -- fuer einen Probelauf vor der vollen Watchlist.",
    )
    deepen.add_argument(
        "--years",
        type=_positive_count,
        default=None,
        help=(
            "Zieltiefe in Jahren. Ohne Angabe backtesting.history_years aus der "
            "Konfiguration -- das ist der Regelfall."
        ),
    )
    deepen.add_argument(
        "--window-days",
        type=_positive_count,
        default=FENSTERGROESSE_HANDELSTAGE,
        help=(
            f"Groesse eines Fensters in **Handelstagen** (Standard "
            f"{FENSTERGROESSE_HANDELSTAGE}). IBKR rechnet die Zeitraumangabe bei "
            "Intraday-Bars in Handelstagen, nicht in Kalendertagen (ADR 0028)."
        ),
    )
    deepen.add_argument(
        "--no-pacing",
        action="store_true",
        help=(
            "Ohne Mindestabstand zwischen den Anfragen. Nur fuer wenige Symbole -- "
            "IBKR sperrt die Verbindung bei mehr als 60 Anfragen in zehn Minuten."
        ),
    )
    deepen.set_defaults(handler=command_deepen_history)

    export = subparsers.add_parser(
        "export-bars",
        help=(
            "Schreibt gespeicherte Bars als CSV heraus -- fuer einen echten "
            "Datenausschnitt im Golden Master (tests/golden)."
        ),
    )
    export.add_argument(
        "--symbols",
        required=True,
        help="Kommagetrennte Symbole. Je Symbol entsteht eine Datei <symbol>.bars.csv.",
    )
    export.add_argument(
        "--output",
        required=True,
        help="Vorhandenes Zielverzeichnis, etwa backend\\tests\\golden\\data.",
    )
    export.add_argument(
        "--since",
        type=date.fromisoformat,
        default=None,
        help=(
            "Nur Bars ab diesem Datum (JJJJ-MM-TT). Ohne Angabe der ganze Bestand -- "
            "der ist fuer eine eingefrorene Datei meist mehr, als gebraucht wird."
        ),
    )
    export.set_defaults(handler=command_export_bars)

    reach = subparsers.add_parser(
        "calendar-reach",
        help=(
            "Misst, wie weit der TWS-Handelskalender voraus reicht -- die offene "
            "Frage hinter E4 (Wochentagsnaeherung im Earnings-Filter)."
        ),
    )
    reach.add_argument("--provider", choices=("ibkr",), default=None)
    reach.add_argument(
        "--symbols",
        default=None,
        help=(
            "Kommagetrennte Symbole; gefragt wird nur das erste. Ohne Angabe das "
            "erste der Watchlist -- die Handelszeiten gelten fuer die Boerse, "
            "nicht fuer das einzelne Papier."
        ),
    )
    reach.add_argument("--config", default=argparse.SUPPRESS)
    reach.set_defaults(handler=command_calendar_reach)

    dispatch = subparsers.add_parser(
        "dispatch",
        help=(
            "Der taegliche Lauf fuer die Aufgabenplanung: holt die Luecke und rechnet, "
            "aber nur wenn die Zielkerze geschlossen und der Lauf noch nicht erledigt ist."
        ),
    )
    dispatch.add_argument(
        "--provider",
        choices=("fixture", "ibkr"),
        default=None,
        help="Uebersteuert market_data.provider nur fuer diesen Lauf.",
    )
    dispatch.add_argument(
        "--earnings-provider",
        choices=("fixture", "finnhub"),
        default=None,
        help=(
            "Uebersteuert earnings_filter.provider nur fuer diesen Lauf. 'finnhub' "
            "braucht ATA_FINNHUB_API_KEY und liefert echte Termine statt der "
            "Fixture-Daten."
        ),
    )
    dispatch.add_argument(
        "--research-provider",
        choices=("fixture", "anthropic", "none"),
        default=None,
        help=(
            "Uebersteuert research.provider nur fuer diesen Lauf. 'anthropic' braucht "
            "ATA_LLM_API_KEY und loest je Kandidat einen echten, kostenpflichtigen "
            "API-Aufruf aus. 'none' schaltet den Agenten bewusst ab: Der "
            "Berichtspunkt erscheint als gekennzeichnete Luecke (provider_disabled) "
            "statt als Fixture-Schein-Ergebnis; kostet nichts, braucht keinen "
            "Schluessel."
        ),
    )
    dispatch.add_argument(
        "--ratings-provider",
        choices=("fixture", "finnhub"),
        default=None,
        help=(
            "Uebersteuert analyst_ratings.provider nur fuer diesen Lauf. "
            "'finnhub' fuellt Berichtspunkt 9 mit gezaehlten Analystenvoten; "
            "ohne den Schalter bleibt er auf den Fixture-Werten stehen. "
            "Kostenlos, braucht aber ATA_FINNHUB_API_KEY."
        ),
    )
    dispatch.add_argument(
        "--fundamentals-provider",
        choices=("fixture", "edgar"),
        default=None,
        help=(
            "Uebersteuert fundamentals.provider nur fuer diesen Lauf. 'edgar' braucht "
            "ATA_EDGAR_CONTACT und liest die SEC-Einreichungen; ohne diese Angabe "
            "traegt Berichtspunkt 10 fuer jedes Symbol dieselben Fixture-Zahlen."
        ),
    )
    dispatch.add_argument(
        "--technical-agent-provider",
        choices=("fixture", "anthropic", "none"),
        default=None,
        help=(
            "Uebersteuert technical_agent.provider nur fuer diesen Lauf. 'anthropic' "
            "braucht ATA_LLM_API_KEY und loest je Kandidat einen kostenpflichtigen "
            "Modellaufruf aus (rund 0,005 USD). 'none' schaltet den Agenten bewusst "
            "ab (gekennzeichnete Luecke statt Fixture-Einstufungen). Bewusst "
            "getrennt von '--research-provider': Beide Agenten sind entkoppelt und "
            "haben eigene Pools (ADR 0037)."
        ),
    )
    dispatch.add_argument(
        "--options-provider",
        choices=("fixture", "ibkr"),
        default=None,
        help=(
            "Uebersteuert options.provider nur fuer diesen Lauf. 'ibkr' fuellt "
            "Berichtspunkt 13 mit Put-Vorschlaegen aus der echten Optionskette "
            "und braucht ein Optionsmarktdaten-Abo; ohne den Schalter bleibt er "
            "auf den Fixture-Werten stehen."
        ),
    )
    dispatch.add_argument(
        "--notification-channel",
        choices=("dry_run", "telegram"),
        default=None,
        help=(
            "Uebersteuert notifications.channel nur fuer diesen Lauf. 'telegram' "
            "braucht ATA_NOTIFICATION_TOKEN und --telegram-chat-id (ADR 0024)."
        ),
    )
    dispatch.add_argument(
        "--telegram-chat-id",
        default=None,
        help=(
            "Uebersteuert notifications.telegram.chat_id nur fuer diesen Lauf. Kein "
            "Geheimnis, gehoert aber wie die Anbieter-Schalter in die Argumente der "
            "Aufgabenplanung statt in config/default.yaml."
        ),
    )
    dispatch.set_defaults(handler=command_dispatch)

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

    chart = subparsers.add_parser(
        "chart",
        help="Validierungschart als HTML -- Kursverlauf mit jedem Urteil der Regel.",
    )
    chart.add_argument(
        "--symbols",
        required=True,
        help="Kommagetrennte Symbole. Je Symbol entsteht eine HTML-Datei.",
    )
    chart.add_argument(
        "--output",
        default="charts",
        help="Zielverzeichnis der HTML-Dateien (Vorgabe: charts).",
    )
    chart.add_argument(
        "--provider",
        choices=("fixture", "ibkr"),
        default=None,
        help="Uebersteuert market_data.provider nur fuer diesen Lauf.",
    )
    chart.set_defaults(handler=command_chart)

    technical = subparsers.add_parser(
        "technical",
        help="Deterministische Chartauswertung eines Symbols aus dem Bestand anzeigen.",
    )
    technical.add_argument(
        "--provider",
        choices=("fixture", "ibkr"),
        default=None,
        help=(
            "Uebersteuert market_data.provider nur fuer diesen Lauf. Die "
            "Chartauswertung braucht 'ibkr' -- ohne laufende TWS, aber mit "
            "gefuelltem Bestand."
        ),
    )
    technical.add_argument(
        "--symbols",
        required=True,
        help="Kommagetrennte Symbole, z. B. 'AAPL,MSFT'.",
    )
    technical.add_argument(
        "--interpret",
        action="store_true",
        help=(
            "Laesst die Auswertung zusaetzlich vom Technical Agent einordnen "
            "(ADR 0026). Ohne diese Angabe bleibt das Kommando kostenfrei."
        ),
    )
    technical.add_argument(
        "--agent-provider",
        choices=("fixture", "anthropic", "none"),
        default=None,
        help=(
            "Uebersteuert technical_agent.provider nur fuer diesen Lauf. "
            "'anthropic' loest je Symbol einen kostenpflichtigen Modellaufruf aus, "
            "'none' schaltet den Agenten bewusst ab (UNAVAILABLE statt "
            "Fixture-Einstufungen). Bewusst getrennt von '--provider', das die "
            "Marktdaten steuert."
        ),
    )
    technical.add_argument(
        "--show-prompt",
        action="store_true",
        help="Zeigt zusaetzlich, welche Daten dem Modell uebergeben wurden.",
    )
    technical.set_defaults(handler=command_technical)

    fundamental = subparsers.add_parser(
        "fundamental",
        help="Deterministische Fundamentalkennzahlen aus den SEC-Einreichungen (ADR 0032).",
    )
    fundamental.add_argument(
        "--provider",
        choices=("fixture", "edgar"),
        default=None,
        help=(
            "Uebersteuert fundamentals.provider nur fuer diesen Lauf. 'edgar' ruft "
            "die SEC ab -- kostenlos, aber gedrosselt und je Aktie mehrere Megabyte."
        ),
    )
    fundamental.add_argument(
        "--symbols",
        default="",
        help="Kommagetrennte Symbole, z. B. 'AAPL,NVDA'. Alternativ --watchlist.",
    )
    fundamental.add_argument(
        "--watchlist",
        action="store_true",
        help=(
            "Wertet jedes Symbol der Watchlist aus. Gedacht fuer die Messung der "
            "Tag-Abdeckung (ADR 0032 L1) -- sinnvoll nur zusammen mit --summary."
        ),
    )
    fundamental.add_argument(
        "--summary",
        action="store_true",
        help=(
            "Eine Zeile je Aktie statt des vollen Blocks, dazu eine Auswertung am "
            "Ende. Der volle Block laeuft bei hundert Titeln aus dem Terminalpuffer."
        ),
    )
    fundamental.add_argument(
        "--output",
        default=None,
        help="Schreibt alle Einzelwerte als CSV, damit nichts am Puffer haengt.",
    )
    fundamental.add_argument(
        "--market-data-provider",
        choices=("fixture", "ibkr"),
        default=None,
        help=(
            "Uebersteuert market_data.provider nur fuer diesen Lauf -- noetig fuer "
            "--price-from-bars. Der Schalter heisst nicht '--provider', weil der "
            "bei diesem Unterbefehl schon die Fundamentalquelle uebersteuert. Auf dem "
            "Server bleibt config/default.yaml unveraendert, damit 'git pull' keinen "
            "lokalen Diff vorfindet; produktive Quellen werden ueber Schalter gesetzt."
        ),
    )
    fundamental.add_argument(
        "--price-from-bars",
        action="store_true",
        help=(
            "Nimmt je Aktie den Schluss der letzten abgeschlossenen Kerze aus dem "
            "gespeicherten Bestand -- dieselbe Regel wie im Tageslauf (ADR 0035). "
            "Erst damit rechnet ein Lauf ueber die Watchliste die vier "
            "bewertungsabhaengigen Kennzahlen. Setzt einen gefuellten Bestand voraus "
            "und laedt dafuer die volle Historie jeder Aktie -- das verdoppelt die "
            "Laufzeit ungefaehr."
        ),
    )
    fundamental.add_argument(
        "--exchange",
        default="NASDAQ",
        help="Nur fuer die Bildung des Symbols relevant; EDGAR kennt keine Boerse.",
    )
    fundamental.add_argument(
        "--price",
        type=float,
        default=None,
        help=(
            "Kurs fuer die Bewertungskennzahlen -- die optionale, nicht blockierende "
            "Eingabe aus ADR 0032. Ohne ihn entfallen genau die vier "
            "bewertungsabhaengigen Kennzahlen, alle uebrigen bleiben vollstaendig."
        ),
    )
    fundamental.set_defaults(handler=command_fundamental)

    research = subparsers.add_parser(
        "research",
        help="Manueller Probelauf des Research Agent fuer ein einzelnes Symbol (ADR 0021/0023).",
    )
    research.add_argument(
        "--provider",
        choices=("fixture", "anthropic", "none"),
        default=None,
        help=(
            "Uebersteuert research.provider nur fuer diesen Lauf. 'anthropic' loest "
            "einen echten, kostenpflichtigen API-Aufruf aus. 'none' liefert die "
            "gekennzeichnete Luecke (provider_disabled) -- die Einzelprobe des "
            "abgeschalteten Zustands."
        ),
    )
    research.add_argument("--symbol", required=True, help="Das zu recherchierende Symbol.")
    research.add_argument(
        "--exchange",
        default="NASDAQ",
        help="Nur fuer die Anfrage an das Sprachmodell relevant, nicht persistiert.",
    )
    research.add_argument(
        "--max-searches",
        # model_copy(update=...) umgeht die Pydantic-Pruefung, deshalb hier
        # validieren -- sonst erreichte '--max-searches 0' die API als
        # 'max_uses: 0'.
        type=_positive_count,
        default=None,
        help=(
            "Uebersteuert research.max_searches nur fuer diesen Lauf. Achtung: Ein "
            "zu knapper Wert kann teurer werden statt billiger -- das Modell "
            "versucht abgelehnte Aufrufe erneut, und jeder Versuch verrechnet den "
            "Kontext neu."
        ),
    )
    research.add_argument(
        "--max-fetches",
        type=_positive_count,
        default=None,
        help="Uebersteuert research.max_fetches nur fuer diesen Lauf.",
    )
    research.set_defaults(handler=command_research)

    ratings = subparsers.add_parser(
        "ratings",
        help="Analystenempfehlungen eines Symbols oder der ganzen Watchliste (ADR 0043).",
    )
    ratings.add_argument(
        "--config",
        default=argparse.SUPPRESS,
        help="Pfad zur Konfigurationsdatei. Auch vor dem Unterbefehl zulaessig.",
    )
    ratings.add_argument(
        "--symbol", default=None, help="Ein Symbol, z. B. 'AAPL'. Alternativ --watchlist."
    )
    ratings.add_argument(
        "--watchlist",
        action="store_true",
        help=(
            "Fragt jedes Symbol der Watchlist ab -- der Messlauf fuer die Schwellen "
            "der News-Komponente. Rund zweihundert Abrufe, kostenlos."
        ),
    )
    ratings.add_argument(
        "--output",
        default=None,
        help=(
            "Schreibt den Kauf-Anteil je Aktie als CSV. Die Datei traegt die Spalten, "
            "die 'calibrate-scores' liest."
        ),
    )
    ratings.add_argument(
        "--exchange",
        default="NASDAQ",
        help="Nur fuer die Bildung des Symbols relevant; Finnhub kennt keine Boerse.",
    )
    ratings.add_argument(
        "--provider",
        choices=("fixture", "finnhub"),
        default=None,
        help=(
            "Uebersteuert analyst_ratings.provider nur fuer diesen Aufruf. "
            "'finnhub' ist kostenlos, braucht aber den Zugangsschluessel."
        ),
    )
    ratings.set_defaults(handler=command_ratings)

    options = subparsers.add_parser(
        "options",
        help="Cash-Secured-Put-Vorschlaege eines Symbols oder der Watchliste (ADR 0048).",
    )
    options.add_argument(
        "--config",
        default=argparse.SUPPRESS,
        help="Pfad zur Konfigurationsdatei. Auch vor dem Unterbefehl zulaessig.",
    )
    options.add_argument(
        "--symbol", default=None, help="Ein Symbol, z. B. 'AAPL'. Alternativ --watchlist."
    )
    options.add_argument(
        "--watchlist",
        action="store_true",
        help=(
            "Fragt jedes Symbol der Watchlist ab -- der Messlauf fuer die Schwellen "
            "der Optionsattraktivitaet."
        ),
    )
    options.add_argument(
        "--output",
        default=None,
        help=(
            "Schreibt die annualisierte Rendite je Aktie als CSV. Die Datei traegt "
            "die Spalten, die 'calibrate-scores' liest."
        ),
    )
    options.add_argument(
        "--price",
        type=float,
        default=None,
        help=(
            "Kurs von Hand statt aus dem Bestand -- fuer eine Probe ohne gefuellte "
            "Datenbank. Gilt nur zusammen mit --symbol."
        ),
    )
    options.add_argument(
        "--exchange",
        default="NASDAQ",
        help="Nur fuer die Bildung des Symbols relevant; der Kontrakt kommt aus der Watchliste.",
    )
    options.add_argument(
        "--provider",
        choices=("fixture", "ibkr"),
        default=None,
        help=(
            "Uebersteuert options.provider nur fuer diesen Aufruf. 'ibkr' braucht eine "
            "laufende TWS und das Optionsmarktdaten-Abo."
        ),
    )
    options.add_argument(
        "--market-data-provider",
        choices=("fixture", "ibkr"),
        default=None,
        help=(
            "Uebersteuert market_data.provider -- die Quelle des **Kurses**, nicht der "
            "Optionskette. Ohne 'ibkr' ist der Bestand leer und es gibt kein Strike-Band."
        ),
    )
    options.add_argument(
        "--market-data-type",
        type=int,
        choices=(1, 2, 3, 4),
        default=None,
        help=(
            "Uebersteuert options.market_data_type: 1 live, 2 'frozen', 3 verzoegert, "
            "4 verzoegert und 'frozen'. Nach Boersenschluss liefert 1 nichts mehr."
        ),
    )
    options.add_argument(
        "--record",
        default=None,
        help=(
            "Schreibt die Rohantworten der TWS zur Optionskette als JSON mit -- die "
            "Vorlage fuer den Contract-Test (A2-M7). Nur mit --symbol und "
            "'--provider ibkr'; am Ergebnis aendert der Schalter nichts."
        ),
    )
    options.set_defaults(handler=command_options)

    report = subparsers.add_parser(
        "report",
        help="Die gespeicherten Analyseberichte eines Laufs anzeigen (ADR 0039).",
    )
    report.add_argument(
        "--run",
        required=True,
        help="Lauf-ID (UUID). Zu finden ueber die API oder in der Tabelle analysis_runs.",
    )
    report.add_argument(
        "--symbol",
        default=None,
        help="Nur den Bericht dieser Aktie, statt aller Kandidaten des Laufs.",
    )
    report.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help=(
            "'text' ist die lesbare Fassung, 'json' das gespeicherte Dokument "
            "unveraendert -- die verbindliche Fassung."
        ),
    )
    report.add_argument(
        "--output",
        default=None,
        help="Datei statt Konsole. Wird vor dem ersten Datenbankzugriff geprueft.",
    )
    report.set_defaults(handler=command_report)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        exit_code: int = args.handler(args)
    except WatchlistError as error:
        print(f"Watchlist: {error}", file=sys.stderr)
        return 2
    finally:
        # Auch nach einem Abbruch: Eine Verbindung, die niemand mehr braucht,
        # gehoert geschlossen und nicht dem Aufraeumer ueberlassen.
        _alle_engines_schliessen()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
