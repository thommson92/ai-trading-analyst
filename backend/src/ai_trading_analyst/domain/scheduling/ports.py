"""Schnittstellen des Dispatchers.

Der Domain Layer kennt weder IBKR noch PostgreSQL noch einen Push-Dienst --
nur diese drei Protokolle.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Protocol

from .models import DailyRunSummary, TradingSession


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

    def unresolved(self) -> Sequence[tuple[date, datetime]]:
        """Laeufe, die weder gelungen sind noch gemeldet wurden."""
        ...

    def is_done(self, session_date: date, candle_close: datetime) -> bool: ...

    def begin(self, session_date: date, candle_close: datetime, now: datetime) -> int:
        """Vermerkt den Versuch und liefert die laufende Nummer."""
        ...

    def mark_succeeded(self, session_date: date, candle_close: datetime, now: datetime) -> None: ...

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


class DailyRunLookup(Protocol):
    """Die eine Frage des Waechters -- lesend, und sonst nichts (ADR 0071).

    **Bewusst nicht der volle ``DispatcherRunRepository``.** Der Waechter soll
    den Advisory Lock nicht einmal anfassen koennen: Ein Waechter, der die
    Sperre nimmt, blockiert den Lauf, den er ueberwacht. Was er nicht kann,
    kann er auch nicht versehentlich tun.

    ``SqlAlchemyDispatcherRunRepository`` erfuellt beide Protokolle; welches
    ein Aufrufer verlangt, sagt, was er damit vorhat.
    """

    def summary_on(self, session_date: date) -> DailyRunSummary:
        """Was an diesem Handelstag versucht wurde, ueber alle Kerzen hinweg.

        Ohne ``candle_close``: Der Waechter kennt ihn nicht, denn er haengt am
        Boersenkalender, und der kommt von der TWS -- die auszufallen pflegt.
        Ein Waechter, der erst die TWS braucht, um zu pruefen, ob der Lauf
        lief, waere genau dann stumm, wenn er reden soll.

        Ohne Zeile fuer diesen Tag: ``attempts == 0``.
        """
        ...


class NotifierError(Exception):
    """Eine Meldung konnte nicht zugestellt werden.

    Wird vom Application-Layer isoliert: Ein Kanal, der gerade nicht
    erreichbar ist, darf den Analyse-Lauf nicht anhalten (ADR 0024). Die
    Meldung gilt dann als nicht gesendet und wird beim naechsten Start erneut
    versucht.
    """


class Notifier(Protocol):
    """Ausgang fuer Meldungen an den Nutzer.

    Der Ausloeser gehoert hierher und nicht in den Dispatcher -- sonst
    muesste der angefasst werden, nur weil ein Push-Dienst dazukommt
    (ADR 0019). Welcher Kanal zustellt, entscheidet ADR 0024.

    Raises:
        NotifierError: wenn die Meldung nicht zugestellt werden konnte.
    """

    def send(self, subject: str, body: str) -> None: ...


class DashboardPublisherError(Exception):
    """Der Snapshot des Dashboards ging nicht hinaus.

    Wird vom Application Layer isoliert, aus demselben Grund wie
    ``NotifierError``: Das Ergebnis des Laufs steht zu diesem Zeitpunkt
    bereits in der Datenbank. Ein Anbieter, der gerade nicht erreichbar ist,
    darf einen erledigten Lauf nicht nachtraeglich scheitern lassen
    (ADR 0060, Entscheidung Punkt 2).
    """


class DashboardUploadError(DashboardPublisherError):
    """Der Baum steht auf dem Server, ging aber nicht zum Anbieter.

    **Eine Unterklasse, damit der Vertrag des Ports unveraendert gilt** --
    wer nur ``DashboardPublisherError`` abfaengt, verpasst nichts. Getrennt
    ist sie trotzdem, weil die Lage eine andere ist und die Meldung darum
    eine andere sein muss: Beim Schreibfehler steht draussen weiter der
    vorige Stand *und* auf dem Server auch; hier ist der Server voraus.
    """


class DashboardPreviewUrlError(DashboardPublisherError):
    """Der Baum ging hinaus, aber der Anbieter hat Vorschau-Adressen vergeben.

    Das ist kein Transportfehler, sondern ein Sicherheitsbefund: Wegen des
    stabilen Salts (ADR 0060, Nachtrag vom 2026-09-08) stehen **alle** je
    hochgeladenen Fassungen unter demselben Schluessel. Unerreichbar sind
    die alten nur, solange keine Vorschau-Adresse auf sie zeigt. Taucht
    trotzdem eine auf, gehoert das gemeldet und nicht protokolliert.
    """


class DashboardPublisher(Protocol):
    """Ausgang fuer den Snapshot, den das Dashboard ausserhalb des Servers
    anzeigt (ADR 0060).

    Die Richtung ist Absicht und der Kern der Entscheidung: Der Server
    **sendet**. Es gibt keinen Weg zurueck -- kein eingehender Port, kein
    Agent, kein Tunnel. Die Domain kennt weder den Anbieter noch das
    Dateiformat, nur diesen einen Aufruf.

    Raises:
        DashboardPublisherError: wenn der Snapshot nicht hinausging.
    """

    def publish(self) -> None: ...
