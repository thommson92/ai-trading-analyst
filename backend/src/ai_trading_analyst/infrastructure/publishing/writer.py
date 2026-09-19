"""Der Datenbaum als Verzeichnis -- schreiben, was sich geaendert hat.

Der Snapshot kommt als Aufzaehlung von ``(Pfad, Bytes)`` herein und liegt
danach als Verzeichnis vor, das ein Anbieter ausliefern kann. Dazwischen
steht genau eine Entscheidung je Datei: **hat sich ihr Klartext geaendert?**

Warum das zaehlt: Der Vollexport ist gemessen rund 75 MB roh, und der
allergroesste Teil davon sind Kursreihen, die sich zwischen zwei Laeufen um
eine einzige Kerze unterscheiden -- oder um gar nichts, wenn eine Aktie
nicht mehr gehandelt wird. Wer jedes Mal alles neu schreibt, laedt jedes Mal
alles hoch. In Stufe 2 kommt hinzu, dass Chiffrat sich mit jeder Nonce
aendert: Ohne den Vergleich am **Klartext** saehe jede Datei bei jedem Lauf
neu aus, und "nur Neues hochladen" waere nicht zu haben.

Der Zustand dazu -- Hash je Pfad, dazu Salt und Baumkennung -- liegt
ausserhalb des veroeffentlichten Verzeichnisses. Er enthaelt in Stufe 2 die
Zuordnung von Pfad zu opakem Namen und gehoert damit zu dem, was der
Anbieter gerade **nicht** sehen soll.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from ai_trading_analyst.observability.logging_setup import get_logger

from .crypto import Verschluesselung

_logger = get_logger(__name__)

ZUSTAND_FORMAT = 1

_KOPF_PFAD = "data/manifest.head.json"
"""Der Klartextkopf gehoert zum Baum, stammt aber nicht aus dem Snapshot --
er wird beim Schreiben erzeugt und darf deshalb nicht als verwaist gelten."""


@dataclass(frozen=True, slots=True)
class Dateizustand:
    """Was ueber eine Datei des letzten Standes bekannt ist."""

    hash: str
    """SHA-256 des **Klartexts**, hexadezimal."""
    ziel: str
    """Der Name im Verzeichnis -- in Stufe 1 der Pfad selbst, in Stufe 2 opak."""
    fassung: str | None = None
    """Unter welcher Fassung der Inhalt entstand (ADR 0068).

    Nur fuer die Pfade gesetzt, die als unveraenderlich gelten. ``None``
    heisst: unbekannt -- entweder ein Pfad, der ohnehin jedes Mal neu
    entsteht, oder ein Zustand aus der Zeit vor ADR 0068. Beide Male wird
    gerechnet, und das ist die sichere Richtung.
    """


@dataclass(frozen=True, slots=True)
class Exporteintrag:
    """Eine Datei, wie der Schreiber sie entgegennimmt.

    ``inhalt is None`` heisst **unveraendert**: Der Erzeuger hat entschieden,
    dass sich an dieser Datei nichts geaendert haben kann, und sie deshalb
    gar nicht erst gebaut (ADR 0068). Der Schreiber uebernimmt dann
    Pruefsumme und Zielnamen aus dem bekannten Stand.

    Die Infrastruktur kennt die Praesentationsschicht nicht (Doc 10,
    Paragraph 9) -- deshalb dieser eigene Typ und nicht ``Exportdatei``.
    """

    pfad: str
    inhalt: bytes | None
    fassung: str | None = None


@dataclass
class Exportzustand:
    """Was zwischen zwei Exporten erhalten bleiben muss.

    ``baum_id`` und ``salt`` sind bewusst **stabil** ueber viele Exporte
    hinweg: Aus ihnen leiten sich Schluessel und damit die opaken Dateinamen
    ab. Ein neues Salt je Lauf ergaebe bei jedem Lauf einen vollstaendig
    neuen Baum -- jede Datei neu, jede Datei hochzuladen.

    **Auch ein Wechsel der Passphrase aendert beide nicht.** Er aendert den
    abgeleiteten Schluessel, und damit aendern sich alle Dateinamen und alle
    Inhalte; die alten Dateien gelten danach als verwaist und verschwinden.
    Salt und Baumkennung bleiben aber dieselben, und die Zusatzdaten
    unterscheiden alt und neu deshalb nicht -- das leistet der Schluessel.
    Ein Salt, das ueber zwei Passphrasen desselben Nutzers steht, ist
    unbedenklich; was es nicht ist, ist ein Ersatz fuer den Schluesselwechsel.

    Kein Geheimnis in dieser Datei: Salt und Baumkennung sind oeffentliche
    Parameter, sie stehen ohnehin im Klartextkopf. Die Zuordnung Pfad ->
    opaker Name ist es demgegenueber schon -- sie bleibt hier und geht nicht
    mit hinaus.
    """

    baum_id: str
    salt: bytes
    iterationen: int
    dateien: dict[str, Dateizustand] = field(default_factory=dict)

    @classmethod
    def lade(cls, pfad: Path) -> Exportzustand | None:
        """Der letzte Stand, oder ``None`` beim ersten Lauf.

        Ein unlesbarer Zustand ist ausdruecklich **kein** Grund abzubrechen:
        Er kostet die Ersparnis, nicht den Export. Wer ihn nicht lesen kann,
        schreibt alles neu -- und das ist immer richtig, nur langsamer.
        """
        if not pfad.is_file():
            return None
        try:
            roh = json.loads(pfad.read_text(encoding="utf-8"))
            return cls(
                baum_id=str(roh["tree_id"]),
                salt=bytes.fromhex(str(roh["salt"])),
                iterationen=int(roh["iterations"]),
                dateien={
                    str(p): Dateizustand(
                        hash=str(w["hash"]),
                        ziel=str(w["ziel"]),
                        # Ein Zustand aus der Zeit vor ADR 0068 kennt das
                        # Feld nicht. Der erste Export danach rechnet dann
                        # einmal alles neu und traegt es nach.
                        fassung=None if w.get("fassung") is None else str(w["fassung"]),
                    )
                    for p, w in dict(roh.get("files", {})).items()
                },
            )
        except (OSError, ValueError, KeyError, TypeError) as fehler:
            _logger.warning(
                "Exportzustand %s ist nicht lesbar (%s) -- der Baum wird vollstaendig "
                "neu geschrieben.",
                pfad,
                fehler,
            )
            return None

    def speichere(self, pfad: Path) -> None:
        pfad.parent.mkdir(parents=True, exist_ok=True)
        inhalt = json.dumps(
            {
                "format": ZUSTAND_FORMAT,
                "tree_id": self.baum_id,
                "salt": self.salt.hex(),
                "iterations": self.iterationen,
                "files": {
                    p: (
                        {"hash": w.hash, "ziel": w.ziel}
                        if w.fassung is None
                        else {"hash": w.hash, "ziel": w.ziel, "fassung": w.fassung}
                    )
                    for p, w in sorted(self.dateien.items())
                },
            },
            ensure_ascii=False,
            indent=1,
        )
        _atomar_schreiben(pfad, inhalt.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class Schreibbericht:
    """Was ein Export bewirkt hat -- fuer das Protokoll und die Abnahme."""

    dateien: int
    geschrieben: int
    unveraendert: int
    entfernt: int
    bytes_geschrieben: int

    def als_text(self) -> str:
        return (
            f"{self.dateien} Dateien, davon {self.geschrieben} geschrieben "
            f"({self.bytes_geschrieben} Byte), {self.unveraendert} unveraendert, "
            f"{self.entfernt} entfernt"
        )


def _atomar_schreiben(ziel: Path, inhalt: bytes) -> None:
    """Erst daneben, dann an die Stelle.

    Ein abgebrochener Schreibvorgang hinterlaesst sonst eine halbe Datei, und
    eine halbe verschluesselte Datei ist von einer manipulierten nicht zu
    unterscheiden -- der Browser verwuerfe sie mit derselben Meldung.
    """
    ziel.parent.mkdir(parents=True, exist_ok=True)
    vorlaeufig = ziel.with_name(ziel.name + ".neu")
    vorlaeufig.write_bytes(inhalt)
    os.replace(vorlaeufig, ziel)


class Verzeichnisschreiber:
    """Schreibt den Snapshot in ein Verzeichnis, wahlweise verschluesselt.

    Dieselbe Klasse fuer beide Stufen: Stufe 1 uebergibt keine
    ``Verschluesselung``, Stufe 2 eine. Das ist die Naht, die der Spike-Bericht
    in Abschnitt 8.1 verlangt -- eine Schreibfunktion, die in Stufe 2 die
    Verschluesselung uebernimmt, und sonst nichts Neues.
    """

    def __init__(
        self,
        wurzel: Path,
        *,
        verschluesselung: Verschluesselung | None = None,
        kopf: bytes | None = None,
    ) -> None:
        if (verschluesselung is None) != (kopf is None):
            raise ValueError(
                "Verschluesselung und Klartextkopf gehoeren zusammen: entweder beide "
                "oder keines von beiden."
            )
        self._wurzel = wurzel
        self._verschluesselung = verschluesselung
        self._kopf = kopf

    def schreibe(
        self, dateien: Iterable[Exporteintrag], zustand: Exportzustand
    ) -> Schreibbericht:
        """Schreibt den Baum und fuehrt ``zustand`` nach.

        ``zustand`` wird dabei veraendert und nicht kopiert: Der Aufrufer
        speichert ihn danach. Zwischenstaende zu speichern brachte nichts --
        ein Export, der auf halbem Weg abbricht, hat noch kein Manifest, und
        ohne Manifest zeigt die Oberflaeche den alten Stand.
        """
        vorher = dict(zustand.dateien)
        zustand.dateien.clear()

        geschrieben = unveraendert = anzahl = 0
        bytes_geschrieben = 0
        vorhandene: set[Path] = set()

        for eintrag in dateien:
            anzahl += 1
            pfad = eintrag.pfad
            alt = vorher.get(pfad)

            if eintrag.inhalt is None:
                # **Nicht gerechnet, also auch nichts zu pruefen.** Dass der
                # Pfad bekannt ist und seine Zieldatei liegt, hat der
                # Erzeuger entschieden -- er bekam genau die Pfade, fuer die
                # beides gilt. Fehlt der Eintrag hier trotzdem, ist das ein
                # Programmfehler und kein Betriebszustand.
                if alt is None:
                    raise ValueError(
                        f"'{pfad}' wurde als unveraendert gemeldet, steht aber nicht "
                        "im bekannten Stand."
                    )
                zustand.dateien[pfad] = alt
                vorhandene.add(self._wurzel / alt.ziel)
                unveraendert += 1
                continue

            klartext = eintrag.inhalt
            digest = hashlib.sha256(klartext).hexdigest()
            ziel_name = self._zielname(pfad)
            ziel = self._wurzel / ziel_name
            vorhandene.add(ziel)
            zustand.dateien[pfad] = Dateizustand(
                hash=digest, ziel=ziel_name, fassung=eintrag.fassung
            )

            if alt is not None and alt.hash == digest and alt.ziel == ziel_name and ziel.is_file():
                unveraendert += 1
                continue

            inhalt = (
                klartext
                if self._verschluesselung is None
                else self._verschluesselung.verschluessele(pfad, klartext)
            )
            _atomar_schreiben(ziel, inhalt)
            geschrieben += 1
            bytes_geschrieben += len(inhalt)

        if self._kopf is not None:
            ziel = self._wurzel / _KOPF_PFAD
            vorhandene.add(ziel)
            _atomar_schreiben(ziel, self._kopf)

        entfernt = self._entferne_verwaiste(vorhandene)
        bericht = Schreibbericht(
            dateien=anzahl,
            geschrieben=geschrieben,
            unveraendert=unveraendert,
            entfernt=entfernt,
            bytes_geschrieben=bytes_geschrieben,
        )
        _logger.info("Datenbaum geschrieben: %s", bericht.als_text())
        return bericht

    def _zielname(self, pfad: str) -> str:
        if self._verschluesselung is None:
            return pfad
        return f"data/{self._verschluesselung.dateiname(pfad)}"

    def _entferne_verwaiste(self, vorhandene: set[Path]) -> int:
        """Alles unter ``data/``, was nicht mehr zum Snapshot gehoert.

        Ohne diesen Schritt bliebe jede je exportierte Datei liegen: der
        Bericht einer Aktie, die aus der Watchliste fiel, der Chart unter dem
        alten opaken Namen nach einem Passphrase-Wechsel. Beim Anbieter waere
        das genau die Datenhalde, die der Spike-Bericht als T20 fuehrt -- nur
        eben schon auf dem Server angelegt.
        """
        datenwurzel = self._wurzel / "data"
        if not datenwurzel.is_dir():
            return 0
        entfernt = 0
        for gefunden in sorted(datenwurzel.rglob("*")):
            if gefunden.is_file() and gefunden not in vorhandene:
                gefunden.unlink()
                entfernt += 1
        for verzeichnis in sorted(datenwurzel.rglob("*"), reverse=True):
            if verzeichnis.is_dir() and not any(verzeichnis.iterdir()):
                verzeichnis.rmdir()
        return entfernt
