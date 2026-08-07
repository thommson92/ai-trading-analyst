"""``/api/v1/analysis-runs`` -- keine Fachlogik, nur Uebersetzung und Aufruf
des Application Use Case bzw. der Repositories ueber die UnitOfWork."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ai_trading_analyst.application.run_analysis import RunAnalysisUseCase
from ai_trading_analyst.domain.analysis import UnitOfWork

from ..dependencies import get_run_analysis_use_case, get_unit_of_work_factory
from ..schemas import AnalysisRunResponse

router = APIRouter(prefix="/api/v1/analysis-runs", tags=["analysis-runs"])


@router.post("", response_model=AnalysisRunResponse, status_code=status.HTTP_201_CREATED)
def start_analysis_run(
    use_case: RunAnalysisUseCase = Depends(get_run_analysis_use_case),
) -> AnalysisRunResponse:
    """Startet in Sprint 1B ausschliesslich einen fixture-basierten manuellen Lauf."""
    summary = use_case.execute()
    return AnalysisRunResponse.from_domain(summary.run)


@router.get("", response_model=list[AnalysisRunResponse])
def list_analysis_runs(
    uow_factory: Callable[[], UnitOfWork] = Depends(get_unit_of_work_factory),
) -> list[AnalysisRunResponse]:
    with uow_factory() as uow:
        runs = uow.analysis_runs.list_all()
    return [AnalysisRunResponse.from_domain(run) for run in runs]


@router.get("/{run_id}", response_model=AnalysisRunResponse)
def get_analysis_run(
    run_id: UUID,
    uow_factory: Callable[[], UnitOfWork] = Depends(get_unit_of_work_factory),
) -> AnalysisRunResponse:
    with uow_factory() as uow:
        run = uow.analysis_runs.get(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="AnalysisRun nicht gefunden."
        )
    return AnalysisRunResponse.from_domain(run)
