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
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import text

from ai_trading_analyst.application.run_analysis import RunAnalysisUseCase
from ai_trading_analyst.config.loader import load_config, load_secrets
from ai_trading_analyst.config.settings import AppConfig, IndicatorConfig, Secrets
from ai_trading_analyst.domain.analysis import (
    EarningsProvider,
    HistoricalBarSource,
    MarketDataProvider,
    ResearchProvider,
    UnitOfWork,
)
from ai_trading_analyst.domain.backtesting import BacktestParameters
from ai_trading_analyst.domain.earnings import EarningsFilterParameters
from ai_trading_analyst.domain.screening import (
    CandidateRuleParameters,
    IndicatorParameters,
    SessionParameters,
)
from ai_trading_analyst.infrastructure.anthropic import (
    AnthropicResearchPricing,
    AnthropicResearchProvider,
    AnthropicResearchSettings,
)
from ai_trading_analyst.infrastructure.finnhub import (
    FinnhubConnectionSettings,
    FinnhubEarningsProvider,
)
from ai_trading_analyst.infrastructure.fixtures.earnings_provider import FixtureEarningsProvider
from ai_trading_analyst.infrastructure.fixtures.market_data_provider import (
    FixtureMarketDataProvider,
)
from ai_trading_analyst.infrastructure.fixtures.research_provider import FixtureResearchProvider
from ai_trading_analyst.infrastructure.ibkr import (
    ContractSpec,
    IbAsyncBarSource,
    IbkrConnectionSettings,
    IbkrMarketDataProvider,
)
from ai_trading_analyst.infrastructure.persistence.session import (
    build_engine,
    build_session_factory,
)
from ai_trading_analyst.infrastructure.persistence.stored_bar_source import StoredBarSource
from ai_trading_analyst.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
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


def build_finnhub_earnings_provider(config: AppConfig, secrets: Secrets) -> FinnhubEarningsProvider:
    finnhub = config.earnings_filter.finnhub
    return FinnhubEarningsProvider(
        FinnhubConnectionSettings(
            base_url=finnhub.base_url,
            api_key=secrets.require("finnhub_api_key"),
            request_timeout_seconds=float(finnhub.request_timeout_seconds),
            lookahead_calendar_days=finnhub.lookahead_calendar_days,
        )
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


def build_earnings_filter_params(config: AppConfig) -> EarningsFilterParameters:
    return EarningsFilterParameters(
        configured_exclusion_candles=config.earnings_filter.configured_exclusion_candles,
        candles_per_day=build_session_parameters(config).candles_per_day,
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
            fetch_allowed_domains=config.research.fetch_allowed_domains,
            pricing=AnthropicResearchPricing(
                input_usd_per_million=config.research.pricing.input_usd_per_million,
                output_usd_per_million=config.research.pricing.output_usd_per_million,
                usd_per_search=config.research.pricing.usd_per_search,
            ),
        )
    )


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
    market_data_provider = build_market_data_provider(
        loaded.config, indicators, project_root(loaded.source_path), uow_factory=uow_factory
    )
    earnings_provider = build_earnings_provider(loaded.config, secrets)
    earnings_filter_params = build_earnings_filter_params(loaded.config)
    research_provider = build_research_provider(loaded.config, secrets)
    use_case = RunAnalysisUseCase(
        market_data_provider,
        earnings_provider,
        research_provider,
        uow_factory,
        candidate_rule_params,
        earnings_filter_params,
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
