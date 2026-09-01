"""Bewusst abgeschaltete Agenten -- ``provider: none``.

Der dritte Wert neben ``fixture`` und ``anthropic``, und er beantwortet eine
andere Frage: ``fixture`` simuliert einen **funktionierenden** Anbieter fuer
Start und Tests -- mit erfundenen, aber vollstaendig aussehenden Ergebnissen.
Im Scharfbetrieb waere genau das falsch: Ein Fixture-Ergebnis traegt
Teilwerte in den Score und Einstufungen in die Ergebnismeldung, die aussehen
wie geprueft und es nicht sind (CLAUDE.md: keine erfundenen Werte).

``none`` sagt stattdessen die Wahrheit: Der Betreiber hat den Agenten
abgeschaltet. Das Ergebnis ist ``UNAVAILABLE`` mit dem Grund
``provider_disabled`` -- derselbe Pfad wie bei einem Anbieterausfall, und
alles dahinter verhaelt sich bereits richtig: Der Score gewichtet die
fehlende Komponente um, der Bericht weist die Luecke aus, die Meldung
unterdrueckt die Zeile. Kein Netz, kein Schluessel, keine Kosten.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from ai_trading_analyst.domain.analysis import ResearchProvider, Stock, TechnicalInterpreter
from ai_trading_analyst.domain.research import ResearchReport, ResearchStatus
from ai_trading_analyst.domain.technical import (
    TechnicalAssessment,
    TechnicalAssessmentStatus,
    TechnicalSnapshot,
)

REASON_DISABLED = "provider_disabled"
"""Der Grund an jedem Ergebnis dieser Klassen. Eine Konstante, weil derselbe
Wert in Score-Begruendung und Berichtsluecke auftaucht -- ein Tippfehler
fiele erst dort auf."""


class DisabledResearchProvider(ResearchProvider):
    """Liefert fuer jede Aktie ``UNAVAILABLE`` -- der Agent ist abgeschaltet."""

    def __init__(self, now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._now = now

    def research(self, stock: Stock) -> ResearchReport:
        return ResearchReport(
            status=ResearchStatus.UNAVAILABLE,
            evaluated_at=self._now(),
            model=None,
            prompt_version=None,
            reason=REASON_DISABLED,
        )


class DisabledTechnicalInterpreter(TechnicalInterpreter):
    """Liefert fuer jeden Snapshot ``UNAVAILABLE`` -- der Agent ist abgeschaltet.

    **Bewusst ohne die Snapshot-Weiche** des Ports: Dessen
    ``INSUFFICIENT_DATA``-Regel verhindert den vergeblichen Anbieteraufruf,
    den es hier nicht gibt. Die Einordnung fehlt, weil der Betreiber sie
    abgeschaltet hat -- auch bei perfektem Snapshot. ``snapshot_insufficient``
    schoebe die Luecke den Daten zu.
    """

    def __init__(self, now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._now = now

    def interpret(self, stock: Stock, snapshot: TechnicalSnapshot) -> TechnicalAssessment:
        return TechnicalAssessment(
            status=TechnicalAssessmentStatus.UNAVAILABLE,
            evaluated_at=self._now(),
            model=None,
            prompt_version=None,
            interpreted_analysis_version=snapshot.analysis_version,
            reason=REASON_DISABLED,
        )
