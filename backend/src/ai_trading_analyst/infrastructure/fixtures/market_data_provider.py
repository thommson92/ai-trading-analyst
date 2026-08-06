"""Dauerhaft nutzbarer Testprovider auf Basis versionierter JSON-Fixtures.

Liefert deterministische, vom aktuellen Datum unabhaengige Kerzenserien fuer
vier Szenarien (siehe ``data/v1/stocks.json``): ein qualifizierter Kandidat,
ein Nicht-Kandidat, eine Aktie mit ``UNKNOWN_DATA_INCOMPLETE`` und eine
Aktie, deren Verarbeitung einen kontrollierten Providerfehler erzeugt.

Jede Kerzenserie besteht aus einer "Baseline", die fuer sich genommen nie ein
Signal ausloest (RSI==RSI-MA, EMA5==EMA20, Kurs==EMA20 -- Gleichheit ist auf
der Vorkerze zulaessig, aber nirgends eine strikte Ueberschreitung). Die
Fixture-Definition ueberschreibt gezielt einzelne Kerzen, um genau das
gewuenschte Szenario zu erzeugen -- dasselbe Prinzip wie in den
Domain-Unit-Tests (``tests/unit/domain/screening/conftest.py``), hier aber
als Produktionscode dauerhaft nutzbar.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib import resources
from typing import Any

from ai_trading_analyst.domain.analysis import MarketDataProvider, MarketDataProviderError, Stock
from ai_trading_analyst.domain.screening import Candle, CandleSeries, IndicatorValues

_FIXTURE_PACKAGE = "ai_trading_analyst.infrastructure.fixtures.data.v1"
_FIXTURE_FILE = "stocks.json"
_EPOCH = datetime(2024, 1, 2, 12, 45, tzinfo=UTC)
_TIMEFRAME = timedelta(minutes=195)
_BASELINE = IndicatorValues(rsi=50.0, rsi_ma=50.0, ema5=100.0, ema20=100.0)
_STOCK_NAMESPACE = uuid.UUID("f6a1b2c3-0000-4000-8000-000000000001")


@dataclass(frozen=True, slots=True)
class _StockFixture:
    symbol: str
    exchange: str
    scenario: str
    indicator_overrides: dict[int, IndicatorValues]
    candle_overrides: dict[int, dict[str, float]]
    error_message: str | None


def _stock_id(symbol: str) -> uuid.UUID:
    return uuid.uuid5(_STOCK_NAMESPACE, symbol)


def _load_fixture_document() -> dict[str, Any]:
    raw = resources.files(_FIXTURE_PACKAGE).joinpath(_FIXTURE_FILE).read_text(encoding="utf-8")
    document: dict[str, Any] = json.loads(raw)
    return document


def _parse_indicator_overrides(raw: dict[str, Any]) -> dict[int, IndicatorValues]:
    return {
        int(index): IndicatorValues(
            rsi=values.get("rsi", _BASELINE.rsi),
            rsi_ma=values.get("rsi_ma", _BASELINE.rsi_ma),
            ema5=values.get("ema5", _BASELINE.ema5),
            ema20=values.get("ema20", _BASELINE.ema20),
        )
        for index, values in raw.items()
    }


class FixtureMarketDataProvider(MarketDataProvider):
    """Implementiert ``MarketDataProvider`` ausschliesslich mit Fixture-Daten."""

    def __init__(self) -> None:
        document = _load_fixture_document()
        self._series_length: int = document["series_length"]
        self._fixtures: dict[str, _StockFixture] = {
            entry["symbol"]: _StockFixture(
                symbol=entry["symbol"],
                exchange=entry["exchange"],
                scenario=entry["scenario"],
                indicator_overrides=_parse_indicator_overrides(
                    entry.get("indicator_overrides", {})
                ),
                candle_overrides={
                    int(index): values
                    for index, values in entry.get("candle_overrides", {}).items()
                },
                error_message=entry.get("error_message"),
            )
            for entry in document["stocks"]
        }

    def list_stocks(self) -> Sequence[Stock]:
        return tuple(
            Stock(id=_stock_id(fixture.symbol), symbol=fixture.symbol, exchange=fixture.exchange)
            for fixture in self._fixtures.values()
        )

    def get_candle_series(self, stock: Stock) -> CandleSeries:
        fixture = self._fixtures.get(stock.symbol)
        if fixture is None:
            raise MarketDataProviderError(
                f"Keine Fixture-Daten fuer Symbol '{stock.symbol}' hinterlegt."
            )

        if fixture.scenario == "provider_error":
            raise MarketDataProviderError(fixture.error_message or "Simulierter Providerfehler.")

        candles = tuple(self._build_candle(i, fixture) for i in range(self._series_length))
        indicators = tuple(
            fixture.indicator_overrides.get(i, _BASELINE) for i in range(self._series_length)
        )
        return CandleSeries(candles=candles, indicators=indicators)

    @staticmethod
    def _build_candle(index: int, fixture: _StockFixture) -> Candle:
        overrides = fixture.candle_overrides.get(index, {})
        close = overrides.get("close", 100.0)
        return Candle(
            timestamp=_EPOCH + index * _TIMEFRAME,
            daily_candle_index=1 if index % 2 == 0 else 2,
            open=overrides.get("open", 100.0),
            high=max(overrides.get("open", 100.0), close, 100.0),
            low=min(overrides.get("open", 100.0), close, 100.0),
            close=close,
            volume=1_000.0,
        )
