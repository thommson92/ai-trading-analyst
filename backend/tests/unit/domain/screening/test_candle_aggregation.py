"""Bildung der 195-Minuten-Kerzen aus nativen Bars.

Die Testdaten sind bewusst echte Handelstage in ``America/New_York``, damit
Sommer-/Winterzeit und der Sitzungsbeginn 09:30 tatsaechlich mitgeprueft
werden und nicht nur eine Rechnung auf UTC-Offsets.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from ai_trading_analyst.domain.screening.candle_aggregation import (
    CandleAggregationError,
    IntradayBar,
    SessionParameters,
    aggregate_intraday_bars,
)

NEW_YORK = ZoneInfo("America/New_York")
PARAMETERS = SessionParameters(
    timezone="America/New_York",
    session_open=time(9, 30),
    session_minutes=390,
    timeframe_minutes=195,
)
BARS_PER_CANDLE = 13


def bars_for_session(
    session_date: date, count: int, first_close: float = 100.0, step: float = 1.0
) -> list[IntradayBar]:
    """Fortlaufende 15-Minuten-Bars ab Sitzungsbeginn des angegebenen Tages."""
    session_start = datetime.combine(session_date, time(9, 30), tzinfo=NEW_YORK)
    return [
        IntradayBar(
            start=session_start + timedelta(minutes=15 * index),
            open=first_close + step * index,
            high=first_close + step * index + 0.5,
            low=first_close + step * index - 0.5,
            close=first_close + step * index,
            volume=1_000.0,
        )
        for index in range(count)
    ]


class TestVollstaendigeSitzung:
    def test_ein_voller_handelstag_ergibt_genau_zwei_kerzen(self) -> None:
        candles = aggregate_intraday_bars(bars_for_session(date(2026, 3, 10), 26), 15, PARAMETERS)
        assert len(candles) == 2
        assert [candle.daily_candle_index for candle in candles] == [1, 2]

    def test_die_kerze_traegt_den_zeitstempel_ihres_beginns(self) -> None:
        candles = aggregate_intraday_bars(bars_for_session(date(2026, 3, 10), 26), 15, PARAMETERS)
        assert candles[0].timestamp == datetime(2026, 3, 10, 9, 30, tzinfo=NEW_YORK)
        assert candles[1].timestamp == datetime(2026, 3, 10, 12, 45, tzinfo=NEW_YORK)

    def test_ohlcv_wird_korrekt_zusammengefasst(self) -> None:
        bars = bars_for_session(date(2026, 3, 10), BARS_PER_CANDLE)
        candle = aggregate_intraday_bars(bars, 15, PARAMETERS)[0]
        assert candle.open == bars[0].open
        assert candle.close == bars[-1].close
        assert candle.high == max(bar.high for bar in bars)
        assert candle.low == min(bar.low for bar in bars)
        assert candle.volume == sum(bar.volume for bar in bars)

    def test_die_reihenfolge_der_eingehenden_bars_ist_egal(self) -> None:
        bars = bars_for_session(date(2026, 3, 10), BARS_PER_CANDLE)
        aus_reihenfolge = aggregate_intraday_bars(list(reversed(bars)), 15, PARAMETERS)
        assert aus_reihenfolge == aggregate_intraday_bars(bars, 15, PARAMETERS)

    def test_bars_in_utc_werden_in_die_boersenzeitzone_umgerechnet(self) -> None:
        lokal = bars_for_session(date(2026, 3, 10), BARS_PER_CANDLE)
        in_utc = [
            IntradayBar(
                start=bar.start.astimezone(UTC),
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            for bar in lokal
        ]
        assert aggregate_intraday_bars(in_utc, 15, PARAMETERS) == aggregate_intraday_bars(
            lokal, 15, PARAMETERS
        )


class TestNurAbgeschlosseneKerzen:
    def test_eine_laufende_kerze_wird_nicht_geliefert(self) -> None:
        # Zwoelf statt dreizehn Bars: die Kerze laeuft noch.
        candles = aggregate_intraday_bars(bars_for_session(date(2026, 3, 10), 12), 15, PARAMETERS)
        assert candles == ()

    def test_die_erste_kerze_bleibt_erhalten_waehrend_die_zweite_noch_laeuft(self) -> None:
        candles = aggregate_intraday_bars(bars_for_session(date(2026, 3, 10), 20), 15, PARAMETERS)
        assert [candle.daily_candle_index for candle in candles] == [1]

    def test_ein_verkuerzter_handelstag_liefert_nur_die_vollstaendige_kerze(self) -> None:
        # Frueher Schluss um 13:00 -- die zweite Kerze wird nie vollstaendig.
        candles = aggregate_intraday_bars(bars_for_session(date(2026, 11, 27), 14), 15, PARAMETERS)
        assert [candle.daily_candle_index for candle in candles] == [1]

    def test_eine_luecke_mitten_in_der_kerze_verhindert_sie(self) -> None:
        bars = bars_for_session(date(2026, 3, 10), BARS_PER_CANDLE)
        del bars[5]
        assert aggregate_intraday_bars(bars, 15, PARAMETERS) == ()


class TestSitzungsgrenzen:
    def test_bars_vor_sitzungsbeginn_werden_verworfen(self) -> None:
        vorboerslich = IntradayBar(
            start=datetime(2026, 3, 10, 8, 0, tzinfo=NEW_YORK),
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=1.0,
        )
        bars = [vorboerslich, *bars_for_session(date(2026, 3, 10), BARS_PER_CANDLE)]
        candles = aggregate_intraday_bars(bars, 15, PARAMETERS)
        assert len(candles) == 1
        assert candles[0].low > 1.0

    def test_bars_nach_sitzungsende_werden_verworfen(self) -> None:
        nachboerslich = IntradayBar(
            start=datetime(2026, 3, 10, 17, 0, tzinfo=NEW_YORK),
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=1.0,
        )
        bars = [*bars_for_session(date(2026, 3, 10), 26), nachboerslich]
        assert len(aggregate_intraday_bars(bars, 15, PARAMETERS)) == 2

    def test_mehrere_handelstage_bleiben_getrennt_und_chronologisch(self) -> None:
        bars = bars_for_session(date(2026, 3, 10), 26) + bars_for_session(date(2026, 3, 11), 26)
        candles = aggregate_intraday_bars(bars, 15, PARAMETERS)
        assert len(candles) == 4
        assert [candle.daily_candle_index for candle in candles] == [1, 2, 1, 2]
        assert list(candles) == sorted(candles, key=lambda candle: candle.timestamp)

    def test_die_zeitumstellung_verschiebt_den_sitzungsbeginn_nicht(self) -> None:
        # 2026-03-08 ist der Umstellungstag; der Montag danach beginnt
        # weiterhin um 09:30 Ortszeit, nicht um 08:30.
        candles = aggregate_intraday_bars(bars_for_session(date(2026, 3, 9), 26), 15, PARAMETERS)
        assert candles[0].timestamp.utcoffset() == timedelta(hours=-4)
        assert len(candles) == 2


class TestFehlerhafteEingaben:
    def test_naiver_zeitstempel_wird_abgelehnt(self) -> None:
        naiv = IntradayBar(
            start=datetime(2026, 3, 10, 9, 30),  # noqa: DTZ001 -- genau das ist der Testfall
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=1.0,
        )
        with pytest.raises(CandleAggregationError, match="Zeitzone"):
            aggregate_intraday_bars([naiv], 15, PARAMETERS)

    def test_doppelt_gelieferter_bar_wird_abgelehnt(self) -> None:
        bars = bars_for_session(date(2026, 3, 10), BARS_PER_CANDLE)
        with pytest.raises(CandleAggregationError, match="doppelt"):
            aggregate_intraday_bars([*bars, bars[0]], 15, PARAMETERS)

    def test_nicht_teilbare_bar_groesse_wird_abgelehnt(self) -> None:
        with pytest.raises(CandleAggregationError, match="ohne Rest"):
            aggregate_intraday_bars(bars_for_session(date(2026, 3, 10), 4), 30, PARAMETERS)

    def test_bar_groesse_null_wird_abgelehnt(self) -> None:
        with pytest.raises(CandleAggregationError, match="groesser als 0"):
            aggregate_intraday_bars([], 0, PARAMETERS)

    def test_sitzung_die_nicht_in_kerzen_aufgeht_wird_abgelehnt(self) -> None:
        with pytest.raises(CandleAggregationError, match="Vielfaches"):
            SessionParameters(
                timezone="America/New_York",
                session_open=time(9, 30),
                session_minutes=400,
                timeframe_minutes=195,
            )
