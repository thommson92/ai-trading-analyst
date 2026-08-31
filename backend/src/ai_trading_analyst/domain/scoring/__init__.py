"""Die beiden Scores (Doc 09; ADR 0041, ADR 0045).

Reine Funktionen ueber bereits gerechnete Teilergebnisse. Kein Teilwert
entsteht aus Freitext, und keine Zahl wird erfunden: Was fehlt, fehlt, und
die uebrigen Gewichte werden darauf umgerechnet.
"""

from .aggregate import aggregate
from .long_term import KENNZAHLEN_JE_KOMPONENTE, SCORED_METRICS, compute_long_term_score
from .parameters import MetricThresholds, RecommendationParameters, ScoringParameters
from .recommendation import RecommendationResult, derive_recommendation
from .swing import (
    ANALYST_BUY_SHARE_LABEL,
    SIGNAL_TEILWERTE,
    analyst_buy_share,
    compute_swing_score,
)
from .values import (
    RANGFOLGE,
    ComponentName,
    Recommendation,
    ScoreComponent,
    ScoreConfidence,
    ScoreKind,
    ScoreResult,
    ScoreStatus,
)

__all__ = [
    "ANALYST_BUY_SHARE_LABEL",
    "KENNZAHLEN_JE_KOMPONENTE",
    "RANGFOLGE",
    "SCORED_METRICS",
    "SIGNAL_TEILWERTE",
    "ComponentName",
    "MetricThresholds",
    "Recommendation",
    "RecommendationParameters",
    "RecommendationResult",
    "ScoreComponent",
    "ScoreConfidence",
    "ScoreKind",
    "ScoreResult",
    "ScoreStatus",
    "ScoringParameters",
    "aggregate",
    "analyst_buy_share",
    "compute_long_term_score",
    "compute_swing_score",
    "derive_recommendation",
]
