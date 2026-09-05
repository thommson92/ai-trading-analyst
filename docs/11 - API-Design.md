# API-Design

> **Wozu dieses Dokument.** Es beschreibt die Web-API, wie sie im
> Dashboard-Sprint entsteht. Entschieden ist sie in
> [ADR 0053](adr/0053-lese-api-kein-lauf-ueber-http.md); bei Widersprüchen
> gilt das ADR. Das Zielbild mit allen künftigen Endpunkten steht
> unverändert in Doc 10 §6.14.
>
> **Die frühere Fassung ist überholt.** Sie stammte aus der Planungsphase,
> führte unversionierte Pfade (`/api/analyses`, `/api/dashboard`) und einen
> Auslöser `POST /api/run-analysis` „nur Administrator". Beides gibt es
> nicht: Die Pfade tragen seit Sprint 1 das Präfix `/api/v1`, und ein
> Analyselauf lässt sich über HTTP nicht starten (ADR 0053).

## Grundprinzip

Eine versionierte REST-API unter `/api/v1` zwischen Frontend und Backend.
Sie ist **lesend**. Sie enthält keine Fachlogik: Die Endpunkte übersetzen
Anfragen, rufen Anwendungsfälle oder Repositories über die UnitOfWork auf und
geben zurück, was dort steht.

Die API und das Dashboard laufen im selben Prozess und unter derselben
Herkunft — das Frontend ist ein statischer Export, den dieselbe Anwendung
ausliefert ([ADR 0052](adr/0052-dashboard-als-statischer-export.md)). Deshalb
gibt es keine CORS-Regelung.

Eine Authentifizierung gibt es nicht. Sie ist bewusst nicht vorgesehen,
solange nichts das eigene Netz verlässt
([ADR 0049](adr/0049-dashboard-mvp-nur-lan.md)).

## Endpunkte

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/api/v1/analysis-runs` | Läufe, neueste zuerst, paginiert; optional nach Status gefiltert |
| GET | `/api/v1/analysis-runs/{run_id}` | Ein Lauf mit seinen Kennzahlen |
| GET | `/api/v1/analysis-runs/{run_id}/reports` | Die Berichte dieses Laufs als Kurzliste |
| GET | `/api/v1/reports/{report_id}` | Ein Bericht — das vollständige gespeicherte Dokument |
| GET | `/api/v1/stocks/{symbol}/reports` | Die Berichte einer Aktie über alle Läufe, neueste zuerst, paginiert |
| GET | `/api/v1/stocks/{symbol}/backtest` | Beide Backtests einer Aktie — Signal und Optionen, getrennt — samt Einzeltrades |
| GET | `/api/v1/stocks/{symbol}/chart` | Der Validierungschart als reine Daten (Kerzen, Indikatoren, Entscheidungspunkte) |
| GET | `/api/v1/options-backtests` | Die Messungen des Optionsbacktests, jüngste zuerst, mit ihren Annahmen |
| GET | `/api/v1/options-backtests/{measurement_id}` | Eine Messung: Kombinationen über alle Aktien und die Aktienzeilen |
| GET | `/api/v1/system/health` | Liveness — der Prozess läuft |
| GET | `/api/v1/system/readiness` | Readiness — die Datenbank ist erreichbar |

Es gibt **keinen Sammelendpunkt** `/dashboard`. Die Tagesübersicht setzt sich
aus den obigen Aufrufen zusammen; ein Endpunkt, der genau eine Ansicht
bedient, verlagerte deren Zuschnitt in die API.

### Läufe

`GET /api/v1/analysis-runs` liefert je Lauf die Felder von
`AnalysisRunResponse`: `id`, `status`, `started_at`, `completed_at`,
`number_of_stocks`, `candidates_found`, `error_message`. Der Statusfilter
kennt die Werte von `RunStatus` (`SCHEDULED`, `RUNNING`, `SCREENING`,
`COMPLETED`, `PARTIALLY_COMPLETED`, `FAILED`).

Die Tagesübersicht braucht zwei verschiedene Läufe und holt sie mit zwei
Aufrufen: den **neuesten** (`?limit=1`) für den aktuellen Stand und den
**letzten erfolgreichen** (`?status=COMPLETED&limit=1`) für den
Zeitpunkt der letzten vollständigen Analyse. Doc 10 §6.15 verlangt beides,
und die beiden sind nicht dasselbe.

`GET /api/v1/analysis-runs/{run_id}` ergänzt die gezählten Kennzahlen des
Laufs: gescreente Aktien, Kandidaten, wegen eines Berichtstermins
ausgeschlossene Kandidaten (`EARNINGS_EXCLUDED`), Kandidaten mit unbekanntem
Termin (`UNKNOWN`) und die Zahl der isolierten Modulfehler. Gezählt wird in
einem Anwendungsfall der Application-Schicht, nicht im Endpunkt.

### Berichte

`GET /api/v1/analysis-runs/{run_id}/reports` gibt eine **Kurzliste**:
`report_id`, `symbol`, `recommendation`, `swing_score`, `investment_score`,
`created_at`. Diese Werte stehen als eigene Spalten an `stock_reports` —
genau dafür gibt es sie: Sie beantworten die Frage, ohne das Dokument zu
öffnen. Der Unternehmensname gehört nicht dazu; er steht nur im Dokument.

`GET /api/v1/reports/{report_id}` gibt das gespeicherte Dokument
**unverändert** zurück, mit seinen deutschen Schlüsseln und allen achtzehn
Abschnitten samt `nummer`, `verfuegbar`, `inhalt` und `vorbehalte`. Es wird
nicht neu erzeugt und nicht umbenannt: Ein abgeschlossener Bericht darf nicht
durch heutigen Code laufen (Doc 10 §8, [ADR 0039](adr/0039-report-generator.md)).

Daraus folgt eine bewusste Uneinheitlichkeit: Die **Hüllen** der API sind
englisch benannt wie die übrigen Antwortschemata, die **Nutzlast des
Berichts** ist deutsch. Sie ist ein gespeichertes Dokument, kein
Antwortschema.

### Historie

`GET /api/v1/stocks/{symbol}/reports` liefert dieselbe Kurzliste für ein
Symbol über alle Läufe hinweg. Das ist die Analysehistorie aus US-010: Jeder
Eintrag zeigt Datum, Empfehlung und beide Scores und führt in die
Detailansicht.

### Backtests

Zwei Backtests, und sie bleiben in der API **getrennt** — bis in die
Feldnamen. Der Signal-Backtest sagt, ob das Signal trägt; der
Optionsbacktest, ob sich damit Geld verdienen ließe. Es gibt nirgends eine
gemeinsame Zahl, so wenig wie es eine gemeinsame Erfolgsquote aus
Trefferquote und Halten oberhalb des Einstiegs gibt (`CLAUDE.md`).

`GET /api/v1/stocks/{symbol}/backtest` liefert beides für eine Aktie, dazu
die Einzeltrades der jüngsten Messung. Mit `?measurement_id=` gilt eine
bestimmte statt der jüngsten. Lief noch kein Messlauf, ist `measurement`
`null` und die Optionsseite leer — der Signal-Backtest steht trotzdem, denn
er entsteht im Tageslauf.

`GET /api/v1/options-backtests` und `/{measurement_id}` bedienen die
Gesamtübersicht. **An jeder Messung stehen ihre Annahmen** —
Volatilitätsaufschlag, Verfallskalender, Strike-Raster,
Ausführungsabschlag. Sie sind das einzige, was zwei Messungen desselben
Tages unterscheidet, und ohne sie ist keine Zahl darunter deutbar: Jede
Prämie des Optionsbacktests ist modelliert
([ADR 0058](adr/0058-optionsvorschlaege-im-rueckblick.md)).

Die Aktienzeilen einer Messung entstehen **aus den Einzeltrades** und nicht
als Mittel der Kombinationszeilen; ein Mittel von Mitteln gewichtete eine
Aktie mit drei Trades so schwer wie eine mit dreißig. Sortiert kommen sie
nach der Rendite der gemanagten Variante, Aktien ohne belastbare Stichprobe
ans Ende — was „gut" heißt, entscheidet die API und nicht die Oberfläche.

`GET /api/v1/stocks/{symbol}/chart` gibt den Payload des Validierungscharts,
erzeugt von derselben Funktion wie `cli chart`. Die Kerzen kommen
**ausschließlich aus dem Bestand**; ein Webdienst, der dafür die
TWS-Client-ID belegte, wäre gefährlicher als kein Chart
([ADR 0052](adr/0052-dashboard-als-statischer-export.md)). Geliefert wird die
ganze Reihe — ein Fenster verschöbe die Frage, welches das richtige ist, in
die Oberfläche.

**Keiner dieser Endpunkte startet einen Messlauf.** Er läuft über die ganze
Watchliste und fünf Jahre und entsteht über `cli options-backtest`, aus
demselben Grund, aus dem die API keinen Analyselauf startet.

## Paginierung

Die beiden Listen, die **unbegrenzt wachsen**, sind paginiert — die Läufe
und die Historie einer Aktie. Doc 10 §6.14 verlangt Pagination bei Listen:

- `limit` — Voreinstellung 25, Obergrenze 100,
- `offset` — Voreinstellung 0,
- Sortierung fest: neueste zuerst.

Die Antwort ist eine Hülle mit `items`, `total`, `limit` und `offset`. Ohne
`total` wüsste die Oberfläche nicht, ob eine weitere Seite existiert.

**Die Berichte eines Laufs sind bewusst nicht paginiert.** Ein Bericht
entsteht nur für einen Kandidaten ([ADR 0039](adr/0039-report-generator.md)),
und deren Zahl steht als `candidates_found` am Lauf selbst. Eine Seitenlogik
über eine Liste, die von vornherein begrenzt ist, wäre eine Hülle ohne
Inhalt.

## Fehler

Die Fehlerstruktur ist die von FastAPI und wird nicht ersetzt:

- `404` mit `{"detail": "…"}`, wenn ein Lauf, ein Bericht oder ein Symbol
  nicht existiert,
- `422` mit der Validierungsstruktur von FastAPI, wenn ein Parameter nicht
  passt (etwa `limit=500` oder eine unlesbare UUID),
- `500` nur bei einem unerwarteten Fehler.

Eine eigene Fehlerhülle darüberzulegen brächte eine zweite Struktur für
denselben Zweck.

## Was es nicht gibt

- **Kein Schreibpfad.** Kein `POST /analysis-runs`, kein `…/retry`, keine
  Konfigurationsänderung über HTTP. Läufe entstehen über die
  Aufgabenplanung und `cli dispatch` (ADR 0053).
- **Keine Authentifizierung und keine Rollen.** Erst mit der Exposition
  (Neubewertung von ADR 0049).
- **Keine Endpunkte für Kerzen, Watchlisten oder Backtests** als eigene
  Ressourcen. Was das Dashboard davon braucht, steht bereits im Bericht.

## OpenAPI

FastAPI erzeugt die Beschreibung selbst; sie liegt unter `/openapi.json`,
die bedienbare Fassung unter `/docs`. Beide sind nur im eigenen Netz
erreichbar, wie die API selbst.
