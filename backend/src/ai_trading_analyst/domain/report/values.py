"""Werte des Analyseberichts (Doc 10, Paragraph 6.12; ADR 0039).

Der Bericht **erzeugt keine neuen Fakten**. Er ordnet gespeicherte
Analyseergebnisse den achtzehn Pflichtpunkten zu und traegt ausdruecklich
ein, was fehlt -- statt einen Punkt stillschweigend wegzulassen.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from ai_trading_analyst.domain.analysts import AnalystRecommendations
from ai_trading_analyst.domain.backtesting import BacktestResult
from ai_trading_analyst.domain.earnings import EarningsFilterResult
from ai_trading_analyst.domain.fundamentals import FundamentalSnapshot
from ai_trading_analyst.domain.research import ResearchReport
from ai_trading_analyst.domain.scoring import ScoreResult
from ai_trading_analyst.domain.screening import ScreeningStatus, SignalEvent
from ai_trading_analyst.domain.technical import TechnicalAssessment, TechnicalSnapshot

REPORT_SCHEMA_VERSION = "report-v2"
"""Fassung des Berichtsschemas (Doc 10, Paragraph 8).

Sie steigt, wenn sich Zuschnitt oder Bedeutung der Abschnitte aendert -- nicht,
wenn ein Zulieferer neue Zahlen liefert. Dessen eigene Version steht ohnehin
am jeweiligen Teilergebnis.

``report-v1`` fuehrte alle achtzehn Punkte, vier davon zwangslaeufig als
Luecke: Optionsanalyse und Scoring gehoerten zu Sprint 5. **Fuer diese vier
gilt die Regel weiter** -- wenn sie kommen, fuellen sich Luecken, und die
Version steigt davon nicht.

``report-v2`` (ADR 0043) ist ein anderer Fall: Punkt 9 hat seine Nutzlast
nicht gefuellt, sondern **ausgetauscht**. Er trug
``{positive_faktoren, negative_faktoren, kursziele}`` aus der Recherche und
traegt jetzt ``{empfehlungen, kursziele}`` aus einer gezaehlten
Votenverteilung. Dazu kommt in Punkt 18 die Quellenart ``ANALYSTS``.

Das Dokument wird unveraenderlich gespeichert. Bliebe die Nummer stehen,
laegen unter **einer** Version zwei nicht vereinbare Nutzlasten desselben
Abschnitts, und wer die Berichte spaeter auswertet, koennte sie nicht
auseinanderhalten. Genau dafuer gibt es das Feld.
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
    ANALYSTS = "ANALYSTS"
    """Die Analystenempfehlungen (ADR 0043).

    Eine eigene Art und nicht ``RESEARCH``: Die Verteilung ist **gezaehlt,
    nicht recherchiert**. Wer die Herkunft einer Berichtsaussage prueft, muss
    sehen, dass hier kein Sprachmodell beteiligt war. Als Adresse steht der
    Endpunkt selbst -- er ist die tatsaechliche Herkunft, auch wenn er ohne
    Zugangsschluessel nicht abrufbar ist."""


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
class StoredReport:
    """Ein gespeicherter Bericht, so wie er geschrieben wurde.

    Beim Lesen kommt **das Dokument** zurueck und kein rekonstruiertes
    ``StockReport``. Das ist Absicht: Das Dokument ist die verbindliche
    Fassung (ADR 0039, Entscheidung 4). Es beim Lesen wieder in Domain-Objekte
    zu zerlegen und daraus erneut ein Dokument zu bauen hiesse, einen
    abgeschlossenen Bericht durch heutigen Code laufen zu lassen -- genau das,
    was Doc 10, Paragraph 8 ausschliesst.

    Die Felder daneben sind die der Spalten: Sie beantworten die Fragen, fuer
    die man das Dokument nicht oeffnen muss.
    """

    symbol: str
    created_at: datetime
    report_schema_version: str
    app_version: str
    document: Mapping[str, Any]


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
    analysts: AnalystRecommendations | None = None

    swing_score: ScoreResult | None = None
    """Der vollstaendige Score und nicht nur seine Zahl.

    Doc 10, Paragraph 6.11 verlangt an jedem Score neun Angaben -- Teilwerte,
    Gewichtungen, Datenabdeckung, Konfidenz, Faktoren, begrenzende Risiken
    und Berechnungsversion. Eine blosse Zahl im Bericht waere genau die
    Scheingenauigkeit, die derselbe Absatz ausschliesst."""
    investment_score: ScoreResult | None = None
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
    """Die Versionen beider Scores in einem Feld (Doc 10, Paragraph 8).

    Sie stehen ohnehin an jedem ``ScoreResult``; hier zusammengefasst, weil
    Doc 10 die Berechnungsversion **am Bericht** verlangt und die beiden
    Scores getrennt versioniert sind (``swing_version`` steigt mit der
    Optionsanalyse, ``long_term_version`` mit einer Neumessung der
    Schwellen). Leer, wenn kein Score entstanden ist."""

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
