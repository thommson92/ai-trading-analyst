"""API-Schemas (Presentation-Schicht) -- reine Uebersetzung, keine Fachlogik."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from ai_trading_analyst.application.read_run_overview import RunOverview
from ai_trading_analyst.domain.analysis import AnalysisRun, RunStatus
from ai_trading_analyst.domain.report import StoredReport
from ai_trading_analyst.domain.scoring import Recommendation


class Page[T](BaseModel):
    """Eine Seite einer Liste.

    ``total`` gehoert dazu, nicht nur die Eintraege: Ohne die Gesamtzahl
    koennte die Oberflaeche nicht sagen, ob eine weitere Seite existiert --
    sie muesste raten oder blind weiterblaettern.
    """

    items: list[T]
    total: int
    limit: int
    offset: int


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


class AnalysisRunDetailResponse(AnalysisRunResponse):
    """Ein Lauf mit den Zahlen, die nicht an ihm selbst stehen."""

    earnings_excluded: int
    earnings_unknown: int
    module_errors: int

    @classmethod
    def from_overview(cls, overview: RunOverview) -> AnalysisRunDetailResponse:
        run = overview.run
        return cls(
            id=run.id,
            status=run.status,
            started_at=run.started_at,
            completed_at=run.completed_at,
            number_of_stocks=run.number_of_stocks,
            candidates_found=run.candidates_found,
            error_message=run.error_message,
            earnings_excluded=overview.earnings_excluded,
            earnings_unknown=overview.earnings_unknown,
            module_errors=overview.module_errors,
        )


class ReportSummaryResponse(BaseModel):
    """Die Kurzfassung eines Berichts -- was in einer Liste steht.

    Genau die Werte, die als eigene Spalten an ``stock_reports`` liegen. Wer
    mehr braucht, holt das Dokument; alles andere hiesse, es hier in Teilen
    nachzubauen.
    """

    report_id: UUID
    symbol: str
    created_at: datetime
    recommendation: Recommendation | None
    swing_score: float | None
    investment_score: float | None

    @classmethod
    def from_domain(cls, report: StoredReport) -> ReportSummaryResponse:
        return cls(
            report_id=report.id,
            symbol=report.symbol,
            created_at=report.created_at,
            recommendation=report.recommendation,
            swing_score=report.swing_score,
            investment_score=report.investment_score,
        )


class HealthResponse(BaseModel):
    status: str = "ok"


class ReadinessResponse(BaseModel):
    status: str
    database: str
