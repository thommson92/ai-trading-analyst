"""Historischer Backfill: den Bestand an nativen Bars auffuellen.

Der Job holt beim Anbieter **nur, was fehlt**. Er kennt dafuer keinen festen
Zeitraum, sondern fragt den Bestand: Bis wann liegen fuer diese Aktie schon
Bars vor? Daraus ergibt sich die Anfrage — ein Tag nach einem gewoehnlichen
Lauf, drei Wochen nach einem Serverausfall, der volle Standardzeitraum beim
allerersten Mal.

Das ist die Anforderung aus [ADR 0018](../../../docs/adr/0018-kein-windows-autologon.md):
Weil nach dem sonntaeglichen Neustart erst am Montag von Hand gestartet wird,
muss der Backfill **beliebig grosse Luecken** schliessen koennen. Ein
verlaengertes Wochenende darf kein Sonderfall sein.

Zwei Eigenschaften machen den Lauf betriebstauglich (ADR 0014, E3):

* **Wiederholbar.** Das Speichern ist ueber ``(symbol, start)`` idempotent.
  Ein abgebrochener Lauf wird schlicht erneut gestartet; aufzuraeumen gibt es
  nichts.
* **Fehlerisoliert.** Faellt eine Aktie aus, laeuft der Rest weiter. Bei rund
  200 Symbolen und einer Stunde Laufzeit waere ein Abbruch beim ersten
  unbekannten Symbol die schlechteste aller Antworten.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ai_trading_analyst.domain.analysis import (
    ContractSpec,
    HistoricalBarSource,
    MarketDataProviderError,
    UnitOfWork,
)
from ai_trading_analyst.observability.logging_setup import get_logger

_logger = get_logger(__name__)

UEBERLAPPUNG_TAGE = 1
"""Wieviel ueber den letzten bekannten Bar hinaus zurueckgefragt wird.

Ein Tag Ueberlappung kostet nichts -- doppelte Bars werden beim Speichern
uebergangen -- und verhindert den Fall, in dem ein Lauf mitten in einem
Handelstag abbricht und der naechste genau diesen Rest ueberspringt.
"""


@dataclass(frozen=True, slots=True)
class SymbolBackfill:
    """Was der Lauf fuer eine Aktie erreicht hat."""

    symbol: str
    requested_days: int | None
    received_bars: int = 0
    stored_bars: int = 0
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.error is not None


@dataclass(frozen=True, slots=True)
class BackfillReport:
    results: tuple[SymbolBackfill, ...] = field(default_factory=tuple)

    @property
    def stored_bars(self) -> int:
        return sum(result.stored_bars for result in self.results)

    @property
    def failures(self) -> tuple[SymbolBackfill, ...]:
        return tuple(result for result in self.results if result.failed)


def missing_days(
    latest_start: datetime | None, now: datetime, overlap_days: int = UEBERLAPPUNG_TAGE
) -> int | None:
    """Wieviele Tage muessen nachgeholt werden?

    ``None`` heisst: Es liegt noch nichts vor, also der konfigurierte
    Standardzeitraum. Sonst der Abstand zum juengsten Bar, aufgerundet und um
    die Ueberlappung erweitert -- mindestens aber ein Tag, damit auch ein Lauf
    kurz nach dem letzten Bar noch die laufende Sitzung nachzieht.
    """
    if latest_start is None:
        return None
    abstand = (now - latest_start).days
    return max(abstand + overlap_days, 1)


class BackfillHistoryUseCase:
    def __init__(
        self,
        bar_source: HistoricalBarSource,
        uow_factory: Callable[[], UnitOfWork],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._bar_source = bar_source
        self._uow_factory = uow_factory
        self._now = now

    def execute(
        self,
        watchlist: Sequence[ContractSpec],
        on_progress: Callable[[int, int, SymbolBackfill], None] | None = None,
    ) -> BackfillReport:
        ergebnisse: list[SymbolBackfill] = []
        for index, contract in enumerate(watchlist, start=1):
            ergebnis = self._backfill_one(contract)
            ergebnisse.append(ergebnis)
            if on_progress is not None:
                on_progress(index, len(watchlist), ergebnis)
        return BackfillReport(results=tuple(ergebnisse))

    def _backfill_one(self, contract: ContractSpec) -> SymbolBackfill:
        symbol = contract.symbol
        with self._uow_factory() as uow:
            tage = missing_days(uow.intraday_bars.latest_start(symbol), self._now())

        try:
            bars = self._bar_source.fetch_intraday_bars(contract, tage)
        except MarketDataProviderError as error:
            # Systemgrenze: Ein Ausfall bei einer Aktie beendet den Lauf nicht.
            _logger.warning("%s: Abruf fehlgeschlagen -- %s", symbol, error)
            return SymbolBackfill(symbol=symbol, requested_days=tage, error=str(error))

        with self._uow_factory() as uow:
            neu = uow.intraday_bars.add_all(symbol, bars)
            uow.commit()

        return SymbolBackfill(
            symbol=symbol,
            requested_days=tage,
            received_bars=len(bars),
            stored_bars=neu,
        )
