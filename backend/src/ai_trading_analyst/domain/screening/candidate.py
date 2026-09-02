"""Die Kandidatenregel ueber das Sechs-Kerzen-Fenster.

Zwei Kaufsignale aus dreien, dazu mindestens eines der beiden
Zusatzkriterien -- ``qualifies`` haelt die Regel als reine Mengenaussage
fest (ADR 0056).

Formalisiert G1-Pruefvorlage Abschnitt 3.4. ``evaluate_candidate`` ist die
einzige Funktion, ueber die eine Kandidatenentscheidung getroffen wird -- sie
gilt gleichermassen fuer die taegliche Live-Pruefung wie fuer jeden
Entscheidungspunkt im Backtesting (Abschnitt 4.1).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .signals import (
    ema5_ema20_cross,
    no_recent_ema_downcross,
    price_ema20_breakout,
    rsi_cross,
    rsi_oversold,
)
from .values import (
    CONFIRMATION_SIGNALS,
    CROSSING_SIGNALS,
    CandleSeries,
    DataIncompleteError,
    IndicatorValues,
    ScreeningResult,
    ScreeningStatus,
    SignalEvent,
    SignalType,
)

_WINDOW_SIGNAL_FUNCTIONS: dict[SignalType, Callable[[CandleSeries, int], bool]] = {
    SignalType.RSI_CROSS: rsi_cross,
    SignalType.PRICE_EMA20_BREAKOUT: price_ema20_breakout,
    SignalType.EMA5_EMA20_CROSS: ema5_ema20_cross,
    SignalType.RSI_OVERSOLD: rsi_oversold,
}
"""Ereigniskriterien: ueber jede Kerze des Fensters ausgewertet."""

_DECISION_CANDLE_FUNCTIONS: dict[SignalType, Callable[[CandleSeries, int], bool]] = {
    SignalType.NO_RECENT_EMA_DOWNCROSS: no_recent_ema_downcross,
}
"""Kriterien, die genau einmal an der Entscheidungskerze gelten (Abschnitt 2.5).

Ueber das Fenster geodert waeren sie sinnlos: "In irgendeinem der sechs
Fuenf-Kerzen-Fenster gab es kein Abwaertskreuz" ist fast immer wahr."""


@dataclass(frozen=True, slots=True)
class CandidateRuleParameters:
    """Von Gate G1 unabhaengige Parameter der Kandidatenregel (Abschnitt 3.1).

    Bewusst als eigenstaendiges Domain-Objekt statt als Abhaengigkeit auf das
    Pydantic-Konfigurationsschema, damit der Signalkern ohne die
    Anwendungskonfiguration testbar und verwendbar bleibt. Die Application-
    Schicht baut diese Parameter aus ``AppConfig`` zusammen.
    """

    required_crossing_signals: int
    """Wie viele der drei **Kaufsignale** feuern muessen (``CROSSING_SIGNALS``).

    Die Zusatzkriterien zaehlen hier nicht mit: Sie ersetzen kein Kaufsignal,
    sondern kommen obendrauf (ADR 0056)."""

    signal_lookback_previous_candles: int
    warmup_candles: int


def qualifies(fired_signal_types: frozenset[SignalType], required_crossing_signals: int) -> bool:
    """Die Kandidatenregel als reine Mengenaussage (Abschnitt 3.3).

    Zwei Bedingungen, beide muessen gelten:

    1. Mindestens ``required_crossing_signals`` der drei **Kaufsignale**.
    2. Mindestens **eines** der beiden Zusatzkriterien.

    Der zweite Teil ist der Grund, warum das keine "N aus fuenf"-Regel ist:
    Waeren alle fuenf gleichwertig, ersetzte ein ueberverkaufter RSI zusammen
    mit der Abwesenheit eines Gegensignals ein zweites Kaufsignal -- und ein
    einzelnes Kreuzungsereignis reichte zur Qualifikation. Gemessen am
    Golden Master waeren so *mehr* Kandidaten entstanden als unter der
    frueheren Regel, obwohl die Schwelle stieg (ADR 0056).

    Eigenstaendig, weil der Backtest dieselbe Frage fuer eine gespeicherte
    Kombination beantworten muss, ohne eine Kerzenserie zu haben.
    """
    kaufsignale = fired_signal_types & CROSSING_SIGNALS
    zusatzkriterien = fired_signal_types & CONFIRMATION_SIGNALS
    return len(kaufsignale) >= required_crossing_signals and len(zusatzkriterien) >= 1


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
       zusaetzlich fuer die Kerze unmittelbar davor. Die Kreuzungsformeln
       benoetigen fuer ihre jeweils frueheste Fensterkerze deren Vorkerze;
       ohne diese zusaetzliche Pruefung koennte eine Datenluecke knapp vor
       dem Fenster unbemerkt bleiben. Dies ist eine Praezisierung der in der
       G1-Pruefvorlage skizzierten Pseudocode-Vorlage, keine fachliche
       Abweichung: Abschnitt 1.5 fordert ausdruecklich, dass jede fuer die
       Fensterauswertung benoetigte Kerze auf Vollstaendigkeit geprueft wird.
    4. Jedes Ereigniskriterium unabhaengig ueber das gesamte Fenster
       auswerten (Abschnitt 3.3) -- Zaehlung pro Typ, nicht pro Ereignis.
    5. Die Kriterien der Entscheidungskerze einmal an ``t`` auswerten
       (Abschnitt 2.5).
    6. ``qualifies`` anwenden.
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
        for signal_type, signal_fn in _WINDOW_SIGNAL_FUNCTIONS.items():
            for i in window:
                if signal_fn(series, i):
                    fired_types.add(signal_type)
                    signal_positions.setdefault(signal_type, i)
        for signal_type, signal_fn in _DECISION_CANDLE_FUNCTIONS.items():
            if signal_fn(series, t):
                fired_types.add(signal_type)
                signal_positions.setdefault(signal_type, t)
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
        if qualifies(frozenset(fired_types), params.required_crossing_signals)
        else ScreeningStatus.NOT_CANDIDATE
    )
    return ScreeningResult(
        status=status, fired_signal_types=frozenset(fired_types), signal_events=events
    )
