"""Abstrakte Schnittstellen (Ports) fuer Marktdaten und Persistenz.

Konkrete Implementierungen (Fixture-Provider, SQLAlchemy-Repositories) leben
in der Infrastructure-Schicht und referenzieren diese Protocols -- nie
umgekehrt. Der Domain Layer kennt keinen konkreten Datenanbieter (Doc 10,
Paragraph 9).
"""

from __future__ import annotations

from collections.abc import Sequence
from types import TracebackType
from typing import Protocol
from uuid import UUID

from ai_trading_analyst.domain.screening import CandleSeries

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
