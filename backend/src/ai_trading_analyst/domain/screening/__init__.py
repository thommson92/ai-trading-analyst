"""Deterministischer Signalkern (Gate G1, Sprint 1A).

Oeffentliche Schnittstelle des Screener-Domainkerns. Fachliche Grundlage ist
ausschliesslich ``docs/requirements/g1-pruefvorlage.md``.
"""

from .candidate import CandidateRuleParameters, evaluate_candidate
from .candle_aggregation import (
    AggregationResult,
    CandleAggregationError,
    IncompleteCandle,
    IncompleteReason,
    IntradayBar,
    SessionParameters,
    aggregate_intraday_bars,
)
from .indicators import (
    IndicatorParameters,
    UnsupportedSmoothingMethodError,
    compute_indicator_values,
    exponential_moving_average,
    relative_strength_index,
    simple_moving_average,
    wilder_moving_average,
)
from .signals import (
    ema5_ema20_cross,
    no_recent_ema_downcross,
    price_ema20_breakout,
    rsi_cross,
    rsi_oversold,
)
from .values import (
    SIGNAL_RULE_VERSION,
    Candle,
    CandleSeries,
    DataIncompleteError,
    IndicatorValues,
    ScreeningResult,
    ScreeningStatus,
    SignalEvent,
    SignalType,
)

__all__ = [
    "SIGNAL_RULE_VERSION",
    "AggregationResult",
    "CandidateRuleParameters",
    "Candle",
    "CandleAggregationError",
    "CandleSeries",
    "DataIncompleteError",
    "IncompleteCandle",
    "IncompleteReason",
    "IndicatorParameters",
    "IndicatorValues",
    "IntradayBar",
    "ScreeningResult",
    "ScreeningStatus",
    "SessionParameters",
    "SignalEvent",
    "SignalType",
    "UnsupportedSmoothingMethodError",
    "aggregate_intraday_bars",
    "compute_indicator_values",
    "ema5_ema20_cross",
    "evaluate_candidate",
    "exponential_moving_average",
    "no_recent_ema_downcross",
    "price_ema20_breakout",
    "relative_strength_index",
    "rsi_cross",
    "rsi_oversold",
    "simple_moving_average",
    "wilder_moving_average",
]
