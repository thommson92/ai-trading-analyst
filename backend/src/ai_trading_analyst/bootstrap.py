"""Composition Root.

Verdrahtet konkrete Infrastruktur (Fixture-Provider, SQLAlchemy) mit
Application und Presentation. Liegt bewusst ausserhalb der vier Schichten
(``domain``, ``application``, ``infrastructure``, ``presentation``) --
``tests/architecture/test_layer_boundaries.py`` prueft nur Importe innerhalb
dieser vier Pakete. Nur an dieser einen Stelle duerfen alle Schichten
gleichzeitig referenziert werden (Doc 10, Paragraph 9).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from functools import cache, partial
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import text

from ai_trading_analyst.application.read_run_overview import ReadRunOverviewUseCase
from ai_trading_analyst.application.run_analysis import AgentConcurrency
from ai_trading_analyst.config.loader import load_config, load_secrets
from ai_trading_analyst.config.settings import (
    AppConfig,
    DashboardExportConfig,
    IndicatorConfig,
    MissingSecretError,
    Secrets,
)
from ai_trading_analyst.domain.analysis import (
    AnalystRecommendationsProvider,
    EarningsProvider,
    FundamentalDataProvider,
    HistoricalBarSource,
    MarketDataProvider,
    MarketDataUnavailableError,
    OptionsDataProvider,
    RepeatSuppressionParameters,
    ResearchProvider,
    TechnicalInterpreter,
    UnitOfWork,
)
from ai_trading_analyst.domain.backtesting import BacktestParameters
from ai_trading_analyst.domain.backtesting.options_trade import OptionsBacktestParameters
from ai_trading_analyst.domain.earnings import EarningsFilterParameters
from ai_trading_analyst.domain.fundamentals import FundamentalParameters, MetricName
from ai_trading_analyst.domain.options import OptionsParameters
from ai_trading_analyst.domain.scoring import (
    SCORED_METRICS,
    SIGNAL_TEILWERTE,
    ComponentName,
    MetricThresholds,
    Recommendation,
    RecommendationParameters,
    ScoringParameters,
)
from ai_trading_analyst.domain.screening import (
    CandidateRuleParameters,
    IndicatorParameters,
    SessionParameters,
    SignalType,
)
from ai_trading_analyst.domain.technical import TechnicalAnalysisParameters
from ai_trading_analyst.infrastructure.anthropic import (
    AnthropicResearchPricing,
    AnthropicResearchProvider,
    AnthropicResearchSettings,
    AnthropicTechnicalInterpreter,
    AnthropicTechnicalPricing,
    AnthropicTechnicalSettings,
)
from ai_trading_analyst.infrastructure.disabled import (
    DisabledResearchProvider,
    DisabledTechnicalInterpreter,
)
from ai_trading_analyst.infrastructure.edgar import (
    EdgarConnectionSettings,
    EdgarFundamentalDataProvider,
)
from ai_trading_analyst.infrastructure.finnhub import (
    FinnhubAnalystRecommendationsProvider,
    FinnhubConnectionSettings,
    FinnhubEarningsProvider,
    FinnhubRecommendationSettings,
)
from ai_trading_analyst.infrastructure.fixtures.analyst_recommendations_provider import (
    FixtureAnalystRecommendationsProvider,
)
from ai_trading_analyst.infrastructure.fixtures.earnings_provider import FixtureEarningsProvider
from ai_trading_analyst.infrastructure.fixtures.fundamental_provider import (
    FixtureFundamentalDataProvider,
)
from ai_trading_analyst.infrastructure.fixtures.market_data_provider import (
    FixtureMarketDataProvider,
)
from ai_trading_analyst.infrastructure.fixtures.options_provider import FixtureOptionsProvider
from ai_trading_analyst.infrastructure.fixtures.research_provider import FixtureResearchProvider
from ai_trading_analyst.infrastructure.fixtures.technical_interpreter import (
    FixtureTechnicalInterpreter,
)
from ai_trading_analyst.infrastructure.ibkr import (
    ContractSpec,
    IbAsyncBarSource,
    IbkrConnectionSettings,
    IbkrMarketDataProvider,
    IbkrOptionsProvider,
    OptionChainSource,
)
from ai_trading_analyst.infrastructure.persistence.session import (
    build_engine,
    build_session_factory,
)
from ai_trading_analyst.infrastructure.persistence.stored_bar_source import StoredBarSource
from ai_trading_analyst.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from ai_trading_analyst.infrastructure.publishing import (
    MINDEST_ITERATIONEN,
    Bauziel,
    Exportziel,
    FrontendBauer,
    Hochladeziel,
    SnapshotPublisher,
    WranglerHochlader,
    wrangler_befehl,
)
from ai_trading_analyst.infrastructure.throttle import Drossel
from ai_trading_analyst.infrastructure.watchlists import (
    WatchlistError,
    load_watchlist_directory,
)
from ai_trading_analyst.presentation.api.app import create_app
from ai_trading_analyst.presentation.export import Exportquellen, iter_snapshot


def project_root(config_path: Path) -> Path:
    """Das Verzeichnis ueber ``config/`` -- Bezugspunkt fuer relative Pfade."""
    return config_path.resolve().parent.parent


def build_ibkr_bar_source(
    config: AppConfig,
    on_option_tickers: Callable[[Sequence[Any]], None] | None = None,
) -> IbAsyncBarSource:
    """Die Verbindung zur TWS -- einmal gebaut, von Backfill und Provider genutzt.

    ``on_option_tickers`` sieht die Optionsnotierungen, bevor sie uebersetzt
    werden. Gebraucht vom Mitschnitt (``cli options --record``); sonst
    ``None`` und damit folgenlos.
    """
    ibkr = config.market_data.ibkr
    return IbAsyncBarSource(
        IbkrConnectionSettings(
            host=ibkr.host,
            port=ibkr.port,
            client_id=ibkr.client_id,
            connect_timeout_seconds=float(ibkr.connect_timeout_seconds),
        ),
        native_bar_minutes=ibkr.native_bar_minutes,
        duration=ibkr.history_duration,
        minimum_request_interval_seconds=ibkr.minimum_request_interval_seconds,
        on_option_tickers=on_option_tickers,
    )


def build_bar_source(
    config: AppConfig, uow_factory: Callable[[], UnitOfWork] | None
) -> HistoricalBarSource:
    """Bestand oder Anbieter, je nach ``market_data.source``.

    Ohne ``uow_factory`` bleibt nur der Anbieter: Das ist der Weg fuer einen
    gezielten Einzelabruf ueber die Kommandozeile, der ohne Datenbank
    auskommen soll.
    """
    if config.market_data.source == "stored":
        if uow_factory is None:
            raise ValueError(
                "market_data.source steht auf 'stored', es wurde aber keine Datenbank "
                "uebergeben. Der Bestand braucht eine Verbindung."
            )
        return StoredBarSource(uow_factory)
    return build_ibkr_bar_source(config)


def build_watchlist(config: AppConfig, root: Path) -> Sequence[ContractSpec]:
    return load_watchlist_directory(root / config.market_data.ibkr.watchlist_directory)


def build_session_parameters(config: AppConfig) -> SessionParameters:
    return SessionParameters(
        timezone=config.market.timezone,
        session_open=config.market.session_open_time(),
        session_minutes=config.market.regular_session_minutes,
        timeframe_minutes=config.market.timeframe_minutes,
        early_close=config.market.early_close_time(),
    )


def build_indicator_parameters(indicators: IndicatorConfig) -> IndicatorParameters:
    return IndicatorParameters(
        rsi_length=indicators.rsi_length,
        rsi_method=indicators.rsi_method,
        rsi_ma_length=indicators.rsi_ma_length,
        rsi_ma_type=indicators.rsi_ma_type,
        fast_ema_length=indicators.fast_ema_length,
        slow_ema_length=indicators.slow_ema_length,
    )


def build_chart_market_data(
    config: AppConfig,
    indicators: IndicatorConfig,
    root: Path,
    uow_factory: Callable[[], UnitOfWork],
) -> Callable[[], MarketDataProvider]:
    """Die Kerzenquelle fuer Charts: **immer** der Bestand, nie ein Anbieter.

    Zwei Aufrufer, dieselbe Anforderung -- der Chart-Endpunkt (Stufe J) und
    der Snapshot-Export (Stufe K). Beide zeigen Kerzen an, die schon
    gerechnet wurden; keiner von beiden darf welche beschaffen.

    **``market_data.provider`` wird hier bewusst nicht gelesen.** Der Wert
    steht auf dem Server auf ``fixture``, damit ``git pull`` keinen lokalen
    Diff vorfindet; die produktive Quelle wird je Lauf ueber die
    Kommandozeile geschaltet. Wer ihn hier erbte, baute den Chart aus
    **Fixture-Daten** -- erfundenen Kursen, die neben echten
    Analyseergebnissen stuenden und nicht als erfunden zu erkennen waeren.
    Genau das verbietet Doc 12 ("Keine erfundenen Werte"), und es ist beim
    ersten Export auf dem Server auch tatsaechlich passiert.

    Der ``IbkrMarketDataProvider`` steht hier nur fuer die Kerzenbildung und
    die Indikatoren -- dieselben wie im Screener. Kontaktiert wird die TWS
    nicht: Die Bars kommen aus ``StoredBarSource``, und ein Webdienst, der
    dafuer eine TWS-Client-ID belegte, waere gefaehrlicher als kein Chart
    (ADR 0052).

    **Die Watchlist bleibt Voraussetzung.** Sie liefert die Kontrakte; eine
    Aktie, die nicht darauf steht, bekommt keinen Chart, auch wenn Bars zu
    ihr im Bestand liegen. Fehlt das Verzeichnis ganz, wirft
    ``build_watchlist`` -- siehe die Aufrufer, was sie damit tun.

    Gebaut wird erst beim ersten Aufruf: ``build_watchlist`` liest die
    Watchlist-Dateien und wirft ohne sie. Beim Start gebaut, koennte ein
    fehlendes Verzeichnis den ganzen Dienst am Hochfahren hindern -- den
    Chart zu verlieren ist genug.
    """
    # Direkt gebaut und nicht ueber ``build_market_data_provider``: Der
    # Umweg brauchte eine umgeschriebene Konfiguration, in der ``"ibkr"``
    # dann "nicht Fixture" bedeutete -- ein Zauberwort an einer Stelle, die
    # ein spaeterer zweiter Anbieter stillschweigend uebergehen wuerde.
    @cache
    def chart_market_data() -> MarketDataProvider:
        try:
            watchlist = build_watchlist(config, root)
        except WatchlistError as fehler:
            # Uebersetzt, weil die Praesentationsschicht ``WatchlistError``
            # nicht kennen darf (Doc 10, Paragraph 9) -- und weil die
            # Einordnung stimmt: Eine fehlende Watchlist ist ein
            # Betriebsproblem, keine Auskunft ueber die Datenlage. Der
            # Endpunkt meldet daraufhin 503 statt 500, und der Tageslauf
            # isoliert es ohnehin.
            raise MarketDataUnavailableError(
                f"Die Watchlist ist nicht lesbar, deshalb gibt es keinen Chart: {fehler}"
            ) from fehler
        return IbkrMarketDataProvider(
            bar_source=StoredBarSource(uow_factory),
            watchlist=watchlist,
            session_parameters=build_session_parameters(config),
            indicator_parameters=build_indicator_parameters(indicators),
            native_bar_minutes=config.market_data.ibkr.native_bar_minutes,
        )

    return chart_market_data


def build_market_data_provider(
    config: AppConfig,
    indicators: IndicatorConfig,
    root: Path,
    watchlist: Sequence[ContractSpec] | None = None,
    bar_source: HistoricalBarSource | None = None,
    uow_factory: Callable[[], UnitOfWork] | None = None,
) -> MarketDataProvider:
    """Waehlt den Marktdatenanbieter anhand der Konfiguration.

    ``fixture`` bleibt der Standard und der Weg fuer Tests und fuer einen
    Start ohne laufende TWS; ``ibkr`` ist die produktive Quelle (ADR 0014).

    ``watchlist`` uebersteuert die Dateien -- gedacht fuer einen gezielten
    Einzelabruf ueber die Kommandozeile, nicht fuer den regulaeren Lauf.
    ``bar_source`` ebenso; sonst entscheidet ``market_data.source``.
    """
    if config.market_data.provider == "fixture":
        return FixtureMarketDataProvider()

    return IbkrMarketDataProvider(
        bar_source=bar_source if bar_source is not None else build_bar_source(config, uow_factory),
        watchlist=watchlist if watchlist is not None else build_watchlist(config, root),
        session_parameters=build_session_parameters(config),
        indicator_parameters=build_indicator_parameters(indicators),
        native_bar_minutes=config.market_data.ibkr.native_bar_minutes,
    )


@cache
def _finnhub_drossel(max_requests_per_second: float) -> Drossel:
    """**Eine Drossel je Konto, nicht je Endpunkt** (ADR 0046).

    Finnhubs Grenze gilt fuer den Zugangsschluessel, und der Tageslauf fragt
    je Kandidat den Earnings-Kalender und die Empfehlungen unmittelbar
    nacheinander. Zwei getrennte Drosseln liessen beide ersten Aufrufe sofort
    durch und verdoppelten die Rate -- genau der ``429``, den die Drossel
    verhindern soll.

    ``cache``, weil die beiden ``build_*``-Funktionen unabhaengig
    voneinander aufgerufen werden: einmal aus ``build_app``, einmal aus dem
    CLI. Ein Modul-Singleton waere dasselbe, nur ohne den Schluessel auf die
    Rate.
    """
    return Drossel(max_requests_per_second)


def build_finnhub_earnings_provider(config: AppConfig, secrets: Secrets) -> FinnhubEarningsProvider:
    finnhub = config.finnhub
    return FinnhubEarningsProvider(
        FinnhubConnectionSettings(
            base_url=finnhub.base_url,
            api_key=secrets.require("finnhub_api_key"),
            request_timeout_seconds=float(finnhub.request_timeout_seconds),
            lookahead_calendar_days=config.earnings_filter.lookahead_calendar_days,
            max_requests_per_second=finnhub.max_requests_per_second,
        ),
        drossel=_finnhub_drossel(finnhub.max_requests_per_second),
    )


def build_earnings_provider(config: AppConfig, secrets: Secrets) -> EarningsProvider:
    """Waehlt den Earnings-Anbieter anhand der Konfiguration.

    ``fixture`` bleibt der Standard und der Weg fuer Tests und fuer einen
    Start ohne Finnhub-Zugang; ``finnhub`` ist die produktive Quelle
    (ADR 0017, ADR 0020).
    """
    if config.earnings_filter.provider == "fixture":
        return FixtureEarningsProvider()
    return build_finnhub_earnings_provider(config, secrets)


def build_analyst_recommendations_provider(
    config: AppConfig, secrets: Secrets
) -> AnalystRecommendationsProvider:
    """Waehlt den Anbieter der Analystenempfehlungen (ADR 0043).

    Muster ``build_earnings_provider``: ``fixture`` bleibt der Standard und
    der Weg fuer einen Start ohne Finnhub-Zugang.
    """
    if config.analyst_ratings.provider == "fixture":
        return FixtureAnalystRecommendationsProvider()
    finnhub = config.finnhub
    return FinnhubAnalystRecommendationsProvider(
        FinnhubRecommendationSettings(
            base_url=finnhub.base_url,
            api_key=secrets.require("finnhub_api_key"),
            request_timeout_seconds=float(finnhub.request_timeout_seconds),
            months=config.analyst_ratings.months,
            max_requests_per_second=finnhub.max_requests_per_second,
        ),
        drossel=_finnhub_drossel(finnhub.max_requests_per_second),
    )


def build_earnings_filter_params(config: AppConfig) -> EarningsFilterParameters:
    return EarningsFilterParameters(
        configured_exclusion_candles=config.earnings_filter.configured_exclusion_candles,
        candles_per_day=build_session_parameters(config).candles_per_day,
    )


def build_repeat_suppression_params(config: AppConfig) -> RepeatSuppressionParameters:
    """Die Wiederholsperre des Tageslaufs (ADR 0054)."""
    return RepeatSuppressionParameters(window_days=config.repeat_suppression.window_days)


def app_version() -> str:
    """Die Anwendungsversion aus den Paketmetadaten (Doc 10, Paragraph 8).

    Aus ``pyproject.toml``, nicht aus einer zweiten Konstante im Code -- die
    liefe irgendwann auseinander. Ist das Paket nicht installiert, ist die
    Umgebung nicht die aus Doc 14 (dort steht ``pip install --no-deps -e .``);
    das ist ein Umgebungsfehler und soll auffallen, statt einen leeren
    Versionsstring in jeden Bericht zu schreiben.
    """
    return metadata.version("ai-trading-analyst")


def build_agent_concurrency(config: AppConfig) -> AgentConcurrency:
    """Je Agent ein eigener Pool (ADR 0037, Risiko R9)."""
    return AgentConcurrency(
        research=config.research.max_concurrent_calls,
        technical=config.technical_agent.max_concurrent_calls,
    )


def build_technical_analysis_params(config: AppConfig) -> TechnicalAnalysisParameters:
    """Uebersetzt den Konfigurationsabschnitt in die Domain-Parameter (ADR 0025)."""
    section = config.technical_analysis
    return TechnicalAnalysisParameters(
        pivot_reach=section.pivot_reach,
        zone_tolerance_pct=section.zone_tolerance_pct,
        min_touches=section.min_touches,
        moderate_pivot_count=section.moderate_pivot_count,
        strong_pivot_count=section.strong_pivot_count,
        max_zones_per_side=section.max_zones_per_side,
        history_candles=section.history_candles,
        atr_length=section.atr_length,
        trend_lookback=section.trend_lookback,
        trend_flat_pct=section.trend_flat_pct,
        extremes_lookback=section.extremes_lookback,
    )


def build_fundamental_data_provider(
    config: AppConfig, secrets: Secrets
) -> FundamentalDataProvider:
    """Waehlt den Fundamentaldaten-Anbieter anhand der Konfiguration (ADR 0032).

    Das ``secrets`` ist hier **kein Zugangsdatum**: EDGAR verlangt keinen
    Schluessel. Es traegt allein die Kontaktadresse fuer den ``User-Agent``,
    die aus ``config/default.yaml`` heraus ist, weil das Repository
    oeffentlich ist -- Begruendung am Feld ``Secrets.edgar_contact``.
    """
    section = config.fundamentals
    if section.provider == "fixture":
        return FixtureFundamentalDataProvider()
    if secrets.edgar_contact is None:
        # Eigene Meldung statt ``secrets.require``: Der Grund ist hier
        # ungewoehnlich genug, dass "Secret nicht gesetzt" allein in die Irre
        # fuehrte -- man suchte einen Schluessel, den es nicht gibt.
        raise MissingSecretError(
            "ATA_EDGAR_CONTACT ist nicht gesetzt. Die SEC verlangt im User-Agent "
            "eine Kontaktadresse und antwortet ohne sie mit 403. Sie ist kein "
            "Zugangsdatum, steht aber trotzdem in der Umgebung und nicht in "
            "config/default.yaml: Das Repository ist oeffentlich."
        )
    return EdgarFundamentalDataProvider(
        EdgarConnectionSettings(
            base_url=section.edgar.base_url,
            index_base_url=section.edgar.index_base_url,
            contact=secrets.edgar_contact.get_secret_value(),
            request_timeout_seconds=section.edgar.request_timeout_seconds,
            max_requests_per_second=section.edgar.max_requests_per_second,
        ),
        parameters=FundamentalParameters(growth_years=section.growth_years),
    )


def build_options_params(config: AppConfig) -> OptionsParameters:
    """Aus ``OptionsConfig`` die Auswahlparameter der Domain (ADR 0048)."""
    section = config.options
    return OptionsParameters(
        min_days_to_expiration=section.min_days_to_expiration,
        max_days_to_expiration=section.max_days_to_expiration,
        target_days_to_expiration=section.target_days_to_expiration,
        min_delta=section.min_delta,
        max_delta=section.max_delta,
        min_moneyness=section.min_moneyness,
        max_moneyness=section.max_moneyness,
        max_strikes=section.max_strikes,
        max_suggestions=section.max_suggestions,
        max_relative_spread=section.max_relative_spread,
        min_open_interest=section.min_open_interest,
        min_volume=section.min_volume,
        hedge_width_pct=section.hedge_width_pct,
    )


def build_options_backtest_params(
    config: AppConfig,
    *,
    volatility_uplift: float,
    risk_free_rate: float,
    execution_haircut: float,
) -> OptionsBacktestParameters:
    """Aus ``OptionsConfig`` die Annahmen des historischen Laufs (ADR 0058).

    **Laufzeitfenster und Ziel-Delta kommen aus derselben Konfiguration wie
    der Live-Betrieb** -- sonst maesse der Rueckblick still eine andere
    Strategie als die gehandelte, sobald jemand die Konfiguration aendert.
    Genau das will Festlegung 5 verhindern. Heute stimmen die Vorgaben
    ueberein; das ist ein Zufall, auf den sich nichts stuetzen soll.

    Das Ziel-Delta ist die **Mitte** des produktiven Bandes: Live entscheidet
    das Band, welche Kontrakte durchgehen; historisch muss ein einzelner
    Strike gewaehlt werden, und die Mitte ist die sparsamste Uebersetzung.

    Volatilitaetsaufschlag, Zinssatz und Ausfuehrungsabschlag stehen dagegen
    **nicht** in der Konfiguration: Sie gehoeren zum Messlauf und nicht zum
    Tageslauf, und der Aufschlag ist ausdruecklich zum Variieren gedacht
    (Festlegung 2) -- das Ergebnis gehoert als Band gelesen.
    """
    section = config.options
    return OptionsBacktestParameters(
        min_days_to_expiration=section.min_days_to_expiration,
        max_days_to_expiration=section.max_days_to_expiration,
        target_days_to_expiration=section.target_days_to_expiration,
        target_delta=(section.min_delta + section.max_delta) / 2.0,
        volatility_uplift=volatility_uplift,
        risk_free_rate=risk_free_rate,
        execution_haircut=execution_haircut,
    )


def build_options_provider(
    config: AppConfig, root: Path, bar_source: OptionChainSource | None = None
) -> OptionsDataProvider:
    """Waehlt den Optionsdaten-Anbieter anhand der Konfiguration (ADR 0048).

    ``bar_source`` ist die **bereits bestehende** TWS-Anbindung. Sie wird
    hereingereicht und nicht hier gebaut: IBKR laesst je Client-ID genau eine
    Verbindung zu, und eine zweite verdraengte die erste mitten im Lauf. Ohne
    sie bleibt nur der Fixture-Anbieter -- der Weg fuer einen Lauf ohne TWS.
    """
    parameters = build_options_params(config)
    if config.options.provider == "fixture":
        return FixtureOptionsProvider(parameters)
    if bar_source is None:
        raise ValueError(
            "options.provider steht auf 'ibkr', es wurde aber keine TWS-Anbindung "
            "uebergeben. Die Optionskette laeuft ueber dieselbe Verbindung wie die "
            "Kerzen -- IBKR laesst je Client-ID nur eine zu."
        )
    return IbkrOptionsProvider(
        bar_source,
        watchlist=build_watchlist(config, root),
        parameters=parameters,
        market_data_type=config.options.market_data_type,
    )


def build_research_provider(config: AppConfig, secrets: Secrets) -> ResearchProvider:
    """Waehlt den Research-Anbieter anhand der Konfiguration.

    ``fixture`` bleibt der Standard und der Weg fuer Tests und fuer einen
    Start ohne Anthropic-Zugang; ``anthropic`` ist die produktive Quelle
    (ADR 0021, ADR 0023); ``none`` schaltet den Agenten bewusst ab.

    Der ``none``-Zweig steht **vor** dem Zugriff auf ``llm_api_key``: Ein
    abgeschalteter Agent darf keinen Schluessel verlangen -- das ist sein
    Zweck.
    """
    if config.research.provider == "fixture":
        return FixtureResearchProvider()
    if config.research.provider == "none":
        return DisabledResearchProvider()
    return AnthropicResearchProvider(
        AnthropicResearchSettings(
            api_key=secrets.require("llm_api_key"),
            model=config.llm.research.model,
            fallback_model=config.llm.research.fallback_model,
            max_searches=config.research.max_searches,
            max_fetches=config.research.max_fetches,
            max_fetch_content_tokens=config.research.max_fetch_content_tokens,
            max_input_tokens_per_symbol=config.research.max_input_tokens_per_symbol,
            max_output_tokens=config.research.max_output_tokens,
            request_timeout_seconds=config.research.request_timeout_seconds,
            max_retries=config.research.max_retries,
            fetch_allowed_domains=config.research.fetch_allowed_domains,
            max_citations=config.research.max_citations,
            pricing=AnthropicResearchPricing(
                input_usd_per_million=config.research.pricing.input_usd_per_million,
                output_usd_per_million=config.research.pricing.output_usd_per_million,
                usd_per_search=config.research.pricing.usd_per_search,
            ),
        )
    )


def build_technical_interpreter(config: AppConfig, secrets: Secrets) -> TechnicalInterpreter:
    """Waehlt den Anbieter des Technical Agent (ADR 0026).

    Muster ``build_research_provider``: ``fixture`` ist der Standard und der
    Weg fuer Tests und einen Start ohne Anthropic-Zugang, ``none`` schaltet
    den Agenten bewusst ab (Zweig vor dem Schluesselzugriff). Das
    Modellprofil kommt aus ``llm.technical`` und ist bereits vorbelegt.
    """
    if config.technical_agent.provider == "fixture":
        return FixtureTechnicalInterpreter()
    if config.technical_agent.provider == "none":
        return DisabledTechnicalInterpreter()
    return AnthropicTechnicalInterpreter(
        AnthropicTechnicalSettings(
            api_key=secrets.require("llm_api_key"),
            model=config.llm.technical.model,
            fallback_model=config.llm.technical.fallback_model,
            max_output_tokens=config.technical_agent.max_output_tokens,
            request_timeout_seconds=config.technical_agent.request_timeout_seconds,
            max_retries=config.technical_agent.max_retries,
            pricing=AnthropicTechnicalPricing(
                input_usd_per_million=config.technical_agent.pricing.input_usd_per_million,
                output_usd_per_million=config.technical_agent.pricing.output_usd_per_million,
            ),
        )
    )


def build_scoring_params(config: AppConfig) -> ScoringParameters:
    """Aus ``ScoringConfig`` die Parameter der beiden Scores (ADR 0041, 0045).

    **Hier und nicht in der Konfiguration** wird geprueft, dass die Schwellen
    zu den Kennzahlen passen: ``config`` kennt die Domain nicht, und die
    Domain kennt keine Konfigurationsdatei. Diese Funktion kennt beide Seiten
    und ist damit die einzige Stelle, an der ein Tippfehler im
    Kennzahlennamen auffallen kann -- beim Start und nicht als
    stillschweigend uebersprungene Kennzahl in einem Ergebnis.
    """
    schwellen: dict[MetricName, MetricThresholds] = {}
    for name, eintrag in config.scoring.thresholds.items():
        try:
            kennzahl = MetricName(name)
        except ValueError as error:
            raise ValueError(
                f"scoring.thresholds: '{name}' ist keine bekannte Kennzahl"
            ) from error
        schwellen[kennzahl] = MetricThresholds(
            boundaries=eintrag.boundaries, higher_is_better=eintrag.higher_is_better
        )

    fehlend = sorted(name.value for name in SCORED_METRICS - schwellen.keys())
    if fehlend:
        raise ValueError(
            "scoring.thresholds: ohne Schwellen keine Teilwerte -- es fehlen "
            + ", ".join(fehlend)
        )

    _pruefe_signalabbildung(config)

    empfehlung = config.scoring.recommendation
    return ScoringParameters(
        recommendation=RecommendationParameters(
            strong_candidate=empfehlung.strong_candidate,
            candidate=empfehlung.candidate,
            watch=empfehlung.watch,
            investment_strong=empfehlung.investment_strong,
            investment_weak=empfehlung.investment_weak,
            cap_false_signal_high=Recommendation(empfehlung.cap_false_signal_high),
            cap_earnings_unknown=Recommendation(empfehlung.cap_earnings_unknown),
            version=empfehlung.version,
        ),
        swing_weights=_gewichte(config.scoring.swing_weights),
        long_term_weights=_gewichte(config.scoring.long_term_weights),
        thresholds=schwellen,
        analyst_max_age_days=config.scoring.analyst_max_age_days,
        analyst_buy_share=MetricThresholds(
            boundaries=config.scoring.analyst_buy_share.boundaries,
            higher_is_better=config.scoring.analyst_buy_share.higher_is_better,
        ),
        options_annualized_return=(
            None
            if config.scoring.options_annualized_return is None
            else MetricThresholds(
                boundaries=config.scoring.options_annualized_return.boundaries,
                higher_is_better=config.scoring.options_annualized_return.higher_is_better,
            )
        ),
        minimum_coverage=config.scoring.minimum_coverage,
        normal_confidence_coverage=config.scoring.normal_confidence_coverage,
        swing_version=config.scoring.swing_version,
        long_term_version=config.scoring.long_term_version,
    )


def _pruefe_signalabbildung(config: AppConfig) -> None:
    """Fuer jede moegliche Signalzahl eines Kandidaten gibt es einen Teilwert.

    ``SIGNAL_TEILWERTE`` kennt heute fuenf, vier und drei Signale -- weil ein
    Kandidat mindestens zwei Kaufsignale und ein Zusatzkriterium traegt. Die
    Zahl der geforderten Kaufsignale ist aber konfigurierbar: Auf eins
    gesetzt, verloere jeder Kandidat mit nur zwei erfuellten Kriterien still
    eine Komponente mit einem Viertel des Gewichts. Wie bei den Schwellen
    faellt das nur hier auf, wo Konfiguration und Domain zugleich sichtbar
    sind.
    """
    # Mindestens ein Zusatzkriterium kommt zu den Kaufsignalen hinzu -- das
    # ist die Kandidatenregel, nicht eine Annahme ueber die Daten.
    kleinste_kandidatengroesse = config.screening.required_crossing_signals + 1
    moeglich = range(kleinste_kandidatengroesse, len(SignalType) + 1)
    ohne_abbildung = sorted(set(moeglich) - SIGNAL_TEILWERTE.keys())
    if ohne_abbildung:
        raise ValueError(
            "screening.required_crossing_signals laesst Kandidaten mit "
            f"{ohne_abbildung} erfuellten Kriterien zu, fuer die es keinen "
            "Teilwert gibt (ADR 0056)"
        )


def _gewichte(section: BaseModel) -> dict[ComponentName, float]:
    """Die Feldnamen des Abschnitts sind die Komponentennamen in klein.

    Keine zweite Liste, die mit der ersten synchron bleiben muesste: Ein Feld
    ohne passenden ``ComponentName`` bricht beim Start mit einem
    ``KeyError``, statt eine Komponente ohne Gewicht zu hinterlassen.
    """
    return {
        ComponentName[name.upper()]: float(wert) for name, wert in section.model_dump().items()
    }


def build_backtest_params(config: AppConfig) -> BacktestParameters:
    return BacktestParameters(
        horizons=config.backtesting.horizons,
        minimum_sample_size=config.backtesting.minimum_sample_size,
        normal_confidence_sample_size=config.backtesting.normal_confidence_sample_size,
        history_years=config.backtesting.history_years,
    )


def build_candidate_rule_params(
    indicators: IndicatorConfig, config: AppConfig
) -> CandidateRuleParameters:
    """Die Kandidatenregel, wie der Lauf sie sieht.

    Zweimal gebraucht -- vom Webdienst fuer den Validierungschart und vom
    Exportschritt fuer denselben Chart als Datei. Zweimal aufgeschrieben
    liefen sie irgendwann auseinander.
    """
    return CandidateRuleParameters(
        required_crossing_signals=config.screening.required_crossing_signals,
        signal_lookback_previous_candles=config.screening.signal_lookback_previous_candles,
        warmup_candles=indicators.warmup_candles,
    )


def build_dashboard_publisher(
    config: AppConfig,
    secrets: Secrets,
    root: Path,
    *,
    uow_factory: Callable[[], UnitOfWork],
) -> SnapshotPublisher | None:
    """Der Exportschritt -- oder ``None``, wenn er abgeschaltet ist (ADR 0060).

    Ausgeliefert ist er abgeschaltet. Eingeschaltet wird er ueber die
    Konfiguration der Aufgabenplanung, wie die Anbieter auch.

    **Der Chart kommt aus dem Bestand, nie von der TWS.** Der Export laeuft am
    Ende des Tageslaufs, und der haelt zu diesem Zeitpunkt die Client-ID; ein
    zweiter Zugriff darauf wuerde die Verbindung verdraengen. Dieselbe
    Festlegung wie im Webdienst (ADR 0052), hier aus einem zweiten Grund.

    Raises:
        ValueError: wenn ein Ziel eingestellt ist, aber kein Verzeichnis.
        MissingSecretError: wenn verschluesselt werden soll und die
            Passphrase fehlt. **Kein Rueckfall auf Klartext:** Ein Tippfehler
            im Namen der Umgebungsvariablen wuerde sonst stillschweigend
            Berichte und Kurse offen beim Anbieter ablegen.
    """
    einstellungen = config.dashboard_export
    if einstellungen.target == "none":
        return None
    if not einstellungen.directory:
        raise ValueError(
            "dashboard_export.target ist gesetzt, aber dashboard_export.directory fehlt."
        )

    verzeichnis = (root / einstellungen.directory).resolve()
    zustandsdatei = (
        (root / einstellungen.state_file).resolve()
        if einstellungen.state_file
        else verzeichnis.with_name(verzeichnis.name + ".zustand.json")
    )
    if zustandsdatei.is_relative_to(verzeichnis):
        # Die Zustandsdatei traegt die Zuordnung von Pfad zu opakem Namen --
        # genau das Geheimnis, das die Verschluesselung der Dateinamen
        # schuetzt. Laege sie im veroeffentlichten Verzeichnis, ginge sie beim
        # naechsten Upload mit hinaus, und die Opazitaet waere vollstaendig
        # hin. Das ist kein Hinweis wert, sondern ein Abbruch.
        raise ValueError(
            f"dashboard_export.state_file ({zustandsdatei}) liegt im "
            f"veroeffentlichten Verzeichnis ({verzeichnis}). Sie enthaelt die "
            "Zuordnung von Pfad zu Dateiname und darf den Server nicht verlassen."
        )
    if einstellungen.encrypt and einstellungen.pbkdf2_iterations < MINDEST_ITERATIONEN:
        # Hier und nicht erst in der Ableitung: Der Tageslauf baut diesen
        # Schritt vor dem halbstuendigen Backfill, damit eine
        # Fehlkonfiguration auffaellt, bevor gerechnet wird -- und nicht erst
        # am Ende, wenn der Lauf fertig ist.
        raise ValueError(
            f"dashboard_export.pbkdf2_iterations ist {einstellungen.pbkdf2_iterations}; "
            f"verlangt sind mindestens {MINDEST_ITERATIONEN} (ADR 0060, Punkt 6)."
        )
    passphrase = (
        secrets.require("dashboard_export_passphrase") if einstellungen.encrypt else None
    )

    indicators = config.require_indicators()
    quellen = Exportquellen(
        uow_factory=uow_factory,
        backtest_parameters=build_backtest_params(config),
        candidate_rule_parameters=build_candidate_rule_params(indicators, config),
        chart_market_data=build_chart_market_data(config, indicators, root, uow_factory),
        repeat_suppression=build_repeat_suppression_params(config),
        market_timezone=config.market.timezone,
    )

    def dateien() -> Iterator[tuple[str, bytes]]:
        """Die Naht zwischen den Schichten.

        Die Infrastruktur darf die Praesentationsschicht nicht kennen
        (Doc 10, Paragraph 9). Sie bekommt deshalb Pfad und Bytes, und wo
        die herkommen, weiss allein dieser Composition Root.
        """
        for datei in iter_snapshot(quellen):
            yield datei.pfad, datei.inhalt

    return SnapshotPublisher(
        snapshot=dateien,
        ziel=Exportziel(
            wurzel=verzeichnis,
            zustandsdatei=zustandsdatei,
            passphrase=passphrase,
            iterationen=einstellungen.pbkdf2_iterations,
        ),
        hochlader=(
            _build_hochlader(einstellungen, secrets, root, verzeichnis)
            if einstellungen.target == "cloudflare"
            else None
        ),
    )


def build_dashboard_url(config: AppConfig, secrets: Secrets) -> str | None:
    """Die Adresse des Dashboards fuer die Ergebnismeldung (ADR 0065).

    Nur wenn der Export zum Anbieter geht **und** verschluesselt ist -- so
    lautet E5 aus ADR 0060: der Link erst nach Stufe 2. Ohne ``ATA_DASHBOARD_URL``
    gibt es keinen Link und keinen Fehler; mit einer Adresse, die nicht zum
    Anbieter oder nicht zum Worker passt, bricht der Start ab: Ein falscher
    Link in jeder Meldung waere schlimmer als keiner.

    Raises:
        ValueError: bei einer Adresse in fremder Form.
        MissingSecretError: wenn der Worker-Name fehlt, gegen den geprueft wird.
    """
    einstellungen = config.dashboard_export
    if einstellungen.target != "cloudflare" or not einstellungen.encrypt:
        return None
    roh = secrets.dashboard_url
    if roh is None:
        return None
    form = "ATA_DASHBOARD_URL muss die Form https://<worker>.<subdomain>.workers.dev/ haben."
    teile = urlsplit(roh.get_secret_value().strip())
    host = teile.hostname
    if (
        teile.scheme != "https"
        or host is None
        or teile.username is not None
        or teile.port is not None
        or teile.query
        or teile.fragment
        or teile.path not in ("", "/")
    ):
        raise ValueError(form)
    glieder = host.split(".")
    if len(glieder) != 4 or glieder[-2:] != ["workers", "dev"]:
        raise ValueError(form)
    worker = secrets.require("dashboard_publish_worker").strip()
    if glieder[0] != worker:
        raise ValueError(
            "ATA_DASHBOARD_URL nennt einen anderen Worker als ATA_DASHBOARD_PUBLISH_WORKER."
        )
    return f"https://{host}/"


def build_frontend_bauer(config: AppConfig, root: Path) -> FrontendBauer:
    """Der Bau der Oberflaeche fuer ``publish --full`` (ADR 0065).

    Raises:
        ValueError: wenn kein veroeffentlichtes Verzeichnis eingestellt ist
            oder es das Projekt selbst umfasst -- der Bau leert es.
    """
    einstellungen = config.dashboard_export
    if not einstellungen.directory:
        raise ValueError("dashboard_export.directory fehlt -- ohne Ziel gibt es nichts zu bauen.")
    frontend = (root / "frontend").resolve()
    verzeichnis = (root / einstellungen.directory).resolve()
    if root.resolve().is_relative_to(verzeichnis) or frontend.is_relative_to(verzeichnis):
        # Der Bau leert das Verzeichnis bis auf ``data/``. Zeigte es auf das
        # Projekt oder das Frontend, waere das ein Loeschen des Quellcodes.
        raise ValueError(
            f"dashboard_export.directory ({verzeichnis}) umfasst das Projekt -- der Bau der "
            "Oberflaeche leert das Verzeichnis und darf dort nicht arbeiten."
        )
    return FrontendBauer(
        Bauziel(
            frontend=frontend,
            verzeichnis=verzeichnis,
            zeitgrenze=einstellungen.build_timeout_seconds,
            datenmodus="verschluesselt" if einstellungen.encrypt else "statisch",
        )
    )


def _build_hochlader(
    einstellungen: DashboardExportConfig,
    secrets: Secrets,
    root: Path,
    verzeichnis: Path,
) -> WranglerHochlader:
    """Der Weg nach draussen (ADR 0060, E4).

    Raises:
        ValueError: wenn das Upload-Werkzeug fehlt oder die erzeugte
            Konfigurationsdatei im veroeffentlichten Verzeichnis laege.
        MissingSecretError: wenn Token, Konto oder Worker-Name fehlen.
    """
    arbeitsverzeichnis = (
        (root / einstellungen.upload_directory).resolve()
        if einstellungen.upload_directory
        else verzeichnis.with_name(verzeichnis.name + ".upload")
    )
    if arbeitsverzeichnis.is_relative_to(verzeichnis):
        # Dieselbe Begruendung wie bei der Zustandsdatei: Die erzeugte
        # Konfiguration nennt den Worker beim Namen, und der Name ist die
        # halbe Adresse des Dashboards (ADR 0060, E6). Was im Verzeichnis
        # liegt, geht mit hinauf.
        raise ValueError(
            f"dashboard_export.upload_directory ({arbeitsverzeichnis}) liegt im "
            f"veroeffentlichten Verzeichnis ({verzeichnis}). Die erzeugte "
            "Konfiguration nennt den Worker und darf den Server nicht verlassen."
        )

    if arbeitsverzeichnis.anchor != verzeichnis.anchor:
        # Das Werkzeug loest den Zielpfad relativ zu seiner
        # Konfigurationsdatei auf. Ueber Laufwerksgrenzen gibt es keinen
        # relativen Pfad, und ``os.path.relpath`` bricht dort ab -- mitten
        # im Upload und mit einer Meldung, die nichts erklaert.
        raise ValueError(
            f"dashboard_export.upload_directory ({arbeitsverzeichnis}) liegt auf einem "
            f"anderen Laufwerk als das veroeffentlichte Verzeichnis ({verzeichnis}). "
            "Beide muessen auf demselben liegen."
        )

    # ``strip`` an allen dreien: Diese Werte werden aus einer Konsole in eine
    # Datei kopiert, und ein mitgenommenes Leerzeichen ist dort unsichtbar.
    # Beim Token faellt es als Absage des Anbieters auf, beim Worker-Namen als
    # ungueltiger Name -- beides Meldungen, die auf nichts hinweisen.
    return WranglerHochlader(
        Hochladeziel(
            worker=secrets.require("dashboard_publish_worker").strip(),
            konto=secrets.require("dashboard_publish_account").strip(),
            token=secrets.require("dashboard_publish_token").strip(),
            baum=verzeichnis,
            arbeitsverzeichnis=arbeitsverzeichnis,
            # Erst beim Upload aufgeloest: Ein fehlendes Werkzeug soll den
            # Upload kosten und nicht den ganzen Lauf -- dieser Bau laeuft
            # vor dem Backfill, und ein Fehler hier bricht mit 2 ab.
            befehl=partial(wrangler_befehl, root / "frontend" / "node_modules" / "wrangler"),
            zeitgrenze=einstellungen.upload_timeout_seconds,
        )
    )




def build_app() -> FastAPI:
    """Die Web-Anwendung: Datenbank, sonst nichts.

    Sie baut **keinen einzigen Anbieter** -- die API ist lesend (ADR 0053).
    Das ist kein Sparen, sondern eine Zusage: Ein dauerhaft laufender
    Webdienst, der die TWS-Client-ID belegte oder auf Zuruf einen Lauf mit
    Fixture-Daten in die Produktivdatenbank schriebe, waere gefaehrlicher als
    kein Dashboard.

    **Eine Ausnahme, und sie ist eng gefasst:** Der Validierungschart braucht
    Kerzen. Dafuer entsteht **ein** Marktdatenanbieter, dessen Quelle fest auf
    ``stored`` steht -- er liest die Datenbank und kann die TWS nicht
    erreichen. Er wird **beim ersten Aufruf** gebaut und nicht beim Start:
    Ueber ``build_watchlist`` haengt er an der Watchlist-Datei, und ein
    fehlendes Verzeichnis soll den Chart kosten, nicht den ganzen Dienst.
    """
    loaded = load_config()
    secrets = load_secrets()
    # Auch ohne Anbieter: Fehlt der Indikatorblock, ist die Konfiguration
    # unvollstaendig, und das soll beim Start auffallen und nicht erst beim
    # naechsten Lauf (``GateNotClearedError``).
    loaded.config.require_indicators()

    engine = build_engine(secrets.require("database_url"))
    session_factory = build_session_factory(engine)

    def uow_factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    def check_database_ready() -> bool:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            return False
        return True

    # Der Export liegt neben ``config/`` im Projekt und wandert mit ihm; ein
    # eigener Konfigurationswert waere eine Einstellung, die nie jemand
    # anders setzt (ADR 0052).
    app = create_app(project_root(loaded.source_path) / "frontend" / "out")
    app.state.uow_factory = uow_factory
    app.state.run_overview_use_case = ReadRunOverviewUseCase(
        uow_factory,
        repeat_suppression=build_repeat_suppression_params(loaded.config),
        market_timezone=loaded.config.market.timezone,
    )
    app.state.check_database_ready = check_database_ready
    # Die Schwellen der Stichprobengroesse und die Kandidatenregel kommen aus
    # derselben Konfiguration wie im Lauf. Eine Oberflaeche, die anders
    # einstuft als der Lauf, der die Zahlen erzeugt hat, waere schlimmer als
    # gar keine.
    indicators = loaded.config.require_indicators()
    app.state.backtest_parameters = build_backtest_params(loaded.config)
    app.state.candidate_rule_parameters = build_candidate_rule_params(
        indicators, loaded.config
    )
    app.state.chart_market_data = build_chart_market_data(
        loaded.config, indicators, project_root(loaded.source_path), uow_factory
    )
    return app


