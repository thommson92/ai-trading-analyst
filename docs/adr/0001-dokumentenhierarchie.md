# ADR 0001: Doc 10 ist bei Widersprüchen maßgeblich

- Status: Angenommen
- Datum: 2026-08-06

## Kontext

Die Fachdokumente in `docs/` sind zu unterschiedlichen Zeitpunkten und in
unterschiedlicher Tiefe entstanden. An mehreren Stellen widersprechen sie sich:

| Thema | Widerspruch |
|---|---|
| API-Pfade | Doc 11 nennt `/api/analyses`, Doc 10 §6.14 `/api/v1/analysis-runs` |
| Redis | Doc 13 führt Redis als Pflicht-Service, Doc 10 §3 nur bei nachgewiesenem Bedarf |
| Swing-Score | Doc 09 nennt fünf gewichtete Komponenten, Doc 10 §6.11 sechs ohne Gewichte |
| Earnings-Fenster | Doc 02 nennt „10–20 Kerzen", Doc 10 §6.5 macht daraus einen konfigurierbaren Wert |
| Datenmodell | Doc 05 ist deutlich flacher als die Anforderungen in Doc 10 §8 |
| Backtest-Einstieg | Doc 07 nennt den Close der Signalkerze |
| Analyse-Reihenfolge | Doc 10 §4 zeichnet `RESEARCH → TECH/FUND/OPTIONS` |

Ohne festgelegte Rangfolge müsste jeder Widerspruch einzeln neu diskutiert
werden — und zwar erfahrungsgemäß dann, wenn der Code schon geschrieben ist.

## Entscheidung

`docs/10 - System Architecture.md` ist bei Widersprüchen maßgeblich. Die
übrigen Dokumente werden nachgezogen, sobald der betroffene Sprint läuft.

Zwei Ausnahmen, in denen eine ausdrückliche Freigabe Doc 10 überstimmt:

1. **Backtest-Einstieg** (F4): Der Einstieg ist der Schlusskurs der Kerze, bei
   der die Qualifikationsregel erstmals erkannt wird — nicht der Close der
   Signalkerze aus Doc 07. Live wird erst nach Kerzenschluss gescreent, und die
   Regel erlaubt Signale bis zu fünf Kerzen rückwirkend; Doc 07 würde einen
   Preis unterstellen, den man real nie bekommen hätte.
2. **Analyse-Reihenfolge**: Backtesting, technische Analyse, Research,
   Fundamentalanalyse und Optionsanalyse laufen unabhängig; zusammengeführt
   wird erst im Scoring. Die in Doc 10 §4 gezeichnete Abhängigkeit von Research
   besteht fachlich nicht.

## Begründung

Doc 10 ist das jüngste, mit Abstand detaillierteste Dokument (1.623 Zeilen
gegenüber 42–241 in den übrigen) und das einzige, das Zustandsmodelle,
Fehlerbehandlung, Provenienz und Testarchitektur ausformuliert. Die kürzeren
Dokumente sind eher Skizzen als Spezifikationen.

Die beiden Ausnahmen sind keine Abweichung von der Regel, sondern fachliche
Entscheidungen des Auftraggebers, die über allen Dokumenten stehen.

## Konsequenzen

- Bei jedem Widerspruch gilt Doc 10, ohne erneute Diskussion.
- Doc 11 und Doc 13 werden angeglichen, wenn API bzw. Deployment umgesetzt
  werden — nicht vorher, um keine Dokumentation zu pflegen, die noch keinen
  Code beschreibt.
- Doc 07 wird um den freigegebenen Einstiegszeitpunkt korrigiert, sobald das
  Backtesting implementiert wird.
- Der offene Punkt beim Swing-Score (fünf oder sechs Komponenten) bleibt eine
  fachliche Frage und wird nicht durch diese Rangfolge entschieden.
