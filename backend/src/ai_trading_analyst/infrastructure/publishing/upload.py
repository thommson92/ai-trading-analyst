"""Der Weg nach draussen: der Datenbaum geht zum Anbieter (ADR 0060, E4).

Erprobt wurde am 2026-09-17 von Hand, was hier eingebaut ist -- ``wrangler``
als Unterprozess, mit einem Token, das genau ein Recht traegt (Doc 14,
Stufe L). Der Datenweg DW1, ein Upload aus Python heraus, waere der schmalere
gewesen; die Schnittstelle des Anbieters fuer statische Dateien ist aber
mehrstufig und ohne das Werkzeug muehsam nachzubauen. Damit wird Node vom
Bauwerkzeug zum Auslieferungswerkzeug (Nachtrag zu ADR 0052, Punkt 2).

**Drei Dinge macht dieses Modul bewusst anders, als ein Aufruf es muesste:**

1. Es schreibt die Konfigurationsdatei **selbst**, bei jedem Upload neu. Die
   Zeile ``"preview_urls": false`` steht damit als Konstante im Code und kann
   nicht von Hand verrutschen -- sie ist die einzige Sperre davor, dass alle
   je hochgeladenen Fassungen wieder erreichbar werden.
2. Es gibt dem Unterprozess **nicht** die eigene Umgebung mit, sondern eine
   Erlaubnisliste. Ein fremdes Werkzeug hat die Export-Passphrase, die
   Datenbankverbindung und den Modellschluessel nicht zu sehen.
3. Es prueft die Ausgabe auf Vorschau-Adressen und meldet einen Fund, statt
   ihn zu protokollieren. Doc 14, Stufe L, Schritt 7 verlangt genau das,
   sobald der Exportschritt den Upload uebernimmt.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ai_trading_analyst.domain.scheduling import (
    DashboardPreviewUrlError,
    DashboardUploadError,
)
from ai_trading_analyst.observability.logging_setup import get_logger

_logger = get_logger(__name__)

KOMPATIBILITAETSDATUM = "2026-09-17"
"""Festgeschrieben, nicht mitlaufend.

Das Datum bestimmt, nach welchen Regeln der Anbieter den Worker ausfuehrt.
Ein Wert, der mit dem Kalender wandert, aenderte dieses Verhalten irgendwann
ohne Anlass und ohne dass jemand es ausgeloest haette. Angehoben wird er von
Hand, wenn es einen Grund gibt -- dann mit einer Probe danach.
"""

KONFIGURATIONSNAME = "wrangler.jsonc"

PFLICHTDATEIEN = ("index.html", "_headers")
"""Ohne die zwei geht der Baum nicht hinaus.

``index.html`` ist die Oberflaeche; fehlt sie, laege draussen ein Haufen
Chiffrat ohne etwas, das ihn anzeigt. ``_headers`` traegt CSP, HSTS und die
uebrigen Sicherheits-Header; fehlt sie, liefert der Anbieter die Seite ohne
sie aus, und das faellt niemandem auf. Beide entstehen beim Bau der
Oberflaeche (Doc 14, Stufe K, Schritt 2) und nicht in diesem Schritt -- er
prueft deshalb nur, dass sie da sind.
"""

_UMGEBUNG_UEBERNOMMEN = (
    "PATH",
    "HOME",
    "USERPROFILE",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "TEMP",
    "TMP",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "PROGRAMDATA",
    "NUMBER_OF_PROCESSORS",
)
"""Was der Unterprozess von der eigenen Umgebung sieht -- und sonst nichts.

Eine Erlaubnisliste statt eines Abzugs von ``os.environ``: Damit kann kein
spaeter hinzukommendes ``ATA_``-Geheimnis versehentlich mitwandern. Node
braucht den Suchpfad und unter Windows die Handvoll Systemvariablen darunter;
``NODE_OPTIONS`` steht ausdruecklich nicht dabei, weil darueber Code in den
Prozess kaeme.
"""

_WORKERS_DEV = re.compile(r"https?://([a-z0-9][a-z0-9.-]*\.workers\.dev)", re.IGNORECASE)
_GELESEN = re.compile(r"Read (\d+) files? from the assets directory", re.IGNORECASE)
_GESENDET = re.compile(r"Uploaded (\d+) files?", re.IGNORECASE)
_VERSION = re.compile(r"Current Version ID:\s*([0-9A-Za-z-]{8,})")


@dataclass(frozen=True, slots=True)
class Hochladeziel:
    """Wohin der Datenbaum geht und womit."""

    worker: str
    konto: str
    token: str
    baum: Path
    """Das Verzeichnis, das hochgeladen wird -- Oberflaeche und ``data/``."""
    arbeitsverzeichnis: Path
    """Wo die erzeugte Konfigurationsdatei entsteht. **Nicht im Baum.**"""
    befehl: Sequence[str]
    """Wie das Werkzeug gestartet wird, z. B. ``["node", ".../wrangler.js"]``."""
    zeitgrenze: int


@dataclass(frozen=True, slots=True)
class Hochladebericht:
    """Was ein Upload bewirkt hat -- fuer das Protokoll.

    Die drei Zahlen sind ``None``, wenn sie sich aus der Ausgabe nicht lesen
    liessen. Das ist Absicht: Sie stehen im Protokoll und sonst nirgends, und
    keine Entscheidung haengt an ihnen. Ein Werkzeug, das seine Ausgabe
    umformuliert, soll den Lauf nicht scheitern lassen.
    """

    dateien_gesamt: int | None
    dateien_gesendet: int | None
    version: str | None
    dauer_sekunden: float

    def als_text(self) -> str:
        gesendet = "?" if self.dateien_gesendet is None else str(self.dateien_gesendet)
        gesamt = "?" if self.dateien_gesamt is None else str(self.dateien_gesamt)
        return (
            f"{gesendet} von {gesamt} Dateien gesendet, Version "
            f"{self.version or 'unbekannt'}, {self.dauer_sekunden:.1f} s"
        )


class Hochlader(Protocol):
    """Der Ausgang zum Anbieter.

    Raises:
        DashboardUploadError: wenn der Baum nicht hinausging.
        DashboardPreviewUrlError: wenn er hinausging, der Anbieter aber
            Vorschau-Adressen vergeben hat.
    """

    def lade_hoch(self) -> Hochladebericht: ...


Prozessstarter = Callable[
    [Sequence[str], Path, dict[str, str], int], "subprocess.CompletedProcess[str]"
]


def _starte_prozess(
    befehl: Sequence[str],
    arbeitsverzeichnis: Path,
    umgebung: dict[str, str],
    zeitgrenze: int,
) -> subprocess.CompletedProcess[str]:
    """Der einzige Prozessstart im Produktivcode dieses Projekts.

    Als Argumentliste und ohne ``shell=True``: Der Worker-Name kommt aus der
    Umgebung, und eine Zeichenkette, die eine Shell auseinandernimmt, waere
    ein Einfallstor ohne Not. ``stdin`` ist geschlossen, damit das Werkzeug
    in einem unbeaufsichtigten Lauf nicht auf eine Antwort wartet, die
    niemand gibt.
    """
    return subprocess.run(
        list(befehl),
        cwd=arbeitsverzeichnis,
        env=umgebung,
        capture_output=True,
        text=True,
        check=False,
        timeout=zeitgrenze,
        stdin=subprocess.DEVNULL,
    )


class WranglerHochlader:
    """Setzt ``Hochlader`` mit dem Werkzeug des Anbieters um."""

    def __init__(self, ziel: Hochladeziel, *, starter: Prozessstarter | None = None) -> None:
        self._ziel = ziel
        self._starter = starter if starter is not None else _starte_prozess

    def lade_hoch(self) -> Hochladebericht:
        self._pruefe_baum()
        konfiguration = self.schreibe_konfiguration()
        befehl = [*self._ziel.befehl, "deploy", "--config", str(konfiguration)]

        _logger.info("Datenbaum geht hinaus: %s", self._ziel.baum)
        begonnen = time.monotonic()
        try:
            ergebnis = self._starter(
                befehl,
                self._ziel.arbeitsverzeichnis,
                self._umgebung(),
                self._ziel.zeitgrenze,
            )
        except FileNotFoundError as fehler:
            raise DashboardUploadError(
                f"Das Upload-Werkzeug laesst sich nicht starten: {fehler}. "
                "Fehlt Node auf dem Server, oder wurde 'npm ci' im Frontend "
                "nach dem letzten 'git pull' nicht ausgefuehrt?"
            ) from fehler
        except subprocess.TimeoutExpired as fehler:
            raise DashboardUploadError(
                f"Der Upload hat nach {self._ziel.zeitgrenze} s nicht geantwortet "
                "und wurde abgebrochen. Der Datenbaum liegt geschrieben auf dem Server."
            ) from fehler
        dauer = time.monotonic() - begonnen

        ausgabe = f"{ergebnis.stdout or ''}\n{ergebnis.stderr or ''}"
        if ergebnis.returncode != 0:
            raise DashboardUploadError(
                f"Der Upload endete mit Rueckgabewert {ergebnis.returncode}: "
                f"{_letzte_zeilen(ausgabe)}"
            )

        bericht = _lies_bericht(ausgabe, dauer)
        _logger.info("Datenbaum gesendet: %s", bericht.als_text())
        self._pruefe_vorschauadressen(ausgabe)
        return bericht

    def schreibe_konfiguration(self) -> Path:
        """Legt die Konfigurationsdatei neu an und gibt ihren Pfad zurueck.

        **Bei jedem Upload neu, und ohne zu fragen, was vorher dastand.** Der
        Zielpfad wird relativ zur Datei angegeben, weil das Werkzeug ihn so
        aufloest (am 2026-09-17 beobachtet) und der Aufruf ohnehin aus ihrem
        Verzeichnis kommt -- damit stimmen beide Lesarten ueberein.
        """
        self._ziel.arbeitsverzeichnis.mkdir(parents=True, exist_ok=True)
        pfad = self._ziel.arbeitsverzeichnis / KONFIGURATIONSNAME
        verzeichnis = os.path.relpath(self._ziel.baum, self._ziel.arbeitsverzeichnis)
        pfad.write_text(
            "{\n"
            "  // Erzeugt vom Exportschritt, bei jedem Upload neu (ADR 0060, E4).\n"
            "  // Aenderungen von Hand gehen beim naechsten Lauf verloren.\n"
            f"  \"name\": {json.dumps(self._ziel.worker)},\n"
            f"  \"compatibility_date\": \"{KOMPATIBILITAETSDATUM}\",\n"
            "  \"workers_dev\": true,\n"
            "  // Ausdruecklich, und das ist die Falle dieser Datei: preview_urls\n"
            "  // folgt ohne Angabe dem Wert von workers_dev, also true. Ein Upload\n"
            "  // ohne diese Zeile schaltete abgeschaltete Vorschau-Adressen\n"
            "  // stillschweigend wieder ein -- und weil Salt und Baumkennung ueber\n"
            "  // alle Exporte stabil sind, stuenden damit alle je hochgeladenen\n"
            "  // Fassungen wieder unter demselben Schluessel erreichbar.\n"
            "  \"preview_urls\": false,\n"
            f"  \"assets\": {{ \"directory\": {json.dumps(verzeichnis.replace(os.sep, '/'))} }}\n"
            "}\n",
            encoding="utf-8",
        )
        return pfad

    def _pruefe_baum(self) -> None:
        fehlend = [name for name in PFLICHTDATEIEN if not (self._ziel.baum / name).is_file()]
        if not fehlend:
            return
        raise DashboardUploadError(
            f"Im Datenbaum fehlen {', '.join(fehlend)} -- es ginge Chiffrat ohne "
            "Oberflaeche und ohne Sicherheits-Header hinaus. Beide entstehen beim "
            "Bau der Oberflaeche (Doc 14, Stufe K, Schritt 2), nicht in diesem Schritt."
        )

    def _umgebung(self) -> dict[str, str]:
        umgebung = {
            name: wert
            for name in _UMGEBUNG_UEBERNOMMEN
            if (wert := os.environ.get(name)) is not None
        }
        umgebung["CLOUDFLARE_API_TOKEN"] = self._ziel.token
        umgebung["CLOUDFLARE_ACCOUNT_ID"] = self._ziel.konto
        # Keine Nutzungsdaten an den Anbieter, keine Steuerzeichen in der
        # Ausgabe -- die wird gelesen, nicht angesehen.
        umgebung["WRANGLER_SEND_METRICS"] = "false"
        umgebung["NO_COLOR"] = "1"
        return umgebung

    def _pruefe_vorschauadressen(self, ausgabe: str) -> None:
        """Sucht in der Ausgabe nach Adressen, die nicht die Produktivadresse sind.

        **Die Probe haengt an der Form der Adresse, nicht am Wortlaut des
        Werkzeugs.** Die Produktivadresse lautet ``<worker>.<konto>.workers.dev``,
        eine Vorschau ``<kennung>-<worker>.<konto>.workers.dev``: Das erste
        Namensglied unterscheidet die beiden. Eine Formulierungsaenderung im
        naechsten Werkzeug laesst diese Probe damit unberuehrt.
        """
        erwartet = self._ziel.worker.casefold()
        vorschauen = sorted(
            {
                treffer.group(1)
                for treffer in _WORKERS_DEV.finditer(ausgabe)
                if treffer.group(1).split(".")[0].casefold() != erwartet
            }
        )
        if not vorschauen:
            return
        raise DashboardPreviewUrlError(
            f"Der Anbieter hat Vorschau-Adressen vergeben ({', '.join(vorschauen)}). "
            "Aeltere Fassungen waeren darueber erreichbar und stehen wegen des "
            "stabilen Salts unter demselben Schluessel."
        )


def _lies_bericht(ausgabe: str, dauer: float) -> Hochladebericht:
    version = _VERSION.search(ausgabe)
    return Hochladebericht(
        dateien_gesamt=_zahl(_GELESEN, ausgabe),
        dateien_gesendet=_zahl(_GESENDET, ausgabe),
        version=version.group(1) if version is not None else None,
        dauer_sekunden=dauer,
    )


def _zahl(muster: re.Pattern[str], ausgabe: str) -> int | None:
    treffer = muster.search(ausgabe)
    return int(treffer.group(1)) if treffer is not None else None


def _letzte_zeilen(text: str, anzahl: int = 10) -> str:
    zeilen = [zeile.strip() for zeile in text.splitlines() if zeile.strip()]
    return " | ".join(zeilen[-anzahl:])
