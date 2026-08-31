"""Die beiden Scores (Doc 09; ADR 0041, ADR 0045).

Reine Funktionen ueber bereits gerechnete Teilergebnisse. Kein Teilwert
entsteht aus Freitext, und keine Zahl wird erfunden: Was fehlt, fehlt, und
die uebrigen Gewichte werden darauf umgerechnet.
"""

from .aggregate import aggregate
from .long_term import KENNZAHLEN_JE_KOMPONENTE, SCORED_METRICS, compute_long_term_score
from .parameters import MetricThresholds, ScoringParameters
from .swing import SIGNAL_TEILWERTE, compute_swing_score
from .values import (
    ComponentName,
    ScoreComponent,
    ScoreConfidence,
    ScoreKind,
    ScoreResult,
    ScoreStatus,
)

__all__ = [
    "KENNZAHLEN_JE_KOMPONENTE",
    "SCORED_METRICS",
    "SIGNAL_TEILWERTE",
    "ComponentName",
    "MetricThresholds",
    "ScoreComponent",
    "ScoreConfidence",
    "ScoreKind",
    "ScoreResult",
    "ScoreStatus",
    "ScoringParameters",
    "aggregate",
    "compute_long_term_score",
    "compute_swing_score",
]
