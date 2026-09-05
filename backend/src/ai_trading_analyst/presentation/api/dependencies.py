"""FastAPI-Dependencies. Lesen fertig verdrahtete Objekte aus ``app.state``,
statt selbst konkrete Infrastruktur zu konstruieren -- das Verdrahten
uebernimmt ausschliesslich der Composition Root (``ai_trading_analyst.bootstrap``,
bewusst ausserhalb der vier Schichten, siehe Doc 10 Paragraph 9)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Request

from ai_trading_analyst.application.read_run_overview import ReadRunOverviewUseCase
from ai_trading_analyst.domain.analysis import MarketDataProvider, UnitOfWork
from ai_trading_analyst.domain.backtesting import BacktestParameters
from ai_trading_analyst.domain.screening import CandidateRuleParameters


def get_run_overview_use_case(request: Request) -> ReadRunOverviewUseCase:
    use_case: ReadRunOverviewUseCase = request.app.state.run_overview_use_case
    return use_case


def get_unit_of_work_factory(request: Request) -> Callable[[], UnitOfWork]:
    factory: Callable[[], UnitOfWork] = request.app.state.uow_factory
    return factory


def get_backtest_parameters(request: Request) -> BacktestParameters:
    """Die Schwellen der Stichprobengroesse -- dieselben wie im Messlauf.

    Sie stehen in der Konfiguration und nicht in der Oberflaeche: Eine
    Konfidenz, die die API anders einstuft als der Lauf, der die Zahlen
    erzeugt hat, waere schlimmer als gar keine.
    """
    params: BacktestParameters = request.app.state.backtest_parameters
    return params


def get_candidate_rule_parameters(request: Request) -> CandidateRuleParameters:
    params: CandidateRuleParameters = request.app.state.candidate_rule_parameters
    return params


def get_chart_market_data(request: Request) -> MarketDataProvider:
    """Der Anbieter fuer den Validierungschart -- **ausschliesslich aus dem
    Bestand**.

    Der Composition Root setzt ``market_data.source`` fuer diesen Anbieter
    fest auf ``stored``. Ein Webdienst, der die TWS-Client-ID belegt, waere
    gefaehrlicher als kein Chart (ADR 0052).
    """
    provider: MarketDataProvider = request.app.state.chart_market_data
    return provider
