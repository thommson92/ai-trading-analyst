"""Der Waechter meldet, was der Tageslauf selbst nicht mehr melden kann."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ai_trading_analyst.application.watch_daily_run import (
    LAUF_HOECHSTDAUER,
    SICHERUNG_HOECHSTALTER,
    WatchDailyRunUseCase,
)
from ai_trading_analyst.config import SchedulerConfig
from ai_trading_analyst.domain.scheduling import (
    DailyRunSummary,
    NotifierError,
    SchedulerParameters,
)

NEW_YORK = ZoneInfo("America/New_York")
HANDELSTAG = date(2026, 9, 22)
"""Ein Dienstag."""
SAMSTAG = date(2026, 9, 26)

AUSGELIEFERT = SchedulerConfig()
PARAMETER = SchedulerParameters(
    timeframe_minutes=195,
    daily_candle_index=1,
    safety_buffer_seconds=AUSGELIEFERT.safety_buffer_seconds,
    max_catch_up_seconds=AUSGELIEFERT.max_catch_up_seconds,
    timezone="America/New_York",
    session_open=time(9, 30),
    session_minutes=390,
)

NACH_FRISTABLAUF = datetime.combine(HANDELSTAG, time(23, 15), tzinfo=NEW_YORK)
"""Die Uhrzeit, zu der die Aufgabe laeuft -- lange nach der Nachholfrist."""
VOR_FAELLIGKEIT = datetime.combine(HANDELSTAG, time(10, 0), tzinfo=NEW_YORK)

GELUNGEN = DailyRunSummary(attempts=1, succeeded=True)


class FakeZustand:
    """Nur die eine Frage, die der Waechter stellt."""

    def __init__(self, lage: DailyRunSummary) -> None:
        self._lage = lage
        self.gefragt: list[date] = []

    def summary_on(self, session_date: date) -> DailyRunSummary:
        self.gefragt.append(session_date)
        return self._lage


class FakeMelder:
    def __init__(self, *, kaputt: bool = False) -> None:
        self.meldungen: list[tuple[str, str]] = []
        self._kaputt = kaputt

    def send(self, subject: str, body: str) -> None:
        if self._kaputt:
            raise NotifierError("Kanal nicht erreichbar")
        self.meldungen.append((subject, body))


def waechter(
    *,
    lage: DailyRunSummary = GELUNGEN,
    jetzt: datetime = NACH_FRISTABLAUF,
    melder: FakeMelder | None = None,
    sicherung: datetime | None = None,
    sicherung_geprueft: bool = False,
    max_alter: timedelta = SICHERUNG_HOECHSTALTER,
    max_dauer: timedelta = LAUF_HOECHSTDAUER,
) -> tuple[WatchDailyRunUseCase, FakeMelder]:
    kanal = melder if melder is not None else FakeMelder()
    return (
        WatchDailyRunUseCase(
            runs=FakeZustand(lage),
            parameters=PARAMETER,
            notifier=kanal,
            now=lambda: jetzt,
            latest_backup=(lambda: sicherung) if sicherung_geprueft else None,
            max_backup_age=max_alter,
            max_run_duration=max_dauer,
        ),
        kanal,
    )


class TestDerLauf:
    def test_ein_erledigter_lauf_ergibt_keinen_befund(self) -> None:
        fall, melder = waechter(lage=DailyRunSummary(attempts=3, succeeded=True))
        bericht = fall.execute()
        assert not bericht.conspicuous
        assert melder.meldungen == []

    def test_kein_einziger_versuch_wird_gemeldet(self) -> None:
        """Der Fall vom 2026-09-22: Die Aufgabe startete 17-mal und starb
        jedes Mal in argparse -- es gibt keine Zeile, die der Tageslauf selbst
        haette finden koennen."""
        fall, melder = waechter(lage=DailyRunSummary(attempts=0, succeeded=False))
        bericht = fall.execute()
        assert bericht.conspicuous
        assert "keinen einzigen Versuch" in bericht.findings[0]
        assert bericht.notified
        assert len(melder.meldungen) == 1

    def test_versuche_ohne_erfolg_nennen_den_letzten_fehler(self) -> None:
        fall, _ = waechter(
            lage=DailyRunSummary(attempts=4, succeeded=False, last_error="TWS nicht erreichbar")
        )
        bericht = fall.execute()
        assert "4 Versuch(e)" in bericht.findings[0]
        assert "TWS nicht erreichbar" in bericht.findings[0]

    def test_der_unterschied_zwischen_kein_start_und_gescheitert_ist_sichtbar(self) -> None:
        """Beide fuehren bei der Fehlersuche an voellig verschiedene Orte."""
        ohne, _ = waechter(lage=DailyRunSummary(attempts=0, succeeded=False))
        mit, _ = waechter(lage=DailyRunSummary(attempts=2, succeeded=False))
        assert ohne.execute().findings != mit.execute().findings

    def test_vor_fristablauf_wird_nichts_gemeldet(self) -> None:
        """Sonst meldete ein Waechter, der aus Versehen mittags laeuft, einen
        Lauf als ausgefallen, der noch gar nicht faellig ist."""
        fall, melder = waechter(
            lage=DailyRunSummary(attempts=0, succeeded=False), jetzt=VOR_FAELLIGKEIT
        )
        assert not fall.execute().conspicuous
        assert melder.meldungen == []

    def test_am_wochenende_wird_der_lauf_nicht_geprueft(self) -> None:
        fall, _ = waechter(
            lage=DailyRunSummary(attempts=0, succeeded=False),
            jetzt=datetime.combine(SAMSTAG, time(23, 15), tzinfo=NEW_YORK),
        )
        assert not fall.execute().conspicuous


class TestDerLaufendeLauf:
    """Ein Lauf darf um 23:15 noch arbeiten -- er dauert rund 103 Minuten."""

    def test_ein_frisch_laufender_lauf_wird_nicht_gemeldet(self) -> None:
        fall, melder = waechter(
            lage=DailyRunSummary(
                attempts=1,
                succeeded=False,
                running=True,
                first_attempt_at=NACH_FRISTABLAUF - timedelta(minutes=90),
            )
        )
        assert not fall.execute().conspicuous
        assert melder.meldungen == []

    def test_ein_haengender_lauf_wird_gemeldet(self) -> None:
        """Der dritte blinde Fleck: Er haelt die Sperre, und deshalb kommt die
        Ueberfaelligkeitsmeldung des Dispatchers nicht hinaus."""
        fall, _ = waechter(
            lage=DailyRunSummary(
                attempts=1,
                succeeded=False,
                running=True,
                first_attempt_at=NACH_FRISTABLAUF - timedelta(hours=5),
            )
        )
        bericht = fall.execute()
        assert bericht.conspicuous
        assert "5.0 Stunden" in bericht.findings[0]
        assert "Sperre" in bericht.findings[0]

    def test_die_grenze_ist_das_zeitlimit_der_aufgabe(self) -> None:
        assert LAUF_HOECHSTDAUER == timedelta(hours=3)


class TestBereitsGemeldet:
    def test_was_der_dispatcher_schon_gemeldet_hat_bleibt_still(self) -> None:
        """Sonst kaeme dieselbe Sache zweimal -- der Waechter faengt, was
        *keiner* meldet."""
        fall, melder = waechter(
            lage=DailyRunSummary(attempts=3, succeeded=False, alerted=True, last_error="TWS weg")
        )
        assert not fall.execute().conspicuous
        assert melder.meldungen == []

    def test_eine_meldung_ohne_versuch_bleibt_ebenfalls_still(self) -> None:
        """``mark_alert_sent`` legt ohne vorherigen Versuch eine Zeile mit
        ``attempts = 0`` an. Ohne diese Pruefung meldete der Waechter 'kein
        einziger Versuch' fuer einen Tag, an dem laengst gemeldet wurde."""
        fall, _ = waechter(lage=DailyRunSummary(attempts=0, succeeded=False, alerted=True))
        assert not fall.execute().conspicuous

    def test_die_sicherung_wird_trotzdem_geprueft(self) -> None:
        """Der Dispatcher meldet nur den Lauf. Von der Sicherung weiss er
        nichts."""
        fall, _ = waechter(
            lage=DailyRunSummary(attempts=0, succeeded=False, alerted=True),
            sicherung_geprueft=True,
            sicherung=None,
        )
        assert fall.execute().conspicuous


class TestDieSicherung:
    def test_ohne_angegebene_ablage_wird_nicht_geprueft(self) -> None:
        fall, _ = waechter(sicherung_geprueft=False)
        assert not fall.execute().conspicuous

    def test_eine_frische_sicherung_ergibt_keinen_befund(self) -> None:
        fall, _ = waechter(
            sicherung_geprueft=True, sicherung=NACH_FRISTABLAUF - timedelta(hours=23)
        )
        assert not fall.execute().conspicuous

    def test_eine_zu_alte_sicherung_wird_gemeldet(self) -> None:
        fall, _ = waechter(
            sicherung_geprueft=True, sicherung=NACH_FRISTABLAUF - timedelta(hours=50)
        )
        bericht = fall.execute()
        assert bericht.conspicuous
        assert "50 Stunden alt" in bericht.findings[0]

    def test_eine_leere_ablage_wird_gemeldet(self) -> None:
        fall, _ = waechter(sicherung_geprueft=True, sicherung=None)
        assert "keine einzige Sicherung" in fall.execute().findings[0]

    def test_die_sicherung_wird_auch_am_wochenende_geprueft(self) -> None:
        """Gesichert wird taeglich. Eine Sicherung, die samstags ausfaellt,
        faellt auch montags aus."""
        fall, _ = waechter(
            jetzt=datetime.combine(SAMSTAG, time(23, 15), tzinfo=NEW_YORK),
            sicherung_geprueft=True,
            sicherung=None,
        )
        assert fall.execute().conspicuous

    def test_die_grenze_liegt_ueber_vierundzwanzig_stunden(self) -> None:
        """Zwei taegliche Laeufe liegen fast genau 24 Stunden auseinander --
        bei einer glatten Grenze meldete schon eine um Minuten verschobene
        Ausfuehrung einen Ausfall."""
        assert SICHERUNG_HOECHSTALTER > timedelta(hours=24)


class TestDieMeldung:
    def test_beide_befunde_stehen_in_einer_meldung(self) -> None:
        fall, melder = waechter(
            lage=DailyRunSummary(attempts=0, succeeded=False),
            sicherung_geprueft=True,
            sicherung=None,
        )
        bericht = fall.execute()
        assert len(bericht.findings) == 2
        assert len(melder.meldungen) == 1

    def test_ein_unerreichbarer_kanal_wird_ausgewiesen(self) -> None:
        """Der schlechteste Fall: Es gibt einen Befund, und niemand erfaehrt
        davon. Er darf nicht wie 'alles in Ordnung' aussehen."""
        fall, _ = waechter(
            lage=DailyRunSummary(attempts=0, succeeded=False), melder=FakeMelder(kaputt=True)
        )
        bericht = fall.execute()
        assert bericht.conspicuous
        assert not bericht.notified

    def test_die_meldung_traegt_keine_kurse(self) -> None:
        """ADR 0024 -- der Waechter kennt auch keine."""
        fall, melder = waechter(lage=DailyRunSummary(attempts=0, succeeded=False))
        fall.execute()
        _, text = melder.meldungen[0]
        assert "$" not in text

    def test_gefragt_wird_nach_dem_handelstag_in_boersenzeit(self) -> None:
        zustand = FakeZustand(DailyRunSummary(attempts=0, succeeded=False))
        fall = WatchDailyRunUseCase(
            runs=zustand,
            parameters=PARAMETER,
            notifier=FakeMelder(),
            now=lambda: NACH_FRISTABLAUF,
        )
        fall.execute()
        assert zustand.gefragt == [HANDELSTAG]
