"""API-Schemas (Presentation-Schicht) -- reine Uebersetzung, keine Fachlogik."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from ai_trading_analyst.domain.analysis import AnalysisRun, RunStatus


class AnalysisRunResponse(BaseModel):
    id: UUID
    status: RunStatus
    started_at: datetime
    completed_at: datetime | None
    number_of_stocks: int
    candidates_found: int
    error_message: str | None

    @classmethod
    def from_domain(cls, run: AnalysisRun) -> AnalysisRunResponse:
        return cls(
            id=run.id,
            status=run.status,
            started_at=run.started_at,
            completed_at=run.completed_at,
            number_of_stocks=run.number_of_stocks,
            candidates_found=run.candidates_found,
            error_message=run.error_message,
        )


class HealthResponse(BaseModel):
    status: str = "ok"


class ReadinessResponse(BaseModel):
    status: str
    database: str
