"""Deterministische Chartauswertung (Doc 10, Paragraph 6.8; ADR 0025).

Die deterministische Haelfte des Technical Analysis Module. Getrennt von
``domain.screening``: Dort liegen die unter Gate G1 freigegebenen
Signalformeln, die ueber Kandidat oder Nichtkandidat entscheiden -- hier
entsteht nur die Beschreibung der Lage, in der diese Entscheidung gefallen
ist. Nichts aus diesem Modul fliesst in eine Signalentscheidung zurueck.
"""

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
    "PriceZone",
    "SwingPoint",
    "TechnicalAnalysisParameters",
    "TechnicalSnapshot",
    "TechnicalStatus",
    "TrendDirection",
    "ZoneKind",
    "ZoneStrength",
    "average_true_range",
    "build_zones",
    "compute_technical_snapshot",
    "find_swing_points",
    "true_ranges",
]
