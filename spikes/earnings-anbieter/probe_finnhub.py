"""Prueft den Earnings-Kalender von Finnhub gegen die eigene Watchlist.

Beantwortet die fachlichen Fragen P4 bis P8 aus
``docs/requirements/earnings-anbieter-evaluation.md``:

* **P4** Wie weit reicht der Vorlauf in der Gratis-Stufe?
* **P5** Sind die Termine als bestaetigt oder geschaetzt gekennzeichnet?
  Ein geschaetzter Termin, der als bestaetigt behandelt wird, waere ein
  erfundener Wert.
* **P6** Wie viele Titel der eigenen Watchlist sind abgedeckt?
* **P7** Liefert derselbe Anbieter auch Ratings und Kursziele?
* **P8** Steht dabei, ob vor oder nach Boersenschluss gemeldet wird?

Der Kalenderabruf kostet **eine einzige Anfrage** fuer den gesamten
Zeitraum, unabhaengig von der Zahl der Symbole. Genau das ist der Grund,
warum das Anfragekontingent hier nicht die bindende Grenze ist.

Der Schluessel wird ausschliesslich aus der Umgebungsvariablen
``ATA_FINNHUB_API_KEY`` gelesen -- nie als Argument, nie im Code, nie in der
Ausgabe (Projektregel: Geheimnisse nur ueber ``ATA_``-Variablen).

Einmalige Diagnose, kein Produktionscode.

Aufruf:

    export ATA_FINNHUB_API_KEY="..."
    python spikes/earnings-anbieter/probe_finnhub.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

API_KEY_VARIABLE = "ATA_FINNHUB_API_KEY"
CALENDAR_URL = "https://finnhub.io/api/v1/calendar/earnings"

BESTAETIGUNGS_HINWEISE = ("confirm", "status", "verified", "estimated", "tentative")
"""Feldnamen, die auf eine Kennzeichnung bestaetigt/geschaetzt hindeuten
wuerden (P5). Gesucht wird nach Teilzeichenketten, weil der genaue Name
nicht bekannt ist -- das ist ja gerade die Frage."""


class ProbeError(RuntimeError):
    """Der Abruf ist gescheitert -- mit einer Meldung fuer den Aufrufer."""


def read_api_key() -> str:
    schluessel = os.environ.get(API_KEY_VARIABLE, "").strip()
    if not schluessel:
        raise ProbeError(
            f"{API_KEY_VARIABLE} ist nicht gesetzt. Kostenlosen Schluessel unter "
            "https://finnhub.io/register anlegen und setzen -- nicht im Code ablegen."
        )
    return schluessel


def fetch_calendar(api_key: str, von: date, bis: date) -> dict[str, Any]:
    parameter = urllib.parse.urlencode(
        {"from": von.isoformat(), "to": bis.isoformat(), "token": api_key}
    )
    try:
        with urllib.request.urlopen(f"{CALENDAR_URL}?{parameter}", timeout=30) as antwort:
            return dict(json.load(antwort))
    except urllib.error.HTTPError as fehler:
        # Der Schluessel steht in der URL und damit moeglicherweise in der
        # Fehlermeldung -- deshalb nur Status und Grund weitergeben.
        raise ProbeError(
            f"Finnhub hat mit HTTP {fehler.code} geantwortet ({fehler.reason}). "
            "Bei 401/403 stimmt der Schluessel nicht, bei 429 ist das Kontingent "
            "erschoepft."
        ) from None
    except urllib.error.URLError as fehler:
        raise ProbeError(f"Keine Verbindung zu Finnhub: {fehler.reason}") from None


def fetch_in_chunks(
    api_key: str, von: date, bis: date, fenster_tage: int
) -> tuple[list[dict[str, Any]], list[str]]:
    """Holt einen langen Zeitraum in kurzen Fenstern.

    Eine einzelne Anfrage ueber 120 Tage lieferte 1500 Eintraege -- eine
    verdaechtig runde Zahl -- und darin ausschliesslich Termine der letzten
    sechs Wochen des Zeitraums. Die naheliegenden Termine fehlten also
    vollstaendig, ohne dass die Antwort das kenntlich gemacht haette. Wer
    einen langen Zeitraum am Stueck anfragt, bekommt stillschweigend einen
    Ausschnitt.

    Kurze Fenster umgehen das. Sie kosten mehr Anfragen, aber bei 60 je
    Minute faellt das nicht ins Gewicht.
    """
    eintraege: list[dict[str, Any]] = []
    hinweise: list[str] = []
    gesehen: set[tuple[str, str]] = set()

    fenster_start = von
    while fenster_start <= bis:
        fenster_ende = min(fenster_start + timedelta(days=fenster_tage - 1), bis)
        antwort = fetch_calendar(api_key, fenster_start, fenster_ende)
        teil = list(antwort.get("earningsCalendar", []))
        hinweise.append(
            f"  {fenster_start} bis {fenster_ende}: {len(teil)} Eintraege"
            + (
                "  <-- verdaechtig runde Zahl, moeglicherweise gekuerzt"
                if teil and len(teil) % 500 == 0
                else ""
            )
        )
        for eintrag in teil:
            kennung = (str(eintrag.get("symbol")), str(eintrag.get("date")))
            if kennung not in gesehen:
                gesehen.add(kennung)
                eintraege.append(eintrag)
        fenster_start = fenster_ende + timedelta(days=1)

    return eintraege, hinweise


def watchlist_symbols(verzeichnis: Path) -> list[str]:
    """Liest die TradingView-Exporte, ohne den Produktivcode zu importieren.

    Der Spike bleibt eigenstaendig; die paar Zeilen Parsing sind billiger
    als eine Abhaengigkeit auf ``backend/``.
    """
    symbole: list[str] = []
    for datei in sorted(verzeichnis.glob("*.txt")):
        for eintrag in datei.read_text(encoding="utf-8").split(","):
            bereinigt = eintrag.strip()
            if not bereinigt or bereinigt.startswith("###"):
                continue
            symbole.append(bereinigt.split(":")[-1].strip())
    return sorted(set(symbole))


def _hat_wert(wert: Any) -> bool:
    """``epsActual: null`` ist ein vorhandenes Feld ohne Wert.

    Die Unterscheidung ist nicht kosmetisch: Ein Feld, das immer da, aber
    fuer kuenftige Termine immer leer ist, taugt fuer nichts.
    """
    return wert is not None and str(wert).strip() != ""


def _vorlaufanalyse(eintraege: Sequence[dict[str, Any]]) -> list[str]:
    """Haengt die Angabe der Tageszeit vom Vorlauf ab?

    Der Kalender kennt kein Feld ``confirmed`` (P5). Es gibt aber eine
    naheliegende Vermutung: Boersennotierte Unternehmen bestaetigen ihren
    Termin ueblicherweise wenige Wochen vorher, und erst dann steht auch
    fest, ob vor oder nach Schluss gemeldet wird. Waere das so, muesste
    ``hour`` bei nahen Terminen deutlich haeufiger gefuellt sein als bei
    fernen -- und liesse sich als Ersatz fuer die fehlende Kennzeichnung
    verwenden.

    Verteilt sich die Luecke dagegen gleichmaessig ueber den Vorlauf, ist
    ``hour`` einfach unvollstaendig und als Hinweis auf einen bestaetigten
    Termin **nicht** brauchbar. Die Auswertung entscheidet das, statt es zu
    vermuten.
    """
    heute = date.today()  # noqa: DTZ011 -- Kalendertag genuegt fuer eine Diagnose
    eimer: dict[int, list[bool]] = {}
    for eintrag in eintraege:
        roh = str(eintrag.get("date", ""))
        try:
            termin = date.fromisoformat(roh)
        except ValueError:
            continue
        woche = max((termin - heute).days, 0) // 7
        eimer.setdefault(woche, []).append(_hat_wert(eintrag.get("hour")))

    if not eimer:
        return []

    zeilen = ["", "  Vorlauf gegen Angabe der Tageszeit:"]
    for woche in sorted(eimer):
        werte = eimer[woche]
        anteil = sum(werte) / len(werte) * 100
        zeilen.append(
            f"    in {woche} Woche(n): {sum(werte):>4} von {len(werte):>4} "
            f"mit Tageszeit ({anteil:.0f} %)"
        )
    zeilen.append(
        "  Faellt der Anteil mit dem Vorlauf deutlich, ist eine gefuellte "
        "Tageszeit ein Hinweis auf einen bestaetigten Termin."
    )
    return zeilen


def summarize(
    eintraege: Sequence[dict[str, Any]], watchlist: Iterable[str]
) -> list[str]:
    """Fasst die Antwort zusammen -- Felder und Abdeckung, keine Kennzahlen."""
    zeilen: list[str] = []
    beobachtet = sorted({symbol for eintrag in eintraege if (symbol := eintrag.get("symbol"))})

    zeilen.append(f"Eintraege insgesamt: {len(eintraege)}")
    zeilen.append(f"Verschiedene Symbole: {len(beobachtet)}")

    felder: Counter[str] = Counter()
    gefuellt: Counter[str] = Counter()
    for eintrag in eintraege:
        # Nicht ``update(eintrag)``: Ein Counter nimmt ein Mapping als
        # Element-zu-Anzahl und wuerde die Werte aufaddieren.
        felder.update(eintrag.keys())
        gefuellt.update(name for name, wert in eintrag.items() if _hat_wert(wert))
    zeilen.append("")
    zeilen.append("Felder je Eintrag (vorhanden / davon mit Wert):")
    for name, anzahl in sorted(felder.items()):
        anteil = gefuellt[name] / len(eintraege) * 100 if eintraege else 0.0
        zeilen.append(
            f"  {name:<20} {anzahl:>5} vorhanden, {gefuellt[name]:>5} mit Wert "
            f"({anteil:.0f} %)"
        )

    mehrfach = Counter(str(eintrag.get("symbol")) for eintrag in eintraege)
    doppelte = [symbol for symbol, anzahl in mehrfach.items() if anzahl > 1]
    if doppelte:
        zeilen.append("")
        zeilen.append(
            f"{len(doppelte)} Symbole erscheinen mehrfach im Zeitraum "
            f"(z. B. {', '.join(sorted(doppelte)[:8])}) -- zu klaeren, ob das "
            "zwei Quartale sind oder Dubletten."
        )

    zeilen.append("")
    zeilen.append("P5 -- Kennzeichnung bestaetigt/geschaetzt:")
    verdaechtig = [
        name
        for name in felder
        if any(hinweis in name.lower() for hinweis in BESTAETIGUNGS_HINWEISE)
    ]
    if verdaechtig:
        zeilen.append(f"  moegliche Felder: {', '.join(sorted(verdaechtig))}")
        for name in sorted(verdaechtig):
            werte = sorted({str(eintrag.get(name)) for eintrag in eintraege})[:8]
            zeilen.append(f"    {name} = {' | '.join(werte)}")
    else:
        zeilen.append(
            "  KEIN solches Feld vorhanden. Damit laesst sich ein bestaetigter"
        )
        zeilen.append(
            "  nicht von einem geschaetzten Termin unterscheiden -- das ist ein"
        )
        zeilen.append("  Befund, kein Fehler der Sonde.")

    zeilen.append("")
    zeilen.append("P8 -- Tageszeit der Meldung:")
    if "hour" in felder:
        verteilung = Counter(str(eintrag.get("hour", "")) for eintrag in eintraege)
        aufstellung = ", ".join(
            f"{wert or '(leer)'}: {anzahl}" for wert, anzahl in verteilung.most_common()
        )
        zeilen.append(f"  hour = {aufstellung}")
        zeilen.extend(_vorlaufanalyse(eintraege))
    else:
        zeilen.append("  kein Feld zur Tageszeit vorhanden")

    watchlist = sorted(set(watchlist))
    if watchlist:
        getroffen = sorted(set(beobachtet) & set(watchlist))
        zeilen.append("")
        zeilen.append("P6 -- Abdeckung der eigenen Watchlist:")
        zeilen.append(f"  Watchlist: {len(watchlist)} Symbole")
        zeilen.append(
            f"  davon im Zeitraum mit Termin: {len(getroffen)} "
            f"({len(getroffen) / len(watchlist) * 100:.0f} %)"
        )
        zeilen.append(
            "  Hinweis: Ein fehlender Termin heisst nicht 'nicht abgedeckt' -- "
            "die meisten Titel berichten schlicht nicht in diesem Fenster."
        )
        if getroffen:
            zeilen.append(f"  Beispiele: {', '.join(getroffen[:12])}")
    return zeilen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--tage", type=int, default=30, help="Vorlauf ab heute (Standard: 30)"
    )
    parser.add_argument(
        "--watchlists",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "watchlists",
        help="Verzeichnis mit den TradingView-Exporten",
    )
    parser.add_argument(
        "--fenster",
        type=int,
        default=30,
        help="Groesse der einzelnen Anfragefenster in Tagen (Standard: 30). "
        "Lange Zeitraeume am Stueck liefern nur einen Ausschnitt.",
    )
    parser.add_argument(
        "--from-file", type=Path, default=None, help="Gespeicherte Antwort auswerten"
    )
    args = parser.parse_args(argv)

    heute = date.today()  # noqa: DTZ011 -- Kalendertag genuegt fuer eine Diagnose
    bis = heute + timedelta(days=args.tage)
    hinweise: list[str] = []
    try:
        if args.from_file is not None:
            antwort = json.loads(args.from_file.read_text(encoding="utf-8"))
            eintraege = list(antwort.get("earningsCalendar", []))
            quelle = str(args.from_file)
        else:
            eintraege, hinweise = fetch_in_chunks(
                read_api_key(), heute, bis, args.fenster
            )
            antwort = {"earningsCalendar": eintraege}
            quelle = (
                f"finnhub.io, {heute} bis {bis} "
                f"in Fenstern zu {args.fenster} Tagen ({len(hinweise)} Anfragen)"
            )
    except ProbeError as fehler:
        print(str(fehler), file=sys.stderr)
        return 2

    ziel = (
        Path(__file__).parent
        / "results"
        / f"finnhub_{heute.isoformat()}_{args.tage}t.json"
    )
    ziel.write_text(json.dumps(antwort, indent=2), encoding="utf-8")

    print(f"Quelle: {quelle}")
    print(f"Antwort gespeichert: {ziel}  (nicht versioniert)")
    if hinweise:
        print("\nAnfragen:")
        for zeile in hinweise:
            print(zeile)
    print()
    if not eintraege:
        print(
            "Die Antwort enthaelt keinen einzigen Termin. Das ist ein Fehlschlag, "
            "kein Ergebnis -- vermutlich deckt die Gratis-Stufe den Endpunkt nicht ab.",
            file=sys.stderr,
        )
        return 1

    watchlist = (
        watchlist_symbols(args.watchlists) if args.watchlists.is_dir() else []
    )
    for zeile in summarize(eintraege, watchlist):
        print(zeile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
