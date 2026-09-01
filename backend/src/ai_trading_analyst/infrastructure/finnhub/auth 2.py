"""Wie der Finnhub-Schluessel an die Anfrage kommt.

**Im Header und nicht als Abfrageparameter.** Beide Wege akzeptiert Finnhub;
der Unterschied liegt daneben. Ein Schluessel in der URL steht in jedem
Fehlertext von ``httpx``, in jedem Proxy-Protokoll und in jeder
Wiederholungsmeldung. [ADR 0044](../../../../../docs/adr/0044-schwaerzung-an-der-log-senke.md)
hat das an der Log-Senke geschwaerzt und den Weg hierher ausdruecklich als
den besseren, aber ungegangenen benannt -- das Repository-Audit fuehrt ihn
als A2-M10.

Die Schwaerzung bleibt trotzdem. Sie faengt, was ein einzelner Aufrufer
vergisst; dieser Weg sorgt dafuer, dass es nichts zu vergessen gibt.
"""

from __future__ import annotations

HEADER = "X-Finnhub-Token"


def authentifizierung(api_key: str) -> dict[str, str]:
    return {HEADER: api_key}
