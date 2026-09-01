"""Geheimnisse aus allem entfernen, was das System nach aussen schreibt.

**Der gemessene Befund.** Finnhub nahm den Zugangsschluessel als
Query-Parameter ``token`` entgegen, und genau so hat ihn dieses System
geschickt. Damit stand er in der URL -- und die URL steht an mindestens drei
Stellen, an denen niemand ein Geheimnis vermutet:

1. Im Text jeder ``httpx``-Ausnahme::

       Server error '500 ...' for url
       'https://finnhub.io/api/v1/stock/recommendation?symbol=AAPL&token=echt-geheim'

2. **In jeder erfolgreichen Anfrage.** ``httpx`` protokolliert selbst, auf
   ``INFO``::

       HTTP Request: GET https://finnhub.io/...&token=echt-geheim "HTTP/1.1 200 OK"

   ``config/default.yaml`` steht auf ``level: INFO``. Der Schluessel stand
   damit nicht im Ausnahmefall im Protokoll, sondern **bei jedem Abruf** --
   rund zweihundert Zeilen je Tageslauf.

3. In der **Ausnahmekette**. ``raise ... from error`` haelt die ausloesende
   Ausnahme als ``__cause__`` fest. Ein geschwaerzter Text der aeusseren
   Ausnahme nuetzt dann nichts: ``_logger.exception`` formatiert die ganze
   Kette, und die Ursache traegt die unveraenderte URL.

Eine Schwaerzung an einer einzelnen Fehlermeldung erwischt nur (1). Deshalb
sitzt sie hier an der **Senke**: Der Log-Formatter laesst jede fertige Zeile
durch ``redact_registered`` laufen -- Meldung, Traceback und Zusatzfelder
gleichermassen. Was das System nicht selbst formuliert hat, ist damit
genauso abgedeckt wie die eigenen Meldungen.

**Der Header ist inzwischen der Weg.** Seit dem 2026-09-01 schickt der
Finnhub-Adapter den Schluessel als ``X-Finnhub-Token``
(``infrastructure/finnhub/auth.py``); in der URL steht er nicht mehr, und
damit sind alle drei Kanaele an der Wurzel trocken.

Diese Schwaerzung bleibt trotzdem und ist keine Doppelung: Sie wirkt fuer
**jedes** Geheimnis und jeden Anbieter -- auch fuer den naechsten Parameter,
den jemand ergaenzt, ohne diesen Absatz gelesen zu haben.
"""

from __future__ import annotations

import logging
import threading
from urllib.parse import quote

# Kein ``get_logger`` aus ``logging_setup``: Das Modul importiert diese
# Datei bereits, und ein Ringimport waere die Folge.
_logger = logging.getLogger(__name__)

_PLATZHALTER = "***"

_MINDESTLAENGE = 8
"""Kuerzere Geheimnisse werden nicht ersetzt.

Ein leerer String ersetzte jede Position im Text, ein einzelnes Zeichen
zerschriebe ihn -- ohne etwas zu schuetzen. Ein echter Zugangsschluessel ist
deutlich laenger; ein kuerzerer ist ohnehin kein gueltiger Zugang.
"""

_lock = threading.Lock()
_bekannte_geheimnisse: set[str] = set()


def register_secret(secret: str) -> None:
    """Meldet ein Geheimnis an, das aus allen Logzeilen entfernt wird.

    Wird beim Laden der Geheimnisse fuer **jeden** gesetzten Wert aufgerufen,
    nicht je Adapter: Ein Geheimnis, das nur ein einziger Anbieter benutzt,
    kann trotzdem an ganz anderer Stelle in eine Zeile geraten.

    Ein zu kurzer Wert wird **nicht** angemeldet -- er wuerde den Text
    zerschreiben, ohne etwas zu schuetzen. Das ist eine Warnung und kein
    Abbruch: Diese Schicht ist ein Schutznetz, und ein Schutznetz darf nicht
    die Ursache dafuer sein, dass ein Lauf nicht startet. Ob ein Wert
    plausibel ist, prueft ``Secrets``, nicht die Schwaerzung.
    """
    if not secret:
        return
    if len(secret) < _MINDESTLAENGE:
        _logger.warning(
            "Ein Geheimnis ist kuerzer als %d Zeichen und wird in Protokollen nicht "
            "geschwaerzt. Vermutlich ist eine ATA_-Umgebungsvariable falsch gesetzt.",
            _MINDESTLAENGE,
        )
        return
    with _lock:
        _bekannte_geheimnisse.add(secret)


def forget_secrets() -> None:
    """Leert die Anmeldungen. Fuer Tests -- der Betrieb ruft das nicht auf."""
    with _lock:
        _bekannte_geheimnisse.clear()


def redact(text: str, secret: str) -> str:
    """``text`` mit jedem Vorkommen von ``secret`` ersetzt.

    Ersetzt wird auch die **prozentkodierte** Form: ``httpx`` kodiert
    Query-Werte, und ein Schluessel mit Sonderzeichen stuende sonst in
    veraenderter Schreibweise unverdeckt im Text. Bei den heute ueblichen
    alphanumerischen Schluesseln sind beide Formen gleich -- die zweite
    Ersetzung kostet nichts und haengt nicht an dieser Annahme.

    Ein zu kurzes Geheimnis wird hier uebergangen statt abgelehnt: Diese
    Funktion laeuft im Fehlerpfad, und eine Ausnahme aus der Schwaerzung
    heraus verdraengte die eigentliche Fehlermeldung.
    """
    if len(secret) < _MINDESTLAENGE:
        return text

    geschwaerzt = text.replace(secret, _PLATZHALTER)
    kodiert = quote(secret, safe="")
    if kodiert != secret:
        geschwaerzt = geschwaerzt.replace(kodiert, _PLATZHALTER)
    return geschwaerzt


def redact_registered(text: str) -> str:
    """``text`` ohne jedes angemeldete Geheimnis.

    Ist nichts angemeldet, wird der Text unveraendert zurueckgegeben -- der
    Normalfall in Tests und bei einem Lauf ganz ohne Zugangsdaten.
    """
    with _lock:
        geheimnisse = tuple(_bekannte_geheimnisse)
    for geheimnis in geheimnisse:
        text = redact(text, geheimnis)
    return text
