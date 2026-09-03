"""Historischer Replay der Kandidatenregel (G1-Prüfvorlage Abschnitt 4.1, 4.3).

Zwei getrennte Schritte, damit jeder fuer sich testbar bleibt: das Auffinden
aller historischen Entscheidungspunkte, und ihre Buendelung zu Episoden.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ai_trading_analyst.domain.screening import (
    CandidateRuleParameters,
    CandleSeries,
    ScreeningStatus,
    SignalEvent,
    evaluate_candidate,
)

from .values import SignalCombination

_FIRST_DAILY_CANDLE = 1


@dataclass(frozen=True, slots=True)
class HistoricalDecision:
    """Ein historischer Entscheidungspunkt.

    Traegt neben der Signalkombination auch die einzelnen Signalereignisse --
    die Episodenbildung fragt danach, *welche* Kreuzung ausgewertet wurde,
    nicht nur, welche Typen zusammenkamen.
    """

    index: int
    combination: SignalCombination
    signal_events: frozenset[SignalEvent]


def find_historical_decisions(
    series: CandleSeries, params: CandidateRuleParameters
) -> tuple[HistoricalDecision, ...]:
    """Findet jedes historische ``CANDIDATE``-Ergebnis der Qualifikationsregel.

    Nur die erste Tageskerze ist je ein Entscheidungspunkt
    (G1-Pruefvorlage Abschnitt 4.1) -- wie im Live-Betrieb. Die zweite
    Tageskerze wird nie selbst geprueft, wirkt aber ueber das
    Sechs-Kerzen-Fenster in spaetere Entscheidungspunkte hinein, weil
    ``evaluate_candidate`` unveraendert auf der vollstaendigen Kerzenfolge
    rechnet.
    """
    decisions: list[HistoricalDecision] = []
    for t in range(len(series)):
        if series.candle(t).daily_candle_index != _FIRST_DAILY_CANDLE:
            continue
        result = evaluate_candidate(series, t, params)
        if result.status == ScreeningStatus.CANDIDATE:
            decisions.append(
                HistoricalDecision(
                    index=t,
                    combination=result.fired_signal_types,
                    signal_events=frozenset(result.signal_events),
                )
            )
    return tuple(decisions)


def group_into_episodes(
    decisions: Sequence[HistoricalDecision],
) -> tuple[tuple[HistoricalDecision, ...], ...]:
    """Buendelt Entscheidungspunkte, die dieselbe Bewegung auswerten.

    Zwei aufeinanderfolgende Entscheidungspunkte gehoeren zur selben Episode,
    wenn sie mindestens ein **identisches Signalereignis** teilen -- denselben
    Signaltyp an derselben Kerze (Abschnitt 4.3). Gezaehlt wird spaeter der
    erste Trigger jeder Episode.

    Massgeblich ist die geteilte Grundlage, nicht der zeitliche Abstand. Der
    frueher hier stehende Fuenf-Kerzen-Cooldown konnte das nicht
    unterscheiden: Er trennte nach Kalender und fasste damit sowohl
    zusammen, was zusammengehoerte, als auch, was nur dicht beieinander lag
    (ADR 0057).

    **Der Nachbarvergleich genuegt fuer die transitive Huelle.** Teilen sich
    der erste und der dritte Entscheidungspunkt ein Ereignis ``(X, k)``, dann
    liegt ``k`` auch im Fenster jedes dazwischenliegenden Punktes -- die
    Fenster sind zusammenhaengende Kerzenbereiche, und ein Ereignis, das zwei
    von ihnen enthalten, enthalten auch alle dazwischen. Der mittlere Punkt
    fuehrt dieses Ereignis also ebenfalls und verkettet die Kette bereits
    ueber den Nachbarvergleich.

    ``NO_RECENT_EMA_DOWNCROSS`` traegt als Position immer die
    Entscheidungskerze und kann deshalb nie zwei Punkte verketten -- richtig
    so: Ein Kriterium, das an jeder Kerze neu gilt, sagt nichts ueber
    gemeinsame Grundlage.
    """
    episodes: list[list[HistoricalDecision]] = []
    laufende_ereignisse: frozenset[SignalEvent] = frozenset()
    for decision in decisions:
        if episodes and (laufende_ereignisse & decision.signal_events):
            episodes[-1].append(decision)
            laufende_ereignisse |= decision.signal_events
        else:
            episodes.append([decision])
            laufende_ereignisse = decision.signal_events
    return tuple(tuple(episode) for episode in episodes)
