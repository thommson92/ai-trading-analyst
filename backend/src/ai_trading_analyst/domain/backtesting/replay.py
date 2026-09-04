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


def is_decision_point(series: CandleSeries, t: int) -> bool:
    """Wird an dieser Kerze ueberhaupt entschieden?

    Nur die erste Tageskerze -- wie im Live-Betrieb (G1-Pruefvorlage
    Abschnitt 4.1). Oeffentlich, damit der Validierungschart dieselbe
    Definition benutzt und nicht eine zweite, die stillschweigend
    auseinanderlaufen koennte.
    """
    return series.candle(t).daily_candle_index == _FIRST_DAILY_CANDLE


@dataclass(frozen=True, slots=True)
class HistoricalDecision:
    """Ein historischer Entscheidungspunkt.

    Traegt neben der Signalkombination auch die einzelnen Feuerungen -- die
    Episodenbildung fragt danach, *welche* Kreuzung ausgewertet wurde, nicht
    nur, welche Typen zusammenkamen.

    ``signal_firings`` und nicht ``signal_events``: Gebraucht wird **jedes**
    Feuern im Fenster, nicht das erste je Typ. Werteten zwei
    Entscheidungspunkte dieselbe Kreuzung aus, haette aber einer von beiden
    fuer denselben Signaltyp noch eine aeltere Fundstelle im Fenster, so
    stuende dort eine andere Position -- und die geteilte Grundlage bliebe
    unsichtbar. Die Episoden zerfielen genau dort, wo sie zusammengehoeren.
    """

    index: int
    combination: SignalCombination
    signal_firings: frozenset[SignalEvent]


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
        if not is_decision_point(series, t):
            continue
        result = evaluate_candidate(series, t, params)
        if result.status == ScreeningStatus.CANDIDATE:
            decisions.append(
                HistoricalDecision(
                    index=t,
                    combination=result.fired_signal_types,
                    signal_firings=result.signal_firings,
                )
            )
    return tuple(decisions)


def group_into_episodes(
    decisions: Sequence[HistoricalDecision],
) -> tuple[tuple[HistoricalDecision, ...], ...]:
    """Buendelt Entscheidungspunkte, die dieselbe Bewegung auswerten.

    Zwei aufeinanderfolgende Entscheidungspunkte gehoeren zur selben Episode,
    wenn sie mindestens eine **identische Feuerung** teilen -- denselben
    Signaltyp an derselben Kerze (Abschnitt 4.3). Gezaehlt wird spaeter der
    erste Trigger jeder Episode.

    Massgeblich ist die geteilte Grundlage, nicht der zeitliche Abstand. Der
    frueher hier stehende Fuenf-Kerzen-Cooldown konnte das nicht
    unterscheiden: Er trennte nach Kalender und fasste damit sowohl
    zusammen, was zusammengehoerte, als auch, was nur dicht beieinander lag
    (ADR 0057).

    **Der Nachbarvergleich genuegt fuer die transitive Huelle.** Teilen sich
    der erste und der dritte Entscheidungspunkt eine Feuerung ``(X, k)``, dann
    liegt ``k`` auch im Fenster jedes dazwischenliegenden Punktes -- die
    Fenster sind zusammenhaengende Kerzenbereiche, und eine Kerze, die zwei
    von ihnen enthalten, enthalten auch alle dazwischen. Der mittlere Punkt
    fuehrt diese Feuerung also ebenfalls und verkettet die Kette bereits ueber
    den Nachbarvergleich.

    Dieser Schluss haelt nur, weil ``signal_firings`` **jede** Feuerung fuehrt:
    ``X`` feuert bei allen dreien an ``k``, und damit steht ``(X, k)`` bei
    allen dreien auch drin. Mit der fuer den Bericht gespeicherten fruehesten
    Fundstelle je Typ waere er falsch -- dort haette der mittlere Punkt
    moeglicherweise eine aeltere Position vermerkt und die Kette zerrissen.

    ``NO_RECENT_EMA_DOWNCROSS`` feuert immer an der Entscheidungskerze und kann
    deshalb nie zwei Punkte verketten -- richtig so: Ein Kriterium, das an
    jeder Kerze neu gilt, sagt nichts ueber gemeinsame Grundlage.
    """
    episodes: list[list[HistoricalDecision]] = []
    for decision in decisions:
        vorgaenger = episodes[-1][-1] if episodes else None
        if vorgaenger is not None and (vorgaenger.signal_firings & decision.signal_firings):
            episodes[-1].append(decision)
        else:
            episodes.append([decision])
    return tuple(tuple(episode) for episode in episodes)
