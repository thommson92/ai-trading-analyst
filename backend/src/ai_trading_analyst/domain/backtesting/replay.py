"""Historischer Replay der 3-aus-5-Kandidatenregel (G1-Prüfvorlage
Abschnitt 4.1, 4.3).

Zwei getrennte Schritte, damit jeder fuer sich testbar bleibt: das Auffinden
aller historischen Entscheidungspunkte, und die Cooldown-Deduplizierung
darauf.
"""

from __future__ import annotations

from collections.abc import Sequence

from ai_trading_analyst.domain.screening import (
    CandidateRuleParameters,
    CandleSeries,
    ScreeningStatus,
    evaluate_candidate,
)

from .values import SignalCombination

Decision = tuple[int, SignalCombination]
"""Ein historischer Entscheidungspunkt: Kerzenindex und die dort
aufgetretene Signalkombination."""

_FIRST_DAILY_CANDLE = 1


def find_historical_decisions(
    series: CandleSeries, params: CandidateRuleParameters
) -> tuple[Decision, ...]:
    """Findet jedes historische ``CANDIDATE``-Ergebnis der Qualifikationsregel.

    Nur die erste Tageskerze ist je ein Entscheidungspunkt
    (G1-Pruefvorlage Abschnitt 4.1) -- wie im Live-Betrieb. Die zweite
    Tageskerze wird nie selbst geprueft, wirkt aber ueber das
    Sechs-Kerzen-Fenster in spaetere Entscheidungspunkte hinein, weil
    ``evaluate_candidate`` unveraendert auf der vollstaendigen Kerzenfolge
    rechnet.
    """
    decisions: list[Decision] = []
    for t in range(len(series)):
        if series.candle(t).daily_candle_index != _FIRST_DAILY_CANDLE:
            continue
        result = evaluate_candidate(series, t, params)
        if result.status == ScreeningStatus.CANDIDATE:
            decisions.append((t, result.fired_signal_types))
    return tuple(decisions)


def deduplicate_with_cooldown(
    decisions: Sequence[Decision], cooldown_candles: int
) -> tuple[Decision, ...]:
    """Entfernt Ereignisse innerhalb der Cooldown-Frist nach dem zuletzt
    behaltenen Ereignis (CLAUDE.md "Backtesting": 5 Kerzen nach jedem
    gezaehlten Ereignis, unabhaengig von der Signalkombination -- sonst
    zaehlte dieselbe Kursbewegung bei knapp unterschiedlicher
    Signalmischung mehrfach).
    """
    kept: list[Decision] = []
    last_kept_index: int | None = None
    for index, combination in decisions:
        if last_kept_index is None or index - last_kept_index > cooldown_candles:
            kept.append((index, combination))
            last_kept_index = index
    return tuple(kept)
