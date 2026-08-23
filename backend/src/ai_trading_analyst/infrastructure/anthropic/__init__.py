"""KI-Anbindung ueber die Anthropic-API (ADR 0021, ADR 0023, ADR 0026).

Zwei Agenten mit sehr verschiedenem Zuschnitt: Der Research Agent fuehrt
einen mehrrundigen Werkzeugzyklus mit Websuche und Zitaten, der Technical
Agent eine einzelne Anfrage ohne Werkzeuge. Sie teilen sich das SDK und das
Muster (striktes Abschluss-Werkzeug, eigene Typpruefung, Ausweichmodell), aber
keinen Code -- der Zuschnitt ist zu unterschiedlich, als dass eine gemeinsame
Oberklasse mehr erklaeren wuerde als sie verbirgt.
"""

from .provider import (
    AnthropicResearchPricing,
    AnthropicResearchProvider,
    AnthropicResearchSettings,
)
from .technical_interpreter import (
    AnthropicTechnicalInterpreter,
    AnthropicTechnicalPricing,
    AnthropicTechnicalSettings,
)

__all__ = [
    "AnthropicResearchPricing",
    "AnthropicResearchProvider",
    "AnthropicResearchSettings",
    "AnthropicTechnicalInterpreter",
    "AnthropicTechnicalPricing",
    "AnthropicTechnicalSettings",
]
