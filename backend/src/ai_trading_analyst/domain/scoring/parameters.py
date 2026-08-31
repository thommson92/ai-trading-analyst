"""Die Stellschrauben des Scorings, aus ``ScoringConfig`` gebaut (bootstrap.py).

Muster ``BacktestParameters``: Die Domain rechnet, kennt aber keine
Konfigurationsdatei. Was hier steht, ist gemessen (die Schwellen, ADR 0045)
oder gesetzt (Gewichte und Abdeckungsgrenzen, ADR 0041) -- in beiden Faellen
aenderbar, ohne diese Datei anzufassen.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ai_trading_analyst.domain.fundamentals import MetricName

from .values import RANGFOLGE, ComponentName, Recommendation

_STUFEN = (2.0, 4.0, 6.0, 8.0, 10.0)
"""Die fuenf Teilwerte, aufsteigend (ADR 0045, Entscheidung 1).

Das unterste Fuenftel bekommt **2 und nicht 0**: Ein Titel im untersten
Fuenftel der Nettomarge hat trotzdem eine Nettomarge.
"""


@dataclass(frozen=True, slots=True)
class MetricThresholds:
    """Die vier Fuenftelgrenzen einer Kennzahl und ihre Richtung.

    ``higher_is_better`` ist ein Pflichtfeld und kein Default: Bei KGV, KUV,
    Kurs/FCF, Verschuldungsgrad und Verwaesserung ist **niedriger** besser,
    und ein vergessener Schalter kehrte die Bewertung stillschweigend um.
    """

    boundaries: tuple[float, float, float, float]
    higher_is_better: bool

    def __post_init__(self) -> None:
        if list(self.boundaries) != sorted(self.boundaries):
            raise ValueError(f"Fuenftelgrenzen muessen aufsteigen, gegeben sind {self.boundaries}")

    def score(self, value: float) -> float:
        """Der Teilwert zwischen 2 und 10 fuer einen gemessenen Wert.

        Bei aufsteigender Richtung faellt ein Wert **auf** einer Grenze in
        das obere Fuenftel, bei absteigender in das bessere -- die Grenzen
        selbst sind gemessene Werte der Watchliste und gehoeren nicht in das
        schlechtere Feld.
        """
        if self.higher_is_better:
            hoehere = sum(1 for grenze in self.boundaries if value >= grenze)
            return _STUFEN[hoehere]
        niedrigere = sum(1 for grenze in self.boundaries if value > grenze)
        return _STUFEN[len(self.boundaries) - niedrigere]


@dataclass(frozen=True, slots=True)
class RecommendationParameters:
    """Die Stellschrauben der Empfehlungsstufe (ADR 0046).

    Alles hier ist **gesetzt, nicht gemessen** -- eine Empfehlung liesse sich
    erst an realisierten Ausgaengen kalibrieren, und die gibt es nicht. Die
    Stufengrenzen sind immerhin nicht geraten, sondern von der Skala
    abgelesen, aus der der Swing-Score gebaut ist (2/4/6/8/10, ADR 0045).
    """

    strong_candidate: float
    candidate: float
    watch: float
    investment_strong: float
    """Ab hier hebt der Investment-Score die Stufe um eine."""
    investment_weak: float
    """Bis hier senkt er sie um eine."""
    cap_false_signal_high: Recommendation
    cap_earnings_unknown: Recommendation
    version: str

    def __post_init__(self) -> None:
        if not self.strong_candidate > self.candidate > self.watch:
            raise ValueError(
                "Die Stufengrenzen muessen fallen: strong_candidate > candidate > watch, "
                f"gegeben sind {self.strong_candidate}, {self.candidate}, {self.watch}"
            )
        if self.investment_weak >= self.investment_strong:
            raise ValueError(
                "investment_weak muss unter investment_strong liegen, sonst hoebe und "
                "senkte derselbe Wert die Stufe zugleich"
            )
        for grenze in (self.cap_false_signal_high, self.cap_earnings_unknown):
            if grenze not in RANGFOLGE:
                raise ValueError(
                    f"{grenze} taugt nicht als Obergrenze -- INSUFFICIENT_DATA ist keine "
                    "schlechtere Stufe, sondern gar keine"
                )


@dataclass(frozen=True, slots=True)
class ScoringParameters:
    """Gewichte, Grenzen und Schwellen beider Scores."""

    swing_weights: Mapping[ComponentName, float]
    long_term_weights: Mapping[ComponentName, float]
    thresholds: Mapping[MetricName, MetricThresholds]
    analyst_buy_share: MetricThresholds
    """Die Schwellen der News-Komponente (ADR 0046). Ein eigenes Feld und
    kein Eintrag in ``thresholds``: Der Kauf-Anteil ist keine
    ``MetricName`` -- er stammt nicht aus einer SEC-Einreichung, sondern aus
    einer gezaehlten Votenverteilung."""
    analyst_max_age_days: int
    """Aelter darf der juengste Monatsstand der Analystenvoten nicht sein
    (ADR 0046). Gesetzt: Die Voten erscheinen monatlich, zwei ausgefallene
    Staende sind keine Abdeckung mehr."""
    minimum_coverage: float
    """Unterhalb dieser Datenabdeckung entsteht kein Score, sondern
    ``INSUFFICIENT_DATA`` (Doc 09). Gesetzt, nicht gemessen."""
    normal_confidence_coverage: float
    """Ab dieser Abdeckung gilt der Score als ``NORMAL`` belastbar, darunter
    als ``LOW_COVERAGE``. Muster ``normal_confidence_sample_size`` im
    Backtesting."""
    recommendation: RecommendationParameters
    swing_version: str
    long_term_version: str

    def __post_init__(self) -> None:
        if self.normal_confidence_coverage < self.minimum_coverage:
            raise ValueError(
                "normal_confidence_coverage darf nicht kleiner als minimum_coverage sein"
            )

