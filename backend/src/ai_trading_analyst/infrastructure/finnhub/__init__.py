"""Finnhub-Adapter: Earnings-Kalender (ADR 0017, ADR 0020) und
Analystenempfehlungen (ADR 0043).

Ein Konto, ein Schluessel, ein Host -- zwei Endpunkte in zwei Modulen, weil
sie weder Antwortformat noch Plausibilitaetsschranke teilen.
"""

from .provider import (
    FinnhubConnectionSettings,
    FinnhubEarningsProvider,
    FinnhubEarningsProviderError,
)
from .recommendations import (
    FinnhubAnalystRecommendationsProvider,
    FinnhubAnalystRecommendationsProviderError,
    FinnhubRecommendationSettings,
)

__all__ = [
    "FinnhubAnalystRecommendationsProvider",
    "FinnhubAnalystRecommendationsProviderError",
    "FinnhubConnectionSettings",
    "FinnhubEarningsProvider",
    "FinnhubEarningsProviderError",
    "FinnhubRecommendationSettings",
]
