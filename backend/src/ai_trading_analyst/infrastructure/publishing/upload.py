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

**Alles hier wirft ``DashboardUploadError``, nie einen Abbruch des Laufs.**
Der Baum ist zu diesem Zeitpunkt geschrieben; ein Werkzeug, das fehlt, und
eine Leitung, die schweigt, duerfen einen erledigten Tageslauf nicht
nachtraeglich scheitern lassen (ADR 0060, Punkt 2).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
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
    "TMPDIR",
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
braucht den Suchpfad und unter Windows die Handvoll Systemvariablen darunter.

**Bewusst eng, nicht vollstaendig.** ``NODE_OPTIONS`` fehlt, weil darueber
Code in den Prozess kaeme; ``NODE_EXTRA_CA_CERTS`` und die Proxy-Variablen
fehlen ebenfalls. In einem Netz mit HTTP-Proxy oder aufgebrochenem TLS
muesste diese Liste erweitert werden -- der Fehler saehe dann nach einem
Netzproblem aus und waere eines.
"""

_WORKERS_DEV = re.compile(r"https?://([A-Za-z0-9][A-Za-z0-9_.-]*\.workers\.dev)")
_GELESEN = re.compile(r"Read (\d+) files? from the assets directory", re.IGNORECASE)
_GESENDET = re.compile(r"Uploaded (\d+) files?", re.IGNORECASE)
_VERSION = re.compile(r"Current Version ID:\s*([0-9A-Za-z-]{8,})")


def wrangler_befehl(paket: Path) -> list[str]:
    """Wie das Upload-Werkzeug gestartet wird.

    **Ueber den Paket-Einstieg aus ``main``, nicht ueber den Starter in
    ``bin``.** Der Starter ist nur ein Vorspann: Er prueft die Node-Version
    und startet dann `wrangler` als **eigenen Prozess weiter**, der unsere
    Leitungen erbt. Eine Zeitgrenze liefe damit ins Leere -- abgeschossen
    wuerde der Vorspann, weitergeladen haette der Enkel, und das Einsammeln
    der Ausgabe wartete unter Windows ohne Zeitgrenze auf Leitungen, die
    niemand mehr schliesst. Gemessen am 2026-09-18.

    Der Preis ist die Node-Version, die der Starter sonst prueft: `wrangler`
    verlangt mindestens 22. Dieselbe Fassung verlangt Doc 14, Stufe J,
    Schritt 1, und dieselbe baut die CI -- geprueft wird sie dort, nicht hier.

    Raises:
        DashboardUploadError: wenn das Werkzeug fehlt oder anders aussieht
            als erwartet. **Kein Abbruch des Laufs:** Das Werkzeug fehlt in
            aller Regel, weil nach einem ``git pull`` das ``npm ci`` im
            Frontend ausblieb -- der Baum soll dann geschrieben werden und
            nur nicht hinausgehen.
    """
    beschreibung = paket / "package.json"
    try:
        inhalt = json.loads(beschreibung.read_text(encoding="utf-8"))
    except (OSError, ValueError) as fehler:
        raise DashboardUploadError(
            f"Das Upload-Werkzeug ist nicht lesbar ({beschreibung}): {fehler}. "
            "Auf dem Server gehoert nach jedem 'git pull' ein 'npm ci' im "
            "Frontend dazu (Doc 14, Stufe K, Schritt 0)."
        ) from fehler

    einstieg = inhalt.get("main") if isinstance(inhalt, dict) else None
    if not isinstance(einstieg, str):
        raise DashboardUploadError(
            f"Das Upload-Werkzeug nennt keinen Einstieg ({beschreibung}, Feld 'main')."
        )
    pfad = (paket / einstieg).resolve()
    if not pfad.is_file():
        raise DashboardUploadError(
            f"Der Einstieg des Upload-Werkzeugs fehlt ({pfad}). Ist 'npm ci' im "
            "Frontend durchgelaufen?"
        )
    return ["node", str(pfad)]


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
    befehl: Callable[[], Sequence[str]]
    """Wie das Werkzeug gestartet wird -- **aufgeloest erst beim Upload**.

    Nicht schon beim Bau des Exportschritts: Der laeuft im Tageslauf vor dem
    Backfill, und ein Fehler dort brechte den ganzen Lauf ab. Ein fehlendes
    Upload-Werkzeug soll aber nur den Upload kosten.
    """
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

    **Die Ausgabe geht in Dateien und nicht in Leitungen, und das ist der
    Punkt.** Mit Leitungen lauert unter Windows eine Falle, die auf dem
    Windows-Lauf der CI am 2026-09-18 gemessen wurde: Startet der
    Unterprozess seinerseits ein Kind -- und `wrangler` tut das, wenn man es
    ueber seinen Starter aufruft --, erbt dieses Kind die Leitungen. Nach
    einer Zeitueberschreitung stirbt nur der Unterprozess; die Lesefaeden
    haengen weiter am offenen Schreibende, und schon das **Schliessen** der
    Leitung wartet auf sie. Gemessen: 30 Sekunden statt einer, und mit einem
    langlebigen Enkel beliebig lange -- still, im naechtlichen Lauf,
    innerhalb der Exportsperre.

    Dateien haben dieses Problem nicht: Es gibt keine Lesefaeden, nichts zu
    schliessen, und was bis zum Abschuss geschrieben wurde, ist lesbar --
    die Fehlersuche gewinnt sogar dazu.

    **Gelesen wird ausdruecklich als UTF-8.** Ohne Angabe naehme Python die
    Codierung des Systems -- auf einem deutschen Windows ``cp1252``, und
    daran zerbricht schon das erste Emoji, das `wrangler` ausgibt. Der Upload
    waere dann gelungen und der Schritt trotzdem gescheitert.
    ``errors="replace"``, weil eine unlesbare Protokollzeile kein Grund ist,
    einen gelungenen Upload zu verwerfen.
    """
    with (
        tempfile.TemporaryFile() as ausgabe,
        tempfile.TemporaryFile() as fehlerausgabe,
    ):
        with subprocess.Popen(
            list(befehl),
            cwd=arbeitsverzeichnis,
            env=umgebung,
            stdin=subprocess.DEVNULL,
            stdout=ausgabe,
            stderr=fehlerausgabe,
        ) as prozess:
            try:
                prozess.wait(timeout=zeitgrenze)
            except subprocess.TimeoutExpired:
                prozess.kill()
                # Kehrt zurueck, auch wenn ein Enkel weiterlebt: Gewartet
                # wird auf diesen Prozess, nicht auf seine Nachkommen.
                prozess.wait()
                raise
        ausgabe.seek(0)
        fehlerausgabe.seek(0)
        return subprocess.CompletedProcess(
            list(befehl),
            prozess.returncode,
            ausgabe.read().decode("utf-8", errors="replace"),
            fehlerausgabe.read().decode("utf-8", errors="replace"),
        )


class WranglerHochlader:
    """Setzt ``Hochlader`` mit dem Werkzeug des Anbieters um."""

    def __init__(self, ziel: Hochladeziel, *, starter: Prozessstarter | None = None) -> None:
        self._ziel = ziel
        self._starter = starter if starter is not None else _starte_prozess

    def lade_hoch(self) -> Hochladebericht:
        self._pruefe_baum()
        self._pruefe_arbeitsverzeichnis()
        befehl = [*self._ziel.befehl(), "deploy", "--config", str(self.schreibe_konfiguration())]

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
        try:
            self._ziel.arbeitsverzeichnis.mkdir(parents=True, exist_ok=True)
            pfad = self._ziel.arbeitsverzeichnis / KONFIGURATIONSNAME
            verzeichnis = os.path.relpath(self._ziel.baum, self._ziel.arbeitsverzeichnis)
            pfad.write_text(
                "{\n"
                "  // Erzeugt vom Exportschritt, bei jedem Upload neu (ADR 0060, E4).\n"
                "  // Aenderungen von Hand gehen beim naechsten Lauf verloren.\n"
                f'  "name": {json.dumps(self._ziel.worker)},\n'
                f'  "compatibility_date": "{KOMPATIBILITAETSDATUM}",\n'
                '  "workers_dev": true,\n'
                "  // Ausdruecklich, und das ist die Falle dieser Datei: preview_urls\n"
                "  // folgt ohne Angabe dem Wert von workers_dev, also true. Ein Upload\n"
                "  // ohne diese Zeile schaltete abgeschaltete Vorschau-Adressen\n"
                "  // stillschweigend wieder ein -- und weil Salt und Baumkennung ueber\n"
                "  // alle Exporte stabil sind, stuenden damit alle je hochgeladenen\n"
                "  // Fassungen wieder unter demselben Schluessel erreichbar.\n"
                '  "preview_urls": false,\n'
                f'  "assets": {{ "directory": '
                f"{json.dumps(verzeichnis.replace(os.sep, '/'))} }}\n"
                "}\n",
                encoding="utf-8",
            )
        except OSError as fehler:
            raise DashboardUploadError(
                f"Die Konfiguration fuer den Upload liess sich nicht schreiben: {fehler}. "
                "Der Datenbaum liegt geschrieben auf dem Server."
            ) from fehler
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

    def _pruefe_arbeitsverzeichnis(self) -> None:
        """Keine ``.env`` neben der Konfigurationsdatei.

        `wrangler` liest eine ``.env`` neben seiner Konfiguration ein. Laege
        das Arbeitsverzeichnis versehentlich in der Projektwurzel, bekaeme
        das fremde Werkzeug damit **jedes** ``ATA_``-Geheimnis in die Hand --
        an der Erlaubnisliste in ``_umgebung`` vorbei, die genau das
        verhindern soll. Die Zusage dieses Moduls haengt also nicht nur an
        der Liste, sondern auch daran, wo gearbeitet wird.
        """
        env = self._ziel.arbeitsverzeichnis / ".env"
        if env.exists():
            raise DashboardUploadError(
                f"Neben der Upload-Konfiguration liegt eine .env ({env}). Das Werkzeug "
                "liest sie ein, und darin stehen die ATA_-Geheimnisse. "
                "dashboard_export.upload_directory gehoert an einen eigenen Ort."
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

        **Sie ist trotzdem nur die zweite Sperre.** Nennt das Werkzeug eine
        vergebene Vorschau-Adresse gar nicht, sieht sie nichts. Die tragende
        Sperre ist ``"preview_urls": false`` in der Konfiguration, die dieses
        Modul selbst schreibt.
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
