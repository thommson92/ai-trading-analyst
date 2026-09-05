"""Historische Signalprüfung (Doc 07; G1-Prüfvorlage Abschnitt 4; CLAUDE.md "Backtesting")."""

from .metrics import compute_backtest_results, compute_horizon_metrics, group_by_combination
from .options_metrics import (
    OptionsBacktestResult,
    OptionsBacktestScope,
    PooledMetrics,
    VariantMetrics,
    kombinationskuerzel,
    pool_trades,
)
from .replay import (
    HistoricalDecision,
    find_historical_decisions,
    group_into_episodes,
    is_decision_point,
)
from .values import (
    BacktestConfidence,
    BacktestParameters,
    BacktestResult,
    HorizonMetrics,
    SignalCombination,
)

__all__ = [
    "BacktestConfidence",
    "BacktestParameters",
    "BacktestResult",
    "HistoricalDecision",
    "HorizonMetrics",
    "OptionsBacktestResult",
    "OptionsBacktestScope",
    "PooledMetrics",
    "SignalCombination",
    "VariantMetrics",
    "compute_backtest_results",
    "compute_horizon_metrics",
    "find_historical_decisions",
    "group_by_combination",
    "group_into_episodes",
    "is_decision_point",
    "kombinationskuerzel",
    "pool_trades",
]
