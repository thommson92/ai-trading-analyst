"""Tests der reinen Ausschlussentscheidung ``evaluate_earnings_filter``."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from ai_trading_analyst.domain.earnings import (
    EarningsFilterParameters,
    EarningsFilterStatus,
    NextEarningsDate,
    evaluate_earnings_filter,
)

AS_OF = date(2026, 8, 17)
EVALUATED_AT = datetime(2026, 8, 17, 12, 45, tzinfo=UTC)
PARAMS = EarningsFilterParameters(configured_exclusion_candles=20, candles_per_day=2)


def _termin(tage_nach_as_of: int) -> NextEarningsDate:
    return NextEarningsDate(
        date=AS_OF + timedelta(days=tage_nach_as_of),
        source="finnhub",
        retrieved_at=EVALUATED_AT,
    )


def test_kein_termin_ergibt_unknown_mit_grund() -> None:
    result = evaluate_earnings_filter(None, AS_OF, PARAMS, EVALUATED_AT)
    assert result.status is EarningsFilterStatus.UNKNOWN
    assert result.reason == "no_coverage"
    assert result.candles_until_earnings is None


def test_termin_innerhalb_des_fensters_schliesst_aus() -> None:
    # 3 Tage voraus = 6 Kerzen, deutlich innerhalb der 20-Kerzen-Schwelle.
    result = evaluate_earnings_filter(_termin(3), AS_OF, PARAMS, EVALUATED_AT)
    assert result.status is EarningsFilterStatus.EARNINGS_EXCLUDED
    assert result.candles_until_earnings == 6
    assert result.source == "finnhub"
    assert result.reason is None


def test_termin_genau_an_der_schwelle_schliesst_noch_aus() -> None:
    # 10 Handelstage (kein Wochenende dazwischen relevant) = 20 Kerzen exakt.
    result = evaluate_earnings_filter(_termin(14), AS_OF, PARAMS, EVALUATED_AT)
    assert result.candles_until_earnings == 20
    assert result.status is EarningsFilterStatus.EARNINGS_EXCLUDED


def test_termin_eine_kerze_ueber_der_schwelle_ist_frei() -> None:
    result = evaluate_earnings_filter(_termin(15), AS_OF, PARAMS, EVALUATED_AT)
    assert result.candles_until_earnings == 22
    assert result.status is EarningsFilterStatus.EARNINGS_CLEAR


def test_termin_weit_in_der_zukunft_ist_frei() -> None:
    result = evaluate_earnings_filter(_termin(60), AS_OF, PARAMS, EVALUATED_AT)
    assert result.status is EarningsFilterStatus.EARNINGS_CLEAR
