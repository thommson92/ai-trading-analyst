# ADR 0039: Report Generator — achtzehn Punkte, Lücken benannt, ohne Sprachmodell

- Status: Angenommen
- Datum: 2026-08-30

## Kontext

Der Report Generator ist der letzte offene Punkt aus Sprint 4 und in der
Roadmap der einzige ohne jede Erläuterung — er wurde nie begonnen. Fünf
Analysemodule liefern strukturierte Ergebnisse, die nirgends zusammenlaufen.

Der Bestand vor dieser Entscheidung:

- kein `domain/report/`-Paket, kein `ReportGenerator`-Port,
- **keine `report_schema_version`** — Doc 10 §8 verlangt sie seit jeher, und
  [ADR 0026](0026-technical-agent-ki-einordnung.md) hat sie ausdrücklich
  hierher verwiesen, „damit sie nicht übersehen wird",
- kein JSON-Ausgabeweg im ganzen System,
- ein Modellprofil `llm.report` in `config/default.yaml`, das keine Codestelle
  liest.

Doc 10 §6.12 gibt achtzehn Pflichtpunkte vor. Vier davon — Put-Strategien,
Swing Score, Long-Term Investment Score und die daraus folgende Empfehlung —
stehen auf Optionsanalyse und Scoring, und beide gehören zu Sprint 5.

## Entscheidung

### 1. Der Bericht führt alle achtzehn Punkte

Auch die vier, die er heute nicht füllen kann. Sie erscheinen als Abschnitt
mit `verfuegbar: false` und einer Begründung, nicht als fehlender Schlüssel.

Punkt 17 („Konfidenz und Datenlücken") zählt sie auf. Dabei wird
unterschieden zwischen `FEHLT` — der Punkt hat keinen Inhalt — und
`EINGESCHRAENKT` — er hat einen, aber unter Vorbehalt. Eine Trefferquote, die
ungefilterte Ereignisse zählt ([ADR 0038](0038-backtest-im-tageslauf.md)),
fehlt nicht; sie gilt nur eingeschränkt.

Es gibt **keine Gesamtkonfidenz.** Die drei vorhandenen Zahlen messen
Verschiedenes: Belegdichte der Recherche, Sicherheit der KI-Einordnung, Anteil
gerechneter Fundamentalkennzahlen. Sie zu einer zu verrechnen ergäbe eine
Zahl, die nichts bedeutet.

### 2. Der Bericht ist deterministisch — vorerst ohne Sprachmodell

Er ordnet gespeicherte Ergebnisse zu und trägt ein, was fehlt. Das Feld
`summary` bleibt leer: Ein deterministisch zusammengesetzter Satz wäre eine
Formulierung ohne Verfasser.

Die KI-Formulierung folgt als eigenes Feature nach dem Muster von ADR 0026 —
getrennt gespeichert, gegen ein Schema validiert, ausschließlich einordnend.
`llm.report` bleibt bis dahin ungenutzt.

### 3. Drei Varianten

| Variante | Form |
|---|---|
| maschinenlesbar | JSON-Dokument, in der Datenbank gespeichert — die **verbindliche** Fassung |
| vollständig lesbar | `cli report`, Text auf der Konsole |
| kompakt | Telegram-Kurzfassung, siehe [ADR 0040](0040-inhalt-der-ergebnismeldung.md) |

Der Dashboard-Bericht und der Dateiexport aus Doc 10 §6.12 entstehen nicht:
Es gibt kein Dashboard (Sprint 6), und den Export nennt Doc 10 selbst als
spätere Phase.

Die anderen beiden Fassungen entstehen **aus** dem Dokument, nicht neben ihm.

### 4. Das Dokument wird gespeichert, nicht bei Bedarf neu gerechnet

Eigene Tabelle `stock_reports`, ein Datensatz je Lauf und Aktie, nie
überschrieben. Sie trägt `report_schema_version`, `app_version` und —
vorerst leer — `scoring_version`, `recommendation`, `swing_score`,
`investment_score` und `summary`.

Der Name weicht von Doc 05 (`StockAnalysis`) ab, weil „Analysis" im Schema
bereits mit `analysis_runs` belegt ist. Gemeint ist dieselbe Entität.

### 5. Der Unternehmensname kommt aus dem SEC-Symbolverzeichnis

`company_tickers.json` führt zu jedem Ticker den amtlichen Namen, und der
Fundamentaldaten-Adapter lädt die Datei ohnehin zur CIK-Auflösung. Fehlt der
Registrant, bleibt der Name leer und Punkt 1 ist eine Lücke.

## Begründung

**Zu 1.** Die Alternative wäre, heute nur zu führen, was gefüllt werden kann,
und das Schema mit Sprint 5 zu heben. Das sähe ordentlicher aus und wäre
irreführend: Ein Leser, der vierzehn Punkte sieht, hält sie für den ganzen
Bericht. Vierzehn Punkte plus vier ausdrückliche Lücken sagen ihm, dass die
Analyse unvollständig ist — und warum. Das ist dieselbe Regel, nach der eine
fehlende Fundamentalkennzahl fehlend bleibt, statt geschätzt zu werden.

Nebenbei bleibt das Schema stabil: Sprint 5 füllt Lücken, statt Felder
hinzuzufügen. `report-v1` steigt dadurch nicht.

**Zu 2.** Dasselbe Muster wie beim Technical Agent (ADR 0025 dann 0026) und
bei der Fundamentalanalyse (ADR 0032, KI-Hälfte offen): erst die
deterministische Hälfte, dann die Einordnung, getrennt gespeichert. Es hat
sich zweimal bewährt — beide Male hat die deterministische Hälfte Fehler
sichtbar gemacht, die eine gleichzeitig gebaute KI-Schicht verdeckt hätte.

**Zu 4.** Ein Bericht, der bei jedem Abruf neu entsteht, ändert sich still mit
jeder Codeänderung. Doc 10 §8 verlangt das Gegenteil: Abgeschlossene
Analyseberichte werden nicht überschrieben. Das Dokument zu speichern
verdoppelt Daten, die auch in `screening_results` stehen — und genau diese
Verdopplung ist die Zusicherung.

## Konsequenzen

**Positiv**

- Sprint 4 ist abgeschlossen; ein Lauf produziert ein vorzeigbares Ergebnis
  statt Konsolenzeilen.
- Die Berichtsschema-Version existiert, ein halbes Jahr nachdem Doc 10 sie
  gefordert hat.
- Es gibt erstmals einen maschinenlesbaren Ausgabeweg. Das Dashboard in
  Sprint 6 rendert das Dokument, statt die Zusammenstellung zu wiederholen.
- Was fehlt, steht im Bericht. Nach dem ersten echten Lauf ist ablesbar,
  welche Punkte regelmäßig leer bleiben — eine Meßgröße, die es vorher nicht
  gab.

**Negativ und offen**

- **Der Bericht liest sich noch nicht wie ein Bericht.** Ohne die KI-Hälfte
  ist die Konsolenfassung eine geordnete Aufstellung, kein Text.
- **Vier von achtzehn Punkten sind heute immer leer.** Bei jedem Kandidaten,
  in jedem Lauf. Das ist ehrlich, aber es sieht nach mehr Lücke aus, als das
  System tatsächlich hat.
- **Das Dokument verdoppelt gespeicherte Daten.** Gewollt (siehe oben), aber
  `stock_reports` wächst schneller als jede andere Tabelle: ein JSONB je
  Kandidat und Lauf.
- **Die Umwandlung in reine Daten läuft generisch** über die
  Dataclass-Felder, nicht über handgeschriebene Feldlisten. Ein neues Feld an
  einem Teilergebnis erscheint damit automatisch im Bericht — gewollt, aber
  es heißt auch, dass niemand es ausdrücklich freigibt.
- **Der Unternehmensname fehlt für jeden Nicht-SEC-Registranten**, und die
  Watchliste enthält solche Titel. Punkt 1 bleibt dort eine Lücke.
- **Berichte entstehen nur für Kandidaten.** Ein Lauf ohne Kandidaten
  hinterlässt einen Lauf ohne Berichte. Doc 10 §6.13 verlangt, dass auch er
  gespeichert wird — das tut `analysis_runs` bereits.
- **Keine Rückrechnung:** Läufe vor dieser Änderung bekommen keinen Bericht.
