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

from ai_trading_analyst.domain.backtesting import BacktestResult
from ai_trading_analyst.domain.earnings import NextEarningsDate
from ai_trading_analyst.domain.research import ResearchReport
from ai_trading_analyst.domain.screening import CandleSeries, IntradayBar

from .models import (
    AnalysisRun,
    ContractSpec,
    Stock,
    StockProcessingError,
    StockScreeningOutcome,
)


class MarketDataProviderError(Exception):
    """Ein Marktdatenanbieter konnte fuer eine Aktie keine Daten liefern.

    Wird vom Application-Layer pro Aktie isoliert (Fehlerisolation) -- ein
    Fehler bei einer Aktie darf den Lauf nicht insgesamt scheitern lassen.
    """


class HistoricalBarSource(Protocol):
    """Liefert native Intraday-Bars einer Aktie, aeltester Bar zuerst.

    Bewusst getrennt von ``MarketDataProvider``: Der Provider liefert fertige
    Kerzen samt Indikatoren, diese Quelle nur Rohbars. Der Backfill braucht
    genau die Rohbars, und der Screener liest sie spaeter aus dem eigenen
    Bestand -- dieselbe Schnittstelle, einmal gegen die TWS, einmal gegen die
    Datenbank.
    """

    def fetch_intraday_bars(
        self, contract: ContractSpec, days: int | None = None
    ) -> Sequence[IntradayBar]:
        """Holt Bars der letzten ``days`` Tage.

        ``None`` bedeutet den konfigurierten Standardzeitraum -- den Fall des
        allerersten Abrufs, wenn noch nichts gespeichert ist. Danach fragt der
        Backfill nur noch die Luecke seit dem letzten bekannten Bar an.

        Raises:
            MarketDataProviderError: wenn die Bars nicht beschafft werden
                konnten.
        """
        ...

    def close(self) -> None:
        """Gibt eine gehaltene Verbindung frei. Muss mehrfach aufrufbar sein."""
        ...


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


class EarningsProviderError(Exception):
    """Ein Earnings-Anbieter konnte fuer eine Aktie keinen Termin liefern.

    Wird vom Application-Layer pro Aktie isoliert -- ein Ausfall der Quelle
    ist ein normaler Betriebszustand (ADR 0017), kein Laufabbruch. Die
    technische Analyse laeuft unabhaengig weiter (Doc 10: Analysemodule sind
    entkoppelt).
    """


class EarningsProvider(Protocol):
    """Liefert den naechsten bekannten Earnings-Termin einer Aktie."""

    def next_earnings_date(self, stock: Stock) -> NextEarningsDate | None:
        """Naechster kuenftiger Earnings-Termin, oder ``None`` bei fehlender
        Abdeckung (ADR 0017 L3) -- niemals stillschweigend als unbedenklich
        zu werten.

        Raises:
            EarningsProviderError: wenn die Quelle nicht erreichbar war.
        """
        ...


class ResearchProviderError(Exception):
    """Ein Research-Anbieter konnte fuer eine Aktie keinen Bericht liefern.

    Wird vom Application-Layer pro Aktie isoliert -- ein Ausfall der Quelle
    ist ein normaler Betriebszustand, kein Laufabbruch (Muster
    ``EarningsProviderError``). Die deterministische Chartanalyse und das
    Backtesting laufen unabhaengig von Research weiter (CLAUDE.md, Doc 10:
    Analysemodule sind entkoppelt).
    """


class ResearchProvider(Protocol):
    """Liefert einen strukturierten Recherche-Bericht zu einer Aktie."""

    def research(self, stock: Stock) -> ResearchReport:
        """Bericht mit Belegen, oder ``status=INSUFFICIENT_DATA`` bei zu
        duenner Grundlage -- niemals ein erfundener Bericht (Doc 10,
        Paragraph 10, Halluzinationsschutz).

        Raises:
            ResearchProviderError: wenn die Quelle nicht erreichbar war.
        """
        ...


class BacktestResultRepository(Protocol):
    def add(self, result: BacktestResult) -> None: ...
    def list_for_stock(self, stock_id: UUID) -> Sequence[BacktestResult]: ...


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
    backtest_results: BacktestResultRepository

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
