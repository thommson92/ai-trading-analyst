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
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any


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
                **felder,
                **zusatz,
            },
        )
