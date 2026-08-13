"""Abstrakte Schnittstellen (Ports) fuer Marktdaten und Persistenz.

Konkrete Implementierungen (Fixture-Provider, SQLAlchemy-Repositories) leben
in der Infrastructure-Schicht und referenzieren diese Protocols -- nie
umgekehrt. Der Domain Layer kennt keinen konkreten Datenanbieter (Doc 10,
Paragraph 9).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from types import TracebackType
from typing import Protocol
from uuid import UUID

from ai_trading_analyst.domain.screening import CandleSeries, IntradayBar

from .models import AnalysisRun, Stock, StockProcessingError, StockScreeningOutcome


class MarketDataProviderError(Exception):
    """Ein Marktdatenanbieter konnte fuer eine Aktie keine Daten liefern.

    Wird vom Application-Layer pro Aktie isoliert (Fehlerisolation) -- ein
    Fehler bei einer Aktie darf den Lauf nicht insgesamt scheitern lassen.
    """


class MarketDataProvider(Protocol):
    """Liefert die fuer die Kandidatenpruefung benoetigten Aktien und Kerzen."""

    def list_stocks(self) -> Sequence[Stock]: ...

    def get_candle_series(self, stock: Stock) -> CandleSeries:
        """Liefert die vollstaendige Kerzenserie einer Aktie.

        Raises:
            MarketDataProviderError: wenn fuer diese Aktie keine Daten
                beschafft werden konnten.
        """
        ...


class IntradayBarRepository(Protocol):
    """Speicher fuer die nativen Bars des Anbieters.

    Er beantwortet die eine Frage, von der der Backfill lebt: **Bis wann
    liegen fuer diese Aktie schon Daten vor?** Daraus ergibt sich, was noch
    zu holen ist -- ein Tag nach einem gewoehnlichen Lauf, drei Wochen nach
    einem laengeren Ausfall, ein ganzes Jahr beim ersten Mal. Ein fester
    Zeitraum je Lauf wuerde entweder zu viel holen oder zu wenig.
    """

    def latest_start(self, symbol: str) -> datetime | None:
        """Beginn des juengsten gespeicherten Bars, oder ``None``."""
        ...

    def add_all(self, symbol: str, bars: Sequence[IntradayBar]) -> int:
        """Speichert Bars und liefert die Zahl der **neu** hinzugekommenen.

        Wiederholt gelieferte Bars werden uebergangen, nicht als Fehler
        behandelt: Die Zeitraeume zweier Laeufe ueberlappen sich zwangslaeufig,
        und ein abgebrochener Lauf muss ohne Aufraeumen wiederholbar sein.
        """
        ...

    def list_for(self, symbol: str) -> Sequence[IntradayBar]:
        """Alle gespeicherten Bars einer Aktie, nach Zeit aufsteigend."""
        ...


class StockRepository(Protocol):
    def add(self, stock: Stock) -> None: ...
    def get_by_symbol(self, symbol: str) -> Stock | None: ...
    def list_all(self) -> Sequence[Stock]: ...


class AnalysisRunRepository(Protocol):
    def add(self, run: AnalysisRun) -> None: ...
    def get(self, run_id: UUID) -> AnalysisRun | None: ...
    def list_all(self) -> Sequence[AnalysisRun]: ...
    def update(self, run: AnalysisRun) -> None: ...


class ScreeningResultRepository(Protocol):
    def add(self, outcome: StockScreeningOutcome) -> None: ...
    def list_for_run(self, run_id: UUID) -> Sequence[StockScreeningOutcome]: ...


class ProcessingErrorRepository(Protocol):
    def add(self, error: StockProcessingError) -> None: ...
    def list_for_run(self, run_id: UUID) -> Sequence[StockProcessingError]: ...


class UnitOfWork(Protocol):
    """Transaktionsgrenze ueber alle Repositories eines Analyse-Laufs.

    Jeder Verwendungsblock committet oder rollt vollstaendig zurueck -- kein
    teilweise geschriebener Zustand innerhalb einer einzelnen Transaktion.
    """

    stocks: StockRepository
    intraday_bars: IntradayBarRepository
    analysis_runs: AnalysisRunRepository
    screening_results: ScreeningResultRepository
    processing_errors: ProcessingErrorRepository

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
