"""``/api/v1/signal-backtests`` -- der Signal-Backtest ueber alle Aktien
(ADR 0062). Der Zusammenbau steht in ``..views``, derselbe Code wie im
Exportschritt."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends

from ai_trading_analyst.domain.analysis import UnitOfWork

from .. import views
from ..dependencies import get_unit_of_work_factory
from ..schemas import SignalBacktestOverviewResponse

router = APIRouter(prefix="/api/v1/signal-backtests", tags=["signal-backtests"])


@router.get("", response_model=SignalBacktestOverviewResponse)
def signal_backtest_overview(
    uow_factory: Callable[[], UnitOfWork] = Depends(get_unit_of_work_factory),
) -> SignalBacktestOverviewResponse:
    """Je Aktie die juengste Auswertung mit allen Signalkombinationen."""
    with uow_factory() as uow:
        return views.signal_backtest_overview(uow)
