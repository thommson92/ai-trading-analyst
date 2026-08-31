"""Dauerhaft nutzbarer Testprovider fuer die Analystenempfehlungen (ADR 0043).

Wie ``FixtureEarningsProvider`` bewusst nicht an feste Kalenderdaten
gebunden: Jeder Monatsstand ist ueber ``months_ago`` relativ zum
Bezugsmonat definiert. Das Szenario bleibt so stabil, auch wenn die Zeit
weiterlaeuft.

Die Verteilungen der vier Fixture-Symbole sind absichtlich **verschieden** --
eine steigende Zustimmung, eine ueberwiegend ablehnende, eine sehr duenn
besetzte und ein Providerfehler. Gleichfoermige Fixtures haben beim letzten
Mal zwei Berichtsmutationen gruen bleiben lassen; wo alle Werte gleich sind,
faellt eine Verwechslung nicht auf.

Symbole ohne Eintrag ergeben ``UNKNOWN`` mit Grund ``no_coverage`` -- ein
Fixture-Lauf kommt so mit jeder Watchlist zurecht.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from importlib import resources
from typing import Any

from ai_trading_analyst.domain.analysis import (
    AnalystRecommendationsProvider,
    AnalystRecommendationsProviderError,
    Stock,
)
from ai_trading_analyst.domain.analysts import (
    AnalystRecommendations,
    AnalystRecommendationStatus,
    RecommendationPeriod,
)

_FIXTURE_PACKAGE = "ai_trading_analyst.infrastructure.fixtures.data.v1"
_FIXTURE_FILE = "analyst_recommendations.json"
_SOURCE_NAME = "fixture"
_SOURCE_URL = "https://example.com/fixture/analyst-recommendations"
"""Keine echte Adresse -- dieselbe Konvention wie beim
Fixture-Research-Anbieter. Der Bericht darf Fixture-Zahlen nicht mit der
Adresse des echten Dienstes belegen."""


@dataclass(frozen=True, slots=True)
class _RecommendationFixture:
    symbol: str
    periods: tuple[dict[str, int], ...]
    error_message: str | None


def _load_fixture_document() -> dict[str, Any]:
    raw = resources.files(_FIXTURE_PACKAGE).joinpath(_FIXTURE_FILE).read_text(encoding="utf-8")
    document: dict[str, Any] = json.loads(raw)
    return document


def _month_start_before(reference: date, months_ago: int) -> date:
    """Der Monatserste, der ``months_ago`` Monate vor ``reference`` liegt.

    Finnhub gibt seine Monatsstaende als Monatserste aus; das Fixture bildet
    das nach, damit ein Wechsel vom Fixture zum echten Anbieter nicht
    plotzlich ein anderes Datumsformat liefert.
    """
    month_index = reference.year * 12 + (reference.month - 1) - months_ago
    return date(month_index // 12, month_index % 12 + 1, 1)


class FixtureAnalystRecommendationsProvider(AnalystRecommendationsProvider):
    """Implementiert ``AnalystRecommendationsProvider`` mit Fixture-Daten."""

    def __init__(self, reference_date: Callable[[], date] = date.today) -> None:
        document = _load_fixture_document()
        self._reference_date = reference_date
        self._fixtures: dict[str, _RecommendationFixture] = {
            entry["symbol"]: _RecommendationFixture(
                symbol=entry["symbol"],
                periods=tuple(entry.get("periods", ())),
                error_message=entry.get("error_message"),
            )
            for entry in document["stocks"]
        }

    def recommendations(self, stock: Stock) -> AnalystRecommendations:
        evaluated_at = datetime.now(UTC)
        fixture = self._fixtures.get(stock.symbol)

        # Der Fehlerfall zuerst: Das Fehlerfixture hat naturgemaess keine
        # Monatsstaende, und in der umgekehrten Reihenfolge liefe es
        # stillschweigend als "keine Abdeckung" durch, statt zu werfen.
        if fixture is not None and fixture.error_message is not None:
            raise AnalystRecommendationsProviderError(fixture.error_message)

        if fixture is None or not fixture.periods:
            return AnalystRecommendations(
                status=AnalystRecommendationStatus.UNKNOWN,
                evaluated_at=evaluated_at,
                source=_SOURCE_NAME,
                source_url=_SOURCE_URL,
                retrieved_at=evaluated_at,
                reason="no_coverage",
            )

        reference = self._reference_date()
        periods = tuple(
            RecommendationPeriod(
                period=_month_start_before(reference, entry["months_ago"]),
                strong_buy=entry["strong_buy"],
                buy=entry["buy"],
                hold=entry["hold"],
                sell=entry["sell"],
                strong_sell=entry["strong_sell"],
            )
            for entry in fixture.periods
        )
        return AnalystRecommendations(
            status=AnalystRecommendationStatus.COMPLETED,
            evaluated_at=evaluated_at,
            periods=periods,
            source=_SOURCE_NAME,
            source_url=_SOURCE_URL,
            retrieved_at=evaluated_at,
        )
