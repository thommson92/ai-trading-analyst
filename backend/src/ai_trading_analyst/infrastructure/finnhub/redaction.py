"""Den Zugangsschluessel aus Fehlertexten entfernen.

Finnhub nimmt den Schluessel als Query-Parameter ``token``. ``httpx`` schreibt
die **vollstaendige URL** in den Text seiner Ausnahmen:

    Server error '500 Internal Server Error' for url
    'https://finnhub.io/api/v1/stock/recommendation?symbol=AAPL&token=echt-geheim'

Dieser Text wird in die Vertragsausnahme uebernommen, landet damit auf
``stderr`` und in jedem Protokoll, das den Fehler festhaelt. Ein Geheimnis
gehoert weder dorthin noch in eine Fehlermeldung, die jemand in ein Ticket
kopiert (CLAUDE.md, Abschnitt Sicherheit).

**Warum nicht einfach den Header verwenden?** Finnhub akzeptiert den
Schluessel auch als ``X-Finnhub-Token``, und dann taeuchte er in keiner URL
auf. Das waere der bessere Weg -- er aendert aber die Authentisierung einer
laufenden, produktiven Anbindung, und geprueft werden koennte er nur gegen
den echten Dienst. Diese Funktion schliesst die Luecke ohne dieses Risiko;
der Wechsel auf den Header bleibt als eigener Schritt moeglich und raeumt
beide unten genannten Kanten mit ab.
"""

from __future__ import annotations

from urllib.parse import quote

from ai_trading_analyst.observability.logging_setup import get_logger

_logger = get_logger(__name__)

_PLATZHALTER = "***"

_MINDESTLAENGE = 8
"""Kuerzere Geheimnisse werden nicht ersetzt.

Ein leerer String ersetzte jede Position im Text, ein einzelnes Zeichen
zerschriebe ihn -- ohne etwas zu schuetzen. Ein echter Finnhub-Schluessel ist
deutlich laenger; ein kuerzerer ist ohnehin kein gueltiger Zugang.
"""


def redact(text: str, secret: str) -> str:
    """``text`` mit jedem Vorkommen von ``secret`` ersetzt.

    Ersetzt wird auch die **prozentkodierte** Form: ``httpx`` kodiert
    Query-Werte, und ein Schluessel mit Sonderzeichen stuende sonst in
    veraenderter Schreibweise unverdeckt im Text. Bei den heute ueblichen
    alphanumerischen Finnhub-Schluesseln sind beide Formen gleich -- die
    zweite Ersetzung kostet nichts und haengt nicht an dieser Annahme.

    Ein zu kurzes Geheimnis wird uebergangen, aber **nicht stillschweigend**:
    Sonst stuende es unbemerkt im Protokoll.
    """
    if len(secret) < _MINDESTLAENGE:
        _logger.warning(
            "Zugangsschluessel ist kuerzer als %d Zeichen und wird in Fehlertexten "
            "nicht geschwaerzt. Ein gueltiger Finnhub-Schluessel ist laenger -- "
            "vermutlich ist die Umgebungsvariable falsch gesetzt.",
            _MINDESTLAENGE,
        )
        return text

    geschwaerzt = text.replace(secret, _PLATZHALTER)
    kodiert = quote(secret, safe="")
    if kodiert != secret:
        geschwaerzt = geschwaerzt.replace(kodiert, _PLATZHALTER)
    return geschwaerzt
