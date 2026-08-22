"""Die deterministische Chartauswertung einer Kerze (Doc 10, Paragraph 6.8).

Fuehrt zusammen, was Doc 10 als deterministische Berechnungen des Technical
Analysis Module auffuehrt: Trendrichtung, RSI, Lage zu EMA5 und EMA20,
Volatilitaet ueber die Average True Range, juengste Hoch- und Tiefpunkte,
Zonen und die Abstaende zu ihnen.

Kein Sprachmodell ist daran beteiligt. Das Ergebnis ist die Eingabe des
Technical Agent, der es ausschliesslich einordnen darf (CLAUDE.md).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from ai_trading_analyst.domain.screening import Candle, CandleSeries, wilder_moving_average

from .values import (
    TECHNICAL_ANALYSIS_VERSION,
    TechnicalAnalysisParameters,
    TechnicalSnapshot,
    TechnicalStatus,
    TrendDirection,
)
from .zones import build_zones


def true_ranges(candles: Sequence[Candle]) -> list[float | None]:
    """True Range je Kerze; ``None`` fuer die erste.

    Die True Range vergleicht die Kerzenspanne mit dem Abstand zum
    **vorherigen** Schlusskurs und erfasst so die Luecke zwischen zwei
    Kerzen. Fuer die erste Kerze gibt es keinen Vorgaenger -- das Ergebnis
    bleibt ``None`` statt ersatzweise auf die blosse Spanne zurueckzufallen
    (CLAUDE.md: fehlende Werte bleiben fehlend).
    """
    result: list[float | None] = [None]
    for index in range(1, len(candles)):
        candle = candles[index]
        previous_close = candles[index - 1].close
        result.append(
            max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        )
    return result


def average_true_range(candles: Sequence[Candle], length: int) -> list[float | None]:
    """ATR nach Wilder -- dieselbe Glaettung, die schon dem RSI zugrunde liegt.

    Bewusst die vorhandene Funktion aus ``domain.screening.indicators`` und
    keine zweite Implementierung: Zwei Glaettungen mit minimal
    unterschiedlichem Startverhalten waeren im Bericht nicht auseinander-
    zuhalten.
    """
    return wilder_moving_average(true_ranges(candles), length)


def _trend(
    series: CandleSeries, index: int, params: TechnicalAnalysisParameters
) -> TrendDirection | None:
    """Trendrichtung aus Steigung des EMA20 und Lage von EMA5 zu EMA20.

    Beide muessen dasselbe sagen. Widersprechen sie sich -- der EMA20 steigt,
    aber der EMA5 ist bereits darunter gefallen --, ist das Ergebnis
    ``SIDEWAYS`` und nicht die Richtung des staerkeren der beiden Hinweise:
    Genau in dieser Lage ist die Richtung tatsaechlich offen, und eine
    Festlegung wuerde dem spaeteren Bericht eine Eindeutigkeit vorspiegeln,
    die die Kursreihe nicht hergibt.
    """
    earlier_index = index - params.trend_lookback
    if earlier_index < 0:
        return None

    current = series.indicator(index)
    earlier_ema20 = series.indicator(earlier_index).ema20
    if current.ema5 is None or current.ema20 is None or earlier_ema20 is None:
        return None
    if earlier_ema20 == 0:
        return None

    slope_pct = (current.ema20 - earlier_ema20) / earlier_ema20
    if abs(slope_pct) < params.trend_flat_pct:
        return TrendDirection.SIDEWAYS
    if slope_pct > 0 and current.ema5 > current.ema20:
        return TrendDirection.UP
    if slope_pct < 0 and current.ema5 < current.ema20:
        return TrendDirection.DOWN
    return TrendDirection.SIDEWAYS


def _relative_distance(close: float, reference: float | None) -> float | None:
    if reference is None or reference == 0:
        return None
    return (close - reference) / reference


def _extremes(
    candles: Sequence[Candle], start: int, end: int
) -> tuple[float, datetime, float, datetime]:
    """Hoechstes Hoch und tiefstes Tief samt Zeitpunkt in ``candles[start:end]``.

    Bei mehreren gleich hohen Kerzen gewinnt die aelteste -- der Zeitpunkt,
    an dem das Niveau zuerst erreicht wurde.
    """
    window = candles[start:end]
    highest = max(window, key=lambda candle: candle.high)
    lowest = min(window, key=lambda candle: candle.low)
    return highest.high, highest.timestamp, lowest.low, lowest.timestamp


def compute_technical_snapshot(
    series: CandleSeries,
    index: int,
    params: TechnicalAnalysisParameters,
    evaluated_at: datetime,
) -> TechnicalSnapshot:
    """Wertet die Kerze ``index`` deterministisch aus.

    Sind bis einschliesslich ``index`` weniger Kerzen vorhanden, als das
    laengste benoetigte Fenster verlangt, ist das Ergebnis
    ``INSUFFICIENT_DATA`` -- nicht eine auf einem kuerzeren Fenster
    gerechnete Auswertung, der man den Unterschied spaeter nicht mehr ansieht
    (CLAUDE.md: ohne belastbare Grundlage lautet das Ergebnis
    INSUFFICIENT_DATA).
    """
    if not series.has_index(index):
        raise IndexError(f"Kerzenindex {index} liegt ausserhalb der Serie (Laenge {len(series)})")

    available = index + 1
    if available < params.minimum_candles:
        return TechnicalSnapshot(
            status=TechnicalStatus.INSUFFICIENT_DATA,
            evaluated_at=evaluated_at,
            analysis_version=TECHNICAL_ANALYSIS_VERSION,
            reason="too_few_candles",
        )

    candle = series.candle(index)
    indicators = series.indicator(index)
    close = candle.close

    window_start = max(0, available - params.history_candles)
    atr = average_true_range(series.candles[: index + 1], params.atr_length)[index]
    recent_high, recent_high_at, recent_low, recent_low_at = _extremes(
        series.candles, available - params.extremes_lookback, available
    )

    return TechnicalSnapshot(
        status=TechnicalStatus.COMPLETED,
        evaluated_at=evaluated_at,
        analysis_version=TECHNICAL_ANALYSIS_VERSION,
        candle_timestamp=candle.timestamp,
        close=close,
        trend=_trend(series, index, params),
        rsi=indicators.rsi,
        ema5=indicators.ema5,
        ema20=indicators.ema20,
        distance_to_ema5_pct=_relative_distance(close, indicators.ema5),
        distance_to_ema20_pct=_relative_distance(close, indicators.ema20),
        atr=atr,
        atr_pct=None if atr is None or close == 0 else atr / close,
        recent_high=recent_high,
        recent_high_at=recent_high_at,
        recent_low=recent_low,
        recent_low_at=recent_low_at,
        zones=build_zones(series.candles, window_start, available, close, params),
    )
