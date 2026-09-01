# Die Datenreihen des Golden Master

Vier Fälle, **zwei verschiedener Herkunft.** Der Unterschied ist der Grund für
dieses Dokument.

| Fall | Herkunft | Bars |
|---|---|---|
| `synthetic-trend` | **erzeugt** — `../generate_bars.py` | 5.994 |
| `synthetic-range` | **erzeugt** — `../generate_bars.py` | 9.594 |
| `aapl` | **gemessen** — IBKR über den Server, 2026-09-01 | 10.794 |
| `msft` | **gemessen** — IBKR über den Server, 2026-09-01 | 10.794 |

## Die erzeugten Fälle

Ihr Modulkopf in `../generate_bars.py` sagt, warum sie erzeugt sind und was
daraus folgt. Kurz: Der reale Bestand lag zum Zeitpunkt ihrer Entstehung nur
auf dem Server, und ein Golden Master ohne Daten ist keiner. Sie prüfen die
Kette an einem Verlauf, dessen Eigenschaften bekannt sind — und genau das ist
zugleich ihre Grenze: Eine erzeugte Reihe kann nur bestätigen, was ihr
Erzeuger für möglich hielt.

## Die gemessenen Fälle

Echte 195-Minuten-Kerzen ab dem **2025-01-02** aus dem `intraday_bars`-Bestand
des Windows-Servers, gezogen am 2026-09-01 mit

```powershell
cli export-bars --symbols AAPL,MSFT --output tests\golden\data --since 2025-01-02
```

Das Kommando liest nur; der Bestand blieb unverändert. Ursprung der Bars ist
die IBKR-Historienschnittstelle (`reqHistoricalData`), gesammelt über die
Backfill-Läufe seit August 2026.

**Prüfsummen** — damit eine von Hand veränderte CSV auffällt. Die erzeugten
Fälle brauchen das nicht: Sie lassen sich aus `generate_bars.py`
reproduzieren, und ein Test tut das.

```
721dca3a06a3e2812d8f6283b669c9a7f2d12fd2abc0a1a3a03c59cec2462f4f  aapl.bars.csv
c604da93d4f0ec1d713843eb1211f90c893b70bec206d39e02c18b4f79d87cd3  msft.bars.csv
```

Nachprüfen: `shasum -a 256 aapl.bars.csv msft.bars.csv` (macOS/Linux),
`Get-FileHash aapl.bars.csv -Algorithm SHA256` (Windows).

## Zur Weitergabefrage bei den IBKR-Bars

Aufgeworfen von der unabhängigen Review am 2026-09-01: Für die eingefrorenen
Finnhub-Antworten ist die Frage ausdrücklich durchgespielt
([ADR 0017](../../../../../docs/adr/0017-finnhub-fuer-earnings-und-ratings.md)
L8 untersagt die Weitergabe an Dritte — siehe
`../../unit/infrastructure/finnhub/data/HERKUNFT.md`), für die um
Größenordnungen umfangreicheren Bars hier stand sie ungestellt.

**Entscheidung des Projektinhabers vom 2026-09-01: Die Bars bleiben.**
Begründung: eigene, über den eigenen Zugang bezogene Daten, ein kleiner
Ausschnitt zweier allgemein bekannter Titel, ausschließlich als
Testdatensatz.

Das ist eine Abwägung, keine juristische Prüfung — niemand hat IBKRs
Marktdatenvereinbarung daraufhin gelesen. Wer den Umfang hier ausweitet
(weitere Titel, längere Zeiträume, andere Datenarten), sollte das nicht als
Präzedenzfall nehmen, sondern die Frage neu stellen. Das Projekt hat mit
[ADR 0012](../../../../../docs/adr/0012-gate-g3-strang-a-no-go-non-display-nutzung.md)
schon einmal eine ganze Datenquelle an einer Nutzungsbedingung scheitern
lassen.
