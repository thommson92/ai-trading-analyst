"""Der Exportweg von Anfang bis Ende (ADR 0060).

Die Einzelteile haben eigene Tests. Hier laeuft der ganze Weg: Datenbaum
bauen, verschluesselt in ein Verzeichnis schreiben -- und danach so lesen,
wie es der Browser tut. Nur der Aufbau der Daten ist gefaelscht (Fakes statt
Datenbank); Verschluesselung, Namensbildung, Manifest und Pruefsummen sind
dieselben wie im Betrieb.

Das ist der Nachweis, den die Abnahmekriterien des PoC am Server verlangen:
Beim Anbieter liegt nichts Lesbares, und was dort liegt, ergibt mit der
Passphrase wieder genau den Stand.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from ai_trading_analyst.infrastructure.publishing import (
    Dateizustand,
    Exporteintrag,
    Exportziel,
    SnapshotPublisher,
    Verschluesselung,
    leite_schluessel_ab,
)
from ai_trading_analyst.infrastructure.publishing.crypto import MINDEST_ITERATIONEN
from ai_trading_analyst.presentation.export import BekannteDatei, iter_snapshot
from tests.unit.presentation.test_export_snapshot import lauf, quellen_mit

PASSPHRASE = "sieben-zufaellige-woerter-aus-dem-passwortmanager-xyz"


def veroeffentliche(tmp_path: Path, **kwargs: Any) -> SnapshotPublisher:
    quellen, _ = quellen_mit(("AAPL", "BRK B"), laeufe=(lauf(),))

    def dateien(bekannt: Mapping[str, Dateizustand]) -> Any:
        """Dieselbe Naht wie im Composition Root (ADR 0068)."""
        vorstand = {
            pfad: BekannteDatei(hash=stand.hash, fassung=stand.fassung)
            for pfad, stand in bekannt.items()
        }
        for datei in iter_snapshot(quellen, bekannt=vorstand):
            yield Exporteintrag(pfad=datei.pfad, inhalt=datei.inhalt, fassung=datei.fassung)

    return SnapshotPublisher(
        snapshot=dateien,
        ziel=Exportziel(
            wurzel=tmp_path / "public",
            zustandsdatei=tmp_path / "zustand.json",
            passphrase=kwargs.get("passphrase", PASSPHRASE),
            iterationen=MINDEST_ITERATIONEN,
        ),
    )


class _AlsBrowser:
    """Liest den Baum so, wie es die Oberflaeche tut.

    Bewusst ohne den Schreibcode: Der Weg beginnt beim Klartextkopf, leitet
    die Schluessel selbst ab und bildet die Dateinamen selbst. Wuerde er
    Objekte des Schreibers wiederverwenden, pruefte er nur, dass der Code mit
    sich selbst einig ist.
    """

    def __init__(self, wurzel: Path, passphrase: str) -> None:
        self.wurzel = wurzel
        self.kopf = json.loads(
            (wurzel / "data" / "manifest.head.json").read_text(encoding="utf-8")
        )
        assert self.kopf["kdf"] == "PBKDF2-HMAC-SHA256"
        assert self.kopf["cipher"] == "AES-256-GCM"
        assert self.kopf["iterations"] >= MINDEST_ITERATIONEN
        # Die Namensableitung wird hier von Hand nachgerechnet -- genau das
        # tut auch der Browser, und genau daran faellt auf, wenn die
        # Serverseite sie aendert.
        stamm = hashlib.pbkdf2_hmac(
            "sha256",
            passphrase.encode("utf-8"),
            bytes.fromhex(self.kopf["salt"]),
            int(self.kopf["iterations"]),
            32,
        )
        self._namen = hmac.digest(stamm, b"ata-export-name-v1", "sha256")
        self._krypto = Verschluesselung(
            leite_schluessel_ab(
                passphrase, bytes.fromhex(self.kopf["salt"]), int(self.kopf["iterations"])
            ),
            baum_id=str(self.kopf["tree_id"]),
            format_version=int(self.kopf["format"]),
        )
        self.manifest: dict[str, Any] = json.loads(
            self.lade_roh("data/manifest.json").decode("utf-8")
        )

    def dateiname(self, pfad: str) -> str:
        return hmac.new(self._namen, pfad.encode("utf-8"), "sha256").hexdigest()[:32]

    def lade_roh(self, pfad: str) -> bytes:
        datei = self.wurzel / "data" / self.dateiname(pfad)
        return self._krypto.entschluessele(pfad, datei.read_bytes())

    def lade(self, pfad: str) -> Any:
        klartext = self.lade_roh(pfad)
        erwartet = self.manifest["files"][pfad]
        assert hashlib.sha256(klartext).hexdigest() == erwartet, pfad
        return json.loads(klartext.decode("utf-8"))


class TestDerGanzeWeg:
    def test_alles_was_das_manifest_nennt_laesst_sich_lesen(self, tmp_path: Path) -> None:
        veroeffentliche(tmp_path).schreibe_baum()

        browser = _AlsBrowser(tmp_path / "public", PASSPHRASE)

        assert browser.manifest["files"]
        for pfad in browser.manifest["files"]:
            assert browser.lade(pfad) is not None

    def test_die_symbolzuordnung_fuehrt_zu_den_dateien(self, tmp_path: Path) -> None:
        """``BRK B`` wird zu ``BRK-B`` -- und die Oberflaeche findet den Chart
        ueber das Manifest statt ueber eine zweite Umsetzung der Regel."""
        veroeffentliche(tmp_path).schreibe_baum()
        browser = _AlsBrowser(tmp_path / "public", PASSPHRASE)

        name = browser.manifest["symbols"]["BRK B"]

        assert name == "BRK-B"
        assert browser.lade(f"data/stocks/{name}/chart.json")["symbol"] == "BRK B"

    def test_beim_anbieter_liegt_nichts_lesbares(self, tmp_path: Path) -> None:
        """Weder in den Namen noch in den Inhalten -- ausser dem Kopf, der
        Salt und Runden nennen muss."""
        veroeffentliche(tmp_path).schreibe_baum()

        for datei in (tmp_path / "public").rglob("*"):
            if not datei.is_file() or datei.name == "manifest.head.json":
                continue
            assert "AAPL" not in datei.name
            assert "chart" not in datei.name
            inhalt = datei.read_bytes()
            assert b"AAPL" not in inhalt
            assert b"symbol" not in inhalt

    def test_ohne_passphrase_ist_nichts_zu_lesen(self, tmp_path: Path) -> None:
        veroeffentliche(tmp_path).schreibe_baum()
        with pytest.raises(Exception):  # noqa: B017 -- InvalidTag der Bibliothek
            _AlsBrowser(tmp_path / "public", "falsche-passphrase")

    def test_der_zweite_lauf_schreibt_nur_das_manifest_neu(self, tmp_path: Path) -> None:
        """Der Grund fuer den Vergleich am Klartext: Sonst waere jeder Lauf
        ein vollstaendiger Upload."""
        veroeffentlicher = veroeffentliche(tmp_path)
        erst = veroeffentlicher.schreibe_baum().schreiben
        zweit = veroeffentlicher.schreibe_baum().schreiben

        assert erst.geschrieben == erst.dateien
        assert zweit.geschrieben == 1  # das Manifest, es traegt den Zeitpunkt
        assert zweit.unveraendert == zweit.dateien - 1

    def test_stufe_1_ergibt_denselben_baum_im_klartext(self, tmp_path: Path) -> None:
        """Stufe 1 und Stufe 2 unterscheiden sich in einer Schreibfunktion --
        nicht im Inhalt."""
        veroeffentliche(tmp_path, passphrase=None).schreibe_baum()

        manifest = json.loads(
            (tmp_path / "public" / "data" / "manifest.json").read_text(encoding="utf-8")
        )

        assert not (tmp_path / "public" / "data" / "manifest.head.json").exists()
        for pfad, erwartet in manifest["files"].items():
            inhalt = (tmp_path / "public" / pfad).read_bytes()
            assert hashlib.sha256(inhalt).hexdigest() == erwartet
