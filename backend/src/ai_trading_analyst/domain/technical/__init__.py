"""Deterministische Chartauswertung (Doc 10, Paragraph 6.8; ADR 0025).

Beide Haelften des Technical Analysis Module: die deterministische Auswertung
(``values``, ``zones``, ``snapshot``) und die Wertobjekte ihrer
KI-Interpretation (``assessment``, ADR 0026). Getrennt gespeichert, wie Doc
10, Paragraph 6.8 es verlangt, aber fachlich dasselbe Modul.

Getrennt von ``domain.screening``: Dort liegen die unter Gate G1
freigegebenen Signalformeln, die ueber Kandidat oder Nichtkandidat
entscheiden -- hier entsteht nur die Beschreibung der Lage, in der diese
Entscheidung gefallen ist. Nichts aus diesem Modul fliesst in eine
Signalentscheidung zurueck, auch nichts aus der Interpretation.
"""

from .assessment import (
    BreakoutQuality,
    FalseSignalRisk,
    MomentumState,
    RiskRewardRating,
    SwingEntryPlausibility,
    TechnicalAssessment,
    TechnicalAssessmentStatus,
    TrendStrength,
)
from .snapshot import average_true_range, compute_technical_snapshot, true_ranges
from .values import (
    TECHNICAL_ANALYSIS_VERSION,
    PriceZone,
    SwingPoint,
    TechnicalAnalysisParameters,
    TechnicalSnapshot,
    TechnicalStatus,
    TrendDirection,
    ZoneKind,
    ZoneStrength,
)
from .zones import build_zones, find_swing_points

__all__ = [
    "TECHNICAL_ANALYSIS_VERSION",
    "BreakoutQuality",
    "FalseSignalRisk",
    "MomentumState",
    "PriceZone",
    "RiskRewardRating",
    "SwingEntryPlausibility",
    "SwingPoint",
    "TechnicalAnalysisParameters",
    "TechnicalAssessment",
    "TechnicalAssessmentStatus",
    "TechnicalSnapshot",
    "TechnicalStatus",
    "TrendDirection",
    "TrendStrength",
    "ZoneKind",
    "ZoneStrength",
    "average_true_range",
    "build_zones",
    "compute_technical_snapshot",
    "find_swing_points",
    "true_ranges",
]
