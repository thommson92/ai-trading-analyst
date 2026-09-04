"""Die Kandidatenregel ueber das Sechs-Kerzen-Fenster.

Zwei Kaufsignale aus dreien, dazu mindestens eines der beiden
Zusatzkriterien -- ``qualifies`` haelt die Regel als reine Mengenaussage
fest (ADR 0056). Zwei Torbedingungen an der Entscheidungskerze kommen
hinzu (``_failed_gates``, ADR 0057): Sie zaehlen nicht mit, koennen eine
erfuellte Signalmenge aber verwerfen.

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

MAX_CROSSING_SIGNAL_AGE_CANDLES = 1
"""Wie alt das juengste Kaufsignal an der Entscheidungskerze hoechstens sein
darf (Torbedingung T1, Abschnitt 3.6).

``1`` heisst: Es muss an ``t`` oder ``t-1`` gefeuert haben. Wie die uebrigen
Regelschwellen im Code und nicht in der Konfiguration -- was die Regel
bedeutet, haengt an ``SIGNAL_RULE_VERSION`` (ADR 0056 Abschnitt 4, ADR 0057)."""

GATE_STALE_CROSSING_SIGNALS = "stale_crossing_signals"
"""Kein Kaufsignal hat an ``t`` oder ``t-1`` gefeuert."""

GATE_CLOSE_NOT_ABOVE_EMA20 = "close_not_above_ema20"
"""Der Schlusskurs der Entscheidungskerze liegt nicht ueber dem EMA20."""


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

    def __post_init__(self) -> None:
        if not 1 <= self.required_crossing_signals <= len(CROSSING_SIGNALS):
            raise ValueError(
                "required_crossing_signals muss zwischen 1 und "
                f"{len(CROSSING_SIGNALS)} liegen, ist aber "
                f"{self.required_crossing_signals} -- mehr Kaufsignale, als es "
                "gibt, liefern dauerhaft null Kandidaten, und ein Lauf ohne "
                "Kandidaten sieht aus wie ein ruhiger Markt statt wie ein "
                "Konfigurationsfehler"
            )


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
    7. Die Torbedingungen pruefen -- aber nur, wenn Schritt 6 durchging:
       "zu wenige Signale" ist keine verworfene Qualifikation und traegt
       deshalb keinen Grund (Abschnitt 3.6).
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
    # Jedes tatsaechliche Feuern, nicht nur das erste je Typ. Frische
    # (Abschnitt 3.6) und Episodenbildung (Abschnitt 4.3) haengen beide daran;
    # die gespeicherte fruehste Fundstelle taugt fuer keines von beidem.
    firings: set[SignalEvent] = set()
    try:
        for signal_type, signal_fn in _WINDOW_SIGNAL_FUNCTIONS.items():
            for i in window:
                if not signal_fn(series, i):
                    continue
                fired_types.add(signal_type)
                signal_positions.setdefault(signal_type, i)
                firings.add(SignalEvent(signal_type=signal_type, candle_index=i))
        for signal_type, signal_fn in _DECISION_CANDLE_FUNCTIONS.items():
            if signal_fn(series, t):
                fired_types.add(signal_type)
                signal_positions.setdefault(signal_type, t)
                firings.add(SignalEvent(signal_type=signal_type, candle_index=t))
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
    if not qualifies(frozenset(fired_types), params.required_crossing_signals):
        # Zu wenige Signale ist keine verworfene Qualifikation -- ohne Grund.
        return ScreeningResult(
            status=ScreeningStatus.NOT_CANDIDATE,
            fired_signal_types=frozenset(fired_types),
            signal_events=events,
            signal_firings=frozenset(firings),
        )

    gate_reason = _failed_gates(series, t, frozenset(firings))
    return ScreeningResult(
        status=ScreeningStatus.NOT_CANDIDATE if gate_reason else ScreeningStatus.CANDIDATE,
        fired_signal_types=frozenset(fired_types),
        signal_events=events,
        signal_firings=frozenset(firings),
        reason=gate_reason,
    )


def _failed_gates(series: CandleSeries, t: int, firings: frozenset[SignalEvent]) -> str | None:
    """Die Torbedingungen an der Entscheidungskerze (Abschnitt 3.6).

    Liefert ``None``, wenn beide gelten, sonst die Gruende als ein Wert fuer
    ``ScreeningResult.reason``.

    Die Tore sind **Filter, keine Kriterien**: Sie zaehlen nicht mit,
    veraendern ``fired_signal_types`` nicht und erscheinen in keiner
    Signalkombination. Deshalb sind sie auch keine ``SignalType``-Mitglieder --
    das ersparte die Erweiterung des Datenbank-Enums (ADR 0057).

    Ihre Daten deckt die Vollstaendigkeitspruefung des Fensters bereits ab;
    ein eigener ``UNKNOWN_DATA_INCOMPLETE``-Pfad entsteht nicht.
    """
    gruende = []

    kreuzungen = [
        firing.candle_index for firing in firings if firing.signal_type in CROSSING_SIGNALS
    ]
    if not kreuzungen or t - max(kreuzungen) > MAX_CROSSING_SIGNAL_AGE_CANDLES:
        gruende.append(GATE_STALE_CROSSING_SIGNALS)

    ema20 = series.indicator(t).ema20
    if ema20 is None or not series.candle(t).close > ema20:
        gruende.append(GATE_CLOSE_NOT_ABOVE_EMA20)

    return "gate:" + "+".join(gruende) if gruende else None
