"""Testbausteine fuer den Signalkern.

``baseline_indicators()`` liefert einen Zustand, in dem keines der vier
Ereigniskriterien feuert (Gleichheit auf allen Vergleichen, RSI weit ueber der
Ueberverkauft-Schwelle). Ueberschreibt man nur den Wert einer einzelnen Kerze
``i`` so, dass die Ueberschreitung strikt wird, feuert das jeweilige Signal
ausschliesslich an dieser Kerze -- die Vorkerze erfuellt die (Gleichheit
erlaubende) Vorbedingung bereits durch die Baseline. Das haelt die Fenster-
und Kandidatentests unabhaengig von den exakten Zahlenbeispielen der
G1-Pruefvorlage lesbar.

**Fuer ``NO_RECENT_EMA_DOWNCROSS`` gilt das nicht:** Das Kriterium ist
erfuellt, wenn etwas *nicht* geschehen ist, und in der Baseline geschieht
nichts. Es feuert deshalb in fast jedem Test mit -- gewollt, denn genau so
verhaelt es sich auch am Markt in ruhiger Lage. Wer es abschalten will,
setzt mit ``ema_downcross_at`` ein Abwaertskreuz in den Bereich ``t-4 .. t``.
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


BASELINE_EMA = 99.0
"""Die Baseline-EMAs liegen **unter** dem Baseline-Schlusskurs von 100.

Beides zugleich muss gelten: Ema5==Ema20 erfuellt jede Vorkerzen-
Gleichheitsbedingung der Kreuzungen, und ``close > ema20`` erfuellt die
Torbedingung T2 (ADR 0057). Laegen die EMAs auf dem Schlusskurs, scheiterte
jeder Testfall an T2 -- am Markt entspricht die Lage einer Aktie, die nach
einem Aufwaertskreuz ueber ihrem Durchschnitt notiert."""


def baseline_indicators() -> IndicatorValues:
    """Rsi==RsiMa und Ema5==Ema20: erfuellt jede Vorkerzen-Gleichheitsbedingung,
    feuert aber selbst nie (keine strikte Ueberschreitung auf der aktuellen Kerze)."""
    return IndicatorValues(rsi=50.0, rsi_ma=50.0, ema5=BASELINE_EMA, ema20=BASELINE_EMA)


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
    return IndicatorValues(rsi=60.0, rsi_ma=50.0, ema5=BASELINE_EMA, ema20=BASELINE_EMA)


def ema5_ema20_cross_fires() -> IndicatorValues:
    return IndicatorValues(rsi=50.0, rsi_ma=50.0, ema5=110.0, ema20=BASELINE_EMA)


def rsi_oversold_fires() -> IndicatorValues:
    return IndicatorValues(rsi=25.0, rsi_ma=50.0, ema5=BASELINE_EMA, ema20=BASELINE_EMA)


def ema_downcross_fires() -> IndicatorValues:
    """Eine Kerze, an der EMA5 den EMA20 nach unten schneidet.

    Nur diese eine Kerze wird gebraucht: Die Baseline der Vorkerze traegt
    ``ema5 == ema20`` und erfuellt damit die Gleichheit zulassende
    Vorbedingung ``ema5 >= ema20`` -- dieselbe Konvention wie bei den
    Aufwaertskreuzen, nur gespiegelt. Signal C feuert dadurch nirgends mit.
    """
    return IndicatorValues(rsi=50.0, rsi_ma=50.0, ema5=90.0, ema20=BASELINE_EMA)


def price_ema20_breakout_candles_at(index: int) -> dict[int, Candle]:
    """Signal B feuert an ``index`` -- dafuer braucht es **zwei** Kerzen.

    Die Vorkerze muss auf oder unter dem EMA20 schliessen, die Kerze selbst
    darueber. Die Baseline schliesst bereits ueber dem EMA20 (T2), also wird
    die Vorkerze eigens abgesenkt.
    """
    return {
        index - 1: make_candle(index - 1, open=98.0, close=98.0),
        index: make_candle(index, open=98.0, close=105.0),
    }
