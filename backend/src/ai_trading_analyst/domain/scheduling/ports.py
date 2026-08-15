"""Schnittstellen des Dispatchers.

Der Domain Layer kennt weder IBKR noch PostgreSQL noch einen Push-Dienst --
nur diese drei Protokolle.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from .models import TradingSession


class TradingCalendarError(Exception):
    """Der Boersenkalender war nicht abrufbar.

    Ausdruecklich etwas anderes als "kein Handelstag": Wer den Kalender nicht
    lesen kann, weiss nicht, ob heute Feiertag ist -- er weiss nur, dass er es
    nicht weiss. Der Dispatcher behandelt das als "nicht erledigt, spaeter
    erneut versuchen" (ADR 0019).
    """


class TradingCalendar(Protocol):
    """Handelszeiten der Boerse, samt Feiertagen und verkuerzten Tagen."""

    def session_on(self, day: date) -> TradingSession | None:
        """``None`` heisst: kein Handelstag.

        Raises:
            TradingCalendarError: wenn der Kalender nicht abrufbar war.
        """
        ...


class DispatcherRunRepository(Protocol):
    """Der dauerhafte Zustand je ``(session_date, candle_close)``.

    Er liegt in derselben Datenbank wie die Analyseergebnisse: Zwei Orte fuer
    zusammengehoerigen Zustand waeren eine Quelle fuer Widersprueche nach
    einem Absturz zwischen beiden Schreibvorgaengen.
    """

    def acquire_lock(self) -> bool:
        """Sperrt gegen ueberlappende Starts. ``False`` = laeuft schon.

        Der eindeutige Schluessel allein genuegt nicht: Ein Lauf dauert
        laenger als der Abstand zwischen zwei Starts der Aufgabenplanung, und
        zwei gleichzeitige Backfills wuerden sich an der TWS verdraengen --
        IBKR laesst je Client-ID nur eine Verbindung zu.
        """
        ...

    def release_lock(self) -> None: ...

    def is_done(self, session_date: date, candle_close: datetime) -> bool: ...

    def begin(self, session_date: date, candle_close: datetime, now: datetime) -> int:
        """Vermerkt den Versuch und liefert die laufende Nummer."""
        ...

    def mark_succeeded(
        self, session_date: date, candle_close: datetime, now: datetime
    ) -> None: ...

    def mark_failed(
        self, session_date: date, candle_close: datetime, now: datetime, error: str
    ) -> None: ...

    def alert_sent(self, session_date: date, candle_close: datetime) -> bool:
        """Wurde fuer diesen Lauf bereits alarmiert?

        Ohne diese Frage meldete sich der Dispatcher nach Fristablauf alle
        15 Minuten erneut.
        """
        ...

    def mark_alert_sent(
        self, session_date: date, candle_close: datetime, now: datetime
    ) -> None: ...


class Notifier(Protocol):
    """Ausgang fuer Meldungen an den Nutzer.

    Der Kanal ist als F10 noch nicht entschieden; bis dahin protokolliert die
    Umsetzung nur. Der Ausloeser gehoert trotzdem hierher und nicht in den
    Dispatcher -- sonst muesste der spaeter angefasst werden, nur weil ein
    Push-Dienst dazukommt.
    """

    def send(self, subject: str, body: str) -> None: ...
