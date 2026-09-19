# ADR 0068: Der Export rechnet abgeschlossene Läufe nicht jeden Tag neu

- Status: Vorgeschlagen
- Datum: 2026-09-20

## Kontext

Der Dashboard-Export läuft seit dem 2026-09-18 im Tageslauf. Am ersten
produktiven Tag kostete er **42,7 Minuten**; der Gesamtlauf stieg damit von
rund 53 auf **103 Minuten** (gemessen über `scripts/laufzeiten.py`, siehe
Doc 14 „Wo die Zeit eines Laufs bleibt").

Das ist deutlich mehr als die 784 Sekunden, die Doc 14 Stufe K Schritt 4 für
das bloße Schreiben gemessen hatte. Der Unterschied liegt nicht am Schreiben,
sondern am Rechnen — und zwar an einem Anteil, der **mit jedem Handelstag
wächst**:

`presentation/export/snapshot.py` baut bei jedem Export

- **jeden je gelaufenen Analyse-Lauf** neu (`_alle_laeufe`, dann je Lauf ein
  `ReadRunOverviewUseCase.execute`),
- **je Lauf die Kurzliste** seiner Berichte,
- und **je historischem Bericht eine eigene Abfrage** (`stock_reports.get`).

Der Verzeichnisschreiber ist bereits inkrementell, aber nur beim *Schreiben*:
Er bildet die Prüfsumme des fertigen Klartexts und schreibt nur, was sich
geändert hat. Doc 14 sagt das ausdrücklich — „‚Nur Änderungen' bezieht sich
auf das Schreiben, nicht auf das Rechnen". Um die Prüfsumme zu bilden, muss
der Inhalt aber erst entstehen. Gespart werden Schreibvorgänge und Übertragung,
keine Rechenzeit.

Die Zahlen wachsen weiter: Jeder Handelstag fügt einen Lauf und ein bis
vierzig Berichte hinzu, und jeder davon wird ab dann jeden Abend erneut
gerechnet.

## Entscheidung

### 1. Drei Pfadfamilien gelten als unveränderlich

| Pfad | Inhalt | Warum unveränderlich |
|---|---|---|
| `data/reports/{id}.json` | das gespeicherte Berichtsdokument, unverändert | ADR 0039; abgeschlossene Analysen werden nie überschrieben (CLAUDE.md) |
| `data/analysis-runs/{id}.json` | die Laufansicht | leitet sich allein aus den Zeilen dieses Laufs und **früherer** Läufe ab |
| `data/analysis-runs/{id}/reports.json` | die Kurzliste des Laufs | die Berichte eines Laufs entstehen während dieses Laufs |

Der Sperrstatus in der Laufansicht (ADR 0062) ist dabei der einzige Punkt,
der überhaupt außerhalb des Laufs schaut — und er schaut ausschließlich
zurück: `_gesperrte` rechnet mit dem Fenster bis zum **Startzeitpunkt des
Laufs**. Ein späterer Lauf kann die Ansicht eines früheren nicht ändern.

**Alles andere wird weiterhin jedes Mal gebaut**: die Chartdateien (neue
Kerzen), `analysis-runs.json`, `stocks.json`, `signal-backtests.json`, die
Optionsmessungen und die Listen je Aktie. Sie ändern sich täglich, und eine
Zwischenspeicherung wäre dort Aufwand ohne Ertrag.

### 2. Der Exportzustand merkt sich, unter welcher Fassung eine Datei entstand

`Dateizustand` bekommt neben `hash` und `ziel` ein Feld `fassung`. Übersprungen
wird eine Datei genau dann, wenn **alle drei** Bedingungen gelten:

1. Der Pfad steht im bekannten Stand,
2. seine Fassung ist die heutige,
3. die Zieldatei liegt tatsächlich noch da.

Die Prüfsumme für das Manifest kommt dann aus dem Zustand statt aus dem
Inhalt. Sie ist dieselbe — das ist der ganze Punkt.

Ein Zustand ohne `fassung` (aus der Zeit vor diesem ADR) zählt als unbekannt:
Der erste Export danach rechnet einmal alles neu und trägt die Fassung nach.

### 3. Die Fassung wird abgeleitet, nicht gepflegt

`EXPORT_FASSUNG` ist die Prüfsumme über

- das JSON-Schema der beteiligten Antwortmodelle (`AnalysisRunDetailResponse`,
  die Kurzlisteneinträge),
- `REPORT_SCHEMA_VERSION`,
- und ein **von Hand gesetztes Salz** `_FASSUNG_SALZ`.

Die ersten beiden ändern sich von selbst, sobald sich die *Form* einer
exportierten Datei ändert — daran muss niemand denken. Das Salz deckt den
Rest: eine geänderte *Rechnung* bei gleicher Form, etwa eine Korrektur an
`_gesperrte`.

### 4. `publish --full` bleibt die Notbremse und umgeht alles

Der Schalter verwirft den bekannten Stand bereits heute
(`publisher.schreibe_baum`, `zustand.dateien.clear()`). Damit entfällt
zugleich jede Fassungsangabe, und jede Datei entsteht neu. Wer zweifelt,
ob draußen steht, was hier liegt, hat weiterhin genau einen Befehl dafür.

## Begründung

**Zu 1.** Die Unveränderlichkeit ist keine neue Annahme, sondern eine
bestehende Zusicherung des Systems: „Abgeschlossene Analysen werden nicht
überschrieben. Eine Neuberechnung erzeugt eine neue Version mit Referenz auf
das Original." Eine Datei, die aus unveränderlichen Zeilen entsteht, jeden
Abend neu zu rechnen, ist Arbeit ohne möglichen Unterschied im Ergebnis.

Die Alternative — den Export in einen eigenen Vorgang auszulagern — verlagert
die Zeit nur und macht sie nicht kleiner; das Dashboard stünde außerdem
zeitweise auf einem anderen Stand als die Meldung, die auf es verweist.

**Zu 2.** Die Zwischenspeicherung sitzt im Exportzustand und nicht in einer
neuen Ablage: Dort steht bereits, was der letzte Export erzeugt hat, samt
Prüfsumme und Zielnamen. Eine zweite Ablage daneben müsste mit dieser
konsistent gehalten werden, und zwei Zustände, die auseinanderlaufen können,
sind schlechter als einer.

Die dritte Bedingung — die Zieldatei liegt noch da — ist nicht überflüssig:
Der Zustand behauptet etwas über ein Verzeichnis, das er nicht kontrolliert.
Genau deshalb gibt es `--full`.

**Zu 3.** Eine Fassungsnummer, an die jemand denken muss, wird irgendwann
vergessen — und der Fehler wäre still: Das Dashboard zeigte für die Historie
das alte Format und für heute das neue. Das Schema der Antwortmodelle zu
hashen macht den häufigsten Fall selbsttragend. Das Salz bleibt trotzdem, weil
eine geänderte Rechnung bei gleicher Form nicht erkennbar ist; **dieser Rest
ist eine bewusst in Kauf genommene Lücke**, und `--full` ist ihr Gegenmittel.

## Konsequenzen

**Positiv**

- Der Anteil des Exports, der mit jedem Handelstag wächst, wächst nicht mehr.
  Was bleibt, hängt an der Zahl der Aktien, nicht an der Zahl der Tage.
- Der erste Export nach einer Schemaänderung rechnet von selbst alles neu.
- Die Ersparnis ist am Protokoll ablesbar: `export_zerlegung` weist
  `lauf_uebersicht`, `lauf_kurzliste` und `bericht` getrennt aus.

**Negativ und offen**

- **Eine geänderte Rechnung bei unveränderter Form fällt nicht auf.** Wer
  `_gesperrte` oder die Übersetzung eines Berichts ändert, muss `_FASSUNG_SALZ`
  erhöhen oder einmal `publish --full` fahren. Das steht als Kommentar an der
  Konstante, nicht nur hier.
- **Der Zustand wird wichtiger.** Bisher kostete ein verlorener Zustand nur
  Schreibvorgänge, jetzt kostet er auch Rechenzeit. Teurer wird nichts, was
  nicht vorher auch teuer war — der Verlust führt zum heutigen Verhalten.
- **Die Ersparnis ist nicht gemessen, sondern hergeleitet.** Wieviel der
  42,7 Minuten auf die drei Pfadfamilien entfallen, sagt erst der erste Lauf
  mit der Zerlegung aus Doc 14. Dass es wächst, steht dagegen fest.
- Der Export trägt damit eine zweite Art von Inkrementalität. Die erste
  betrifft das Schreiben, die zweite das Rechnen; sie sind unabhängig, und
  beide hängen am selben Zustand.
