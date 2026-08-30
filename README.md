# AI Trading Analyst

Persönliches, KI-gestütztes Analyse-System für Long-Swing-Trades auf US-Aktien.

Das System screent täglich Watchlisten nach definierten technischen
Kaufsignalen, reduziert sie auf wenige Kandidaten und analysiert diese vertieft
— technisch, fundamental, nachrichtenseitig und im Hinblick auf
Cash-Secured-Put-Strategien. Ergebnis ist eine begründete Entscheidungsgrundlage
im Web-Dashboard plus eine Push-Nachricht aufs Smartphone.

**Das System führt keine Orders aus.** Die Handelsentscheidung bleibt beim
Nutzer.

## Grundprinzip

Zwei Schichten, streng getrennt:

- **Deterministisch** — Screener, Earnings-Filter, Backtesting,
  Score-Arithmetik. Reiner Programmcode, reproduzierbar, versioniert. Ein
  Sprachmodell verändert hier nichts.
- **Interpretativ** — Research, qualitative Einordnung, Berichtstexte.
  Sprachmodell mit strukturierten Ein-/Ausgaben, Quellenbindung und
  `INSUFFICIENT_DATA` statt Halluzination.

Jedes Analysemodul speichert seine Berechnungen und seine KI-Interpretation
getrennt.

## Projektstand

**Sprints 1–3 abgeschlossen, Sprint 4 begonnen.** Die deterministische Kette
läuft durchgehend: Watchlist-Import, resumierbarer Backfill, Bildung
abgeschlossener 195-Minuten-Kerzen aus nativen 15-Minuten-Bars,
Indikatorberechnung, Screener, Earnings-Filter, Backtesting und der
Trading-Day-Dispatcher.

Die **Historientiefe** ist gemessen und aufgefüllt: Der Tiefen-Backfill lief am
2026-08-24 über die volle Watchlist, der Backtest erreicht seither `NORMAL`
statt `LOW_SAMPLE`
([ADR 0027](docs/adr/0027-historientiefe-messen-vor-anspruch.md),
[ADR 0028](docs/adr/0028-historientiefe-gemessen.md)).

Gate G1 ist fachlich freigegeben
([ADR 0010](docs/adr/0010-gate-g1-freigegeben.md)); die drei Signalregeln und
die 2-aus-3-Kandidatenregel sind reiner Domain-Code
(`backend/src/ai_trading_analyst/domain/screening`).

Als Datenquelle ist **Interactive Brokers** freigegeben
([ADR 0014](docs/adr/0014-ibkr-produktivintegration-freigegeben.md), technisch
`GO_WITH_LIMITATIONS`, vertraglich `GO`); TradingView ist mit **NO_GO**
ausgeschieden ([ADR 0012](docs/adr/0012-gate-g3-strang-a-no-go-non-display-nutzung.md)).
Earnings-Termine kommen von Finnhub
([ADR 0017](docs/adr/0017-finnhub-fuer-earnings-und-ratings.md)), die
KI-Anbindung von Anthropic
([ADR 0021](docs/adr/0021-ki-anbindung-anthropic-api.md)).

Aus Sprint 4 steht der **Research Agent** mit Quellenbindung und
Kostensteuerung ([ADR 0022](docs/adr/0022-research-agent-quellen.md),
[ADR 0023](docs/adr/0023-research-agent-zitierarchitektur.md)).

Ebenfalls aus Sprint 4 steht die **technische Analyse** (Doc 10,
Paragraph 6.8), beide Hälften. Deterministisch berechnet werden
Trendrichtung, Volatilität über die Average True Range, jüngste Hoch- und
Tiefpunkte, Unterstützungs-/Widerstandszonen aus Swing-Pivots mit Clustering
und daraus das Chance-Risiko-Verhältnis
([ADR 0025](docs/adr/0025-deterministische-chartauswertung-und-zonen.md)).
Darauf setzt der **Technical Agent** auf: Er ordnet diese Werte qualitativ
ein — Trendstärke, Breakout-Qualität, überkauft/überverkauft,
Fehlsignalrisiko, Chance/Risiko und Plausibilität eines Swing-Einstiegs —,
ohne eine einzige Zahl davon zu verändern
([ADR 0026](docs/adr/0026-technical-agent-ki-einordnung.md)).

Beides läuft für jeden Kandidaten und hängt an keinem anderen Analysemodul.
`cli technical --provider ibkr --symbols AAPL` gibt die Berechnung samt Zonen
aus, `--interpret` zusätzlich die Einordnung und `--show-prompt` die
vollständige Modelleingabe — damit nachprüfbar bleibt, dass das Sprachmodell
nur den fertigen Snapshot sieht.

Zusammengeführt wird das alles vom **Report Generator** (Doc 10,
Paragraph 6.12): Je Kandidat entsteht ein Bericht über alle achtzehn
Pflichtpunkte — auch die vier, die auf Optionsanalyse und Scoring aus
Sprint 5 stehen. Sie erscheinen ausdrücklich als Lücke mit Begründung, nicht
als weggelassener Punkt ([ADR 0039](docs/adr/0039-report-generator.md)). Zu
Punkt 5 gehört die historische Signalstatistik, die seit
[ADR 0038](docs/adr/0038-backtest-im-tageslauf.md) im Tageslauf entsteht.
Der Bericht wird als JSON-Dokument unveränderlich gespeichert;
`cli report --run <lauf-id>` zeigt ihn lesbar oder als Dokument. Die
KI-Formulierung folgt getrennt.

Der **Benachrichtigungskanal (F10)** ist entschieden und umgesetzt
([ADR 0024](docs/adr/0024-benachrichtigungskanal-telegram.md)): Ein
ausgefallener Tageslauf meldet sich über Telegram, statt nur im Protokoll zu
erscheinen. Nach einem erfolgreichen Lauf kommt eine Kurzfassung — Symbole,
Signaltypen, Fehlsignalrisiko als Stufe. Kurse und Kennzahlen bleiben
bewusst draußen, die Nachricht verlässt das eigene Netz
([ADR 0040](docs/adr/0040-inhalt-der-ergebnismeldung.md)).

Welcher Anbieter jeweils läuft, entscheidet `config/default.yaml`. Alle
externen Quellen stehen dort bewusst auf `fixture`, damit Start und Tests ohne
Zugangsdaten auskommen; scharf geschaltet wird je Lauf über Argumente — siehe
[Doc 14](docs/14%20-%20Inbetriebnahme%20und%20Betrieb.md).

Noch offen:

| Thema | Stand |
|---|---|
| Fundamental Agent, KI-Hälfte | Sprint 4 — die deterministischen Kennzahlen stehen ([ADR 0032](docs/adr/0032-fundamentalanalyse-deterministisch.md), [ADR 0033](docs/adr/0033-zwoelfmonatswerte-statt-jahresabschluss.md)), die Einordnung folgt |
| Report Generator, KI-Hälfte | Sprint 4 — der deterministische Bericht steht ([ADR 0039](docs/adr/0039-report-generator.md)), die Formulierung folgt |
| Optionsanalyse, Swing- und Investment-Score | Sprint 5 |
| Dashboard und Analysehistorie | Sprint 6 — das Frontend ist ein Next.js-Gerüst |

Der Erledigungsstand der Befunde aus dem
[Repository-Audit](docs/audits/2026-08-23-repository-audit.md) wird in der
[Nachverfolgung](docs/audits/2026-08-23-nachverfolgung.md) geführt.

## Struktur

```
backend/          Python 3.12/3.13, FastAPI-Anwendung
  src/ai_trading_analyst/
    domain/         Fachregeln, Provider-Schnittstellen (ohne Infrastruktur)
      screening/      Signalregeln, 2-aus-3-Kandidatenregel (Gate G1),
                      Indikatorberechnung, 195-Minuten-Kerzenbildung
      technical/      Deterministische Chartauswertung: Zonen, Trend, ATR
                      (ADR 0025) -- fliesst nie in eine Signalentscheidung
      analysis/       AnalysisRun/Stock-Modelle, Provider-Ports
    application/    Use Cases, Orchestrierung (run_analysis.py)
    infrastructure/ Repositories, Adapter
      fixtures/       FixtureMarketDataProvider, versionierte JSON-Fixtures
      ibkr/           IbkrMarketDataProvider, TWS-Anbindung (ADR 0014)
      persistence/    SQLAlchemy-Modelle, Repositories, UnitOfWork
    presentation/   API-Endpunkte, Schemas (/api/v1)
    config/         Konfiguration und Geheimnisse
    observability/  Logging, Correlation IDs
    bootstrap.py    Composition Root -- verdrahtet alle Schichten
    main.py         ASGI-Einstiegspunkt (uvicorn ai_trading_analyst.main:app)
  migrations/       Alembic-Migrationen
  tests/
    unit/           Fachliche Einzeltests, keine Datenbank
    integration/    Repositories, Migration, API -- echtes PostgreSQL
    architecture/   Schichtgrenzen (bricht bei Verstoß die CI)
frontend/         Next.js 15, TypeScript strict
config/           default.yaml — fachliche Konfiguration ohne Geheimnisse
docs/             Fachdokumente 01–14 (14: Inbetriebnahme und Betrieb)
docs/adr/         Architecture Decision Records
```

Bei Widersprüchen zwischen den Fachdokumenten ist
`docs/10 - System Architecture.md` maßgeblich (siehe
[ADR 0001](docs/adr/0001-dokumentenhierarchie.md)).

## Einrichtung

Vorausgesetzt: Python 3.12 auf dem Entwicklungsrechner, **3.13 auf dem
Windows-Server**, Node.js 20+. `requires-python` laesst beide zu, und die
CI prueft beide.

### Backend

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install --require-hashes -r requirements-dev.lock.txt
.venv/bin/pip install --no-deps -e .
```

Auf dem Windows-Server — dort läuft die TWS, also auch das Backend:

```powershell
cd backend
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock.txt
.venv\Scripts\python.exe -m pip install --no-deps -e .
```

Die Installation läuft ausschließlich über die Lock-Datei mit Hash-Verifikation
— keine Versionsauflösung auf dem jeweiligen Rechner. Siehe
[ADR 0008](docs/adr/0008-reproduzierbare-installation.md).

Damit dieselbe Lock-Datei auf macOS, Linux und Windows funktioniert, wird sie
plattformunabhängig erzeugt (siehe unten und
[ADR 0015](docs/adr/0015-plattformunabhaengige-lock-dateien.md)). `uvicorn`
wird ohne das Extra `standard` geführt — es zieht `uvloop` nach, das es für
Windows nicht gibt und das dieses Projekt nicht braucht.

Ändert sich `pyproject.toml`, werden die Lock-Dateien neu erzeugt — mit `uv`
und **immer** mit `--universal`, siehe
[ADR 0015](docs/adr/0015-plattformunabhaengige-lock-dateien.md):

```bash
cd backend
uv pip compile --universal --generate-hashes \
    --output-file requirements.lock.txt pyproject.toml
uv pip compile --universal --generate-hashes --extra dev \
    --output-file requirements-dev.lock.txt pyproject.toml
```

`--universal` schreibt die Umgebungsmarker in die Datei, statt sie auf dem
erzeugenden Rechner auszuwerten (`colorama==0.4.6 ; sys_platform == 'win32'`).
Ohne das entsteht eine Lock-Datei, die nur auf der Plattform funktioniert, auf
der sie erzeugt wurde — der Fehler zeigt sich dann erst auf dem Zielsystem.
`uv` ist nur zum Erzeugen nötig; installiert wird weiterhin mit `pip`.

### Frontend

```bash
cd frontend
npm ci
```

`npm ci` installiert exakt die in `package-lock.json` festgeschriebenen
Versionen und bricht ab, wenn `package.json` und die Lock-Datei
auseinanderlaufen — im Gegensatz zu `npm install` also reproduzierbar.

### Marktdaten über Interactive Brokers

Die Watchlist kommt aus `watchlists/` — allen `*.txt` darin, im
TradingView-Exportformat (`NASDAQ:NVDA,NYSE:BRK.B,…`, `###Abschnitt` als
Überschrift). Mehrfachnennungen über mehrere Listen werden zusammengefasst,
`BRK.B` wird in IBKRs Schreibweise `BRK B` übersetzt.

Für einen manuellen Lauf gegen die TWS gibt es eine Kommandozeile:

```bash
cd backend
# Was würde gescreent? Ohne jede Verbindung zur TWS:
.venv/bin/python -m ai_trading_analyst.cli watchlist

# Einzelne Symbole, ohne Wartezeit zwischen den Anfragen:
.venv/bin/python -m ai_trading_analyst.cli screen --provider ibkr \
    --symbols AAPL,MSFT --no-pacing

# Die vollständige Watchlist, direkt von der TWS:
.venv/bin/python -m ai_trading_analyst.cli screen --provider ibkr
```

### Der tägliche Ablauf: erst holen, dann rechnen

Mit `--source live` fragt `screen` bei **jedem** Lauf die TWS — rund 20 s je
Aktie, also eine gute Stunde für die volle Watchlist. Der Ablauf zerfällt
deshalb in zwei Schritte, die einander nicht brauchen:

```bash
# Holt nur, was seit dem letzten Lauf fehlt. Beim ersten Mal ein Jahr,
# danach die Lücke -- ein Tag, ein Wochenende, drei Wochen nach einem Ausfall.
.venv/bin/python -m ai_trading_analyst.cli backfill --provider ibkr

# Rechnet auf dem Bestand: ohne TWS, ohne Pacing.
.venv/bin/python -m ai_trading_analyst.cli screen --provider ibkr
```

`market_data.source` steht ausgeliefert auf `stored`; nur der Backfill
spricht noch mit der TWS. Das gilt **auch für den persistierten Lauf hinter
der API** — beide nehmen dieselbe Quelle, damit der Lauf zur Kontrolle nicht
anders arbeitet als der reguläre. `--source live` stellt für einen einzelnen
Aufruf um.

`backfill` und der Lauf aus dem Bestand brauchen die Datenbank
(`ATA_DATABASE_URL`). Die Adresse steht entweder
in der Umgebung oder in einer `.env` im Projektwurzelverzeichnis (Vorlage:
`.env.example`); die Umgebungsvariable gewinnt. Gespeichert werden die
**nativen 15-Minuten-Bars**, nicht die daraus gebildeten Kerzen: Ändert sich
eine Aggregationsregel, ist das ein erneuter Lauf über lokale Daten statt
eines Abrufs über ein Jahr und alle Symbole.

Ein abgebrochener Backfill wird schlicht erneut gestartet — Schreibvorgänge
sind über `(symbol, start)` idempotent, aufzuräumen gibt es nichts.

**Was der Bestand nicht selbst merkt:** Er kennt nur seinen jüngsten Bar. Ein
Tag, der mitten in der Historie fehlt, wird deshalb nie von allein nachgeholt
— und die Kerzenbildung erkennt einen *vollständig* fehlenden Handelstag
nicht, weil dafür ein Börsenkalender nötig wäre. Drei Vorkehrungen dagegen:
Der Backfill meldet, wenn eine Antwort deutlich weniger Historie enthält als
angefragt (so kürzt IBKR stillschweigend); er meldet außerdem, wenn eine
Antwort *später* ansetzt als der letzte gespeicherte Bar — dann klafft
zweifelsfrei etwas dazwischen. Und `--from` holt einen Zeitraum nach:

```bash
.venv/bin/python -m ai_trading_analyst.cli backfill --provider ibkr \
    --symbols AAPL --from 2026-01-01
```

**Was `--from` nicht kann:** bereits gespeicherte Bars berichtigen. Die Ablage
lässt Dubletten fallen, damit ein wiederholter Lauf nichts anrichtet — ein
vorhandener Bar bleibt deshalb stehen, wie er ist. Füllen lässt sich damit
nur, was fehlt. Deshalb legt der Backfill den noch laufenden, unfertigen Bar
gar nicht erst ab: Er wäre sonst dauerhaft ein Zwischenstand.

Nebeneffekt, der wichtiger ist als die Geschwindigkeit: Der Lauf wird
**wiederholbar**. IBKRs Ein-Jahres-Fenster wandert mit der Uhr, und schon
zwei Läufe desselben Tages ergaben unterschiedlich viele Kerzen. Auf dem
Bestand liefert dieselbe Analyse dasselbe Ergebnis.

`market_data.provider` bleibt in `config/default.yaml` bewusst auf `fixture`,
damit API und Tests ohne TWS auskommen; `--provider ibkr` schaltet für den
einzelnen Lauf um.

Scheitert der Aufruf unter macOS mit `ModuleNotFoundError: ai_trading_analyst`,
obwohl die Installation lief: Python überspringt `.pth`-Dateien mit gesetztem
`hidden`-Flag, und manche Werkzeuge setzen es. `pytest` merkt davon nichts,
weil es `src` selbst auf den Pfad legt.

```bash
chflags nohidden .venv/lib/python3.12/site-packages/*.pth
```

**Zur Laufzeit:** IBKR lässt 60 Historienanfragen je zehn Minuten zu und
sperrt bei Überschreitung die Verbindung. Zwischen zwei Anfragen liegen
deshalb 11 Sekunden (`minimum_request_interval_seconds`) — bei rund 190
Symbolen dauert ein vollständiger Lauf gut eine halbe Stunde. `--no-pacing`
schaltet das ab und ist nur für eine Handvoll Symbole gedacht.

Voraussetzung ist eine laufende, **manuell angemeldete** TWS mit aktiviertem
API-Zugriff (Einstellungen → API → Settings → "Enable ActiveX and Socket
Clients"). Zwei Punkte aus [ADR 0014](docs/adr/0014-ibkr-produktivintegration-freigegeben.md)
gelten dabei verbindlich:

- **Die Client-ID muss frei sein.** Läuft an derselben TWS-Instanz eine
  weitere Anwendung, braucht jede ihre eigene ID.
- **"Read-Only API" nicht aktivieren**, solange eine andere Anwendung über
  dieselbe TWS echte Orders überträgt — der Schalter gilt TWS-weit und würde
  auch sie blockieren. Dass der Analyzer nur liest, ist in seinem Code
  verankert, nicht in dieser Einstellung.

Ohne erreichbare TWS meldet der Provider einen klaren Fehler; erfundene oder
zwischengespeicherte Kurse gibt es nicht.

## Der automatische Tageslauf

Beide Schritte — Bestand auffüllen und rechnen — laufen im Betrieb über ein
einziges Kommando:

```bash
.venv/bin/python -m ai_trading_analyst.cli dispatch --provider ibkr
```

Es entscheidet selbst, ob etwas zu tun ist, und endet meistens sofort. Die
Zielkerze ist die erste des Tages (09:30–12:45 New Yorker Zeit,
`market.daily_candle_index`); gerechnet wird ab 12:50, also nach dem
Sicherheitspuffer aus `scheduler.safety_buffer_seconds`.

Die Entscheidung fällt **in der Zeitzone der Börse**. Feiertage und verkürzte
Handelstage kommen aus IBKRs Handelszeiten, nicht aus einer gepflegten Liste.
Ein bereits erledigter Lauf wird nicht wiederholt, ein gescheiterter beim
nächsten Start erneut versucht. Ohne die Daten der Zielkerze entsteht **kein**
Analyse-Lauf — ein Ergebnis auf dem Stand von gestern sähe aus wie die heutige
Analyse und wäre es nicht. Die Entscheidungen dahinter stehen in
[ADR 0019](docs/adr/0019-trading-day-dispatcher.md).

Gerechnet wird über denselben Anwendungsfall wie beim manuellen Lauf.
Earnings-Filter und Research Agent hängen darin und laufen deshalb automatisch
mit. Beide stehen ausgeliefert auf `fixture`; der tägliche Lauf braucht also
weder einen Finnhub- noch einen Anthropic-Zugang, liefert dann aber auch keine
echten Termine und keine echte Recherche.

Scharf geschaltet werden sie **nicht** in `config/default.yaml`, sondern je
Lauf über Argumente:

```bash
.venv/bin/python -m ai_trading_analyst.cli dispatch --provider ibkr \
    --earnings-provider finnhub --research-provider anthropic
```

Damit trägt der Eintrag in der Aufgabenplanung die produktiven Schalter und
`git pull` findet auf dem Server keinen lokalen Diff vor — dieselbe Begründung
wie bei `--provider ibkr`. `--research-provider anthropic` löst je Kandidat
einen echten, kostenpflichtigen API-Aufruf aus.

### Eintrag in der Windows-Aufgabenplanung

Ausgelöst wird der Lauf von der Windows-Aufgabenplanung, alle 15 Minuten in
einem großzügigen Abendfenster. Der Auslöser ist dumm, das Programm
entscheidet. Das Startfenster ist die **einzige Stelle im ganzen System mit
einer deutschen Uhrzeit** und steht deshalb nicht im Code, sondern in der
Betriebsdokumentation: **[Doc 14 — Inbetriebnahme und
Betrieb](docs/14%20-%20Inbetriebnahme%20und%20Betrieb.md)**.

Dort stehen auch die Abnahme in sieben Stufen, die Rückgabewerte, mit denen die
Aufgabenplanung nur meldet was wirklich schiefging, und das Vorgehen im
laufenden Betrieb.

### Geheimnisse

```bash
cp .env.example .env
```

Anschließend die Werte in `.env` setzen. Die Datei ist von `.gitignore`
ausgeschlossen und darf nie committet werden. Alle Variablen tragen das Präfix
`ATA_`.

## Entwicklung

Alle Prüfungen laufen lokal mit denselben Befehlen wie in der CI.

```bash
# Backend
cd backend
.venv/bin/python -m pytest              # Tests
.venv/bin/python -m ruff check .        # Linting
.venv/bin/python -m mypy src tests      # Typprüfung (strict)

# Frontend
cd frontend
npm run lint
npm run typecheck
npm run build
```

### Tests mit echtem PostgreSQL

`backend/tests/integration/` prüft Persistenz, Migrationen und die REST-API
gegen echtes PostgreSQL — SQLite ist dafür bewusst kein Ersatz. Ohne
erreichbare Datenbank schlagen diese Tests mit einer klaren Fehlermeldung
fehl (kein stilles Überspringen). Lokal:

```bash
docker run -d --name ata-postgres-test \
  -e POSTGRES_USER=ata -e POSTGRES_PASSWORD=ata -e POSTGRES_DB=ata_test \
  -p 55432:5432 postgres:16-alpine

export TEST_DATABASE_URL="postgresql+psycopg://ata:ata@localhost:55432/ata_test"
cd backend && .venv/bin/python -m pytest
```

In der CI übernimmt das ein Postgres-Service-Container (`.github/workflows/ci.yml`).

### Backend lokal starten

```bash
cd backend
cp ../.env.example ../.env   # ATA_DATABASE_URL und ATA_SESSION_SECRET setzen
.venv/bin/python -m alembic upgrade head
.venv/bin/uvicorn ai_trading_analyst.main:app --reload
```

`POST /api/v1/analysis-runs` startet einen manuellen Lauf mit den Anbietern
aus `config/default.yaml` — ausgeliefert also `fixture`. Anders als die
Kommandozeile kennt der Endpunkt keine Übersteuerung je Aufruf; der produktive
Lauf läuft über `cli dispatch`.

## Konfiguration

Fachliche Werte stehen in `config/default.yaml`. Die Datei enthält keine
Geheimnisse und wird beim Start streng validiert: Unbekannte Schlüssel und in
sich widersprüchliche Werte führen zu einem Startfehler statt zu einem stillen
Default.

Ein abweichender Pfad lässt sich über `ATA_CONFIG_FILE` setzen.

Der Abschnitt `indicators` enthält die für Gate G1 fachlich freigegebenen
Parameter — siehe [ADR 0010](docs/adr/0010-gate-g1-freigegeben.md).

## Mitwirken

Es wird nie direkt auf `main` oder `dev` gearbeitet. Feature-Branches zweigen
von `dev` ab und werden per Pull Request zurückgeführt (siehe
[ADR 0002](docs/adr/0002-branching-modell.md)). Vor jedem PR laufen die
Test-Suite und eine unabhängige Code-Review.

Seit dem 2026-08-24 ist das nicht mehr nur Vereinbarung, sondern erzwungen:
`main` und `dev` sind geschützt, ein Merge braucht einen Pull Request und
fünf grüne CI-Jobs. Force-Push und Löschen sind gesperrt. Der
Repository-Inhaber behält bewusst einen Notausgang, damit ein Flake ihn nicht
aus seinem eigenen Repository aussperrt — was das im Einzelnen heißt und was
dabei *nicht* erzwungen wird, steht in
[ADR 0031](docs/adr/0031-merge-schutz-aktiv.md), das
[ADR 0009](docs/adr/0009-required-checks-nicht-konfigurierbar.md) ablöst.

Die dort beschriebene Interimsregel bleibt trotzdem sinnvoll: `gh pr checks
<nummer>` zeigt einen Fehlschlag früher als ein blockierter Merge-Knopf.
