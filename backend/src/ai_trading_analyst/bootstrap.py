"""Composition Root.

Verdrahtet konkrete Infrastruktur (Fixture-Provider, SQLAlchemy) mit
Application und Presentation. Liegt bewusst ausserhalb der vier Schichten
(``domain``, ``application``, ``infrastructure``, ``presentation``) --
``tests/architecture/test_layer_boundaries.py`` prueft nur Importe innerhalb
dieser vier Pakete. Nur an dieser einen Stelle duerfen alle Schichten
gleichzeitig referenziert werden (Doc 10, Paragraph 9).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from functools import cache
from importlib import metadata
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import text

from ai_trading_analyst.application.run_analysis import AgentConcurrency, RunAnalysisUseCase
from ai_trading_analyst.config.loader import load_config, load_secrets
from ai_trading_analyst.config.settings import (
    AppConfig,
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
    OptionsDataProvider,
    ResearchProvider,
    TechnicalInterpreter,
    UnitOfWork,
)
from ai_trading_analyst.domain.backtesting import BacktestParameters
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
from ai_trading_analyst.infrastructure.throttle import Drossel
from ai_trading_analyst.infrastructure.watchlists import load_watchlist_directory
from ai_trading_analyst.presentation.api.app import create_app


def project_root(config_path: Path) -> Path:
    """Das Verzeichnis ueber ``config/`` -- Bezugspunkt fuer relative Pfade."""
    return config_path.resolve().parent.parent


def build_ibkr_bar_source(config: AppConfig) -> IbAsyncBarSource:
    """Die Verbindung zur TWS -- einmal gebaut, von Backfill und Provider genutzt."""
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
    (ADR 0021, ADR 0023).
    """
    if config.research.provider == "fixture":
        return FixtureResearchProvider()
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
    Weg fuer Tests und einen Start ohne Anthropic-Zugang. Das Modellprofil
    kommt aus ``llm.technical`` und ist bereits vorbelegt.
    """
    if config.technical_agent.provider == "fixture":
        return FixtureTechnicalInterpreter()
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

    ``SIGNAL_TEILWERTE`` kennt heute drei und zwei Signale -- weil
    ``screening.required_signal_count`` auf zwei steht. Die Zahl ist aber
    konfigurierbar: Auf eins gesetzt, verloere jeder Ein-Signal-Kandidat
    still eine Komponente mit einem Viertel des Gewichts. Wie bei den
    Schwellen faellt das nur hier auf, wo Konfiguration und Domain zugleich
    sichtbar sind.
    """
    moeglich = range(config.screening.required_signal_count, len(SignalType) + 1)
    ohne_abbildung = sorted(set(moeglich) - SIGNAL_TEILWERTE.keys())
    if ohne_abbildung:
        raise ValueError(
            "screening.required_signal_count laesst Kandidaten mit "
            f"{ohne_abbildung} Signalen zu, fuer die es keinen Teilwert gibt "
            "(ADR 0045, Abschnitt 4)"
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
        cooldown_candles=config.backtesting.cooldown_candles,
        minimum_sample_size=config.backtesting.minimum_sample_size,
        normal_confidence_sample_size=config.backtesting.normal_confidence_sample_size,
        history_years=config.backtesting.history_years,
    )


def build_app() -> FastAPI:
    loaded = load_config()
    secrets = load_secrets()
    indicators = loaded.config.require_indicators()

    engine = build_engine(secrets.require("database_url"))
    session_factory = build_session_factory(engine)

    def uow_factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    candidate_rule_params = CandidateRuleParameters(
        required_signal_count=loaded.config.screening.required_signal_count,
        signal_lookback_previous_candles=loaded.config.screening.signal_lookback_previous_candles,
        warmup_candles=indicators.warmup_candles,
    )
    # Einmal gebaut und an beide gereicht: IBKR laesst je Client-ID genau
    # eine Verbindung zu. Der Aufbau selbst kostet nichts -- ``IbAsyncBarSource``
    # verbindet erst beim ersten Abruf.
    ibkr_quelle = (
        build_ibkr_bar_source(loaded.config)
        if "ibkr" in (loaded.config.market_data.provider, loaded.config.options.provider)
        else None
    )
    market_data_provider = build_market_data_provider(
        loaded.config,
        indicators,
        project_root(loaded.source_path),
        bar_source=(
            ibkr_quelle if loaded.config.market_data.source == "live" else None
        ),
        uow_factory=uow_factory,
    )
    earnings_provider = build_earnings_provider(loaded.config, secrets)
    earnings_filter_params = build_earnings_filter_params(loaded.config)
    research_provider = build_research_provider(loaded.config, secrets)
    technical_interpreter = build_technical_interpreter(loaded.config, secrets)
    use_case = RunAnalysisUseCase(
        market_data_provider,
        earnings_provider,
        research_provider,
        technical_interpreter,
        build_fundamental_data_provider(loaded.config, secrets),
        build_analyst_recommendations_provider(loaded.config, secrets),
        build_options_provider(loaded.config, project_root(loaded.source_path), ibkr_quelle),
        uow_factory,
        candidate_rule_params,
        earnings_filter_params,
        build_technical_analysis_params(loaded.config),
        build_backtest_params(loaded.config),
        build_scoring_params(loaded.config),
        agent_concurrency=build_agent_concurrency(loaded.config),
        app_version=app_version(),
        market_timezone=loaded.config.market.timezone,
    )

    def check_database_ready() -> bool:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            return False
        return True

    app = create_app()
    app.state.run_analysis_use_case = use_case
    app.state.uow_factory = uow_factory
    app.state.check_database_ready = check_database_ready

    if isinstance(market_data_provider, IbkrMarketDataProvider):
        # Die TWS laesst je Client-ID nur eine Verbindung zu. Wird sie beim
        # Herunterfahren nicht getrennt, blockiert sie den naechsten Start bis
        # zum Timeout der Gegenstelle.
        app.router.on_shutdown.append(bar_source_closer(market_data_provider))
    return app


def bar_source_closer(provider: IbkrMarketDataProvider) -> Callable[[], None]:
    def close_bar_source() -> None:
        provider.close()

    return close_bar_source
