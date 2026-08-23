"""Der Dispatcher: was bei einem Start tatsaechlich passiert.

Alle Aussenkanten sind ersetzt -- Kalender, Zustand, Backfill, Analyse,
Meldung. Geprueft wird die Entscheidung, nicht die Arbeit dahinter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ai_trading_analyst.application.dispatch_daily_run import (
    DispatchDailyRunUseCase,
)
from ai_trading_analyst.config import SchedulerConfig
from ai_trading_analyst.domain.analysis import MarketDataProviderError
from ai_trading_analyst.domain.scheduling import (
    DispatchDecision,
    SchedulerParameters,
    TradingCalendarError,
    TradingSession,
)

NEW_YORK = ZoneInfo("America/New_York")
HANDELSTAG = date(2026, 8, 14)
KERZE_ZU = datetime(2026, 8, 14, 12, 45, tzinfo=NEW_YORK)
FRUEHESTENS = datetime(2026, 8, 14, 12, 50, tzinfo=NEW_YORK)

AUSGELIEFERT = SchedulerConfig()
"""Die Werte aus config/default.yaml, nicht nachgebaute.

``TestEchtesStartfenster`` prueft, dass die Nachholfrist im Startfenster der
Aufgabenplanung liegt. Mit nachgebauten Werten pruefte er sich selbst statt
den Betrieb -- genau daran ist die Meldung schon einmal vorbeigelaufen.
"""

PARAMETER = SchedulerParameters(
    timeframe_minutes=195,
    daily_candle_index=1,
    safety_buffer_seconds=AUSGELIEFERT.safety_buffer_seconds,
    max_catch_up_seconds=AUSGELIEFERT.max_catch_up_seconds,
    timezone="America/New_York",
    session_open=time(9, 30),
    session_minutes=390,
)


class FakeKalender:
    def __init__(self, sitzung: TradingSession | Exception | None) -> None:
        self._sitzung = sitzung

    def session_on(self, day: date) -> TradingSession | None:
        if isinstance(self._sitzung, Exception):
            raise self._sitzung
        return self._sitzung


def handelstag(tag: date = HANDELSTAG, schluss: time = time(16, 0)) -> TradingSession:
    return TradingSession(
        session_date=tag,
        open=datetime.combine(tag, time(9, 30), tzinfo=NEW_YORK),
        close=datetime.combine(tag, schluss, tzinfo=NEW_YORK),
    )


@dataclass
class FakeZustand:
    """Der Dispatcher-Zustand im Speicher."""

    erledigt: bool = False
    lock_frei: bool = True
    alarmiert: bool = False
    versuche: int = 0
    fehler: list[str] = field(default_factory=list)
    erfolge: int = 0
    lock_gehalten: bool = False

    def acquire_lock(self) -> bool:
        if not self.lock_frei:
            return False
        self.lock_gehalten = True
        return True

    def release_lock(self) -> None:
        self.lock_gehalten = False

    offen: list[tuple[date, datetime]] = field(default_factory=list)

    def unresolved(self) -> list[tuple[date, datetime]]:
        return list(self.offen)

    def is_done(self, session_date: date, candle_close: datetime) -> bool:
        return self.erledigt

    def begin(self, session_date: date, candle_close: datetime, now: datetime) -> int:
        self.versuche += 1
        if (session_date, candle_close) not in self.offen:
            self.offen.append((session_date, candle_close))
        return self.versuche

    def mark_succeeded(self, session_date: date, candle_close: datetime, now: datetime) -> None:
        self.erfolge += 1
        self.erledigt = True
        if (session_date, candle_close) in self.offen:
            self.offen.remove((session_date, candle_close))

    def mark_failed(
        self, session_date: date, candle_close: datetime, now: datetime, error: str
    ) -> None:
        self.fehler.append(error)

    def alert_sent(self, session_date: date, candle_close: datetime) -> bool:
        return self.alarmiert

    def mark_alert_sent(self, session_date: date, candle_close: datetime, now: datetime) -> None:
        self.alarmiert = True
        if (session_date, candle_close) in self.offen:
            self.offen.remove((session_date, candle_close))


class FakeMelder:
    def __init__(self) -> None:
        self.meldungen: list[tuple[str, str]] = []

    def send(self, subject: str, body: str) -> None:
        self.meldungen.append((subject, body))


@dataclass
class Aufbau:
    zustand: FakeZustand
    melder: FakeMelder
    backfills: list[int]
    analysen: list[int]


STANDARD = object()
"""Unterscheidet "nicht angegeben" von "kein Handelstag" -- beides waere
sonst ``None``, und ein Feiertagstest liefe still gegen einen Handelstag."""


def baue(
    *,
    jetzt: datetime,
    sitzung: TradingSession | Exception | object | None = STANDARD,
    zustand: FakeZustand | None = None,
    letzter_bar: datetime | None = None,
    backfill_fehler: Exception | None = None,
    analyse_fehler: Exception | None = None,
) -> tuple[DispatchDailyRunUseCase, Aufbau]:
    aufbau = Aufbau(
        zustand=zustand or FakeZustand(),
        melder=FakeMelder(),
        backfills=[],
        analysen=[],
    )

    def backfill() -> None:
        aufbau.backfills.append(1)
        if backfill_fehler is not None:
            raise backfill_fehler

    def analyse(erwartete_kerze: datetime) -> None:
        aufbau.analysen.append(1)
        if analyse_fehler is not None:
            raise analyse_fehler

    use_case = DispatchDailyRunUseCase(
        calendar=FakeKalender(handelstag() if sitzung is STANDARD else sitzung),  # type: ignore[arg-type]
        runs=aufbau.zustand,
        parameters=PARAMETER,
        backfill=backfill,
        analyse=analyse,
        latest_stored_bar=lambda: letzter_bar if letzter_bar else KERZE_ZU - timedelta(minutes=15),
        notifier=aufbau.melder,
        native_bar_minutes=15,
        now=lambda: jetzt,
    )
    return use_case, aufbau


class TestNichtsZuTun:
    """Fast alle Starts enden hier -- zwoelf am Abend, einer arbeitet."""

    def test_vor_dem_sicherheitspuffer(self) -> None:
        use_case, aufbau = baue(jetzt=datetime(2026, 8, 14, 12, 46, tzinfo=NEW_YORK))

        ergebnis = use_case.execute()

        assert ergebnis.decision is DispatchDecision.TOO_EARLY
        assert aufbau.backfills == []

    def test_am_wochenende(self) -> None:
        use_case, aufbau = baue(jetzt=datetime(2026, 8, 15, 14, 0, tzinfo=NEW_YORK), sitzung=None)

        ergebnis = use_case.execute()

        assert ergebnis.decision is DispatchDecision.NO_TRADING_DAY
        assert aufbau.backfills == []

    def test_am_feiertag(self) -> None:
        """Der Kalender sagt es vorher -- kein Warten, kein Fehlalarm."""
        use_case, aufbau = baue(jetzt=FRUEHESTENS, sitzung=None)

        assert use_case.execute().decision is DispatchDecision.NO_TRADING_DAY
        assert aufbau.melder.meldungen == []

    def test_wenn_der_lauf_schon_erledigt_ist(self) -> None:
        use_case, aufbau = baue(jetzt=FRUEHESTENS, zustand=FakeZustand(erledigt=True))

        ergebnis = use_case.execute()

        assert ergebnis.decision is DispatchDecision.ALREADY_DONE
        assert aufbau.backfills == []

    def test_wenn_ein_anderer_start_noch_arbeitet(self) -> None:
        """Ein Backfill ueber die volle Watchlist dauert laenger als der
        Abstand zwischen zwei Starts."""
        use_case, aufbau = baue(jetzt=FRUEHESTENS, zustand=FakeZustand(lock_frei=False))

        use_case.execute()

        assert aufbau.backfills == []

    def test_an_einem_verkuerzten_tag_ohne_zielkerze(self) -> None:
        zweite = SchedulerParameters(
            timeframe_minutes=195,
            daily_candle_index=2,
            safety_buffer_seconds=AUSGELIEFERT.safety_buffer_seconds,
            max_catch_up_seconds=AUSGELIEFERT.max_catch_up_seconds,
            timezone="America/New_York",
            session_open=time(9, 30),
            session_minutes=390,
        )
        use_case, aufbau = baue(jetzt=FRUEHESTENS, sitzung=handelstag(schluss=time(13, 0)))
        use_case._parameters = zweite

        assert use_case.execute().decision is DispatchDecision.NO_TRADING_DAY
        assert aufbau.backfills == []


class TestGelingenderLauf:
    def test_erst_holen_dann_rechnen(self) -> None:
        use_case, aufbau = baue(jetzt=FRUEHESTENS)

        ergebnis = use_case.execute()

        assert ergebnis.decision is DispatchDecision.RUN
        assert ergebnis.error is None
        assert aufbau.backfills == [1]
        assert aufbau.analysen == [1]

    def test_der_lauf_wird_als_erledigt_vermerkt(self) -> None:
        use_case, aufbau = baue(jetzt=FRUEHESTENS)

        use_case.execute()

        assert aufbau.zustand.erfolge == 1
        assert aufbau.zustand.erledigt

    def test_die_sperre_wird_wieder_freigegeben(self) -> None:
        use_case, aufbau = baue(jetzt=FRUEHESTENS)

        use_case.execute()

        assert not aufbau.zustand.lock_gehalten

    def test_auch_nach_einem_fehler(self) -> None:
        """Sonst blockierte ein einziger Ausfall alle folgenden Starts."""
        use_case, aufbau = baue(
            jetzt=FRUEHESTENS, backfill_fehler=MarketDataProviderError("TWS weg")
        )

        use_case.execute()

        assert not aufbau.zustand.lock_gehalten


class TestKeinLaufOhneFrischeDaten:
    """Ein Lauf auf dem Stand von gestern saehe aus wie die heutige Analyse
    und waere es nicht."""

    def test_ohne_die_daten_der_zielkerze_wird_nicht_gerechnet(self) -> None:
        use_case, aufbau = baue(jetzt=FRUEHESTENS, letzter_bar=KERZE_ZU - timedelta(days=1))

        ergebnis = use_case.execute()

        assert ergebnis.error is not None
        assert aufbau.analysen == []

    def test_ein_leerer_bestand_ebenfalls_nicht(self) -> None:
        use_case, aufbau = baue(jetzt=FRUEHESTENS, letzter_bar=None)
        use_case._latest_stored_bar = lambda: None

        ergebnis = use_case.execute()

        assert ergebnis.error is not None
        assert aufbau.analysen == []

    def test_der_lauf_gilt_dann_nicht_als_erledigt(self) -> None:
        """Der naechste Start soll es erneut versuchen."""
        use_case, aufbau = baue(jetzt=FRUEHESTENS, letzter_bar=KERZE_ZU - timedelta(days=1))

        use_case.execute()

        assert not aufbau.zustand.erledigt
        assert len(aufbau.zustand.fehler) == 1

    def test_der_letzte_bar_der_zielkerze_genuegt(self) -> None:
        """Der Bar um 12:30 ist der letzte der Kerze, die um 12:45 endet."""
        use_case, aufbau = baue(jetzt=FRUEHESTENS, letzter_bar=KERZE_ZU - timedelta(minutes=15))

        assert use_case.execute().error is None
        assert aufbau.analysen == [1]


class TestAusfall:
    def test_ein_tws_ausfall_wird_vermerkt_und_wiederholt(self) -> None:
        zustand = FakeZustand()
        use_case, _ = baue(
            jetzt=FRUEHESTENS,
            zustand=zustand,
            backfill_fehler=MarketDataProviderError("Keine Verbindung zur TWS"),
        )

        ergebnis = use_case.execute()

        assert ergebnis.failed
        assert "Keine Verbindung zur TWS" in (ergebnis.error or "")
        assert not zustand.erledigt

    def test_ein_fehler_beim_rechnen_ebenso(self) -> None:
        use_case, aufbau = baue(jetzt=FRUEHESTENS, analyse_fehler=RuntimeError("kaputt"))

        ergebnis = use_case.execute()

        assert ergebnis.failed
        assert not aufbau.zustand.erledigt

    def test_die_versuche_werden_gezaehlt(self) -> None:
        zustand = FakeZustand()
        use_case, _ = baue(jetzt=FRUEHESTENS, zustand=zustand, backfill_fehler=RuntimeError("weg"))

        use_case.execute()
        use_case.execute()

        assert zustand.versuche == 2


class TestNachholfrist:
    SPAET = datetime(2026, 8, 14, 17, 30, tzinfo=NEW_YORK)

    def test_nach_ablauf_wird_gemeldet(self) -> None:
        use_case, aufbau = baue(jetzt=self.SPAET)

        ergebnis = use_case.execute()

        assert ergebnis.decision is DispatchDecision.TOO_LATE
        assert ergebnis.alerted
        assert len(aufbau.melder.meldungen) == 1
        assert "TWS" in aufbau.melder.meldungen[0][1]

    def test_es_wird_nicht_mehr_gerechnet(self) -> None:
        use_case, aufbau = baue(jetzt=self.SPAET)

        use_case.execute()

        assert aufbau.backfills == []
        assert aufbau.analysen == []

    def test_gemeldet_wird_nur_einmal(self) -> None:
        """Sonst meldete sich der Dispatcher alle 15 Minuten erneut."""
        zustand = FakeZustand()
        use_case, aufbau = baue(jetzt=self.SPAET, zustand=zustand)

        use_case.execute()
        use_case.execute()
        use_case.execute()

        assert len(aufbau.melder.meldungen) == 1

    def test_ein_erledigter_lauf_meldet_nichts(self) -> None:
        use_case, aufbau = baue(jetzt=self.SPAET, zustand=FakeZustand(erledigt=True))

        ergebnis = use_case.execute()

        assert ergebnis.decision is DispatchDecision.ALREADY_DONE
        assert aufbau.melder.meldungen == []


class TestKalenderNichtAbrufbar:
    """Der Kalender kommt von der TWS, und die faellt aus.

    Ohne Notbehelf wuesste der Dispatcher nicht einmal, dass ein Lauf faellig
    waere -- ein ausgefallener Abend saehe aus wie ein Feiertag, und die
    Meldung bliebe aus.
    """

    def test_an_einem_wochentag_wird_die_uebliche_sitzung_angenommen(self) -> None:
        use_case, _ = baue(
            jetzt=FRUEHESTENS,
            sitzung=TradingCalendarError("Keine Verbindung zur TWS"),
            backfill_fehler=MarketDataProviderError("Keine Verbindung zur TWS"),
        )

        ergebnis = use_case.execute()

        assert ergebnis.decision is DispatchDecision.RUN
        assert ergebnis.failed  # der Backfill scheitert erwartungsgemaess

    def test_und_nach_der_frist_wird_gemeldet(self) -> None:
        """Das ist der Punkt: Ein Abend ohne TWS bleibt nicht stumm."""
        use_case, aufbau = baue(
            jetzt=datetime(2026, 8, 14, 17, 30, tzinfo=NEW_YORK),
            sitzung=TradingCalendarError("Keine Verbindung zur TWS"),
        )

        ergebnis = use_case.execute()

        assert ergebnis.decision is DispatchDecision.TOO_LATE
        assert len(aufbau.melder.meldungen) == 1

    def test_am_wochenende_bleibt_es_still(self) -> None:
        """Dafuer braucht es keinen Kalender -- und keine Meldung."""
        use_case, aufbau = baue(
            jetzt=datetime(2026, 8, 15, 17, 30, tzinfo=NEW_YORK),
            sitzung=TradingCalendarError("Keine Verbindung zur TWS"),
        )

        ergebnis = use_case.execute()

        assert ergebnis.decision is DispatchDecision.NO_TRADING_DAY
        assert aufbau.melder.meldungen == []


class TestEchtesStartfenster:
    """Der Test, der gefehlt hat.

    Die Meldung nach Fristablauf nuetzt nichts, wenn die Aufgabenplanung zu
    keinem Zeitpunkt startet, an dem sie ausloesen wuerde. Hier laufen genau
    die Startzeiten aus der Betriebsanleitung durch -- 17:30 bis 21:30
    deutscher Zeit, alle 15 Minuten -- und zwar in beiden Lagen der
    Zeitumstellung.
    """

    BERLIN = ZoneInfo("Europe/Berlin")

    def _startzeiten(self, tag: date) -> list[datetime]:
        erster = datetime.combine(tag, time(17, 30), tzinfo=self.BERLIN)
        return [erster + timedelta(minutes=15 * schritt) for schritt in range(17)]

    def _abend_ohne_tws(self, tag: date) -> tuple[int, list[tuple[str, str]]]:
        """Ein ganzer Abend mit ausgefallener TWS. Liefert Versuche und
        Meldungen."""
        zustand = FakeZustand()
        melder = FakeMelder()
        versuche = 0
        for jetzt in self._startzeiten(tag):
            use_case, _ = baue(
                jetzt=jetzt,
                sitzung=handelstag(tag),
                zustand=zustand,
                backfill_fehler=MarketDataProviderError("Keine Verbindung zur TWS"),
            )
            use_case._notifier = melder
            use_case.execute()
            versuche = zustand.versuche
        return versuche, melder.meldungen

    def test_ein_ausgefallener_abend_wird_gemeldet(self) -> None:
        versuche, meldungen = self._abend_ohne_tws(date(2026, 8, 14))

        assert versuche > 0, "es haette ueberhaupt versucht werden muessen"
        assert len(meldungen) == 1

    def test_auch_waehrend_der_auseinanderlaufenden_zeitumstellung(self) -> None:
        """Im Maerz liegt 12:50 New Yorker Zeit auf 17:50 statt 18:50."""
        versuche, meldungen = self._abend_ohne_tws(date(2026, 3, 12))

        assert versuche > 0
        assert len(meldungen) == 1

    def test_und_nicht_oefter_als_einmal(self) -> None:
        """Sonst meldete sich der Dispatcher den ganzen Abend."""
        _, meldungen = self._abend_ohne_tws(date(2026, 8, 14))
        assert len(meldungen) == 1

    def test_ein_gelingender_abend_meldet_nichts(self) -> None:
        zustand = FakeZustand()
        melder = FakeMelder()
        laeufe = 0
        for jetzt in self._startzeiten(date(2026, 8, 14)):
            use_case, aufbau = baue(jetzt=jetzt, zustand=zustand)
            use_case._notifier = melder
            use_case.execute()
            laeufe += len(aufbau.analysen)

        assert laeufe == 1, "genau ein Lauf je Handelstag"
        assert melder.meldungen == []


class TestBoersendatum:
    """Gerechnet wird im Datum der Boerse, nicht in UTC.

    Im heutigen Abendfenster faellt beides zusammen. Sobald aber nach der
    zweiten Tageskerze gerechnet wird -- 16:00 New Yorker Zeit, also nach
    Mitternacht UTC --, waere das UTC-Datum der Folgetag, und der Kalender
    meldete faelschlich "kein Handelstag".
    """

    class MerkenderKalender:
        def __init__(self) -> None:
            self.gefragt: list[date] = []

        def session_on(self, day: date) -> TradingSession:
            self.gefragt.append(day)
            return handelstag(day)

    def test_gefragt_wird_nach_dem_handelstag_der_boerse(self) -> None:
        kalender = self.MerkenderKalender()
        use_case, _ = baue(jetzt=FRUEHESTENS)
        use_case._calendar = kalender

        use_case.execute()

        assert kalender.gefragt == [HANDELSTAG]

    def test_auch_wenn_in_utc_schon_der_naechste_tag_ist(self) -> None:
        """21:00 New Yorker Zeit sind 01:00 UTC am Folgetag."""
        kalender = self.MerkenderKalender()
        use_case, _ = baue(jetzt=datetime(2026, 8, 15, 1, 0, tzinfo=UTC))
        use_case._calendar = kalender

        use_case.execute()

        assert kalender.gefragt == [HANDELSTAG]


class TestErledigtOhneKalender:
    """Nach dem gelungenen Lauf folgen abends noch etliche Starts.

    Jeder von ihnen belegte sonst kurz die TWS-Verbindung, die IBKR je
    Client-ID nur einmal vergibt -- und zwar fuer eine Auskunft, die den
    Ausgang gar nicht mehr aendern kann.
    """

    class ZaehlenderKalender:
        def __init__(self) -> None:
            self.aufrufe = 0

        def session_on(self, day: date) -> TradingSession:
            self.aufrufe += 1
            return handelstag(day)

    def test_ein_erledigter_lauf_fragt_die_tws_nicht_mehr(self) -> None:
        kalender = self.ZaehlenderKalender()
        use_case, _ = baue(jetzt=FRUEHESTENS, zustand=FakeZustand(erledigt=True))
        use_case._calendar = kalender

        ergebnis = use_case.execute()

        assert ergebnis.decision is DispatchDecision.ALREADY_DONE
        assert kalender.aufrufe == 0

    def test_ein_offener_lauf_fragt_sie_sehr_wohl(self) -> None:
        kalender = self.ZaehlenderKalender()
        use_case, _ = baue(jetzt=FRUEHESTENS)
        use_case._calendar = kalender

        use_case.execute()

        assert kalender.aufrufe == 1
