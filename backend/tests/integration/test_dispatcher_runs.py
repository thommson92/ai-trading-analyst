"""Zustand und Sperre des Dispatchers gegen echtes PostgreSQL.

Beides laesst sich mit einem Testdoppel nicht belegen: Der Advisory Lock ist
ein Verhalten der Datenbank, und die Frage, ob ein Lauf nach einem Neustart
noch als erledigt gilt, ist genau die Frage nach der Dauerhaftigkeit.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ai_trading_analyst.infrastructure.persistence.dispatcher_runs import (
    SqlAlchemyDispatcherRunRepository,
)

HANDELSTAG = date(2026, 8, 14)
KERZE_ZU = datetime(2026, 8, 14, 16, 45, tzinfo=UTC)
JETZT = datetime(2026, 8, 14, 16, 50, tzinfo=UTC)

Repo = SqlAlchemyDispatcherRunRepository


@pytest.fixture
def repo(session_factory: sessionmaker[Session], engine: Engine) -> Iterator[Repo]:
    speicher = SqlAlchemyDispatcherRunRepository(session_factory(), engine)
    try:
        yield speicher
    finally:
        speicher.release_lock()


@pytest.fixture
def zweiter_repo(
    session_factory: sessionmaker[Session], engine: Engine
) -> Iterator[Repo]:
    """Ein zweiter Start, wie ihn die Aufgabenplanung 15 Minuten spaeter
    ausloest."""
    speicher = SqlAlchemyDispatcherRunRepository(session_factory(), engine)
    try:
        yield speicher
    finally:
        speicher.release_lock()


class TestSperre:
    def test_der_erste_start_bekommt_sie(self, repo: Repo) -> None:
        assert repo.acquire_lock()

    def test_der_zweite_bekommt_sie_nicht(self, repo: Repo, zweiter_repo: Repo) -> None:
        """Ein Lauf ueber die volle Watchlist dauert laenger als der Abstand
        zwischen zwei Starts -- ohne Sperre wuerden sich zwei Backfills an der
        TWS verdraengen."""
        assert repo.acquire_lock()
        assert not zweiter_repo.acquire_lock()

    def test_nach_der_freigabe_wieder(self, repo: Repo, zweiter_repo: Repo) -> None:
        repo.acquire_lock()
        repo.release_lock()

        assert zweiter_repo.acquire_lock()

    def test_freigeben_ohne_sperre_ist_folgenlos(self, repo: Repo) -> None:
        repo.release_lock()
        repo.release_lock()

    def test_die_sperre_ueberlebt_ein_commit(self, repo: Repo, zweiter_repo: Repo) -> None:
        """Der Grund fuer die eigene Verbindung: Ein commit() gibt die
        Verbindung an den Pool zurueck. Laege die Sperre darauf, waere sie
        danach verwaist."""
        assert repo.acquire_lock()
        repo.begin(HANDELSTAG, KERZE_ZU, JETZT)  # committet

        assert not zweiter_repo.acquire_lock()


class TestZustand:
    def test_ein_unbekannter_lauf_gilt_nicht_als_erledigt(self, repo: Repo) -> None:
        assert not repo.is_done(HANDELSTAG, KERZE_ZU)

    def test_der_erste_versuch_traegt_die_nummer_eins(self, repo: Repo) -> None:
        assert repo.begin(HANDELSTAG, KERZE_ZU, JETZT) == 1

    def test_ein_gescheiterter_versuch_blockiert_den_naechsten_nicht(
        self, repo: Repo
    ) -> None:
        """Eine nicht angemeldete TWS ist der haeufigste Grund -- der naechste
        Start soll es erneut versuchen."""
        repo.begin(HANDELSTAG, KERZE_ZU, JETZT)
        repo.mark_failed(HANDELSTAG, KERZE_ZU, JETZT, "Keine Verbindung zur TWS")

        assert not repo.is_done(HANDELSTAG, KERZE_ZU)
        assert repo.begin(HANDELSTAG, KERZE_ZU, JETZT + timedelta(minutes=15)) == 2

    def test_ein_gelungener_lauf_gilt_als_erledigt(self, repo: Repo) -> None:
        repo.begin(HANDELSTAG, KERZE_ZU, JETZT)
        repo.mark_succeeded(HANDELSTAG, KERZE_ZU, JETZT)

        assert repo.is_done(HANDELSTAG, KERZE_ZU)

    def test_das_ueberlebt_einen_neustart(
        self, repo: Repo, session_factory: sessionmaker[Session], engine: Engine
    ) -> None:
        """Der Zustand liegt in der Datenbank und nicht im Prozess."""
        repo.begin(HANDELSTAG, KERZE_ZU, JETZT)
        repo.mark_succeeded(HANDELSTAG, KERZE_ZU, JETZT)

        nach_neustart = SqlAlchemyDispatcherRunRepository(session_factory(), engine)
        assert nach_neustart.is_done(HANDELSTAG, KERZE_ZU)

    def test_zwei_kerzen_desselben_tages_sind_getrennte_laeufe(self, repo: Repo) -> None:
        """Der Schluessel ist bewusst (session_date, candle_close): Wird
        spaeter auch nach der zweiten Tageskerze gerechnet, sind das zwei."""
        zweite_kerze = KERZE_ZU + timedelta(minutes=195)
        repo.begin(HANDELSTAG, KERZE_ZU, JETZT)
        repo.mark_succeeded(HANDELSTAG, KERZE_ZU, JETZT)

        assert repo.is_done(HANDELSTAG, KERZE_ZU)
        assert not repo.is_done(HANDELSTAG, zweite_kerze)


class TestMeldung:
    def test_ohne_vermerk_gilt_sie_als_nicht_abgesetzt(self, repo: Repo) -> None:
        assert not repo.alert_sent(HANDELSTAG, KERZE_ZU)

    def test_der_vermerk_haelt(self, repo: Repo) -> None:
        """Sonst meldete sich der Dispatcher alle 15 Minuten erneut."""
        repo.begin(HANDELSTAG, KERZE_ZU, JETZT)
        repo.mark_alert_sent(HANDELSTAG, KERZE_ZU, JETZT)

        assert repo.alert_sent(HANDELSTAG, KERZE_ZU)

    def test_er_geht_auch_ohne_vorherigen_versuch(self, repo: Repo) -> None:
        """Die Frist kann ablaufen, ohne dass je ein Versuch stattfand -- etwa
        wenn der Server den ganzen Abend aus war."""
        repo.mark_alert_sent(HANDELSTAG, KERZE_ZU, JETZT)

        assert repo.alert_sent(HANDELSTAG, KERZE_ZU)
        assert not repo.is_done(HANDELSTAG, KERZE_ZU)
