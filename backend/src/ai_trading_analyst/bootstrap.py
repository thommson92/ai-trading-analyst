"""Composition Root.

Verdrahtet konkrete Infrastruktur (Fixture-Provider, SQLAlchemy) mit
Application und Presentation. Liegt bewusst ausserhalb der vier Schichten
(``domain``, ``application``, ``infrastructure``, ``presentation``) --
``tests/architecture/test_layer_boundaries.py`` prueft nur Importe innerhalb
dieser vier Pakete. Nur an dieser einen Stelle duerfen alle Schichten
gleichzeitig referenziert werden (Doc 10, Paragraph 9).
"""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy import text

from ai_trading_analyst.application.run_analysis import RunAnalysisUseCase
from ai_trading_analyst.config.loader import load_config, load_secrets
from ai_trading_analyst.domain.analysis import UnitOfWork
from ai_trading_analyst.domain.screening import CandidateRuleParameters
from ai_trading_analyst.infrastructure.fixtures.market_data_provider import (
    FixtureMarketDataProvider,
)
from ai_trading_analyst.infrastructure.persistence.session import (
    build_engine,
    build_session_factory,
)
from ai_trading_analyst.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from ai_trading_analyst.presentation.api.app import create_app


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
    use_case = RunAnalysisUseCase(FixtureMarketDataProvider(), uow_factory, candidate_rule_params)

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
    return app
