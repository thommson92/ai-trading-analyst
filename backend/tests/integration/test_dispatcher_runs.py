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
def zweiter_repo(session_factory: sessionmaker[Session], engine: Engine) -> Iterator[Repo]:
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

    def test_ein_gescheiterter_versuch_blockiert_den_naechsten_nicht(self, repo: Repo) -> None:
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


class TestTageszusammenfassung:
    """Die Frage des Waechters: Was geschah an diesem Handelstag?

    Sie kommt ohne ``candle_close`` aus -- der Waechter kennt ihn nicht, weil
    er am Boersenkalender haengt und der von der TWS kommt.
    """

    def test_ein_tag_ohne_zeile_hat_keine_versuche(self, repo: Repo) -> None:
        lage = repo.summary_on(HANDELSTAG)
        assert lage.attempts == 0
        assert not lage.succeeded
        assert not lage.started

    def test_versuche_werden_ueber_alle_kerzen_summiert(self, repo: Repo) -> None:
        zweite_kerze = KERZE_ZU + timedelta(minutes=195)
        repo.begin(HANDELSTAG, KERZE_ZU, JETZT)
        repo.begin(HANDELSTAG, KERZE_ZU, JETZT)
        repo.begin(HANDELSTAG, zweite_kerze, JETZT)

        lage = repo.summary_on(HANDELSTAG)
        assert lage.attempts == 3
        assert lage.started
        assert not lage.succeeded

    def test_ein_erfolg_an_irgendeiner_kerze_genuegt(self, repo: Repo) -> None:
        """``bool_or`` und nicht "der letzte": Stehen mehrere Kerzen am Tag,
        muss die Zusammenfassung "irgendeiner kam durch" sagen."""
        zweite_kerze = KERZE_ZU + timedelta(minutes=195)
        repo.begin(HANDELSTAG, KERZE_ZU, JETZT)
        repo.mark_succeeded(HANDELSTAG, KERZE_ZU, JETZT)
        repo.begin(HANDELSTAG, zweite_kerze, JETZT)

        assert repo.summary_on(HANDELSTAG).succeeded

    def test_der_fehlertext_kommt_vom_juengsten_versuch(self, repo: Repo) -> None:
        """**Zwei Kerzen, nicht zweimal dieselbe.** Bei derselben Kerze
        ueberschriebe der zweite Fehler den ersten in derselben Zeile, und die
        Sortierung nach ``last_attempt_at`` bliebe ungeprueft."""
        zweite_kerze = KERZE_ZU + timedelta(minutes=195)
        spaeter = JETZT + timedelta(minutes=195)
        repo.begin(HANDELSTAG, KERZE_ZU, JETZT)
        repo.mark_failed(HANDELSTAG, KERZE_ZU, JETZT, "der aeltere")
        repo.begin(HANDELSTAG, zweite_kerze, spaeter)
        repo.mark_failed(HANDELSTAG, zweite_kerze, spaeter, "der juengere")

        assert repo.summary_on(HANDELSTAG).last_error == "der juengere"

    def test_ein_laufender_lauf_wird_als_solcher_ausgewiesen(self, repo: Repo) -> None:
        repo.begin(HANDELSTAG, KERZE_ZU, JETZT)
        lage = repo.summary_on(HANDELSTAG)
        assert lage.running
        assert lage.first_attempt_at is not None

    def test_ein_beendeter_lauf_laeuft_nicht_mehr(self, repo: Repo) -> None:
        repo.begin(HANDELSTAG, KERZE_ZU, JETZT)
        repo.mark_failed(HANDELSTAG, KERZE_ZU, JETZT, "TWS weg")
        assert not repo.summary_on(HANDELSTAG).running

    def test_eine_abgesetzte_meldung_ist_sichtbar(self, repo: Repo) -> None:
        """Sonst meldete der Waechter dieselbe Sache ein zweites Mal."""
        repo.begin(HANDELSTAG, KERZE_ZU, JETZT)
        repo.mark_failed(HANDELSTAG, KERZE_ZU, JETZT, "TWS weg")
        assert not repo.summary_on(HANDELSTAG).alerted
        repo.mark_alert_sent(HANDELSTAG, KERZE_ZU, JETZT)
        assert repo.summary_on(HANDELSTAG).alerted

    def test_eine_meldung_ohne_versuch_zaehlt_nicht_als_versuch(self, repo: Repo) -> None:
        """``mark_alert_sent`` legt ohne vorherigen Versuch eine Zeile mit
        ``attempts = 0`` an -- der Server war aus, oder der Start scheiterte
        vor dem Programm. Genau der Fall vom 2026-09-22."""
        repo.mark_alert_sent(HANDELSTAG, KERZE_ZU, JETZT)
        lage = repo.summary_on(HANDELSTAG)
        assert lage.attempts == 0
        assert not lage.started
        assert lage.alerted
        assert lage.last_error is not None

    def test_ein_anderer_tag_zaehlt_nicht_mit(self, repo: Repo) -> None:
        repo.begin(HANDELSTAG, KERZE_ZU, JETZT)
        assert repo.summary_on(HANDELSTAG - timedelta(days=1)).attempts == 0


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


class TestOffeneLaeufe:
    """Woran der Dispatcher erkennt, dass etwas liegengeblieben ist.

    Er sieht sie bei jedem Start durch, nicht nur die des heutigen Tages --
    sonst waere ein Abend mit ausgefallener TWS am naechsten Morgen
    endgueltig vergessen.
    """

    def test_ohne_eintraege_ist_nichts_offen(self, repo: Repo) -> None:
        assert list(repo.unresolved()) == []

    def test_ein_begonnener_lauf_ist_offen(self, repo: Repo) -> None:
        repo.begin(HANDELSTAG, KERZE_ZU, JETZT)

        assert list(repo.unresolved()) == [(HANDELSTAG, KERZE_ZU)]

    def test_ein_gescheiterter_lauf_bleibt_offen(self, repo: Repo) -> None:
        repo.begin(HANDELSTAG, KERZE_ZU, JETZT)
        repo.mark_failed(HANDELSTAG, KERZE_ZU, JETZT, "Keine Verbindung zur TWS")

        assert list(repo.unresolved()) == [(HANDELSTAG, KERZE_ZU)]

    def test_ein_gelungener_lauf_nicht(self, repo: Repo) -> None:
        repo.begin(HANDELSTAG, KERZE_ZU, JETZT)
        repo.mark_succeeded(HANDELSTAG, KERZE_ZU, JETZT)

        assert list(repo.unresolved()) == []

    def test_ein_gemeldeter_lauf_ebenfalls_nicht(self, repo: Repo) -> None:
        """Sonst meldete er sich bei jedem weiteren Start erneut."""
        repo.begin(HANDELSTAG, KERZE_ZU, JETZT)
        repo.mark_failed(HANDELSTAG, KERZE_ZU, JETZT, "TWS weg")
        repo.mark_alert_sent(HANDELSTAG, KERZE_ZU, JETZT)

        assert list(repo.unresolved()) == []

    def test_auch_laeufe_frueherer_tage_werden_gefunden(self, repo: Repo) -> None:
        vortag = date(2026, 8, 13)
        vortagskerze = KERZE_ZU - timedelta(days=1)
        repo.begin(vortag, vortagskerze, JETZT - timedelta(days=1))
        repo.mark_failed(vortag, vortagskerze, JETZT - timedelta(days=1), "TWS weg")
        repo.begin(HANDELSTAG, KERZE_ZU, JETZT)

        offen = list(repo.unresolved())

        assert offen == [(vortag, vortagskerze), (HANDELSTAG, KERZE_ZU)]
