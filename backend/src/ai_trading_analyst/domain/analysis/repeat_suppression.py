"""Wiederholsperre des Tageslaufs (ADR 0054).

Ein Symbol, dessen letzte volle Analyse in das Sperrfenster faellt, wird vom
Lauf komplett uebersprungen: keine Signalpruefung, keine Analyse, keine
Zeile in Ergebnis und Meldung. Anker ist die letzte volle Analyse -- ein
unterdruecktes Wiederauftreten erzeugt keine neue Analysezeile und
verlaengert die Sperre deshalb nicht.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta


@dataclass(frozen=True, slots=True)
class RepeatSuppressionParameters:
    """Sperrfenster des Tageslaufs.

    ``window_days``: Kalendertage einschliesslich des Analysetages -- ein am
    Tag 0 analysierter Titel kehrt am Tag ``window_days`` zurueck. ``0``
    schaltet die Sperre ab; ``1`` wirkt faktisch ebenso, weil der laufende
    Tag nie sperrt (siehe ``suppression_window``). Ausloeser ist jede volle
    Analyse (ADR 0054) -- die verworfene Variante "nur empfohlene Stufen
    sperren" waere bei Bedarf eine zusaetzliche WHERE-Klausel auf der Spalte
    ``recommendation``, kein Parameter.
    """

    window_days: int


def suppression_window(
    now: datetime, params: RepeatSuppressionParameters
) -> tuple[datetime, datetime] | None:
    """``(seit, bis)`` des Sperrfensters -- ``None`` bei Sperre aus.

    Gesperrt ist eine volle Analyse mit ``seit <= evaluated_at < bis``. Das
    Fenster zaehlt in **Kalendertagen der uebergebenen Zeitzone** (der
    Aufrufer uebergibt ``now`` in Boersenzeit) und endet am Beginn des
    laufenden Tages -- der Tag selbst sperrt nie, aus zwei Gruenden
    (ADR 0054):

    - Ein Wiederholungslauf desselben Tages (Absturz, Dispatcher-Retry)
      darf die Zeilen des abgebrochenen Laufs nicht als Sperre sehen, sonst
      fehlten dem angenommenen Lauf des Tages genau diese Kandidaten.
    - Der Kalenderanker macht die Rueckkehr planbar: Tag 0 analysiert,
      Tag ``window_days`` wieder dran -- unabhaengig vom Minuten-Jitter
      des Schedulers, der bei einem Uhrzeitvergleich aus sieben Tagen
      unvorhersehbar acht machte.
    """
    if params.window_days <= 0:
        return None
    bis = datetime.combine(now.date(), time.min, tzinfo=now.tzinfo)
    seit = bis - timedelta(days=params.window_days - 1)
    return seit, bis
