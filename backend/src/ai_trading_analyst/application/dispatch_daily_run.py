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

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ai_trading_analyst.domain.scheduling import (
    DispatchDecision,
    DispatcherRunRepository,
    Notifier,
    ScheduledRun,
    SchedulerParameters,
    TradingCalendar,
    TradingCalendarError,
    assumed_session,
    scheduled_run_for,
)
from ai_trading_analyst.observability.logging_setup import get_logger

_logger = get_logger(__name__)


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
        backfill: Callable[[], None],
        analyse: Callable[[], None],
        latest_stored_bar: Callable[[], datetime | None],
        notifier: Notifier,
        native_bar_minutes: int,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
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

    def execute(self) -> DispatchOutcome:
        if not self._runs.acquire_lock():
            # Der vorige Start arbeitet noch -- ein Backfill ueber die volle
            # Watchlist dauert laenger als der Abstand zwischen zwei Starts.
            _logger.info("Ein Lauf ist bereits in Arbeit -- dieser Start endet ohne Aktion.")
            return DispatchOutcome(decision=DispatchDecision.ALREADY_DONE)
        try:
            return self._dispatch()
        finally:
            self._runs.release_lock()

    def _dispatch(self) -> DispatchOutcome:
        jetzt = self._now()
        kalender_lesbar = True
        try:
            session = self._calendar.session_on(jetzt.date())
        except TradingCalendarError as error:
            # Der Kalender kommt von der TWS, und die faellt aus. Ohne ihn
            # wuesste der Dispatcher nicht einmal, dass heute ein Lauf faellig
            # waere -- ein dauerhaft ausgefallener Abend saehe aus wie ein
            # Feiertag, und die Meldung nach Fristablauf bliebe aus.
            _logger.warning("Boersenkalender nicht abrufbar (%s) -- Wochentag angenommen.", error)
            session = assumed_session(jetzt.date(), self._parameters)
            kalender_lesbar = False

        if session is None:
            # Am Wochenende auch ohne Kalender eindeutig.
            _logger.info("%s ist kein Handelstag.", jetzt.date().isoformat())
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
            return DispatchOutcome(decision=entscheidung, scheduled=geplant)
        if entscheidung is DispatchDecision.TOO_LATE:
            return self._give_up(geplant, jetzt)

        return self._run(geplant, jetzt)

    def _run(self, geplant: ScheduledRun, jetzt: datetime) -> DispatchOutcome:
        versuch = self._runs.begin(geplant.session_date, geplant.candle_close, jetzt)
        _logger.info(
            "Lauf fuer %s, Kerze %s -- Versuch %d.",
            geplant.session_date.isoformat(),
            geplant.candle_close.isoformat(),
            versuch,
        )
        try:
            self._backfill()
            self._require_target_candle(geplant)
            self._analyse()
        except Exception as error:  # Systemgrenze: TWS, Datenbank, Anbieter
            meldung = f"{type(error).__name__}: {error}"
            _logger.warning("Lauf gescheitert (Versuch %d): %s", versuch, meldung)
            self._runs.mark_failed(
                geplant.session_date, geplant.candle_close, self._now(), meldung
            )
            return DispatchOutcome(
                decision=DispatchDecision.RUN,
                scheduled=geplant,
                attempt=versuch,
                error=meldung,
            )

        self._runs.mark_succeeded(geplant.session_date, geplant.candle_close, self._now())
        return DispatchOutcome(
            decision=DispatchDecision.RUN, scheduled=geplant, attempt=versuch
        )

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

    def _give_up(self, geplant: ScheduledRun, jetzt: datetime) -> DispatchOutcome:
        """Nachholfrist abgelaufen -- einmal melden, dann Ruhe geben."""
        if self._runs.alert_sent(geplant.session_date, geplant.candle_close):
            return DispatchOutcome(decision=DispatchDecision.TOO_LATE, scheduled=geplant)

        self._notifier.send(
            f"Analyse-Lauf {geplant.session_date.isoformat()} ausgefallen",
            f"Die Kerze {geplant.candle_close.isoformat()} wurde bis {jetzt.isoformat()} "
            "nicht gerechnet. Die Nachholfrist ist abgelaufen; es wird nicht weiter "
            "versucht. Haeufigste Ursache: Die TWS laeuft nicht oder ist nicht "
            "angemeldet.",
        )
        self._runs.mark_alert_sent(geplant.session_date, geplant.candle_close, jetzt)
        _logger.error(
            "Nachholfrist fuer %s abgelaufen -- Meldung abgesetzt.",
            geplant.session_date.isoformat(),
        )
        return DispatchOutcome(
            decision=DispatchDecision.TOO_LATE, scheduled=geplant, alerted=True
        )


class DataNotArrivedError(RuntimeError):
    """Die Daten der Zielkerze liegen nicht vor.

    Kein Fehler im Sinne eines Defekts: Der haeufigste Grund ist eine nicht
    angemeldete TWS. Der naechste Start versucht es erneut.
    """
