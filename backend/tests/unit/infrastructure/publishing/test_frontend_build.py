"""Der Bau der Oberflaeche im Exportschritt (ADR 0065) -- gegen einen
eingesetzten Prozessstarter, `next` selbst laeuft hier nicht."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from ai_trading_analyst.domain.scheduling import DashboardPublisherError
from ai_trading_analyst.infrastructure.publishing import Bauziel, FrontendBauer, next_befehl


class Starter:
    def __init__(
        self, *, rueckgabewert: int = 0, erzeugt: bool = True, fehler: Exception | None = None
    ) -> None:
        self.rueckgabewert = rueckgabewert
        self.erzeugt = erzeugt
        self.fehler = fehler
        self.aufrufe: list[tuple[Sequence[str], Path, dict[str, str], int]] = []

    def __call__(
        self,
        befehl: Sequence[str],
        arbeitsverzeichnis: Path,
        umgebung: dict[str, str],
        zeitgrenze: int,
    ) -> subprocess.CompletedProcess[str]:
        self.aufrufe.append((befehl, arbeitsverzeichnis, umgebung, zeitgrenze))
        if self.fehler is not None:
            raise self.fehler
        if self.erzeugt:
            aus = arbeitsverzeichnis / "out-verschluesselt"
            (aus / "_next" / "static").mkdir(parents=True, exist_ok=True)
            (aus / "index.html").write_text("<html></html>", encoding="utf-8")
            (aus / "_headers").write_text("/*\n", encoding="utf-8")
            (aus / "_next" / "static" / "neu.js").write_text("neu", encoding="utf-8")
        return subprocess.CompletedProcess(list(befehl), self.rueckgabewert, "", "Fehlerzeile")


def frontend(tmp_path: Path) -> Path:
    wurzel = tmp_path / "frontend"
    paket = wurzel / "node_modules" / "next"
    (paket / "dist" / "bin").mkdir(parents=True)
    (paket / "package.json").write_text(
        json.dumps({"bin": {"next": "dist/bin/next"}}), encoding="utf-8"
    )
    (paket / "dist" / "bin" / "next").write_text("", encoding="utf-8")
    return wurzel


def ziel(tmp_path: Path) -> Path:
    verzeichnis = tmp_path / "var" / "dashboard"
    (verzeichnis / "data").mkdir(parents=True)
    (verzeichnis / "data" / "abc").write_text("chiffrat", encoding="utf-8")
    (verzeichnis / "_next" / "static").mkdir(parents=True)
    (verzeichnis / "_next" / "static" / "alt.js").write_text("alt", encoding="utf-8")
    (verzeichnis / "index.html").write_text("alt", encoding="utf-8")
    return verzeichnis


def test_der_befehl_geht_ueber_den_einstieg_des_pakets(tmp_path: Path) -> None:
    befehl = next_befehl(frontend(tmp_path))
    assert befehl[0] == "node"
    assert befehl[1].endswith("next") and befehl[2] == "build"


def test_ohne_werkzeug_eine_verstaendliche_meldung(tmp_path: Path) -> None:
    with pytest.raises(DashboardPublisherError, match="npm ci"):
        next_befehl(tmp_path / "leer")


def test_der_bau_ersetzt_die_oberflaeche_und_laesst_den_datenbaum_stehen(tmp_path: Path) -> None:
    starter = Starter()
    verzeichnis = ziel(tmp_path)
    bauer = FrontendBauer(
        Bauziel(frontend=frontend(tmp_path), verzeichnis=verzeichnis, zeitgrenze=30),
        starter=starter,
    )

    bericht = bauer.baue()

    assert bericht.dateien == 3
    assert (verzeichnis / "data" / "abc").read_text(encoding="utf-8") == "chiffrat"
    assert not (verzeichnis / "_next" / "static" / "alt.js").exists()
    assert (verzeichnis / "_next" / "static" / "neu.js").exists()
    assert (verzeichnis / "index.html").read_text(encoding="utf-8") == "<html></html>"


def test_die_umgebung_ist_eine_erlaubnisliste_mit_dem_zero_knowledge_modus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATA_DASHBOARD_EXPORT_PASSPHRASE", "geheim")
    monkeypatch.setenv("NODE_OPTIONS", "--require boese")
    starter = Starter()
    wurzel = frontend(tmp_path)
    FrontendBauer(
        Bauziel(frontend=wurzel, verzeichnis=ziel(tmp_path), zeitgrenze=30),
        starter=starter,
    ).baue()

    _, arbeitsverzeichnis, umgebung, zeitgrenze = starter.aufrufe[0]
    assert arbeitsverzeichnis == wurzel
    assert zeitgrenze == 30
    assert umgebung["NEXT_PUBLIC_DATENMODUS"] == "verschluesselt"
    assert "ATA_DASHBOARD_EXPORT_PASSPHRASE" not in umgebung
    assert "NODE_OPTIONS" not in umgebung


def test_ein_gescheiterter_bau_schreibt_nichts_und_nennt_die_ausgabe(tmp_path: Path) -> None:
    verzeichnis = ziel(tmp_path)
    bauer = FrontendBauer(
        Bauziel(frontend=frontend(tmp_path), verzeichnis=verzeichnis, zeitgrenze=30),
        starter=Starter(rueckgabewert=1, erzeugt=False),
    )
    with pytest.raises(DashboardPublisherError, match="Fehlerzeile"):
        bauer.baue()
    assert (verzeichnis / "index.html").read_text(encoding="utf-8") == "alt"


def test_ein_bau_ohne_pflichtdateien_wird_abgewiesen(tmp_path: Path) -> None:
    bauer = FrontendBauer(
        Bauziel(frontend=frontend(tmp_path), verzeichnis=ziel(tmp_path), zeitgrenze=30),
        starter=Starter(erzeugt=False),
    )
    with pytest.raises(DashboardPublisherError, match=r"index\.html"):
        bauer.baue()


def test_eine_zeitueberschreitung_ist_ein_bau_fehler(tmp_path: Path) -> None:
    bauer = FrontendBauer(
        Bauziel(frontend=frontend(tmp_path), verzeichnis=ziel(tmp_path), zeitgrenze=1),
        starter=Starter(fehler=subprocess.TimeoutExpired(cmd="next", timeout=1)),
    )
    with pytest.raises(DashboardPublisherError, match="1 s"):
        bauer.baue()


def test_der_statische_datenmodus_wird_durchgereicht(tmp_path: Path) -> None:
    starter = Starter()
    ziel_statisch = Bauziel(
        frontend=frontend(tmp_path),
        verzeichnis=ziel(tmp_path),
        zeitgrenze=30,
        datenmodus="statisch",
    )
    FrontendBauer(ziel_statisch, starter=starter).baue()
    assert starter.aufrufe[0][2]["NEXT_PUBLIC_DATENMODUS"] == "statisch"


def test_ein_fehler_beim_ablegen_ist_ein_bau_fehler_und_kein_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def kaputt(*_: object, **__: object) -> None:
        raise PermissionError("Datei gesperrt")

    monkeypatch.setattr(shutil, "copytree", kaputt)
    bauer = FrontendBauer(
        Bauziel(frontend=frontend(tmp_path), verzeichnis=ziel(tmp_path), zeitgrenze=30),
        starter=Starter(),
    )
    with pytest.raises(DashboardPublisherError, match="Datei gesperrt"):
        bauer.baue()
