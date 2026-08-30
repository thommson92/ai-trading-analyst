"""Analystenempfehlungen: die gezaehlte Votenverteilung je Monatsstand
(Doc 10, Paragraph 6.12 Punkt 9; ADR 0043).

Bewusst ohne Kursziele -- sie bleiben dauerhaft zurueckgestellt, weil keine
Score-Komponente sie braucht und der Endpunkt kostenpflichtig ist
(ADR 0017 L5, ADR 0043).
"""

from .values import (
    ANALYST_ANALYSIS_VERSION,
    AnalystRecommendations,
    AnalystRecommendationStatus,
    RecommendationPeriod,
)

__all__ = [
    "ANALYST_ANALYSIS_VERSION",
    "AnalystRecommendationStatus",
    "AnalystRecommendations",
    "RecommendationPeriod",
]
