"""Dauer eines Abschnitts messen und als eigenes Feld protokollieren.

Die Zusage aus dem Modulkopf von ``logging_setup`` -- Zusatzfelder landen als
eigene JSON-Schluessel -- wird hier zum ersten Mal eingeloest. Gemessen wird
mit ``time.monotonic``: Eine Zeitumstellung oder ein NTP-Sprung waehrend eines
einstuendigen Laufs darf keine negative Dauer erzeugen.

Bewusst **nur Protokoll und kein Feld am Ergebnis**: Wie lange eine Rechnung
gedauert hat, ist eine Aussage ueber den Rechner, nicht ueber die Aktie. Ein
abgeschlossenes Analyseergebnis ist unveraenderlich und beschreibt den
fachlichen Befund (CLAUDE.md, "Daten und Ergebnisse").
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any

_RECORD_EIGENE_NAMEN = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)))
"""Namen, die ``logging`` selbst am ``LogRecord`` belegt.

``Logger.log`` wirft fuer jeden davon ein ``KeyError`` -- und zwar **vor**
dem Formatter, dessen Umbenennung hier also nicht mehr greift. Aus dem
``finally`` heraus verdraengte das die echte Ausnahme des Abschnitts: Der
Aufrufer saehe einen KeyError ueber ein Logfeld statt des Anbieterfehlers,
den er sucht.
"""


def _ungefaehrlich(felder: Mapping[str, Any]) -> dict[str, Any]:
    """Benennt um, was ``logging`` sonst zurueckweist."""
    return {
        (f"feld_{name}" if name in _RECORD_EIGENE_NAMEN else name): wert
        for name, wert in felder.items()
    }


@contextmanager
def gemessen(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    monotonic: Callable[[], float] = time.monotonic,
    **felder: Any,
) -> Iterator[dict[str, Any]]:
    """Misst den umschlossenen Abschnitt und schreibt **eine** Zeile.

    Das hineingereichte Woerterbuch nimmt Felder auf, die erst waehrend des
    Abschnitts feststehen -- etwa wieviele Aktien tatsaechlich Kandidaten
    wurden. Es wird beim Verlassen mit ausgegeben.

    **Auch bei einer Ausnahme.** Ein Abschnitt, der scheitert, hat trotzdem
    Zeit gekostet, und gerade die ist interessant. Die Ausnahme laeuft
    unveraendert weiter; die Zeile traegt dann ``ausgang: "fehler"``.
    """
    zusatz: dict[str, Any] = {}
    begonnen = monotonic()
    ausgang = "ok"
    try:
        yield zusatz
    except BaseException:
        ausgang = "fehler"
        raise
    finally:
        dauer_ms = round((monotonic() - begonnen) * 1000, 1)
        logger.log(
            level,
            "%s: %.1f s",
            event,
            dauer_ms / 1000,
            extra={
                "event": event,
                "duration_ms": dauer_ms,
                "ausgang": ausgang,
                **_ungefaehrlich({**felder, **zusatz}),
            },
        )


class Zeitkonto:
    """Sammelt Dauern unter Namen und gibt sie **einmal** aus.

    Fuer Abschnitte, die sich nicht am Stueck messen lassen. Der wichtigste
    Fall ist ein **Generator**: Zwischen zwei ``yield`` ist er angehalten,
    und die Zeit gehoert dem Verbraucher. Ein ``with`` um die Schleife
    herum maesse dessen Arbeit mit -- beim Export also das Verschluesseln
    und Schreiben, nicht das Rechnen, um das es geht.

    Gemessen wird deshalb jeder Rechenaufruf einzeln, und am Ende steht eine
    Zeile mit der Summe je Name. Das ist zugleich die lesbare Form: Eine
    Zeile je Bericht waeren bei zweihundert Berichten zweihundert Zeilen,
    durch die niemand sieht.
    """

    def __init__(self) -> None:
        self._summen: dict[str, float] = {}
        self._aufrufe: dict[str, int] = {}

    @contextmanager
    def bei(self, name: str, *, monotonic: Callable[[], float] = time.monotonic) -> Iterator[None]:
        begonnen = monotonic()
        try:
            yield
        finally:
            # Auch ein gescheiterter Aufruf hat gerechnet.
            self._summen[name] = self._summen.get(name, 0.0) + (monotonic() - begonnen)
            self._aufrufe[name] = self._aufrufe.get(name, 0) + 1

    def als_felder(self) -> dict[str, Any]:
        """Die Summen in Millisekunden, je Name zwei Felder."""
        felder: dict[str, Any] = {}
        for name, sekunden in sorted(self._summen.items()):
            felder[f"{name}_ms"] = round(sekunden * 1000, 1)
            felder[f"{name}_anzahl"] = self._aufrufe[name]
        return felder

    def protokolliere(self, logger: logging.Logger, event: str, **felder: Any) -> None:
        """Eine Zeile mit allem, was gesammelt wurde."""
        logger.info(
            "%s: %s",
            event,
            ", ".join(
                f"{name} {sekunden:.1f} s ({self._aufrufe[name]}x)"
                for name, sekunden in sorted(
                    self._summen.items(), key=lambda paar: paar[1], reverse=True
                )
            )
            or "nichts gemessen",
            extra={"event": event, **_ungefaehrlich(felder), **self.als_felder()},
        )
