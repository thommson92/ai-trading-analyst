"""Dauerhaft nutzbarer Testprovider fuer den Research Agent (ADR 0023).

Anders als beim Earnings-Filter gibt es hier kein sinnvoll variierbares
Szenario je Symbol (kein Datum, kein Vorlauf) -- der Fixture-Provider liefert
deshalb unabhaengig vom Symbol denselben deterministischen, vollstaendig
belegten Bericht. Das genuegt fuer Start und Tests ohne Anthropic-Zugang.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from ai_trading_analyst.domain.analysis import ResearchProvider, Stock
from ai_trading_analyst.domain.research import (
    Citation,
    ResearchReport,
    ResearchStatus,
    SourceLicenseClass,
)

_MODEL = "fixture"
_PROMPT_VERSION = "fixture-v1"


class FixtureResearchProvider(ResearchProvider):
    """Implementiert ``ResearchProvider`` ausschliesslich mit Fixture-Daten."""

    def __init__(self, now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._now = now

    def research(self, stock: Stock) -> ResearchReport:
        evaluated_at = self._now()
        return ResearchReport(
            status=ResearchStatus.COMPLETED,
            evaluated_at=evaluated_at,
            model=_MODEL,
            prompt_version=_PROMPT_VERSION,
            summary=f"Fixture-Recherche fuer {stock.symbol} -- keine echte Anbieteranfrage.",
            positive_factors=("Beispielhafter positiver Faktor",),
            negative_factors=("Beispielhafter negativer Faktor",),
            risks=("Beispielhaftes Risiko",),
            confidence=0.5,
            citations=(
                Citation(
                    url=f"https://example.com/fixture/{stock.symbol}",
                    title=f"Fixture-Quelle fuer {stock.symbol}",
                    retrieved_at=evaluated_at,
                    cited_text="Beispielhafter zitierter Ausschnitt.",
                    license_class=SourceLicenseClass.UNKNOWN,
                    transformation="zusammengefasst",
                ),
            ),
        )
