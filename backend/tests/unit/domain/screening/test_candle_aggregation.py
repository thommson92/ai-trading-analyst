"""Bildung der 195-Minuten-Kerzen aus nativen Bars.

Die Testdaten sind bewusst echte Handelstage in ``America/New_York``, damit
Sommer-/Winterzeit und der Sitzungsbeginn 09:30 tatsaechlich mitgeprueft
werden und nicht nur eine Rechnung auf UTC-Offsets.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from ai_trading_analyst.domain.screening import Candle
from ai_trading_analyst.domain.screening.candle_aggregation import (
    CandleAggregationError,
    IncompleteReason,
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
    early_close=time(13, 0),
)
BARS_PER_CANDLE = 13


def aggregate(
    bars: list[IntradayBar], native_bar_minutes: int, parameters: SessionParameters
) -> tuple[Candle, ...]:
    """Kurzform fuer die Faelle, in denen nur die fertigen Kerzen zaehlen."""
    return aggregate_intraday_bars(bars, native_bar_minutes, parameters).candles


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
        candles = aggregate(bars_for_session(date(2026, 3, 10), 26), 15, PARAMETERS)
        assert len(candles) == 2
        assert [candle.daily_candle_index for candle in candles] == [1, 2]

    def test_die_kerze_traegt_den_zeitstempel_ihres_beginns(self) -> None:
        candles = aggregate(bars_for_session(date(2026, 3, 10), 26), 15, PARAMETERS)
        assert candles[0].timestamp == datetime(2026, 3, 10, 9, 30, tzinfo=NEW_YORK)
        assert candles[1].timestamp == datetime(2026, 3, 10, 12, 45, tzinfo=NEW_YORK)

    def test_ohlcv_wird_korrekt_zusammengefasst(self) -> None:
        bars = bars_for_session(date(2026, 3, 10), BARS_PER_CANDLE)
        candle = aggregate(bars, 15, PARAMETERS)[0]
        assert candle.open == bars[0].open
        assert candle.close == bars[-1].close
        assert candle.high == max(bar.high for bar in bars)
        assert candle.low == min(bar.low for bar in bars)
        assert candle.volume == sum(bar.volume for bar in bars)

    def test_die_reihenfolge_der_eingehenden_bars_ist_egal(self) -> None:
        bars = bars_for_session(date(2026, 3, 10), BARS_PER_CANDLE)
        aus_reihenfolge = aggregate(list(reversed(bars)), 15, PARAMETERS)
        assert aus_reihenfolge == aggregate(bars, 15, PARAMETERS)

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
        assert aggregate(in_utc, 15, PARAMETERS) == aggregate(
            lokal, 15, PARAMETERS
        )


class TestNurAbgeschlosseneKerzen:
    def test_eine_laufende_kerze_wird_nicht_geliefert(self) -> None:
        # Zwoelf statt dreizehn Bars: die Kerze laeuft noch.
        candles = aggregate(bars_for_session(date(2026, 3, 10), 12), 15, PARAMETERS)
        assert candles == ()

    def test_die_erste_kerze_bleibt_erhalten_waehrend_die_zweite_noch_laeuft(self) -> None:
        candles = aggregate(bars_for_session(date(2026, 3, 10), 20), 15, PARAMETERS)
        assert [candle.daily_candle_index for candle in candles] == [1]

    def test_ein_verkuerzter_handelstag_liefert_nur_die_vollstaendige_kerze(self) -> None:
        # Frueher Schluss um 13:00 -- die zweite Kerze wird nie vollstaendig.
        candles = aggregate(bars_for_session(date(2026, 11, 27), 14), 15, PARAMETERS)
        assert [candle.daily_candle_index for candle in candles] == [1]

    def test_eine_luecke_mitten_in_der_kerze_verhindert_sie(self) -> None:
        bars = bars_for_session(date(2026, 3, 10), BARS_PER_CANDLE)
        del bars[5]
        assert aggregate(bars, 15, PARAMETERS) == ()


class TestUnvollstaendigeKerzenWerdenGemeldet:
    """Ohne diese Meldung waere eine Datenluecke von einer laufenden Kerze
    nicht mehr zu unterscheiden -- und die verbleibenden Kerzen waeren
    scheinbar zusammenhaengend."""

    def test_die_laufende_kerze_wird_als_unvollstaendig_ausgewiesen(self) -> None:
        ergebnis = aggregate_intraday_bars(
            bars_for_session(date(2026, 3, 10), 20), 15, PARAMETERS
        )
        assert len(ergebnis.candles) == 1
        assert len(ergebnis.incomplete) == 1
        assert ergebnis.incomplete[0].daily_candle_index == 2
        assert ergebnis.incomplete[0].received_bars == 7
        assert ergebnis.incomplete[0].expected_bars == 13

    def test_eine_luecke_mitten_in_der_historie_wird_ausgewiesen(self) -> None:
        bars = bars_for_session(date(2026, 3, 10), 26) + bars_for_session(date(2026, 3, 11), 26)
        del bars[3]
        ergebnis = aggregate_intraday_bars(bars, 15, PARAMETERS)

        assert len(ergebnis.candles) == 3
        assert len(ergebnis.incomplete) == 1
        luecke = ergebnis.incomplete[0]
        assert luecke.timestamp == datetime(2026, 3, 10, 9, 30, tzinfo=NEW_YORK)
        assert luecke.timestamp < ergebnis.candles[-1].timestamp

    def test_eine_lueckenlose_historie_meldet_nichts(self) -> None:
        ergebnis = aggregate_intraday_bars(
            bars_for_session(date(2026, 3, 10), 26), 15, PARAMETERS
        )
        assert ergebnis.incomplete == ()


class TestVerkuerzterHandelstagIstKeineLuecke:
    """Der 28.11.2025 (Tag nach Thanksgiving) schloss um 13:00 statt 16:00.

    Die zweite Kerze bekam genau einen Bar. Das sah zunaechst wie eine
    Datenluecke aus, ist aber das Gegenteil: Es hat schlicht nicht mehr
    Handel gegeben. Live gegen die TWS aufgetreten, siehe ADR 0014.
    """

    @staticmethod
    def _thanksgiving_freitag() -> list[IntradayBar]:
        # 09:30-13:00 = 14 Bars: 13 fuer die erste Kerze, einer fuer die zweite.
        return bars_for_session(date(2025, 11, 28), 14)

    def test_die_zweite_kerze_gilt_als_sitzungsende(self) -> None:
        ergebnis = aggregate_intraday_bars(self._thanksgiving_freitag(), 15, PARAMETERS)
        assert len(ergebnis.candles) == 1
        assert len(ergebnis.incomplete) == 1
        assert ergebnis.incomplete[0].reason is IncompleteReason.SESSION_ENDED
        assert ergebnis.incomplete[0].received_bars == 1

    def test_auch_mitten_in_der_historie(self) -> None:
        bars = (
            bars_for_session(date(2025, 11, 26), 26)
            + self._thanksgiving_freitag()
            + bars_for_session(date(2025, 12, 1), 26)
        )
        ergebnis = aggregate_intraday_bars(bars, 15, PARAMETERS)
        assert len(ergebnis.candles) == 5
        assert [gap.reason for gap in ergebnis.incomplete] == [
            IncompleteReason.SESSION_ENDED
        ]

    def test_fehlende_bars_mit_weiterem_handel_danach_gelten_nicht_als_sitzungsende(
        self,
    ) -> None:
        bars = bars_for_session(date(2026, 3, 10), 26)
        del bars[5]  # mitten in der ersten Kerze, der Tag lief weiter
        ergebnis = aggregate_intraday_bars(bars, 15, PARAMETERS)
        assert [gap.reason for gap in ergebnis.incomplete] == [IncompleteReason.DATA_GAP]

    def test_ein_loch_kurz_vor_sitzungsende_ist_kein_sitzungsende(self) -> None:
        # Bars bis 13:00, aber der Bar um 12:45 fehlt: Die vorhandenen Bars
        # liegen weder am Anfang noch am Ende des Fensters an -- da fehlt
        # wirklich etwas.
        bars = bars_for_session(date(2025, 11, 28), 16)
        del bars[13]
        ergebnis = aggregate_intraday_bars(bars, 15, PARAMETERS)
        assert [gap.reason for gap in ergebnis.incomplete] == [IncompleteReason.DATA_GAP]

    def test_die_laufende_kerze_am_ende_gilt_ebenfalls_als_sitzungsende(self) -> None:
        ergebnis = aggregate_intraday_bars(
            bars_for_session(date(2026, 3, 10), 20), 15, PARAMETERS
        )
        assert ergebnis.incomplete[0].reason is IncompleteReason.SESSION_ENDED


class TestSpaeterHandelsbeginnIstKeineLuecke:
    """Der erste Handelstag nach einem Boersengang beginnt nicht um 09:30.

    Die Eroeffnungsauktion findet Stunden spaeter statt; davor gibt es den
    Kurs schlicht nicht. Live gegen die TWS aufgetreten (SPCX, 12.06.2026:
    4 von 13 Bars in der ersten Kerze) und ebenso nach einer
    Eroeffnungsunterbrechung.
    """

    @staticmethod
    def _erster_handelstag(erster_bar_index: int) -> list[IntradayBar]:
        return bars_for_session(date(2026, 6, 12), 26)[erster_bar_index:]

    def test_die_erste_kerze_des_tages_gilt_als_spaeter_beginn(self) -> None:
        # Handel ab 11:45: vier Bars bis 12:45, danach der volle Nachmittag.
        ergebnis = aggregate_intraday_bars(self._erster_handelstag(9), 15, PARAMETERS)

        assert len(ergebnis.candles) == 1  # die zweite Kerze des Tages
        assert [gap.reason for gap in ergebnis.incomplete] == [
            IncompleteReason.SESSION_STARTED_LATE
        ]
        assert ergebnis.incomplete[0].received_bars == 4

    def test_auch_wenn_nur_ein_einziger_bar_fehlt(self) -> None:
        """Der Fall LKQ vom 26.01.2026: 12 von 13 Bars, Handelsbeginn 09:45."""
        ergebnis = aggregate_intraday_bars(self._erster_handelstag(1), 15, PARAMETERS)
        assert [gap.reason for gap in ergebnis.incomplete] == [
            IncompleteReason.SESSION_STARTED_LATE
        ]

    def test_ein_spaeter_beginn_an_einem_folgetag_bleibt_eine_luecke(self) -> None:
        """Die zweite Kerze eines Tages kann nicht 'spaet beginnen'.

        Wenn am selben Tag vormittags gehandelt wurde, ist ein fehlender Bar
        um 12:45 kein Handelsbeginn, sondern ein Loch zwischen zwei
        gehandelten Zeitraeumen.
        """
        bars = bars_for_session(date(2026, 3, 10), 26)
        del bars[13]
        ergebnis = aggregate_intraday_bars(bars, 15, PARAMETERS)
        assert [gap.reason for gap in ergebnis.incomplete] == [IncompleteReason.DATA_GAP]

    def test_der_erste_fehlende_bar_wird_benannt(self) -> None:
        ergebnis = aggregate_intraday_bars(self._erster_handelstag(9), 15, PARAMETERS)
        assert ergebnis.incomplete[0].first_missing_bar == datetime(
            2026, 6, 12, 9, 30, tzinfo=NEW_YORK
        )

    def test_der_erste_fehlende_bar_wird_auch_mitten_im_fenster_benannt(self) -> None:
        bars = bars_for_session(date(2026, 3, 10), 26)
        del bars[5]
        ergebnis = aggregate_intraday_bars(bars, 15, PARAMETERS)
        assert ergebnis.incomplete[0].first_missing_bar == datetime(
            2026, 3, 10, 10, 45, tzinfo=NEW_YORK
        )


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
        candles = aggregate(bars, 15, PARAMETERS)
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
        assert len(aggregate(bars, 15, PARAMETERS)) == 2

    def test_mehrere_handelstage_bleiben_getrennt_und_chronologisch(self) -> None:
        bars = bars_for_session(date(2026, 3, 10), 26) + bars_for_session(date(2026, 3, 11), 26)
        candles = aggregate(bars, 15, PARAMETERS)
        assert len(candles) == 4
        assert [candle.daily_candle_index for candle in candles] == [1, 2, 1, 2]
        assert list(candles) == sorted(candles, key=lambda candle: candle.timestamp)

    def test_die_zeitumstellung_verschiebt_den_sitzungsbeginn_nicht(self) -> None:
        # 2026-03-08 ist der Umstellungstag; der Montag danach beginnt
        # weiterhin um 09:30 Ortszeit, nicht um 08:30.
        candles = aggregate(bars_for_session(date(2026, 3, 9), 26), 15, PARAMETERS)
        assert candles[0].timestamp.utcoffset() == timedelta(hours=-4)
        assert len(candles) == 2


class TestFehlerhafteEingaben:
    def test_ein_bar_neben_dem_zeitraster_wird_abgelehnt(self) -> None:
        """Sonst entstuende eine Kerze mit richtiger Bar-Anzahl, falschem
        Eroeffnungskurs und falschem Zeitraster -- und niemand saehe es."""
        bars = bars_for_session(date(2026, 3, 10), BARS_PER_CANDLE)
        bars[0] = IntradayBar(
            start=datetime(2026, 3, 10, 9, 37, tzinfo=NEW_YORK),
            open=999.0,
            high=999.0,
            low=999.0,
            close=999.0,
            volume=1.0,
        )
        with pytest.raises(CandleAggregationError, match="Raster"):
            aggregate(bars, 15, PARAMETERS)

    def test_ein_zusaetzlicher_bar_neben_dem_raster_wird_ebenfalls_abgelehnt(self) -> None:
        bars = bars_for_session(date(2026, 3, 10), BARS_PER_CANDLE)
        bars.append(
            IntradayBar(
                start=datetime(2026, 3, 10, 9, 37, tzinfo=NEW_YORK),
                open=999.0,
                high=999.0,
                low=999.0,
                close=999.0,
                volume=1.0,
            )
        )
        with pytest.raises(CandleAggregationError, match="Raster"):
            aggregate(bars, 15, PARAMETERS)

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
            aggregate([naiv], 15, PARAMETERS)

    def test_doppelt_gelieferter_bar_wird_abgelehnt(self) -> None:
        bars = bars_for_session(date(2026, 3, 10), BARS_PER_CANDLE)
        with pytest.raises(CandleAggregationError, match="doppelt"):
            aggregate([*bars, bars[0]], 15, PARAMETERS)

    def test_nicht_teilbare_bar_groesse_wird_abgelehnt(self) -> None:
        with pytest.raises(CandleAggregationError, match="ohne Rest"):
            aggregate(bars_for_session(date(2026, 3, 10), 4), 30, PARAMETERS)

    def test_bar_groesse_null_wird_abgelehnt(self) -> None:
        with pytest.raises(CandleAggregationError, match="groesser als 0"):
            aggregate([], 0, PARAMETERS)

    def test_sitzung_die_nicht_in_kerzen_aufgeht_wird_abgelehnt(self) -> None:
        with pytest.raises(CandleAggregationError, match="Vielfaches"):
            SessionParameters(
                timezone="America/New_York",
                session_open=time(9, 30),
                session_minutes=400,
                timeframe_minutes=195,
                early_close=time(13, 0),
            )
