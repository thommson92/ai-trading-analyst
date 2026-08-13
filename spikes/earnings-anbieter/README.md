# Earnings-Anbieter: Sonde

Beantwortet die fachlichen Fragen aus der
[Anbieterevaluation](../../docs/requirements/earnings-anbieter-evaluation.md),
nachdem IBKR als Research-Quelle ausgeschieden ist
([ADR 0016](../../docs/adr/0016-ibkr-keine-quelle-fuer-research-daten.md)).

Erster Kandidat ist **Finnhub** — der einzige geprüfte Anbieter, dessen
Gratis-Stufe den Earnings-Kalender überhaupt enthält.

## Was geprüft wird

| # | Frage |
|---|---|
| P4 | Wie weit reicht der Vorlauf in der Gratis-Stufe? |
| P5 | Sind die Termine als **bestätigt oder geschätzt** gekennzeichnet? |
| P6 | Wie viele Titel der eigenen Watchlist sind abgedeckt? |
| P8 | Steht dabei, ob vor oder nach Börsenschluss gemeldet wird? |

P5 ist die wichtigste. Ein geschätzter Termin, der als bestätigt behandelt
wird, wäre genau der erfundene Wert, den Doc 10 ausschließt. Die Sonde meldet
das Fehlen einer solchen Kennzeichnung deshalb ausdrücklich als **Befund**,
nicht als Leerstelle.

P7 — Ratings und Kursziele beim selben Anbieter — beantwortet die zweite
Sonde `probe_finnhub_ratings.py`, weil es andere Endpunkte betrifft.

## Ausführen

Kostenlosen Schlüssel unter <https://finnhub.io/register> anlegen. Der
Schlüssel wird **ausschließlich** aus der Umgebungsvariablen gelesen — nie
als Argument, nie im Code, nie in der Ausgabe (Projektregel: Geheimnisse nur
über `ATA_`-Variablen; ein Argument stünde in der Shell-Historie).

```bash
export ATA_FINNHUB_API_KEY="..."
backend/.venv/bin/python spikes/earnings-anbieter/probe_finnhub.py
```

Läuft von jedem Rechner — anders als die TWS-Sonden braucht das hier keinen
Windows-Server, nur einen Internetzugang.

Der Abruf kostet **eine einzige Anfrage** für den gesamten Zeitraum,
unabhängig von der Zahl der Symbole. Genau deshalb ist das Anfragekontingent
hier nicht die bindende Grenze.

Die Antwort landet unversioniert unter `results/` und lässt sich ohne
erneuten Abruf auswerten:

```bash
python probe_finnhub.py --from-file results/finnhub_2026-08-13.json
```

## Tests

```bash
backend/.venv/bin/python -m pytest spikes/earnings-anbieter/tests
```

## Status: beantwortet (2026-08-13)

Alle Fragen sind gelaufen; die Ergebnisse stehen in der
[Anbieterevaluation](../../docs/requirements/earnings-anbieter-evaluation.md)
und die Entscheidung in
[ADR 0017](../../docs/adr/0017-finnhub-fuer-earnings-und-ratings.md).

Die Sonden bleiben erhalten und werden **nicht eingefroren**: Sie sind der
Weg, eine Aussage nachzuprüfen, wenn Finnhub sein Angebot ändert. Ihre Tests
laufen in der CI mit.
