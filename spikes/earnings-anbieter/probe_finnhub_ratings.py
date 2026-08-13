"""Prueft, ob Finnhub auch Ratings und Kursziele liefert (P7).

Seit IBKR als Research-Quelle ausgeschieden ist
([ADR 0016](../../docs/adr/0016-ibkr-keine-quelle-fuer-research-daten.md)),
fehlen nicht nur die Earnings-Termine, sondern auch Analystenratings und
Kursziele. Liefert Finnhub beides, braucht es nur einen Anbieter statt zwei.

Die Frage ist nicht durch Recherche zu beantworten, sondern durch einen
Abruf: Eine Antwort mit Daten heisst enthalten, ein 403 heisst
kostenpflichtig. Vergleichsseiten irren sich hier regelmaessig -- der
angebliche Vorlauf von einem Monat beim Earnings-Kalender war ebenfalls
falsch.

Ausgegeben werden Feldnamen, Fuellgrad und Wertformen -- keine
Analystenaussagen. Ein Kursziel von 350 ist die lizenzgebundene Aussage und
erscheint als ``999``; dass es ein Feld ``targetMean`` gibt, ist die
Antwort auf unsere Frage.

Aufruf:

    export ATA_FINNHUB_API_KEY="..."
    python spikes/earnings-anbieter/probe_finnhub_ratings.py AAPL MSFT WMT
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from probe_finnhub import read_api_key

ENDPUNKTE = {
    "Empfehlungen": "https://finnhub.io/api/v1/stock/recommendation",
    "Kursziel": "https://finnhub.io/api/v1/stock/price-target",
}


def value_shape(wert: Any) -> str:
    """Ersetzt Inhalt durch sein Muster -- wie bei der RESC-Sonde."""
    text = str(wert).strip()
    if not text:
        return "(leer)"
    muster = "".join(
        "9" if z.isdigit() else "A" if z.isalpha() else z for z in text
    )
    return re.sub(r"(.)\1{7,}", r"\1{...}", muster)[:40]


def fetch(url: str, api_key: str, symbol: str) -> tuple[int, Any]:
    parameter = urllib.parse.urlencode({"symbol": symbol, "token": api_key})
    try:
        with urllib.request.urlopen(f"{url}?{parameter}", timeout=30) as antwort:
            return antwort.status, json.load(antwort)
    except urllib.error.HTTPError as fehler:
        # Der Schluessel steht in der URL -- nur Status weitergeben.
        return fehler.code, None
    except urllib.error.URLError as fehler:
        print(f"Keine Verbindung zu Finnhub: {fehler.reason}", file=sys.stderr)
        raise SystemExit(2) from None


def beschreibe(nutzlast: Any) -> list[str]:
    """Fasst eine Antwort zu Feldern und Wertformen zusammen."""
    if isinstance(nutzlast, list):
        if not nutzlast:
            return ["    leere Liste -- Endpunkt erreichbar, aber ohne Daten"]
        zeilen = [f"    {len(nutzlast)} Eintraege, Felder des ersten:"]
        nutzlast = nutzlast[0]
    else:
        zeilen = ["    Felder:"]
    if not isinstance(nutzlast, dict) or not nutzlast:
        return ["    keine auswertbare Struktur"]
    for name in sorted(nutzlast):
        zeilen.append(f"      {name:<18} ~ {value_shape(nutzlast[name])}")
    return zeilen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("symbole", nargs="*", default=["AAPL", "MSFT", "WMT"])
    args = parser.parse_args(argv)

    api_key = read_api_key()
    verdikt: dict[str, set[int]] = {name: set() for name in ENDPUNKTE}

    for symbol in args.symbole:
        print(f"\n{symbol}")
        for name, url in ENDPUNKTE.items():
            status, nutzlast = fetch(url, api_key, symbol)
            verdikt[name].add(status)
            print(f"  {name}: HTTP {status}")
            if status == 200:
                for zeile in beschreibe(nutzlast):
                    print(zeile)

    print("\nP7 -- Ergebnis:")
    for name, stati in verdikt.items():
        if stati == {200}:
            befund = "in der Gratis-Stufe enthalten"
        elif 403 in stati or 401 in stati:
            befund = "kostenpflichtig oder nicht berechtigt"
        else:
            befund = f"unklar, Status {sorted(stati)}"
        print(f"  {name}: {befund}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
