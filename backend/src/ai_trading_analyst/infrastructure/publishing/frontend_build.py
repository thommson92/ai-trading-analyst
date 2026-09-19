"""Der Bau der Oberflaeche im Exportschritt (ADR 0065).

Bis dahin war der Bau Handarbeit (Doc 14, Stufe K, Schritt 2), und wer ihn
vergass, schickte mit ``publish`` eine alte Oberflaeche zu neuen Daten
hinaus. Jetzt baut ``publish --full`` sie selbst: `next build` im
Zero-Knowledge-Modus in ein eigenes Verzeichnis, danach in das
veroeffentlichte Verzeichnis kopiert -- den Datenbaum darunter laesst der
Schritt stehen.

Derselbe Prozessstart wie beim Upload: Argumentliste, Erlaubnisliste fuer
die Umgebung, Ausgabe in Dateien, Zeitgrenze.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ai_trading_analyst.domain.scheduling import DashboardPublisherError
from ai_trading_analyst.observability.logging_setup import get_logger

from .upload import (
    _STEUERZEICHEN,
    PFLICHTDATEIEN,
    Prozessstarter,
    _letzte_zeilen,
    _starte_prozess,
    basisumgebung,
)

_logger = get_logger(__name__)

AUSGABEVERZEICHNIS = "out-verschluesselt"
"""Wohin `next build` im Zero-Knowledge-Modus schreibt (``frontend/next.config.ts``).
Getrennt von ``out/``, damit der LAN-Build stehen bleibt."""

DATENVERZEICHNIS = "data"
"""Der Datenbaum im veroeffentlichten Verzeichnis. Er gehoert dem
Exportschritt und bleibt beim Kopieren der Oberflaeche unangetastet."""

@dataclass(frozen=True, slots=True)
class Bauziel:
    frontend: Path
    """Das Frontend-Verzeichnis mit ``package.json`` und ``node_modules``."""
    verzeichnis: Path
    """Das veroeffentlichte Verzeichnis, in das die Oberflaeche kommt."""
    zeitgrenze: int
    datenmodus: Literal["verschluesselt", "statisch"] = "verschluesselt"
    """Das Verfahren des Baums -- Eigenschaft des Builds (ADR 0060). Folgt
    ``dashboard_export.encrypt``: Eine verschluesselte Oberflaeche ueber
    einem Klartextbaum fragte nach einer Passphrase, die es nicht gibt."""


@dataclass(frozen=True, slots=True)
class Baubericht:
    dateien: int
    dauer_sekunden: float

    def als_text(self) -> str:
        return f"{self.dateien} Dateien der Oberflaeche in {self.dauer_sekunden:.0f} s gebaut"


def next_befehl(frontend: Path) -> list[str]:
    """Wie `next build` gestartet wird -- ueber den Einstieg des Pakets, wie
    beim Upload-Werkzeug, damit die Zeitgrenze den richtigen Prozess trifft."""
    beschreibung = frontend / "node_modules" / "next" / "package.json"
    try:
        inhalt = json.loads(beschreibung.read_text(encoding="utf-8"))
    except (OSError, ValueError) as fehler:
        raise DashboardPublisherError(
            f"Das Bauwerkzeug ist nicht lesbar ({beschreibung}): {fehler}. Auf dem "
            "Server gehoert nach jedem 'git pull' ein 'npm ci' im Frontend dazu."
        ) from fehler
    programme = inhalt.get("bin") if isinstance(inhalt, dict) else None
    einstieg = programme.get("next") if isinstance(programme, dict) else None
    if not isinstance(einstieg, str):
        raise DashboardPublisherError(
            f"Das Bauwerkzeug nennt keinen Einstieg ({beschreibung}, Feld 'bin.next')."
        )
    pfad = (beschreibung.parent / einstieg).resolve()
    if not pfad.is_file():
        raise DashboardPublisherError(f"Der Einstieg des Bauwerkzeugs fehlt ({pfad}).")
    return ["node", str(pfad), "build"]


class FrontendBauer:
    def __init__(self, ziel: Bauziel, *, starter: Prozessstarter | None = None) -> None:
        self._ziel = ziel
        self._starter = starter if starter is not None else _starte_prozess

    def baue(self) -> Baubericht:
        """Baut die Oberflaeche und legt sie in das veroeffentlichte
        Verzeichnis -- ohne den Datenbaum darunter anzufassen.

        Raises:
            DashboardPublisherError: bei jedem Fehler. Der Baum wird dann
                nicht geschrieben und nichts geht hinaus -- Server und
                Anbieter bleiben beide auf dem alten Stand.
        """
        befehl = next_befehl(self._ziel.frontend)
        _logger.info("Oberflaeche wird gebaut: %s", self._ziel.frontend)
        begonnen = time.monotonic()
        try:
            ergebnis = self._starter(
                befehl, self._ziel.frontend, self._umgebung(), self._ziel.zeitgrenze
            )
        except FileNotFoundError as fehler:
            raise DashboardPublisherError(
                f"Das Bauwerkzeug laesst sich nicht starten: {fehler}. Fehlt Node?"
            ) from fehler
        except subprocess.TimeoutExpired as fehler:
            raise DashboardPublisherError(
                f"Der Bau der Oberflaeche hat nach {self._ziel.zeitgrenze} s nicht "
                "geantwortet und wurde abgebrochen."
            ) from fehler
        if ergebnis.returncode != 0:
            ausgabe = _STEUERZEICHEN.sub("", f"{ergebnis.stdout or ''}\n{ergebnis.stderr or ''}")
            raise DashboardPublisherError(
                f"Der Bau der Oberflaeche ist gescheitert (Rueckgabe {ergebnis.returncode}): "
                f"{_letzte_zeilen(ausgabe)}"
            )
        quelle = self._ziel.frontend / AUSGABEVERZEICHNIS
        fehlende = [name for name in PFLICHTDATEIEN if not (quelle / name).is_file()]
        if fehlende:
            raise DashboardPublisherError(
                f"Der Bau hat {', '.join(fehlende)} nicht erzeugt ({quelle})."
            )
        try:
            anzahl = self._kopiere(quelle)
        except OSError as fehler:
            # Unter Windows haelt schon ein offener Explorer eine Datei fest.
            raise DashboardPublisherError(
                f"Die Oberflaeche liess sich nicht in {self._ziel.verzeichnis} legen: {fehler}"
            ) from fehler
        return Baubericht(dateien=anzahl, dauer_sekunden=time.monotonic() - begonnen)

    def _kopiere(self, quelle: Path) -> int:
        """Alte Oberflaeche raus, neue rein, Datenbaum stehen lassen.

        Erst vollstaendig in ein Zwischenverzeichnis daneben kopiert, dann
        getauscht: Das Fenster, in dem das veroeffentlichte Verzeichnis ohne
        ``index.html`` steht, ist damit ein Verschieben je Eintrag und kein
        Kopieren je Datei. Die Buendel von Next tragen einen Hash je Bau;
        ohne das Aufraeumen blieben die Buendel jedes frueheren Baus liegen
        und gingen mit hinaus (Doc 14, Stufe K, Schritt 2).
        """
        ziel = self._ziel.verzeichnis
        zwischen = ziel.with_name(ziel.name + ".neu")
        if zwischen.exists():
            shutil.rmtree(zwischen)
        shutil.copytree(quelle, zwischen, ignore=shutil.ignore_patterns(DATENVERZEICHNIS))
        anzahl = sum(1 for pfad in zwischen.rglob("*") if pfad.is_file())
        ziel.mkdir(parents=True, exist_ok=True)
        for eintrag in ziel.iterdir():
            if eintrag.name == DATENVERZEICHNIS:
                continue
            if eintrag.is_dir() and not eintrag.is_symlink():
                shutil.rmtree(eintrag)
            else:
                eintrag.unlink()
        for eintrag in zwischen.iterdir():
            shutil.move(str(eintrag), str(ziel / eintrag.name))
        zwischen.rmdir()
        return anzahl

    def _umgebung(self) -> dict[str, str]:
        umgebung = basisumgebung()
        # Das Verfahren ist Eigenschaft des Builds (ADR 0060): Nur dieser
        # Wert macht aus der Oberflaeche die Zero-Knowledge-Fassung.
        umgebung["NEXT_PUBLIC_DATENMODUS"] = self._ziel.datenmodus
        umgebung["NEXT_TELEMETRY_DISABLED"] = "1"
        umgebung["NO_COLOR"] = "1"
        umgebung["CI"] = "1"
        return umgebung
