"""Testbausteine fuer die historische Signalpruefung.

Im Unterschied zu ``tests/unit/domain/screening/conftest.py`` alterniert
``daily_candle_index`` hier automatisch (Index 0, 2, 4, ... = erste
Tageskerze) -- fuer den Replay ist genau das die massgebliche Groesse.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ai_trading_analyst.domain.screening import Candle, CandleSeries, IndicatorValues

_EPOCH = datetime(2024, 1, 1, tzinfo=UTC)
_TIMEFRAME = timedelta(minutes=195)

BASELINE = IndicatorValues(rsi=50.0, rsi_ma=50.0, ema5=100.0, ema20=100.0)
RSI_AND_EMA_CROSS_FIRE = IndicatorValues(rsi=60.0, rsi_ma=50.0, ema5=110.0, ema20=100.0)


def make_series(
    length: int,
    *,
    indicator_overrides: dict[int, IndicatorValues] | None = None,
    closes: dict[int, float] | None = None,
) -> CandleSeries:
    indicator_overrides = indicator_overrides or {}
    closes = closes or {}
    candles = tuple(
        Candle(
            timestamp=_EPOCH + i * _TIMEFRAME,
            daily_candle_index=1 if i % 2 == 0 else 2,
            open=closes.get(i, 100.0),
            high=closes.get(i, 100.0),
            low=closes.get(i, 100.0),
            close=closes.get(i, 100.0),
            volume=1_000.0,
        )
        for i in range(length)
    )
    indicators = tuple(indicator_overrides.get(i, BASELINE) for i in range(length))
    return CandleSeries(candles=candles, indicators=indicators)
