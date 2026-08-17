"""Tests der Wertobjekte selbst -- unabhaengig von Kalender und Filterregel."""

from __future__ import annotations

from datetime import UTC, date, datetime

from ai_trading_analyst.domain.earnings import (
    EarningsFilterResult,
    EarningsFilterStatus,
    NextEarningsDate,
)


def test_next_earnings_date_ist_unveraenderlich() -> None:
    termin = NextEarningsDate(
        date=date(2026, 9, 1), source="finnhub", retrieved_at=datetime.now(UTC)
    )
    assert termin.date == date(2026, 9, 1)
    assert termin.source == "finnhub"


def test_earnings_filter_result_ohne_termin_hat_keine_kerzenangabe() -> None:
    result = EarningsFilterResult(
        status=EarningsFilterStatus.UNKNOWN,
        evaluated_at=datetime.now(UTC),
        reason="no_coverage",
    )
    assert result.next_earnings_date is None
    assert result.candles_until_earnings is None
    assert result.source is None
