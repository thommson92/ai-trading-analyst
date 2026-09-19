"""Tests der Wartestelle zwischen Backfill und Analyse (ADR 0069).

Jeder Test hat eine harte Obergrenze: Ein Fehler in einer Wartestelle zeigt
sich als Test, der nicht mehr zurückkehrt, und ein hängender Testlauf ist
schlimmer als ein roter.
"""

from __future__ import annotations

import threading

import pytest

from ai_trading_analyst.application.bereitschaft import Bereitschaft

FRIST = 5.0
"""Sekunden, nach denen ein Test als hängend gilt."""


def im_hintergrund(arbeit: object) -> threading.Thread:
    faden = threading.Thread(target=arbeit)  # type: ignore[arg-type]
    faden.daemon = True
    faden.start()
    return faden


class TestMelden:
    def test_ein_gemeldetes_symbol_laesst_sofort_durch(self) -> None:
        bereitschaft = Bereitschaft()
        bereitschaft.melde("AAPL")

        assert bereitschaft.warte_auf("AAPL") is True

    def test_der_wartende_wird_geweckt(self) -> None:
        bereitschaft = Bereitschaft()
        ergebnis: list[bool] = []

        faden = im_hintergrund(lambda: ergebnis.append(bereitschaft.warte_auf("AAPL")))
        bereitschaft.melde("AAPL")
        faden.join(FRIST)

        assert not faden.is_alive(), "die Wartestelle haengt"
        assert ergebnis == [True]

    def test_ein_fremdes_symbol_weckt_nicht(self) -> None:
        bereitschaft = Bereitschaft()
        faden = im_hintergrund(lambda: bereitschaft.warte_auf("AAPL"))

        bereitschaft.melde("MSFT")
        faden.join(0.2)

        assert faden.is_alive(), "auf ein fremdes Symbol darf niemand durchkommen"
        bereitschaft.beende()
        faden.join(FRIST)


class TestEnde:
    """Die Zusicherung, auf die es ankommt: Niemand wartet ewig."""

    def test_nach_dem_ende_kehrt_der_wartende_zurueck(self) -> None:
        bereitschaft = Bereitschaft()
        ergebnis: list[bool] = []

        faden = im_hintergrund(lambda: ergebnis.append(bereitschaft.warte_auf("NIE")))
        bereitschaft.beende()
        faden.join(FRIST)

        assert not faden.is_alive(), "ein beendeter Backfill laesst niemanden haengen"
        assert ergebnis == [False]

    def test_nach_dem_ende_wartet_niemand_mehr(self) -> None:
        bereitschaft = Bereitschaft()
        bereitschaft.beende()

        assert bereitschaft.warte_auf("NIE") is False

    def test_ein_gemeldetes_symbol_bleibt_auch_nach_dem_ende_gemeldet(self) -> None:
        """Der Normalfall am Ende eines Laufs: Der Backfill ist durch, die
        Analyse arbeitet die letzten Symbole ab."""
        bereitschaft = Bereitschaft()
        bereitschaft.melde("AAPL")
        bereitschaft.beende()

        assert bereitschaft.warte_auf("AAPL") is True

    def test_das_ende_ist_mehrfach_aufrufbar(self) -> None:
        """Der Backfill-Thread meldet es im ``finally``; ein zweiter Aufruf
        aus einer Fehlerbehandlung darf nichts anrichten."""
        bereitschaft = Bereitschaft()
        bereitschaft.beende()
        bereitschaft.beende()

        assert bereitschaft.warte_auf("NIE") is False

    def test_viele_wartende_werden_alle_geweckt(self) -> None:
        bereitschaft = Bereitschaft()
        faeden = [im_hintergrund(lambda: bereitschaft.warte_auf("NIE")) for _ in range(8)]

        bereitschaft.beende()
        for faden in faeden:
            faden.join(FRIST)

        assert not [faden for faden in faeden if faden.is_alive()]


class TestZusammenspiel:
    def test_die_analyse_folgt_dem_backfill_in_dessen_reihenfolge(self) -> None:
        """Der Ablauf des Tageslaufs im Kleinen: Ein Melder, ein Wartender,
        und am Ende hat der Wartende jedes Symbol genau einmal gesehen."""
        symbole = [f"S{nummer}" for nummer in range(20)]
        bereitschaft = Bereitschaft()
        gesehen: list[str] = []

        def analysiere() -> None:
            for symbol in symbole:
                bereitschaft.warte_auf(symbol)
                gesehen.append(symbol)

        faden = im_hintergrund(analysiere)
        for symbol in symbole:
            bereitschaft.melde(symbol)
        bereitschaft.beende()
        faden.join(FRIST)

        assert not faden.is_alive(), "die Analyse haengt"
        assert gesehen == symbole

    def test_die_analyse_kommt_auch_durch_wenn_der_backfill_abbricht(self) -> None:
        """Nach dem Abbruch bleiben die uebrigen Symbole ungemeldet -- die
        Analyse rechnet trotzdem weiter, auf dem Bestand, den es gibt."""
        bereitschaft = Bereitschaft()
        gesehen: list[tuple[str, bool]] = []

        def analysiere() -> None:
            for symbol in ("A", "B", "C"):
                gesehen.append((symbol, bereitschaft.warte_auf(symbol)))

        faden = im_hintergrund(analysiere)
        bereitschaft.melde("A")
        bereitschaft.beende()  # der Backfill scheitert bei B
        faden.join(FRIST)

        assert not faden.is_alive(), "ein gescheiterter Backfill haelt die Analyse an"
        assert gesehen == [("A", True), ("B", False), ("C", False)]


@pytest.mark.parametrize("wiederholung", range(5))
def test_melden_und_warten_vertragen_sich_bei_wiederholung(wiederholung: int) -> None:
    """Gegen die Verschraenkung, die nur manchmal schiefgeht: Melder und
    Wartender starten gleichzeitig, mehrfach."""
    symbole = [f"S{nummer}" for nummer in range(50)]
    bereitschaft = Bereitschaft()
    gesehen: list[str] = []

    def melde_alle() -> None:
        for symbol in symbole:
            bereitschaft.melde(symbol)
        bereitschaft.beende()

    def analysiere() -> None:
        for symbol in symbole:
            bereitschaft.warte_auf(symbol)
            gesehen.append(symbol)

    melder = im_hintergrund(melde_alle)
    warter = im_hintergrund(analysiere)
    melder.join(FRIST)
    warter.join(FRIST)

    assert not warter.is_alive()
    assert gesehen == symbole


class TestEndeAbwarten:
    """Vor jedem TWS-Zugriff (ADR 0069, Punkt 2).

    Die Analyse kann vor dem Backfill fertig sein -- sie überspringt die
    Titel der Wiederholsperre, er führt sie bewusst weiter nach.
    """

    def test_wartet_bis_der_melder_durch_ist(self) -> None:
        bereitschaft = Bereitschaft()
        durch: list[str] = []

        def warte_und_merke() -> None:
            bereitschaft.warte_auf_ende()
            durch.append("ja")

        faden = im_hintergrund(warte_und_merke)
        faden.join(0.2)
        assert faden.is_alive(), "vor dem Ende darf niemand durchkommen"

        bereitschaft.beende()
        faden.join(FRIST)

        assert not faden.is_alive(), "die Wartestelle haengt"
        assert durch == ["ja"]

    def test_nach_dem_ende_kehrt_es_sofort_zurueck(self) -> None:
        bereitschaft = Bereitschaft()
        bereitschaft.beende()

        bereitschaft.warte_auf_ende()

    def test_gemeldete_symbole_allein_genuegen_nicht(self) -> None:
        """Alle Symbole gemeldet heisst nicht, dass der Backfill durch ist --
        er legt danach noch ab und gibt die Verbindung frei."""
        bereitschaft = Bereitschaft()
        bereitschaft.melde("AAPL")

        faden = im_hintergrund(bereitschaft.warte_auf_ende)
        faden.join(0.2)

        assert faden.is_alive()
        bereitschaft.beende()
        faden.join(FRIST)


class TestAnzahlAbwarten:
    """Für das Datengate (ADR 0069, Punkt 3)."""

    def test_wartet_bis_genug_gemeldet_ist(self) -> None:
        bereitschaft = Bereitschaft()
        ergebnis: list[int] = []

        faden = im_hintergrund(lambda: ergebnis.append(bereitschaft.warte_auf_anzahl(3)))
        bereitschaft.melde("A")
        bereitschaft.melde("B")
        faden.join(0.2)
        assert faden.is_alive(), "zwei sind nicht drei"

        bereitschaft.melde("C")
        faden.join(FRIST)

        assert not faden.is_alive()
        assert ergebnis == [3]

    def test_ein_vorzeitiges_ende_laesst_durch(self) -> None:
        """Ein Backfill, der bei Symbol zwei scheitert, darf das Gate nicht
        auf ewig warten lassen -- es soll dann gerade abbrechen."""
        bereitschaft = Bereitschaft()
        bereitschaft.melde("A")
        bereitschaft.beende()

        assert bereitschaft.warte_auf_anzahl(5) == 1

    def test_mehr_als_verlangt_ist_kein_problem(self) -> None:
        bereitschaft = Bereitschaft()
        for symbol in ("A", "B", "C", "D"):
            bereitschaft.melde(symbol)

        assert bereitschaft.warte_auf_anzahl(2) == 4
