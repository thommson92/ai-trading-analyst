"""Ein Lauf mit den Zahlen, nach denen die Tagesuebersicht fragt.

Zwei der vier Zahlen stehen bereits am Lauf selbst -- gescreente Aktien und
gefundene Kandidaten. Die beiden anderen liegen verstreut: Wie oft der
Earnings-Filter ausgeschlossen hat, steht an den Screening-Ergebnissen, und
wie viele Aktien an einem Modulfehler haengen blieben, in der Fehlertabelle.

Sie hier zusammenzufuehren und nicht im Endpunkt ist der Unterschied
zwischen Uebersetzung und Fachlogik: Der Endpunkt uebersetzt eine Anfrage,
dieser Anwendungsfall entscheidet, aus welchen Quellen sich die Auskunft
zusammensetzt (Doc 12, "keine KI- oder Geschaeftslogik in API-Endpunkten";
Doc 10, Paragraph 6.14).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from ai_trading_analyst.domain.analysis import AnalysisRun, UnitOfWork
from ai_trading_analyst.domain.earnings import EarningsFilterStatus


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


class ReadRunOverviewUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, run_id: UUID) -> RunOverview | None:
        """Der Lauf mit seinen Zahlen -- oder ``None``, wenn es ihn nicht gibt."""
        with self._uow_factory() as uow:
            run = uow.analysis_runs.get(run_id)
            if run is None:
                return None
            earnings = uow.screening_results.count_by_earnings_status(run_id)
            return RunOverview(
                run=run,
                earnings_excluded=earnings.get(EarningsFilterStatus.EARNINGS_EXCLUDED, 0),
                earnings_unknown=earnings.get(EarningsFilterStatus.UNKNOWN, 0),
                module_errors=uow.processing_errors.count_for_run(run_id),
            )
