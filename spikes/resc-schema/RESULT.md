# Ergebnis der RESC-Inhaltsprüfung

Erhoben am 2026-08-12 gegen die TWS des Projektinhabers, Symbole `AAPL`
(325.325 Zeichen) und `WMT` (323.706 Zeichen). Ausgewertet mit
`probe_resc.py`; die vollständigen XML-Antworten liegen unversioniert unter
`results/`.

Der Datensatz heißt `REarnEstCons` — Reuters Earnings Estimates Consensus.

## Die beiden Fragen

### F9, Analystenratings und Kursziele: **abgedeckt**

| Was | Wo | Ausprägungen |
|---|---|---|
| Kursziel | `ConsEstimates/NPEstimates/NPEstimate[@type=TARGETPRICE]` | `High`, `Low`, `Mean`, `Median` |
| Empfehlungen | `ConsEstimates/Recommendations/STOpinion/ConsOpinion` | `@code` 1–5, `@desc` `BUY`, `OUTPERFORM`, `HOLD`, `UNDERPERFORM`, `SELL` |
| Zahl der Analysten je Empfehlung | `ConsOpValue[@type=NumOfEst]` | ganze Zahlen |

Ein separater Anbieter für Ratings und Kursziele ist damit **nicht nötig**.
Die Empfehlungen liegen als Verteilung vor (wie viele Analysten je Stufe),
nicht als fertige Durchschnittsnote — ein Mittelwert ist daraus
deterministisch berechenbar.

**Nicht jedes Symbol hat Empfehlungen.** Bei `WMT` ist `Recommendations`
leer: das Element existiert, ohne Inhalt. Ein Feature, das Ratings
voraussetzt, läuft für einen Teil der Watchlist ohne Datengrundlage. Das ist
der Regelfall aus Doc 10 — fehlt eine Kennzahl, bleibt sie fehlend, kein
Ersatzwert.

### Earnings-Termine: **nicht abgedeckt**

Kein Element und kein Attribut enthält einen **künftigen** Berichtstermin.
Die feinste Zeitangabe zu einer Periode ist `@endCalYear`/`@endMonth` — das
Ende der Geschäftsperiode, monatsgenau. Das ist nicht der Berichtstermin:
Unternehmen berichten typisch drei bis sechs Wochen nach Periodenende.

Damit bleibt **Einschränkung E1 aus ADR 0014 unverändert gültig**. Der
Earnings-Filter (F9, Sprint 3) braucht einen eigenen Anbieter.

Ein Randbefund dazu: `Actuals/…/ActValue@updated` trägt einen vollständigen
Zeitstempel (`9999-99-99A99:99:99`, also ISO mit Uhrzeit). Er steht nur an
**Ist-Werten**, nicht an Schätzungen, und markiert den Zeitpunkt, zu dem
Reuters den Wert eingepflegt hat — nicht den Zeitpunkt der Veröffentlichung.
Der früheste `@updated` je Geschäftsperiode wäre eine **Näherung** für den
historischen Berichtstermin, wie sie das Backtesting bräuchte.

Diese Näherung ist hier ausdrücklich **nicht** als Lösung vorgeschlagen. Ihr
Fehler ist unbekannt, und eine spätere Korrektur eines Wertes durch Reuters
überschreibt den Zeitstempel — dann steht dort das Korrekturdatum. Ein
Einstiegsfilter auf dieser Grundlage wäre ein stiller Ersatzwert und damit
gegen die Projektregel. Verwendbar wäre sie allenfalls als Gegenprobe zu
einer echten Quelle, und erst nachdem sie gegen bekannte Termine geprüft
wurde.

## Was sonst noch drinsteht

Über die ursprüngliche Frage hinaus, weil es die Anbieterfrage für andere
Module berührt:

- **16 Kennzahlen** als Ist-Wert *und* als Schätzung, je Quartal und
  Geschäftsjahr: `BVPS`, `CFSHR`, `DDPS1`, `EBIT`, `EBITD`, `EBS`, `EIBT`,
  `EPS`, `EV`, `GPS`, `GROSMGN`, `NETDEBT` und vier weitere. Für AAPL sind
  das 196 Ist-Perioden und 389 Schätzperioden. Das ist eine belastbare
  Grundlage für die Fundamentalanalyse — ob sie ausreicht, ist eine eigene
  Frage.
- **Schätzungsrevisionen.** `ConsValue@dateType` kennt `CURR`, `1MA` und
  `3MA` — derselbe Schätzwert heute, vor einem Monat und vor drei Monaten.
  Die Veränderung einer Konsensschätzung ist ein eigenständiges Signal und
  liegt hier ohne Zusatzaufwand vor.
- **Streuung je Schätzung:** `High`, `Low`, `Mean`, `Median`, `StdDev` und
  `NumOfEst`. Uneinigkeit unter Analysten ist damit messbar, nicht nur der
  Mittelwert.
- **Kurskontext:** `MarketDataItem@type` liefert `52WKHIGH`, `52WKLOW`,
  `CLPRICE`, `MARKETCAP`.
- **Kennungen:** `SecId@type` liefert `ISIN`, `RIC`, `TICKER` und
  `InstrumentPI` — eine saubere Zuordnung über Symbolschreibweisen hinweg.
- **Sektor** nach Reuters-Klassifikation (`Sector@code`, `@set=R`).

## Folgerungen

1. Die offene Entscheidung „Anbieter für Analystenratings und Kursziele" aus
   der [ADR-Übersicht](../../docs/adr/README.md) kann geschlossen werden:
   IBKR RESC deckt sie ab.
2. E1 aus ADR 0014 bleibt bestehen. Der Earnings-Workstream ist **nicht**
   entfallen, wohl aber schärfer umrissen: Gesucht ist eine Quelle für
   **künftige Berichtstermine**, nicht für Schätzungen oder Ratings.
3. Vor einer produktiven Nutzung ist zu klären, ob RESC lizenzrechtlich für
   die geplante Verarbeitung genutzt werden darf. Die Daten stammen von
   Reuters/Refinitiv und werden über das IBKR-Abonnement bereitgestellt —
   dieselbe Frage, an der die TradingView-Anbindung gescheitert ist
   ([ADR 0012](../../docs/adr/0012-gate-g3-strang-a-no-go-non-display-nutzung.md)).
   Diese Prüfung steht aus und gehört in das ADR zur F9-Datenquelle.
