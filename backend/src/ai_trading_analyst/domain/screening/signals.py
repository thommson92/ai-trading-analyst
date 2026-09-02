"""Die fachlich freigegebenen Signalregeln (G1-Pruefvorlage Abschnitt 2).

Jede Funktion prueft genau eine Kerze ``t`` gegen ihre unmittelbare Vorkerze
``t - 1``. Vergleiche verwenden die ungerundeten Werte ohne Gleichheitstoleranz:
Gleichheit ist auf der Vorkerze zulaessig (``<=``), auf der aktuellen Kerze
muss die Ueberschreitung strikt sein (``>``) -- Abschnitt 1.4.

Fehlt ein benoetigter Wert, wird ``DataIncompleteError`` ausgeloest statt ``False``
zurueckzugeben: eine Datenluecke ist kein negatives Signal (Abschnitt 1.5).
"""

from __future__ import annotations

from .values import CandleSeries, DataIncompleteError


def rsi_cross(series: CandleSeries, t: int) -> bool:
    """Signal A -- RSI(14, Wilder) kreuzt SMA(RSI, 14) von unten nach oben."""
    if not series.has_index(t - 1) or not series.has_index(t):
        raise DataIncompleteError(candle_index=t, required=("RSI", "RSI_MA"))

    prev, curr = series.indicator(t - 1), series.indicator(t)
    if prev.rsi is None or prev.rsi_ma is None or curr.rsi is None or curr.rsi_ma is None:
        raise DataIncompleteError(candle_index=t, required=("RSI", "RSI_MA"))

    return prev.rsi <= prev.rsi_ma and curr.rsi > curr.rsi_ma


def price_ema20_breakout(series: CandleSeries, t: int) -> bool:
    """Signal B -- Schlusskurs kreuzt EMA20 von unten nach oben.

    Ein Gap-up ueber den EMA20 erfuellt das Signal, sofern die Vorkerze auf
    oder unter dem EMA20 geschlossen hat: Bezugspunkt ist der Schlusskurs der
    Vorkerze, nicht die Eroeffnung der aktuellen Kerze (ADR 0056).
    """
    if not series.has_index(t - 1) or not series.has_index(t):
        raise DataIncompleteError(candle_index=t, required=("CLOSE", "EMA20"))

    prev_candle, prev_ind = series.candle(t - 1), series.indicator(t - 1)
    curr_candle, curr_ind = series.candle(t), series.indicator(t)
    if prev_ind.ema20 is None or curr_ind.ema20 is None:
        raise DataIncompleteError(candle_index=t, required=("CLOSE", "EMA20"))

    return prev_candle.close <= prev_ind.ema20 and curr_candle.close > curr_ind.ema20


def ema5_ema20_cross(series: CandleSeries, t: int) -> bool:
    """Signal C -- EMA5 kreuzt EMA20 von unten nach oben, auf Kerzenschluss bestaetigt."""
    if not series.has_index(t - 1) or not series.has_index(t):
        raise DataIncompleteError(candle_index=t, required=("EMA5", "EMA20"))

    prev, curr = series.indicator(t - 1), series.indicator(t)
    if prev.ema5 is None or prev.ema20 is None or curr.ema5 is None or curr.ema20 is None:
        raise DataIncompleteError(candle_index=t, required=("EMA5", "EMA20"))

    return prev.ema5 <= prev.ema20 and curr.ema5 > curr.ema20
