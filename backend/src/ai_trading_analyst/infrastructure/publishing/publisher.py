"""Der Ausgang fuer den Snapshot des Dashboards (ADR 0060, Entscheidung 2).

Der Server sendet; es gibt keinen Weg zurueck. Diese Klasse setzt den Port
``DashboardPublisher`` um und tut dabei genau drei Dinge: den Datenbaum
holen, ihn schreiben -- in Stufe 2 verschluesselt -- und den Zustand
fortschreiben, aus dem der naechste Lauf weiss, was sich geaendert hat.

**Der Datenbaum kommt als Aufzaehlung herein und nicht als Aufruf in die
Praesentationsschicht.** Die Infrastruktur darf sie nicht kennen (Doc 10,
Paragraph 9); verdrahtet wird beides im Composition Root. Der Preis ist eine
Zeile dort, der Gewinn ist eine Schicht, die von Berichten, Charts und
Antwortschemata nichts weiss.

**Seit dem Upload sind es vier Dinge**, und das vierte ist ausgelagert: Wer
den Baum entgegennimmt, weiss diese Klasse nicht. Sie kennt nur den Port
``Hochlader``; ohne ihn endet der Weg im Verzeichnis, und das bleibt die
Rueckfallstufe (``target: directory``).
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from ai_trading_analyst.domain.scheduling import (
    DashboardPublisherError,
    DashboardUploadError,
)
from ai_trading_analyst.observability.logging_setup import get_logger

from .crypto import (
    KryptoKonfigurationError,
    Verschluesselung,
    kopf,
    leite_schluessel_ab,
)
from .frontend_build import Baubericht
from .upload import Hochladebericht, Hochlader
from .writer import Exportzustand, Schreibbericht, Verzeichnisschreiber

_logger = get_logger(__name__)

SALT_LAENGE = 32

SPERRE_VERFAELLT = timedelta(hours=1)
"""Ab wann eine liegengebliebene Sperre uebergangen wird.

Ein Export dauert Minuten, nicht Stunden. Eine aeltere Sperre stammt
deshalb nicht von einem laufenden Vorgang, sondern von einem abgestuerzten
-- und eine Sperre, die niemand mehr aufhebt, waere schlimmer als keine:
Sie hielte den Tageslauf dauerhaft vom Export ab, und zwar still.
"""
MANIFEST_PFAD = "data/manifest.json"
FORMAT_VERSION = 1
"""Beide muessen mit ``presentation.export`` uebereinstimmen.

Der Klartextkopf nennt den (in Stufe 2 opaken) Namen des Manifests, damit
der Browser weiss, womit er anfangen soll. Dafuer braucht diese Schicht den
kanonischen Pfad und die Formatversion -- und darf beides nicht aus der
Praesentationsschicht holen. Ein Test haelt die Seiten zusammen.
"""


@dataclass(frozen=True, slots=True)
class Exportziel:
    """Wohin der Datenbaum geschrieben wird und wie er geschuetzt ist."""

    wurzel: Path
    zustandsdatei: Path
    passphrase: str | None
    """``None`` heisst Stufe 1: Klartext hinter der Anmeldung an der Kante."""
    iterationen: int


@dataclass(frozen=True, slots=True)
class Exportbericht:
    """Was ein Export bewirkt hat -- geschrieben und, wenn eingeschaltet, gesendet.

    ``hochladen`` ist ``None``, wenn der Baum nur geschrieben wurde
    (``target: directory``). Es ist **nie** ``None``, weil ein Upload
    fehlschlug: Dann gibt es keinen Bericht, sondern einen Fehler.
    """

    schreiben: Schreibbericht
    hochladen: Hochladebericht | None

    oberflaeche: Baubericht | None = None
    """Gesetzt, wenn ``publish --full`` die Oberflaeche mitgebaut hat (ADR 0065)."""

    def als_text(self) -> str:
        teile = [] if self.oberflaeche is None else [self.oberflaeche.als_text()]
        teile.append(self.schreiben.als_text())
        if self.hochladen is not None:
            teile.append(self.hochladen.als_text())
        return "; ".join(teile)


class SnapshotPublisher:
    """Setzt ``DashboardPublisher`` um."""

    def __init__(
        self,
        *,
        snapshot: Callable[[], Iterable[tuple[str, bytes]]],
        ziel: Exportziel,
        hochlader: Hochlader | None = None,
    ) -> None:
        self._snapshot = snapshot
        self._ziel = ziel
        self._hochlader = hochlader

    @contextmanager
    def _sperre(self) -> Iterator[None]:
        """Verhindert zwei gleichzeitige Exporte in dasselbe Verzeichnis.

        Der Tageslauf schreibt am Ende jedes Laufs, und die Kommandozeile
        kann jederzeit dazwischenkommen -- auf diesem Server ist genau das
        schon vorgekommen. Zwei Laeufe zugleich loeschen sich zwar nichts
        weg (die Namen sind pfadstabil), schreiben aber zwei verschiedene
        Manifeste: Der Browser folgt dem, das gewonnen hat, und faende bei
        jeder Datei des anderen Laufs eine abweichende Pruefsumme. Das heilt
        beim naechsten Lauf -- sieht dazwischen aber genau wie der Angriff
        aus, gegen den die Pruefsumme steht. Ein Fehlalarm an dieser Stelle
        ist teurer als eine Sperre.
        """
        pfad = self._ziel.zustandsdatei.with_name(self._ziel.zustandsdatei.name + ".lock")
        pfad.parent.mkdir(parents=True, exist_ok=True)
        try:
            griff = os.open(pfad, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if not self._sperre_ist_verfallen(pfad):
                raise DashboardPublisherError(
                    f"Ein anderer Export schreibt gerade nach {self._ziel.wurzel}."
                ) from None
            _logger.warning(
                "Liegengebliebene Sperre %s wird uebergangen -- aelter als %s.",
                pfad,
                SPERRE_VERFAELLT,
            )
            pfad.unlink(missing_ok=True)
            griff = os.open(pfad, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(griff, f"{os.getpid()} {datetime.now(UTC).isoformat()}\n".encode())
            os.close(griff)
            yield
        finally:
            pfad.unlink(missing_ok=True)

    @staticmethod
    def _sperre_ist_verfallen(pfad: Path) -> bool:
        try:
            alter = datetime.now(UTC) - datetime.fromtimestamp(pfad.stat().st_mtime, tz=UTC)
        except OSError:
            # Gerade verschwunden -- dann ist sie ohnehin keine mehr.
            return True
        return alter > SPERRE_VERFAELLT

    def publish(self) -> None:
        """Setzt den Port ``DashboardPublisher`` um.

        Ohne Rueckgabewert: Der Tageslauf hat mit dem Bericht nichts vor --
        er steht im Protokoll, und der Lauf haengt nicht davon ab. Wer ihn
        braucht (die Kommandozeile), ruft ``schreibe_baum`` auf.
        """
        self.schreibe_baum()

    def schreibe_baum(
        self, *, voll: bool = False, oberflaeche: Callable[[], Baubericht] | None = None
    ) -> Exportbericht:
        """Schreibt den Snapshot und sendet ihn, wenn ein Hochlader da ist.

        ``oberflaeche`` baut vorher die Oberflaeche in das Verzeichnis
        (ADR 0065) -- **unter derselben Sperre** wie Schreiben und Senden:
        Ein Tageslauf, der waehrend des Baus exportierte, laese ein halbes
        Verzeichnis. Scheitert der Bau, wird nichts geschrieben.

        ``voll`` verwirft den bekannten Stand und schreibt jede Datei neu.
        Das ist der Weg nach einem Anbieterwechsel und nach jedem Zweifel,
        ob draussen wirklich steht, was hier liegt -- der Zustand behauptet
        etwas ueber ein Verzeichnis, das er nicht selbst kontrolliert.

        **Gesendet wird unter derselben Sperre, unter der geschrieben wird.**
        Zwei Uploads desselben Workers zugleich gaebe es sonst genauso wie
        zwei Schreibvorgaenge, und die Sperre verfaellt erst nach einer
        Stunde -- Schreiben und Senden passen zusammen hinein.

        Raises:
            DashboardPublisherError: wenn der Baum nicht geschrieben werden
                konnte. Der Aufrufer im Tageslauf isoliert das; das Ergebnis
                des Laufs steht zu diesem Zeitpunkt bereits in der Datenbank.
            DashboardUploadError: wenn er geschrieben wurde, aber nicht
                hinausging.
            DashboardPreviewUrlError: wenn er hinausging, der Anbieter aber
                Vorschau-Adressen vergeben hat.
        """
        begonnen = time.monotonic()
        _logger.info(
            "Dashboard-Export beginnt: Ziel %s, %s, %s.",
            self._ziel.wurzel,
            "verschluesselt" if self._ziel.passphrase is not None else "Klartext",
            "Vollexport" if voll else "nur Aenderungen",
        )
        with self._sperre():
            gebaut = None if oberflaeche is None else oberflaeche()
            try:
                zustand = self._zustand()
                if voll:
                    zustand.dateien.clear()
                schreiber = self._schreiber(zustand)
                geschrieben = schreiber.schreibe(self._snapshot(), zustand)
                zustand.speichere(self._ziel.zustandsdatei)
            except KryptoKonfigurationError as fehler:
                raise DashboardPublisherError(
                    f"Verschluesselung nicht einsatzbereit: {fehler}"
                ) from fehler
            except OSError as fehler:
                raise DashboardPublisherError(f"Datenbaum nicht schreibbar: {fehler}") from fehler

            # Ab hier steht der Baum. Alles, was jetzt noch schiefgeht, ist
            # ein Upload-Fehler und keiner beim Schreiben -- die beiden Lagen
            # verlangen verschiedene Meldungen, weil im einen Fall der Server
            # dem Anbieter voraus ist und im anderen nicht.
            hochgeladen = self._sende(geschrieben)

        bericht = Exportbericht(
            schreiben=geschrieben, hochladen=hochgeladen, oberflaeche=gebaut
        )
        _logger.info(
            "Dashboard-Export fertig nach %.1f s: %s",
            time.monotonic() - begonnen,
            bericht.als_text(),
        )
        return bericht

    def _sende(self, geschrieben: Schreibbericht) -> Hochladebericht | None:
        """Der Baum geht hinaus -- oder es gibt einen Upload-Fehler.

        **Breit gefangen, und das ist hier kein stiller Rueckfall.** Hinter
        diesem Aufruf steht ein fremder Prozess, also eine echte
        Systemgrenze. Entscheidend ist aber ein anderer Punkt: Ab hier ist
        der Baum **immer** geschrieben. Liesse man eine unerwartete Ausnahme
        durch, faele sie im Tageslauf in den allgemeinen Zweig und meldete
        "Dashboard nicht aktualisiert" -- also genau die Lage, die nicht
        vorliegt. Die Unterscheidung "der Server ist voraus" ist die Zusage,
        die dieser Schritt gibt; sie darf nicht daran haengen, welche
        Ausnahmeart ein Adapter gerade wirft.
        """
        if self._hochlader is None:
            return None
        try:
            return self._hochlader.lade_hoch()
        except DashboardPublisherError:
            # Schon eingeordnet -- unveraendert weiterreichen.
            raise
        except Exception as fehler:
            raise DashboardUploadError(
                f"Der Upload ist unerwartet gescheitert: {fehler!r}. Der Datenbaum "
                f"({geschrieben.dateien} Dateien) liegt geschrieben auf dem Server."
            ) from fehler

    def _zustand(self) -> Exportzustand:
        """Der letzte Stand -- oder ein frischer Baum.

        Salt und Baumkennung entstehen genau einmal und bleiben danach
        stehen. Wuerden sie je Lauf neu gezogen, aenderte sich der abgeleitete
        Schluessel und mit ihm jeder opake Dateiname: Jeder Lauf ergaebe einen
        vollstaendig neuen Baum, und "nur Neues hochladen" gaebe es nicht.
        """
        bekannt = Exportzustand.lade(self._ziel.zustandsdatei)
        if bekannt is not None:
            bekannt.iterationen = self._ziel.iterationen
            return bekannt
        _logger.info("Kein Exportzustand gefunden -- der Datenbaum entsteht neu.")
        return Exportzustand(
            baum_id=str(uuid4()),
            salt=os.urandom(SALT_LAENGE),
            iterationen=self._ziel.iterationen,
        )

    def _schreiber(self, zustand: Exportzustand) -> Verzeichnisschreiber:
        if self._ziel.passphrase is None:
            # Stufe 1. Kein stiller Ersatz: Wer ohne Passphrase exportiert,
            # legt Klartext ab, und das gehoert ins Protokoll.
            _logger.warning(
                "Datenbaum wird im Klartext geschrieben (Stufe 1) -- ohne Passphrase "
                "sieht der Anbieter Berichte, Kurse und Symbole."
            )
            return Verzeichnisschreiber(self._ziel.wurzel)

        schluessel = leite_schluessel_ab(
            self._ziel.passphrase, zustand.salt, zustand.iterationen
        )
        verschluesselung = Verschluesselung(
            schluessel, baum_id=zustand.baum_id, format_version=FORMAT_VERSION
        )
        return Verzeichnisschreiber(
            self._ziel.wurzel,
            verschluesselung=verschluesselung,
            kopf=kopf(
                salt=zustand.salt,
                iterationen=zustand.iterationen,
                format_version=FORMAT_VERSION,
                baum_id=zustand.baum_id,
                manifest=verschluesselung.dateiname(MANIFEST_PFAD),
            ),
        )
