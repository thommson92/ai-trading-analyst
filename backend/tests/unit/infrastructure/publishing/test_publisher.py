"""Der Exportschritt als Ganzes (ADR 0060, Entscheidung Punkt 2).

Er tut drei Dinge -- Baum holen, schreiben, Zustand fortschreiben -- und die
Tests hier pruefen vor allem das dritte: Salt und Baumkennung muessen ueber
Laeufe hinweg stehen bleiben, sonst waere jeder Lauf ein vollstaendig neuer
Baum und damit ein vollstaendiger Upload.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from ai_trading_analyst.domain.scheduling import (
    DashboardPublisherError,
    DashboardUploadError,
)
from ai_trading_analyst.infrastructure.publishing.crypto import MINDEST_ITERATIONEN
from ai_trading_analyst.infrastructure.publishing.publisher import (
    Exportziel,
    SnapshotPublisher,
)
from ai_trading_analyst.infrastructure.publishing.upload import Hochladebericht
from ai_trading_analyst.infrastructure.publishing.writer import Exportzustand

PASSPHRASE = "eine-lange-zufaellige-passphrase-aus-dem-manager"


def baum(*paare: tuple[str, bytes]) -> Iterator[tuple[str, bytes]]:
    yield from paare


class _Hochlader:
    """Zaehlt die Uploads und wirft auf Wunsch."""

    def __init__(self, *, fehler: Exception | None = None) -> None:
        self.fehler = fehler
        self.aufrufe = 0

    def lade_hoch(self) -> Hochladebericht:
        self.aufrufe += 1
        if self.fehler is not None:
            raise self.fehler
        return Hochladebericht(
            dateien_gesamt=1, dateien_gesendet=1, version="v1", dauer_sekunden=0.5
        )


def publisher(
    tmp_path: Path,
    *,
    passphrase: str | None = PASSPHRASE,
    iterationen: int = MINDEST_ITERATIONEN,
    inhalt: tuple[tuple[str, bytes], ...] = (("data/manifest.json", b"{}"),),
    hochlader: _Hochlader | None = None,
) -> SnapshotPublisher:
    return SnapshotPublisher(
        snapshot=lambda: baum(*inhalt),
        ziel=Exportziel(
            wurzel=tmp_path / "public",
            zustandsdatei=tmp_path / "zustand.json",
            passphrase=passphrase,
            iterationen=iterationen,
        ),
        hochlader=hochlader,
    )


class TestStufe1:
    def test_schreibt_klartext_und_keinen_kopf(self, tmp_path: Path) -> None:
        publisher(tmp_path, passphrase=None).schreibe_baum()
        assert (tmp_path / "public" / "data" / "manifest.json").read_bytes() == b"{}"
        assert not (tmp_path / "public" / "data" / "manifest.head.json").exists()


class TestStufe2:
    def test_schreibt_chiffrat_und_kopf(self, tmp_path: Path) -> None:
        publisher(tmp_path).schreibe_baum()
        datenwurzel = tmp_path / "public" / "data"
        kopf = json.loads((datenwurzel / "manifest.head.json").read_text(encoding="utf-8"))
        assert kopf["iterations"] == MINDEST_ITERATIONEN
        assert (datenwurzel / kopf["manifest"]).is_file()
        assert (datenwurzel / kopf["manifest"]).read_bytes() != b"{}"

    def test_der_kopf_nennt_den_namen_des_manifests(self, tmp_path: Path) -> None:
        """Der Browser hat sonst keinen Anfang: Alle anderen Namen stehen im
        Manifest, und das Manifest selbst ist ebenso opak."""
        publisher(tmp_path).schreibe_baum()
        datenwurzel = tmp_path / "public" / "data"
        kopf = json.loads((datenwurzel / "manifest.head.json").read_text(encoding="utf-8"))
        namen = {p.name for p in datenwurzel.iterdir()} - {"manifest.head.json"}
        assert kopf["manifest"] in namen

    def test_zu_wenige_runden_brechen_ab(self, tmp_path: Path) -> None:
        with pytest.raises(DashboardPublisherError, match="Verschluesselung"):
            publisher(tmp_path, iterationen=1000).schreibe_baum()


class TestZustandUeberLaeufe:
    def test_salt_und_baumkennung_bleiben_stehen(self, tmp_path: Path) -> None:
        """Wuerden sie je Lauf neu gezogen, aenderte sich jeder Dateiname."""
        veroeffentlicher = publisher(tmp_path)
        veroeffentlicher.schreibe_baum()
        erst = Exportzustand.lade(tmp_path / "zustand.json")

        veroeffentlicher.schreibe_baum()
        zweit = Exportzustand.lade(tmp_path / "zustand.json")

        assert erst is not None and zweit is not None
        assert erst.salt == zweit.salt
        assert erst.baum_id == zweit.baum_id
        assert erst.dateien == zweit.dateien

    def test_zweiter_lauf_schreibt_nichts_neu(self, tmp_path: Path) -> None:
        veroeffentlicher = publisher(tmp_path)
        veroeffentlicher.schreibe_baum()
        bericht = veroeffentlicher.schreibe_baum().schreiben
        assert bericht.geschrieben == 0
        assert bericht.unveraendert == 1

    def test_voll_schreibt_alles_neu(self, tmp_path: Path) -> None:
        """Der Weg nach jedem Zweifel, ob draussen steht, was hier liegt."""
        veroeffentlicher = publisher(tmp_path)
        veroeffentlicher.schreibe_baum()
        bericht = veroeffentlicher.schreibe_baum(voll=True).schreiben
        assert bericht.geschrieben == 1
        assert bericht.unveraendert == 0

    def test_neue_passphrase_ergibt_einen_neuen_baum(self, tmp_path: Path) -> None:
        """Alte Dateien gelten danach als verwaist und verschwinden -- statt
        als lesbare Reste unter alten Namen liegen zu bleiben."""
        publisher(tmp_path).schreibe_baum()
        vorher = {p.name for p in (tmp_path / "public" / "data").iterdir()}

        bericht = publisher(
            tmp_path, passphrase="eine-ganz-andere-passphrase"
        ).schreibe_baum().schreiben

        nachher = {p.name for p in (tmp_path / "public" / "data").iterdir()}
        assert bericht.geschrieben == 1
        assert bericht.entfernt == 1
        assert nachher != vorher
        assert nachher & vorher == {"manifest.head.json"}


class TestFehler:
    def test_nicht_schreibbares_ziel_wird_zum_portfehler(self, tmp_path: Path) -> None:
        """Der Tageslauf isoliert genau diesen Fehlertyp."""
        sperre = tmp_path / "public"
        sperre.write_text("keine Datei erwartet, sondern ein Verzeichnis", encoding="utf-8")
        with pytest.raises(DashboardPublisherError, match="nicht schreibbar"):
            publisher(tmp_path).schreibe_baum()

    def test_publish_setzt_den_port_um(self, tmp_path: Path) -> None:
        """Die Portfassung ohne Rueckgabewert; der Bericht steht im Protokoll."""
        publisher(tmp_path).publish()
        assert (tmp_path / "public" / "data" / "manifest.head.json").is_file()


class TestSperre:
    def test_ein_zweiter_export_wird_abgewiesen(self, tmp_path: Path) -> None:
        """Zwei gleichzeitige Laeufe schrieben zwei verschiedene Manifeste.

        Der Browser folgte dem, das gewonnen hat, und faende bei jeder Datei
        des anderen Laufs eine abweichende Pruefsumme -- ein Fehlalarm, der
        genau wie der Angriff aussieht, gegen den die Pruefsumme steht.
        """
        sperre = tmp_path / "zustand.json.lock"
        sperre.parent.mkdir(parents=True, exist_ok=True)
        sperre.write_text("999 laeuft", encoding="utf-8")

        with pytest.raises(DashboardPublisherError, match="anderer Export"):
            publisher(tmp_path).schreibe_baum()

    def test_die_sperre_wird_danach_wieder_freigegeben(self, tmp_path: Path) -> None:
        veroeffentlicher = publisher(tmp_path)
        veroeffentlicher.schreibe_baum()
        assert not (tmp_path / "zustand.json.lock").exists()
        veroeffentlicher.schreibe_baum()

    def test_auch_nach_einem_fehler_bleibt_keine_sperre_liegen(self, tmp_path: Path) -> None:
        """Eine Sperre, die niemand mehr aufhebt, waere schlimmer als keine:
        Sie hielte den Tageslauf still vom Export ab."""
        with pytest.raises(DashboardPublisherError):
            publisher(tmp_path, iterationen=1000).schreibe_baum()
        assert not (tmp_path / "zustand.json.lock").exists()

    def test_eine_liegengebliebene_sperre_wird_uebergangen(self, tmp_path: Path) -> None:
        import os
        import time

        sperre = tmp_path / "zustand.json.lock"
        sperre.parent.mkdir(parents=True, exist_ok=True)
        sperre.write_text("999 abgestuerzt", encoding="utf-8")
        alt = time.time() - 7200
        os.utime(sperre, (alt, alt))

        bericht = publisher(tmp_path).schreibe_baum().schreiben

        assert bericht.geschrieben == 1


class TestDerWegNachDraussen:
    """Der Upload haengt am Schreiben und nicht daneben (ADR 0060, E4)."""

    def test_ohne_hochlader_endet_der_weg_im_verzeichnis(self, tmp_path: Path) -> None:
        """Die Rueckfallstufe ``target: directory`` -- schreiben, nicht senden."""
        bericht = publisher(tmp_path).schreibe_baum()

        assert bericht.hochladen is None
        assert bericht.als_text() == bericht.schreiben.als_text()

    def test_nach_dem_schreiben_geht_der_baum_hinaus(self, tmp_path: Path) -> None:
        hochlader = _Hochlader()

        bericht = publisher(tmp_path, hochlader=hochlader).schreibe_baum()

        assert hochlader.aufrufe == 1
        assert bericht.hochladen is not None
        assert bericht.hochladen.version == "v1"
        assert "v1" in bericht.als_text()

    def test_ein_gescheitertes_schreiben_sendet_nichts(self, tmp_path: Path) -> None:
        """**Die wichtigste Reihenfolge in diesem Schritt.** Ginge ein halb
        geschriebener Baum hinaus, stuenden draussen Dateien neben einem
        Manifest, das sie nicht kennt -- und der Browser meldete genau die
        Pruefsummenverletzung, gegen die die Pruefsumme steht."""
        hochlader = _Hochlader()

        with pytest.raises(DashboardPublisherError):
            publisher(tmp_path, iterationen=1000, hochlader=hochlader).schreibe_baum()

        assert hochlader.aufrufe == 0

    def test_senden_false_laesst_den_baum_liegen(self, tmp_path: Path) -> None:
        """``publish --no-upload``: schreiben, ohne eine Fassung beim
        Anbieter zu erzeugen."""
        hochlader = _Hochlader()

        bericht = publisher(tmp_path, hochlader=hochlader).schreibe_baum(senden=False)

        assert hochlader.aufrufe == 0
        assert bericht.hochladen is None
        assert bericht.schreiben.geschrieben == 1

    def test_ein_gescheiterter_upload_laesst_den_baum_geschrieben(self, tmp_path: Path) -> None:
        """Der Zustand ist zu diesem Zeitpunkt gespeichert, und das soll so
        sein: Was auf dem Server liegt, liegt dort. Der naechste Lauf
        schreibt nur noch das Manifest neu und sendet wieder alles, was
        draussen fehlt -- das Werkzeug vergleicht selbst."""
        hochlader = _Hochlader(fehler=DashboardUploadError("Leitung weg"))

        with pytest.raises(DashboardUploadError):
            publisher(tmp_path, hochlader=hochlader).schreibe_baum()

        assert (tmp_path / "zustand.json").is_file()
        assert not (tmp_path / "zustand.json.lock").exists()
