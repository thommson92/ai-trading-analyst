# ADR 0038: Backtest je Kandidat im Tageslauf, Earnings-Abweichung gekennzeichnet

- Status: Angenommen
- Datum: 2026-08-30

## Kontext

Doc 10 §7 sieht die historische Signalprüfung je Kandidat vor. Gebaut ist sie
seit Sprint 3, aber sie hängt nicht am Tageslauf: `cli backtest` rechnet auf
Zuruf über die volle Watchliste, und niemand liest die Ergebnisse
automatisiert. Das Audit vom 2026-08-23 führt das als **E1** mit Priorität
HOCH.

Zwei Dinge haben sich seitdem geändert.

**Die Datengrundlage steht.** E1 war laut Audit an E2 gebunden — die
Historientiefe. Die ist gemessen und geholt:
[ADR 0028](0028-historientiefe-gemessen.md) belegt mindestens 17,4 Jahre
verfügbare Tiefe, der Tiefen-Backfill lief am 2026-08-24, und der Backtest
erreicht damit `NORMAL`-Konfidenz bei n=44–60 statt der vorherigen
Ein-Jahres-Basis.

**Der Bericht braucht sie.** Punkt 5 des Mindestinhalts aus Doc 10 §6.12 ist
die „historische Signalstatistik". Ohne Backtest im Lauf hätte der Report
Generator dort entweder eine Lücke oder eine Zahl aus einem ganz anderen
Zeitpunkt.

Offen bleibt daneben **E3** beziehungsweise Risiko **R6**: Der Backtest zählt
Ereignisse, die der Live-Filter wegen eines nahen Earnings-Termins
ausgeschlossen hätte. Historische Termine gibt es nicht — ADR 0017 hält das
als Einschränkung L9 fest. Die Kennzahlen messen damit eine leicht andere
Strategie als die gehandelte.

## Entscheidung

### 1. Der Backtest läuft für jeden Kandidaten im Tageslauf

Er rechnet in Phase 1 von `RunAnalysisUseCase`, direkt hinter der
deterministischen Chartauswertung, **auf derselben bereits geladenen
Kerzenreihe**. Kein zusätzlicher Abruf beim Marktdatenanbieter, keine neue
externe Abhängigkeit — `compute_backtest_results` ist eine reine
Domain-Funktion.

Wie die Chartauswertung läuft er **vor** dem Earnings-Filter und unabhängig
von dessen Ergebnis: Er hängt an keiner externen Quelle, und ihn hinter den
Filter zu hängen machte ihn ohne Not von einer abhängig, die ausfallen kann.

Ergebnisse gehen wie bisher nach `backtest_results`, jetzt mit dem
`analysis_run_id` des Laufs. Bei `cli backtest` bleibt die Spalte leer.

### 2. Fehlt die Historie, bleibt der Backtest leer — der Lauf nicht

`compute_backtest_results` bricht ab, wenn im Betrachtungsfenster keine
einzige Kerze liegt. Dieser eine, dokumentierte Fall wird abgefangen,
protokolliert und führt zu **keinem** Backtest-Ergebnis; der Bericht weist
Punkt 5 dann als Lücke aus. Jeder andere Fehler schlägt in die
Fehlerisolation je Aktie durch — er wäre ein Programmfehler und soll
auffallen.

### 3. Die Earnings-Abweichung steht am Ergebnis

`BacktestResult` bekommt `earnings_exclusion_applied: bool`, heute
durchgehend `False`. Der Bericht führt die Abweichung bei Punkt 5 mit auf.

**E3 wird damit nicht entschieden**, sondern sichtbar gemacht. Ein
EDGAR-Adapter für historische `8-K`-Termine bleibt der vorgemerkte Weg, vor
Sprint 5, wenn das Scoring die Zahl erstmals wirklich braucht.

## Begründung

**Zu 1.** Die Alternative aus dem Audit — ein separater nächtlicher Batch —
entkoppelt zwar, kostet aber einen zweiten Eintrag in der Aufgabenplanung und
liefert Zahlen aus einem anderen Zeitpunkt als der Lauf, der sie zitiert. Der
Bericht müsste dann zwei Stichtage führen und erklären. Im Tageslauf steht die
Statistik auf **derselben Kerze** wie Screening, Chartauswertung und
Bewertung.

Der Preis ist gering. Die Kerzenreihe ist bereits geladen, der Backtest
rechnet ohne Netz, und er läuft nur für Kandidaten — nicht für alle 192
Titel der Watchliste. Das Audit veranschlagt Sekunden; das deckt sich mit dem
Zuschnitt.

Die dritte Option — bis Sprint 5 warten — war richtig, solange niemand die
Ergebnisse las. Mit dem Report Generator liest sie jemand.

**Zu 3.** Die Abweichung zu verschweigen wäre der bequeme Weg: Sie ist klein,
und niemand fragt danach. Aber der Bericht behauptete dann eine
Trefferquote für eine Strategie, die so nicht gehandelt wird. Ein Feld am
Ergebnis kostet nichts und macht aus einer unbekannten Ungenauigkeit eine
bekannte.

Ein Feld, das heute immer `False` ist, sieht nach Vorratshaltung aus. Es ist
aber das Gegenteil: Sobald E3 entschieden ist, sagen die alten Zeilen
weiterhin die Wahrheit über sich selbst, statt rückwirkend so auszusehen, als
wären sie gefiltert worden.

## Konsequenzen

**Positiv**

- Berichtspunkt 5 hat eine Grundlage, die zum selben Lauf gehört.
- Das Scoring in Sprint 5 findet die „historische Signalqualität" je
  Kandidat vor, ohne dass jemand einen Befehl von Hand anstößt.
- E1 und M4 aus dem Audit vom 2026-08-23 sind erledigt.
- R6 bleibt offen, ist aber nicht mehr unsichtbar.

**Negativ und offen**

- **Der Lauf wird länger.** Der Replay geht über bis zu fünf Jahre Kerzen je
  Kandidat. Gemessen ist das auf dem Entwicklungsrechner, nicht auf dem
  Server; der erste produktive Lauf zeigt den echten Wert.
- **Mehr Zeilen in `backtest_results`.** Vier Signalkombinationen mal drei
  Horizonte sind zwölf Zeilen je Kandidat und Lauf. Die Tabelle wächst
  linear mit den Kandidaten, nicht mit der Watchliste.
- **Dieselbe Aktie bekommt an aufeinanderfolgenden Tagen fast gleiche
  Zeilen.** Das ist gewollt — abgeschlossene Analysen werden nicht
  überschrieben —, aber es ist Redundanz.
- **R6 besteht fort.** Die Trefferquoten bleiben die einer ungefilterten
  Strategie, bis E3 entschieden ist.
- **Der Backtest sieht die Kerzenreihe, die der Anbieter gerade liefert.**
  Bei `--source stored` ist das der Bestand, bei einem Direktabruf das, was
  die TWS hergibt. `history_start`/`history_end` stehen am Ergebnis; wer sie
  ignoriert, vergleicht Zahlen unterschiedlicher Tiefe.
