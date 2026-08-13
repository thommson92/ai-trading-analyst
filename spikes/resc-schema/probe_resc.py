"""Einmalige Strukturpruefung der RESC-Antwort von Interactive Brokers.

Der IBKR-Spike hat belegt, dass ``reqFundamentalData(reportType='RESC')``
einen substantiellen Datensatz liefert (325 KB XML fuer AAPL), aber nicht,
**was** darin steht. Genau das ist die offene Entscheidung aus ADR 0014:
Taugt RESC als Quelle fuer Analystenratings und Kursziele (F9) -- und
enthaelt es womoeglich auch den naechsten Berichtstermin, was den Bedarf an
einem eigenen Earnings-Anbieter (Einschraenkung E1) verkleinern wuerde?

Diese Sonde beantwortet das, ohne den Inhalt preiszugeben. Ausgegeben werden
nur **Struktur** und **Wertformen**: Elementpfade, Attributnamen,
Haeufigkeiten und Muster wie ``9999-99-99`` statt ``2026-07-30``. Der Grund
ist zweifach -- die Daten stammen von einem Drittanbieter und sind
lizenzgebunden, und eine Antwort kann Kennungen enthalten, die nicht in ein
Protokoll gehoeren. Fuer die Frage "gibt es ein Feld mit dem Berichtstermin"
genuegt die Struktur.

Das vollstaendige XML wird lokal unter ``results/`` abgelegt (nicht
versioniert), damit gezielte Rueckfragen ohne einen zweiten TWS-Abruf
beantwortet werden koennen.

Einmalige Diagnose, kein Produktionscode: Die Sonde laeuft ausserhalb der
Anwendung, schreibt nichts in deren Datenbestand und stellt keine
ordererzeugenden Anfragen.

Aufruf auf dem Windows-Server (aus ``backend/``, dessen venv ``ib_async``
bereits enthaelt):

    .venv\\Scripts\\python.exe ..\\spikes\\resc-schema\\probe_resc.py AAPL
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from xml.etree import ElementTree

REPORT_TYPE = "RESC"

# Nicht die Client-ID des Analyzers (17) und nicht die der Trade Automation
# Toolbox (99): Eine doppelt vergebene ID wirft die bestehende Verbindung aus
# der TWS.
DEFAULT_CLIENT_ID = 18

MAX_SHAPES_PER_PATH = 3
"""Mehr Formbeispiele je Pfad bringen keinen Erkenntnisgewinn und blaehen die
Ausgabe auf."""

MAX_SCHEMA_VALUES = 12

SCHEMA_ATTRIBUTES = frozenset(
    {
        "type",
        "periodType",
        "periodUnit",
        "periodNum",
        "periodLength",
        "set",
        "code",
        "unit",
        "dateType",
        "desc",
        "currCode",
        "fyem",
        "fyNum",
    }
)
"""Attribute, deren Werte das **Schema** beschreiben und nicht die Daten.

``type="EPS"`` sagt, welche Kennzahl es gibt -- das ist die Frage, um die es
hier geht, und keine lizenzgebundene Analystenaussage. Bei diesen Attributen
werden die vorkommenden Werte aufgezaehlt; bei allen uebrigen (etwa
``updated`` oder ``endCalYear``) bleibt es bei der Wertform, denn dort steht
Inhalt.
"""


def value_shape(text: str) -> str:
    """Ersetzt Inhalt durch sein Muster: ``2026-07-30`` wird ``9999-99-99``.

    Ziffern werden zu ``9``, Buchstaben zu ``A``, alles andere bleibt stehen.
    Laengere Laeufe werden gekuerzt, damit ein Fliesstext nicht als
    Hunderte von ``A`` erscheint.
    """
    bereinigt = text.strip()
    if not bereinigt:
        return ""
    muster = "".join(
        "9" if zeichen.isdigit() else "A" if zeichen.isalpha() else zeichen
        for zeichen in bereinigt
    )
    gekuerzt = re.sub(r"(9)\1{7,}", r"\1{...}", muster)
    gekuerzt = re.sub(r"(A)\1{7,}", r"\1{...}", gekuerzt)
    return gekuerzt[:60]


def summarize(xml_text: str) -> list[str]:
    """Fasst das XML zu einer Zeile je Elementpfad zusammen."""
    wurzel = ElementTree.fromstring(xml_text)

    anzahl: dict[str, int] = {}
    attribute: dict[str, dict[str, set[str]]] = {}
    formen: dict[str, set[str]] = {}

    def besuche(element: ElementTree.Element, pfad: str) -> None:
        anzahl[pfad] = anzahl.get(pfad, 0) + 1
        je_attribut = attribute.setdefault(pfad, {})
        for name, wert in element.attrib.items():
            gezeigt = wert.strip() if name in SCHEMA_ATTRIBUTES else value_shape(wert)
            if gezeigt:
                je_attribut.setdefault(name, set()).add(gezeigt)
        form = value_shape(element.text or "")
        if form:
            formen.setdefault(pfad, set()).add(form)
        for kind in element:
            besuche(kind, f"{pfad}/{kind.tag}")

    besuche(wurzel, wurzel.tag)

    zeilen = []
    for pfad in sorted(anzahl):
        teile = [f"{pfad}  (x{anzahl[pfad]})"]
        for name in sorted(attribute[pfad]):
            werte = sorted(attribute[pfad][name])
            grenze = MAX_SCHEMA_VALUES if name in SCHEMA_ATTRIBUTES else MAX_SHAPES_PER_PATH
            rest = f"  (+{len(werte) - grenze} weitere)" if len(werte) > grenze else ""
            beschriftung = "=" if name in SCHEMA_ATTRIBUTES else "~"
            teile.append(f"  @{name} {beschriftung} " + " | ".join(werte[:grenze]) + rest)
        if pfad in formen:
            beispiele = sorted(formen[pfad])[:MAX_SHAPES_PER_PATH]
            teile.append("  Wertform: " + " | ".join(beispiele))
        zeilen.append("\n".join(teile))
    return zeilen


def fetch_resc(symbol: str, host: str, port: int, client_id: int, timeout: float) -> str:
    from ib_async import IB, Stock

    ib = IB()
    ib.connect(host, port, clientId=client_id, timeout=timeout)
    try:
        contracts = ib.qualifyContracts(Stock(symbol, "SMART", "USD"))
        if not contracts:
            raise SystemExit(f"Kontrakt fuer '{symbol}' konnte nicht aufgeloest werden.")
        return str(ib.reqFundamentalData(contracts[0], REPORT_TYPE))
    finally:
        ib.disconnect()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("symbol", help="Aktiensymbol, z. B. AAPL")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7496)
    parser.add_argument("--client-id", type=int, default=DEFAULT_CLIENT_ID)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--from-file",
        type=Path,
        default=None,
        help="Bereits gespeichertes XML auswerten, statt die TWS zu fragen.",
    )
    args = parser.parse_args(argv)

    if args.from_file is not None:
        xml_text = args.from_file.read_text(encoding="utf-8")
        quelle = str(args.from_file)
    else:
        xml_text = fetch_resc(
            args.symbol, args.host, args.port, args.client_id, args.timeout
        )
        quelle = f"TWS {args.host}:{args.port}"

    if not xml_text.strip():
        print(
            f"Leere Antwort fuer '{args.symbol}'. Das ist ein Fehlschlag, kein Ergebnis "
            "(ADR 0014, Einschraenkung E4) -- vermutlich fehlt die Berechtigung.",
            file=sys.stderr,
        )
        return 1

    ziel = Path(__file__).parent / "results" / f"{args.symbol}_resc.xml"
    ziel.write_text(xml_text, encoding="utf-8")

    print(f"Quelle: {quelle}")
    print(f"Symbol: {args.symbol}")
    print(f"Groesse: {len(xml_text):,} Zeichen")
    print(f"Vollstaendiges XML gespeichert: {ziel}  (nicht versioniert)")
    print("\nStruktur (Inhalte durch Wertformen ersetzt):\n")
    for zeile in summarize(xml_text):
        print(zeile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
