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

**Sprint 2 — Marktdaten.** Toolchain, Konfiguration, Logging, Schichtstruktur
und CI stehen (Sprint 0 Teil A). Gate G1 ist fachlich freigegeben
([ADR 0010](docs/adr/0010-gate-g1-freigegeben.md)); die drei Signalregeln und
die 2-aus-3-Kandidatenregel sind als reiner Domain-Code implementiert
(`backend/src/ai_trading_analyst/domain/screening`, Tag `sprint-1a-baseline`).
Die durchgehend lauffähige Kette aus Sprint 1B steht: Marktdatenanbieter →
Application Use Case → Screener → PostgreSQL → REST API (`/api/v1`).

Als Datenquelle ist **Interactive Brokers** freigegeben
([ADR 0014](docs/adr/0014-ibkr-produktivintegration-freigegeben.md), technisch
`GO_WITH_LIMITATIONS`, vertraglich `GO`); TradingView ist mit **NO_GO**
ausgeschieden ([ADR 0012](docs/adr/0012-gate-g3-strang-a-no-go-non-display-nutzung.md)).
Der `IbkrMarketDataProvider` baut aus nativen 15-Minuten-Bars abgeschlossene
195-Minuten-Kerzen und berechnet RSI, RSI-MA, EMA5 und EMA20 selbst. Welcher
Anbieter läuft, entscheidet `market_data.provider` in `config/default.yaml`;
der Standard bleibt `fixture`.

Noch offen: Watchlist-Import aus IBKR, historischer Backfill, Scheduler,
Frontend-Ausbau.

Bewusst noch nicht begonnen:

| Thema | Blockiert durch |
|---|---|
| Earnings-Termine | Anbieterwahl offen — IBKR liefert sie nicht (ADR 0014, E1) |
| KI-Integration | ADR ausstehend |

## Struktur

```
backend/          Python 3.12, FastAPI-Anwendung
  src/ai_trading_analyst/
    domain/         Fachregeln, Provider-Schnittstellen (ohne Infrastruktur)
      screening/      Signalregeln, 2-aus-3-Kandidatenregel (Gate G1),
                      Indikatorberechnung, 195-Minuten-Kerzenbildung
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
docs/             Fachdokumente 01–13
docs/adr/         Architecture Decision Records
```

Bei Widersprüchen zwischen den Fachdokumenten ist
`docs/10 - System Architecture.md` maßgeblich (siehe
[ADR 0001](docs/adr/0001-dokumentenhierarchie.md)).

## Einrichtung

Vorausgesetzt: Python 3.12, Node.js 20+.

### Backend

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install --require-hashes -r requirements-dev.lock.txt
.venv/bin/pip install --no-deps -e .
```

Die Installation läuft ausschließlich über die Lock-Datei mit Hash-Verifikation
— keine Versionsauflösung auf dem jeweiligen Rechner. Siehe
[ADR 0008](docs/adr/0008-reproduzierbare-installation.md).

Ändert sich `pyproject.toml`, werden die Lock-Dateien neu erzeugt:

```bash
.venv/bin/pip install "pip-tools>=7.4,<8"
.venv/bin/pip-compile --generate-hashes --output-file=requirements.lock.txt pyproject.toml
.venv/bin/pip-compile --generate-hashes --extra=dev --output-file=requirements-dev.lock.txt pyproject.toml
```

### Frontend

```bash
cd frontend
npm ci
```

`npm ci` installiert exakt die in `package-lock.json` festgeschriebenen
Versionen und bricht ab, wenn `package.json` und die Lock-Datei
auseinanderlaufen — im Gegensatz zu `npm install` also reproduzierbar.

### Marktdaten über Interactive Brokers

Der produktive Anbieter wird ausdrücklich eingeschaltet — der Standard bleibt
`fixture`:

```yaml
market_data:
  provider: ibkr
  ibkr:
    watchlist:
      - symbol: AAPL
```

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

`POST /api/v1/analysis-runs` startet in Sprint 1B ausschließlich einen
fixture-basierten manuellen Lauf (`FixtureMarketDataProvider`) — noch keine
produktiven Marktdaten.

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

**Bekannte Einschränkung:** Required Status Checks lassen sich für dieses
private Repository im aktuellen GitHub-Plan nicht konfigurieren (weder über
Branch Protection noch über Rulesets — beide verlangen GitHub Pro oder ein
öffentliches Repository). Bis das geklärt ist, gilt ersatzweise: kein Merge
ohne vorher geprüfte grüne CI (`gh pr checks <nummer>`). Details und die
vorbereitete Konfiguration in
[ADR 0009](docs/adr/0009-required-checks-nicht-konfigurierbar.md).
