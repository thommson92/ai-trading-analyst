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


TREFFERGRENZE = 1500
"""Beobachtete Obergrenze je Anfrage.

Belegt am 2026-08-13: Ein Abruf ueber 120 Tage lieferte genau 1500
Eintraege, und ein Abruf ueber die 30 Tage vom 12.10. bis 10.11. ebenfalls.
Gekuerzt wird dabei **der Anfang** des Zeitraums -- im 120-Tage-Lauf fehlten
die naechsten sechs Wochen vollstaendig, im 30-Tage-Lauf die Wochen 9 und 10.
Die Antwort macht das mit keinem Feld kenntlich.
"""


def _fetch_zeitraum(
    api_key: str, von: date, bis: date, hinweise: list[str], tiefe: int = 0
) -> list[dict[str, Any]]:
    """Holt einen Zeitraum und halbiert ihn, wenn die Antwort gekuerzt wurde.

    Eine feste Fenstergroesse genuegt nicht: 30 Tage reichen im September,
    laufen in der Hochsaison Ende Oktober aber in die Grenze. Statt eine
    Groesse zu raten, wird die Kuerzung erkannt und der Zeitraum geteilt --
    so tief, bis die Antwort vollstaendig ist.
    """
    antwort = fetch_calendar(api_key, von, bis)
    teil = list(antwort.get("earningsCalendar", []))
    einrueckung = "  " + "  " * tiefe

    if len(teil) < TREFFERGRENZE or von == bis:
        vermerk = (
            "  <-- an der Grenze, aber nicht weiter teilbar"
            if len(teil) >= TREFFERGRENZE
            else ""
        )
        hinweise.append(f"{einrueckung}{von} bis {bis}: {len(teil)} Eintraege{vermerk}")
        return teil

    hinweise.append(
        f"{einrueckung}{von} bis {bis}: {len(teil)} Eintraege "
        f"<-- an der Grenze von {TREFFERGRENZE}, wird geteilt"
    )
    mitte = von + (bis - von) / 2
    return [
        *_fetch_zeitraum(api_key, von, mitte, hinweise, tiefe + 1),
        *_fetch_zeitraum(api_key, mitte + timedelta(days=1), bis, hinweise, tiefe + 1),
    ]


def fetch_in_chunks(
    api_key: str, von: date, bis: date, fenster_tage: int
) -> tuple[list[dict[str, Any]], list[str]]:
    """Holt einen langen Zeitraum in kurzen Fenstern, ohne Kuerzungen.

    Wer einen langen Zeitraum am Stueck anfragt, bekommt stillschweigend
    einen Ausschnitt und haelt ihn fuer das Ganze. Kurze Fenster und die
    Teilung bei Erreichen der Grenze verhindern das. Sie kosten mehr
    Anfragen, aber bei 60 je Minute faellt das nicht ins Gewicht.
    """
    eintraege: list[dict[str, Any]] = []
    hinweise: list[str] = []
    gesehen: set[tuple[str, str]] = set()

    fenster_start = von
    while fenster_start <= bis:
        fenster_ende = min(fenster_start + timedelta(days=fenster_tage - 1), bis)
        for eintrag in _fetch_zeitraum(api_key, fenster_start, fenster_ende, hinweise):
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


def _eimer_nach_vorlauf(eintraege: Sequence[dict[str, Any]]) -> dict[int, list[bool]]:
    heute = date.today()  # noqa: DTZ011 -- Kalendertag genuegt fuer eine Diagnose
    eimer: dict[int, list[bool]] = {}
    for eintrag in eintraege:
        try:
            termin = date.fromisoformat(str(eintrag.get("date", "")))
        except ValueError:
            continue
        woche = max((termin - heute).days, 0) // 7
        eimer.setdefault(woche, []).append(_hat_wert(eintrag.get("hour")))
    return eimer


def _tabelle(eimer: dict[int, list[bool]]) -> list[str]:
    zeilen = []
    for woche in sorted(eimer):
        werte = eimer[woche]
        anteil = sum(werte) / len(werte) * 100
        zeilen.append(
            f"    in {woche:>2} Woche(n): {sum(werte):>4} von {len(werte):>4} "
            f"mit Tageszeit ({anteil:.0f} %)"
        )
    return zeilen


def _vorlaufanalyse(
    eintraege: Sequence[dict[str, Any]], watchlist: Sequence[str]
) -> list[str]:
    """Zeigt die Tageszeit einen bestaetigten Termin an -- oder nur Groesse?

    Der Kalender kennt kein Feld ``confirmed`` (P5). Naheliegend waere:
    Unternehmen bestaetigen ihren Termin wenige Wochen vorher, und erst dann
    steht fest, ob vor oder nach Schluss gemeldet wird. Dann muesste ``hour``
    bei nahen Terminen haeufiger gefuellt sein als bei fernen.

    Es gibt aber eine zweite Erklaerung, die dasselbe Bild erzeugt: ``hour``
    ist bei **gut abgedeckten grossen Titeln** eher bekannt als bei kleinen,
    unabhaengig vom Vorlauf. Dann steigt der Anteil einfach dort, wo viele
    Grossunternehmen berichten -- und ``hour`` taugt **nicht** als Ersatz
    fuer die fehlende Kennzeichnung.

    Unterschieden wird das an der eigenen Watchlist: Sie besteht durchweg
    aus grossen, gut abgedeckten Titeln. Bleibt der Anteil dort ueber alle
    Vorlaufwochen hinweg hoch, ist es ein Groesseneffekt.
    """
    zeilen = ["", "  Vorlauf gegen Angabe der Tageszeit (alle Titel):"]
    zeilen.extend(_tabelle(_eimer_nach_vorlauf(eintraege)))

    bekannte = set(watchlist)
    eigene = [e for e in eintraege if str(e.get("symbol")) in bekannte]
    if not eigene:
        return zeilen

    fremde = [e for e in eintraege if str(e.get("symbol")) not in bekannte]
    zeilen.append("")
    zeilen.append("  Nur die eigene Watchlist (grosse, gut abgedeckte Titel):")
    zeilen.extend(_tabelle(_eimer_nach_vorlauf(eigene)))

    anteil_eigene = sum(_hat_wert(e.get("hour")) for e in eigene) / len(eigene) * 100
    zeilen.append("")
    zeilen.append(f"  Anteil mit Tageszeit -- Watchlist: {anteil_eigene:.0f} %")
    if fremde:
        anteil_fremde = sum(_hat_wert(e.get("hour")) for e in fremde) / len(fremde) * 100
        zeilen.append(f"  Anteil mit Tageszeit -- uebrige:   {anteil_fremde:.0f} %")
    zeilen.append(
        "  Liegt die Watchlist durchgehend deutlich hoeher, ist die Tageszeit "
        "ein Merkmal der Abdeckung und kein Hinweis auf einen bestaetigten Termin."
    )
    return zeilen


def summarize(
    eintraege: Sequence[dict[str, Any]], watchlist: Iterable[str]
) -> list[str]:
    """Fasst die Antwort zusammen -- Felder und Abdeckung, keine Kennzahlen."""
    zeilen: list[str] = []
    watchlist = sorted(set(watchlist))
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
        zeilen.extend(_vorlaufanalyse(eintraege, watchlist))
    else:
        zeilen.append("  kein Feld zur Tageszeit vorhanden")

    if watchlist:
        getroffen = sorted(set(beobachtet) & set(watchlist))
        fehlend = sorted(set(watchlist) - set(beobachtet))
        zeilen.append("")
        zeilen.append("P6 -- Abdeckung der eigenen Watchlist:")
        zeilen.append(f"  Watchlist: {len(watchlist)} Symbole")
        zeilen.append(
            f"  davon im Zeitraum mit Termin: {len(getroffen)} "
            f"({len(getroffen) / len(watchlist) * 100:.0f} %)"
        )
        # Ueber vier Monate muss jeder Quartalsberichterstatter einmal
        # auftauchen. Wer dann fehlt, ist der interessante Fall -- eine
        # abweichende Schreibweise, ein Neuling oder eine echte Luecke.
        if fehlend:
            zeilen.append(f"  OHNE Termin ({len(fehlend)}): {', '.join(fehlend)}")
        else:
            zeilen.append("  Kein Titel ohne Termin.")
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
