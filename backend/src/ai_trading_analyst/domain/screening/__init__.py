"""Deterministischer Signalkern (Gate G1, Sprint 1A).

Oeffentliche Schnittstelle des Screener-Domainkerns. Fachliche Grundlage ist
ausschliesslich ``docs/requirements/g1-pruefvorlage.md``.
"""

from .candidate import CandidateRuleParameters, evaluate_candidate
from .signals import ema5_ema20_cross, price_ema20_breakout, rsi_cross
from .values import (
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
    "CandidateRuleParameters",
    "Candle",
    "CandleSeries",
    "DataIncompleteError",
    "IndicatorValues",
    "ScreeningResult",
    "ScreeningStatus",
    "SignalEvent",
    "SignalType",
    "ema5_ema20_cross",
    "evaluate_candidate",
    "price_ema20_breakout",
    "rsi_cross",
]
