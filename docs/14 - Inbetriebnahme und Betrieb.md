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
| `ATA_LLM_API_KEY` | erst ab Stufe G, Schritt 2 |
| `ATA_SESSION_SECRET` | erst mit dem Dashboard — heute ohne Wirkung |
| `ATA_NOTIFICATION_TOKEN` | erst ab Stufe H (Telegram, [ADR 0024](adr/0024-benachrichtigungskanal-telegram.md)) |

Die `.env` ist von `.gitignore` ausgeschlossen und darf nie committet werden.

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
eine `<symbol>.bars.csv`. Danach einmalig aufzeichnen und beides committen:

```powershell
$env:ATA_GOLDEN_MASTER_RECORD = "1"
.venv\Scripts\python.exe -m pytest tests\golden
Remove-Item Env:\ATA_GOLDEN_MASTER_RECORD
```

Die Reihe muss über 250 Kerzen hinausreichen — darunter antwortet die
Kandidatenprüfung ausnahmslos mit `UNKNOWN_DATA_INCOMPLETE`, und die
Aufzeichnung enthielte nichts. Ein Test hält das fest.

## Zwischenschritt: Reichweite des Handelskalenders messen (optional)

Kein Abnahmekriterium, sondern die Messung hinter einer offenen
Entscheidung (E4). Der Earnings-Filter zählt Handelstage bis zum nächsten
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

**Entschieden wird damit nichts**; das Ergebnis geht in ein ADR.

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
Verdrahtung, aussagelos für den Inhalt. Mit `anthropic` kostet jeder Aufruf
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
-m ai_trading_analyst.cli dispatch --provider ibkr --earnings-provider finnhub --research-provider anthropic --notification-channel telegram --telegram-chat-id <CHAT_ID>
```

Der Kanal wird nur im Fehlerfall angefasst — im Regelfall sendet er nichts.
Die Meldung enthält bewusst nur Handelstag, Kerzenzeitpunkt und Ursache, keine
Kurse oder Analyseergebnisse (ADR 0024).

---

# Laufender Betrieb

## Nach jedem Serverneustart

Die TWS von Hand starten und anmelden. Ohne angemeldete Sitzung entscheidet der
Dispatcher nicht einmal, ob heute ein Handelstag ist — er meldet Rückgabewert 1
und versucht es beim nächsten Start erneut, bis die Nachholfrist abläuft.

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
```

Findet `git pull` einen lokalen Diff in `config/default.yaml`, wurde auf dem
Server konfiguriert statt in der Aufgabenplanung — siehe Stufe G.
