"""Wertobjekte des Research Agent (Doc 06; Doc 10, Paragraph 6.7 und 10;
ADR 0021, ADR 0023).

Reines Python -- keine Infrastruktur, kein Anbieter. Der Domain Layer kennt
Anthropic nicht (Doc 10, Paragraph 9), nur ``ResearchProvider`` als Port
(``domain.analysis.ports``). Anders als bei Backtesting/Screening gibt es
hier keine eigene Berechnung -- der Adapter befuellt diese Werte direkt aus
der bereits strukturiert validierten Anbieterantwort.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class SourceLicenseClass(StrEnum):
    """Grobe Einordnung einer Zitatquelle (ADR 0023, Zitierarchitektur
    Punkt 6) -- deterministisch aus der URL bestimmt, nie vom Sprachmodell
    selbst erfragt (CLAUDE.md: Scores/Klassen nicht aus LLM-Freitext
    uebernehmen)."""

    PRIMARY_SOURCE = "PRIMARY_SOURCE"
    """SEC-Filing, Investor-Relations-Mitteilung o. Ae. -- ADR 0023 bevorzugt
    diese Klasse ausdruecklich vor sekundaerer Berichterstattung."""
    NEWS_MEDIA = "NEWS_MEDIA"
    UNKNOWN = "UNKNOWN"


class SourceRank(StrEnum):
    """Wie nah eine Quelle am Geschehen steht (ADR 0029).

    **Getrennt von** ``SourceLicenseClass``, obwohl beide aus der Domain
    entstehen: Die Lizenzklasse beantwortet, was mit dem Inhalt rechtlich
    geschehen darf; der Rang beantwortet, wie belastbar er ist. Eine
    Agenturmeldung kann urheberrechtlich heikel und trotzdem gut belegt sein
    -- ein Feld fuer beides haette eine der beiden Fragen verdraengt.

    Deterministisch aus der URL bestimmt, nie vom Sprachmodell erfragt
    (CLAUDE.md: Klassifikationen nicht aus LLM-Freitext uebernehmen).
    """

    REGULATORY = "REGULATORY"
    """Amtliche Einreichung oder Veroeffentlichung -- SEC, Notenbanken."""
    COMPANY = "COMPANY"
    """Das Unternehmen selbst: Investor Relations und die
    Original-Pressemitteilungsdienste, ueber die es meldet."""
    FINANCIAL_MEDIA = "FINANCIAL_MEDIA"
    """Fachpresse mit eigener Redaktion und Finanzschwerpunkt."""
    GENERAL_MEDIA = "GENERAL_MEDIA"
    """Nachrichtenagenturen und allgemeine Presse."""
    AGGREGATOR = "AGGREGATOR"
    """Portale und Meinungsplattformen, die ueberwiegend Fremdinhalte
    buendeln -- verwertbar, aber selten die Originalquelle."""
    UNRANKED = "UNRANKED"
    """Keiner bekannten Stufe zuzuordnen. Ausdruecklich **keine** Aussage
    ueber die Guete -- nur, dass wir sie nicht kennen."""


RANGFOLGE: tuple[SourceRank, ...] = (
    SourceRank.REGULATORY,
    SourceRank.COMPANY,
    SourceRank.FINANCIAL_MEDIA,
    SourceRank.GENERAL_MEDIA,
    SourceRank.AGGREGATOR,
    SourceRank.UNRANKED,
)
"""Von der belastbarsten Stufe zur schwaechsten.

Ausdrueckliche Konstante statt der Deklarationsreihenfolge des Enums: Eine
spaeter eingefuegte Stufe wuerde die Sortierung sonst still verschieben, ohne
dass ein Test darauf zeigt.
"""


def rangindex(rank: SourceRank) -> int:
    """Position in ``RANGFOLGE`` -- kleiner ist belastbarer."""
    return RANGFOLGE.index(rank)


class ResearchCoverage(StrEnum):
    """Wie breit ein Bericht tatsaechlich belegt ist (ADR 0029).

    Ausdruecklich **neben** ``ResearchStatus``, nicht darin: ``COMPLETED``
    sagt, dass der Lauf technisch durchgelaufen ist. Ein realer Lauf meldete
    ``COMPLETED`` mit einer einzigen Suche, null erfolgreichen Abrufen und
    acht abgelehnten Werkzeugaufrufen (ADR 0023) -- technisch zutreffend,
    inhaltlich duenn. Beides in ein Feld zu pressen haette einen der beiden
    Befunde verschwinden lassen.

    Deterministisch aus dem berechnet, was messbar geschehen ist -- nie aus
    einer Selbstauskunft des Modells.
    """

    BROAD = "BROAD"
    LIMITED = "LIMITED"
    THIN = "THIN"


class ResearchStatus(StrEnum):
    """Muster ``EarningsFilterStatus`` -- drei Werte, kein stilles Fehlen."""

    COMPLETED = "COMPLETED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    """Das Modell selbst meldet zu wenig belastbare Grundlage (Doc 10 Paragraph 10
    Halluzinationsschutz) -- kein erfundener Bericht statt fehlender Quellen."""
    UNAVAILABLE = "UNAVAILABLE"
    """Anbieterausfall (Muster ``EarningsFilterStatus.UNKNOWN``) -- blockiert
    nie die technische Analyse (CLAUDE.md, Doc 10)."""


@dataclass(frozen=True, slots=True)
class Citation:
    """Ein einzelner Beleg fuer eine Aussage im Bericht (ADR 0023,
    Zitierarchitektur Punkt 1/2/6) -- Rueckverfolgbarkeit bis zur
    Originalquelle, nicht nur eine Sammelquelle je Bericht."""

    url: str
    title: str
    retrieved_at: datetime
    """Eigene Abrufzeit, nicht die vom Anbieter gemeldete Aktualitaet der
    Quelle selbst."""
    cited_text: str | None
    license_class: SourceLicenseClass
    transformation: str
    """Wie die Quelle im Bericht verwendet wurde, z. B. "zusammengefasst"
    oder "aggregiert aus n Quellen" (ADR 0023, Zitierarchitektur Punkt 6)."""
    source_rank: SourceRank = SourceRank.UNRANKED
    """Belastbarkeit der Quelle (ADR 0029) -- getrennt von der Lizenzklasse."""
    source_age: str | None = None
    """Das vom Anbieter gemeldete Alter der Seite, **unveraendert uebernommen**
    (ADR 0029).

    Ausdruecklich nicht ``published_at``: Die Anthropic-API liefert bei
    Suchtreffern ``page_age`` als *relative* Angabe ("3 days ago"), bei
    Abrufen ueberhaupt kein Datum. Daraus ein Veroeffentlichungsdatum zu
    rechnen waere ein abgeleiteter Wert an einer Stelle, die Genauigkeit
    verspricht -- CLAUDE.md verbietet genau das. Der Rohwert wird gespeichert,
    nie geparst und fliesst in keine Berechnung ein.

    ``None`` bei Zitaten aus ``web_fetch`` und ueberall dort, wo der Anbieter
    nichts gemeldet hat."""


@dataclass(frozen=True, slots=True)
class ResearchEvidence:
    """Die Tatsachen, aus denen ``ResearchCoverage`` entsteht (ADR 0029).

    Sie werden mitgespeichert, nicht nur die Stufe: Eine Einstufung ohne die
    Zahlen dahinter waere ein weiteres undurchsichtiges Etikett, und ob eine
    Schwelle richtig gewaehlt war, laesst sich spaeter nur an den Rohwerten
    pruefen. Dasselbe Muster wie beim Backtest, der rohe und deduplizierte
    Stichprobengroesse beide ausweist.

    Nicht enthalten ist der beste erreichte Quellenrang -- er ist aus den
    gespeicherten Zitaten ablesbar. Die Deckelung entfernt die schwaechsten
    zuerst, der beste Rang ueberlebt sie also immer.
    """

    distinct_sources: int
    """Verschiedene zitierte URLs **vor** der Deckelung."""
    successful_fetches: int
    """Wie viele Dokumente tatsaechlich gelesen wurden. Der Unterschied
    zwischen einem Bericht aus Suchschnipseln und einem aus einem Filing."""
    rejected_tool_calls: int
    """Abgelehnte Werkzeugaufrufe (``max_uses_exceeded``, ``url_not_allowed``
    und Verwandte). Jeder davon hat den gesamten Kontext erneut verrechnet --
    laut ADR 0023 stand diese Diagnose bisher nur im Protokoll."""
    dropped_citations: int
    """Wie viele Zitate die Deckelung verworfen hat. Steht hier, damit die
    Auslassung nicht still bleibt."""


@dataclass(frozen=True, slots=True)
class ResearchReport:
    """Persistierbares Ergebnis des Research Agent samt Belegen.

    Deckt Doc 10 Paragraph 10 ("strukturierte Ausgaben") und Paragraph 12
    (Modell-/Prompt-Version an jedem Ergebnis) ab.
    """

    status: ResearchStatus
    evaluated_at: datetime
    model: str | None
    """``None`` nur bei ``UNAVAILABLE`` -- ein Anbieterausfall kann schon vor
    der Modellwahl auftreten (z. B. ein Authentifizierungsfehler)."""
    prompt_version: str | None
    analysis_version: str | None = None
    """Version der deterministischen Ableitung (Rang, Abdeckung, Deckelung).

    Getrennt von ``prompt_version``, weil beide sich unabhaengig aendern --
    Muster ``TechnicalAssessment.interpreted_analysis_version``. Ohne dieses
    Feld liesse sich ein gespeicherter ``coverage``-Wert nicht der Regel
    zuordnen, unter der er entstanden ist."""
    summary: str | None = None
    positive_factors: tuple[str, ...] = ()
    negative_factors: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    confidence: float | None = None
    citations: tuple[Citation, ...] = ()
    coverage: ResearchCoverage | None = None
    """Wie breit der Bericht belegt ist -- getrennt vom ``status`` (ADR 0029).

    ``None`` bei ``UNAVAILABLE``: Ein Anbieterausfall hat keine Abdeckung, und
    ``THIN`` waere dort eine Aussage ueber einen Bericht, den es nicht gibt."""
    evidence: ResearchEvidence | None = None
    """Die Zahlen hinter ``coverage``. Zusammen gesetzt oder zusammen ``None``."""
    reason: str | None = None
    """Nur bei ``UNAVAILABLE``/``INSUFFICIENT_DATA`` gesetzt (Muster
    ``EarningsFilterResult.reason``): ``"provider_error"``,
    ``"insufficient_sources"`` oder ``"provider_disabled"`` (der Betreiber
    hat den Agenten abgeschaltet, ``research.provider: none``)."""
