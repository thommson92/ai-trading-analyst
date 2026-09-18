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

Voraussetzung: Python 3.13 und PostgreSQL sind installiert. Auf dem
Entwicklungsrechner laeuft 3.12 -- `requires-python` laesst beide zu, und die
CI prueft beide. Wer hier 3.12 einrichtet, bekommt eine Umgebung, die nicht
der geprueften Serverumgebung entspricht.

```powershell
py -3.13 --version
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
| `ATA_EDGAR_CONTACT` | sobald `fundamentals.provider` auf `edgar` steht |
| `ATA_LLM_API_KEY` | erst ab Stufe G, Schritt 2 |
| `ATA_SESSION_SECRET` | erst mit dem Dashboard — heute ohne Wirkung |
| `ATA_NOTIFICATION_TOKEN` | erst ab Stufe H (Telegram, [ADR 0024](adr/0024-benachrichtigungskanal-telegram.md)) |

Die `.env` ist von `.gitignore` ausgeschlossen und darf nie committet werden.

`ATA_EDGAR_CONTACT` ist die Kontaktadresse, die die SEC im `User-Agent`
verlangt — **kein Zugangsdatum**, EDGAR kennt keinen Schlüssel. Sie steht
trotzdem hier und nicht in `config/default.yaml`: Dieses Repository ist
öffentlich, und eine private Mailadresse gehört nicht hinein. Ohne sie
antwortet die SEC mit 403; der Tageslauf bricht deshalb ab, **bevor** der
halbstündige Backfill beginnt, statt danach.

**Seit ADR 0043 hat sich der Finnhub-Abschnitt verschoben.** Host und
Zeitgrenze stehen jetzt unter `finnhub:` statt unter `earnings_filter.finnhub`,
weil sie zwei Endpunkten gehören. Wer eine eigene Konfigurationsdatei über
`ATA_CONFIG_FILE` einsetzt, muss sie nachziehen — der alte Schlüsselort lässt
den Start mit einem Fehler über einen unbekannten Konfigurationsschlüssel
abbrechen, statt still auf Voreinstellungen zurückzufallen.

Stand bis zum 2026-08-30 war die Adresse von Hand in `config/default.yaml`
eingetragen. Wer diesen Zustand auf dem Server noch vorfindet, verwirft die
lokale Änderung und setzt stattdessen die Variable — eine wieder eingefügte
`contact`-Zeile lässt den Start jetzt mit einem Fehler über einen unbekannten
Konfigurationsschlüssel abbrechen.

Dann das Schema:

```powershell
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic current
```

**Abbruch, wenn:** `alembic current` nicht den **aktuellen Head der
Migrationskette** meldet, oder wenn Alembic mehr als einen Head sieht. Welche
Revision das ist, sagt das Repository selbst — die Anleitung nennt bewusst keine
feste Kennung, weil jede weitere Migration sie überholt:

```powershell
.venv\Scripts\python.exe -m alembic heads
```

Die Ausgabe von `alembic heads` und die von `alembic current` müssen dieselbe
Revision nennen. **Welche Kennung das ist, spielt keine Rolle** — sie ändert
sich mit jeder neuen Migration, und dieses Dokument nennt sie deshalb
absichtlich nicht mehr. Maßgeblich ist allein, dass beide Befehle dasselbe
melden und dass `alembic heads` genau eine Zeile ausgibt.

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

Dann die Datenbank durch die Anwendung hindurch:

```powershell
# In einem ersten Fenster:
.venv\Scripts\python.exe -m uvicorn ai_trading_analyst.main:app

# In einem zweiten:
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/api/v1/system/readiness
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/api/v1/analysis-runs
```

`readiness` muss `ready` und `ok` melden — damit ist die Datenbank
nachgewiesen über die Anwendung erreichbar, nicht nur über `psql`. Der `GET`
antwortet auf einer frischen Installation mit einer leeren Seite
(`total: 0`); das ist der Beweis, dass der Lesepfad steht.

> **Diese Stufe erzeugt seit dem 2026-09-01 keinen Analyse-Lauf mehr.** Sie
> tat es über `POST /api/v1/analysis-runs`, und diesen Endpunkt gibt es nicht
> mehr: Er lief mit den Anbietern aus der Konfiguration — auf dem Server also
> den Fixtures — und hätte einen Lauf aus erfundenen Werten in die
> Produktivdatenbank geschrieben, ununterscheidbar von einem echten
> ([ADR 0053](adr/0053-lese-api-kein-lauf-ueber-http.md)). Über die
> Kommandozeile geht es nicht: `cli screen` und `cli dispatch` sind
> IBKR-Kommandos und weisen einen Lauf mit `fixture` ausdrücklich ab
> (Rückgabewert 2).
>
> Die Kette Konfiguration → Watchlist → Domain → PostgreSQL ist damit auf
> diesem Rechner nicht mehr *vor* der TWS bewiesen, sondern erst in Stufe F.
> Geprüft ist sie weiterhin — `backend/tests/integration/test_full_run.py`
> fährt genau diese Kette mit Fixtures gegen ein echtes PostgreSQL, in jedem
> CI-Lauf. Wer den Beweis auch auf dem Server will, braucht dafür ein eigenes
> Kommando; es gibt bewusst keines.

**Abbruch, wenn:** die Watchlist leer ist oder `readiness` nicht `ready`
meldet.

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
> `backtesting.history_years` (5) unterstellt. Wie damit umzugehen ist, steht in
> [ADR 0027](adr/0027-historientiefe-messen-vor-anspruch.md) — gemessen wird
> zuerst, siehe den nächsten Abschnitt. Kein Teil der Inbetriebnahme.

**Abbruch, wenn:** mehr als eine Handvoll Symbole ohne Daten zurückkommt.

## Zwischenschritt: Historientiefe messen (optional)

Kein Abnahmekriterium. Das Kommando beantwortet die offene Frage aus
[ADR 0027](adr/0027-historientiefe-messen-vor-anspruch.md): Wie weit gibt IBKR
die Historie in 15-Minuten-Auflösung überhaupt her? Es **legt nichts ab** und
braucht deshalb keine Datenbank — nur die laufende TWS.

```powershell
.venv\Scripts\python.exe -m ai_trading_analyst.cli history-depth --provider ibkr `
    --symbols AAPL,MSFT,KO
```

Drei Titel genügen, und die Auswahl ist nicht beliebig: Ein lange notierter
Standardwert zeigt die Grenze des Anbieters, eine jüngere Notierung zeigt nur
ihre eigene kurze Börsenhistorie. Ohne `--symbols` nimmt das Kommando die
ersten drei Titel der Watchlist; ausdrücklich genannte Symbole werden dagegen
alle gemessen — die Zahl begrenzt nur `--limit`.

Das Kommando arbeitet sich je Aktie Fenster für Fenster zurück, bis IBKR nichts
mehr liefert. Mit dem ausgelieferten Abstand von 11 Sekunden dauert das für drei
Titel wenige Minuten; die Laufzeitschätzung steht vor dem ersten Abruf am
Bildschirm.

Entscheidend ist die Spalte **Grenze** im Bericht:

| Grenze | Bedeutung |
|---|---|
| `provider_exhausted` | IBKR gab nichts mehr her — das ist die gesuchte Tiefe |
| `no_progress` | IBKR antwortete, kam aber nicht weiter zurück — auch hier ist Schluss |
| `window_limit` | die eigene Reißleine hat gegriffen — die Tiefe ist nur eine **Untergrenze**, mit `--max-windows` höher ansetzen |
| `error` | Abruf gescheitert — ebenfalls nur eine Untergrenze, die Meldung steht darunter |

Das Ergebnis der ersten Messung steht in
[ADR 0028](adr/0028-historientiefe-gemessen.md): mindestens 17,4 Jahre, alle
drei Titel an der Reißleine. `backtesting.history_years: 5` ist damit belegt
und bleibt.

## Zwischenschritt: Tiefen-Backfill (einmalig, Wochenendlauf)

Der Batch aus [ADR 0028](adr/0028-historientiefe-gemessen.md). Er füllt den
Bestand **rückwärts** auf `backtesting.history_years` auf — der tägliche
`backfill` verlängert ihn nach vorn, dieser nach hinten.

Erst ein Probelauf über wenige Titel:

```powershell
.venv\Scripts\python.exe -m ai_trading_analyst.cli deepen-history --provider ibkr `
    --symbols AAPL,MSFT
```

Dann die volle Watchlist. **Das dauert rund elf Stunden** — 190 Aktien × 5
Fenster bei 11 Sekunden Abstand und etwa 30 Sekunden Übertragung je Fenster.
Der Lauf gehört auf einen Freitagabend:

```powershell
.venv\Scripts\python.exe -m ai_trading_analyst.cli deepen-history --provider ibkr
```

**Ein Abbruch ist unkritisch, und zwar ausdrücklich auch der nächtliche
TWS-Neustart.** Jedes Fenster wird sofort abgelegt; der Ansatzpunkt ist der
älteste gespeicherte Bar und wandert mit jedem Fenster zurück. Ein erneuter
Start setzt genau dort an. Aufzuräumen gibt es nichts.

Ein zweiter Lauf kostet für jede Aktie, die den Zielzeitraum **erreicht hat**,
keine einzige Anfrage: Sie meldet „war schon tief genug". Das Kommando lässt
sich deshalb bedenkenlos wiederholen, solange noch Aktien fehlgeschlagen sind.

Eine Ausnahme, die man kennen muss: Aktien, deren Börsenhistorie **kürzer** ist
als der Zielzeitraum, erreichen ihn nie. Sie kosten bei jedem Wiederholen eine
Anfrage und bleiben dauerhaft in der Liste „Unter dem Zielzeitraum" stehen.
Das ist richtig so — der Lauf kann nicht wissen, ob IBKR morgen mehr liefert —,
aber es heißt: **Nicht wiederholen, bis diese Liste leer ist.** Sie wird es bei
einer jungen Notierung nie. Maßgeblich ist allein die Zeile
„Fehlgeschlagen".

Am Ende auf zwei Zeilen achten:

- **Fehlgeschlagen** — Aktien, bei denen Abruf oder Ablage scheiterten.
  Einfach erneut starten; sie setzen dort an, wo sie aufhörten.
- **Unter dem Zielzeitraum** — Aktien, für die IBKR nicht so weit zurück
  liefert. Bei einer Neuemission erwartbar und **kein Fehler**: Die
  Kennzahlen dieser Aktien tragen ihren tatsächlichen `history_start`.

Der Bestand wächst dabei erheblich — rund 33.000 Bars je Aktie für fünf
Jahre, bei voller Watchlist etwa 6,3 Millionen Zeilen. Für PostgreSQL
unkritisch, aber beim Sichern zu bedenken.

## Zwischenschritt: Datenausschnitt für den Golden Master ziehen (optional)

Ebenfalls kein Abnahmekriterium. Der Golden Master
(`backend/tests/golden`) bewacht das Rechenverfahren von Screener und
Backtest gegen unbeabsichtigte Änderungen. Seine eingefrorenen Bars sind
**erzeugt, nicht gemessen** — der reale Bestand liegt nur hier auf dem
Server. Ein echter Ausschnitt lässt sich danebenlegen:

```powershell
.venv\Scripts\python.exe -m ai_trading_analyst.cli export-bars `
    --symbols AAPL,MSFT --output tests\golden\data --since 2025-01-02
```

Das Kommando liest nur; der Bestand bleibt unverändert. Je Symbol entsteht
eine `<symbol>.bars.csv`. Danach einmalig aufzeichnen und beides committen —
**auf einem kleinen Branch mit Pull Request**, nicht direkt: `dev` ist
geschützt ([ADR 0031](adr/0031-merge-schutz-aktiv.md)), ein Commit darauf
würde beim Push abgewiesen:

```powershell
$env:ATA_GOLDEN_MASTER_RECORD = "1"
.venv\Scripts\python.exe -m pytest tests\golden
Remove-Item Env:\ATA_GOLDEN_MASTER_RECORD
```

Die Reihe muss über 250 Kerzen hinausreichen — darunter antwortet die
Kandidatenprüfung ausnahmslos mit `UNKNOWN_DATA_INCOMPLETE`, und die
Aufzeichnung enthielte nichts. Ein Test hält das fest.

## Zwischenschritt: Contract-Antworten einfrieren (einmalig, A2-M7)

Ebenfalls kein Abnahmekriterium — aber der Schritt, der eine ganze
Fehlerklasse abdeckt, die heute niemand bemerken würde: **die stille
Formatänderung eines Anbieters.** Alle Adaptertests laufen gegen
selbstgeschriebene Antworten. Benennt Finnhub morgen ein Feld um, sind sie
weiterhin grün, und der Tageslauf liefert `INSUFFICIENT_DATA`. Für EDGAR ist
je eine echte Antwort eingefroren
(`backend/tests/unit/infrastructure/edgar/data/`); für Finnhub und die
IBKR-Optionskette fehlt sie.

Die Dateien werden hier auf dem Server gezogen, weil hier die Zugänge liegen
— und wie beim Golden Master **auf einem kleinen Branch mit Pull Request**,
nicht direkt auf `dev` ([ADR 0031](adr/0031-merge-schutz-aktiv.md)).

### Die beiden Finnhub-Antworten

Reines HTTP, also genügt `curl.exe`. Der Schlüssel steht seit
[ADR 0044](adr/0044-geheimnisse-an-der-log-senke-schwaerzen.md) im Kopf, nicht
in der Adresse — er landet damit **weder in der Datei noch in der
Kommandohistorie der Shell**. `-o` statt einer Umleitung, damit die Bytes
unverändert ankommen.

> **Der Schlüssel steht in der `.env`, nicht in der Umgebung der Shell.** Die
> Anwendung liest ihn über `Secrets`; `curl` tut das nicht. Ohne die erste
> Zeile unten geht ein **leerer** Header hinaus, und Finnhub antwortet
> `{"error":"Please use an API key."}` — in die Zieldatei, nicht auf den
> Bildschirm. Am 2026-09-01 auf dem Server genau so passiert.

```powershell
$env:ATA_FINNHUB_API_KEY = (Select-String -Path ..\.env `
    -Pattern '^\s*ATA_FINNHUB_API_KEY\s*=\s*(.+)$').Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'")

$ziel = "tests\unit\infrastructure\finnhub\data"
New-Item -ItemType Directory -Force -Path $ziel | Out-Null
$von = (Get-Date).ToString("yyyy-MM-dd")
$bis = (Get-Date).AddDays(90).ToString("yyyy-MM-dd")

curl.exe -s -H "X-Finnhub-Token: $env:ATA_FINNHUB_API_KEY" `
    -o "$ziel\calendar-earnings-AAPL.json" `
    "https://finnhub.io/api/v1/calendar/earnings?symbol=AAPL&from=$von&to=$bis"

curl.exe -s -H "X-Finnhub-Token: $env:ATA_FINNHUB_API_KEY" `
    -o "$ziel\recommendation-AAPL.json" `
    "https://finnhub.io/api/v1/stock/recommendation?symbol=AAPL"
```

Beide Dateien vor dem Commit **ansehen** (`Get-Content`): Enthält der Kalender
im gewählten Fenster keinen Termin, ist die Liste leer — dann ist die
Aufzeichnung wertlos und das Fenster gehört verlängert oder ein anderes Symbol
gewählt. Und ein `-s`-`curl` schreibt auch eine Fehlerantwort klaglos in die
Datei; sie fällt nur beim Hinsehen auf.

### Die IBKR-Optionskette

Für die TWS gibt es kein `curl`. Der Mitschnitt hängt deshalb im Programm
zwischen Adapter und Schnittstelle und schreibt weg, was auf die drei Abrufe
zurückkam. Er ist **passiv**: Ein Lauf mit `--record` und einer ohne liefern
dieselbe Analyse.

Bei laufender TWS, im Fenster zwischen 12:50 und 14:50 New Yorker Zeit —
außerhalb liefert der Live-Modus keine Greeks mehr:

```powershell
.venv\Scripts\python.exe -m ai_trading_analyst.cli options --symbol AAPL `
    --provider ibkr --market-data-provider ibkr `
    --record tests\unit\infrastructure\ibkr\data\optionskette-AAPL.json
```

Bricht der Lauf ab, weil kein Verfallstermin im Fenster liegt, entsteht die
Datei trotzdem — dann mit der Terminliste und ohne Notierungen. Auch das ist
ein brauchbarer Fall, aber kein vollständiger: Für den Contract-Test wird
eine Aufzeichnung **mit** `option_quotes` gebraucht.

Die Datei enthält Kurse und Kontraktdaten eines öffentlich gehandelten
Papiers — nichts Kontobezogenes, keine Zugangsdaten, keine Order.

## Zwischenschritt: Reichweite des Handelskalenders messen (optional)

Kein Abnahmekriterium, sondern die Messung, die die Entscheidung E4 getragen
hat. Sie ist gefallen: Der Kalender reicht nicht, die Wochentagsnäherung
bleibt ([ADR 0030](adr/0030-wochentagsnaeherung-bleibt.md)). Das Kommando
bleibt trotzdem — IBKRs Fenster ist eine Eigenschaft des Anbieters, keine
Naturkonstante, und die Messung lässt sich damit ohne Aufwand wiederholen.

Der Earnings-Filter zählt Handelstage bis zum nächsten
Termin heute über eine **Wochentagsnäherung**: Montag bis Freitag gelten als
Handelstage, Börsenfeiertage bleiben unberücksichtigt
([ADR 0020](adr/0020-earnings-filter-status-und-handelstagskalender.md), L2/L3). Die Näherung
zählt damit zu hoch — der Termin erscheint weiter weg, und der Filter
schließt seltener aus, als er sollte.

Ob der echte Kalender sie ersetzen kann, hängt an einer einzigen Zahl:
Reicht IBKRs `liquidHours` so weit voraus wie das Ausschlussfenster?

```powershell
.venv\Scripts\python.exe -m ai_trading_analyst.cli calendar-reach --provider ibkr
```

Das Kommando liest nur; es braucht keine Datenbank und legt nichts ab.
Gefragt wird stellvertretend das erste Symbol der Watchlist — die
Handelszeiten gelten für die Börse, nicht für das einzelne Papier. Mit
`--symbols AAPL` lässt sich ein anderes wählen.

Gebraucht werden **elf** künftige Handelstage, nicht zehn: Der Filter
schließt aus bis einschließlich 20 Kerzen, die Entscheidung fällt also erst
einen Handelstag danach. Die Schlusszeile sagt, ob der Kalender so weit
reicht. Meldet sie zusätzlich ein „ABER", reicht er für die
Ausschlussentscheidung, aber nicht für die Zahl `candles_until_earnings`,
die auch für nicht ausgeschlossene Titel gespeichert wird.

**Gemessen am 2026-08-24** (Referenzkontrakt NVDA): vier künftige
Handelstage gegen elf gebrauchte. Ein abweichendes Ergebnis wäre ein neues
ADR, kein Nachtrag zu ADR 0030.

## Zwischenschritt: Chartauswertung gegenprüfen (optional)

Kein Abnahmekriterium, sondern eine Gelegenheit. Sobald der Bestand steht,
lässt sich die deterministische Chartauswertung für einzelne Symbole ansehen
([ADR 0025](adr/0025-deterministische-chartauswertung-und-zonen.md)):

```powershell
.venv\Scripts\python.exe -m ai_trading_analyst.cli technical --provider ibkr `
    --symbols AAPL,MSFT
```

`--provider ibkr` ist nötig: Ausgeliefert steht `market_data.provider` auf
`fixture`, und der Fixture-Anbieter kennt nur seine eigenen Kunstsymbole —
ohne die Übersteuerung bricht das Kommando mit einem entsprechenden Hinweis
ab. Wie bei `backfill` und `backtest` wird der Anbieter bewusst nicht
stillschweigend umgestellt.

Ausgegeben werden die wirksamen Zonenparameter, Trend, RSI, Lage zu
EMA5/EMA20, ATR, die jüngsten Hoch- und Tiefpunkte und die Unterstützungs-/
Widerstandszonen mit Spanne, Stärke, Berührungszahl, letzter Bestätigung und
Abstand zum Kurs.

Das Kommando rechnet ausschließlich auf dem gespeicherten Bestand, nie gegen
die TWS — die TWS muss also **nicht** laufen, und es kann nichts stören. Ein
Symbol muss aber in der Watchlist stehen **und** über `backfill` gefüllt
sein; passt kein einziges, zeigt das Kommando die verfügbaren Symbole an.

Die Zonenparameter in `config/default.yaml` (Abschnitt `technical_analysis`)
sind bewusst Konventionen und keine gemessenen Optima. Wer die Zonen neben dem
Chart in der TWS betrachtet und sie für zu breit, zu eng oder zu zahlreich
hält, zieht `zone_tolerance_pct`, `min_touches` oder `max_zones_per_side`
entsprechend nach. Ein neuer Lauf zeigt die Wirkung sofort; gespeicherte
Ergebnisse bleiben davon unberührt — sie führen ihre eigenen Parameter mit.

Worauf beim Vergleich zu achten ist:

- **Zonen überlappen einander nicht.** Tun sie es doch, stimmt etwas nicht.
- **Die Stärke folgt der Zahl der Wendepunkte**, nicht der Berührungen. Eine
  Zone mit einem Wendepunkt und vielen Berührungen ist eine Preisregion, die
  der Kurs durchläuft — sie soll `WEAK` sein.
- Ein nie wieder angelaufenes Verlaufshoch bildet **keine** Zone
  (`min_touches`). Es steht als „jüngstes Hoch" in derselben Ausgabe.
- Eine Zone mit **einem** Wendepunkt und vielen Berührungen ist bekanntes
  Rauschen in Kursnähe — der Kurs läuft dort durch, statt umzukehren. Sie ist
  als `WEAK` gekennzeichnet, belegt aber einen Platz je Seite. Siehe ADR 0025,
  „Negativ / offen".

### Die KI-Einordnung dazu

Mit `--interpret` ordnet der Technical Agent dieselbe Auswertung qualitativ
ein ([ADR 0026](adr/0026-technical-agent-ki-einordnung.md)):

```powershell
.venv\Scripts\python.exe -m ai_trading_analyst.cli technical --provider ibkr `
    --symbols AAPL,MSFT --interpret --agent-provider anthropic --show-prompt
```

`--agent-provider` ist bewusst getrennt von `--provider`: Letzteres steuert
die Marktdaten, Ersteres das Sprachmodell. Ausgeliefert steht
`technical_agent.provider` auf `fixture`; ohne die Übersteuerung läuft eine
Attrappe, die immer dasselbe antwortet — nützlich als Rauchtest der
Verdrahtung, aussagelos für den Inhalt. `none` liefert stattdessen die
gekennzeichnete Lücke des abgeschalteten Agenten. Mit `anthropic` kostet jeder Aufruf
Geld; das Protokoll weist Token und geschätzte Kosten je Symbol aus.

`--show-prompt` gibt aus, was dem Modell übergeben wurde. Es lohnt sich beim
ersten Mal: Man sieht schwarz auf weiß, dass dort nur der fertige Snapshot
steht — keine Rohkerzen, keine Signale, kein Earnings- oder
Research-Ergebnis.

Worauf beim Vergleich zu achten ist:

- **Die Einordnung darf keiner Zahl widersprechen**, die darüber steht. Ein
  als stark beschriebener Trend bei `Trend: SIDEWAYS` ist ein Prompt-Fehler,
  kein Geschmacksurteil.
- **Eine `WEAK`-Zone mit vielen Berührungen darf nicht als starker Halt
  gelesen werden.** Genau dafür steht die Auslegungsregel im Prompt; greift
  sie nicht, gehört sie geschärft.
- **Steht bei Chance/Risiko `NOT_ASSESSABLE`, während oben eine Zahl steht**,
  stimmt etwas nicht. Umgekehrt setzt der Adapter `NOT_ASSESSABLE` selbst
  durch, wenn die Zahl fehlt — das ist Absicht und kein Fehler.
- Es dürfen **keine Zahlen im Fazit** auftauchen, die nicht in der
  Modelleingabe stehen.

### Zwischenschritt: `temperature=0` verifizieren (optional, einmalig)

Offener Punkt E12 ② aus dem Audit vom 2026-08-23. ADR 0026 hält fest, dass
zwei Läufe auf identischer Eingabe für AAPL einmal `MEDIUM` und einmal `HIGH`
als Fehlsignalrisiko ergaben, bei Konfidenz 0,55 und 0,65 — **aber mit drei
verschiedenen Prompt-Fassungen.** Sie waren damit nicht vergleichbar.

Zwei aufeinanderfolgende Läufe mit derselben Fassung zeigen es:

```powershell
.venv\Scripts\python.exe -m ai_trading_analyst.cli technical --provider ibkr `
    --symbols AAPL --interpret --agent-provider anthropic
.venv\Scripts\python.exe -m ai_trading_analyst.cli technical --provider ibkr `
    --symbols AAPL --interpret --agent-provider anthropic
```

Zu vergleichen sind die sechs Einstufungen und die Konfidenz. Die API sagt
keine bitgleiche Ausgabe zu — „reproduzierbar genug" trifft es, nicht
„deterministisch". Das Ergebnis gehört als `### Nachtrag` in ADR 0026, so oder
so: Auch „stabil" ist ein Messergebnis.

Kosten: zwei Aufrufe des günstigen Modells, zusammen rund einen Cent.

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

Die Argumente wachsen mit den Stufen G und H mit; der vollständige
produktive Befehl steht **nur** im Stufe-H-Block „In die Aufgabenplanung
übernehmen", der tatsächlich geschaltete Stand im Abschnitt Betriebszustand.

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

Erst wenn Stufe F über mindestens einen Handelstag trägt. **Alle sechs**
Analyseanbieter stehen in `config/default.yaml` auf `fixture` und werden **nicht
dort** umgestellt: Der produktive Schalter gehört in die Argumente der
Aufgabenplanung, damit ein `git pull` auf dem Server keinen lokalen Diff
vorfindet.

| Anbieter | Schalter | Braucht | Kosten je Kandidat |
|---|---|---|---|
| Earnings-Termine | `--earnings-provider finnhub` | `ATA_FINNHUB_API_KEY` | keine |
| Fundamentaldaten | `--fundamentals-provider edgar` | `ATA_EDGAR_CONTACT` | keine |
| Analystenempfehlungen | `--ratings-provider finnhub` | `ATA_FINNHUB_API_KEY` | keine |
| Optionsanalyse | `--options-provider ibkr` | TWS + Optionsmarktdaten-Abo ([ADR 0048](adr/0048-optionsanalyse-im-tageslauf.md)) | keine |
| Technical Agent | `--technical-agent-provider anthropic` | `ATA_LLM_API_KEY` | ~0,005 USD |
| Research Agent | `--research-provider anthropic` | `ATA_LLM_API_KEY` | ~0,52–0,58 USD |

**Jeder weggelassene Schalter lässt seinen Berichtsabschnitt auf den
Fixture-Werten stehen** — und die sehen dort wie ein Ergebnis aus, nicht wie
eine Lücke. Die Fixture-Fundamentaldaten liefern für jedes Symbol dieselben
erfundenen Zahlen; erkennbar sind sie nur an der offensichtlich unechten
Vorgangsnummer `0000000000-00-000000`. Die Fixture-Analystenempfehlungen
verraten sich an der Quelle `fixture` am Ergebnis.

Für die zwei LLM-Agenten gibt es als dritten Wert **`none`**
([ADR 0051](adr/0051-research-im-dauerbetrieb-abgeschaltet.md)): Er schaltet
den Agenten bewusst ab — der Abschnitt erscheint als gekennzeichnete Lücke
(`UNAVAILABLE`, Grund `provider_disabled`) statt als Fixture-Schein-Ergebnis,
der Score gewichtet die fehlende Komponente um. Kostet nichts, braucht keinen
Schlüssel. Das ist der richtige Wert für einen Scharfbetrieb, der einen der
beiden Modellaufrufe nicht bezahlen will; `fixture` ist es nicht.

Die drei kostenlosen Schalter — Earnings, Fundamentaldaten und
Analystenempfehlungen — können zusammen eingeschaltet werden; die beiden
ersten teilen sich sogar den Finnhub-Schlüssel. Die beiden Modellaufrufe
lohnen einzeln: Der Technical Agent kostet rund einen halben Cent je
Kandidat, der Research Agent das Hundertfache.

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

## Schritt 1b — Analystenempfehlungen über Finnhub

Derselbe Schlüssel, derselbe Host, ein zweiter Endpunkt
([ADR 0043](adr/0043-analystenempfehlungen-statt-kurszielen.md)). Kostenlos,
kein Modellaufruf — deshalb zuerst die Einzelprobe, die **keine**
Aufgabenplanung anzuhalten braucht:

```powershell
.venv\Scripts\python.exe -m ai_trading_analyst.cli ratings --symbol AAPL `
    --provider finnhub
```

Erwartet werden bis zu vier Monatsstände mit der Verteilung `S-Buy` bis
`S-Sell`. Kommt `UNKNOWN` mit Grund `no_coverage`, führt Finnhub das Symbol
nicht — das ist **kein Fehler** und wird auch nicht als „keine Meinung"
gewertet; der Berichtspunkt fehlt dann begründet.

**Kursziele erscheinen nicht und werden nicht kommen.** Der Endpunkt dafür ist
kostenpflichtig, und keine Score-Komponente braucht sie (ADR 0043).
Berichtspunkt 9 bleibt deshalb dauerhaft „eingeschränkt".

Danach in die Argumente der Aufgabenplanung übernehmen:
`--ratings-provider finnhub`.

## Schritt 2 — Research Agent über Anthropic

> **Der Dauerbetrieb fährt seit dem 2026-09-01 `--research-provider none`**
> (Kostenentscheidung, siehe Betriebszustand). Dieser Schritt bleibt die
> **Einzelprobe** — und der Weg für den, der die Recherche später dauerhaft
> scharf schalten will: in Stufe H `none` durch `anthropic` ersetzen
> (~0,52–0,58 USD je Kandidat mit freiem Earnings-Fenster).

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

Wer nach der Einzelprobe dauerhaft scharf schalten will, ersetzt im
Aufgabenplanungs-Eintrag aus Stufe H `--research-provider none` durch
`--research-provider anthropic` — nichts sonst ändert sich.

---

# Stufe H — Benachrichtigungskanal (F10)

Kann unabhängig von Stufe G eingerichtet werden, sobald Stufe F über mindestens
einen Handelstag getragen hat. Kanal, Trennung von Geheimnis und Adresse sowie
die Fehlerisolation stehen in
[ADR 0024](adr/0024-benachrichtigungskanal-telegram.md).

### Bot anlegen

In Telegram mit **@BotFather** chatten, `/newbot` senden, Namen vergeben. Die
Antwort enthält den Bot-Token (`123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`)
— das ist das Geheimnis.

### Chat-ID ermitteln

Dem neuen Bot in Telegram eine beliebige Nachricht schreiben, dann:

```powershell
Invoke-RestMethod -Uri "https://api.telegram.org/bot<TOKEN>/getUpdates"
```

Die Antwort enthält `message.chat.id` — das ist **kein Geheimnis**, nur eine
Adresse, und gehört in `--telegram-chat-id`, nicht in `.env`.

### Geheimnis setzen und Einzelprobe

`ATA_NOTIFICATION_TOKEN` in der `.env` setzen. Der Dispatcher selbst eignet
sich **nicht** für die Probe: Er erreicht die Meldelogik nur bei einem
überfälligen Lauf, und den gibt es bei einer frisch aufgesetzten
`dispatcher_runs`-Tabelle nicht — an einem Tag ohne fälligen oder offenen Lauf
endet `dispatch` schon bei der Handelstagsprüfung, ohne den Kanal je
anzufassen. Stattdessen den Kanal direkt ansprechen:

```powershell
.venv\Scripts\python.exe -c "from ai_trading_analyst.config import NotificationsConfig, TelegramConfig, Secrets; from ai_trading_analyst.infrastructure.notifications import build_notifier; build_notifier(NotificationsConfig(channel='telegram', telegram=TelegramConfig(chat_id='<CHAT_ID>')), Secrets()).send('Testmeldung', 'Einzelprobe Stufe H.')"
```

**Abbruch, wenn:** die Nachricht nicht in Telegram ankommt, oder der Aufruf mit
einem Fehler endet, bevor überhaupt etwas versucht wurde — dann fehlt
`ATA_NOTIFICATION_TOKEN` oder die Chat-ID, und der Fehler benennt, welches.

### In die Aufgabenplanung übernehmen

```
-m ai_trading_analyst.cli dispatch --provider ibkr --earnings-provider finnhub --fundamentals-provider edgar --ratings-provider finnhub --options-provider ibkr --technical-agent-provider anthropic --research-provider none --notification-channel telegram --telegram-chat-id <CHAT_ID>
```

`--research-provider none` ist Absicht, kein vergessener Schalter: Die
Recherche ist der einzige teure Modellaufruf und bleibt im Dauerbetrieb
bewusst abgeschaltet (Beschluss vom 2026-09-01, siehe Betriebszustand) —
ihr Berichtspunkt erscheint als gekennzeichnete Lücke, nicht als
Fixture-Schein-Ergebnis. Scharf schalten: `none` durch `anthropic` ersetzen.

Dies ist die **einzige Stelle mit dem vollständigen Befehl** — die
Stufe-F-Tabelle zeigt bewusst nur den Ausgangszustand, und welcher Stand
tatsächlich geschaltet ist, sagt der Abschnitt Betriebszustand.

Zwei Arten von Meldungen kommen künftig an:

- **Ausgefallener Lauf** — Handelstag, Kerzenzeitpunkt, Ursache. Keine Kurse,
  keine Analyseergebnisse (ADR 0024).
- **Erfolgreicher Lauf** — Anzahl der Kandidaten, je Kandidat Symbol,
  Signaltypen, **beide Scores und die Empfehlungsstufe**, das
  Fehlsignalrisiko als Stufe und der Hinweis auf einen unbekannten
  Berichtstermin. Sortiert nach Swing-Score absteigend, damit bei einer
  Kürzung die besten Kandidaten stehen bleiben.
  **Keine Kurse, keine Kennzahlen, kein Freitext, kein Link**
  ([ADR 0047](adr/0047-scores-in-der-ergebnismeldung.md), das
  [ADR 0040](adr/0040-inhalt-der-ergebnismeldung.md) in genau diesem Punkt
  ablöst).

Ein Lauf ohne Kandidaten meldet sich nicht, solange
`notifications.send_when_no_candidates` auf `false` steht.

---

# Stufe I — Der Analysebericht

Voraussetzung: Stufe F ist durch, es gab mindestens einen Lauf mit
Kandidaten.

Zuerst die Migration, sonst bricht der erste Lauf beim Speichern ab:

```powershell
.venv\Scripts\python.exe -m alembic upgrade head
```

Dann die Lauf-ID heraussuchen und den Bericht ansehen:

```powershell
.venv\Scripts\python.exe -m ai_trading_analyst.cli report --run <lauf-id>
```

Die Lauf-ID steht in der Ausgabe des Tageslaufs („Analyse-Lauf <id>: …") und
in der Tabelle `analysis_runs`.

`--symbol AAPL` zeigt nur einen Kandidaten, `--format json` das gespeicherte
Dokument unverändert, `--output <datei>` schreibt statt zu drucken. Der volle
Text eines Kandidaten umfasst mehrere hundert Zeilen — das ist der
vollständige Bericht aus Doc 10, Paragraph 6.12, kein Auszug.

Worauf beim ersten Mal zu achten ist:

- **Alle achtzehn Punkte müssen erscheinen**, durchnummeriert. Seit Sprint 5
  sind auch Put-Strategien, beide Scores und die Empfehlung gefüllt; im
  Dauerbetrieb steht dafür Punkt 8 (Nachrichten) als gekennzeichnete Lücke
  mit Grund `provider_disabled` — die Recherche läuft bewusst abgeschaltet
  ([ADR 0051](adr/0051-research-im-dauerbetrieb-abgeschaltet.md)).
- **Punkt 5 muss eine Signalstatistik tragen.** Ist er leer, reichte die
  Historie im Betrachtungsfenster nicht — dann fehlt ein Backfill.
- **Punkt 1 sollte den Unternehmensnamen nennen.** Fehlt er, führt das
  SEC-Symbolverzeichnis das Symbol nicht; bei Nicht-US-Titeln ist das
  erwartbar.
- **Kein Punkt darf leer sein, ohne dass darunter eine Begründung steht.**

**Abbruch, wenn:** der Befehl „Kein Lauf mit der ID …" meldet — dann ist die
ID falsch. „Keine Berichte zu Lauf … — 0 Kandidaten" ist dagegen kein Fehler,
sondern ein Lauf ohne Treffer.

---

# Stufe J — Das Dashboard

Erst wenn Stufe I trägt: Das Dashboard zeigt gespeicherte Läufe und
Berichte, es erzeugt keine. Es ist **ausschließlich im eigenen Netz
erreichbar** — keine Portweiterleitung am Router, keine Anmeldung
([ADR 0049](adr/0049-dashboard-mvp-nur-lan.md)).

## Schritt 1 — Node prüfen oder installieren

```powershell
node --version
npm --version
```

Node wird **nur zum Bauen** gebraucht, nicht zur Laufzeit
([ADR 0052](adr/0052-dashboard-als-statischer-export.md)). Ohne Node gibt es
keinen Export und damit kein Dashboard — die API und der Tageslauf laufen aber
weiter.

**Gebraucht wird Node 22 (LTS) — dieselbe Hauptversion, mit der die CI baut**
(`.github/workflows/ci.yml`, Job „Frontend"; `@types/node` im
`package.json` steht ebenfalls auf 22). Mit einer anderen Hauptversion zu
bauen hieße, einen Export auszuliefern, den die CI nie geprüft hat.

Fehlt Node, holt das folgende die jüngste 22er-LTS-Fassung und installiert
sie still:

```powershell
$ProgressPreference = 'SilentlyContinue'
$ziel = "$env:TEMP\node-installer.msi"

$index = Invoke-RestMethod https://nodejs.org/dist/index.json -UseBasicParsing
$fassung = ($index | Where-Object { $_.version -like 'v22.*' -and $_.lts })[0].version
Invoke-WebRequest "https://nodejs.org/dist/$fassung/node-$fassung-x64.msi" `
    -OutFile $ziel -UseBasicParsing
Start-Process msiexec.exe -Wait -ArgumentList "/i `"$ziel`" /qn /norestart"
```

**Danach ein neues PowerShell-Fenster öffnen:** Der Installer setzt `PATH`,
und die laufende Sitzung kennt ihn nicht.

## Schritt 2 — Export bauen

```powershell
cd C:\...\frontend
npm ci
npm run build
```

Ergebnis ist der Ordner `frontend\out`. Er ist nicht eingecheckt und
entsteht auf jedem Rechner neu.

> **`index.html` nicht per Doppelklick öffnen.** Der Browser lädt sie dann
> als `file://`, und die Seite verweist auf ihre JavaScript-Bündel unter
> `/_next/static/…` — absolute Pfade, die dort ins Leere zeigen. React startet
> nie, und die Seite bleibt **dauerhaft** bei „Wird geladen …" stehen, ohne
> Fehlermeldung: Was zu sehen ist, ist der vorgerenderte Ausgangszustand. Es
> lädt nicht lange, es lädt gar nicht. Auch die API wäre von dort nicht
> erreichbar — es gibt keine Herkunft, die auf sie zeigt. Der Export gehört
> hinter den Dienst aus Schritt 3.

## Schritt 3 — Dienst zur Probe starten

```powershell
cd C:\...\backend
.venv\Scripts\python.exe -m uvicorn ai_trading_analyst.main:app --host 0.0.0.0 --port 8000
```

`ai_trading_analyst.main:app` ist der richtige Einstiegspunkt und nicht
`presentation.api.app:create_app`: Nur der Weg über `build_app()` verdrahtet
Datenbank **und** Dashboard-Ordner. Die Fabrik direkt gestartet, liefert eine
API ohne beides.

Dann lokal `http://127.0.0.1:8000/` öffnen. Die Tagesübersicht muss den
letzten Lauf zeigen; `http://127.0.0.1:8000/api/v1/system/readiness` muss
`ready` melden. Bleibt die Seite leer, sagt die Readiness, auf welcher Seite
es klemmt.

> `--host 0.0.0.0` bindet an **alle** Schnittstellen. Das ist der Preis
> dafür, dass die Adresse des Servers per DHCP wechseln darf; abgeschirmt
> wird über die Firewallregel aus Schritt 4 und darüber, dass am Router kein
> Port weitergeleitet ist. Wer eine feste Adresse hat, darf sie hier
> stattdessen eintragen.

## Schritt 4 — Firewall nur für das eigene Netz öffnen

In einer PowerShell **als Administrator**:

```powershell
New-NetFirewallRule -DisplayName "AI Trading Analyst Dashboard" `
  -Direction Inbound -Protocol TCP -LocalPort 8000 -Profile Private -Action Allow
```

`-Profile Private` ist die eigentliche Absicherung: Die Regel gilt nur im
als privat eingestuften Netz. Steht das Serviernetz auf „Öffentlich", greift
sie nicht — dann ist die Netzwerkeinstufung zu korrigieren und **nicht** das
Profil zu erweitern.

## Schritt 5 — Autostart

| Feld | Wert |
|---|---|
| Trigger | **Bei Systemstart** |
| Programm | `C:\...\backend\.venv\Scripts\python.exe` |
| Argumente | `-m uvicorn ai_trading_analyst.main:app --host 0.0.0.0 --port 8000` |
| Starten in | `C:\...\backend` |
| Einstellungen | „Task beenden, falls er länger läuft als" **deaktivieren** |

Anders als der Dispatcher ist das ein **Dauerprozess** — der erste des
Systems. Er braucht keine TWS und keine angemeldete Sitzung; fällt er aus,
fehlt nur die Anzeige, nicht die Analyse.

**Abnahmekriterium:** Von einem anderen Gerät im eigenen Netz zeigt
`http://<server>:8000/` die Tagesübersicht des letzten Laufs — und aus dem
Mobilfunknetz (WLAN aus) ist die Adresse **nicht** erreichbar.

---

# Stufe K — Das Dashboard außerhalb des Servers

**Noch nicht entschieden.** [ADR 0060](adr/0060-dashboard-ausserhalb-des-servers.md)
ist vorgeschlagen; angenommen wird es erst nach einem Proof of Concept beim
Anbieter. Diese Stufe beschreibt deshalb nur, was **ohne** Anbieter geht:
den Datenbaum auf dem Server erzeugen und nachsehen, ob er trägt. Kein
Konto, kein Token, kein Upload, keine Firewall-Regel — Stufe J bleibt
unberührt, und der Server bekommt nichts Eingehendes.

Der Gedanke kehrt Stufe J um: Nicht der Nutzer kommt zum Server, sondern die
Ergebnisse gehen zum Nutzer. Der Server schreibt nach jedem Lauf einen
Datenbaum aus denselben lesenden Endpunkten, die auch das LAN-Dashboard
nutzt, und verschlüsselt ihn. Entschlüsselt wird erst im Browser.

## Schritt 0 — Den Stand einspielen

Diese Stufe bringt eine neue Abhängigkeit mit: `cryptography`, für
AES-256-GCM. Fehlt sie, bricht der Exportbefehl schon beim Import ab. Der Weg
ist der gewöhnliche aus „Aktualisierung" weiter unten:

```powershell
cd C:\Users\Administrator\Documents\TradingViewAnalyzer\backend
git pull
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock.txt
.venv\Scripts\python.exe -m pip install --no-deps -e .
```

Eine Datenbankmigration gehört **nicht** dazu. Der Export liest ausschließlich;
er legt kein Schema an und schreibt keine Zeile.

## Schritt 1 — Passphrase erzeugen und ablegen

Lang und zufällig, nicht ausgedacht — sie wird nie getippt, sondern kommt
aus dem Passwortmanager:

```powershell
# 32 Bytes aus dem kryptographischen Zufallsgenerator, als Base64.
# Das Ergebnis in den Passwortmanager, und nur dorthin.
$bytes = [byte[]]::new(32)
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$rng.Dispose()
if (-not ($bytes | Where-Object { $_ -ne 0 })) {
    throw "Der Zufallsgenerator hat nichts geliefert -- nichts uebernehmen."
}
[Convert]::ToBase64String($bytes)
```

**Nicht `RandomNumberGenerator::Fill`.** Die statische Methode gibt es erst ab
.NET Core 2.1; Windows PowerShell 5.1 laeuft auf dem .NET Framework und kennt
sie nicht. Der Aufruf scheitert dort, laesst das Byte-Array unberuehrt --
und die naechste Zeile kodiert dann pflichtschuldig 32 Nullbytes zu einer
Zeichenfolge, die wie eine Passphrase aussieht (`AAAA...=`). Genau deshalb
steht die Pruefung darueber im Block: Ein Fehlschlag soll abbrechen und nicht
etwas Brauchbares vortaeuschen. `Create()` und `GetBytes()` gibt es in beiden
Welten.

**Nicht `Get-Random`.** Der zieht aus `System.Random` — einem Generator für
Simulationen, nicht für Geheimnisse. Für eine Passphrase, die das einzige
Schloss vor den Daten ist, ist der Unterschied der ganze Punkt. Wer den
Passwortmanager selbst erzeugen lässt, ist ebenso richtig bedient.

Danach in die `.env` im Projektwurzelverzeichnis, zu den übrigen
`ATA_`-Werten:

```
ATA_DASHBOARD_EXPORT_PASSPHRASE=<die erzeugte Zeichenfolge>
```

**Wer sie verliert, verliert die Anzeige, nicht die Daten** — die liegen in
der Datenbank auf dem Server. Ein Wechsel der Passphrase schreibt den ganzen
Datenbaum neu; die alten Dateien verschwinden dabei.

## Schritt 2 — Die Oberfläche im Zero-Knowledge-Modus bauen

Das ist ein **anderer Build** als der aus Stufe J: Er nimmt ausschließlich
Chiffrat an und kennt keine API. Das Verfahren ist Eigenschaft des Builds und
steht in keiner Datei, die neben den Daten liegt — wer beim Anbieter
schreiben darf, kann damit keinen Klartextmodus einschalten.

```powershell
cd C:\...\frontend
$env:NEXT_PUBLIC_DATENMODUS = "verschluesselt"
npm run build
Remove-Item Env:\NEXT_PUBLIC_DATENMODUS
```

**Beide Builds landen in demselben `frontend\out`** — Next kennt nur dieses
eine Ausgabeverzeichnis. Genau daraus liefert der Dienst aus Stufe J das
LAN-Dashboard aus. Wer hier baut, überschreibt es also; der
Zero-Knowledge-Build fände im eigenen Netz keine API und zeigte nur die
Passphrase-Abfrage.

Deshalb: das Ergebnis in das Verzeichnis kopieren, das später hinausgeht,
und den LAN-Build sofort wiederherstellen.

```powershell
New-Item -ItemType Directory -Force ..\var\dashboard | Out-Null

# Die alte Oberflaeche zuerst weg, den Datenbaum aber stehen lassen.
# **Das Sternchen am Pfad und -Force sind beide noetig.** Microsoft
# dokumentiert -Exclude als wirksam nur dort, wo der Befehl den *Inhalt*
# eines Elements adressiert; ohne das Sternchen ist das Verhalten
# versionsabhaengig, und greift die Ausnahme nicht, loescht die Zeile
# 'data' mit. -Force nimmt versteckte Eintraege mit, die sonst liegen
# blieben und weiter mit hinausgingen.
# 'Copy-Item -Force' ueberschreibt nur gleichnamige Dateien, und die Namen
# der Next-Buendel tragen einen Hash je Build -- ohne dieses Aufraeumen
# blieben die Buendel *jedes* frueheren Builds liegen und gingen bei jedem
# Upload mit hinaus. Das Verzeichnis 'data' gehoert dem Exportschritt, der
# darin selbst aufraeumt.
Get-ChildItem ..\var\dashboard\* -Force -Exclude data | Remove-Item -Recurse -Force

Copy-Item -Recurse -Force out\* ..\var\dashboard\
npm run build          # ohne die Variable -- das ist wieder der LAN-Build
```

In dasselbe `var\dashboard` schreibt Schritt 3 gleich den Datenbaum unter
`data\`. Der Exportschritt fasst dabei **nur** `data\` an — die Oberfläche
daneben bleibt unberührt, und beides zusammen ist genau das, was später als
ein Deployment hinaufginge.

Sobald der Weg nach draußen steht, gehört das in ein Skript; solange die
Entscheidung aussteht, ist es Handarbeit unter Aufsicht.

## Schritt 3 — Den Datenbaum schreiben

```powershell
cd C:\...\backend
.venv\Scripts\python.exe -m ai_trading_analyst.cli publish --directory var\dashboard
```

**Kein `--provider` nötig, und das ist Absicht.** Die Kerzen für den Chart
kommen immer aus dem Bestand in der Datenbank, nie von einem Anbieter — der
Export zeigt an, was gerechnet wurde, und beschafft nichts. Voraussetzung ist
deshalb ein gefüllter Bestand aus dem Backfill. Findet der Export zu **keiner
einzigen** Aktie eine Kursreihe, bricht er ab, statt einen Stand ohne Charts
zu schreiben.

Die Ausgabe nennt, wie viele Dateien entstanden, wie viele unverändert
blieben und wie viele entfernt wurden. Beim ersten Mal ist alles neu; beim
zweiten Aufruf muss **genau eine** Datei neu geschrieben werden — das
Manifest, es trägt den Zeitpunkt.

## Schritt 4 — Nachsehen, was dort liegt

```powershell
# Die Dateinamen sagen nichts:
Get-ChildItem var\dashboard\data | Select-Object -First 5 Name, Length

# Der Klartextkopf ist die einzige lesbare Datei -- er nennt Salt und
# Rundenzahl, damit der Browser den Schluessel ableiten kann:
Get-Content var\dashboard\data\manifest.head.json

# Und keine einzige Datei enthaelt ein Symbol im Klartext:
Select-String -Path var\dashboard\data\* -Pattern "AAPL" -List
```

**Rechnen Sie mit einer knappen Viertelstunde.** Auf dem Server gemessen
(2026-09-09, 190 Aktien): **784 Sekunden**, rund 4 Sekunden je Aktie, 685
Dateien, 29 MB.

Der Löwenanteil ist der Validierungschart: Der Export baut ihn je Aktie neu
— dieselbe Indikatorrechnung wie im Screener, dazu die Kandidatenprüfung an
jedem Entscheidungspunkt — und zwar über die **gesamte** Historie im
Bestand. `market_data.ibkr.history_duration` (1 Y) begrenzt nur den
regelmäßigen Lückenschluss; der einmalige Tiefen-Backfill (ADR 0028) hat den
Bestand bis 2021 gefüllt.

**Nicht die Kerzen sind der Kostentreiber, sondern die Bars darunter.** Bei
`timeframe_minutes: 195` und einer 390-Minuten-Sitzung entstehen zwei Kerzen
je Handelstag — fünf Jahre sind rund 2.500 Kerzen, also genau so viele wie
auf dem Entwicklungsrechner. Gelesen werden dafür aber rund **33.000 native
15-Minuten-Bars je Aktie** aus PostgreSQL (ADR 0028), die erst zu diesen
Kerzen aggregiert werden. Das ist der Unterschied zwischen 0,4 und 4
Sekunden, nicht eine tiefere Historie. Verschlüsseln und Schreiben fallen
daneben kaum ins Gewicht.

**Der zweite Aufruf ist genauso teuer.** „Nur Änderungen" bezieht sich auf
das Schreiben, nicht auf das Rechnen: Ob ein Chart sich geändert hat, weiß
der Export erst, wenn er ihn gebaut und seine Prüfsumme gebildet hat. Das
Inkrementelle spart Schreibvorgänge und später Übertragung — keine
Rechenzeit. Für den Tageslauf heißt das: gut eine Viertelstunde am Ende
jedes Laufs, jeden Tag.

**Abnahmekriterien dieser Stufe:** Die letzte Suche findet nichts. Der Kopf
nennt `PBKDF2-HMAC-SHA256`, `AES-256-GCM` und mindestens 600.000 Runden. Der
zweite Aufruf aus Schritt 3 schreibt nur das Manifest neu. Und der
Zustandsvermerk (`var\dashboard.zustand.json`) liegt **außerhalb** des
Verzeichnisses, das später hochgeladen würde — er enthält die Zuordnung von
Pfad zu Dateiname.

## Schritt 4b — Einmal wirklich hineinsehen

Alles bis hier beweist, dass der Baum vollständig und undurchsichtig ist. Es
beweist **nicht**, dass ihn jemand benutzen kann. Dieser Schritt ist der
einzige, der die beiden Hälften außerhalb der Tests zusammenbringt.

Der Datenbaum liegt bereits neben der Oberfläche aus Schritt 2, beides unter
`var\dashboard`. Es fehlt nur ein Webserver davor — die Seite lädt ihre
Dateien per `fetch`, und das geht über `file://` nicht.

```powershell
cd C:\Users\Administrator\Documents\TradingViewAnalyzer\var\dashboard
..\..\backend\.venv\Scripts\python.exe -m http.server 8099 --bind 127.0.0.1
```

**`--bind 127.0.0.1` ist nicht optional.** Ohne die Angabe lauscht der
Server auf allen Schnittstellen, die Windows-Firewall fragt nach, und aus
einer Abnahme wird eine Netzwerkänderung. So bleibt es beim eigenen Rechner:
keine Regel, kein offener Port nach außen, Stufe J unberührt.

Dann im Browser des Servers **`http://localhost:8099/`** öffnen. Die Adresse
ist ebenfalls nicht beliebig: `crypto.subtle` — die Entschlüsselung im
Browser — steht nur in einem *sicheren Kontext* zur Verfügung. `localhost`
und `127.0.0.1` gelten als sicher, die LAN-Adresse des Servers **nicht**.
Über `http://192.168.x.x:8099` erschiene das Passphrase-Feld und die
Entschlüsselung scheiterte an einer Stelle, die nichts mit dem Datenbaum zu
tun hat.

Am Ende `Strg+C`. Der Webserver ist für diesen Blick da und für nichts sonst.

**Was zu prüfen ist:**

| # | Prüfung | Erwartung |
|---|---|---|
| 1 | Die Seite fragt nach einer Passphrase | Nur der Zero-Knowledge-Build tut das. Erscheint stattdessen sofort ein Dashboard, liegt der LAN-Build im Verzeichnis — Schritt 2 wiederholen |
| 2 | Eine **falsche** Passphrase eingeben | Verständliche Fehlermeldung, kein Absturz, keine leere Seite. Danach lässt sich die richtige eingeben |
| 3 | Die richtige Passphrase, mit Blick auf die Uhr | Der Stand öffnet sich. Die Dauer ist die Schlüsselableitung — Bezugswert für AK16 |
| 4 | Die Kopfzeile „Stand" | Nennt Datum des Laufs und Zeitpunkt des Exports. Zeigt sie einen älteren Lauf als erwartet, hat der Export einen alten Stand erwischt |
| 5 | Die Liste „ohne Chart" in derselben Zeile | Sollte leer oder kurz sein. Stehen dort alle Aktien, kommen die Kerzen nicht aus dem Bestand (siehe Schritt 3) |
| 6 | Eine Aktie mit Chart öffnen | Kerzen, EMA und RSI werden gezeichnet. **Einen Schlusskurs gegen die Datenbank gegenprüfen** — das ist die einzige Prüfung, die echte von plausiblen Zahlen unterscheidet |
| 7 | Berichte und Backtests aufrufen | Dieselben Zahlen wie im LAN-Dashboard bzw. in der API |
| 8 | Einen **neuen Tab** auf dieselbe Adresse öffnen | Fragt erneut nach der Passphrase. Sie wird bewusst nirgends abgelegt |
| 9 | Entwicklerwerkzeuge, Reiter „Netzwerk", Seite neu laden | Die angeforderten Dateinamen sind Hexfolgen ohne Bezug zum Symbol, die Antworten sind Binärdaten. Kein einziger lesbarer JSON-Körper außer `manifest.head.json` |
| 10 | Reiter „Konsole" | Keine Fehler |

**Abnahmekriterium dieser Stufe:** Prüfung 6 und Prüfung 9 zusammen. Die
erste zeigt, dass echte Daten ankommen; die zweite, dass unterwegs nichts
davon lesbar war.

Was hier **nicht** geprüft werden kann, ist AK16: die Dauer auf dem
Smartphone. Dazu müsste der Baum erreichbar sein, und das ist er erst mit
einem Anbieter.

## Schritt 5 — Im Tageslauf einschalten (erst nach Schritt 4)

In `config/default.yaml` unter `dashboard_export` das Ziel eintragen
(`directory: var/dashboard`); **geschaltet wird über die Aufgabenplanung**,
wie bei den Anbietern auch. Dem Eintrag aus Stufe F kommt dafür ein Argument
hinzu:

```
--dashboard-export directory
```

Danach schreibt der Tageslauf den Baum am Ende jedes Laufs selbst. Ein
Fehlschlag hält den Lauf nicht an — er kommt als eigene Telegram-Meldung
„Dashboard nicht aktualisiert" und steht im Protokoll.

**Das ist zugleich der Notausschalter:** `--dashboard-export none` in der
Aufgabenplanung, speichern, fertig. Der Tageslauf läuft weiter, nur der
Snapshot bleibt aus. Die Konfigurationsdatei wird dafür nicht angefasst — sie
ist im öffentlichen Repository versioniert.

**Was hier ausdrücklich noch nicht steht:** Anbieterwahl, Konto, Token,
Zugriffsregel, Upload und die Notfallkarte dazu. Das ist Gegenstand des
Proof of Concept aus Abschnitt 11 des
[Spike-Berichts](requirements/f12-externes-hosting-spike.md) und kommt in
diese Stufe, sobald ADR 0060 angenommen ist.

---

# Stufe L — Der Weg nach draußen: Cloudflare Workers mit Access

**Abgenommen am 2026-09-17.** Der Datenbaum steht bei Cloudflare hinter der
GitHub-Anmeldung, und alle Abnahmekriterien sind erfüllt: Ohne Anmeldung
kommt niemand an Inhalte (geprüft am Rechner, am Smartphone im Mobilfunknetz
und mit abgebrochener Anmeldung), die Passphrase öffnet den Stand, ein
Schlusskurs stimmt mit der Datenbank überein, im Netzwerkreiter stehen nur
opake Namen und Binärantworten — und **AK16 ist erfüllt**: Vom Eingeben der
Passphrase bis zum sichtbaren Stand vergeht auf dem Smartphone **unter einer
Sekunde**, gegen ein Ziel von zwei.

Damit ist die Behauptung von ADR 0060 belegt: Echte Daten kommen an, und
unterwegs war nichts davon lesbar.

**Die Sicherheits-Header sind seit dem 2026-09-17 dabei** — sie liegen als
`frontend/public/_headers` im Repository und werden von `next build` nach
`out/` kopiert, gehen also mit jedem Upload mit. Workers liest die Datei und
liefert sie selbst nicht aus. **Offen bleibt** der Upload aus dem
Exportschritt heraus; bis dahin ist Schritt 6 Handarbeit.

Diese Stufe setzt die Anbieterentscheidung um
([Anbieterevaluation](requirements/f12-hosting-anbieter-evaluation.md),
2026-09-09: Cloudflare Pages mit Cloudflare Access). Sie ist zugleich
Phase 2 des Proof of Concept aus Abschnitt 11 des
[Spike-Berichts](requirements/f12-externes-hosting-spike.md) — erst wenn sie
durch ist, kann ADR 0060 angenommen werden.

**Die Reihenfolge ist hier die halbe Sicherheit.** Der Datenbaum geht als
Letztes hinauf. Vorher steht eine Attrappe dort, und an ihr wird geprüft,
ob die Zugriffsregel wirklich greift. Wer zuerst hochlädt und dann absichert,
hat den Stand in der Zwischenzeit öffentlich stehen — und was einmal
abgerufen wurde, holt keine Regel zurück.

**Aus Pages wurde ein Worker, und das ist gut so.** Diese Stufe war für
Cloudflare Pages geschrieben. Die Konsole legt über „Create application"
inzwischen einen **Worker mit statischen Dateien** an, erkennbar an der
Adresse `<name>.<konto>.workers.dev` statt `<name>.pages.dev`; Cloudflare
empfiehlt Workers ausdrücklich für neue Projekte. Für diesen Zweck ist der
Worker **der bessere Ort**: Eine einzige Einstellung schützt alle seine
Adressen einschließlich der Vorschauen — die Falle mit den zwei
Anwendungen, die Pages hatte, entfällt —, und Vorschau-Adressen lassen sich
ganz abschalten. Alle Schritte sind darauf umgestellt und gegen die
Cloudflare-Dokumentation geprüft (Stand 2026-09-17).

**Die Menüpfade sind Stand 2026-09-17.** Cloudflare hat die Konsole
mehrfach umgebaut und „Zero Trust" in „Cloudflare One" umbenannt; ein
Menüpunkt, der hier nicht mehr zu finden ist, ist wahrscheinlich verschoben
und nicht verschwunden. Maßgeblich ist dann die Cloudflare-Dokumentation,
nicht diese Seite.

**Keine Geheimnisse in den Chat.** Passphrase, API-Token und
Wiederherstellungscodes bleiben im Passwortmanager. Für Rückfragen genügt
immer die Fehlermeldung ohne den Wert.

## Schritt 1 — Ein eigenes Cloudflare-Konto

**Ein neues Konto, nicht ein vorhandenes.** Der Grund steht in der
Anbieterevaluation: Das Recht `Cloudflare Pages: Edit` gilt **kontoweit**
und lässt sich nicht auf ein Projekt einengen. In einem Konto, das nur
dieses eine Projekt enthält, sind „kontoweit" und „projektweit" dasselbe —
ein gestohlenes Token kostet dann nichts außerhalb dieses Dashboards.
Liegen dort auch andere Domains, kostet es die.

Beim ersten Aufruf von **Zero Trust** verlangt Cloudflare einen
**Teamnamen**; daraus wird `<team>.cloudflareaccess.com`, und dort landet
die Anmeldemaske. Der Name gehört deshalb zu T9: **nichtssagend**, kein
Bezug zu Trading, Börse, Aktien oder zum eigenen Namen. Er lässt sich
später nur mit Mühe ändern.

Wählen Sie den **Free**-Tarif von Zero Trust. Er deckt 50 Nutzer; gebraucht
wird einer.

## Schritt 2 — Identitätsanbieter festlegen (offene Frage O3)

Access braucht eine Stelle, die die Anmeldung durchführt. Eingebaut ist
**One-time PIN** — ein Einmalcode per E-Mail. Entscheidung **E2** wollte
das ausdrücklich nur als Rückfall, weil damit das E-Mail-Postfach der
einzige Faktor ist.

**Gewählt: GitHub als Identitätsanbieter** (Entscheidung des Inhabers vom
2026-09-10, damit ist O3 beschieden). Das Konto existiert bereits — dasselbe,
in dem dieses Repository liegt —, es kann Passkeys und Authenticator-App,
und es entsteht keine neue Identität, die gepflegt werden muss.

Die Einrichtung hat zwei Hälften: eine OAuth-Anwendung bei GitHub, und der
Eintrag davon in Zero Trust. **Der Teamname aus Schritt 1 muss dafür
feststehen** — er steckt in der Rückruf-Adresse.

**Bei GitHub** unter *Settings → Developer settings → OAuth Apps → New OAuth
App*:

| Feld | Wert |
|---|---|
| Application name | Was bei der Anmeldung angezeigt wird. Nichtssagend halten (T9) |
| Homepage URL | `https://<team>.cloudflareaccess.com` |
| Authorization callback URL | `https://<team>.cloudflareaccess.com/cdn-cgi/access/callback` |

Registrieren, die **Client ID** notieren, dann ein **Client secret**
erzeugen. Beides in den Passwortmanager — das Secret erscheint nur einmal.

**In Cloudflare One** (vormals Zero Trust) unter *Integrations → Identity
providers → Add new identity provider → GitHub*: die Client ID in das Feld **App ID**, das Secret in **Client
secret**, speichern, dann **Finish setup** — dort erteilt GitHub den Zugriff
auf Organisationen und E-Mail-Adressen.

### Die Prüfung, und warum sie vor der Zugriffsregel kommt

Neben der angelegten Anmeldemethode steht **Test**. Diesen Knopf drücken
und die zurückgegebene Identität ansehen.

**Der Grund ist eine Falle, die sonst erst beim Aussperren auffällt:** Die
Zugriffsregel in Schritt 4 lässt genau **eine E-Mail-Adresse** zu. Welche
Adresse GitHub zurückgibt, hängt aber von den Einstellungen des Kontos ab —
wer *Keep my email addresses private* gesetzt hat, wird unter Umständen mit
einer `users.noreply.github.com`-Adresse geführt. Steht in der Regel dann
die private Adresse, meldet Access folgerichtig ab, und zwar jedes Mal.

Deshalb: **Die Adresse, die der Test anzeigt, ist die Adresse, die in die
Regel gehört** — nicht die, die man erwartet hätte.

**Was man dabei wissen sollte:** Damit hängen Repository und Dashboard an
demselben Konto. Wer es übernimmt, hat beides. Das Repository ist
öffentlich und das Dashboard Chiffrat — der Schaden ist begrenzt, aber die
Kopplung ist real. Wer sie nicht will, nimmt ein zweites Konto bei einem
Identitätsanbieter; dann ist O3 damit beschieden.

**Vor dem nächsten Schritt:** Zwei-Faktor-Anmeldung im gewählten Konto
prüfen und die Wiederherstellungscodes in den Passwortmanager legen. Ohne
sie sperrt ein verlorenes Telefon das Dashboard dauerhaft aus.

## Schritt 3 — Der Worker, mit einer Attrappe

**Im Browser, nicht auf dem Server.** Die Attrappe braucht keine
Kommandozeile und keine Anmeldung auf dem Server. Ein früherer Entwurf sah
`npx wrangler login` vor — das hinterlegt eine **breite** Anmeldung
dauerhaft im Benutzerprofil des Servers, mit weit mehr Rechten als das
eingeengte Token aus Schritt 5.

Auf dem Rechner, an dem der Browser läuft, einen Ordner `attrappe` mit
einer einzigen Datei `index.html`:

```html
<h1>leer</h1>
```

In der Cloudflare-Konsole unter **Workers & Pages → Create application →
Get started → Drag and drop your files** den Ordner hineinziehen und
bereitstellen. Heraus kommt ein Worker unter
`<name>.<konto>.workers.dev`.

**Beide Namen landen in der Adresse und sind öffentlich:** der des Workers
und die Konto-Subdomain, die Cloudflare aus dem Kontonamen ableitet. Beide
nichtssagend halten (E6, T9).

## Schritt 4 — Die Zugriffsregel

### 4a — Vorschau-Adressen abschalten

Jede neue Version eines Workers bekommt eine eigene Vorschau-Adresse
(`<kennung>-<name>.<konto>.workers.dev`). Gebraucht wird hier keine — der
Upload geht direkt auf den Produktivstand. Und jede, die es nicht gibt, muss
auch niemand absichern.

Im Worker unter **Settings → Domains & Routes → Preview URLs → Disable**.

**Die Probe darauf ist zweideutig, und das sollte man wissen.** Eine
Vorschau-Adresse lautet
`<Versionskennung verkürzt>-<Worker>.<Konto>.workers.dev`. Ruft man eine
selbst gebildete auf und bekommt „nicht gefunden", kann das heißen, dass
die Vorschauen aus sind — oder dass die Adresse falsch geraten war. Von
außen ist beides nicht zu unterscheiden.

**Verlässlich ist erst Schritt 6b:** `wrangler` nennt nach dem Upload die
Vorschau-Adresse der neuen Version, wenn es eine gibt. Nennt es keine,
sind die Vorschauen aus — und mit `"preview_urls": false` in der
Konfigurationsdatei sind sie es danach ohnehin.

**Am 2026-09-17 so geprüft:** Die Ausgabe nannte nur die
`workers.dev`-Adresse und keine Vorschau-Adresse. Damit ist der Punkt
erledigt.

**Das ist mehr als Aufräumen.** Wegen des stabilen Salts stehen alle je
hochgeladenen Fassungen unter demselben Schlüssel. Abgeschaltete
Vorschau-Adressen machen alte Versionen **unerreichbar**, auch wenn
Cloudflare sie weiter aufbewahrt. Ob sich alte Versionen darüber hinaus
löschen lassen, ist nicht dokumentiert und bleibt ein Punkt für den PoC.

### 4b — Den Worker hinter Access stellen

Im Worker unter dem Reiter **Access → Protect this Worker behind Access →
All traffic**. Die Einstellung schützt nach Cloudflares Beschreibung
**jede** Adresse des Workers: `workers.dev`, Vorschauen, Routen und eigene
Domains.

**Die Falle dieser Stufe steht hier, und sie ist schlimmer als die von
Pages.** Als Richtlinie bietet die Schnellauswahl **Cloudflare account**
und **Email domain** an. „Email domain" lässt jeden zu, der eine
bestätigte Adresse unter dieser Domain hat. Bei einem Freemail-Anbieter
sind das **Millionen Menschen** — die Anmeldung wäre formal eingerichtet
und praktisch offen. **Hier „Cloudflare account" wählen**, nie „Email
domain". Das ist der sichere Ausgangspunkt, nicht das Ziel.

### 4c — Die Anwendung auf genau eine Person schärfen

Die Schnelleinstellung legt im Hintergrund eine Access-Anwendung an, die
sich in **Cloudflare One unter Access controls → Applications** bearbeiten
lässt. Dort:

- **Policy:** die Regel „Cloudflare account" ersetzen durch Action
  **Allow**, Include → **Emails** → genau die Adresse, die der Test in
  Schritt 2 angezeigt hat (P1). Nicht ergänzen, **ersetzen** — Access
  lässt durch, wer **irgendeine** Regel erfüllt.
- **Login methods:** nur **GitHub**. Steht One-time PIN daneben offen, ist
  die Anmeldung so stark wie das schwächere von beidem (E2).
- **Session Duration:** 24 Stunden (8.3).

**Zwei Editoren, und man landet leicht im falschen.** Die Regel (wer darf)
ist eine **Richtlinie** und wird im Richtlinien-Editor gepflegt; die
Anmeldemethoden und die Sitzungsdauer gehören dagegen zur **Anwendung** —
dort im Abschnitt *Configure how users will authenticate*. Im
Richtlinien-Editor sucht man sie vergeblich.

Im Richtlinien-Editor außerdem darauf achten, dass **keine leere
Include-Zeile** stehen bleibt („Selector is… / Value is…"). Sie tut
vermutlich nichts, aber eine Zugriffsregel ist die falsche Stelle für
„vermutlich" — mit dem Papierkorb daneben entfernen.

Eine gespeicherte Richtlinie wirkt erst, wenn sie **an der Anwendung
hängt**. Dort unter *Access policies* die neue anhängen und die alte
„Cloudflare account" **entfernen**.

### Die Prüfung, ohne die dieser Schritt nichts wert ist

**Ein privates Fenster:**

```
https://<name>.<konto>.workers.dev
```

Erwartet wird die Anmeldemaske unter `<team>.cloudflareaccess.com` mit
**GitHub als einziger Möglichkeit** — nicht die Attrappe. Nach der
Anmeldung erscheint `leer`.

Dasselbe **vom Smartphone aus dem Mobilfunknetz**. Und einmal mit einem
**anderen** GitHub-Konto oder ohne Anmeldung abbrechen: Dann darf `leer`
nicht erscheinen.

**Abnahmekriterium:** Ohne Anmeldung kein Inhalt, und mit einer fremden
Identität auch nicht — geprüft in einem Fenster ohne Sitzung.

## Schritt 5 — Das Token für den Server

Erst jetzt, und mit möglichst wenig Rechten. In der Cloudflare-Konsole unter
*My Profile → API Tokens → Create Token → Create Custom Token*:

- Permissions: **Account → Workers Scripts → Edit**
- Account Resources: **Include → dieses eine Konto**
- TTL: ein Ablaufdatum setzen, damit ein vergessenes Token nicht ewig gilt

**Nicht die Vorlage „Edit Cloudflare Workers" nehmen.** Sie bringt
KV-, R2- und Routen-Rechte mit, die hier niemand braucht.

**Am 2026-09-17 auf dem Server bestätigt:** `Workers Scripts: Edit` allein
genügt für `wrangler deploy`, sofern `CLOUDFLARE_ACCOUNT_ID` gesetzt ist —
weitere Rechte wie `Account Settings: Read` oder `Memberships: Read`
braucht es dafür nicht.

Dazu die **Konto-Kennung** (Account ID) aus der Übersicht des Kontos. Sie
ist kein Geheimnis, gehört aber ebenfalls nicht ins Repository.

Das Token erscheint **genau einmal** und kommt in den Passwortmanager —
**noch nicht in die `.env`**. Solange der Upload von Hand läuft, wird es je
Sitzung eingegeben. Ein Geheimnis, das erst ein künftiger Code braucht,
liegt bis dahin nicht auf der Platte.

**Was das Token nicht kann, und das ist der Punkt:** Es darf den Worker
neu bereitstellen. Die Access-Anwendung davor darf es **nicht** anfassen.
Wer es stiehlt, kann den Inhalt ersetzen — nicht die Anmeldung abschalten
(N19).

## Schritt 6 — Hochladen, zuerst noch einmal die Attrappe

### 6a — Die Konfigurationsdatei, außerhalb des Repositorys

`wrangler deploy` braucht für den unbeaufsichtigten Betrieb eine
Konfigurationsdatei — die Kurzform `--assets` funktioniert laut
Dokumentation **nur interaktiv**. Die Datei nennt den Worker beim Namen,
und Name plus Konto-Subdomain **sind** die Adresse des Dashboards. In einem
öffentlichen Repository wäre sie auffindbar (T9). Sie liegt deshalb unter
`var\`, das `.gitignore` ausschließt.

```powershell
cd C:\Users\Administrator\Documents\TradingViewAnalyzer
New-Item -ItemType Directory -Force var\cloudflare, var\attrappe | Out-Null
Set-Content var\attrappe\index.html "<h1>leer</h1>"
```

Dann `var\cloudflare\wrangler.jsonc` anlegen — **mit absolutem Pfad**.
Mit einem relativen greift der Befehl ins Leere, sobald man schon im
Zielverzeichnis steht, und der Fehler scrollt beim nächsten Befehl weg.
Wie sich das äußert, steht am Ende dieses Schritts.

Inhalt, `<name>` durch den Namen des Workers ersetzen:

```jsonc
{
  "name": "<name>",
  "compatibility_date": "2026-09-17",
  "workers_dev": true,
  // Ausdruecklich, und das ist die Falle dieser Datei: preview_urls folgt
  // ohne Angabe dem Wert von workers_dev, also true. Ein Upload ohne diese
  // Zeile schaltete die in Schritt 4a abgeschalteten Vorschauen
  // stillschweigend wieder ein.
  "preview_urls": false,
  "assets": { "directory": "../attrappe" }
}
```

### 6b — Die Attrappe über den Server hochladen

**Warum noch einmal die Attrappe:** Dieser Durchgang prüft alles, was neu
ist — Token, Konfiguration, `wrangler` auf Windows — und vor allem, ob der
Upload an der Absicherung aus Schritt 4 etwas ändert. Geht dabei etwas
schief, steht draußen `leer` und nicht der Datenbaum.

```powershell
cd C:\Users\Administrator\Documents\TradingViewAnalyzer\var\cloudflare

# Das Token ueber Read-Host, nicht als Zeile: Windows PowerShell 5.1
# schreibt jede eingegebene Befehlszeile in eine Verlaufsdatei auf der
# Platte -- auch eine mit dem Token darin. Die Eingabe ueber Read-Host
# landet dort nicht.
$eingabe = Read-Host "Cloudflare-Token" -AsSecureString
$env:CLOUDFLARE_API_TOKEN = [System.Net.NetworkCredential]::new("", $eingabe).Password
$env:CLOUDFLARE_ACCOUNT_ID = "<Konto-Kennung>"
$env:WRANGLER_SEND_METRICS = "false"

npx wrangler@4 deploy

Remove-Item Env:\CLOUDFLARE_API_TOKEN
Remove-Variable eingabe
```

Beim ersten Aufruf fragt `npx`, ob es `wrangler` herunterladen darf.
`@4` hält die Hauptversion fest; ab 4.34 gilt die Grenze von 20.000 Dateien
je Version.

Die Ausgabe nennt das Asset-Verzeichnis, das `wrangler` tatsächlich gelesen
hat. **Der Pfad in `assets.directory` wird relativ zur Konfigurationsdatei
aufgelöst** (am 2026-09-17 so beobachtet), und weil der Aufruf ohnehin aus
deren Verzeichnis kommt, stimmen beide Lesarten überein.

### Wenn etwas schiefgeht

**`fetch failed`, und im Protokoll steht `"configFileType":"none"`.** Dann
hat `wrangler` die Konfigurationsdatei nicht gefunden und ist in seine
Selbsterkennung gelaufen, die Vorlagen aus dem Netz holt — der Netzwerkfehler
ist die Folge, nicht die Ursache. Nachsehen, ob die Datei wirklich im
Arbeitsverzeichnis liegt.

**`fetch failed` ohne diesen Eintrag.** Dann erst die Erreichbarkeit prüfen,
und zwar getrennt für PowerShell und Node:

```powershell
(Invoke-WebRequest https://api.cloudflare.com/client/v4/ -UseBasicParsing).StatusCode
node -e "fetch('https://api.cloudflare.com/client/v4/').then(r=>console.log('HTTP',r.status)).catch(e=>console.log('FEHLER:',e.message))"
```

Ein **HTTP 400** ist hier das *gute* Ergebnis: Es ist Cloudflares Antwort auf
einen Aufruf ohne Endpunkt und belegt, dass die Verbindung steht.

**Nur ein einzelnes Sternchen nach `Read-Host`.** Dann ist das Token nicht
angekommen — `Read-Host -AsSecureString` zeigt eines je Zeichen, bei einem
Token also um vierzig. Prüfbar mit `$env:CLOUDFLARE_API_TOKEN.Length`, was
nur eine Zahl ausgibt.

**Prüfung nach dem Upload, alle drei:**

1. **Privates Fenster** auf die Adresse: weiterhin erst GitHub, dann `leer`.
2. Im Worker unter **Settings → Domains & Routes**: Preview URLs stehen
   weiterhin auf **disabled**.
3. Unter **Access** ist der Worker weiterhin geschützt.

Schlägt eine davon fehl, geht der Datenbaum nicht hinauf.

### 6c — Der echte Datenbaum

In `var\cloudflare\wrangler.jsonc` die eine Zeile ändern:

```jsonc
  "assets": { "directory": "../dashboard" }
```

und denselben Upload wie in 6b wiederholen. `var\dashboard` enthält seit
Stufe K die Oberfläche im Zero-Knowledge-Build und darunter `data\` mit dem
verschlüsselten Baum. Der Zustandsvermerk liegt daneben und geht **nicht**
mit hinauf.

`/aktie/` findet `aktie/index.html` von selbst: Die Voreinstellung
`auto-trailing-slash` bildet genau das ab, was der statische Export mit
`trailingSlash: true` erzeugt.

**Abnahmekriterien** — dieselben wie in Stufe K, Schritt 4b, nur diesmal
über das Netz und vom Smartphone:

- Nach der GitHub-Anmeldung erscheint die Passphrase-Abfrage.
- Die Passphrase öffnet den Stand; ein Chart zeigt echte Kurse.
- Im Reiter *Netzwerk* nur opake Dateinamen und Binärantworten.
- Die Dauer bis zum geöffneten Stand auf dem Smartphone (**AK16**, Ziel:
  unter zwei Sekunden) — die Messung, die bisher nicht möglich war.

### Die Sicherheits-Header

Sie liegen als `frontend/public/_headers` im Repository und kommen über
`next build` in den Export; hochzuladen ist nichts Zusätzliches. Nach dem
ersten Upload einmal prüfen — Entwicklerwerkzeuge, Reiter *Netzwerk*, das
Dokument anklicken, Antwort-Header:

- `Content-Security-Policy` mit `default-src 'none'` und
  `frame-ancestors 'none'`
- `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`
- `Strict-Transport-Security` mit einem `max-age` im Jahresbereich
- bei einer Datei unter `/data/` zusätzlich `Cache-Control: no-store`

Die Dateien unter `/data/` erscheinen im Netzwerkreiter erst **nach** der
Passphrase — vorher hat die Seite nur ihr eigenes HTML geholt.

**Zwei Zugeständnisse stehen darin, beide gemessen und begründet.**
`script-src` erlaubt `'unsafe-inline'`: Next legt je Seite sieben
Inline-Skripte mit den RSC-Nutzdaten ab, die sich mit jedem Build ändern.
Hashes wären nur über einen Generator zu halten, dessen Fehler das Dashboard
beim Anbieter unbrauchbar machte. `style-src` erlaubt es ebenfalls, weil
`recharts` zur Laufzeit `style`-Attribute auf die SVG-Elemente setzt.

**Das Zugeständnis öffnet zwei Senken, nicht eine**, und beide sind heute
verschlossen: eingeschleustes rohes HTML — das Frontend setzt nirgends
welches ein, React maskiert jeden Berichtstext — und **`javascript:`-URLs**,
die `script-src` bewertet und `'unsafe-inline'` erlaubt. Jedes `href` und
`src` hat heute ein konstantes Präfix. Die zweite Bedingung fällt, sobald
Quellen-URLs aus Berichten klickbar werden; das ist bei „Quellenbindung" der
naheliegende nächste Schritt, und der Berichtstext stammt aus einem
Sprachmodell.

Ein Test in `frontend/src/lib/sicherheitsheader.test.ts` bewacht beides: die
Richtlinie selbst und die Annahme, auf der das Zugeständnis ruht — wer
`dangerouslySetInnerHTML` einführt, bekommt einen roten Test mit der
Begründung.

**Am 2026-09-17 beim Anbieter geprüft:** Die Konsole bleibt leer, es wird
also nichts blockiert; alle Header stehen am Dokument, `Cache-Control:
no-store` an den Dateien unter `/data/`; und der Kursverlauf zeichnet
unverändert — das war die Probe auf `style-src`, denn `recharts` hätte ohne
das Zugeständnis seine Größen nicht setzen können.

**Wogegen diese Header nicht helfen:** gegen einen gestohlenen Deploy-Token.
Wer beim Anbieter schreiben darf, ersetzt `_headers` mit demselben Upload.
Dagegen steht die Zugriffsregel, die außerhalb des Deployments liegt.

## Schritt 7 — Alte Versionen

**Löschen lassen sie sich nicht, erreichbar sind sie aber auch nicht.**
Jeder Upload ist eine neue Version des Workers, und Cloudflare bewahrt sie
auf; ein Weg, einzelne zu löschen, ist nicht dokumentiert. Erreichbar wäre
eine alte Version nur über ihre Vorschau-Adresse — und die sind seit
Schritt 4a abgeschaltet und bleiben es dank `"preview_urls": false`.

Das ist der Grund, warum diese Zeile in der Konfigurationsdatei die
wichtigste ist: Wegen des stabilen Salts stehen alle je hochgeladenen
Fassungen unter demselben Schlüssel.

**Zu prüfen nach jedem Upload von Hand:** Preview URLs stehen auf
*disabled*. Sobald der Exportschritt den Upload übernimmt, gehört diese
Prüfung in denselben Schritt.

## Schritt 8 — Die Notfallkarte

In den Passwortmanager, neben die Passphrase:

| Lage | Handgriff |
|---|---|
| Verdacht auf Datenabfluss | In Cloudflare One die Richtlinie der Anwendung leeren oder auf **Block** stellen — wirkt sofort, braucht keinen Upload |
| Token verloren | Token in der Konsole widerrufen; Inhalt und Anmeldung bleiben unberührt |
| Passphrase verloren oder verraten | Neue erzeugen, `.env` ändern, `cli publish --full`, hochladen. **Die alten Versionen bleiben bei Cloudflare unter dem alten Schlüssel liegen** — wer sie loswerden will, löscht den **ganzen Worker** und legt einen neuen mit anderem Namen an (dann ab Schritt 3) |
| Alles abschalten | Worker in der Konsole löschen (*Settings → Delete*); der Server merkt davon nichts |
| Server soll nicht mehr exportieren | `--dashboard-export none` in der Aufgabenplanung (Stufe K, Schritt 5) |

## Was danach noch offen ist

Der Upload läuft nach dieser Stufe **von Hand**. Der Exportschritt kennt
bislang nur `target: none | directory`. Sobald diese Stufe abgenommen ist,
folgt die Umsetzung des Datenwegs (Entscheidung **E4**: `wrangler` als
Unterprozess, wie hier von Hand erprobt, oder HTTP aus Python) samt Prüfung
der Vorschau-Adressen nach jedem Upload, den Sicherheits-Headern und der
Schaltung im Tageslauf (Stufe K, Schritt 5).

# Laufender Betrieb

## Betriebszustand

**Seit dem 2026-09-01 läuft die Aufgabenplanung täglich** (Eintrag aus
Stufe F, Argumente aus Stufe H). Geschaltet sind: Marktdaten `ibkr`,
Earnings-Termine `finnhub`, Analystenempfehlungen `finnhub`,
Fundamentaldaten `edgar`, Optionsanalyse `ibkr`, Technical Agent
`anthropic`, Research **`none`** (bewusst abgeschaltet — Kostenentscheidung;
die Einzelprobe aus Stufe G Schritt 2 bleibt der Weg für gezielte
Recherchen), Meldung `telegram`.

Maßgeblich ist der Argumentstring des Aufgabenplanungs-Eintrags auf dem
Server — dieser Absatz beschreibt ihn nur. Ändert sich der geschaltete
Stand, wird er hier nachgeführt; vor dem 2026-09-01 gab es keinen
automatischen Tageslauf, nur manuell gestartete.

**Der Dashboard-Dienst läuft noch nicht.** Er ist gebaut und beschrieben
(Stufe J), auf dem Server aber noch nicht eingerichtet. Diese Zeile wird
umgeschrieben, sobald er dort steht — bis dahin gibt es genau einen
geplanten Vorgang, den Tageslauf.

**Der Export nach draußen ebenfalls nicht** (Stufe K). Er ist gebaut und
getestet, `dashboard_export.target` steht auf `none`, und die Entscheidung
darüber steht aus.

## Nach jedem Serverneustart

Die TWS von Hand starten und anmelden. Ohne angemeldete Sitzung entscheidet der
Dispatcher nicht einmal, ob heute ein Handelstag ist — er meldet Rückgabewert 1
und versucht es beim nächsten Start erneut, bis die Nachholfrist abläuft.

## Sicherung

Doc 10 §15 fordert ein tägliches Datenbank-Backup mit Restore-Test. Das
MVP setzt davon die einfache Stufe um: **ein täglicher `pg_dump` über die
Aufgabenplanung, in einen eigenen Ordner auf demselben Laufwerk.**

> **Bewusste Einschränkung** (Beschluss vom 2026-09-01): Die Ablage liegt
> *nicht* außerhalb des primären Datenvolumes, wie Doc 10 §15 es als
> Zielbild nennt. Sie schützt gegen Softwarefehler, Fehlbedienung und eine
> kaputte Migration — **nicht** gegen den Ausfall der Platte selbst. Neu zu
> bewerten nach stabilem Betrieb, zusammen mit der Expositionsfrage aus
> [ADR 0049](adr/0049-dashboard-mvp-nur-lan.md).

### Das Passwort zuerst

`%APPDATA%\postgresql\pgpass.conf` anlegen, eine Zeile:

```
localhost:5432:*:ata:<passwort>
```

**Nie in die Task-Argumente.** Die sind im Aufgabenplaner für jeden lesbar,
der den Rechner sieht.

### Die beiden Skripte

Sie liegen **im Repository** unter `scripts\` und wandern damit mit `git
pull` mit. Anders als die `.env` enthalten sie kein Geheimnis — das Passwort
steht in der `pgpass.conf`, nicht im Skript. Ein Sicherungsskript, das nur
auf einem Rechner existiert und nirgends versioniert ist, wäre selbst ein
Ausfallrisiko.

| Skript | Zweck |
|---|---|
| `scripts\sicherung.ps1` | täglicher Dump, Lesbarkeitsprüfung, Aufräumen alter Stände |
| `scripts\sicherung-probe.ps1` | Zählprobe: Wiederherstellung in eine Wegwerfdatenbank |

Erster Lauf von Hand, um zu sehen, dass er trägt:

```powershell
cd C:\Users\Administrator\Documents\TradingViewAnalyzer
powershell.exe -NoProfile -File scripts\sicherung.ps1 -Ziel D:\backups\ata
echo $LASTEXITCODE
```

Erwartet: `0`, eine Zeile „Sicherung erfolgreich" mit Größenangabe, und eine
`.dump`-Datei im Zielordner. **Rückgabewert 2 heißt: keine brauchbare
Sicherung** — der Grund steht darüber und zusätzlich in
`sicherung.log` neben den Dumps.

Zwei Eigenschaften des Skripts, die den Unterschied machen:

- Es **prüft den Dump auf Lesbarkeit** (`pg_restore --list`), nicht nur auf
  Vorhandensein. Ein abgebrochener Schreibvorgang hinterlässt ebenfalls eine
  Datei.
- Es **räumt erst nach einer erfolgreichen Sicherung auf.** Umgekehrt
  löschte ein fehlgeschlagener Lauf die letzten funktionierenden Stände.

### In die Aufgabenplanung

| Feld | Wert |
|---|---|
| Name | `AI Trading Analyst — Sicherung` |
| Trigger | Täglich, Beginn **22:00** (nach dem Dispatch-Fenster 17:30–21:30) |
| Programm | `powershell.exe` |
| Argumente | `-NoProfile -File C:\Users\Administrator\Documents\TradingViewAnalyzer\scripts\sicherung.ps1 -Ziel D:\backups\ata` |

Anders als der Tageslauf braucht diese Aufgabe **keine** angemeldete Sitzung
— sie spricht nur PostgreSQL an, nicht die TWS. „Unabhängig von der
Benutzeranmeldung ausführen" ist hier richtig.

Die Spalte **„Letztes Ausführungsergebnis"** im Aufgabenplaner ist das
einzige Signal, das ohne Zutun sichtbar wird. Sie zeigt genau den
Rückgabewert des Skripts; deshalb meldet es einen Fehlschlag als 2 und nicht
als 0.

### Zählprobe

Einmal bei der Einrichtung, danach bei jedem Pflegetermin:

```powershell
powershell.exe -NoProfile -File scripts\sicherung-probe.ps1 -Quelle D:\backups\ata
```

Das Skript stellt den jüngsten Dump in die Wegwerfdatenbank
`ata_restore_probe` wieder her, zählt `intraday_bars`, `analysis_runs`,
`stock_reports` und `stocks`, stellt die Produktivzahlen daneben und wirft
die Wegwerfdatenbank wieder weg — auch nach einem Abbruch.

**Die Produktivdatenbank wird nie beschrieben.** Der Zielname steht fest im
Skript und ist kein Parameter: Ein Parameter ließe sich mit dem
Produktivnamen belegen, und das Skript löscht seine Zieldatenbank am Ende.

Seither hinzugekommene Läufe erklären eine Differenz zwischen beiden Spalten.
Eine Null erklärt nichts.

**Abnahmekriterium:** ein automatisch entstandener Dump und eine
durchgespielte Zählprobe.

## Pflege

Gemessene Zahlen altern genauso still wie geratene — nur mit besserem
Gewissen. Deshalb ein fester Turnus: **quartalsweise, nächster Termin
2026-12-01.** Drei Gruppen:

1. **Gemessene Schwellen** in `config/default.yaml` (`scoring.thresholds`,
   `analyst_buy_share`, `options_annualized_return`): Messläufe
   `cli ratings --watchlist --output ...` und
   `cli options --provider ibkr --watchlist --output ...`, Auswertung mit
   `cli calibrate-scores`, Nachziehen nach dem Muster „messen, dann
   festlegen" ([ADR 0045](adr/0045-schwellen-der-score-teilwerte.md),
   [ADR 0048](adr/0048-optionsanalyse-im-tageslauf.md)). Die
   **Options-Schwellen** haben einen Zusatzanlass außer der Reihe: eine
   unruhige Marktphase verschiebt die ganze Prämienverteilung (ADR 0048 —
   „kurzlebiger als die übrigen").
2. **LLM-Preislisten** (`research.pricing`, `technical_agent.pricing`) —
   von Hand gepflegt, gegen den aktuellen Anthropic-Katalog prüfen. Sie
   speisen nur die Kostenschätzung im Protokoll; ein veralteter Wert fällt
   nirgends von allein auf.
3. **Modell-Identifier** (`llm.research`, `llm.technical`, jeweils samt
   `fallback_model`) — gegen den dann aktuellen Katalog.
4. **Gemeldete Schwachstellen in Abhängigkeiten.** Der Workflow
   `.github/workflows/audit.yml` läuft wöchentlich und meldet, ohne zu
   blockieren — ob ein Fund gefährlich ist, hängt daran, wie das Paket
   genutzt wird. Die offenen Meldungen gehören einmal je Turnus angesehen
   und beschieden: aktualisieren, oder mit Begründung stehen lassen.

   **Offen stehen gelassen (Stand 2026-09-01):** `postcss` bis
   einschließlich 8.5.22, vier Advisories (XSS über unmaskiertes `</style>`
   und dreimal Dateizugriff über eine `sourceMappingURL` in
   CSS-Kommentaren), transitiv über Next.js 15. Die Fassung dagegen ist
   **Next 16** und damit ein Bruch.

   Warum das vertretbar ist: `postcss` läuft ausschließlich zur Bauzeit und
   ausschließlich über **eigenes** CSS (`src/app/globals.css`). Alle vier
   Advisories setzen voraus, dass ein Angreifer die verarbeitete CSS-Quelle
   beeinflusst. Träte das ein, hätte er bereits Schreibzugriff auf das
   Repository — dann ist `postcss` das kleinste Problem.

   **Solange der Punkt steht, meldet die npm-Hälfte der Prüfung dauerhaft
   rot** — wer sie ansieht, muss wissen, dass das dieser eine bekannte Fund
   ist und nicht ein neuer. Beim nächsten Turnus neu zu bewerten, dann
   zusammen mit dem Sprung auf Next 16.

   *`sharp` und `nanoid` standen hier ebenfalls; beide sind am 2026-09-01
   ohne Bruch gehoben worden (`npm audit fix`).*

Dazu die **Restore-Probe** aus dem Sicherungsabschnitt. Änderungen laufen
wie immer über Branch und Pull Request, nie lokal auf dem Server (Stufe G).

## Wenn ein Tageslauf ausbleibt

Überschreitet ein unerledigter Lauf die Nachholfrist
(`scheduler.max_catch_up_seconds`, ausgeliefert zwei Stunden, also 14:50 New
Yorker Zeit), geht eine Meldung raus — über Telegram, sofern Stufe H eingerichtet
ist ([ADR 0024](adr/0024-benachrichtigungskanal-telegram.md)). Ohne Stufe H
erscheint sie nur im Protokoll, ausdrücklich als *nicht versendet* gekennzeichnet,
und ein stiller Ausfall wird dann nur beim Blick ins Protokoll sichtbar.

Ein Ausfall des Kanals selbst — Telegram nicht erreichbar, Token abgelaufen —
hält den Tageslauf **nicht** an: Die Zustellung ist eine Systemgrenze wie jeder
externe Anbieter und wird isoliert. Die Meldung gilt dann als nicht gesendet und
wird beim nächsten Start in 15 Minuten erneut versucht.

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

# Nur wenn sich unter frontend\ etwas geändert hat:
cd ..\frontend
npm ci
npm run build
cd ..\backend
```

Findet `git pull` einen lokalen Diff in `config/default.yaml`, wurde auf dem
Server konfiguriert statt in der Aufgabenplanung — siehe Stufe G.

Ein neuer Export wird ohne Neustart ausgeliefert — der Dienst liest die
Dateien bei jeder Anfrage. Neu starten muss man ihn nur, wenn `frontend\out`
beim Start des Dienstes noch **gar nicht** existierte: Dann ist das
Dashboard nicht eingehängt, und die API antwortet allein.
