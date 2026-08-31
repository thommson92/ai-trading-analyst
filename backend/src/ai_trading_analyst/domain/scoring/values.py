"""Wertobjekte der beiden Scores (Doc 09; Doc 10, Paragraph 6.11).

Reine Rechnung ohne Infrastruktur und ohne Sprachmodell. Was hier ankommt,
ist bereits gerechnet oder bereits als Enum eingestuft -- **kein Teilwert
entsteht aus Freitext** (CLAUDE.md: Scores werden nie direkt aus
LLM-Freitext uebernommen). Genau dafuer hat ADR 0026 die KI-Einordnung auf
Enums festgelegt.

Die Schwellen, mit denen aus einer Kennzahl ein Teilwert wird, stehen nicht
hier, sondern in der Konfiguration (ADR 0045). Sie sind gemessen und
aenderbar; die Zuordnung Kennzahl zu Komponente ist es nicht.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum


class ScoreKind(StrEnum):
    """Welche der beiden Fragen ein Ergebnis beantwortet (Doc 09).

    Zwei Werte und keine zwei Klassen: Aggregation, Umgewichtung und
    Mindestabdeckung sind fuer beide dieselben. Verschieden ist nur, woraus
    die Teilwerte kommen -- und das steht in ``swing.py`` und
    ``long_term.py``.
    """

    SWING = "SWING"
    LONG_TERM = "LONG_TERM"


class ScoreStatus(StrEnum):
    """Muster ``FundamentalStatus`` -- kein stilles Fehlen."""

    COMPLETED = "COMPLETED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    """Die verfuegbaren Komponenten decken weniger als die Mindestabdeckung
    ab. Dann entsteht **kein** Score (Doc 09): Eine Zahl aus zwei von sechs
    Komponenten saehe im Bericht wie eine vollstaendige aus."""


class ScoreConfidence(StrEnum):
    """Wie belastbar der Gesamtwert ist -- allein aus der Datenabdeckung.

    Bewusst dieselbe Dreiteilung wie ``BacktestConfidence``, und aus
    demselben Grund: Ein Ergebnis, das auf duenner Grundlage steht, ist nicht
    falsch, aber es ist etwas anderes als eines auf voller Grundlage. Die
    Grenze ist gesetzt und konfigurierbar (``scoring.normal_confidence_coverage``),
    nicht gemessen -- es gibt nichts, woran sie sich messen liesse.
    """

    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    LOW_COVERAGE = "LOW_COVERAGE"
    NORMAL = "NORMAL"


class ComponentName(StrEnum):
    """Die zehn Komponenten beider Scores (ADR 0041).

    Ein gemeinsames Enum und nicht zwei: Die Namen ueberschneiden sich
    nicht, und der Aggregator arbeitet fuer beide Scores gleich. Welche
    Komponente zu welchem Score gehoert, entscheidet der jeweilige Rechner.
    """

    TECHNICAL_SIGNALS = "TECHNICAL_SIGNALS"
    SIGNAL_STATISTICS = "SIGNAL_STATISTICS"
    CHART_SETUP = "CHART_SETUP"
    CHANCE_RISK = "CHANCE_RISK"
    NEWS_AND_EVENTS = "NEWS_AND_EVENTS"
    OPTIONS_ATTRACTIVENESS = "OPTIONS_ATTRACTIVENESS"

    PROFITABILITY = "PROFITABILITY"
    GROWTH = "GROWTH"
    VALUATION = "VALUATION"
    BALANCE_SHEET_QUALITY = "BALANCE_SHEET_QUALITY"


@dataclass(frozen=True, slots=True)
class ScoreComponent:
    """Ein Teilwert samt Gewicht und Begruendung.

    ``value`` ist ``None``, wenn die Komponente nicht verfuegbar ist -- und
    dann sagt ``reason``, warum. Eine fehlende Komponente mit 0 zu bewerten
    hiesse zu behaupten, sie sei geprueft und schlecht (Doc 09).
    """

    name: ComponentName
    weight: float
    """Das konfigurierte Gewicht, unabhaengig davon, ob die Komponente
    vorliegt. Es bleibt sichtbar, damit im Bericht steht, wie viel Gewicht
    eine Luecke gekostet hat."""
    value: float | None = None
    effective_weight: float = 0.0
    """Das auf die verfuegbaren Komponenten umgerechnete Gewicht. ``0.0`` bei
    fehlender Komponente und bei ``INSUFFICIENT_DATA``, wo nichts gerechnet
    wird."""
    reason: str | None = None
    """Worauf der Teilwert steht -- oder warum es keinen gibt. Der
    deterministische Begruendungsbaustein zu Doc 10, Paragraph 6.11: "Die
    Begruendung muss mit den Teilwerten uebereinstimmen"."""

    @property
    def available(self) -> bool:
        return self.value is not None

    def with_effective_weight(self, weight: float) -> ScoreComponent:
        return replace(self, effective_weight=weight)


@dataclass(frozen=True, slots=True)
class ScoreResult:
    """Ein fertiger Score mit allen neun Angaben aus Doc 10, Paragraph 6.11.

    Die Gewichtungen stehen an den Komponenten und nicht daneben: Zwei
    Listen, die zueinander passen muessen, laufen frueher oder spaeter
    auseinander.
    """

    kind: ScoreKind
    status: ScoreStatus
    version: str
    components: tuple[ScoreComponent, ...]
    coverage: float
    confidence: ScoreConfidence
    value: float | None = None
    positive_factors: tuple[str, ...] = ()
    negative_factors: tuple[str, ...] = ()
    limiting_risks: tuple[str, ...] = ()
    """Befunde, die den Score begrenzen oder eine Komponente haben entfallen
    lassen (Doc 09 "Begrenzende Risiken"). Heute setzt sie allein die
    Konfidenz der Signalstatistik (ADR 0045, Abschnitt 4); die uebrigen
    Kandidaten folgen mit der Empfehlungsstufe (ADR 0046)."""

    def __post_init__(self) -> None:
        if (self.value is None) != (self.status is ScoreStatus.INSUFFICIENT_DATA):
            raise ValueError(
                f"{self.kind}: Status {self.status} und Gesamtwert {self.value} passen nicht "
                "zusammen -- ein Score ohne Zahl ist INSUFFICIENT_DATA, und umgekehrt"
            )

    @property
    def missing_components(self) -> tuple[ComponentName, ...]:
        """Was nicht eingehen konnte -- ausdruecklich, nicht durch
        Abwesenheit (CLAUDE.md: keine stille Auslassung)."""
        return tuple(k.name for k in self.components if not k.available)
