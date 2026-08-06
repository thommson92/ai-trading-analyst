"""``/api/v1/system`` -- Health- und Readiness-Probes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..schemas import HealthResponse, ReadinessResponse

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness -- der Prozess laeuft. Prueft keine Abhaengigkeiten."""
    return HealthResponse()


@router.get("/readiness", response_model=ReadinessResponse)
def readiness(request: Request) -> ReadinessResponse:
    """Readiness -- kann der Prozess aktuell Anfragen bedienen (z. B. Datenbank erreichbar)."""
    database_ready: bool = request.app.state.check_database_ready()
    return ReadinessResponse(
        status="ready" if database_ready else "not_ready",
        database="ok" if database_ready else "unreachable",
    )
