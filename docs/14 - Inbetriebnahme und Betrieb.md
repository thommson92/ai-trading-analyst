# Inbetriebnahme und Betrieb

Zielumgebung ist der Windows Server, auf dem auch die TWS läuft. Dieses
Dokument ist die Abnahme- und Betriebsanleitung: Was einmalig einzurichten ist,
in welcher Reihenfolge abgenommen wird, und was im laufenden Betrieb zu tun
bleibt.

Die fachlichen Entscheidungen dahinter stehen in
[ADR 0014](adr/0014-ibkr-produktivintegration-freigegeben.md) (IBKR als
Datenquelle), [ADR 0018](adr/0018-kein-windows-autologon.md) (kein Autologon)
und [ADR 0019](adr/0019-trading-day-dispatcher.md) (Dispatcher).

---

# Grundsatz der Abnahme

Die Stufen werden **in dieser Reihenfolge** abgenommen, und jede hat ein
Abbruchkriterium. Schlägt eine Stufe fehl, wird nicht weitergegangen — sonst
treten Fehler aus Konfiguration, Datenbank, TWS und Kerzenbildung gleichzeitig
auf und lassen sich nicht mehr auseinanderhalten.

Alle Befehle laufen in PowerShell aus dem Verzeichnis `backend`.

---

# Stufe A — Umgebung

Voraussetzung: Python 3.12 und PostgreSQL sind installiert.

```powershell
py -3.12 --version
Get-Service -Name postgresql*
git pull
```

Die virtuelle Umgebung gegen die **aktuelle** Lock-Datei nachziehen. Das ist
auch dann nötig, wenn sie schon existiert: Mit dem Research Agent sind
Abhängigkeiten dazugekommen.

```powershell
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock.txt
.venv\Scripts\python.exe -m pip install --no-deps -e .
```

Installiert wird ausschließlich über die Lock-Datei mit Hash-Verifikation, nie
über eine Versionsauflösung auf dem Server
([ADR 0008](adr/0008-reproduzierbare-installation.md)).

**Abbruch, wenn:** die Installation Hash-Fehler meldet. Dann ist die Lock-Datei
nicht die, die zum ausgecheckten Stand gehört.

---

# Stufe B — Datenbank und Geheimnisse

Datenbank und Rolle anlegen, falls noch nicht vorhanden:

```powershell
psql -U postgres -c "CREATE ROLE ata WITH LOGIN PASSWORD '<passwort>';"
psql -U postgres -c "CREATE DATABASE ai_trading_analyst OWNER ata;"
```

Die `.env` gehört ins **Projektwurzelverzeichnis**, nicht nach `backend`. Sie
wird von dort gelesen, unabhängig davon, aus welchem Verzeichnis ein Kommando
startet.

```powershell
copy ..\.env.example ..\.env
```

Für den Betrieb ist genau eine Variable zwingend:

| Variable | Wann nötig |
|---|---|
| `ATA_DATABASE_URL` | **immer** |
| `ATA_FINNHUB_API_KEY` | erst ab Stufe G, Schritt 1 |
| `ATA_LLM_API_KEY` | erst ab Stufe G, Schritt 2 |
| `ATA_SESSION_SECRET` | erst mit dem Dashboard — heute ohne Wirkung |
| `ATA_NOTIFICATION_TOKEN` | erst mit dem Kanal F10 — noch nicht entschieden |

Die `.env` ist von `.gitignore` ausgeschlossen und darf nie committet werden.

Dann das Schema:

```powershell
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic current
```

**Abbruch, wenn:** `alembic current` nicht `01b2e8681b7a` meldet, oder wenn
Alembic mehr als einen Head sieht.

> **Falle:** Meldet Alembic „Revision … is present more than once" oder mehrere
> Heads, liegen Dubletten im Verzeichnis `migrations/versions/` — typischerweise
> Kopien nach dem Muster `…_backtest_results 2.py`, wie Sync- und Kopierwerkzeuge
> sie anlegen. Sie registrieren dieselbe Revision ein zweites Mal und lassen
> `upgrade head` mit „Multiple head revisions are present" scheitern. Solche
> Dateien sind zu entfernen; `git status` zeigt sie als untracked an.

---

# Stufe C — Trockenlauf ohne TWS

Beweist die Kette Konfiguration → Watchlist → Domain → Datenbank, bevor die TWS
als Fehlerquelle dazukommt.

Zuerst die Watchlist. Sie kontaktiert die TWS nicht und liest nur die Dateien
aus `watchlists/`:

```powershell
.venv\Scripts\python.exe -m ai_trading_analyst.cli watchlist
```

Dann ein vollständiger Analyse-Lauf ohne externe Abhängigkeit. Der Weg dahin
führt über die API, nicht über die Kommandozeile: `cli screen` ist das
IBKR-Kommando und weist einen Lauf mit `fixture` ausdrücklich ab
(Rückgabewert 2), weil es sonst mit dem ausgelieferten Standard eine
TWS-Verbindung aufbaute. `POST /api/v1/analysis-runs` dagegen läuft mit den
Anbietern aus der Konfiguration — ausgeliefert also `fixture` — und legt das
Ergebnis in PostgreSQL ab.

```powershell
# In einem ersten Fenster:
.venv\Scripts\uvicorn.exe ai_trading_analyst.main:app

# In einem zweiten:
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/api/v1/system/readiness
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/analysis-runs
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/api/v1/analysis-runs
```

`readiness` muss `ready` und `ok` melden — damit ist die Datenbank
nachgewiesen erreichbar. Der `POST` liefert den angelegten Lauf zurück, der
abschließende `GET` zeigt ihn in der Liste.

**Abbruch, wenn:** die Watchlist leer ist, `readiness` nicht `ready` meldet oder
der `POST` keinen Analyse-Lauf zurückgibt.

---

# Stufe D — Erster TWS-Kontakt

Die TWS braucht eine **angemeldete Sitzung** und wird nach dem sonntäglichen
Neustart von Hand gestartet ([ADR 0018](adr/0018-kein-windows-autologon.md),
[ADR 0014](adr/0014-ibkr-produktivintegration-freigegeben.md), Einschränkung E2).

Einstellungen → API → Settings:

- **"Enable ActiveX and Socket Clients"** aktivieren.
- **Client-ID 17 freihalten.** Läuft an derselben TWS eine weitere Anwendung,
  braucht jede ihre eigene ID (Trade Automation Toolbox: 99).
- **"Read-Only API" nicht aktivieren**, solange eine andere Anwendung über
  dieselbe TWS echte Orders überträgt — der Schalter gilt TWS-weit und würde
  auch sie blockieren. Dass der Analyzer nur liest, ist in seinem Code
  verankert, nicht in dieser Einstellung.
- Port 7496 (TWS Live). Paper 7497, IB Gateway 4001 bzw. 4002.

Erster Abruf bewusst mit **einem** Symbol, damit ein Fehler in Sekunden statt in
einer halben Stunde sichtbar wird:

```powershell
.venv\Scripts\python.exe -m ai_trading_analyst.cli screen --provider ibkr `
    --source live --symbols AAPL --details --no-pacing
```

`--details` zeigt Schlusskurs, RSI, RSI-MA, EMA5 und EMA20 der letzten Kerze.
**Diese Werte gegen den Chart abgleichen.** Das ist die Gelegenheit, die
freigegebenen Gate-G1-Parameter ([ADR 0010](adr/0010-gate-g1-freigegeben.md))
gegen die Realität zu prüfen, bevor sie in einen Bestand einfließen.

**Abbruch, wenn:** die Indikatorwerte vom Chart abweichen. Dann ist zuerst zu
klären, ob die Kerzenbildung oder die Parametrisierung abweicht — kein Backfill
auf zweifelhafter Rechnung.

---

# Stufe E — Historischer Backfill

```powershell
.venv\Scripts\python.exe -m ai_trading_analyst.cli backfill --provider ibkr
```

IBKR lässt 60 Historienanfragen je zehn Minuten zu und sperrt bei Überschreitung
die Verbindung. Zwischen zwei Anfragen liegen deshalb 11 Sekunden; bei rund 190
Symbolen dauert ein vollständiger Lauf gut eine halbe Stunde. Die TWS muss
durchgehend stehen.

Ein Abbruch ist unkritisch: Das Speichern ist über `(symbol, start)` idempotent,
ein erneuter Start holt nur die Lücke. Aufzuräumen gibt es nichts.

Auf zwei Meldungen achten, die der Backfill selbst ausgibt:

- **Gekürzte Antwort** — die Antwort enthält deutlich weniger Historie als
  angefragt. So kürzt IBKR stillschweigend.
- **Späterer Ansatz** — die Antwort beginnt *später* als der letzte gespeicherte
  Bar. Dann klafft zweifelsfrei eine Lücke dazwischen.

Beides wird gezielt nachgeholt:

```powershell
.venv\Scripts\python.exe -m ai_trading_analyst.cli backfill --provider ibkr `
    --symbols AAPL --from 2026-01-01
```

`--from` füllt nur, was fehlt. Bereits gespeicherte Bars bleiben unverändert —
die Ablage lässt Dubletten fallen, damit ein wiederholter Lauf nichts anrichtet.

> **Reichweite des Bestands:** Der erste Lauf holt den konfigurierten Zeitraum
> (`market_data.ibkr.history_duration`, ausgeliefert `1 Y`). Für den täglichen
> Lauf genügt das mit Abstand — der Warm-up braucht 250 Kerzen, also rund 125
> Handelstage. Für die Aussagekraft der Backtest-Kennzahlen ist es weniger, als
> `backtesting.history_years` (5) unterstellt. Ob die Historie verlängert wird,
> ist eine eigene Entscheidung und kein Teil der Inbetriebnahme.

**Abbruch, wenn:** mehr als eine Handvoll Symbole ohne Daten zurückkommt.

---

# Stufe F — Erster Tageslauf und Aufgabenplanung

An einem Handelstag **zwischen 12:50 und 14:50 New Yorker Zeit** von Hand.
Beide Grenzen sind echt: Vor 12:50 ist der Sicherheitspuffer nach Kerzenschluss
noch nicht abgelaufen und der Lauf meldet „zu früh" (Rückgabewert 0, aber ohne
Ergebnis); nach 14:50 ist die Nachholfrist
(`scheduler.max_catch_up_seconds`, zwei Stunden) abgelaufen, und der Lauf endet
mit Rückgabewert 1 samt Überfälligkeitsmeldung.

```powershell
.venv\Scripts\python.exe -m ai_trading_analyst.cli dispatch --provider ibkr
echo $LASTEXITCODE
```

Erwartet: Rückgabewert 0 und ein neuer Analyse-Lauf in der Datenbank.
Anschließend **denselben Aufruf ein zweites Mal** — er muss sofort und ohne
zweiten Lauf enden. Das prüft die Idempotenz über `dispatcher_runs`.

## Eintrag in der Windows-Aufgabenplanung

Das ist die **einzige Stelle im ganzen System mit einer deutschen Uhrzeit**, und
sie steht bewusst hier und nicht im Code.

| Feld | Wert |
|---|---|
| Trigger | Täglich, Mo–Fr, Beginn **17:30**, Wiederholung alle **15 Minuten** für **4 Stunden** |
| Programm | `C:\...\backend\.venv\Scripts\python.exe` |
| Argumente | `-m ai_trading_analyst.cli dispatch --provider ibkr` |
| Starten in | `C:\...\backend` |

Das Fenster ist absichtlich großzügig: 12:50 New Yorker Zeit liegen normalerweise
auf 18:50 unserer Zeit, in den zwei bis drei Wochen, in denen die USA und Europa
an verschiedenen Tagen umstellen, aber auf 17:50. Beide Fälle liegen darin.

Der Auslöser ist dumm, das Programm entscheidet: Der Dispatcher rechnet in
`America/New_York`, holt Feiertage und verkürzte Handelstage aus IBKRs
Handelszeiten und endet an den meisten Starts nach wenigen Millisekunden.

## Rückgabewerte

| Wert | Bedeutung |
|---|---|
| 0 | Lauf durchgeführt — oder nichts zu tun (zu früh, kein Handelstag, bereits erledigt) |
| 1 | Versucht und gescheitert (Daten unvollständig, TWS nicht erreichbar), oder Nachholfrist abgelaufen |
| 2 | Konfigurations- oder Umgebungsfehler; erneutes Starten hilft nicht |
| 130 | Abgebrochen |

„Nichts zu tun" ist bewusst 0: Bei 15-Minuten-Takt wäre alles andere ein
Protokoll voller Fehlschläge, in dem der echte nicht mehr auffiele. Die
Aufgabenplanung meldet damit nur, was wirklich schiefging.

**Abnahmekriterium:** Ein vollständiger Handelstag ohne manuellen Eingriff.

---

# Stufe G — Produktive Anbieter

Erst wenn Stufe F über mindestens einen Handelstag trägt. Beide Anbieter stehen
in `config/default.yaml` auf `fixture` und werden **nicht dort** umgestellt: Der
produktive Schalter gehört in die Argumente der Aufgabenplanung, damit ein
`git pull` auf dem Server keinen lokalen Diff vorfindet.

## Schritt 1 — Earnings-Termine über Finnhub

> **Erst die Aufgabenplanung anhalten.** Seit Stufe F läuft sie alle 15 Minuten
> und hat den Tageslauf um diese Uhrzeit meistens schon erledigt. Ein manueller
> Aufruf endete dann mit „bereits erledigt" und Rückgabewert 0, ohne Finnhub
> auch nur anzufassen — der Schritt sähe grün aus und hätte nichts geprüft.

`ATA_FINNHUB_API_KEY` setzen, die Aufgabe in der Aufgabenplanung deaktivieren,
dann im Fenster zwischen 12:50 und 14:50 New Yorker Zeit von Hand:

```powershell
.venv\Scripts\python.exe -m ai_trading_analyst.cli dispatch --provider ibkr `
    --earnings-provider finnhub
```

Ist der Tageslauf bereits erledigt, hilft nur der nächste Handelstag — ein
erledigter Lauf wird nicht wiederholt, und das ist beabsichtigt.

Danach die Aufgabe mit dem ergänzten Argument wieder aktivieren.

Quelle und akzeptierte Einschränkungen stehen in
[ADR 0017](adr/0017-finnhub-fuer-earnings-und-ratings.md), das Statusmodell in
[ADR 0020](adr/0020-earnings-filter-status-und-handelstagskalender.md). Die
kostenlose Stufe genügt.

Ein fehlender oder leerer Schlüssel bricht den Lauf **vor** dem Backfill ab
(Rückgabewert 2). Das ist Absicht: Erst dahinter bemerkt, hätte er eine halbe
Stunde lang Daten geholt und dann einen Abend voller degradierter Kandidaten
erzeugt.

## Schritt 2 — Research Agent über Anthropic

Zuerst eine **Einzelprobe** mit sichtbarer Kostenschätzung, nicht gleich der
ganze Lauf:

```powershell
.venv\Scripts\python.exe -m ai_trading_analyst.cli research --provider anthropic `
    --symbol AAPL
```

Ein echter Aufruf kostet Geld. Das Budget je Aktie steht in `config/default.yaml`
unter `research` und ist in [ADR 0023](adr/0023-research-agent-zitierarchitektur.md)
begründet; die Notbremse zwischen zwei Anfragen ist
`max_input_tokens_per_symbol`.

Erst danach in die Aufgabenplanung übernehmen:

```
-m ai_trading_analyst.cli dispatch --provider ibkr --earnings-provider finnhub --research-provider anthropic
```

---

# Laufender Betrieb

## Nach jedem Serverneustart

Die TWS von Hand starten und anmelden. Ohne angemeldete Sitzung entscheidet der
Dispatcher nicht einmal, ob heute ein Handelstag ist — er meldet Rückgabewert 1
und versucht es beim nächsten Start erneut, bis die Nachholfrist abläuft.

## Wenn ein Tageslauf ausbleibt

Überschreitet ein unerledigter Lauf die Nachholfrist
(`scheduler.max_catch_up_seconds`, ausgeliefert zwei Stunden, also 14:50 New
Yorker Zeit), geht eine Meldung raus. **Der Kanal ist noch nicht entschieden
(F10);** bis dahin erscheint sie im Protokoll, ausdrücklich als *nicht versendet*
gekennzeichnet. Ein stiller Ausfall wird deshalb heute nur beim Blick ins
Protokoll sichtbar — das ist die wichtigste offene Lücke des Betriebs.

Die Frist liegt bewusst **innerhalb** des Startfensters; wer eines von beiden
verschiebt, muss das andere mitziehen. Ein Test hält die Bedingung fest.

## Was der Dispatcher bewusst nicht tut

Er erzeugt **keinen** Analyse-Lauf auf dem Stand des Vortages. Ein solcher Lauf
sähe aus wie die heutige Analyse und wäre es nicht. Das gilt auch beim
Teilausfall: Erledigt ist ein Lauf erst ab `scheduler.minimum_completion_ratio`
gerechneter Aktien (ausgeliefert 0,9); darunter zählt er wie ein TWS-Ausfall und
wird wiederholt.

## Aktualisierung

```powershell
git pull
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock.txt
.venv\Scripts\python.exe -m pip install --no-deps -e .
.venv\Scripts\python.exe -m alembic upgrade head
```

Findet `git pull` einen lokalen Diff in `config/default.yaml`, wurde auf dem
Server konfiguriert statt in der Aufgabenplanung — siehe Stufe G.
