"""Historische Signalprüfung (Doc 07; G1-Prüfvorlage Abschnitt 4; CLAUDE.md "Backtesting")."""

from .metrics import compute_backtest_results, compute_horizon_metrics, group_by_combination
from .replay import Decision, deduplicate_with_cooldown, find_historical_decisions
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
    "Decision",
    "HorizonMetrics",
    "SignalCombination",
    "compute_backtest_results",
    "compute_horizon_metrics",
    "deduplicate_with_cooldown",
    "find_historical_decisions",
    "group_by_combination",
]
