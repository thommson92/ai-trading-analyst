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

## Schritt 1 — Node prüfen

```powershell
node --version
```

Node wird **nur zum Bauen** gebraucht, nicht zur Laufzeit
([ADR 0052](adr/0052-dashboard-als-statischer-export.md)). Fehlt es, die
aktuelle LTS-Fassung installieren; ohne Node gibt es keinen Export und damit
kein Dashboard — die API und der Tageslauf laufen aber weiter.

## Schritt 2 — Export bauen

```powershell
cd C:\...\frontend
npm ci
npm run build
```

Ergebnis ist der Ordner `frontend\out`. Er ist nicht eingecheckt und
entsteht auf jedem Rechner neu.

## Schritt 3 — Dienst zur Probe starten

```powershell
cd C:\...\backend
.venv\Scripts\python.exe -m uvicorn ai_trading_analyst.main:app --host 0.0.0.0 --port 8000
```

Dann lokal `http://127.0.0.1:8000/` öffnen. Die Tagesübersicht muss den
letzten Lauf zeigen; `http://127.0.0.1:8000/api/v1/system/readiness` muss
`ready` melden.

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

Das Skript liegt **außerhalb des Repositories** (wie die `.env`), etwa als
`C:\...\backup-ata.ps1`:

```powershell
$stamp = Get-Date -Format yyyy-MM-dd
pg_dump -Fc -U ata -d ai_trading_analyst `
    -f "C:\...\backups\ata\ai_trading_analyst-$stamp.dump"
Get-ChildItem "C:\...\backups\ata\*.dump" |
    Where-Object LastWriteTime -lt (Get-Date).AddDays(-14) | Remove-Item
```

Vierzehn Tage rollierend: lang genug, um einen erst spät bemerkten Fehler
zu überleben, kurz genug, dass der Ordner nicht wächst. Das **Passwort
steht nie in den Task-Argumenten**, sondern in
`%APPDATA%\postgresql\pgpass.conf` (eine Zeile:
`localhost:5432:*:ata:<passwort>`) — Task-Argumente sind im
Aufgabenplaner für jeden lesbar, der den Rechner sieht.

| Feld | Wert |
|---|---|
| Trigger | Täglich, Beginn **22:00** (nach dem Dispatch-Fenster 17:30–21:30) |
| Programm | `powershell.exe` |
| Argumente | `-NoProfile -File C:\...\backup-ata.ps1` |

**Restore-Probe** — einmal bei der Einrichtung und danach bei jedem
Pflegetermin, **niemals in die Produktivdatenbank**:

```powershell
psql -U ata -d postgres -c "CREATE DATABASE ata_restore_test OWNER ata;"
pg_restore -U ata -d ata_restore_test "C:\...\backups\ata\<juengster>.dump"
psql -U ata -d ata_restore_test -c "SELECT count(*) FROM intraday_bars;"
psql -U ata -d ata_restore_test -c "SELECT count(*) FROM analysis_runs;"
psql -U ata -d postgres -c "DROP DATABASE ata_restore_test;"
```

Die Zählwerte müssen zu den Produktivzahlen des Sicherungstages passen.
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
