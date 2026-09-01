"""FastAPI-Dependencies. Lesen fertig verdrahtete Objekte aus ``app.state``,
statt selbst konkrete Infrastruktur zu konstruieren -- das Verdrahten
uebernimmt ausschliesslich der Composition Root (``ai_trading_analyst.bootstrap``,
bewusst ausserhalb der vier Schichten, siehe Doc 10 Paragraph 9)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Request

from ai_trading_analyst.application.read_run_overview import ReadRunOverviewUseCase
from ai_trading_analyst.domain.analysis import UnitOfWork


def get_run_overview_use_case(request: Request) -> ReadRunOverviewUseCase:
    use_case: ReadRunOverviewUseCase = request.app.state.run_overview_use_case
    return use_case


def get_unit_of_work_factory(request: Request) -> Callable[[], UnitOfWork]:
    factory: Callable[[], UnitOfWork] = request.app.state.uow_factory
    return factory
