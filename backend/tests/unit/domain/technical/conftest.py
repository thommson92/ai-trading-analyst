"""Testbausteine der deterministischen Chartauswertung.

``series_from_prices`` baut Kerzen ohne eigene Spanne (Open == High == Low ==
Close). Damit liegt jede Kerze auf genau einem Preis, und Swing-Punkte,
Zonengrenzen und Beruehrungen lassen sich an der uebergebenen Zahlenreihe
direkt ablesen -- fuer Tests der Zonenbildung ist das die eindeutigere
Grundlage als realistisch geformte Kerzen.

``small_params()`` verkleinert alle Fenster so weit, dass eine Zahlenreihe von
einem Dutzend Werten reicht. Die Voreinstellungen aus ADR 0025 brauchen 40
Kerzen allein fuer die Extrempunkte; ein Test dagegen soll die Regel zeigen
und nicht eine lange Zahlenkolonne.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from ai_trading_analyst.domain.screening import Candle, CandleSeries, IndicatorValues
from ai_trading_analyst.domain.technical import TechnicalAnalysisParameters

EPOCH = datetime(2024, 1, 1, tzinfo=UTC)
TIMEFRAME = timedelta(minutes=195)


def timestamp_at(index: int) -> datetime:
    return EPOCH + index * TIMEFRAME


def candle_at(
    index: int,
    *,
    high: float,
    low: float,
    close: float | None = None,
    open_: float | None = None,
) -> Candle:
    return Candle(
        timestamp=timestamp_at(index),
        daily_candle_index=1 + index % 2,
        open=high if open_ is None else open_,
        high=high,
        low=low,
        close=low if close is None else close,
        volume=1_000.0,
    )


def series_from_prices(
    prices: Sequence[float],
    *,
    indicators: dict[int, IndicatorValues] | None = None,
) -> CandleSeries:
    """Serie ohne Kerzenspanne -- jede Kerze liegt auf genau einem Preis."""
    overrides = indicators or {}
    candles = tuple(
        candle_at(index, high=price, low=price, close=price, open_=price)
        for index, price in enumerate(prices)
    )
    values = tuple(
        overrides.get(index, IndicatorValues(rsi=None, rsi_ma=None, ema5=None, ema20=None))
        for index in range(len(prices))
    )
    return CandleSeries(candles=candles, indicators=values)


def series_from_ohlc(rows: Sequence[tuple[float, float, float]]) -> CandleSeries:
    """Serie aus ``(high, low, close)`` je Kerze -- fuer Spannen und Luecken."""
    candles = tuple(
        candle_at(index, high=high, low=low, close=close)
        for index, (high, low, close) in enumerate(rows)
    )
    values = tuple(
        IndicatorValues(rsi=None, rsi_ma=None, ema5=None, ema20=None) for _ in rows
    )
    return CandleSeries(candles=candles, indicators=values)


def small_params(**overrides: object) -> TechnicalAnalysisParameters:
    defaults: dict[str, object] = {
        "pivot_reach": 1,
        "zone_tolerance_pct": 0.01,
        "min_touches": 2,
        "moderate_touch_count": 3,
        "strong_touch_count": 4,
        "max_zones_per_side": 3,
        "history_candles": 100,
        "atr_length": 2,
        "trend_lookback": 2,
        "trend_flat_pct": 0.005,
        "extremes_lookback": 3,
    }
    defaults.update(overrides)
    return TechnicalAnalysisParameters(**defaults)  # type: ignore[arg-type]
