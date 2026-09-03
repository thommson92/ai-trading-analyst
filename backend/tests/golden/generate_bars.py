"""Erzeugt die eingefrorenen Bar-Reihen des Golden Masters.

**Diese Bars sind erzeugt, nicht gemessen.** Das ist kein Versehen und wird
hier ausdruecklich festgehalten: Der reale Bestand liegt in der PostgreSQL
des Windows-Servers und ist im Repository nicht vorhanden. Ein Golden Master
darf davon nicht abhaengen -- er soll auf jedem Rechner ohne Netz laufen.

Was der Golden Master leistet, haengt an dieser Unterscheidung:

* **Was er leistet:** Er friert das *Verfahren* ein. Aendert sich die
  Kerzenbildung, die Indikatorrechnung, die Kandidatenregel, der Cooldown oder
  eine Kennzahl, weicht das Ergebnis ab und ein Test bricht. Dafuer genuegen
  erzeugte Kursreihen vollstaendig -- die Rechnung kennt den Unterschied
  nicht.
* **Was er nicht leistet:** Er belegt nichts ueber das Verhalten an echten
  Kursen. Luecken, Feiertage, Splits, Halts und die tatsaechliche Volatilitaet
  stehen hier nicht drin.

Ein echter Ausschnitt laesst sich jederzeit danebenlegen: ``cli export-bars``
schreibt dasselbe Format aus dem Bestand, und ``available_cases()`` nimmt
jede weitere ``*.bars.csv`` als zusaetzlichen Fall auf.

Die Reihen sind ueber einen festen Startwert deterministisch: Derselbe Aufruf
erzeugt dieselbe Datei. Erzeugt wird ein Random Walk auf Bar-Ebene, aus dem
die Kerzenbildung dann regulaere 195-Minuten-Kerzen bildet -- die Bars liegen
deshalb exakt auf dem Sitzungsraster der regulaeren US-Sitzung.

Aufruf::

    python -m tests.golden.generate_bars
"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ai_trading_analyst.domain.screening import IntradayBar
from tests.golden.pipeline import DATA_DIR, NATIVE_BAR_MINUTES, SESSION, write_bars

NEW_YORK = ZoneInfo(SESSION.timezone)

ERSTER_HANDELSTAG = date(2024, 1, 2)

"""Zur Laenge der Reihen -- sie ist nach unten begrenzt durch das, was der
Golden Master bewachen soll.

Der Backtest stuft jede Signalkombination nach ihrer Stichprobengroesse ein,
und die drei Stufen verhalten sich **unterschiedlich**:

* unter 10 deduplizierten Ereignissen: ``INSUFFICIENT_DATA``, und dann gibt
  es fuer diese Kombination **keine einzige** Kennzahl
  (``metrics.py``, ``has_reliable_basis``),
* 10 bis 29: ``LOW_SAMPLE`` mit vollstaendigen Kennzahlen,
* ab 30: ``NORMAL``.

Eine Reihe, die nur die ersten beiden Stufen erreicht, laesst die dritte
unbewacht: Eine Aenderung, die ``NORMAL`` nicht mehr vergibt, liesse die
Aufzeichnungen byteweise gleich und die Suite gruen. Deshalb reicht
``synthetic-range`` bis in die dritte Stufe, waehrend ``synthetic-trend``
kurz bleibt -- eine Reihe genuegt dafuer, und die Bar-Dateien sollen nicht
beide wachsen.

Ein Test in ``test_golden_master.py`` haelt fest, dass ueber beide Faelle
hinweg alle drei Stufen aufgezeichnet sind."""

KURZE_REIHE = 400
"""800 Kerzen -- 250 Warm-up, 550 auswertbare Entscheidungspunkte."""

LANGE_REIHE = 1200
"""2400 Kerzen. Ab hier kommt die haeufigste Kombination ueber 30 Ereignisse
und damit auf ``NORMAL``.

Die Zahl ist zweimal gestiegen, beide Male aus demselben Grund: Die Regel
wurde schaerfer, also braucht dieselbe Aussage mehr Historie. Mit ADR 0056
verteilten sich die Ereignisse auf 12 statt 4 Kombinationen (700 -> 900); mit
den Torbedingungen aus ADR 0057 fallen zusaetzlich rund vierzig Prozent der
Entscheidungspunkte weg. Gemessen unter der heutigen Regel:
900 -> 28, 1200 -> 43.

Das ist kein Datentrick, sondern der sichtbare Preis der neuen Regel -- an
echten Kursen wird die Signalstatistik je Kombination aus demselben Grund
duenner (ADR 0056, Abschnitt Konsequenzen)."""

BARS_JE_TAG = SESSION.session_minutes // NATIVE_BAR_MINUTES


def _handelstage(erster: date, anzahl: int) -> list[date]:
    """Werktage ab ``erster``.

    Ohne Feiertagskalender -- bewusst. Die Kerzenbildung sieht einen
    Feiertag ohnehin nur als Tag ohne Bars, und ein Tag ohne Bars ist keine
    Kerze. Ein Kalender fuegte dem Golden Master nichts hinzu, was er
    bewachen soll.
    """
    tage: list[date] = []
    tag = erster
    while len(tage) < anzahl:
        if tag.weekday() < 5:
            tage.append(tag)
        tag += timedelta(days=1)
    return tage


def _bars_eines_tages(tag: date, kurs: float, wuerfel: random.Random) -> list[IntradayBar]:
    beginn = datetime.combine(tag, time(9, 30), tzinfo=NEW_YORK)
    bars: list[IntradayBar] = []
    for index in range(BARS_JE_TAG):
        start = beginn + timedelta(minutes=NATIVE_BAR_MINUTES * index)
        eroeffnung = kurs
        kurs = max(kurs * (1.0 + wuerfel.gauss(0.0, 0.0025)), 1.0)
        hoch = max(eroeffnung, kurs) * (1.0 + abs(wuerfel.gauss(0.0, 0.0008)))
        tief = min(eroeffnung, kurs) * (1.0 - abs(wuerfel.gauss(0.0, 0.0008)))
        bars.append(
            IntradayBar(
                start=start,
                open=round(eroeffnung, 4),
                high=round(hoch, 4),
                low=round(tief, 4),
                close=round(kurs, 4),
                volume=float(wuerfel.randint(20_000, 200_000)),
            )
        )
    return bars


def erzeuge_reihe(
    seed: int, startkurs: float, drift: float, handelstage: int, erster_tag: date
) -> list[IntradayBar]:
    """Eine vollstaendige Reihe.

    ``drift`` ist der Anteil, um den der Kurs je Handelstag im Mittel
    zulegt oder nachgibt. Er trennt die Faelle voneinander: eine steigende
    Reihe loest andere Signalkombinationen aus als eine seitwaerts laufende.
    """
    wuerfel = random.Random(seed)
    kurs = startkurs
    bars: list[IntradayBar] = []
    for tag in _handelstage(erster_tag, handelstage):
        bars.extend(_bars_eines_tages(tag, kurs, wuerfel))
        kurs = bars[-1].close * (1.0 + drift)
    return bars


BEGINN_DER_LANGEN_REIHE = date(2021, 1, 4)
"""Die lange Reihe beginnt frueher als die kurze -- aus zwei Gruenden.

Sie endet damit **vor** ``pipeline.EVALUATED_AT`` statt Monate danach; eine
Historie, die in der Zukunft des Auswertungszeitpunkts liegt, beschriebe
nichts, was ein Lauf je zu sehen bekaeme.

Und ihr Anfang liegt vor der Fuenf-Jahres-Grenze dieses Zeitpunkts, sodass
``_truncate_to_recent_history`` tatsaechlich etwas abschneidet. Vorher tat es
das in keinem der Faelle -- ein Fehler dort waere unbemerkt geblieben.
"""

FAELLE = {
    "synthetic-trend": (20240102, 100.0, 0.0015, KURZE_REIHE, ERSTER_HANDELSTAG),
    "synthetic-range": (20240103, 50.0, 0.0, LANGE_REIHE, BEGINN_DER_LANGEN_REIHE),
}
"""Name der Datei -> (Startwert, Startkurs, Tagesdrift, Handelstage, erster Tag).

Zwei Reihen, weil eine allein nur einen Ausschnitt der Regeln beruehrt: Die
steigende erzeugt Ausbrueche und EMA-Kreuzungen, die seitwaerts laufende vor
allem RSI-Kreuzungen und lange Strecken ohne Kandidat -- und sie ist die
laengere, damit die Konfidenzstufe ``NORMAL`` ueberhaupt vorkommt.
"""


def main() -> None:
    for name, (seed, startkurs, drift, handelstage, erster_tag) in FAELLE.items():
        bars = erzeuge_reihe(seed, startkurs, drift, handelstage, erster_tag)
        pfad = DATA_DIR / f"{name}.bars.csv"
        write_bars(pfad, bars)
        print(f"{pfad.name}: {len(bars)} Bars")


if __name__ == "__main__":
    main()
