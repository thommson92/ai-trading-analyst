"""Der taegliche Lauf, ausgeloest von der Aufgabenplanung.

Entschieden in [ADR 0019](../../../docs/adr/0019-trading-day-dispatcher.md).

Der Ausloeser ist dumm: Die Windows-Aufgabenplanung startet alle 15 Minuten
dasselbe Kommando. Hier entschieden wird, ob heute ueberhaupt ein Handelstag
ist, ob die Zielkerze geschlossen ist und ob der Lauf nicht laengst erledigt
wurde. Fast alle Starts enden nach wenigen Millisekunden mit "nichts zu tun".

Der eigentliche Lauf besteht aus zwei Schritten, die es beide schon gibt:
Erst den Bestand auffuellen, dann darauf rechnen. Neu ist nur die Frage
dazwischen -- **sind die Daten der Zielkerze tatsaechlich angekommen?**
Ohne sie entsteht kein Analyse-Lauf. Einer auf dem Stand von gestern saehe
aus wie die heutige Analyse und waere es nicht.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from ai_trading_analyst.application.bereitschaft import Bereitschaft
from ai_trading_analyst.domain.scheduling import (
    DispatchDecision,
    DispatcherRunRepository,
    Notifier,
    NotifierError,
    ScheduledRun,
    SchedulerParameters,
    TradingCalendar,
    TradingCalendarError,
    assumed_session,
    scheduled_run_for,
)
from ai_trading_analyst.observability.logging_setup import get_logger

_logger = get_logger(__name__)

_SYMBOLE_VOR_DEM_DATENGATE = 5
"""Wieviele Symbole der Backfill liefern muss, bevor das Datengate prueft.

Keine Konfiguration, sondern eine Abwaegung mit genau zwei Seiten: Zu frueh
gefragt, und ein einzelner ausgesetzter Titel liesse den Lauf abbrechen; zu
spaet, und der frueh gemeinte Abbruch kaeme nach einer halben Stunde. Fuenf
Symbole kosten rund eine Minute.
"""


@dataclass(frozen=True, slots=True)
class DispatchOutcome:
    """Was dieser Start bewirkt hat."""

    decision: DispatchDecision
    scheduled: ScheduledRun | None = None
    attempt: int | None = None
    error: str | None = None
    alerted: bool = False

    @property
    def failed(self) -> bool:
        return self.decision is DispatchDecision.RUN and self.error is not None


class DispatchDailyRunUseCase:
    def __init__(
        self,
        calendar: TradingCalendar,
        runs: DispatcherRunRepository,
        parameters: SchedulerParameters,
        backfill: Callable[
            [Callable[[str, bool], None] | None, Callable[[], bool] | None], None
        ],
        analyse: Callable[[datetime, Bereitschaft | None], None],
        latest_stored_bar: Callable[[], datetime | None],
        notifier: Notifier,
        native_bar_minutes: int,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        verzahnt: bool = False,
    ) -> None:
        self._calendar = calendar
        self._runs = runs
        self._parameters = parameters
        self._backfill = backfill
        self._analyse = analyse
        self._latest_stored_bar = latest_stored_bar
        self._notifier = notifier
        self._native_bar_minutes = native_bar_minutes
        self._now = now
        self._verzahnt = verzahnt

    def execute(self) -> DispatchOutcome:
        if not self._runs.acquire_lock():
            # Der vorige Start arbeitet noch -- ein Backfill ueber die volle
            # Watchlist dauert laenger als der Abstand zwischen zwei Starts.
            _logger.info("Ein Lauf ist bereits in Arbeit -- dieser Start endet ohne Aktion.")
            return DispatchOutcome(decision=DispatchDecision.IN_PROGRESS)
        try:
            return self._dispatch()
        finally:
            self._runs.release_lock()

    def _dispatch(self) -> DispatchOutcome:
        jetzt = self._now()
        # Der Handelstag ist der an der Boerse, nicht der in UTC. Im heutigen
        # Abendfenster faellt beides zusammen; sobald aber nach der zweiten
        # Tageskerze gerechnet wird (16:00 New Yorker Zeit, also nach
        # Mitternacht UTC), waere es der falsche Tag -- und der Kalender
        # meldete faelschlich "kein Handelstag".
        boersentag = jetzt.astimezone(ZoneInfo(self._parameters.timezone)).date()
        gemeldet = self._report_overdue(jetzt)

        if self._is_done_without_calendar(boersentag):
            # Vor dem Kalender, damit ein erledigter Lauf die TWS gar nicht
            # mehr anfaesst -- nach dem gelungenen Lauf folgen abends noch
            # etliche Starts, und jeder von ihnen belegte sonst kurz die
            # Verbindung, die IBKR je Client-ID nur einmal vergibt.
            return DispatchOutcome(decision=DispatchDecision.ALREADY_DONE, alerted=gemeldet)

        kalender_lesbar = True
        try:
            session = self._calendar.session_on(boersentag)
        except TradingCalendarError as error:
            # Der Kalender kommt von der TWS, und die faellt aus. Ohne ihn
            # wuesste der Dispatcher nicht einmal, dass heute ein Lauf faellig
            # waere -- ein dauerhaft ausgefallener Abend saehe aus wie ein
            # Feiertag, und die Meldung nach Fristablauf bliebe aus.
            _logger.warning("Boersenkalender nicht abrufbar (%s) -- Wochentag angenommen.", error)
            session = assumed_session(boersentag, self._parameters)
            kalender_lesbar = False

        if session is None:
            # Am Wochenende auch ohne Kalender eindeutig.
            _logger.info("%s ist kein Handelstag.", boersentag.isoformat())
            return DispatchOutcome(decision=DispatchDecision.NO_TRADING_DAY)

        geplant = scheduled_run_for(session, self._parameters)
        if geplant is None and not kalender_lesbar:
            # Kann bei einer angenommenen Sitzung nicht vorkommen; die Pruefung
            # steht hier, damit ein spaeterer Eingriff nicht still danebengreift.
            raise RuntimeError("Die angenommene Sitzung gibt die Zielkerze nicht her.")
        if geplant is None:
            # Verkuerzter Handelstag, an dem die Zielkerze nie zustande kommt.
            _logger.info(
                "%s gibt Kerze %d nicht her (Schluss %s).",
                session.session_date.isoformat(),
                self._parameters.daily_candle_index,
                session.close.isoformat(),
            )
            return DispatchOutcome(decision=DispatchDecision.NO_TRADING_DAY)

        if self._runs.is_done(geplant.session_date, geplant.candle_close):
            return DispatchOutcome(decision=DispatchDecision.ALREADY_DONE, scheduled=geplant)

        entscheidung = geplant.decide(jetzt)
        if entscheidung is DispatchDecision.TOO_EARLY:
            return DispatchOutcome(decision=entscheidung, scheduled=geplant, alerted=gemeldet)
        if entscheidung is DispatchDecision.TOO_LATE:
            # Zweiter Weg zur Meldung: Der heutige Lauf ist ueberfaellig, ohne
            # dass je ein Versuch stattfand -- dann gibt es keine Zeile, die
            # _report_overdue finden koennte. Das passiert, wenn die
            # Aufgabenplanung erst nach Fristablauf zum ersten Mal startet.
            return DispatchOutcome(
                decision=entscheidung,
                scheduled=geplant,
                alerted=gemeldet or self._alert_once(geplant, jetzt),
            )

        ergebnis = self._run(geplant, jetzt)
        return replace(ergebnis, alerted=True) if gemeldet else ergebnis

    def _is_done_without_calendar(self, boersentag: date) -> bool:
        """Ist der Lauf dieses Handelstages schon erledigt?

        Ohne Kalender beantwortbar: Der Schluss der Zielkerze ergibt sich aus
        der ueblichen Sitzung, und an einem Tag, an dem tatsaechlich gehandelt
        wurde, stimmt er mit dem tatsaechlichen ueberein. Ein verkuerzter Tag
        aendert den Beginn nicht, nur das Ende.
        """
        angenommen = assumed_session(boersentag, self._parameters)
        if angenommen is None:
            return False
        geplant = scheduled_run_for(angenommen, self._parameters)
        if geplant is None:  # pragma: no cover -- die uebliche Sitzung gibt sie her
            return False
        return self._runs.is_done(geplant.session_date, geplant.candle_close)

    def _alert_once(self, geplant: ScheduledRun, jetzt: datetime) -> bool:
        """Meldet einen ueberfaelligen Lauf, aber nur beim ersten Mal.

        Ohne den Vermerk meldete sich der Dispatcher alle 15 Minuten erneut.
        """
        if self._runs.alert_sent(geplant.session_date, geplant.candle_close):
            return False
        return self._notify(geplant.session_date, geplant.candle_close, jetzt)

    def _notify(self, session_date: date, candle_close: datetime, jetzt: datetime) -> bool:
        """Stellt die Meldung zu. ``False``, wenn der Kanal nicht erreichbar war.

        Der Kanal ist eine Systemgrenze und darf den Lauf nicht anhalten
        (ADR 0024): ``_report_overdue`` laeuft **vor** der Entscheidung ueber
        den heutigen Lauf, ein ungefangener Fehler beim Melden eines gestrigen
        Ausfalls verhinderte also die heutige Analyse.

        Gescheiterte Zustellung setzt **keinen** Vermerk. Die Meldung gilt
        damit als offen und wird beim naechsten Start erneut versucht -- die
        Alternative erzeugte genau den stillen Ausfall, gegen den dieser Kanal
        gebaut ist, eine Ebene hoeher.
        """
        try:
            self._notifier.send(
                f"Analyse-Lauf {session_date.isoformat()} ausgefallen",
                f"Die Kerze {candle_close.isoformat()} wurde bis {jetzt.isoformat()} nicht "
                "gerechnet; die Nachholfrist ist abgelaufen. Haeufigste Ursache: Die TWS "
                "laeuft nicht oder ist nicht angemeldet.",
            )
        except NotifierError as error:
            _logger.error(
                "Nachholfrist fuer %s abgelaufen, aber die Meldung ging nicht raus: %s "
                "-- naechster Start versucht es erneut.",
                session_date.isoformat(),
                error,
            )
            return False

        self._runs.mark_alert_sent(session_date, candle_close, jetzt)
        _logger.error(
            "Nachholfrist fuer %s abgelaufen -- Meldung abgesetzt.", session_date.isoformat()
        )
        return True

    def _report_overdue(self, jetzt: datetime) -> bool:
        """Meldet Laeufe, deren Nachholfrist abgelaufen ist -- aus **allen**
        Tagen, nicht nur dem heutigen.

        Der Alarm haengt bewusst nicht am Entscheid ueber den heutigen Lauf.
        Waere er dort aufgehoben, muesste ein Start genau nach Fristablauf
        stattfinden; faellt das Zeitfenster der Aufgabenplanung frueher, gaebe
        es die Meldung nie. Und ein Abend, an dem die TWS durchgehend fehlte,
        waere am naechsten Morgen endgueltig vergessen.
        """
        gemeldet = False
        for session_date, candle_close in self._runs.unresolved():
            frist = candle_close + timedelta(
                seconds=self._parameters.safety_buffer_seconds
                + self._parameters.max_catch_up_seconds
            )
            if jetzt <= frist:
                continue
            gemeldet = self._notify(session_date, candle_close, jetzt) or gemeldet
        return gemeldet

    def _run(self, geplant: ScheduledRun, jetzt: datetime) -> DispatchOutcome:
        versuch = self._runs.begin(geplant.session_date, geplant.candle_close, jetzt)
        _logger.info(
            "Lauf fuer %s, Kerze %s -- Versuch %d.",
            geplant.session_date.isoformat(),
            geplant.candle_close.isoformat(),
            versuch,
        )
        # Die Kerze traegt den Zeitstempel ihres Beginns, der Lauf kennt
        # ihren Schluss -- dazwischen liegt genau eine Kerzenlaenge.
        erwartete_kerze = geplant.candle_close - timedelta(
            minutes=self._parameters.timeframe_minutes
        )
        try:
            if self._verzahnt:
                self._verzahnter_lauf(geplant, erwartete_kerze)
            else:
                self._backfill(None, None)
                self._require_target_candle(geplant)
                self._analyse(erwartete_kerze, None)
        except Exception as error:  # Systemgrenze: TWS, Datenbank, Anbieter
            meldung = f"{type(error).__name__}: {error}"
            _logger.warning("Lauf gescheitert (Versuch %d): %s", versuch, meldung)
            self._runs.mark_failed(geplant.session_date, geplant.candle_close, self._now(), meldung)
            return DispatchOutcome(
                decision=DispatchDecision.RUN,
                scheduled=geplant,
                attempt=versuch,
                error=meldung,
            )

        self._runs.mark_succeeded(geplant.session_date, geplant.candle_close, self._now())
        return DispatchOutcome(decision=DispatchDecision.RUN, scheduled=geplant, attempt=versuch)

    def _verzahnter_lauf(self, geplant: ScheduledRun, erwartete_kerze: datetime) -> None:
        """Backfill im Hintergrund, Analyse davor her (ADR 0069).

        Der Backfill bleibt unveraendert seriell mit seinem Abstand auf einer
        Verbindung -- er wird nicht schneller. Beschleunigt wird, was
        waehrenddessen stillstand: Rund vierunddreissig der fuenfunddreissig
        Minuten sind ``time.sleep``, und in dieser Zeit rechnet jetzt die
        Analyse.

        **Der Fehler des Backfills wird weitergereicht.** Er ist heute der
        Grund, aus dem ein Lauf als gescheitert gilt und in fuenfzehn Minuten
        erneut versucht wird; daran aendert die Verzahnung nichts.
        """
        bereitschaft = Bereitschaft()
        gescheitert: list[BaseException] = []
        abbruch = threading.Event()

        def hole_bars() -> None:
            try:
                self._backfill(
                    lambda symbol, geliefert: bereitschaft.melde(symbol, geliefert=geliefert),
                    abbruch.is_set,
                )
            except BaseException as fehler:
                gescheitert.append(fehler)
            finally:
                # **Ohne diese Zeile haengt der Lauf.** Jeder Wartende kommt
                # erst durch, wenn sein Symbol gemeldet ist oder feststeht,
                # dass nichts mehr kommt.
                bereitschaft.beende()

        faden = threading.Thread(target=hole_bars, name="backfill", daemon=True)
        faden.start()
        try:
            self._require_target_candle_frueh(geplant, bereitschaft)
            # **Vor der Analyse, nicht erst danach.** Ist der Backfill zu
            # diesem Zeitpunkt bereits gescheitert, darf kein vollstaendiger
            # Lauf mehr entstehen: Er wuerde persistiert, gemeldet und
            # exportiert -- und erst danach gaelte er als gescheitert und
            # wuerde in fuenfzehn Minuten wiederholt, mitsamt einem zweiten
            # Laufdatensatz fuer denselben Tag.
            if gescheitert:
                raise gescheitert[0]
            self._analyse(erwartete_kerze, bereitschaft)
        finally:
            # **Erst abbrechen, dann warten.** Ohne das Signal liefe der
            # Backfill nach einem frueh abgebrochenen Lauf noch rund eine
            # halbe Stunde weiter -- und der Dispatcher hielte seine Sperre
            # so lange, sodass die naechsten beiden Starts mit "in Arbeit"
            # endeten. Genau die Zeit, die das fruehe Datengate sparen soll.
            # Der Abbruch wirkt zwischen zwei Symbolen.
            abbruch.set()
            # Der Thread haelt die TWS-Verbindung und gibt sie selbst wieder
            # frei; ein zweiter Lauf traefe sonst auf eine belegte Client-ID.
            faden.join()
        if gescheitert:
            raise gescheitert[0]

    def _require_target_candle_frueh(
        self, geplant: ScheduledRun, bereitschaft: Bereitschaft
    ) -> None:
        """Dasselbe Datengate, nur frueher (ADR 0069, Punkt 3).

        Die Frage lautet unveraendert: Sind die Daten der Zielkerze
        ueberhaupt angekommen? Sie laesst sich nach einer Handvoll Symbole
        genauso beantworten wie nach allen -- nur rund vierunddreissig
        Minuten frueher, und das entscheidet darueber, ob der naechste Start
        in fuenfzehn Minuten noch ins Zeitfenster faellt.
        """
        bereit = bereitschaft.warte_auf_anzahl(_SYMBOLE_VOR_DEM_DATENGATE)
        if bereit == 0:
            # Der Backfill hat kein einziges Symbol geschafft. Die Pruefung
            # unten faende dann den Bestand von gestern und meldete eine
            # ausgebliebene Lieferung -- richtig, aber irrefuehrend.
            raise DataNotArrivedError(
                "Der Backfill hat kein einziges Symbol geliefert -- die Kerze "
                f"{geplant.candle_close.isoformat()} kann nicht gerechnet werden."
            )
        self._require_target_candle(geplant)

    def _require_target_candle(self, geplant: ScheduledRun) -> None:
        """Sind die Daten der Zielkerze angekommen?

        Geprueft wird der juengste Bar im gesamten Bestand, nicht der einer
        bestimmten Aktie: Ein einzelner ausgesetzter Titel darf den Lauf nicht
        verhindern. Ob eine *einzelne* Aktie vollstaendig ist, entscheidet
        ohnehin erst die Kerzenbildung, und zwar je Aktie.
        """
        letzter = self._latest_stored_bar()
        noetig = geplant.candle_close - timedelta(minutes=self._native_bar_minutes)
        if letzter is None:
            raise DataNotArrivedError(
                f"Der Bestand ist leer -- die Kerze {geplant.candle_close.isoformat()} "
                "kann nicht gerechnet werden."
            )
        if letzter < noetig:
            raise DataNotArrivedError(
                f"Der juengste gespeicherte Bar ist {letzter.isoformat()}, noetig waere "
                f"mindestens {noetig.isoformat()}. Die Daten der Zielkerze sind noch "
                "nicht vollstaendig angekommen."
            )


class DataNotArrivedError(RuntimeError):
    """Die Daten der Zielkerze liegen nicht vor.

    Kein Fehler im Sinne eines Defekts: Der haeufigste Grund ist eine nicht
    angemeldete TWS. Der naechste Start versucht es erneut.
    """
