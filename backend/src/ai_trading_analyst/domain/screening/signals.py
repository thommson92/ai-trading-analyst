"""Die fuenf fachlich freigegebenen Signalregeln (G1-Pruefvorlage Abschnitt 2).

Die Kreuzungssignale ``A``, ``B`` und ``C`` pruefen genau eine Kerze ``t``
gegen ihre unmittelbare Vorkerze ``t - 1``. Vergleiche verwenden die
ungerundeten Werte ohne Gleichheitstoleranz: Gleichheit ist auf der Vorkerze
zulaessig (``<=``), auf der aktuellen Kerze muss die Ueberschreitung strikt
sein (``>``) -- Abschnitt 1.4.

``rsi_oversold`` (D) prueft einen Zustand und braucht deshalb als einzige
Funktion keine Vorkerze. ``no_recent_ema_downcross`` (E) prueft die
Abwesenheit eines Ereignisses ueber mehrere Kerzen und wird nur an der
Entscheidungskerze ausgewertet -- warum, steht in Abschnitt 2.5.

Fehlt ein benoetigter Wert, wird ``DataIncompleteError`` ausgeloest statt ``False``
zurueckzugeben: eine Datenluecke ist kein negatives Signal (Abschnitt 1.5).
"""

from __future__ import annotations

from .values import CandleSeries, DataIncompleteError

RSI_OVERSOLD_LEVEL = 30.0
"""Ab wo der RSI als ueberverkauft gilt (Signal D, ADR 0056).

Bewusst hier und nicht in der Konfiguration: Der Wert ist Regelsemantik und
haengt an ``SIGNAL_RULE_VERSION``. Waere er verstellbar, koennten zwei Laeufe
dieselbe Regelversion tragen und dennoch Verschiedenes gerechnet haben."""

EMA_DOWNCROSS_LOOKBACK_PREVIOUS_CANDLES = 4
"""Zusaetzlich zur Entscheidungskerze gepruefte Kreuzungspositionen (Signal E).

Vier plus die Entscheidungskerze sind die fuenf Kerzen aus ADR 0056. Beruehrt
werden dadurch die Kerzen ``t-5`` bis ``t``."""


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


def rsi_oversold(series: CandleSeries, t: int) -> bool:
    """Signal D -- RSI(14, Wilder) liegt unter 30, der Titel ist ueberverkauft.

    Das einzige Kriterium ohne Bezug auf eine Vorkerze: Es beschreibt einen
    Zustand, keinen Uebergang. Die Schwelle ist strikt -- ``RSI == 30``
    erfuellt das Kriterium nicht.
    """
    if not series.has_index(t):
        raise DataIncompleteError(candle_index=t, required=("RSI",))

    curr = series.indicator(t)
    if curr.rsi is None:
        raise DataIncompleteError(candle_index=t, required=("RSI",))

    return curr.rsi < RSI_OVERSOLD_LEVEL


def no_recent_ema_downcross(series: CandleSeries, t: int) -> bool:
    """Signal E -- kein Abwaertskreuz EMA5/EMA20 in den letzten fuenf Kerzen.

    Erfuellt, wenn etwas **nicht** stattgefunden hat: Hat der EMA5 den EMA20
    kurz zuvor nach unten geschnitten, ist der anschliessende Schnitt nach
    oben Gezappel um die Linie und kein Trendwechsel.

    Die Abwaertskreuzung ist die exakte Spiegelung von Signal C -- Gleichheit
    auf der Vorkerze zulaessig (``>=``), Unterschreitung auf der aktuellen
    Kerze strikt (``<``).

    Anders als A bis D wird diese Funktion nur an der Entscheidungskerze
    aufgerufen (Abschnitt 2.5). Sie prueft ihre Kerzen dennoch selbst auf
    Vollstaendigkeit: Stuende ``signal_lookback_previous_candles`` unter vier,
    reichte die Vorpruefung in ``evaluate_candidate`` nicht bis ``t-5``.
    """
    for index in range(t - EMA_DOWNCROSS_LOOKBACK_PREVIOUS_CANDLES, t + 1):
        if not series.has_index(index - 1) or not series.has_index(index):
            raise DataIncompleteError(candle_index=index, required=("EMA5", "EMA20"))

        prev, curr = series.indicator(index - 1), series.indicator(index)
        if prev.ema5 is None or prev.ema20 is None or curr.ema5 is None or curr.ema20 is None:
            raise DataIncompleteError(candle_index=index, required=("EMA5", "EMA20"))

        if prev.ema5 >= prev.ema20 and curr.ema5 < curr.ema20:
            return False

    return True
