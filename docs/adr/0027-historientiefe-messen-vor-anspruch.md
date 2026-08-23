# ADR 0027: Historientiefe — messen, dann holen, was es gibt

- Status: Angenommen
- Datum: 2026-08-23

## Kontext

`config/default.yaml` verspricht in `backtesting.history_years: 5` eine
fünfjährige Historie. Geholt wird seit dem ersten Tag `history_duration: 1 Y`.
Jede Backtest-Kennzahl des Projekts steht damit real auf rund einem Jahr.

Der Widerspruch ist nicht neu.
[ADR 0014](0014-ibkr-produktivintegration-freigegeben.md) hat ihn unter E3
gesehen und einen eigenen Chunking-Batch für den 5-Jahres-Backfill
vorgesehen. Gebaut wurde er nie. Das Repository-Audit vom 2026-08-23 hat den
Punkt als offene Entscheidung E2 und als Risiko R1 („Backtest-Kennzahlen
suggerieren 5 Jahre, Basis ist ~1 Jahr") wieder aufgenommen.

Entscheidend ist dabei eine Lücke, die keines der bestehenden Dokumente
schließt: **Ob fünf Jahre in 15-Minuten-Auflösung bei IBKR überhaupt zu
bekommen sind, ist unbelegt.** Der IBKR-Spike
(`spikes/ibkr-marketdata/REPORT.md`) hat für Intraday-Bars grob zwei Jahre
beobachtet, aber nicht systematisch bis an die Grenze gemessen. Die
Zahl `5` in der Konfiguration ist damit weder gemessen noch von IBKR
zugesagt — sie ist eine aus Doc 02 und Doc 07 übernommene Erwartung.

Die drei Wege, die das Audit unter E2 gegenübergestellt hat:

- **(a)** Batch bauen, die maximal verfügbare Tiefe holen und ehrlich
  ausweisen, was ankam.
- **(b)** `history_years` auf die reale Tiefe senken und die Dokumentation
  anpassen.
- **(c)** 195-Minuten-Kerzen für ältere Zeiträume aus gröberen Bars bilden —
  eine Verfahrensänderung mit neuer Versionsnummer.

## Entscheidung

### 1. Weg (a): so tief, wie der Anbieter hergibt

Verfolgt wird Weg **(a)**. Die Historie wird so weit geholt, wie IBKR sie in
der konfigurierten Bar-Größe herausgibt, und das Ergebnis wird als das
ausgewiesen, was es ist.

Weg (c) ist damit ausgeschlossen: Aus gröberen Bars gebildete
195-Minuten-Kerzen wären andere Kerzen als die des laufenden Betriebs. Ein
Backtest über zwei verschiedene Kerzenverfahren misst zwei verschiedene
Strategien und verrechnet sie zu einer Zahl — genau die Sorte stiller
Vermischung, die dieses Projekt an anderer Stelle ausdrücklich untersagt.

Weg (b) ist keine Alternative, sondern eine **mögliche Folge** von (a): Zeigt
die Messung, dass fünf Jahre nicht erreichbar sind, wird `history_years` auf
die gemessene Tiefe gesenkt. Das ist dann keine Absenkung des Anspruchs,
sondern das Ende einer unbelegten Behauptung.

### 2. Gemessen wird vor dem Holen

Der erste Schritt ist eine Messung, kein Backfill. Sie beantwortet für
zwei bis drei Titel eine einzige Frage: Wie alt ist der älteste Bar, den
IBKR in 15-Minuten-Auflösung noch herausgibt?

Umgesetzt als `cli history-depth`
(`application/measure_history_depth.py`). Das Kommando arbeitet sich Fenster
für Fenster rückwärts, bis der Anbieter nichts mehr liefert, und **legt dabei
nichts ab.** Ein nebenbei entstehender Bestand hätte kein Zustandekommen, auf
das sich jemand berufen könnte, und der nächste reguläre Backfill sähe einen
jüngsten Bar, der ihn glauben ließe, alles dazwischen sei geholt.

### 3. Eine abgebrochene Messung ist keine gemessene Tiefe

Der Bericht nennt zu jedem Symbol, **woran** die Messung geendet hat:

| Grenze | Bedeutung |
|---|---|
| `provider_exhausted` | IBKR gab nichts mehr her — die gesuchte Tiefe |
| `no_progress` | IBKR antwortete, kam aber nicht weiter zurück |
| `window_limit` | eigene Reißleine — die Tiefe ist eine **Untergrenze** |
| `error` | Abruf gescheitert — die Tiefe ist eine **Untergrenze** |

Diese Unterscheidung ist der Kern der Entscheidung. Ohne sie ließe sich eine
an der eigenen Obergrenze abgebrochene Messung als „fünf Jahre erreicht"
lesen — dieselbe Sorte Fehlschluss, die das Projekt bei
`INSUFFICIENT_DATA` und bei den Konfidenzstufen des Backtests bereits
ausschließt.

Maßgeblich für den Anspruch ist die **flachste gemessene** Aktie, nicht die
tiefste: Sie bestimmt, ab wann eine Kennzahl über die Watchlist hinweg
vergleichbar ist.

Eine Aktie, für die kein einziger Bar ankam, zählt dabei **nicht** als
flachste Historie — über ihre Tiefe ist nichts bekannt, und eine unbekannte
Tiefe ist keine kurze. Sie wird gesondert ausgewiesen, und solange eine
solche Aktie im Lauf steht, sagt der Bericht ausdrücklich, dass sein Urteil
nur für die gemessenen Titel gilt. Ohne diese Trennung stützte ein Symbol,
das IBKR gar nicht liefert, ein Urteil über die Watchlist, an dem es nicht
beteiligt war.

### 4. Was aus dem Messergebnis folgt, steht in einem eigenen ADR

Dieses ADR entscheidet den Weg, nicht die Zahl. Sobald die Messung auf dem
Server gelaufen ist, wird in einem Nachfolge-ADR festgehalten:

- die gemessene Tiefe je Titel samt Grenze,
- der daraus gesetzte Wert für `backtesting.history_years`,
- ob der vertiefende Backfill-Batch gebaut wird und mit welcher
  Fenstergröße.

Bis dahin bleibt `history_years: 5` unverändert stehen — nicht weil die Zahl
belegt wäre, sondern weil sie durch eine andere unbelegte Zahl zu ersetzen
nichts gewönne. **Die Messung ist die Voraussetzung, nicht die Schätzung.**

## Begründung

Weg (a) mit vorangestellter Messung ist der einzige, der ohne Annahme
auskommt. (b) sofort zu wählen hieße, `history_years` auf eine Zahl zu
setzen, die ebenfalls niemand gemessen hat — der Fehler bliebe derselbe, nur
in kleinerer Ziffer. (c) verletzt die Trennung der Verfahren.

Dass die Messung nichts speichert, kostet später einen zweiten Durchlauf für
dieselben Zeiträume. Das ist unter dem Pacing-Limit von 60 Anfragen je zehn
Minuten für zwei bis drei Titel eine Sache von Minuten und wiegt leichter als
ein Bestand, dessen Herkunft in keiner Entscheidung steht.

Ein eigener Port (`HistoricalBarWindowSource`) statt eines weiteren Parameters
an `HistoricalBarSource`: Der Bestand als Quelle (`StoredBarSource`) kann die
Frage nach der Anbietertiefe nicht beantworten — er weiß nur, was schon
geholt wurde. Ein gemeinsamer Parameter hätte ihn gezwungen, eine Antwort zu
erfinden.

## Konsequenzen

- Der Widerspruch aus R1 ist damit **noch nicht behoben.** Bis das
  Nachfolge-ADR vorliegt, stehen die Backtest-Kennzahlen weiterhin auf rund
  einem Jahr, während die Konfiguration fünf verspricht. Wer sie liest, muss
  `history_start`/`history_end` am Ergebnis lesen — sie stehen dort.
- Die Messung braucht die TWS und läuft deshalb nur auf dem Windows-Server
  (siehe Doc 14, „Historientiefe messen").
- Erreicht IBKR die fünf Jahre nicht, sind Doc 02 und Doc 07 an der Stelle
  anzupassen, an der sie fünf Jahre versprechen. Das gehört ins
  Nachfolge-ADR.
- `cli history-depth` bleibt danach als Betriebswerkzeug bestehen: Die Tiefe
  eines Anbieters ist nichts, was einmal feststeht.
- E1 (Backtesting im Tageslauf) und E3 (historische Earnings-Termine) hängen
  laut Audit an dieser Entscheidung. Sie sind mit diesem ADR nicht
  entschieden.
