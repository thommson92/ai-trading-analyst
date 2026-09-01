"""``/api/v1/stocks`` -- die Analysehistorie einer Aktie (US-010)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ai_trading_analyst.domain.analysis import UnitOfWork

from ..dependencies import get_unit_of_work_factory
from ..schemas import Page, ReportSummaryResponse

router = APIRouter(prefix="/api/v1/stocks", tags=["stocks"])


@router.get("/{symbol}/reports", response_model=Page[ReportSummaryResponse])
def list_reports_of_stock(
    symbol: str,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    uow_factory: Callable[[], UnitOfWork] = Depends(get_unit_of_work_factory),
) -> Page[ReportSummaryResponse]:
    """Die Berichte einer Aktie ueber alle Laeufe, neueste zuerst.

    Das Symbol wird wie an jeder anderen Eingabegrenze normalisiert
    (``strip().upper()``, wie in der Kommandozeile).

    Eine unbekannte Aktie ist ein 404; eine bekannte ohne Bericht liefert eine
    leere Seite -- sie war nie Kandidat, und das ist eine Auskunft.
    """
    gesucht = symbol.strip().upper()
    with uow_factory() as uow:
        if uow.stocks.get_by_symbol(gesucht) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Aktie nicht gefunden."
            )
        reports = uow.stock_reports.list_for_symbol(gesucht, limit=limit, offset=offset)
        total = uow.stock_reports.count_for_symbol(gesucht)
    return Page(
        items=[ReportSummaryResponse.from_domain(report) for report in reports],
        total=total,
        limit=limit,
        offset=offset,
    )
