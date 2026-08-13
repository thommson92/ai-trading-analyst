# RESC-Inhaltsprüfung

Eine einzelne offene Frage, klar abgegrenzt.

## Warum

Der IBKR-Spike hat belegt, dass `reqFundamentalData(reportType='RESC')` einen
substantiellen Datensatz liefert — 325 KB XML für AAPL, live bestätigt. Was
darin steht, wurde nicht geprüft. Deshalb steht in der
[ADR-Übersicht](../../docs/adr/README.md) bis heute als offen:

> Anbieter für Analystenratings und Kursziele (F9) — IBKR liefert über
> `reqFundamentalData(reportType='RESC')` einen substantiellen
> Analystenschätzungen-Datensatz; Inhalt/Schema wurde im Spike nicht im
> Detail geprüft.

Die Frage hat zwei Konsequenzen, und die zweite ist die interessantere:

1. **Analystenratings und Kursziele (F9).** Deckt RESC sie ab, braucht es
   dafür keinen zweiten Anbieter.
2. **Earnings-Termine.** [ADR 0014](../../docs/adr/0014-ibkr-produktivintegration-freigegeben.md)
   führt unter E1, dass IBKR keine Earnings-Termine liefert — belegt für
   `CalendarReport`, nicht für `RESC`. Analystenschätzungen enthalten
   üblicherweise den erwarteten Berichtstermin, denn ohne ihn ist eine
   Schätzung für ein Quartal nicht einzuordnen. Trifft das hier zu,
   schrumpft der Earnings-Workstream erheblich oder entfällt.

Deshalb steht diese Prüfung **vor** der Anbieterauswahl. Sonst evaluieren wir
möglicherweise Anbieter für Daten, die bereits vorliegen.

## Was die Sonde ausgibt — und was nicht

Die Sonde unterscheidet zwei Arten von Angaben, und die Grenze verläuft
zwischen **Schema** und **Inhalt**:

| Ausgabe | Was erscheint | Beispiel |
|---|---|---|
| `@type = EPS \| REV` | Attribute aus `SCHEMA_ATTRIBUTES` — sie sagen, *welche* Kennzahlen es gibt | `type`, `periodType`, `code`, `unit`, `dateType`, `desc` |
| `@updated ~ 9999-99-99` | alle übrigen Attribute, nur als Wertform | `updated`, `endCalYear`, `ticker` |
| `Wertform: 9.99` | Elementtexte, nur als Wertform | Schätzwerte, Namen, Kurse |

Dass ein Feld `type="PRICE_TGT"` heißt, ist die Antwort auf unsere Frage und
keine Analystenaussage. Der Wert `350` dagegen ist genau die lizenzgebundene
Aussage — er erscheint als `999`. Ein Test hält fest, dass kein
Originalinhalt durchrutscht.

Zwei Gründe für diese Trennung: Die Daten stammen von einem Drittanbieter
und sind lizenzgebunden, und eine Antwort kann Kennungen enthalten, die
nicht in ein Protokoll gehören. Für die Frage „gibt es ein Feld mit dem
Berichtstermin" genügt die Struktur vollständig.

Das komplette XML landet unter `results/` und ist **nicht versioniert**, damit
gezielte Rückfragen ohne einen zweiten TWS-Abruf beantwortet werden können.

## Ausführen

Auf dem Windows-Server, aus `backend/` heraus — dessen venv enthält `ib_async`
bereits, ein eigenes Setup ist nicht nötig:

```powershell
.venv\Scripts\python.exe ..\spikes\resc-schema\probe_resc.py AAPL
```

Client-ID 18: nicht die des Analyzers (17) und nicht die der Trade Automation
Toolbox (99) — eine doppelt vergebene ID wirft die bestehende Verbindung aus
der TWS.

Ein zweites Symbol lohnt sich, um Zufälligkeiten auszuschließen. Sinnvoll ist
eine Aktie mit anderem Berichtsrhythmus, etwa `MSFT` oder `WMT`.

Ohne TWS lässt sich eine gespeicherte Antwort erneut auswerten:

```bash
python probe_resc.py AAPL --from-file results/AAPL_resc.xml
```

## Tests

```bash
backend/.venv/bin/python -m pytest spikes/resc-schema/tests
```

Geprüft sind die reinen Auswertungsfunktionen — insbesondere, dass die
Zusammenfassung die Struktur vollständig zeigt und dabei keinen Inhalt
durchlässt. Der TWS-Abruf braucht eine laufende TWS und ist nicht Gegenstand
der Tests.

## Status: beantwortet (2026-08-12)

Siehe **[RESULT.md](RESULT.md)**. Kurz:

- **Ratings und Kursziele liegen vor** (`TARGETPRICE`, `BUY`…`SELL` mit
  Analystenzahl) — ein eigener Anbieter dafür entfällt. Nicht jedes Symbol
  hat Empfehlungen; bei `WMT` ist der Block leer.
- **Berichtstermine liegen nicht vor.** Einschränkung E1 aus ADR 0014 bleibt
  gültig, der Earnings-Workstream bleibt nötig.

Ein ADR wird durch diesen Spike **nicht** geändert; die Folgerungen gehören
in ein neues ADR zur F9-Datenquelle, einschließlich der noch offenen
Lizenzfrage.
