from datetime import UTC, datetime, timedelta

import pytest

from ibkrspike.timeframe import EXCHANGE_TZ, Bar, TimeframeError, aggregate_to_195_minutes


def _ny_bars(day: str, start_hour: int, start_minute: int, count: int, minutes: int) -> list[Bar]:
    start = datetime.fromisoformat(f"{day}T{start_hour:02d}:{start_minute:02d}:00").replace(
        tzinfo=EXCHANGE_TZ
    )
    return [
        Bar(
            timestamp=start + timedelta(minutes=minutes * i),
            open=100.0 + i,
            high=101.0 + i,
            low=99.0 + i,
            close=100.5 + i,
            volume=10.0 + i,
        )
        for i in range(count)
    ]


def test_volle_195_minuten_aus_13_mal_15_minuten_ergeben_eine_vollstaendige_kerze() -> None:
    bars = _ny_bars("2026-08-06", 9, 30, count=13, minutes=15)

    result = aggregate_to_195_minutes(bars, native_bar_minutes=15)

    assert len(result.candles) == 1
    candle = result.candles[0]
    assert candle.bucket_index == 0
    assert candle.bar_count == 13
    assert candle.is_complete is True
    assert candle.open == bars[0].open
    assert candle.close == bars[-1].close
    assert candle.high == max(b.high for b in bars)
    assert candle.low == min(b.low for b in bars)
    assert candle.volume == sum(b.volume for b in bars)
    assert result.bars_outside_session == []


def test_ein_voller_handelstag_ergibt_genau_zwei_kerzen() -> None:
    # 390 Minuten Sitzung (09:30-16:00) / 15-Minuten-Bars = 26 Bars = 2 Kerzen.
    bars = _ny_bars("2026-08-06", 9, 30, count=26, minutes=15)

    result = aggregate_to_195_minutes(bars, native_bar_minutes=15)

    assert len(result.candles) == 2
    assert [c.bucket_index for c in result.candles] == [0, 1]
    assert all(c.is_complete for c in result.candles)
    assert all(c.bar_count == 13 for c in result.candles)


def test_unvollstaendiger_letzter_bucket_wird_als_unvollstaendig_markiert() -> None:
    bars = _ny_bars("2026-08-06", 9, 30, count=20, minutes=15)  # 1 volle + 7 Bars

    result = aggregate_to_195_minutes(bars, native_bar_minutes=15)

    assert len(result.candles) == 2
    assert result.candles[0].is_complete is True
    assert result.candles[1].is_complete is False
    assert result.candles[1].bar_count == 7


def test_bars_vor_seesionbeginn_werden_ausgeschlossen_nicht_stillschweigend_verrechnet() -> None:
    pre_market = _ny_bars("2026-08-06", 8, 0, count=2, minutes=15)
    regular = _ny_bars("2026-08-06", 9, 30, count=13, minutes=15)

    result = aggregate_to_195_minutes(pre_market + regular, native_bar_minutes=15)

    assert len(result.candles) == 1
    assert len(result.bars_outside_session) == 2


def test_mehrere_handelstage_ergeben_getrennte_kerzen() -> None:
    day1 = _ny_bars("2026-08-06", 9, 30, count=13, minutes=15)
    day2 = _ny_bars("2026-08-07", 9, 30, count=13, minutes=15)

    result = aggregate_to_195_minutes(day1 + day2, native_bar_minutes=15)

    assert len(result.candles) == 2
    assert result.candles[0].session_date.isoformat() == "2026-08-06"
    assert result.candles[1].session_date.isoformat() == "2026-08-07"


def test_utc_zeitstempel_werden_korrekt_in_new_york_zeit_umgerechnet() -> None:
    # 13:30 UTC == 09:30 America/New_York im August (EDT, UTC-4).
    utc_start = datetime(2026, 8, 6, 13, 30, tzinfo=UTC)
    bars = [
        Bar(
            timestamp=utc_start + timedelta(minutes=15 * i),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=10.0,
        )
        for i in range(13)
    ]

    result = aggregate_to_195_minutes(bars, native_bar_minutes=15)

    assert len(result.candles) == 1
    assert result.candles[0].bar_count == 13
    assert result.candles[0].session_date.isoformat() == "2026-08-06"


def test_naive_zeitstempel_wird_abgelehnt() -> None:
    bar = Bar(
        timestamp=datetime(2026, 8, 6, 9, 30),  # noqa: DTZ001 -- bewusst naiv fuer diesen Test
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10.0,
    )

    with pytest.raises(TimeframeError, match="naiv"):
        aggregate_to_195_minutes([bar], native_bar_minutes=15)


def test_nicht_teilbare_native_bar_groesse_wird_abgelehnt() -> None:
    bars = _ny_bars("2026-08-06", 9, 30, count=5, minutes=30)

    with pytest.raises(TimeframeError, match="teilbar"):
        aggregate_to_195_minutes(bars, native_bar_minutes=30)
