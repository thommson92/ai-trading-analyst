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
der Wechsel auf den Header bleibt als eigener Schritt moeglich.
"""

from __future__ import annotations

_PLATZHALTER = "***"


def redact(text: str, secret: str) -> str:
    """``text`` mit jedem Vorkommen von ``secret`` ersetzt.

    Ein leerer oder sehr kurzer ``secret`` wird uebergangen: Ein einzelnes
    Zeichen zu ersetzen zerschriebe den Text, ohne etwas zu schuetzen -- und
    ein leerer String ersetzte jede Position.
    """
    if len(secret) < 8:
        return text
    return text.replace(secret, _PLATZHALTER)
