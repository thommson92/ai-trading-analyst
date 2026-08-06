"""Testbausteine fuer den Signalkern.

``baseline_indicators()`` liefert absichtlich einen Zustand, in dem keines der
drei Signale feuert (Gleichheit auf allen Vergleichen). Ueberschreibt man nur
den Wert einer einzelnen Kerze ``i`` so, dass die Ueberschreitung strikt wird,
feuert das jeweilige Signal ausschliesslich an dieser Kerze -- die Vorkerze
erfuellt die (Gleichheit erlaubende) Vorbedingung bereits durch die Baseline.
Das haelt die Fenster-/Kandidatentests unabhaengig von den exakten
Zahlenbeispielen der G1-Pruefvorlage lesbar.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ai_trading_analyst.domain.screening import Candle, CandleSeries, IndicatorValues

_EPOCH = datetime(2024, 1, 1, tzinfo=UTC)
_TIMEFRAME = timedelta(minutes=195)


def make_candle(
    index: int,
    *,
    daily_candle_index: int = 1,
    open: float = 100.0,  # noqa: A002 -- Feldname aus dem Datenmodell (Doc 05)
    high: float = 100.0,
    low: float = 100.0,
    close: float = 100.0,
    volume: float = 1_000.0,
) -> Candle:
    return Candle(
        timestamp=_EPOCH + index * _TIMEFRAME,
        daily_candle_index=daily_candle_index,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def baseline_indicators() -> IndicatorValues:
    """Rsi==RsiMa und Ema5==Ema20: erfuellt jede Vorkerzen-Gleichheitsbedingung,
    feuert aber selbst nie (keine strikte Ueberschreitung auf der aktuellen Kerze)."""
    return IndicatorValues(rsi=50.0, rsi_ma=50.0, ema5=100.0, ema20=100.0)


def incomplete_indicators() -> IndicatorValues:
    return IndicatorValues(rsi=None, rsi_ma=None, ema5=None, ema20=None)


def build_series(
    length: int,
    *,
    indicator_overrides: dict[int, IndicatorValues] | None = None,
    candle_overrides: dict[int, Candle] | None = None,
) -> CandleSeries:
    indicator_overrides = indicator_overrides or {}
    candle_overrides = candle_overrides or {}
    candles = tuple(candle_overrides.get(i, make_candle(i)) for i in range(length))
    indicators = tuple(indicator_overrides.get(i, baseline_indicators()) for i in range(length))
    return CandleSeries(candles=candles, indicators=indicators)


def rsi_cross_fires() -> IndicatorValues:
    return IndicatorValues(rsi=60.0, rsi_ma=50.0, ema5=100.0, ema20=100.0)


def ema5_ema20_cross_fires() -> IndicatorValues:
    return IndicatorValues(rsi=50.0, rsi_ma=50.0, ema5=110.0, ema20=100.0)


def price_ema20_breakout_candle_at(index: int) -> Candle:
    return make_candle(index, open=100.0, close=105.0)
