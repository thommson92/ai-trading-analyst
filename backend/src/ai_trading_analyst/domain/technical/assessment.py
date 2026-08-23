"""Die KI-Interpretation der Chartauswertung (Doc 10, Paragraph 6.8; ADR 0026).

Die zweite Haelfte des Technical Analysis Module. Doc 10 verlangt, dass
deterministische Berechnung und KI-Interpretation getrennt gespeichert
werden -- ``values.py`` ist die eine Haelfte, dieses Modul die andere. Es
haelt ausschliesslich Wertobjekte: Wie die Einordnung zustande kommt, weiss
allein der Adapter in der Infrastructure-Schicht (CLAUDE.md: Domain- und
Application-Code duerfen von keinem konkreten Modell abhaengen).

Die vier Einstufungen decken die sechs Punkte ab, die Doc 10, Paragraph 6.8
der KI zugesteht: Trendstaerke, Breakout-Qualitaet, ueberkauft/ueberverkauft
und Plausibilitaet eines Swing-Einstiegs als Enums, Fehlsignalrisiken als
Liste, das Chance-Risiko-Verhaeltnis als Kommentar zu der Zahl, die bereits
im ``TechnicalSnapshot`` steht.

**Kein Feld dieses Objekts enthaelt eine berechnete Groesse.** Ein
Sprachmodell darf erlaeutern und einordnen, aber keine deterministische
Berechnung ersetzen (CLAUDE.md, zentrale Regel). Das Verhaeltnis von Chance
und Risiko steht als Zahl im Snapshot; hier steht nur, wie es zu lesen ist.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class TechnicalAssessmentStatus(StrEnum):
    """Muster ``ResearchStatus`` -- drei Werte, kein stilles Fehlen."""

    COMPLETED = "COMPLETED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    """Es gab nichts einzuordnen: Die Chartauswertung war selbst
    ``INSUFFICIENT_DATA``, oder das Modell meldet die Grundlage als zu duenn
    (Doc 10, Paragraph 10, Halluzinationsschutz)."""
    UNAVAILABLE = "UNAVAILABLE"
    """Anbieterausfall. Anders als bei der deterministischen Auswertung ist
    dieser Wert hier noetig -- der Agent haengt an einer externen
    Schnittstelle. Er blockiert nie den Lauf (CLAUDE.md: Analysemodule sind
    entkoppelt)."""


class FalseSignalRisk(StrEnum):
    """Wie gross das Risiko ist, dass das erkannte Signal keines war."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RiskRewardRating(StrEnum):
    """Einstufung des **bereits berechneten** Chance-Risiko-Verhaeltnisses.

    Eine Einstufung und keine Zahl: Die Zahl steht im ``TechnicalSnapshot``
    und stammt aus der Zonengeometrie. Das Modell sagt nur, wie sie zu lesen
    ist.

    ``NOT_ASSESSABLE`` wird vom Adapter **erzwungen**, sobald
    ``TechnicalSnapshot.chance_risk_ratio`` fehlt -- unabhaengig davon, was
    das Modell geantwortet hat. Ohne diese Uebersteuerung koennte ein Modell
    ein Verhaeltnis einstufen, das gar nicht berechnet werden konnte, und die
    Einstufung saehe im Bericht wie eine gerechnete Aussage aus (CLAUDE.md:
    Scores werden nie direkt aus LLM-Freitext uebernommen).
    """

    FAVOURABLE = "FAVOURABLE"
    BALANCED = "BALANCED"
    UNFAVOURABLE = "UNFAVOURABLE"
    NOT_ASSESSABLE = "NOT_ASSESSABLE"


class TrendStrength(StrEnum):
    """Wie tragfaehig der im Snapshot festgestellte Trend ist.

    Bewusst getrennt von ``TrendDirection``: Die *Richtung* ist berechnet und
    steht fest, die *Staerke* ist die Einordnung dazu. Ein Sprachmodell darf
    die Richtung nicht umdeuten.
    """

    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK = "WEAK"
    ABSENT = "ABSENT"
    """Kein tragfaehiger Trend erkennbar. Ein eigener Wert und nicht
    ``None``: "es gibt keinen" ist ein Befund, "nicht beurteilbar" ist
    keiner."""


class BreakoutQuality(StrEnum):
    CONFIRMED = "CONFIRMED"
    TENTATIVE = "TENTATIVE"
    FAILED = "FAILED"
    NO_BREAKOUT = "NO_BREAKOUT"
    """Kein Ausbruch erkennbar -- ein eigener Wert und nicht ``None``: "es
    gibt keinen" ist ein Befund, "nicht beurteilbar" ist keiner."""


class MomentumState(StrEnum):
    OVERBOUGHT = "OVERBOUGHT"
    NEUTRAL = "NEUTRAL"
    OVERSOLD = "OVERSOLD"


class SwingEntryPlausibility(StrEnum):
    """Plausibilitaet eines Swing-Einstiegs (Doc 10, Paragraph 6.8).

    Ausdruecklich **keine** Handelsempfehlung und kein Signal: Ob eine Aktie
    Kandidat ist, entscheidet allein der deterministische Screener unter Gate
    G1. Dieser Wert sagt nur, ob die Chartlage zu einem Swing-Einstieg passt.
    """

    PLAUSIBLE = "PLAUSIBLE"
    QUESTIONABLE = "QUESTIONABLE"
    IMPLAUSIBLE = "IMPLAUSIBLE"


@dataclass(frozen=True, slots=True)
class TechnicalAssessment:
    """Die Einordnung einer Chartauswertung durch das Sprachmodell.

    Alle Inhaltsfelder sind bei ``INSUFFICIENT_DATA`` und ``UNAVAILABLE``
    leer beziehungsweise ``None``. Ein fehlender Wert bleibt fehlend
    (CLAUDE.md) -- kein Ersatztext, der sich im Bericht wie eine Einschaetzung
    liest.
    """

    status: TechnicalAssessmentStatus
    evaluated_at: datetime
    model: str | None
    """Das Modell, das tatsaechlich geantwortet hat -- auch wenn das
    Ausweichmodell einsprang (ADR 0021: die verwendete Modellversion gehoert
    an jedes Ergebnis, nicht nur ins Log). ``None``, wenn der Ausfall vor der
    Modellwahl eintrat."""
    prompt_version: str | None
    interpreted_analysis_version: str | None = None
    """Die Verfahrensversion der Chartauswertung, die eingeordnet wurde.

    Doc 10, Paragraph 12 verlangt fuer jede Empfehlung nachvollziehbar,
    welche Daten verwendet wurden. Steigt das deterministische Verfahren
    spaeter, bleibt an dieser Einordnung erkennbar, dass sie auf der
    aelteren Fassung beruht -- sonst laese man sie gegen Zahlen, die sie nie
    gesehen hat."""

    summary: str | None = None
    trend_strength: TrendStrength | None = None
    breakout_quality: BreakoutQuality | None = None
    momentum_state: MomentumState | None = None
    swing_entry_plausibility: SwingEntryPlausibility | None = None
    false_signal_risk: FalseSignalRisk | None = None
    risk_reward_rating: RiskRewardRating | None = None
    false_signal_risks: tuple[str, ...] = ()
    """Die einzelnen Risiken im Klartext, je Eintrag eines -- die Begruendung
    zu ``false_signal_risk``."""
    confidence: float | None = None
    """Selbsteinschaetzung des Modells zwischen 0 und 1, **kein** Score. Geht
    nie ungeprueft in eine Bewertung ein."""
    reason: str | None = None
    """Nur bei ``INSUFFICIENT_DATA``/``UNAVAILABLE``: etwa
    ``"snapshot_insufficient"``, ``"provider_error"``."""
