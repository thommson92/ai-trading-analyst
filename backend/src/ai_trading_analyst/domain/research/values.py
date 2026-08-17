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
    summary: str | None = None
    positive_factors: tuple[str, ...] = ()
    negative_factors: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    confidence: float | None = None
    citations: tuple[Citation, ...] = ()
    reason: str | None = None
    """Nur bei ``UNAVAILABLE``/``INSUFFICIENT_DATA`` gesetzt (Muster
    ``EarningsFilterResult.reason``): ``"provider_error"`` oder
    ``"insufficient_sources"``."""
