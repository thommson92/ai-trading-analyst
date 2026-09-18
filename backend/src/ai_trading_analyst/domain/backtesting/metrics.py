"""Kennzahlenberechnung der historischen Signalprüfung (Doc 07 "Kennzahlen";
G1-Prüfvorlage Abschnitt 4.2; CLAUDE.md "Backtesting").

Reine Berechnung auf den gezaehlten Entscheidungspunkten -- Replay und
Episodenbildung liegen in ``replay.py``.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta
from uuid import UUID

from ai_trading_analyst.domain.screening import (
    CandidateRuleParameters,
    CandleSeries,
)

from .replay import HistoricalDecision, find_historical_decisions, group_into_episodes
from .values import (
    BacktestComputation,
    BacktestConfidence,
    BacktestEpisode,
    BacktestParameters,
    BacktestResult,
    EpisodeHorizonOutcome,
    HorizonMetrics,
    SignalCombination,
    qualifying_combinations,
)

_DAYS_PER_YEAR = 365


def _truncate_to_recent_history(
    series: CandleSeries, history_years: int, evaluated_at: datetime
) -> CandleSeries:
    """Blendet Kerzen vor dem konfigurierten Historienfenster aus (Doc 10,
    Paragraph 6.6) -- aeltere gespeicherte Kerzen fliessen nicht in den
    Replay ein."""
    cutoff = evaluated_at - timedelta(days=_DAYS_PER_YEAR * history_years)
    start_index = next(
        (i for i in range(len(series)) if series.candle(i).timestamp >= cutoff), len(series)
    )
    return CandleSeries(
        candles=series.candles[start_index:], indicators=series.indicators[start_index:]
    )


def group_by_combination(
    decisions: Sequence[HistoricalDecision],
) -> dict[SignalCombination, tuple[int, ...]]:
    """Gruppiert Entscheidungspunkte nach der exakten Signalkombination."""
    grouped: dict[SignalCombination, list[int]] = defaultdict(list)
    for decision in decisions:
        grouped[decision.combination].append(decision.index)
    return {combination: tuple(indices) for combination, indices in grouped.items()}


def compute_episode_outcome(series: CandleSeries, t: int, horizon: int) -> EpisodeHorizonOutcome:
    """Was der Kurs nach dem Ereignis an Kerze ``t`` bis ``t + horizon`` tat.

    **Die eine Rechnung** hinter Aggregat und Einzelwert (ADR 0061): Die
    Kennzahlen je Horizont mitteln ueber genau diese Ergebnisse, die
    Episodentabelle zeigt sie einzeln. Zwei Fassungen koennten
    auseinanderlaufen, ohne dass ein Test es merkt.

    Reicht die Historie nicht bis zum Horizont, sind alle Werte ``None``.
    """
    if not series.has_index(t + horizon):
        return EpisodeHorizonOutcome(
            horizon=horizon, return_pct=None, max_loss=None, drawdown=None, held_above_entry=None
        )
    entry = series.candle(t).close
    path_after_entry = [series.candle(i).close for i in range(t + 1, t + horizon + 1)]

    running_peak = entry
    max_drawdown = 0.0
    for close in path_after_entry:
        running_peak = max(running_peak, close)
        max_drawdown = max(max_drawdown, (running_peak - close) / running_peak)

    return EpisodeHorizonOutcome(
        horizon=horizon,
        return_pct=(path_after_entry[-1] - entry) / entry,
        max_loss=min((close - entry) / entry for close in path_after_entry),
        drawdown=max_drawdown,
        held_above_entry=all(close > entry for close in path_after_entry),
    )


def compute_horizon_metrics(
    series: CandleSeries,
    dedup_indices: Sequence[int],
    raw_event_count: int,
    horizon: int,
    params: BacktestParameters,
) -> HorizonMetrics:
    """Kennzahlen einer Signalkombination fuer einen Horizont, gerechnet
    ueber die Einstiegskerzen ``dedup_indices`` (die gezaehlten Episoden,
    ADR 0057)."""
    return aggregate_outcomes(
        [compute_episode_outcome(series, t, horizon) for t in dedup_indices],
        raw_event_count,
        horizon,
        params,
    )


def aggregate_outcomes(
    outcomes: Sequence[EpisodeHorizonOutcome],
    raw_event_count: int,
    horizon: int,
    params: BacktestParameters,
) -> HorizonMetrics:
    """Die Kennzahlen aus bereits gerechneten Episodenergebnissen.

    ``deduplicated_event_count`` ist die Zahl der Ereignisse, die tatsaechlich
    bis zu diesem Horizont reichen -- kann je Horizont kleiner sein als die
    Gesamtzahl der gezaehlten Ereignisse, weil ein Ereignis nahe dem Ende
    der Historie einen laengeren Horizont nicht mehr vollstaendig durchlaeuft.
    Unterhalb von ``minimum_sample_size`` gilt die Grundlage als nicht
    belastbar (CLAUDE.md "Daten und Ergebnisse") -- die Kennzahlen bleiben
    dann ``None``, nicht nur niedrig eingestuft.
    """
    returns: list[float] = []
    max_losses: list[float] = []
    drawdowns: list[float] = []
    held_above_entry_flags: list[bool] = []

    for outcome in outcomes:
        if (
            outcome.return_pct is None
            or outcome.max_loss is None
            or outcome.drawdown is None
            or outcome.held_above_entry is None
        ):
            continue  # Horizont nicht erreicht (``reached``), gilt fuer alle vier Felder
        returns.append(outcome.return_pct)
        max_losses.append(outcome.max_loss)
        drawdowns.append(outcome.drawdown)
        held_above_entry_flags.append(outcome.held_above_entry)

    deduplicated_event_count = len(returns)
    confidence = _classify_confidence(deduplicated_event_count, params)
    has_reliable_basis = confidence is not BacktestConfidence.INSUFFICIENT_DATA

    return HorizonMetrics(
        horizon=horizon,
        raw_event_count=raw_event_count,
        deduplicated_event_count=deduplicated_event_count,
        hit_rate=_hit_rate(returns) if has_reliable_basis else None,
        mean_return=statistics.fmean(returns) if has_reliable_basis and returns else None,
        median_return=statistics.median(returns) if has_reliable_basis and returns else None,
        max_loss=min(max_losses) if has_reliable_basis and max_losses else None,
        drawdown=max(drawdowns) if has_reliable_basis and drawdowns else None,
        held_above_entry_rate=(
            sum(held_above_entry_flags) / len(held_above_entry_flags)
            if has_reliable_basis and held_above_entry_flags
            else None
        ),
        confidence=confidence,
    )


def _hit_rate(returns: Sequence[float]) -> float | None:
    if not returns:
        return None
    return sum(1 for r in returns if r > 0) / len(returns)


def _classify_confidence(
    deduplicated_event_count: int, params: BacktestParameters
) -> BacktestConfidence:
    if deduplicated_event_count < params.minimum_sample_size:
        return BacktestConfidence.INSUFFICIENT_DATA
    if deduplicated_event_count < params.normal_confidence_sample_size:
        return BacktestConfidence.LOW_SAMPLE
    return BacktestConfidence.NORMAL


def compute_backtest(
    series: CandleSeries,
    stock_id: UUID,
    candidate_params: CandidateRuleParameters,
    backtest_params: BacktestParameters,
    signal_rule_version: str,
    evaluated_at: datetime,
) -> BacktestComputation:
    """Replay, Episodenbildung, die Episoden selbst und daraus die Kennzahlen.

    **Eine Rechnung** (ADR 0061): Jedes Episodenergebnis entsteht genau
    einmal; die Kennzahlen je Kombination und Horizont mitteln ueber diese
    Ergebnisse. Liefert immer alle moeglichen Signalkombinationen, auch mit
    null Ereignissen -- kein stillschweigendes Weglassen (Projektkonvention).
    Die Horizonte stehen aufsteigend, unabhaengig von der Konfiguration --
    so kommen sie auch aus der Datenbank zurueck.
    """
    series = _truncate_to_recent_history(series, backtest_params.history_years, evaluated_at)
    if len(series) == 0:
        raise ValueError(
            f"Keine einzige gespeicherte Kerze innerhalb der letzten "
            f"{backtest_params.history_years} Jahre -- kein Backtest moeglich."
        )

    raw_decisions = find_historical_decisions(series, candidate_params)
    episodes = group_into_episodes(raw_decisions)
    horizons = tuple(sorted(backtest_params.horizons))

    # Gezaehlt wird der erste Trigger jeder Episode: Er ist der Punkt, an dem
    # die Regel erstmals ansprach, und liefert damit auch den Einstiegskurs
    # (CLAUDE.md "Backtesting", ADR 0057).
    einzelne = tuple(
        BacktestEpisode(
            stock_id=stock_id,
            signal_types=episode[0].combination,
            signal_rule_version=signal_rule_version,
            evaluated_at=evaluated_at,
            entry_at=series.candle(episode[0].index).timestamp,
            entry_close=series.candle(episode[0].index).close,
            trigger_count=len(episode),
            last_trigger_at=series.candle(episode[-1].index).timestamp,
            horizons=tuple(
                compute_episode_outcome(series, episode[0].index, horizon) for horizon in horizons
            ),
        )
        for episode in episodes
    )

    raw_by_combination = group_by_combination(raw_decisions)
    counted_by_combination: dict[SignalCombination, list[BacktestEpisode]] = defaultdict(list)
    for einzelfall in einzelne:
        counted_by_combination[einzelfall.signal_types].append(einzelfall)

    history_start = series.candle(0).timestamp
    history_end = series.candle(len(series) - 1).timestamp

    results = tuple(
        BacktestResult(
            stock_id=stock_id,
            signal_types=combination,
            signal_rule_version=signal_rule_version,
            evaluated_at=evaluated_at,
            history_start=history_start,
            history_end=history_end,
            horizons=tuple(
                aggregate_outcomes(
                    [
                        ergebnis
                        for einzelfall in counted_by_combination.get(combination, ())
                        for ergebnis in einzelfall.horizons
                        if ergebnis.horizon == horizon
                    ],
                    len(raw_by_combination.get(combination, ())),
                    horizon,
                    backtest_params,
                )
                for horizon in horizons
            ),
        )
        for combination in qualifying_combinations(candidate_params.required_crossing_signals)
    )
    return BacktestComputation(results=results, episodes=einzelne)
