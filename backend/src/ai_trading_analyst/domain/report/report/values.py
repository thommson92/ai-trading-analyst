"""Werte des Analyseberichts (Doc 10, Paragraph 6.12; ADR 0039).

Der Bericht **erzeugt keine neuen Fakten**. Er ordnet gespeicherte
Analyseergebnisse den achtzehn Pflichtpunkten zu und traegt ausdruecklich
ein, was fehlt -- statt einen Punkt stillschweigend wegzulassen.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

from ai_trading_analyst.domain.backtesting import BacktestResult
from ai_trading_analyst.domain.earnings import EarningsFilterResult
from ai_trading_analyst.domain.fundamentals import FundamentalSnapshot
from ai_trading_analyst.domain.research import ResearchReport
from ai_trading_analyst.domain.screening import ScreeningStatus, SignalEvent
from ai_trading_analyst.domain.technical import TechnicalAssessment, TechnicalSnapshot

REPORT_SCHEMA_VERSION = "report-v1"
"""Fassung des Berichtsschemas (Doc 10, Paragraph 8).

Sie steigt, wenn sich Zuschnitt oder Bedeutung der Abschnitte aendert -- nicht,
wenn ein Zulieferer neue Zahlen liefert. Dessen eigene Version steht ohnehin
am jeweiligen Teilergebnis.

``report-v1`` fuehrt alle achtzehn Punkte, vier davon zwangslaeufig als
Luecke: Optionsanalyse und Scoring gehoeren zu Sprint 5. Wenn sie kommen,
aendert sich der Zuschnitt nicht -- die Luecken fuellen sich. Die Version
steigt deshalb dann nicht.
"""


class ReportSection(StrEnum):
    """Die achtzehn Pflichtpunkte aus Doc 10, Paragraph 6.12, in der Reihenfolge
    des Dokuments.

    Ein Enum und keine Liste von Ueberschriften: Eine Luecke muss den Punkt
    benennen koennen, zu dem sie gehoert, und der Bericht muss zusichern
    koennen, dass er alle achtzehn fuehrt.
    """

    SYMBOL_UND_UNTERNEHMEN = "SYMBOL_UND_UNTERNEHMEN"
    ANALYSEZEITPUNKT = "ANALYSEZEITPUNKT"
    TECHNISCHE_SIGNALE = "TECHNISCHE_SIGNALE"
    EARNINGS_STATUS = "EARNINGS_STATUS"
    SIGNALSTATISTIK = "SIGNALSTATISTIK"
    TECHNISCHE_LAGE = "TECHNISCHE_LAGE"
    ZONEN = "ZONEN"
    NACHRICHTEN = "NACHRICHTEN"
    ANALYSTENMEINUNGEN = "ANALYSTENMEINUNGEN"
    FUNDAMENTALE_BEWERTUNG = "FUNDAMENTALE_BEWERTUNG"
    CHANCEN = "CHANCEN"
    RISIKEN = "RISIKEN"
    PUT_STRATEGIEN = "PUT_STRATEGIEN"
    SWING_SCORE = "SWING_SCORE"
    INVESTMENT_SCORE = "INVESTMENT_SCORE"
    EMPFEHLUNG = "EMPFEHLUNG"
    KONFIDENZ_UND_DATENLUECKEN = "KONFIDENZ_UND_DATENLUECKEN"
    QUELLEN = "QUELLEN"


class GapKind(StrEnum):
    """Fehlt der Punkt ganz, oder steht er nur unter Vorbehalt?

    Die Unterscheidung ist noetig, weil Punkt 17 beides verlangt: „Konfidenz
    **und** Datenluecken". Eine Trefferquote, die ungefilterte Ereignisse
    zaehlt, fehlt nicht -- sie gilt nur eingeschraenkt. Beides in einen Topf
    zu werfen machte aus einer bekannten Ungenauigkeit ein Loch oder
    umgekehrt.
    """

    FEHLT = "FEHLT"
    EINGESCHRAENKT = "EINGESCHRAENKT"


class Recommendation(StrEnum):
    """Empfehlungsstufen aus Doc 10, Paragraph 6.12.

    Dort ausdruecklich als *beispielhaft* bezeichnet. Sie werden hier
    uebernommen, weil es keine andere Festlegung gibt; die endgueltige
    deutsche Formulierung gehoert zu den KI-Leitlinien und damit zur
    KI-Haelfte des Berichts.
    """

    STRONG_CANDIDATE = "STRONG_CANDIDATE"
    CANDIDATE = "CANDIDATE"
    WATCH = "WATCH"
    AVOID_FOR_NOW = "AVOID_FOR_NOW"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True, slots=True)
class ReportGap:
    """Ein Punkt, der fehlt oder nur eingeschraenkt gilt -- mit Begruendung."""

    section: ReportSection
    kind: GapKind
    reason: str


class SourceKind(StrEnum):
    RESEARCH = "RESEARCH"
    FUNDAMENTALS = "FUNDAMENTALS"


@dataclass(frozen=True, slots=True)
class ReportSource:
    """Ein Beleg fuer Punkt 18, unabhaengig davon, woher er kommt.

    Research liefert Zitate mit Titel und Abrufzeitpunkt, die
    Fundamentalanalyse Einreichungen mit Vorgangsnummer. Beide bekommen hier
    dieselbe flache Form, damit Punkt 18 eine Liste ist und keine Fallunter-
    scheidung.
    """

    kind: SourceKind
    label: str
    url: str
    retrieved_at: datetime | None = None
    filed: date | None = None
    """Einreichungsdatum -- nur bei SEC-Quellen, wo es ein echtes Datum gibt."""
    source_age: str | None = None
    """Das vom Research-Anbieter gemeldete Alter, **roh uebernommen** (ADR
    0029). Ausdruecklich kein Datum: Die Angabe ist relativ ("3 days ago"),
    und sie in ein Datum zu rechnen waere ein abgeleiteter Wert an einer
    Stelle, die Genauigkeit verspricht."""


@dataclass(frozen=True, slots=True)
class StockReport:
    """Der vollstaendige Analysebericht einer Aktie fuer einen Lauf.

    Haelt keine Kopien der Zahlen, sondern die Teilergebnisse selbst: Sie sind
    unveraenderlich und tragen ihre eigene Analyseversion. Eine zweite Fassung
    derselben Zahl waere eine zweite Wahrheit.
    """

    analysis_run_id: uuid.UUID
    stock_id: uuid.UUID
    symbol: str
    exchange: str
    created_at: datetime
    evaluated_at: datetime
    screening_status: ScreeningStatus
    signal_rule_version: str

    company_name: str | None = None
    signals: tuple[SignalEvent, ...] = ()
    earnings: EarningsFilterResult | None = None
    backtest: tuple[BacktestResult, ...] = ()
    technical: TechnicalSnapshot | None = None
    technical_assessment: TechnicalAssessment | None = None
    research: ResearchReport | None = None
    fundamentals: FundamentalSnapshot | None = None

    swing_score: float | None = None
    investment_score: float | None = None
    recommendation: Recommendation | None = None
    summary: str | None = None
    """Die zusammenfassende Formulierung. Bleibt leer, solange der Bericht
    rein deterministisch entsteht -- sie ist Aufgabe der KI-Haelfte (ADR 0039,
    Entscheidung 4). Ein deterministisch zusammengesetzter Satz waere eine
    Formulierung ohne Verfasser."""

    gaps: tuple[ReportGap, ...] = ()
    sources: tuple[ReportSource, ...] = ()

    report_schema_version: str = REPORT_SCHEMA_VERSION
    app_version: str = ""
    scoring_version: str | None = None
    """Leer, bis es ein Scoring gibt (Sprint 5). Doc 10, Paragraph 8 verlangt
    die Version an jedem Ergebnis; sie hier vorzusehen und leer zu lassen ist
    ehrlicher, als sie zu erfinden."""

    missing_sections: frozenset[ReportSection] = field(default_factory=frozenset)

    @property
    def confidences(self) -> dict[str, float]:
        """Die Konfidenzangaben der Zulieferer, soweit vorhanden (Punkt 17).

        Bewusst **keine** Gesamtkonfidenz: Die drei Zahlen messen
        Verschiedenes -- Belegdichte, Sicherheit einer Einordnung, Anteil
        gerechneter Kennzahlen. Sie zu einer zu verrechnen ergaebe eine Zahl,
        die nichts bedeutet.
        """
        werte: dict[str, float] = {}
        if self.research is not None and self.research.confidence is not None:
            werte["research"] = self.research.confidence
        einordnung = self.technical_assessment
        if einordnung is not None and einordnung.confidence is not None:
            werte["technical_assessment"] = einordnung.confidence
        if self.fundamentals is not None:
            werte["fundamentals_coverage"] = self.fundamentals.coverage
        return werte
