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

from ai_trading_analyst.domain.analysts import AnalystRecommendations
from ai_trading_analyst.domain.backtesting import BacktestResult
from ai_trading_analyst.domain.earnings import EarningsFilterResult
from ai_trading_analyst.domain.fundamentals import FundamentalSnapshot
from ai_trading_analyst.domain.research import ResearchReport
from ai_trading_analyst.domain.screening import ScreeningResult
from ai_trading_analyst.domain.technical import TechnicalAssessment, TechnicalSnapshot


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
    technical: TechnicalSnapshot | None = None
    """Nur bei ``ScreeningStatus.CANDIDATE`` gesetzt -- die Chartauswertung
    beschreibt die Lage eines Kandidaten (Doc 10, Paragraph 6.8).

    Haengt an **keinem** anderen Modul: weder am Earnings-Filter noch am
    Research Agent. Beide koennen ausfallen, ohne dass hier etwas fehlt
    (CLAUDE.md: faellt Research aus, bleiben technische Analyse und
    Backtesting vollstaendig)."""
    technical_assessment: TechnicalAssessment | None = None
    """Die KI-Einordnung der Chartauswertung (Doc 10, Paragraph 6.8
    "Qualitative Interpretation"; ADR 0026).

    Gesetzt, sobald ``technical`` gesetzt ist -- und zwar unabhaengig vom
    Earnings-Filter und vom Research Agent. Anders als der Research Agent,
    der nur bei ``EARNINGS_CLEAR` laeuft, gilt hier die Entkopplung der
    Analysemodule ohne Einschraenkung: Gerade bei einem Kandidaten mit nahem
    Earnings-Termin ist die Chartlage interessant.

    Getrennt von ``technical`` gefuehrt und getrennt gespeichert, wie Doc 10
    es verlangt -- kein Feld dieses Objekts fliesst je in den Snapshot
    zurueck."""
    earnings: EarningsFilterResult | None = None
    """Nur bei ``ScreeningStatus.CANDIDATE`` gesetzt -- der Earnings-Filter
    laeuft ausschliesslich fuer bereits qualifizierte Kandidaten (Doc 10,
    Paragraph 6.5)."""
    research: ResearchReport | None = None
    """Nur gesetzt, wenn zusaetzlich ``earnings.status ==
    EarningsFilterStatus.EARNINGS_CLEAR`` war -- der Research Agent laeuft
    nur fuer Kandidaten, die Screener **und** Earnings-Filter bestanden
    haben (Doc 10, Paragraph 6.7)."""
    fundamentals: FundamentalSnapshot | None = None
    """Die deterministischen Fundamentalkennzahlen (Doc 10, Paragraph 6.9;
    ADR 0035) -- nur bei ``ScreeningStatus.CANDIDATE`` gesetzt.

    Haengt wie ``technical`` an keinem anderen Modul. Faellt EDGAR aus,
    bleibt das Feld leer und alles Uebrige vollstaendig; es gibt keinen
    Ersatzwert (CLAUDE.md: Analysemodule sind entkoppelt, fehlende Werte
    bleiben fehlend)."""
    analysts: AnalystRecommendations | None = None
    """Die Votenverteilung der Analysten (Doc 10, Paragraph 6.12 Punkt 9;
    ADR 0043) -- nur bei ``ScreeningStatus.CANDIDATE`` gesetzt.

    Haengt wie ``fundamentals`` an keinem anderen Modul. Insbesondere **nicht**
    am Research Agent: Berichtspunkt 9 steht damit auch dann, wenn die
    Recherche ausgefallen ist. Faellt umgekehrt der Anbieter aus, ist der
    Status ``UNAVAILABLE`` und nicht etwa ``None`` -- der Unterschied zwischen
    "nicht abgefragt" und "abgefragt, keine Antwort" bleibt erhalten."""
    backtest: tuple[BacktestResult, ...] = ()
    """Die historische Signalstatistik je Signalkombination (Doc 10,
    Paragraph 7; ADR 0038) -- nur bei ``ScreeningStatus.CANDIDATE`` gefuellt.

    Rechnet auf derselben bereits geladenen Kerzenreihe wie Screening und
    Chartauswertung, ohne zusaetzlichen Abruf. Reicht die Historie im
    Betrachtungsfenster nicht, bleibt das Feld leer und der Bericht weist
    Punkt 5 als Luecke aus."""


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

    @property
    def completion_ratio(self) -> float:
        """Anteil der Aktien mit Ergebnis an allen betrachteten.

        Ein Lauf ohne betrachtete Aktien ergibt 0.0 und nicht 1.0: Nichts
        gerechnet zu haben ist kein vollstaendiger Lauf.
        """
        betrachtet = len(self.outcomes) + len(self.errors)
        if betrachtet == 0:
            return 0.0
        return len(self.outcomes) / betrachtet


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
