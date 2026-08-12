"""Gemeinsames Ergebnisformat aller Testschritte.

Jeder Schritt ist einzeln ausfuehrbar (Nutzervorgabe) und liefert ein
``StepResult`` -- unabhaengig davon, ob er auf macOS gegen ein generisches
Chromium-Ziel laeuft (Protokoll-Exploration) oder auf Windows gegen echtes
TradingView Desktop (Validierung). Welches der beiden zutrifft, haelt
``environment`` fest, nicht der Schritt selbst -- ein Schritt kennt nur sein
CDP-Ziel, nicht die Absicht dahinter.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class StepStatus(StrEnum):
    """Vier Ausgaenge, bewusst nicht nur bestanden/fehlgeschlagen.

    NOT_APPLICABLE deckt z. B. einen Indikator-Schritt ab, der mangels
    TradingView-Ziel gar nicht erst versucht werden konnte -- das ist etwas
    anderes als ein tatsaechlicher Fehlschlag und muss im Bericht getrennt
    ausgewiesen werden (Vorgabe: "auf macOS nachgewiesen / auf Windows
    nachgewiesen / noch nicht getestet / fehlgeschlagen").
    """

    PASSED = "PASSED"
    FAILED = "FAILED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True, slots=True)
class StepResult:
    step_id: str
    title: str
    status: StepStatus
    started_at: datetime
    finished_at: datetime
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()


StepFunction = Callable[[], Awaitable[dict[str, Any]]]


async def run_step(step_id: str, title: str, func: StepFunction) -> StepResult:
    """Fuehrt einen Schritt kontrolliert aus und wandelt jede Ausnahme in ein
    diagnostizierbares ``FAILED``-Ergebnis um -- kein Schritt darf den
    gesamten Testlauf durch eine unbehandelte Exception abbrechen (Vorgabe:
    "klare Fehlerdiagnosen liefern").

    ``func`` traegt bereits alles, was der jeweilige Schritt braucht (Session,
    Konfiguration, vorherige Ergebnisse) -- ``run_step`` selbst kennt nur das
    einheitliche Ergebnisformat, keine Schrittlogik.

    Ein Schritt signalisiert einen von ``PASSED`` abweichenden Status ueber
    den reservierten Schluessel ``_status`` im zurueckgegebenen Dict (z. B.
    ``NOT_APPLICABLE``, wenn eine Voraussetzung fehlt, oder
    ``INCONCLUSIVE``, wenn noch keine Sonde konfiguriert ist).
    """
    started_at = datetime.now(UTC)
    try:
        details = await func()
        finished_at = datetime.now(UTC)
        status = StepStatus(details.pop("_status", StepStatus.PASSED.value))
        return StepResult(
            step_id=step_id,
            title=title,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            details=details,
        )
    except Exception as exc:
        finished_at = datetime.now(UTC)
        return StepResult(
            step_id=step_id,
            title=title,
            status=StepStatus.FAILED,
            started_at=started_at,
            finished_at=finished_at,
            error=f"{type(exc).__name__}: {exc}",
        )
