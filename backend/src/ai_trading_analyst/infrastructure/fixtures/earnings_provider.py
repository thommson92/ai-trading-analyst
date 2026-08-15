"""Dauerhaft nutzbarer Testprovider fuer den Earnings-Filter (ADR 0020).

Wie ``FixtureMarketDataProvider`` bewusst nicht an ein festes Kalenderdatum
gebunden: Jedes Symbol wird ueber einen Handelstage-Vorlauf ab
``reference_date`` definiert, nicht ueber ein absolutes Datum. Das Szenario
(ausgeschlossen/frei/ohne Abdeckung/Providerfehler) bleibt so stabil, auch
wenn sich ``reference_date`` verschiebt.

Symbole ohne Eintrag ergeben ``None`` (keine Abdeckung) -- ein Fixture-Lauf
kommt so mit jeder Watchlist zurecht, ohne dass jedes Symbol eingetragen sein
muss.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from importlib import resources
from typing import Any

from ai_trading_analyst.domain.analysis import EarningsProvider, EarningsProviderError, Stock
from ai_trading_analyst.domain.earnings import NextEarningsDate

_FIXTURE_PACKAGE = "ai_trading_analyst.infrastructure.fixtures.data.v1"
_FIXTURE_FILE = "earnings.json"
_SOURCE_NAME = "fixture"


@dataclass(frozen=True, slots=True)
class _EarningsFixture:
    symbol: str
    trading_days_offset: int | None
    error_message: str | None


def _load_fixture_document() -> dict[str, Any]:
    raw = resources.files(_FIXTURE_PACKAGE).joinpath(_FIXTURE_FILE).read_text(encoding="utf-8")
    document: dict[str, Any] = json.loads(raw)
    return document


def _advance_trading_days(reference: date, trading_days: int) -> date:
    """Kehrt ``count_future_trading_candles`` um: das Datum, das ``trading_days``
    Wochentage nach ``reference`` liegt (Wochenenden uebersprungen, ADR 0020)."""
    current = reference
    remaining = trading_days
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


class FixtureEarningsProvider(EarningsProvider):
    """Implementiert ``EarningsProvider`` ausschliesslich mit Fixture-Daten."""

    def __init__(self, reference_date: Callable[[], date] = date.today) -> None:
        document = _load_fixture_document()
        self._reference_date = reference_date
        self._fixtures: dict[str, _EarningsFixture] = {
            entry["symbol"]: _EarningsFixture(
                symbol=entry["symbol"],
                trading_days_offset=entry.get("trading_days_offset"),
                error_message=entry.get("error_message"),
            )
            for entry in document["stocks"]
        }

    def next_earnings_date(self, stock: Stock) -> NextEarningsDate | None:
        fixture = self._fixtures.get(stock.symbol)
        if fixture is None:
            return None

        if fixture.error_message is not None:
            raise EarningsProviderError(fixture.error_message)

        if fixture.trading_days_offset is None:
            return None

        reference = self._reference_date()
        earnings_date = _advance_trading_days(reference, fixture.trading_days_offset)
        return NextEarningsDate(
            date=earnings_date, source=_SOURCE_NAME, retrieved_at=datetime.now(UTC)
        )
