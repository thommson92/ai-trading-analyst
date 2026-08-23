"""Golden Master fuer Screener und Backtesting (Doc 10, Paragraph 16).

Das Projekt aendert seine Verfahren bewusst und versioniert sie dabei
(technical-v1 bis v3, Prompt v1 bis v3). Auf der Screener- und
Backtest-Seite fehlte dafuer bislang das Sicherheitsnetz: Eine Aenderung an
der Kerzenbildung, an der Indikatorrechnung, an der 2-aus-3-Regel oder am
Cooldown verschob die Ergebnisse, ohne dass ein Test angeschlagen haette.
Die Unit-Tests pruefen jede Regel einzeln an eigens gebauten Kerzen -- sie
sehen nicht, was eine Aenderung ueber eine ganze Reihe hinweg bewirkt.

Genau das leisten diese Tests: Sie rechnen die vollstaendige Kette ueber
eingefrorene Bars und vergleichen das Ergebnis mit einer aufgezeichneten
Datei. Weicht etwas ab, bricht der Test -- und die Abweichung ist entweder
ein Fehler oder eine gewollte Verfahrensaenderung, die mit einer neuen
Aufzeichnung und einer Versionsnummer einhergeht.

**Neu aufzeichnen** (nur nach einer *gewollten* Aenderung, und der Diff der
``*.expected.json`` gehoert dann in den Commit angesehen):

    ATA_GOLDEN_MASTER_RECORD=1 .venv/bin/python -m pytest tests/golden

Laeuft ohne Netz, ohne Datenbank und ohne TWS. Zur Herkunft der Daten siehe
``generate_bars.py`` -- sie sind erzeugt, nicht gemessen, und der Modulkopf
dort sagt, was daraus folgt.
"""

from __future__ import annotations

import os

import pytest

from tests.golden.generate_bars import FAELLE as ERZEUGTE_FAELLE
from tests.golden.generate_bars import erzeuge_reihe
from tests.golden.pipeline import (
    DATA_DIR,
    GoldenCase,
    available_cases,
    compute_snapshot,
    read_bars,
    read_expected,
    write_expected,
)

AUFZEICHNEN = os.environ.get("ATA_GOLDEN_MASTER_RECORD") == "1"

FAELLE = available_cases()


def test_es_gibt_ueberhaupt_eingefrorene_faelle() -> None:
    """Sonst liefe die Parametrisierung leer durch und meldete Erfolg.

    Genau die Sorte stiller Ausfall, gegen die der Golden Master da ist: Ein
    versehentlich geloeschtes Datenverzeichnis saehe aus wie eine gruene
    Suite.
    """
    assert FAELLE, "tests/golden/data enthaelt keine *.bars.csv"


@pytest.mark.parametrize("fall", FAELLE, ids=lambda fall: fall.name)
class TestGoldenMaster:
    def test_die_kette_liefert_das_aufgezeichnete_ergebnis(self, fall: GoldenCase) -> None:
        bars = read_bars(fall.bars_path)
        aktuell = compute_snapshot(bars)

        if AUFZEICHNEN:
            write_expected(fall.expected_path, aktuell)
            pytest.skip(f"{fall.name} neu aufgezeichnet")

        assert fall.expected_path.exists(), (
            f"Fuer '{fall.name}' fehlt die Aufzeichnung. Einmalig mit "
            "ATA_GOLDEN_MASTER_RECORD=1 anlegen und den Inhalt pruefen, bevor er "
            "committet wird."
        )
        assert aktuell == read_expected(fall.expected_path)

    def test_der_fall_reicht_ueber_den_warmup_hinaus(self, fall: GoldenCase) -> None:
        """Sonst bewachte der Golden Master nur die Kerzenbildung.

        Unterhalb von 250 Kerzen antwortet die Kandidatenpruefung
        ausnahmslos mit ``UNKNOWN_DATA_INCOMPLETE``, und der Backtest faende
        keinen einzigen Entscheidungspunkt -- die Aufzeichnung saehe stabil
        aus, weil sie nichts enthielte.
        """
        snapshot = compute_snapshot(read_bars(fall.bars_path))
        auswertbar = snapshot["candles"] - 250
        assert auswertbar > 0, f"{fall.name} hat nur {snapshot['candles']} Kerzen"

    def test_die_rechnung_ist_in_sich_wiederholbar(self, fall: GoldenCase) -> None:
        """Zweimal dieselbe Eingabe, zweimal dasselbe Ergebnis.

        Faengt eine Abhaengigkeit von der Uhr, von einer Mengenreihenfolge
        oder von einer zufaelligen Kennung ab -- die brechen den Golden
        Master sonst erst bei irgendeinem spaeteren Lauf und sehen dann wie
        eine Verfahrensaenderung aus.
        """
        bars = read_bars(fall.bars_path)

        assert compute_snapshot(bars) == compute_snapshot(bars)


class TestErzeugteDaten:
    """Die eingefrorenen Bars muessen aus dem Erzeuger reproduzierbar sein.

    Ohne diese Pruefung liesse sich eine Bar-Datei von Hand aendern, ohne
    dass es auffiele -- und der Golden Master bewachte dann eine Reihe, die
    niemand mehr erklaeren kann.

    Gilt ausdruecklich nur fuer die ``synthetic-*``-Faelle. Ein echter
    Ausschnitt vom Server (``cli export-bars``) stammt nicht aus dem
    Erzeuger und wird hier nicht geprueft.
    """

    def test_der_erzeuger_liefert_genau_die_abgelegten_bars(self) -> None:
        assert ERZEUGTE_FAELLE, "der Erzeuger kennt keinen einzigen Fall"
        for name, (seed, startkurs, drift, handelstage) in ERZEUGTE_FAELLE.items():
            abgelegt = read_bars(DATA_DIR / f"{name}.bars.csv")
            assert tuple(erzeuge_reihe(seed, startkurs, drift, handelstage)) == abgelegt, (
                f"{name}.bars.csv weicht vom Erzeuger ab -- entweder von Hand "
                "geaendert oder generate_bars.py hat sich veraendert."
            )


@pytest.mark.parametrize("fall", FAELLE, ids=lambda fall: fall.name)
class TestBewachungsumfang:
    """Bewacht der Golden Master ueberhaupt das, was er bewachen soll?

    Eine Aufzeichnung voller Nullwerte saehe genauso stabil aus wie eine
    aussagekraeftige -- und braeche bei keiner Aenderung an der Rechnung,
    weil es nichts zu verschieben gaebe.
    """

    def test_mindestens_eine_kombination_hat_echte_kennzahlen(self, fall: GoldenCase) -> None:
        """Sonst bliebe die gesamte Kennzahlenrechnung unbewacht.

        Unter zehn deduplizierten Ereignissen gibt der Backtest fuer eine
        Kombination gar keine Kennzahl aus. Waeren alle Kombinationen
        darunter, enthielte die Aufzeichnung ausschliesslich ``null``.
        """
        snapshot = compute_snapshot(read_bars(fall.bars_path))
        mit_kennzahlen = [
            horizont
            for ergebnis in snapshot["backtest"]
            for horizont in ergebnis["horizons"]
            if horizont["hit_rate"] is not None
        ]

        assert mit_kennzahlen, (
            f"{fall.name}: keine einzige Kombination kommt ueber "
            "minimum_sample_size -- die Kennzahlenrechnung ist unbewacht."
        )
        beispiel = mit_kennzahlen[0]
        for feld in ("mean_return", "median_return", "max_loss", "drawdown"):
            assert beispiel[feld] is not None, f"{feld} ist trotz ausreichender Stichprobe leer"

    def test_auch_eine_zu_duenne_stichprobe_ist_aufgezeichnet(self, fall: GoldenCase) -> None:
        """Der Gegenfall: keine Kennzahl statt einer schwachen.

        Er ist genauso zu bewachen. Wuerde eine Aenderung anfangen, unter
        der Mindeststichprobe doch Werte auszugeben, faellt es hier auf.
        """
        snapshot = compute_snapshot(read_bars(fall.bars_path))
        zu_duenn = [
            horizont
            for ergebnis in snapshot["backtest"]
            for horizont in ergebnis["horizons"]
            if horizont["confidence"] == "INSUFFICIENT_DATA"
        ]

        assert zu_duenn, f"{fall.name}: kein Fall einer zu duennen Stichprobe aufgezeichnet"
        assert all(horizont["hit_rate"] is None for horizont in zu_duenn)

    def test_es_gibt_kandidaten_und_nicht_kandidaten(self, fall: GoldenCase) -> None:
        """Ein Fall ohne einen einzigen Kandidaten bewachte die 2-aus-3-Regel nicht."""
        zaehlung = compute_snapshot(read_bars(fall.bars_path))["screening"]["status_counts"]

        assert zaehlung.get("CANDIDATE", 0) > 0
        assert zaehlung.get("NOT_CANDIDATE", 0) > 0


def test_alle_drei_konfidenzstufen_sind_aufgezeichnet() -> None:
    """Ueber beide Faelle hinweg, nicht je Fall.

    Die drei Stufen verhalten sich unterschiedlich: ``INSUFFICIENT_DATA``
    gibt gar keine Kennzahl aus, ``LOW_SAMPLE`` und ``NORMAL`` geben
    vollstaendige. Waere eine Stufe nirgends aufgezeichnet, liesse eine
    Aenderung, die sie nicht mehr vergibt, die Dateien byteweise gleich und
    die Suite gruen -- der Golden Master bewachte dann eine Einstufung, die
    in seinen Daten gar nicht vorkommt.
    """
    gesehen = {
        horizont["confidence"]
        for fall in FAELLE
        for ergebnis in compute_snapshot(read_bars(fall.bars_path))["backtest"]
        for horizont in ergebnis["horizons"]
    }

    assert gesehen == {"INSUFFICIENT_DATA", "LOW_SAMPLE", "NORMAL"}
