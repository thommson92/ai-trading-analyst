"""Die 2-aus-3-Kandidatenregel ueber das Sechs-Kerzen-Fenster.

Formalisiert G1-Pruefvorlage Abschnitt 3.4. ``evaluate_candidate`` ist die
einzige Funktion, ueber die eine Kandidatenentscheidung getroffen wird -- sie
gilt gleichermassen fuer die taegliche Live-Pruefung wie fuer jeden
Entscheidungspunkt im Backtesting (Abschnitt 4.1).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .signals import ema5_ema20_cross, price_ema20_breakout, rsi_cross
from .values import (
    CandleSeries,
    DataIncompleteError,
    IndicatorValues,
    ScreeningResult,
    ScreeningStatus,
    SignalEvent,
    SignalType,
)

_SIGNAL_FUNCTIONS: dict[SignalType, Callable[[CandleSeries, int], bool]] = {
    SignalType.RSI_CROSS: rsi_cross,
    SignalType.PRICE_EMA20_BREAKOUT: price_ema20_breakout,
    SignalType.EMA5_EMA20_CROSS: ema5_ema20_cross,
}


@dataclass(frozen=True, slots=True)
class CandidateRuleParameters:
    """Von Gate G1 unabhaengige Parameter der Kandidatenregel (Abschnitt 3.1).

    Bewusst als eigenstaendiges Domain-Objekt statt als Abhaengigkeit auf das
    Pydantic-Konfigurationsschema, damit der Signalkern ohne die
    Anwendungskonfiguration testbar und verwendbar bleibt. Die Application-
    Schicht baut diese Parameter aus ``AppConfig`` zusammen.
    """

    required_signal_count: int
    signal_lookback_previous_candles: int
    warmup_candles: int


def _indicators_complete(values: IndicatorValues) -> bool:
    return (
        values.rsi is not None
        and values.rsi_ma is not None
        and values.ema5 is not None
        and values.ema20 is not None
    )


def evaluate_candidate(
    series: CandleSeries, t: int, params: CandidateRuleParameters
) -> ScreeningResult:
    """Kandidatenpruefung fuer die Kerze mit Index ``t``.

    Ablauf (Abschnitt 3.4, mit einer Praezisierung gegenueber der
    urspruenglichen Pseudocode-Skizze -- siehe unten):

    1. Warm-up: vor ``t`` muessen mindestens ``warmup_candles`` Kerzen liegen.
    2. Fenster bestimmen: ``t`` sowie die ``signal_lookback_previous_candles``
       unmittelbar vorherigen Kerzen (Abschnitt 3.2).
    3. Vollstaendigkeit pruefen -- nicht nur fuer das Fenster selbst, sondern
       zusaetzlich fuer die Kerze unmittelbar davor. Jede der drei
       Signalformeln benoetigt fuer ihre jeweils frueheste Fensterkerze deren
       Vorkerze; ohne diese zusaetzliche Pruefung koennte eine Datenluecke
       knapp vor dem Fenster unbemerkt bleiben. Dies ist eine Praezisierung
       der in der G1-Pruefvorlage skizzierten Pseudocode-Vorlage, keine
       fachliche Abweichung: Abschnitt 1.5 fordert ausdruecklich, dass jede
       fuer die Fensterauswertung benoetigte Kerze auf Vollstaendigkeit
       geprueft wird.
    4. Jeden Signaltyp unabhaengig ueber das gesamte Fenster auswerten
       (Abschnitt 3.3) -- Zaehlung pro Typ, nicht pro Ereignis.
    5. 2-aus-3-Regel anwenden.
    """
    if t < params.warmup_candles:
        return ScreeningResult(
            status=ScreeningStatus.UNKNOWN_DATA_INCOMPLETE, reason="warmup_insufficient"
        )

    window_start = t - params.signal_lookback_previous_candles
    completeness_start = window_start - 1

    for i in range(completeness_start, t + 1):
        if not series.has_index(i) or not _indicators_complete(series.indicator(i)):
            return ScreeningResult(
                status=ScreeningStatus.UNKNOWN_DATA_INCOMPLETE,
                reason="missing_candle_or_indicator",
                affected_index=i,
            )

    window = range(window_start, t + 1)
    fired_types: set[SignalType] = set()
    signal_positions: dict[SignalType, int] = {}
    try:
        for signal_type, signal_fn in _SIGNAL_FUNCTIONS.items():
            for i in window:
                if signal_fn(series, i):
                    fired_types.add(signal_type)
                    signal_positions.setdefault(signal_type, i)
    except DataIncompleteError as exc:
        return ScreeningResult(
            status=ScreeningStatus.UNKNOWN_DATA_INCOMPLETE,
            reason="missing_candle_or_indicator",
            affected_index=exc.candle_index,
        )

    events = tuple(
        SignalEvent(signal_type=signal_type, candle_index=index)
        for signal_type, index in signal_positions.items()
    )
    status = (
        ScreeningStatus.CANDIDATE
        if len(fired_types) >= params.required_signal_count
        else ScreeningStatus.NOT_CANDIDATE
    )
    return ScreeningResult(
        status=status, fired_signal_types=frozenset(fired_types), signal_events=events
    )
