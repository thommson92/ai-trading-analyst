"""Ein Lauf mit den Zahlen, nach denen die Tagesuebersicht fragt.

Zwei der vier Zahlen stehen bereits am Lauf selbst -- gescreente Aktien und
gefundene Kandidaten. Die beiden anderen liegen verstreut: Wie oft der
Earnings-Filter ausgeschlossen hat, steht an den Screening-Ergebnissen, und
wie viele Aktien an einem Modulfehler haengen blieben, in der Fehlertabelle.

Dazu seit ADR 0062 die **gesperrten Symbole**: Die Wiederholsperre
(ADR 0054) nimmt kuerzlich voll analysierte Titel aus dem Lauf, bevor
irgendetwas fuer sie gerechnet wird -- sie hinterlassen keine Zeile. Wer nur
die Ergebniszeilen sieht, kann "gesperrt" nicht von "kein Kandidat"
unterscheiden. Hier wird die Sperre **rekonstruiert**: dasselbe Fenster,
dieselbe Abfrage wie im Lauf, angewandt auf den Startzeitpunkt des Laufs,
minus die Symbole, die der Lauf tatsaechlich bewertet hat.

Sie hier zusammenzufuehren und nicht im Endpunkt ist der Unterschied
zwischen Uebersetzung und Fachlogik: Der Endpunkt uebersetzt eine Anfrage,
dieser Anwendungsfall entscheidet, aus welchen Quellen sich die Auskunft
zusammensetzt (Doc 12, "keine KI- oder Geschaeftslogik in API-Endpunkten";
Doc 10, Paragraph 6.14).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from ai_trading_analyst.domain.analysis import (
    AnalysisRun,
    RepeatSuppressionParameters,
    UnitOfWork,
    suppression_window,
)
from ai_trading_analyst.domain.earnings import EarningsFilterStatus


@dataclass(frozen=True, slots=True)
class SuppressedSymbol:
    """Ein Symbol, das die Wiederholsperre aus diesem Lauf genommen hat --
    und der Lauf, dessen volle Analyse die Sperre ausgeloest hat."""

    symbol: str
    blocking_run_id: UUID
    blocking_evaluated_at: datetime


@dataclass(frozen=True, slots=True)
class RunOverview:
    """Ein Lauf und was ueber ihn gezaehlt wurde."""

    run: AnalysisRun
    earnings_excluded: int
    """Kandidaten, die ein Berichtstermin im Laufzeitfenster ausgeschlossen hat."""
    earnings_unknown: int
    """Kandidaten ohne bekannten Berichtstermin.

    Ausdruecklich getrennt vom Ausschluss: "unbekannt" ist kein belegter
    Nichttermin (ADR 0020), und die Tagesuebersicht darf beides nicht in eine
    Zahl werfen.
    """
    module_errors: int
    suppressed: tuple[SuppressedSymbol, ...] = ()
    """Rekonstruiert, nicht aufgezeichnet (ADR 0062). Die Grenzen: Das
    Fenster ist das **heutige**; ein Symbol, das die Watchlist verlassen hat
    und kurz zuvor Kandidat war, erschiene faelschlich als gesperrt; Laeufe
    vor ADR 0054 zeigen keine Sperren, weil damals alles bewertet wurde."""
    suppression_window_days: int | None = None
    """``None``, wenn die Sperre aus ist oder der Anwendungsfall ohne ihre
    Parameter gebaut wurde -- dann ist die Liste leer, weil nicht gerechnet,
    nicht weil nichts gesperrt war."""


class ReadRunOverviewUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        *,
        repeat_suppression: RepeatSuppressionParameters | None = None,
        market_timezone: str = "America/New_York",
    ) -> None:
        self._uow_factory = uow_factory
        self._repeat_suppression = repeat_suppression
        self._market_timezone = market_timezone

    def execute(self, run_id: UUID) -> RunOverview | None:
        """Der Lauf mit seinen Zahlen -- oder ``None``, wenn es ihn nicht gibt."""
        with self._uow_factory() as uow:
            run = uow.analysis_runs.get(run_id)
            if run is None:
                return None
            earnings = uow.screening_results.count_by_earnings_status(run_id)
            gesperrt, fenster_tage = self._gesperrte(uow, run)
            return RunOverview(
                run=run,
                earnings_excluded=earnings.get(EarningsFilterStatus.EARNINGS_EXCLUDED, 0),
                earnings_unknown=earnings.get(EarningsFilterStatus.UNKNOWN, 0),
                module_errors=uow.processing_errors.count_for_run(run_id),
                suppressed=gesperrt,
                suppression_window_days=fenster_tage,
            )

    def _gesperrte(
        self, uow: UnitOfWork, run: AnalysisRun
    ) -> tuple[tuple[SuppressedSymbol, ...], int | None]:
        """Dieselbe Rechnung wie ``RunAnalysisUseCase._ohne_kuerzlich_analysierte``,
        nur mit dem Startzeitpunkt des Laufs statt mit jetzt."""
        if self._repeat_suppression is None:
            return (), None
        start = run.started_at.astimezone(ZoneInfo(self._market_timezone))
        fenster = suppression_window(start, self._repeat_suppression)
        if fenster is None:
            return (), None
        seit, bis = fenster
        anker = uow.screening_results.latest_candidate_analyses(since=seit, until=bis)
        bewertet = uow.screening_results.symbols_for_run(run.id)
        gesperrt = tuple(
            SuppressedSymbol(
                symbol=symbol,
                blocking_run_id=eintrag.analysis_run_id,
                blocking_evaluated_at=eintrag.evaluated_at,
            )
            for symbol, eintrag in sorted(anker.items())
            if symbol not in bewertet
        )
        return gesperrt, self._repeat_suppression.window_days
