"""Der Analysebericht als lesbarer Text (Doc 10, Paragraph 6.12).

Rendert **das gespeicherte Dokument**, nicht die Domain-Objekte. Damit zeigt
die Konsole genau das, was in der Datenbank steht -- und nicht eine zweite
Zusammenstellung, die davon abweichen koennte.

Solange die KI-Haelfte fehlt, ist das eine geordnete Aufstellung und kein
Fliesstext (ADR 0039, Entscheidung 2).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_EINRUECKUNG = "  "


def render_report(document: Mapping[str, Any], *, symbol: str) -> str:
    """Der vollstaendige Bericht einer Aktie."""
    zeilen: list[str] = [
        f"=== {symbol} ===",
        f"Bericht {document['berichtsschema_version']}, "
        f"Anwendung {document['anwendungsversion']}, "
        f"Signalregel {document['signalregel_version']}",
        f"erstellt {document['erstellt_am']}",
        "",
    ]
    abschnitte = document["abschnitte"]
    for name in sorted(abschnitte, key=lambda n: int(abschnitte[n]["nummer"])):
        zeilen.extend(_abschnitt(name, abschnitte[name]))
    return "\n".join(zeilen)


def render_run(dokumente: Sequence[tuple[str, Mapping[str, Any]]]) -> str:
    """Alle Berichte eines Laufs, durch Leerzeilen getrennt."""
    if not dokumente:
        return "Keine Berichte zu diesem Lauf -- er hatte keine Kandidaten."
    return "\n\n".join(render_report(dok, symbol=symbol) for symbol, dok in dokumente)


def _abschnitt(name: str, abschnitt: Mapping[str, Any]) -> list[str]:
    kopf = f"{abschnitt['nummer']:>2}. {name}"
    if not abschnitt["verfuegbar"]:
        kopf += "  -- NICHT VERFUEGBAR"
    zeilen = [kopf]
    for vorbehalt in abschnitt["vorbehalte"]:
        zeilen.append(f"{_EINRUECKUNG}[{vorbehalt['art']}] {vorbehalt['grund']}")
    if abschnitt["inhalt"] is not None:
        zeilen.extend(_wert(abschnitt["inhalt"], tiefe=1))
    zeilen.append("")
    return zeilen


def _wert(wert: Any, *, tiefe: int) -> list[str]:
    """Gibt beliebig verschachtelte Daten zeilenweise aus.

    Bewusst allgemein wie die Dokumenterzeugung selbst: Eine handgeschriebene
    Ausgabe je Abschnitt veraltete beim naechsten neuen Feld still, und der
    Bericht zeigte dann weniger, als er enthaelt.
    """
    einzug = _EINRUECKUNG * tiefe
    if isinstance(wert, Mapping):
        zeilen: list[str] = []
        # Alphabetisch: PostgreSQL gibt JSONB-Schluessel in eigener Ordnung
        # zurueck (nach Laenge, dann bytewise). Die Ausgabe saehe sonst je
        # nach Feldnamen willkuerlich sortiert aus und aenderte sich, sobald
        # ein Feld umbenannt wird. Alphabetisch ist nicht die fachliche
        # Reihenfolge, aber eine, auf die man sich verlassen kann.
        for schluessel in sorted(wert):
            inhalt = wert[schluessel]
            if inhalt is None or inhalt == [] or inhalt == {}:
                continue
            if isinstance(inhalt, Mapping | list):
                zeilen.append(f"{einzug}{schluessel}:")
                zeilen.extend(_wert(inhalt, tiefe=tiefe + 1))
            else:
                zeilen.append(f"{einzug}{schluessel}: {inhalt}")
        return zeilen
    if isinstance(wert, list):
        zeilen = []
        for eintrag in wert:
            if isinstance(eintrag, Mapping | list):
                zeilen.append(f"{einzug}-")
                zeilen.extend(_wert(eintrag, tiefe=tiefe + 1))
            else:
                zeilen.append(f"{einzug}- {eintrag}")
        return zeilen
    return [f"{einzug}{wert}"]

