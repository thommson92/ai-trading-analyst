"""Wiederholsperre des Tageslaufs (ADR 0054).

Ein Symbol, dessen letzte volle Analyse juenger als das Sperrfenster ist,
wird vom Lauf komplett uebersprungen: keine Signalpruefung, keine Analyse,
keine Zeile in Ergebnis und Meldung. Anker ist die letzte volle Analyse --
ein unterdruecktes Wiederauftreten erzeugt keine neue Analysezeile und
verlaengert die Sperre deshalb nicht.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class RepeatSuppressionParameters:
    """Sperrfenster des Tageslaufs.

    ``window_days``: Kalendertage; ``0`` schaltet die Sperre ab. Ausloeser
    ist jede volle Analyse (ADR 0054) -- die verworfene Variante "nur
    empfohlene Stufen sperren" waere bei Bedarf eine zusaetzliche
    WHERE-Klausel auf der Spalte ``recommendation``, kein Parameter.
    """

    window_days: int


def suppression_cutoff(
    now: datetime, params: RepeatSuppressionParameters
) -> datetime | None:
    """Der Zeitpunkt, ab dem eine Analyse sperrt -- ``None`` bei Sperre aus.

    Strikte Grenze (ADR 0054): Gesperrt ist, was **juenger** als der Cutoff
    ist. Eine exakt ``window_days`` alte Analyse sperrt nicht mehr; die
    Abfrage vergleicht deshalb mit ``evaluated_at > cutoff``.
    """
    if params.window_days <= 0:
        return None
    return now - timedelta(days=params.window_days)
