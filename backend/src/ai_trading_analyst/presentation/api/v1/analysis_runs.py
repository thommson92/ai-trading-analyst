"""``/api/v1/analysis-runs`` -- keine Fachlogik, nur Uebersetzung und Aufruf
des Application Use Case bzw. der Repositories ueber die UnitOfWork.

**Nur lesend** (ADR 0053): Einen Lauf startet die Aufgabenplanung ueber
``cli dispatch``, nicht ein HTTP-Aufruf.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

from ai_trading_analyst.application.read_run_overview import ReadRunOverviewUseCase
from ai_trading_analyst.domain.analysis import RunStatus, UnitOfWork

from ..dependencies import get_run_overview_use_case, get_unit_of_work_factory
from ..schemas import (
    AnalysisRunDetailResponse,
    AnalysisRunResponse,
    Page,
    ReportSummaryResponse,
)

router = APIRouter(prefix="/api/v1/analysis-runs", tags=["analysis-runs"])


@router.get("", response_model=Page[AnalysisRunResponse])
def list_analysis_runs(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: Annotated[list[RunStatus] | None, Query()] = None,
    uow_factory: Callable[[], UnitOfWork] = Depends(get_unit_of_work_factory),
) -> Page[AnalysisRunResponse]:
    """Laeufe, neueste zuerst, seitenweise.

    ``status`` darf mehrfach auftreten
    (``?status=COMPLETED&status=PARTIALLY_COMPLETED``). Das ist der Weg zur
    Frage "der letzte erfolgreiche Lauf": Ein Lauf mit einem isolierten
    Modulfehler ist ``PARTIALLY_COMPLETED`` und trotzdem abgeschlossen
    (Doc 10, Paragraph 11).
    """
    with uow_factory() as uow:
        runs = uow.analysis_runs.list_recent(limit=limit, offset=offset, status=status)
        total = uow.analysis_runs.count(status=status)
    return Page(
        items=[AnalysisRunResponse.from_domain(run) for run in runs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{run_id}", response_model=AnalysisRunDetailResponse)
def get_analysis_run(
    run_id: UUID,
    use_case: ReadRunOverviewUseCase = Depends(get_run_overview_use_case),
) -> AnalysisRunDetailResponse:
    overview = use_case.execute(run_id)
    if overview is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="AnalysisRun nicht gefunden."
        )
    return AnalysisRunDetailResponse.from_overview(overview)


@router.get("/{run_id}/reports", response_model=list[ReportSummaryResponse])
def list_reports_of_run(
    run_id: UUID,
    uow_factory: Callable[[], UnitOfWork] = Depends(get_unit_of_work_factory),
) -> list[ReportSummaryResponse]:
    """Die Berichte eines Laufs als Kurzliste.

    Ohne Seitengrenze: Ein Bericht entsteht nur fuer einen Kandidaten, und
    deren Zahl steht als ``candidates_found`` am Lauf.

    Ein unbekannter Lauf ist ein 404 und keine leere Liste -- sonst saehe ein
    Tippfehler in der Kennung aus wie ein Tag ohne Kandidaten.
    """
    with uow_factory() as uow:
        if uow.analysis_runs.get(run_id) is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND, detail="AnalysisRun nicht gefunden."
            )
        reports = uow.stock_reports.list_for_run(run_id)
    return [ReportSummaryResponse.from_domain(report) for report in reports]
