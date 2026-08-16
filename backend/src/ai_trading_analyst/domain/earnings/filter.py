"""Reine Ausschlussentscheidung des Earnings-Filters (Doc 10, Paragraph 6.5).

Kein Providerzugriff hier -- diese Funktion entscheidet ausschliesslich
anhand eines bereits aufgeloesten ``NextEarningsDate | None``. Der Zugriff
auf den Anbieter liegt in der Infrastruktur- und Application-Schicht.
"""

from __future__ import annotations

from datetime import date, datetime

from .calendar import count_future_trading_candles
from .values import (
    EarningsFilterParameters,
    EarningsFilterResult,
    EarningsFilterStatus,
    NextEarningsDate,
)


def evaluate_earnings_filter(
    next_earnings: NextEarningsDate | None,
    as_of: date,
    params: EarningsFilterParameters,
    evaluated_at: datetime,
) -> EarningsFilterResult:
    """Entscheidet, ob eine Aktie wegen bevorstehender Quartalszahlen
    ausgeschlossen wird.

    ``next_earnings=None`` ergibt immer ``UNKNOWN`` -- fehlende Abdeckung
    wird nie stillschweigend als unbedenklich gewertet (ADR 0017 L3).
    """
    if next_earnings is None:
        return EarningsFilterResult(
            status=EarningsFilterStatus.UNKNOWN,
            evaluated_at=evaluated_at,
            reason="no_coverage",
        )

    candles_until_earnings = count_future_trading_candles(
        as_of=as_of,
        earnings_date=next_earnings.date,
        candles_per_day=params.candles_per_day,
    )

    status = (
        EarningsFilterStatus.EARNINGS_EXCLUDED
        if candles_until_earnings <= params.configured_exclusion_candles
        else EarningsFilterStatus.EARNINGS_CLEAR
    )

    return EarningsFilterResult(
        status=status,
        evaluated_at=evaluated_at,
        next_earnings_date=next_earnings.date,
        candles_until_earnings=candles_until_earnings,
        source=next_earnings.source,
    )
