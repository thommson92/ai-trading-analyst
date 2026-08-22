"""Zustand und Sperre des Dispatchers gegen echtes PostgreSQL (ADR 0019).

Zwei Mechanismen mit zwei verschiedenen Aufgaben, die gern verwechselt
werden:

* Der **eindeutige Schluessel** ``(session_date, candle_close)`` sorgt dafuer,
  dass ein erledigter Lauf erledigt bleibt -- ueber Prozess- und
  Serverneustarts hinweg.
* Der **Advisory Lock** verhindert, dass zwei Starts gleichzeitig arbeiten.
  Der Schluessel allein genuegt dafuer nicht: Ein Lauf ueber die volle
  Watchlist dauert laenger als der Abstand zwischen zwei Starts der
  Aufgabenplanung, und zwei gleichzeitige Backfills wuerden sich an der TWS
  verdraengen -- IBKR laesst je Client-ID nur eine Verbindung zu.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from .orm import DispatcherRunOrm

LOCK_KEY = 0x41544144  # "ATAD" -- eine feste, projektweit eindeutige Zahl
"""Schluessel des Advisory Locks.

PostgreSQL verwaltet diese Sperren global je Datenbank. Eine feste Zahl
genuegt, weil es genau einen Dispatcher gibt; sie steht hier und nicht in der
Konfiguration, damit zwei Installationen auf derselben Datenbank sich
tatsaechlich gegenseitig sperren.
"""


class SqlAlchemyDispatcherRunRepository:
    """Der Zustand ueber die Session, die Sperre ueber eine eigene Verbindung."""

    def __init__(self, session: Session, engine: Engine) -> None:
        self._session = session
        self._engine = engine
        self._lock_connection: Connection | None = None

    def acquire_lock(self) -> bool:
        """``pg_try_advisory_lock`` -- nicht blockierend, auf eigener Verbindung.

        Beides ist wesentlich:

        *Nicht blockierend*, weil ein wartender Start die naechsten Starts der
        Aufgabenplanung ueberdauern und sich stapeln wuerde. Wer die Sperre
        nicht bekommt, hat schlicht nichts zu tun.

        *Eigene Verbindung*, weil PostgreSQL Advisory Locks an die Verbindung
        bindet und nicht an die Transaktion. Ueber die Session der uebrigen
        Arbeit gesetzt, gaebe ein ``commit()`` die Verbindung an den Pool
        zurueck; der naechste Zugriff bekaeme moeglicherweise eine andere, und
        die Sperre laege verwaist auf der ersten.

        Ein angenehmer Nebeneffekt: Bricht der Prozess hart ab, schliesst die
        Verbindung, und PostgreSQL gibt die Sperre von selbst frei. Eine
        haengende Sperre nach einem Absturz gibt es nicht.
        """
        if self._lock_connection is not None:  # pragma: no cover -- Programmierfehler
            raise RuntimeError("Die Sperre wurde bereits angefordert.")
        connection = self._engine.connect()
        erhalten = bool(
            connection.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_KEY}
            ).scalar_one()
        )
        if not erhalten:
            connection.close()
            return False
        self._lock_connection = connection
        return True

    def release_lock(self) -> None:
        if self._lock_connection is None:
            return
        try:
            self._lock_connection.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY}
            )
        finally:
            self._lock_connection.close()
            self._lock_connection = None

    def unresolved(self) -> Sequence[tuple[date, datetime]]:
        """Laeufe, die weder gelungen sind noch gemeldet wurden.

        Der Dispatcher sieht sie bei **jedem** Start durch, nicht nur die des
        heutigen Tages. Sonst waere ein Abend, an dem die TWS durchgehend
        fehlte, am naechsten Morgen endgueltig vergessen -- und die Meldung
        haette nie eine Gelegenheit gehabt.
        """
        zeilen = self._session.execute(
            select(DispatcherRunOrm.session_date, DispatcherRunOrm.candle_close)
            .where(
                DispatcherRunOrm.status != "succeeded",
                DispatcherRunOrm.alert_sent_at.is_(None),
            )
            .order_by(DispatcherRunOrm.candle_close)
        ).all()
        return [(zeile[0], zeile[1]) for zeile in zeilen]

    def is_done(self, session_date: date, candle_close: datetime) -> bool:
        return self._status(session_date, candle_close) == "succeeded"

    def begin(self, session_date: date, candle_close: datetime, now: datetime) -> int:
        """Legt den Versuch an oder zaehlt ihn hoch, und liefert die Nummer.

        ``ON CONFLICT DO UPDATE``: Ein zweiter Versuch desselben Laufs ist der
        Normalfall, nicht die Ausnahme -- die TWS ist abends nicht immer da.
        """
        statement = (
            pg_insert(DispatcherRunOrm)
            .values(
                session_date=session_date,
                candle_close=candle_close,
                status="running",
                attempts=1,
                first_attempt_at=now,
                last_attempt_at=now,
            )
            .on_conflict_do_update(
                index_elements=["session_date", "candle_close"],
                set_={
                    "status": "running",
                    "attempts": DispatcherRunOrm.__table__.c.attempts + 1,
                    "last_attempt_at": now,
                },
            )
            .returning(DispatcherRunOrm.attempts)
        )
        versuch = int(self._session.execute(statement).scalar_one())
        self._session.commit()
        return versuch

    def mark_succeeded(self, session_date: date, candle_close: datetime, now: datetime) -> None:
        self._finish(session_date, candle_close, now, status="succeeded", error=None)

    def mark_failed(
        self, session_date: date, candle_close: datetime, now: datetime, error: str
    ) -> None:
        self._finish(session_date, candle_close, now, status="failed", error=error)

    def alert_sent(self, session_date: date, candle_close: datetime) -> bool:
        eintrag = self._entry(session_date, candle_close)
        return eintrag is not None and eintrag.alert_sent_at is not None

    def mark_alert_sent(
        self, session_date: date, candle_close: datetime, now: datetime
    ) -> None:
        eintrag = self._entry(session_date, candle_close)
        if eintrag is None:
            # Die Frist kann ablaufen, ohne dass je ein Versuch stattfand --
            # etwa wenn der Server den ganzen Abend aus war.
            self._session.add(
                DispatcherRunOrm(
                    session_date=session_date,
                    candle_close=candle_close,
                    status="failed",
                    attempts=0,
                    first_attempt_at=now,
                    last_attempt_at=now,
                    last_error="Nachholfrist ohne Versuch abgelaufen",
                    alert_sent_at=now,
                )
            )
        else:
            eintrag.alert_sent_at = now
        self._session.commit()

    def _finish(
        self,
        session_date: date,
        candle_close: datetime,
        now: datetime,
        status: str,
        error: str | None,
    ) -> None:
        eintrag = self._entry(session_date, candle_close)
        if eintrag is None:  # pragma: no cover -- begin() legt ihn immer an
            raise RuntimeError(
                f"Kein Dispatcher-Eintrag fuer {session_date} / {candle_close.isoformat()}"
            )
        eintrag.status = status
        eintrag.finished_at = now
        eintrag.last_error = error
        self._session.commit()

    def _entry(self, session_date: date, candle_close: datetime) -> DispatcherRunOrm | None:
        return self._session.execute(
            select(DispatcherRunOrm).where(
                DispatcherRunOrm.session_date == session_date,
                DispatcherRunOrm.candle_close == candle_close,
            )
        ).scalar_one_or_none()

    def _status(self, session_date: date, candle_close: datetime) -> str | None:
        eintrag = self._entry(session_date, candle_close)
        return None if eintrag is None else eintrag.status
