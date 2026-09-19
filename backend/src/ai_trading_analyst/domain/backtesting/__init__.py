"""Historische Signalprüfung (Doc 07; G1-Prüfvorlage Abschnitt 4; CLAUDE.md "Backtesting")."""

from .metrics import (
    aggregate_outcomes,
    compute_backtest,
    compute_episode_outcome,
    compute_horizon_metrics,
    group_by_combination,
)
from .options_metrics import (
    OptionsBacktestResult,
    OptionsBacktestScope,
    PooledMetrics,
    VariantMetrics,
    kombinationskuerzel,
    pool_trades,
    thresholds_of,
)
from .replay import (
    HistoricalDecision,
    find_historical_decisions,
    group_into_episodes,
    is_decision_point,
)
from .values import (
    BacktestComputation,
    BacktestConfidence,
    BacktestEpisode,
    BacktestParameters,
    BacktestResult,
    EpisodeHorizonOutcome,
    HorizonMetrics,
    SignalCombination,
)

__all__ = [
    "BacktestComputation",
    "BacktestConfidence",
    "BacktestEpisode",
    "BacktestParameters",
    "BacktestResult",
    "EpisodeHorizonOutcome",
    "HistoricalDecision",
    "HorizonMetrics",
    "OptionsBacktestResult",
    "OptionsBacktestScope",
    "PooledMetrics",
    "SignalCombination",
    "VariantMetrics",
    "aggregate_outcomes",
    "compute_backtest",
    "compute_episode_outcome",
    "compute_horizon_metrics",
    "find_historical_decisions",
    "group_by_combination",
    "group_into_episodes",
    "is_decision_point",
    "kombinationskuerzel",
    "pool_trades",
    "thresholds_of",
]
