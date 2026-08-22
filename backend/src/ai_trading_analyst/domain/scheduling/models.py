"""Was ein Handelstag ist und wann an ihm gerechnet werden darf.

Alles hier ist reine Zeitrechnung in der Zeitzone der Boerse. Keine
Datenbank, keine TWS, keine deutsche Uhrzeit -- die einzige Ortszeit im
System ist das Startfenster der Aufgabenplanung, und die steht in der
Betriebsdokumentation ([ADR 0019](../../../../../docs/adr/0019-trading-day-dispatcher.md)).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo


class DispatchDecision(StrEnum):
    """Was der Dispatcher bei diesem Start zu tun hat."""

    RUN = "run"
    TOO_EARLY = "too_early"
    """Die Zielkerze ist noch nicht geschlossen oder der Sicherheitspuffer
    laeuft noch."""
    NO_TRADING_DAY = "no_trading_day"
    """Wochenende, Feiertag -- oder ein Tag, der zu kurz fuer die Zielkerze
    ist. Laut Boersenkalender, nicht aus ausbleibenden Daten geschlossen."""
    ALREADY_DONE = "already_done"
    IN_PROGRESS = "in_progress"
    """Ein vorheriger Start arbeitet noch. Getrennt von ``ALREADY_DONE``,
    weil "laeuft gerade" und "war schon erfolgreich" bei der Fehlersuche
    genau das Gegenteil bedeuten."""
    TOO_LATE = "too_late"
    """Die Nachholfrist ist abgelaufen. Ein Lauf ergaebe eine Analyse, die
    laengst nicht mehr die des Handelstages waere."""


@dataclass(frozen=True, slots=True)
class TradingSession:
    """Eine regulaere Handelssitzung laut Boersenkalender.

    ``close`` kann vor der ueblichen Zeit liegen -- an verkuerzten Tagen
    schliessen die US-Maerkte um 13:00 Ortszeit. Genau deshalb kommt der
    Kalender von der Boerse und nicht aus einer Uhrzeitkonvention.
    """

    session_date: date
    open: datetime
    close: datetime


@dataclass(frozen=True, slots=True)
class SchedulerParameters:
    """Die Stellschrauben des Dispatchers, alle aus der Konfiguration."""

    timeframe_minutes: int
    daily_candle_index: int
    """Nach welcher Kerze des Tages gerechnet wird. 1 = die erste, also
    09:30 bis 12:45 New Yorker Zeit."""
    safety_buffer_seconds: int
    """Wartezeit nach Kerzenschluss, bevor ueberhaupt gefragt wird. Die Kerze
    ist zwar zu, beim Anbieter aber nicht zwingend schon vollstaendig."""
    max_catch_up_seconds: int
    """Wie lange ein verpasster Lauf noch nachgeholt werden darf."""
    timezone: str
    session_open: time
    session_minutes: int
    """Die uebliche Sitzung -- nur fuer ``assumed_session`` gebraucht."""


def assumed_session(day: date, parameters: SchedulerParameters) -> TradingSession | None:
    """Die uebliche Sitzung eines Wochentags, ohne Kalender.

    Notbehelf fuer den Fall, dass der Boersenkalender nicht abrufbar ist --
    er kommt von der TWS, und die faellt aus. Ohne ihn wuesste der Dispatcher
    nicht einmal, dass heute ein Lauf faellig *waere*, und die Alarmierung
    nach Fristablauf liefe ins Leere: Ein dauerhaft ausgefallener Abend saehe
    aus wie ein Feiertag.

    Verwendet wird das ausschliesslich, um den Lauf als faellig und
    unerledigt zu fuehren. Faellt der Tag in Wahrheit auf einen Feiertag,
    entsteht dadurch eine Meldung zu viel -- die umgekehrte Verwechslung, ein
    echter Ausfall gehalten fuer einen Feiertag, waere schlimmer (ADR 0019).

    ``None`` am Wochenende: Dafuer braucht es keinen Kalender.
    """
    if day.weekday() >= 5:
        return None
    zone = ZoneInfo(parameters.timezone)
    eroeffnung = datetime.combine(day, parameters.session_open, tzinfo=zone)
    return TradingSession(
        session_date=day,
        open=eroeffnung,
        close=eroeffnung + timedelta(minutes=parameters.session_minutes),
    )


@dataclass(frozen=True, slots=True)
class ScheduledRun:
    """Der Lauf, um den es an diesem Handelstag geht."""

    session_date: date
    candle_close: datetime
    earliest_start: datetime
    deadline: datetime

    def decide(self, now: datetime) -> DispatchDecision:
        if now < self.earliest_start:
            return DispatchDecision.TOO_EARLY
        if now > self.deadline:
            return DispatchDecision.TOO_LATE
        return DispatchDecision.RUN


def scheduled_run_for(
    session: TradingSession, parameters: SchedulerParameters
) -> ScheduledRun | None:
    """Der faellige Lauf einer Sitzung -- oder ``None``.

    ``None`` heisst: Diese Sitzung gibt die Zielkerze nicht her. Das ist kein
    Fehler, sondern der verkuerzte Handelstag in Reinform -- schliesst die
    Boerse um 13:00, endet die zweite 195-Minuten-Kerze nie.
    """
    candle_close = session.open + timedelta(
        minutes=parameters.timeframe_minutes * parameters.daily_candle_index
    )
    if candle_close > session.close:
        return None
    earliest = candle_close + timedelta(seconds=parameters.safety_buffer_seconds)
    return ScheduledRun(
        session_date=session.session_date,
        candle_close=candle_close,
        earliest_start=earliest,
        deadline=earliest + timedelta(seconds=parameters.max_catch_up_seconds),
    )
