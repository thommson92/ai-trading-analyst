"""Die Zeitrechnung des Dispatchers.

Reine Logik, deshalb hier und nicht im Integrationstest: Gerade die
Sonderfaelle -- verkuerzter Handelstag, Zeitumstellung, Wochenende -- treten
selten genug auf, dass man sie nicht abwarten will.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ai_trading_analyst.domain.scheduling import (
    DispatchDecision,
    SchedulerParameters,
    TradingSession,
    assumed_session,
    scheduled_run_for,
)

NEW_YORK = ZoneInfo("America/New_York")
PARAMETER = SchedulerParameters(
    timeframe_minutes=195,
    daily_candle_index=1,
    safety_buffer_seconds=300,
    max_catch_up_seconds=4 * 3600,
    timezone="America/New_York",
    session_open=time(9, 30),
    session_minutes=390,
)


def sitzung(tag: date, schluss: time = time(16, 0)) -> TradingSession:
    return TradingSession(
        session_date=tag,
        open=datetime.combine(tag, time(9, 30), tzinfo=NEW_YORK),
        close=datetime.combine(tag, schluss, tzinfo=NEW_YORK),
    )


class TestZielkerze:
    def test_die_erste_kerze_endet_um_12_45(self) -> None:
        geplant = scheduled_run_for(sitzung(date(2026, 8, 14)), PARAMETER)

        assert geplant is not None
        assert geplant.candle_close == datetime(2026, 8, 14, 12, 45, tzinfo=NEW_YORK)

    def test_der_fruehestmoegliche_start_liegt_um_12_50(self) -> None:
        """Die Kerze ist zu, beim Anbieter aber nicht zwingend vollstaendig."""
        geplant = scheduled_run_for(sitzung(date(2026, 8, 14)), PARAMETER)

        assert geplant is not None
        assert geplant.earliest_start == datetime(2026, 8, 14, 12, 50, tzinfo=NEW_YORK)

    def test_ein_verkuerzter_tag_gibt_die_erste_kerze_noch_her(self) -> None:
        """Schluss um 13:00 -- die erste Kerze endet um 12:45 und zaehlt."""
        geplant = scheduled_run_for(sitzung(date(2025, 11, 28), time(13, 0)), PARAMETER)

        assert geplant is not None
        assert geplant.candle_close == datetime(2025, 11, 28, 12, 45, tzinfo=NEW_YORK)

    def test_die_zweite_kerze_gibt_ein_verkuerzter_tag_nicht_her(self) -> None:
        """Der Grund, warum die Sitzung und nicht die Uhrzeit entscheidet."""
        zweite = SchedulerParameters(
            timeframe_minutes=195,
            daily_candle_index=2,
            safety_buffer_seconds=300,
            max_catch_up_seconds=4 * 3600,
            timezone="America/New_York",
            session_open=time(9, 30),
            session_minutes=390,
        )

        assert scheduled_run_for(sitzung(date(2025, 11, 28), time(13, 0)), zweite) is None

    def test_an_einem_vollen_tag_gibt_es_die_zweite_kerze(self) -> None:
        zweite = SchedulerParameters(
            timeframe_minutes=195,
            daily_candle_index=2,
            safety_buffer_seconds=300,
            max_catch_up_seconds=4 * 3600,
            timezone="America/New_York",
            session_open=time(9, 30),
            session_minutes=390,
        )
        geplant = scheduled_run_for(sitzung(date(2026, 8, 14)), zweite)

        assert geplant is not None
        assert geplant.candle_close == datetime(2026, 8, 14, 16, 0, tzinfo=NEW_YORK)


class TestEntscheidung:
    def _geplant(self) -> object:
        geplant = scheduled_run_for(sitzung(date(2026, 8, 14)), PARAMETER)
        assert geplant is not None
        return geplant

    def test_vor_dem_puffer_ist_es_zu_frueh(self) -> None:
        geplant = self._geplant()
        jetzt = datetime(2026, 8, 14, 12, 46, tzinfo=NEW_YORK)
        assert geplant.decide(jetzt) is DispatchDecision.TOO_EARLY  # type: ignore[attr-defined]

    def test_ab_dem_puffer_wird_gerechnet(self) -> None:
        geplant = self._geplant()
        jetzt = datetime(2026, 8, 14, 12, 50, tzinfo=NEW_YORK)
        assert geplant.decide(jetzt) is DispatchDecision.RUN  # type: ignore[attr-defined]

    def test_nach_der_nachholfrist_nicht_mehr(self) -> None:
        geplant = self._geplant()
        jetzt = datetime(2026, 8, 14, 17, 0, tzinfo=NEW_YORK)
        assert geplant.decide(jetzt) is DispatchDecision.TOO_LATE  # type: ignore[attr-defined]

    def test_der_deutsche_abend_faellt_ins_fenster(self) -> None:
        """Die Aufgabenplanung startet in deutscher Zeit -- 18:50 dort sind
        12:50 in New York."""
        geplant = self._geplant()
        jetzt = datetime(2026, 8, 14, 18, 50, tzinfo=ZoneInfo("Europe/Berlin"))
        assert geplant.decide(jetzt) is DispatchDecision.RUN  # type: ignore[attr-defined]

    def test_auch_waehrend_der_auseinanderlaufenden_zeitumstellung(self) -> None:
        """Ende Maerz: Die USA haben umgestellt, Europa noch nicht -- 12:50
        New Yorker Zeit sind dann 17:50 statt 18:50 bei uns."""
        geplant = scheduled_run_for(sitzung(date(2026, 3, 20)), PARAMETER)
        assert geplant is not None

        deutsch = datetime(2026, 3, 20, 17, 50, tzinfo=ZoneInfo("Europe/Berlin"))
        assert geplant.decide(deutsch) is DispatchDecision.RUN


class TestAngenommeneSitzung:
    """Der Notbehelf, wenn der Kalender nicht abrufbar ist."""

    def test_ein_wochentag_ergibt_die_uebliche_sitzung(self) -> None:
        angenommen = assumed_session(date(2026, 8, 14), PARAMETER)

        assert angenommen is not None
        assert angenommen.open == datetime(2026, 8, 14, 9, 30, tzinfo=NEW_YORK)
        assert angenommen.close == datetime(2026, 8, 14, 16, 0, tzinfo=NEW_YORK)

    def test_am_wochenende_gibt_es_nichts_anzunehmen(self) -> None:
        """Dafuer braucht es keinen Kalender."""
        assert assumed_session(date(2026, 8, 15), PARAMETER) is None
        assert assumed_session(date(2026, 8, 16), PARAMETER) is None

    def test_sie_gibt_die_zielkerze_immer_her(self) -> None:
        """Sonst liefe der Notbehelf ins Leere und der Ausfall bliebe stumm."""
        angenommen = assumed_session(date(2026, 8, 14), PARAMETER)
        assert angenommen is not None
        assert scheduled_run_for(angenommen, PARAMETER) is not None

    def test_sie_traegt_die_boersenzeitzone_und_nicht_die_lokale(self) -> None:
        angenommen = assumed_session(date(2026, 1, 5), PARAMETER)
        assert angenommen is not None
        assert angenommen.open.utcoffset() == timedelta(hours=-5)  # Winterzeit
