"""Entitaeten eines Analyse-Laufs (Doc 05: Stock, AnalysisRun).

Im Unterschied zu den Wertobjekten in ``domain.screening`` haben diese
Klassen eine Identitaet (``id``) und einen Lebenszyklus -- ``AnalysisRun``
durchlaeuft mehrere Status, waehrend etwa ``ScreeningResult`` einmal berechnet
und danach nie mehr veraendert wird.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from ai_trading_analyst.domain.earnings import EarningsFilterResult
from ai_trading_analyst.domain.research import ResearchReport
from ai_trading_analyst.domain.screening import ScreeningResult


class RunStatus(StrEnum):
    """Laufstatus eines Analyse-Laufs (Sprint 1B: ohne SKIPPED_*-Status)."""

    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    SCREENING = "SCREENING"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class Stock:
    """Stammdaten einer Aktie (Doc 05)."""

    id: uuid.UUID
    symbol: str
    exchange: str


@dataclass(slots=True)
class AnalysisRun:
    """Ein Analyse-Lauf. Veraenderlich, weil der Status sich waehrend der
    Verarbeitung mehrfach aendert (SCHEDULED -> RUNNING -> SCREENING -> ...)."""

    id: uuid.UUID
    status: RunStatus
    started_at: datetime
    completed_at: datetime | None = None
    number_of_stocks: int = 0
    candidates_found: int = 0
    error_message: str | None = None
    """Nur gesetzt, wenn der Lauf vor Beginn des Screenings insgesamt
    gescheitert ist (z. B. der Marktdatenanbieter lieferte ueberhaupt keine
    Aktienliste). Fuer Fehler bei einzelnen Aktien siehe
    ``StockProcessingError`` -- die betreffen nicht den Lauf als Ganzes."""


@dataclass(frozen=True, slots=True)
class StockScreeningOutcome:
    """Das Ergebnis der Kandidatenpruefung fuer eine Aktie in einem Lauf.

    Verbindet das fachliche Ergebnis aus ``domain.screening`` (unveraendert
    uebernommen, keine Signalformeln in dieser Schicht) mit dem Kontext, in
    dem es entstanden ist.
    """

    analysis_run_id: uuid.UUID
    stock: Stock
    result: ScreeningResult
    decision_candle_index: int
    evaluated_at: datetime
    signal_rule_version: str
    earnings: EarningsFilterResult | None = None
    """Nur bei ``ScreeningStatus.CANDIDATE`` gesetzt -- der Earnings-Filter
    laeuft ausschliesslich fuer bereits qualifizierte Kandidaten (Doc 10,
    Paragraph 6.5)."""
    research: ResearchReport | None = None
    """Nur gesetzt, wenn zusaetzlich ``earnings.status ==
    EarningsFilterStatus.EARNINGS_CLEAR`` war -- der Research Agent laeuft
    nur fuer Kandidaten, die Screener **und** Earnings-Filter bestanden
    haben (Doc 10, Paragraph 6.7)."""


@dataclass(frozen=True, slots=True)
class StockProcessingError:
    """Ein pro Aktie isolierter Fehler, der den restlichen Lauf nicht abbricht."""

    analysis_run_id: uuid.UUID
    stock_symbol: str
    message: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class AnalysisRunSummary:
    """Strukturierte Rueckgabe des Use Cases -- keine Fachlogik, nur Aggregation."""

    run: AnalysisRun
    outcomes: tuple[StockScreeningOutcome, ...] = field(default_factory=tuple)
    errors: tuple[StockProcessingError, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ContractSpec:
    """Wie eine Aktie beim Marktdatenanbieter zu finden ist.

    ``exchange`` ist der Weg der Anfrage (bei IBKR ueblicherweise die
    Sammelroute "SMART"), ``primary_exchange`` die tatsaechliche Heimatboerse.
    Beides auseinanderzuhalten ist noetig, weil dasselbe Kuerzel an mehreren
    Boersen gefuehrt sein kann und die Heimatboerse entscheidet, welches
    Papier gemeint ist.
    """

    symbol: str
    exchange: str = "SMART"
    currency: str = "USD"
    primary_exchange: str | None = None
