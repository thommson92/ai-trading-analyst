# Architecture Decision Records

Jede Architekturentscheidung wird hier als eigenes Dokument festgehalten
(Doc 10, Paragraph 19).

## Format

Dateiname: `NNNN-kurzbeschreibung.md`, fortlaufend nummeriert.

Aufbau:

```markdown
# ADR NNNN: Titel

- Status: Vorgeschlagen | Angenommen | Abgeloest durch ADR-NNNN
- Datum: YYYY-MM-DD

## Kontext
Welches Problem steht an, welche Rahmenbedingungen gelten.

## Entscheidung
Was wird getan.

## Begruendung
Warum diese Option und nicht die Alternativen.

## Konsequenzen
Was folgt daraus, auch das Unangenehme.
```

Ein ADR wird nicht rueckwirkend geaendert. Aendert sich die Entscheidung,
entsteht ein neues ADR, das das alte ausdruecklich abloest.

## Uebersicht

| ADR | Titel | Status |
|---|---|---|
| [0001](0001-dokumentenhierarchie.md) | Doc 10 ist bei Widersprüchen maßgeblich | Angenommen |
| [0002](0002-branching-modell.md) | Branching-Modell main/dev mit Feature-Branches | Angenommen |
| [0003](0003-monorepo-und-schichtung.md) | Monorepo mit vier Schichten und erzwungenen Grenzen | Angenommen |
| [0004](0004-python-toolchain.md) | Python-Toolchain: pyproject, venv, ruff, mypy strict | Angenommen |
| [0005](0005-konfiguration-und-secrets.md) | Konfiguration in YAML, Geheimnisse aus der Umgebung | Angenommen |
| [0006](0006-kein-redis-im-mvp.md) | Kein Redis im MVP, Koordination über PostgreSQL | Angenommen |
| [0007](0007-gate-g1-indikatorparameter.md) | Indikator-Parameter bleiben bis zur Freigabe leer | Abgelöst durch ADR 0010 |
| [0008](0008-reproduzierbare-installation.md) | Reproduzierbare Installation über Lock-Dateien | Angenommen (Erzeuger ersetzt durch ADR 0015) |
| [0009](0009-required-checks-nicht-konfigurierbar.md) | Required Status Checks derzeit nicht konfigurierbar (Plan-Limit) | Angenommen (offener Punkt) |
| [0010](0010-gate-g1-freigegeben.md) | Gate G1 fachlich freigegeben -- Indikator- und Signalparameter | Angenommen |
| [0011](0011-ci-dispatch-unzuverlaessig.md) | GitHub-Actions-Workflow-Dispatch ist unzuverlaessig (Plattformseitig) | Angenommen (offener Punkt) |
| [0012](0012-gate-g3-strang-a-no-go-non-display-nutzung.md) | Gate G3 Strang A -- NO_GO wegen Non-Display-Nutzungsverbots der TradingView-Nutzungsbedingungen | Angenommen |
| [0013](0013-interactive-brokers-kandidat-vorschlag.md) | Interactive Brokers als nächster Kandidat für Marktdaten -- Spike vorgeschlagen | Angenommen (Spike abgeschlossen, GO_WITH_LIMITATIONS; Schritt 4 freigegeben durch ADR 0014) |
| [0014](0014-ibkr-produktivintegration-freigegeben.md) | IBKR als produktive Marktdaten-Grundlage freigegeben -- technisch GO_WITH_LIMITATIONS, vertraglich GO | Angenommen |
| [0015](0015-plattformunabhaengige-lock-dateien.md) | Lock-Dateien plattformunabhängig erzeugen (uv statt pip-compile) | Angenommen |
| [0016](0016-ibkr-keine-quelle-fuer-research-daten.md) | IBKR ist keine Quelle für Research-Daten (RESC: NO_GO) | Angenommen |
| [0017](0017-finnhub-fuer-earnings-und-ratings.md) | Finnhub als Quelle für Earnings-Termine und Analystenratings | Angenommen |
| [0018](0018-kein-windows-autologon.md) | Kein Windows-Autologon — manueller Start wird akzeptiert | Angenommen |
| [0019](0019-trading-day-dispatcher.md) | Trading-Day-Dispatcher — idempotenter Einzelstart statt Dauerprozess | Angenommen |
| [0020](0020-earnings-filter-status-und-handelstagskalender.md) | Earnings-Filter — reduziertes Statusmodell und Wochentagsnäherung für die Kerzenzählung | Angenommen |
| [0021](0021-ki-anbindung-anthropic-api.md) | KI-Anbindung — Anthropic API mit Modellprofilen je Analyseaufgabe | Angenommen |
| [0022](0022-research-agent-quellen.md) | Research Agent — Anthropic Web Search/Web Fetch, SEC EDGAR deterministisch für Fundamentaldaten | Angenommen (GO_WITH_LIMITATIONS) |
| [0023](0023-research-agent-zitierarchitektur.md) | Research Agent — Zitierarchitektur | Angenommen |
| [0024](0024-benachrichtigungskanal-telegram.md) | Benachrichtigungskanal — Telegram Bot API | Angenommen |
| [0025](0025-deterministische-chartauswertung-und-zonen.md) | Deterministische Chartauswertung — Swing-Pivots mit Clustering für Zonen | Angenommen |
| [0026](0026-technical-agent-ki-einordnung.md) | Technical Agent — KI-Einordnung der deterministischen Chartauswertung | Angenommen |

## Offene Entscheidungen

Diese Punkte sind bewusst noch nicht entschieden und erhalten je ein eigenes
ADR, sobald die nötigen Informationen vorliegen:

- Anbindung an TradingView: Gate G2 mit `GO_WITH_LIMITATIONS` abgeschlossen
  (siehe `spikes/tradingview-cdp/REPORT.md`), Gate G3 mit **NO_GO**
  entschieden — siehe [ADR 0012](0012-gate-g3-strang-a-no-go-non-display-nutzung.md)
  und [docs/requirements/g3-entscheidungsvorlage.md](../requirements/g3-entscheidungsvorlage.md).
  TradingView ist damit als Datenquelle erledigt.
- Marktdaten-/Screening-Anbindung anstelle von TradingView — **entschieden.**
  Interactive Brokers ist über [ADR 0014](0014-ibkr-produktivintegration-freigegeben.md)
  als produktive Marktdaten-Grundlage freigegeben (technisch
  GO_WITH_LIMITATIONS, vertraglich GO). Schritt 4 aus
  [ADR 0013](0013-interactive-brokers-kandidat-vorschlag.md) ist damit
  abgeschlossen; die akzeptierten Einschränkungen, Annahmen und Restrisiken
  stehen in ADR 0014.
- Anbieter für historische Intraday-Kurse (F9) — durch IBKR beantwortet
  (ADR 0013, Spike-Frage 3/4: 195-Minuten-Aggregation und historische
  Abdeckung bis 2 Jahre live bestätigt).
- Kursziele (F9) — **zurückgestellt.** Termine und Analystenratings sind
  durch [ADR 0017](0017-finnhub-fuer-earnings-und-ratings.md) entschieden
  (Finnhub, kostenlose Stufe); der Kursziel-Endpunkt ist dort
  kostenpflichtig. Bewusst ohne Kursziele gebaut, nachrüstbar in einer
  späteren Ausbaustufe.
- Historische Berichtstermine für das Backtesting — **zurückgestellt.**
  Vorgemerkter Weg ist SEC EDGAR (Einreichungsdatum des `8-K` mit Item
  2.02): amtlich, kostenlos und ohne Lizenzbeschränkung. Siehe ADR 0017,
  Einschränkung L9.
- Anbieter für Optionsketten mit Greeks (F9) — durch IBKR beantwortet
  (ADR 0013, Spike-Frage 6: Optionsketten-Struktur und modellierte Greeks
  nach Aktivierung eines zusätzlichen Optionsmarktdaten-Abos live
  bestätigt).
- Benachrichtigungskanal (F10) — **entschieden.** Telegram Bot API, siehe
  [ADR 0024](0024-benachrichtigungskanal-telegram.md).
- KI-Anbieter und Modellprofile (F11) — **entschieden.** Anthropic API mit
  gestuften Modellprofilen je Analyseaufgabe, siehe
  [ADR 0021](0021-ki-anbindung-anthropic-api.md).
- Qualitative Interpretation der Chartauswertung — **entschieden.** Der
  Technical Agent ordnet ausschließlich deterministisch berechnete Werte
  ein, siehe [ADR 0026](0026-technical-agent-ki-einordnung.md).
- Externer Zugriff auf das Dashboard (F12)
