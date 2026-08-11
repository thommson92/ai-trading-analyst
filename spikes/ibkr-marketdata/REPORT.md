# Interactive Brokers Marktdaten-Spike: Bericht

**Status: PHASE B ABGESCHLOSSEN -- EMPFEHLUNG: GO_WITH_LIMITATIONS**
(Details und Einschränkungen in Abschnitt 12)

Freigegeben durch den Projektinhaber am 2026-08-11 (siehe
[ADR 0013](../../docs/adr/0013-interactive-brokers-kandidat-vorschlag.md)).
Vorprüfung der Marktdaten-Lizenzbedingungen (Market Data API Supplement zur
GFIS Subscriber Agreement) ist mit GO abgeschlossen und in ADR 0013
dokumentiert -- Gegenstand dieses Berichts ist ausschließlich die
technische Machbarkeit.

## 1. Executive Summary

Alle sieben ursprünglich gestellten Fragen (README.md) sowie die während
des Spikes zusätzlich aufgetretene Koexistenzfrage (Frage 8) sind live
gegen die TWS des Nutzers (Live-Konto, Port 7496) beantwortet. Sechs von
acht Fragen sind **vollständig bestätigt**, eine (Frage 2, unbeaufsichtigter
Neustart) wurde bewusst durch ein manuelles Betriebsmodell ersetzt statt
technisch gelöst, eine (Frage 6, Zusatzdaten) ist im Ergebnis gemischt, aber
für jeden Teilaspekt eindeutig geklärt.

**Was das belegt:**
- Verbindungsaufbau, 195-Minuten-Aggregation, Erkennung abgeschlossener vs.
  laufender Kerzen und historische Datenabdeckung funktionieren zuverlässig
  über die offizielle `ib_async`/TWS-API (Frage 1, 3, 4, 5).
- Ein Mehrsymbol-Durchlauf über 10 Referenzaktien liefert konsistente
  Ergebnisse in vertretbarer Zeit (8 s für 10 Symbole) über eine einzige
  Verbindung (Frage 7).
- Die Koexistenz mit der bereits produktiv laufenden Anwendung TAT
  (Trade Automation Toolbox, echte Optionsorders über dieselbe TWS-Instanz)
  ist sicher, solange unterschiedliche Client-IDs verwendet werden -- ohne
  jede Änderung an TAT (Frage 8).
- Analystenschätzungen, Optionsketten-Struktur und -- nach Aktivierung
  eines zusätzlichen IBKR-Optionsmarktdaten-Abos -- auch modellierte
  Options-Greeks (Delta/Gamma/Vega/Theta/IV) sind über dieselbe API
  verfügbar (Frage 6).

**Was das nicht belegt bzw. bewusst offenlässt:**
- **Kein vollautomatischer Wiederanlauf nach einem echten Windows-Neustart.**
  Der Projektinhaber hat sich für denselben manuellen Montags-Neustart
  entschieden, den er bereits für TAT praktiziert, statt IB Gateway/IBC zu
  automatisieren (Frage 2) -- Windows-Autologon bleibt unabhängig davon eine
  eigene, weiterhin offene Entscheidung.
- **Earnings-Termine sind über IBKR (`CalendarReport`) nicht nutzbar** --
  der Projektinhaber hat entschieden, dafür eine separate Datenquelle
  einzuplanen (Frage 6).
- Drei echte, live gefundene Bugs wurden noch während der Validierung
  behoben: ein Python-3.14/`eventkit`-Kompatibilitätsproblem, ein
  Sicherheitsleck durch ungefiltertes Logging von Kontodaten in einer
  Fremdbibliothek, und eine fälschlich als "ok" gewertete, tatsächlich
  inhaltslose Fundamentaldaten-Antwort (Details in den jeweiligen
  Abschnitten sowie Abschnitt 10).

## 2. Testumgebung

### Phase A (Grundgerüst, abgeschlossen)

- Projektskelett (`config.py`, `redaction.py`, `logging_setup.py`,
  `results_store.py`, `steps/step_connectivity.py`, `cli.py`) mit
  Unit-Tests gegen ein Fake-Client-Objekt, ohne echte TWS/Gateway-Instanz.
- Bibliothek: `ib_async` (aktiv gepflegter Nachfolger von `ib_insync`) als
  Wrapper um die offizielle TWS API.

### Phase B (Live-Validierung, ausstehend)

Voraussetzungen beim Nutzer, bevor Phase B beginnen kann:

- TWS oder IB Gateway installiert und gestartet.
- API-Zugriff aktiviert: TWS/Gateway-Einstellungen -> API -> Settings ->
  "Enable ActiveX and Socket Clients".
- Tatsächlich verwendeter Port bekannt (TWS Live 7496 / Paper 7497,
  IB Gateway Live 4001 / Paper 4002 -- abhängig von Nutzerwahl).
- Klarheit, ob gegen ein Paper- oder ein Live-Konto getestet wird (dringend
  empfohlen: Paper-Konto für die gesamte Spike-Phase, um jedes
  Ausführungsrisiko auszuschließen -- dieser Spike testet ohnehin
  ausschließlich Lesezugriffe, siehe README "Sicherheitsgrenzen").

## 3. Frage 1: Verbindungsaufbau -- BESTAETIGT

**Echter Fund, live auf macOS mit Python 3.14 reproduziert:** `ib_async`s
Abhängigkeit `eventkit` ruft beim Import `asyncio.get_event_loop()` auf.
Seit Python 3.14 wirft das ohne bereits laufenden Event-Loop im
Hauptthread `RuntimeError` statt (wie in älteren Python-Versionen)
stillschweigend einen neuen Loop anzulegen. Ohne Gegenmaßnahme schlägt
bereits `import ib_async` fehl -- nicht erst der eigentliche
Verbindungsaufbau.

Mitigation: `IbAsyncClient` stellt vor dem Import sicher, dass ein
Event-Loop existiert (`_ensure_event_loop_exists()` in
`step_connectivity.py`). Mit dieser Absicherung funktioniert der Import und
der komplette Verbindungsversuch fehlerfrei bis zur eigentlichen
Netzwerkebene -- gegen einen nicht erreichbaren Port (kein TWS/Gateway
gestartet) liefert der Schritt sauber `FAILED` mit
`ConnectionRefusedError`, kein Absturz, kein stiller Fehlschlag:

```json
{
  "_status": "failed",
  "host": "127.0.0.1",
  "port": 7497,
  "error": "ConnectionRefusedError: [Errno 61] Connect call failed ('127.0.0.1', 7497)"
}
```

**Live bestätigt am 2026-08-11** gegen TWS auf dem Windows-Zielserver
(Live-Konto, Port 7496, ursprünglich mit Empfehlung "Read-Only API
aktivieren" -- diese Empfehlung wurde zurückgenommen, siehe Korrektur in
Frage 8: Read-Only API ist ein globaler TWS-Schalter und hätte die
bestehende Anwendung TAT an echten Order-Übermittlungen gehindert; sie ist
tatsächlich nicht aktiviert). "Allow connections from localhost only" ist
aktiviert. Ergebnis (Account-Kennung wie vorgesehen maskiert):

```json
{
  "_status": "ok",
  "host": "127.0.0.1",
  "port": 7496,
  "client_id": 17,
  "managed_accounts": ["U******40"],
  "server_version": 178,
  "connection_stats": {
    "duration_seconds": 0.71,
    "num_bytes_recv": 12752,
    "num_bytes_sent": 118,
    "num_msg_recv": 271,
    "num_msg_sent": 8
  }
}
```

Damit ist Frage 1 (Verbindungsaufbau, Lesen von Basisinfos) für den
TWS-Weg auf Port 7496 bestätigt. IB Gateway als Alternative wurde nach der
Betriebsmodell-Entscheidung zu Frage 2 (manueller Montags-Neustart statt
IBC-Automatisierung) bewusst nicht mehr weiterverfolgt -- TWS ist der
tatsächlich vorgesehene Zugriffsweg.

### Sicherheitsfund (live gefunden, noch am selben Tag behoben)

Beim ersten Live-Test hat `ib_async.IB.connect()` -- wie von der Bibliothek
ungefragt vorgesehen -- automatisch Account-Positionen und Portfoliowerte
synchronisiert und dabei über ihren eigenen Logger (`ib_async.wrapper`,
Level INFO) **unmaskierte** Account-Kennung, konkrete Optionspositionen,
Einstandspreise und unrealisierten Gewinn/Verlust in die Konsolen-/Log-
Ausgabe geschrieben. Das betraf ausschließlich die rohe Log-Ausgabe der
Bibliothek, nicht das von uns gespeicherte Ergebnis -- die
`managed_accounts` im gespeicherten JSON (siehe oben) waren korrekt
maskiert, weil sie durch unsere eigene `redaction.py` liefen. Fremde
Logger tun das nicht automatisch.

**Fix:** `logging_setup.configure_logging()` hebt den Logger
`ib_async.wrapper` gezielt auf `WARNING` an, sodass diese
Positions-/Portfolio-Dumps gar nicht erst ausgegeben oder gespeichert
werden. Mit Regressionstest abgesichert (`tests/test_logging_setup.py`)
und am 2026-08-11 live gegen dasselbe TWS erneut bestätigt: identischer
Verbindungsaufbau, keine Positions-/Portfolio-Zeilen mehr in der Ausgabe.
`num_bytes_recv` bleibt unverändert bei ca. 12,8 kB -- die Bibliothek
fragt die Daten weiterhin intern ab, sie werden nur nicht mehr geloggt.
Echte Datenminimierung bleibt der in "Konsequenz für Schritt 4" genannte
spätere Schritt.

**Konsequenz für Schritt 4 (Produktivintegration):** Diese Beobachtung
spricht dafür, für den Produktivadapter nicht die hochlevelige `IB`-Klasse
zu verwenden (die intern automatisch Konto-Sync betreibt), sondern die
tiefer liegende `Client`-Klasse direkt anzusprechen, die diesen
automatischen Sync nicht durchführt -- echte Datenminimierung statt nur
Log-Unterdrückung. Für den Spike selbst ist die Log-Unterdrückung
ausreichend, da wir ohnehin nie Positions-/Portfoliodaten auswerten.

## 4. Frage 2: Unbeaufsichtigter Neustart (IB Gateway + IBC) -- ZURUECKGESTELLT ZUGUNSTEN EINES MANUELLEN BETRIEBSMODELLS

### Ausdrückliche Umfangsentscheidung des Projektinhabers (2026-08-11)

IBC (Interactive Brokers Controller) automatisiert ausschließlich den
**IB-Gateway-eigenen Login** (Benutzername/Passwort/2FA-Dialoge) -- den
Teil, für den TradingView Desktop keine Automatisierungsmöglichkeit bot.
Es löst **nicht** das andere, ursprüngliche R2-Problem: Nach einem echten
Windows-Neustart braucht IB Gateway wie jede GUI-Anwendung weiterhin eine
bereits angemeldete, interaktive Windows-Sitzung (Windows-Session-0-
Isolation gilt unverändert). Das ist exakt der Teil, den der Projektinhaber
beim TradingView-Spike bewusst zurückgestellt hat (Windows-Autologon =
dauerhaft auf dem Server hinterlegtes Zugangsdatum, eigene
Sicherheitsentscheidung).

Auf Nachfrage hat der Projektinhaber diese Abgrenzung für den IBKR-Spike
ausdrücklich bestätigt und **nicht** neu geöffnet:

> "Bitte Option 1 umsetzen: Im aktuellen Spike nur die IBC-/IB-Gateway-
> Automatisierung innerhalb einer bereits angemeldeten Windows-Sitzung
> testen. Windows-Autologon ist weiterhin ausdrücklich out of scope und
> darf nicht stillschweigend eingerichtet werden. Entsprechend soll
> Frage 2/R2 durch diesen Spike nicht als vollständig gelöst gelten:
> Abgedeckt: automatischer Start und Login von IB Gateway nach einem
> Gateway-Absturz oder -Neustart innerhalb einer bestehenden interaktiven
> Windows-Sitzung. Nicht abgedeckt: vollständig unbeaufsichtigte
> Wiederherstellung nach einem echten Windows- bzw. Host-Neustart."

**Konsequenz für dieses Dokument:** Selbst ein vollständig erfolgreicher
Test in diesem Abschnitt bedeutet **nicht**, dass R2 gelöst ist. Es bedeutet
nur, dass die IBKR-seitige Login-Automatisierung funktioniert -- die
Windows-Autologon-Frage bleibt ein eigenständiger, unverändert offener
Entscheidungspunkt, unabhängig vom technischen Ergebnis dieses Abschnitts.

### Zusätzlicher Hinweis: Zugangsdaten in der IBC-Konfiguration

Damit IBC den IB-Gateway-Login automatisieren kann, braucht es Zugriff auf
die IBKR-Zugangsdaten (`config.ini`, Felder `IbLoginId`/`IbPassword`). Das
ist eine andere, engere Frage als Windows-Autologon (sie betrifft nur den
IBKR-Login, nicht die Windows-Anmeldung), aber ebenfalls ein dauerhaft auf
dem Server hinterlegtes Zugangsdatum. Empfehlung für die Einrichtung (siehe
Anleitung unten): Datei außerhalb des Git-Repositories ablegen, Windows-
Dateiberechtigungen auf das Administrator-/Betriebskonto einschränken.

### Weiterer Verlauf (2026-08-11): Betriebsmodell geklärt, IB Gateway/IBC zurückgestellt

Die IBC-Einrichtung (Schritt 4 der Anleitung: `StartGateway.bat`) funktionierte
beim Nutzer nicht auf Anhieb. Bevor das weiter verfolgt wurde, hat der
Nutzer den geplanten Betrieb präzisiert:

> "Auf dem Windows-Server läuft bereits dauerhaft eine andere Anwendung,
> die ebenfalls die IBKR-API über die TWS nutzt. Der Server installiert
> regelmäßig sonntags um 23:55 Uhr deutscher Zeit notwendige Updates und
> wird anschließend neu gestartet. Mein bisheriger Betriebsablauf ist,
> mich montags manuell bei der IBKR TWS anzumelden und danach die
> bestehende Anwendung zu starten. Für den Analyzer können wir zunächst
> denselben Ablauf vorsehen: Nach dem geplanten sonntäglichen
> Windows-Neustart erfolgt die Wiederinbetriebnahme am Montag bewusst
> manuell. [...] Die Nichtverfügbarkeit zwischen dem sonntäglichen
> Neustart und dem manuellen Start am Montag wird vorerst als bekannte
> betriebliche Einschränkung akzeptiert."

**Konsequenz:** IB Gateway und IBC werden für diesen Spike **nicht weiter
verfolgt**. Ihr einziger Zweck wäre die Login-Automatisierung *innerhalb*
einer laufenden Sitzung gewesen -- bei ohnehin manuellem Wochenstart
entfällt dieser Nutzen, während zusätzliche Komplexität (separater
Prozess, eigene Zugangsdaten in `config.ini`, zusätzlicher Fehlerpunkt --
siehe den nicht funktionierenden Testlauf) bliebe. Der Analyzer wird
stattdessen direkt über **TWS** betrieben, wie die bereits bestehende
Anwendung auch.

### Testumfang und -stand (final für diesen Spike)

- **Abgedeckt:** keine neue technische Automatisierung. Bewusst
  akzeptiertes manuelles Betriebsmodell, deckungsgleich mit dem bereits
  etablierten Ablauf der bestehenden Anwendung auf demselben Server.
- **Ausdrücklich nicht abgedeckt und nicht Ziel dieses Spikes:**
  vollständig unbeaufsichtigte Wiederherstellung nach einem echten
  Windows-/Host-Neustart (erfordert Windows-Autologon -- separate,
  weiterhin offene Entscheidung, siehe ADR 0013). Ausbaustufe für später,
  falls gewünscht.
- **Status: Geklärt.** R2 ist damit nicht technisch gelöst, sondern durch
  eine bewusste betriebliche Entscheidung des Projektinhabers umgangen --
  exakt das gleiche Muster wie beim TradingView-Spike, nur diesmal
  zusätzlich durch die bereits gelebte Praxis der bestehenden Anwendung
  gedeckt.

## 4a. Frage 8: Koexistenz mit bestehender TWS-/API-Anwendung -- BESTAETIGT

Neu aufgekommen durch die obige Betriebsklärung: Der Windows-Server betreibt
bereits dauerhaft eine andere Anwendung, die ebenfalls über die TWS-API
auf dasselbe IBKR-Konto zugreift -- mutmaßlich dieselbe TWS-Instanz
(Port 7496), gegen die auch Frage 1/3/4 dieses Spikes bereits erfolgreich
getestet wurden. Das erklärt rückwirkend auch die in Abschnitt 3
("Sicherheitsfund") beobachteten SPX-Optionspositionen -- diese stammen
mit hoher Wahrscheinlichkeit von dieser bestehenden Anwendung, nicht vom
Analyzer.

**Nicht verhandelbare Nebenbedingung (Nutzervorgabe):** Die bestehende
Anwendung darf durch den Analyzer-Spike **nicht beeinträchtigt oder
umkonfiguriert** werden. Es werden keine Änderungen an der bestehenden
TWS-Konfiguration vorgenommen, kein zweiter Login versucht.

### Zwei Optionen, fachlich eingeordnet

1. **Geteilte TWS-Sitzung, unterschiedliche Client-IDs (favorisiert).**
   IBKR unterstützt offiziell mehrere gleichzeitige API-Clients an einer
   TWS-Instanz, solange jeder eine eindeutige `clientId` verwendet. Kein
   zweiter Login, keine Änderung an der bestehenden Sitzung -- der
   Analyzer wäre einfach ein weiterer, unabhängiger, rein lesender
   API-Client an derselben, bereits laufenden TWS.
2. **Separates IB Gateway für den Analyzer, bestehende Anwendung bleibt
   auf TWS.** Risikoreicher: IBKR lässt pro Benutzername in der Regel nur
   eine aktive Sitzung gleichzeitig zu. Ein zweiter Login mit demselben
   Benutzernamen könnte die bestehende TWS-Sitzung trennen -- das wäre
   genau die ausgeschlossene Beeinträchtigung. Nur sinnvoll, falls ein
   separater IBKR-Benutzername für denselben Account existiert.

### Antworten des Nutzers (2026-08-11) und Einordnung

Die bestehende Anwendung ist die **Trade Automation Toolbox (TAT)**, ein
kommerzielles Optionen-Handelsautomatisierungs-Tool.

| # | Antwort | Einordnung |
|---|---|---|
| K1 | Client-ID von TAT: **99**. Ermittelt über die TAT-eigenen Verbindungseinstellungen. | Eindeutig verschieden von unserer `IBKRSPIKE_CLIENT_ID` (`17`) -- keine Kollision. |
| K2 | Keine Auffälligkeiten während der bisherigen Tests. TAT prüft nur zweimal täglich zu festen Uhrzeiten Einstiegskriterien und übermittelt ggf. eine Optionsorder, sonst passiert nichts. | Passt zur unauffälligen Koexistenz, auch wenn die Testfenster nicht zwingend mit den TAT-Handelszeitpunkten zusammenfielen. |
| K3 | TAT läuft über **dieselbe TWS-Instanz, denselben Port (7496)** wie unser Analyzer. Verbindung bleibt nach Einschätzung des Nutzers den ganzen Tag bestehen. | Exakt die favorisierte Option 1 -- kein zweiter Login, keine separate Sitzung. |
| K4 | Nur sporadische/wenige Live-Marktdaten-Abonnements. | Geringes Risiko für das geteilte Marktdatenzeilen-Kontingent. |

**Wichtiger Korrekturpunkt zu "Read-Only API":** Die ursprüngliche
Empfehlung dieses Spikes, "Read-Only API" in TWS zu aktivieren (siehe
Frage 1), war **falsch für diese Umgebung** und wird hiermit
zurückgenommen. Read-Only API ist ein globaler TWS-Schalter für die
gesamte Instanz, nicht pro Client-ID -- er hätte auch TAT daran gehindert,
echte Optionsorder zu übermitteln. Der Nutzer hat bestätigt, dass
Read-Only API **nicht** aktiviert ist (aus genau diesem Grund: TAT braucht
Schreibzugriff). Das ist korrekt so.

**Der Analyzer braucht diesen TWS-weiten Schalter nicht als Schutz.** Die
Lesebeschränkung ist stattdessen strukturell im eigenen Code verankert:
`ibkr_client.IbAsyncClient` ruft ausschließlich lesende Methoden auf
(`isConnected`, `managedAccounts`, `serverVersion`, `connectionStats`,
`qualifyContracts`, `reqHistoricalData`) -- keine einzige
order-erzeugende Methode (`placeOrder` o. ä.) existiert im gesamten
Spike-Code. Das ist nachprüfbar (Code-Review), nicht nur behauptet, und
funktioniert unabhängig vom TWS-weiten Read-Only-Schalter.

**Ergebnis: Option 1 ist bestätigt.** Analyzer (`clientId=17`) und TAT
(`clientId=99`) koexistieren an derselben TWS-Instanz ohne Konflikt --
unterschiedliche Client-IDs, keine Änderung an TAT oder der bestehenden
TWS-Konfiguration, kein zweiter Login, kein Zugriff auf ordererzeugende
API-Methoden durch den Analyzer.

**Verbleibende Restunsicherheit (bewusst nicht weiter geprüft):** Ob TAT
tatsächlich erfolgreich Order übermitteln kann, wurde durch diesen Spike
nicht verifiziert und soll es auch nicht -- das reale Testen einer
echten Order-Übermittlung ist ausdrücklich nicht Aufgabe dieses
Analyzer-Spikes und würde ein unnötiges Risiko für die bestehende
Anwendung darstellen. Da Read-Only API nie aktiviert war, bestand für TAT
zu keinem Zeitpunkt ein Risiko durch diesen Spike.

## 5. Frage 3: Marktdatenauflösung / 195-Minuten-Aggregation -- BESTAETIGT

Implementiert und mit synthetischen Fixtures getestet (`timeframe.py`,
`steps/step_historical_bars.py`, 15 neue Tests): historische Bars via
`reqHistoricalData` (offizielle IBKR-API) laden und zu 195-Minuten-Kerzen
aggregieren, mit ausdrücklicher Kennzeichnung unvollständiger Kerzen
(`is_complete`) und expliziter Behandlung von Bars außerhalb der
Session (`bars_outside_session_count`) statt stillschweigender
Einbeziehung oder Auslassung.

Nur native Bar-Größen, die 195 Minuten ohne Rest teilen, sind zugelassen
(1/3/5/13/15/39/65 Minuten) -- alles andere wird mit klarer Fehlermeldung
abgelehnt statt eine schiefe Aggregation stillschweigend zu berechnen.

**Windows-Fund (live auf dem Zielserver reproduziert):** `zoneinfo` findet
unter Windows keine IANA-Zeitzonendaten, weil Windows (anders als macOS/
Linux) keine System-Tzdata mitbringt -- `ZoneInfo("America/New_York")`
scheiterte beim ersten Windows-Testlauf mit `ZoneInfoNotFoundError`. Fix:
`tzdata` als Abhängigkeit ergänzt (reines Python-Paket mit der
IANA-Datenbank, von der Python-Dokumentation für genau diesen Fall
empfohlen). Nach `pip install -e ".[dev]"` erneut getestet werden.

**Live bestätigt am 2026-08-11** gegen TWS (Symbol AAPL, `--duration "5 D"
--bar-size "15 mins"`):

```json
{
  "raw_bar_count": 107,
  "bars_outside_session_count": 0,
  "aggregated_candle_count": 9,
  "complete_candle_count": 8,
  "incomplete_candle_count": 1
}
```

- Vier abgeschlossene Handelstage (2026-08-05, -06, -07, -10) ergaben
  jeweils **exakt zwei vollständige 195-Minuten-Kerzen** mit `bar_count: 13`
  -- genau wie architektonisch erwartet (390 Minuten Sitzung / 195 = 2).
- `bars_outside_session_count: 0` -- IBKRs `useRTH=true` filtert
  Pre-/After-Market-Bars zuverlässig heraus, keine eigene Nacharbeit nötig.
- Der laufende Handelstag (2026-08-11, Abruf während der Sitzung) wurde
  korrekt als **unvollständig** erkannt (`bar_count: 3`,
  `is_complete: false`) -- bestätigt live, dass die "nur abgeschlossene
  Kerzen"-Regel (Doc 10) mit dieser Aggregation sauber durchsetzbar ist,
  ohne die laufende Kerze separat herausfiltern zu müssen.
- Rohbar-Anzahl stimmt exakt: 4 volle Tage × 26 Bars + 3 Bars vom
  laufenden Tag = 107, wie gemeldet.

**Damit offen für die nächste Frage (Frage 4):** wie tief die Historie
tatsächlich zurückreicht und wo Pacing-/Duration-Limits bei größeren
Anfragen (z. B. `--duration "1 Y"` oder länger) greifen -- das war
ursprünglich Teil dieser Frage, gehört inhaltlich aber eher zur
Abdeckungs-/Rate-Limit-Frage als zur reinen Mechanik, die hiermit
bestätigt ist.

## 6. Frage 4: Historische Abdeckung und Rate-Limits -- BESTAETIGT

Neuer Schritt `historical-coverage`: fragt dieselbe Bar-Größe mit
steigender Historientiefe ab (Standard: 1 M / 3 M / 6 M / 1 Y / 2 Y / 5 Y)
und meldet je Dauer, ob IBKR Daten liefert, wie viele Bars und welche
Zeitspanne tatsächlich zurückkommt -- oder eine konkrete Fehlermeldung,
falls ein Pacing- oder Duration-Limit greift. Bewusst **empirisch**
ermittelt statt aus der IBKR-Dokumentation übernommen, da sich Limits
zwischen Kontotypen/Abo-Stufen und API-Versionen unterscheiden können.
Zwischen den Anfragen liegt eine konfigurierbare Pause (Standard 2s), um
die dokumentierte Pacing-Grenze (max. 60 historische Anfragen je 10
Minuten) nicht zu strapazieren.

**Live bestätigt am 2026-08-11** gegen TWS (Symbol AAPL, 15-Minuten-Bars,
Standard-Dauern):

| Dauer | Status | Bars | Zeitspanne |
|---|---|---|---|
| 1 M | ok | 551 | 2026-07-13 -- 2026-08-11 |
| 3 M | ok | 1.565 | 2026-05-14 -- 2026-08-11 |
| 6 M | ok | 3.177 | 2026-02-13 -- 2026-08-11 |
| 1 Y | ok | 6.481 | 2025-08-12 -- 2026-08-11 |
| 2 Y | ok | 12.945 | 2024-08-12 -- 2026-08-11 |
| 5 Y | **inconclusive** | -- | -- |

Bar-Anzahl wächst über 1 M bis 2 Y plausibel und nahezu proportional zur
Dauer -- kein Hinweis auf stille Datenlücken oder Kappung in diesem
Bereich.

**Wichtiger Fund zu "5 Y":** Kein IBKR-Fehlercode, sondern ein
**Client-seitiger Timeout** in `ib_async`:

```
WARNING ib_async.ib: reqHistoricalData: Timeout for Stock(conId=265598,
symbol='AAPL', exchange='SMART', primaryExchange='NASDAQ', currency='USD',
localSymbol='AAPL', tradingClass='NMS')
```

`ib_async.IB.reqHistoricalData()` hat einen Default-Timeout von 60
Sekunden (Parameter `timeout: float = 60`, siehe `ibkr_client.py`) und
gibt bei Überschreitung -- statt eine Exception zu werfen -- eine leere
Bar-Liste zurück, die unser Code korrekterweise als `INCONCLUSIVE`
("keine Bars zurückgegeben") behandelt statt als Erfolg mit 0 Bars
misszuverstehen. Die Gesamt-Sitzungsdauer von 136s (bei ~10s
Pacing-Pausen für die übrigen fünf Anfragen) zeigt, dass die 5-Jahres-
Anfrage selbst deutlich länger als 60s gebraucht hätte, um die deutlich
größere Datenmenge (hochgerechnet ca. 32.000+ Bars) zu übertragen.

**Konsequenz:** Das bestätigt empirisch die bereits im Projektplan
vorgesehene Architektur (Sprint 2, "Historischer Backfill als
resumierbarer, rate-limit-fester Batch-Job") -- ein einzelner
5-Jahres-Request auf 15-Minuten-Basis ist mit Standardeinstellungen
**nicht praktikabel**. Der produktive Adapter muss den Backfill in
kleinere Zeitfenster zerlegen (z. B. 1-Jahres-Schritte über den
`endDateTime`-Parameter rückwärts wandern lassen, wie bei 1 Y/2 Y hier
bereits erfolgreich getestet), nicht als einzelne Großanfrage. Ein
größerer expliziter `timeout`-Wert könnte das Problem zusätzlich oder
alternativ entschärfen, wurde in diesem Spike aber nicht mehr getestet,
da die Chunking-Strategie ohnehin architektonisch vorgesehen und hier
bereits als funktionierender Weg (1 Y/2 Y) bestätigt ist.

## 7. Frage 5: Abgeschlossene vs. laufende Kerze -- BESTAETIGT

Keine eigene Live-Anfrage noetig -- die Antwort liegt bereits als Nebenergebnis
von Frage 3 vor und wird hier nur formal festgehalten, damit sie nicht als
offen missverstanden wird.

**Mechanik:** `timeframe.aggregate_to_195_minutes()` markiert eine
195-Minuten-Kerze genau dann als `is_complete: true`, wenn die Anzahl der
tatsaechlich gelieferten nativen Bars in ihrem Bucket der erwarteten Anzahl
entspricht (`195 / native_bar_minutes`, bei 15-Minuten-Bars also 13). Das ist
eine reine Zaehl-Regel ohne Sonderfall-Erkennung "ist das die aktuell
laufende Kerze" -- und genau das macht sie robust: Eine laufende Kerze hat
zwangslaeufig weniger Bars als eine abgeschlossene, unabhaengig davon, ob der
Abruf waehrend der Sitzung, kurz nach Sitzungsende oder Tage spaeter erfolgt.

**Live-Beleg (bereits in Frage 3 dokumentiert):** Beim Abruf am 2026-08-11
waehrend laufender Sitzung wurde der aktuelle Handelstag korrekt mit
`bar_count: 3` und `is_complete: false` erkannt, waehrend alle vier
zurueckliegenden, tatsaechlich abgeschlossenen Handelstage `bar_count: 13`
und `is_complete: true` zeigten -- keine manuelle Sonderbehandlung noetig,
keine Unschaerfe an der Grenze.

**Konsequenz fuer den produktiven Adapter:** Die "nur abgeschlossene
Kerzen"-Regel (Doc 10) laesst sich direkt aus `is_complete` ableiten, ohne
zusaetzlich die aktuelle Serverzeit mit dem Sitzungsende vergleichen zu
muessen. Restrisiko (siehe R9 im Projektplan): Bleibt die Datenlieferung
eines Anbieters kurzzeitig hinter der realen Zeit zurueck, koennte eine
tatsaechlich bereits geschlossene Kerze noch als unvollstaendig erscheinen --
das ist aber der sichere Fehlerfall (zu vorsichtig, nicht zu voreilig) und
deckt sich mit der ohnehin geplanten Karenzzeit/Polling-Logik aus Sprint 2.

## 8. Frage 6: Zusatzdaten (Earnings/Fundamentaldaten/Optionen, F9) -- BESTAETIGT

Neuer Schritt `supplementary-data` (`steps/step_supplementary_data.py`, 6
neue Tests) prueft drei unabhaengige Datentypen ueber die offizielle API,
jeweils ohne die anderen zu blockieren, falls einer scheitert:

- **Earnings-Kalender:** `reqFundamentalData(contract, 'CalendarReport')` --
  laut `ib_async`-Dokumentation (Verweis auf die offizielle IBKR-API,
  https://interactivebrokers.github.io/tws-api/fundamentals.html) liefert
  dieser Report-Typ den "Company's calendar", worunter u. a. Earnings-Termine
  fallen.
- **Analystenschaetzungen:** `reqFundamentalData(contract, 'RESC')`
  ("Analyst Estimates").
- **Optionsketten mit Greeks:** `reqSecDefOptParams()` liefert Verfallstermine
  und Strikes ohne Marktdaten; fuer eine Beispieloption (naechster
  Verfallstermin, Strike nahe der Mitte der gelisteten Strikes als grobe
  ATM-Naeherung) wird zusaetzlich ein Snapshot per `reqTickers()`
  angefragt und geprueft, ob IBKR modellierte Greeks (`modelGreeks`: Delta,
  Gamma, Vega, Theta, implizite Volatilitaet) mitliefert.

**Bewusst nicht angenommen, sondern offen als Ergebnis markiert:** Sowohl
Fundamentaldaten als auch Optionsmarktdaten mit Greeks haengen bei IBKR
typischerweise von **separaten, zusaetzlich zu abonnierenden**
Marktdaten-/Datenpaketen ab (Reuters Fundamentals bzw. Optionsmarktdaten-
Abo), unabhaengig vom bereits bestaetigten Aktienkurs-Zugriff aus Frage 1/3/4.
Der Schritt unterscheidet deshalb explizit `ok` (Daten kamen zurueck),
`inconclusive` (leere Antwort bzw. Snapshot ohne Greeks -- vermutlich
fehlende Berechtigung) und `failed` (technischer Fehler), statt eine leere
Antwort stillschweigend als "nicht verfuegbar" gleichzusetzen mit einem
echten Fehler.

**Live bestätigt am 2026-08-11** gegen TWS (Symbol AAPL):

```json
{
  "earnings_calendar": {"status": "ok", "xml_length": 2},
  "analyst_estimates": {"status": "ok", "xml_length": 325326},
  "option_chain": {
    "status": "ok", "chain_count": 20, "exchange": "CBOE",
    "expiration_count": 24, "strike_count": 127,
    "nearest_expiration": "20260812",
    "greeks_probe": {
      "status": "inconclusive",
      "reason": "Snapshot ohne modellierte Greeks -- vermutlich fehlende Optionsmarktdaten-Berechtigung"
    }
  }
}
```

**Live-Fund und sofort behobener Fehler im eigenen Code:** `CalendarReport`
kam technisch fehlerfrei zurueck, aber mit `xml_length: 2` -- eine
inhaltslose Whitespace-Antwort (`"\r\n"`), keine echten Kalenderdaten. Die
urspruengliche Prueflogik (`if not xml`) haette das faelschlich als `ok`
durchgehen lassen, weil der String technisch nicht leer war. Sofort korrigiert
auf `if not xml.strip()`, mit Regressionstest (`test_whitespace_only_antwort_
gilt_als_inconclusive_nicht_ok`). Damit gilt fuer diesen Report-Typ jetzt
korrekt: **`inconclusive`, keine nutzbaren Earnings-Termine ueber
`CalendarReport` fuer diesen Kontrakt.**

**Ergebnis je Datentyp:**

| Datentyp | Ergebnis | Befund |
|---|---|---|
| Earnings-Kalender (`CalendarReport`) | **nicht verfuegbar** | Inhaltslose Antwort (nach Korrektur `inconclusive`) -- dieser Report-Typ liefert fuer den Account/Kontrakt keine brauchbaren Earnings-Termine |
| Analystenschaetzungen (`RESC`) | **verfuegbar** | 325.326 Zeichen XML -- substantieller, echter Datenumfang |
| Optionsketten-Struktur (Verfallstermine/Strikes) | **verfuegbar** | 20 Ketten, 24 Verfallstermine, 127 Strikes fuer AAPL/CBOE -- keine zusaetzliche Berechtigung noetig |
| Optionsdaten mit Greeks (Delta/Gamma/Vega/Theta/IV) | **verfuegbar (nach Abo-Aktivierung)** | Zunaechst explizit abgelehnt (`Error 10091: zusätzliches Abonnement erforderlich`); nach Aktivierung des Optionsmarktdaten-Abos durch den Nutzer liefert derselbe Testfall echte Greeks (siehe Nachtrag unten) |

Nebenbefund im selben Log: `Error 10276: Der Newsfeed ist nicht zulässig`
(reqId 4) -- ein Newsfeed-bezogener Tick, den `reqTickers()` fuer
Optionskontrakte offenbar standardmaessig mitanfragt. Fuer dieses Ergebnis
nicht relevant (blockiert weder die Optionsketten-Struktur noch die
uebrigen Anfragen), aber dokumentiert, um ihn nicht spaeter faelschlich als
neuen, unbekannten Fehler zu behandeln.

**Nachtrag, erneuter Live-Test am 2026-08-11 (nach Aktivierung des
Optionsmarktdaten-Abos durch den Nutzer):**

```json
"greeks_probe": {
  "status": "ok",
  "implied_vol": 0.3535,
  "delta": 0.9771,
  "gamma": 0.0096,
  "vega": 0.0107,
  "theta": -0.0830
}
```

Modellierte Greeks kommen jetzt zurueck -- die vormalige Ablehnung (Fehler
10091) war tatsaechlich eine reine Abo-Frage, kein technisches Hindernis.
Das im selben Testlauf weiterhin gezeigte `earnings_calendar: {"status":
"ok", "xml_length": 2}` stammt von einem Serverstand **vor** dem
Code-Fix aus diesem Bericht (`if not xml.strip()`) -- der zugrunde liegende
Rohbefund (inhaltslose Zwei-Zeichen-Antwort) ist unveraendert und bleibt
wie oben beschrieben `inconclusive`; nach einem erneuten `git pull` zeigt
derselbe Testlauf den korrigierten Status.

Delta 0,977 ist fuer die gewaehlte Beispieloption plausibel, aber kein
realistischer ATM-Wert -- die grobe Strike-Naeherung (Median der
gelisteten Strikes) waehlte hier zufaellig eine deutlich im Geld liegende
Option. Fuer diesen reinen Machbarkeitsnachweis (kommen ueberhaupt Greeks
zurueck) unerheblich; ein produktiver Adapter wuerde den Strike anhand des
tatsaechlichen Kurses waehlen.

**Konsequenz fuer F9 (Entscheidung des Projektinhabers, 2026-08-11):**
IBKR deckt **Analystenschaetzungen**, die **strukturellen
Optionsketten-Daten** und -- nach Aktivierung des zusaetzlichen
Optionsmarktdaten-Abos -- auch **Options-Greeks** ab. Fuer
**Earnings-Termine** liefert `CalendarReport` keine brauchbaren Daten;
der Projektinhaber hat entschieden, dafuer eine **separate Datenquelle**
einzuplanen statt weitere IBKR-Report-Typen zu untersuchen. F9 gilt damit
fuer Analystenschaetzungen, Optionsketten und Greeks durch IBKR als
beantwortet; fuer Earnings-Termine bleibt ein eigenes ADR (Anbieterwahl)
noetig.

## 9. Frage 7: Mehrsymbol-Durchlauf (Referenzvergleich) -- BESTAETIGT

Neuer Schritt `multi-symbol` (`steps/step_multi_symbol.py`, 5 neue Tests):
baut **eine** TWS-Verbindung auf und durchlaeuft dann sequenziell eine Liste
von Symbolen (Standard: dieselben 10 Referenzaktien wie beim
Gate-G2-Mehrsymbol-Vergleich), pro Symbol Kontraktaufloesung + historische
Bars + 195-Minuten-Aggregation. Ein fehlschlagendes Symbol wird einzeln mit
Fehlermeldung vermerkt und bricht den Durchlauf der uebrigen Symbole nicht
ab -- Laufzeit wird sowohl je Symbol als auch fuer den Gesamtdurchlauf
gemessen.

**Live bestätigt am 2026-08-11** gegen TWS (10 Referenzaktien: AAPL, MSFT,
AMZN, GOOGL, META, NVDA, TSLA, JPM, XOM, UNH; `--duration "5 D" --bar-size
"15 mins"`):

- **10 von 10 Symbolen erfolgreich**, keine Fehler, keine `inconclusive`
  -- ueber eine einzige TWS-Verbindung, wie es ein produktiver
  Watchlist-Lauf vorsaehe.
- **Gesamtlaufzeit 8,0 s** fuer 10 Symbole (~0,8 s je Symbol im Mittel) --
  fuer eine taeglich einmalige Watchlist-Verarbeitung mit deutlich mehr als
  10 Symbolen unproblematisch hochskalierbar innerhalb der dokumentierten
  Pacing-Grenzen (siehe Frage 4).
- **Konsistente Kerzenzahlen ueber alle 10 Symbole:** jedes Symbol lieferte
  exakt `raw_bar_count: 115` und `complete_candle_count: 8` -- bei
  laufender Sitzung (Abruf 12:26 ET) plausibel: vier vollstaendige
  Handelstage x 2 Kerzen = 8 vollstaendige Kerzen, plus der noch laufende
  Handelstag als neunte, unvollstaendige Kerze. Keine Ausreisser zwischen
  unterschiedlichen Branchen/Börsenplätzen (Tech, Finanzen, Energie,
  Gesundheitswesen in der Liste vertreten).

**Konsequenz:** Die Mechanik aus Frage 1/3/5 ist nicht auf ein einzelnes
Testsymbol (AAPL) beschraenkt, sondern verhaelt sich ueber eine
repraesentative Watchlist hinweg gleichfoermig und schnell genug fuer den
produktiven Tageslauf.

## 10. Technische Risiken

Stand nach Abschluss von Phase B -- jeder Punkt ist entweder durch einen
echten Live-Testlauf bestaetigt/entkraeftet oder bewusst offen geblieben.

- **R2 (unbeaufsichtigter Betrieb) -- bewusst nicht geloest, sondern
  operativ umgangen.** Wie bei TradingView (Gate G2/G3) ist ein
  vollautomatischer Wiederanlauf nach einem echten Windows-Neustart nicht
  belegt. Anders als urspruenglich in ADR 0013 angenommen, loest IB
  Gateway + IBC dieses Problem nicht grundsaetzlich, sondern nur die
  IBKR-Login-Automatisierung *innerhalb* einer bereits angemeldeten
  Windows-Sitzung (Frage 2) -- die Windows-Session-0-Isolation nach einem
  Host-Neustart bleibt davon unberuehrt. Der Projektinhaber hat sich
  deshalb fuer denselben manuellen Montags-Neustart entschieden, den er
  bereits fuer die bestehende Anwendung TAT praktiziert. Windows-Autologon
  bleibt eine eigenstaendige, weiterhin offene Entscheidung.
- **`ib_async`-Client-Timeout ist kein IBKR-Limit, aber technisch
  wirksam.** Der Default-Timeout von 60 Sekunden fuehrt bei sehr grossen
  Historienabfragen (5 Jahre auf 15-Minuten-Basis) zu einer leeren
  Ruecklieferung statt eines Fehlers (Frage 4) -- ohne den eigenen
  `INCONCLUSIVE`-Status waere das leicht als "0 Bars vorhanden"
  misszuverstehen. Ein produktiver Adapter muss die bereits vorgesehene
  Chunking-Strategie (kleinere Zeitfenster statt Grossanfragen) umsetzen,
  nicht nur den Timeout erhoehen.
- **Fundamentaldaten-Abos sind pro Report-Typ getrennt zu pruefen, nicht
  pauschal anzunehmen.** `RESC` (Analystenschaetzungen) und `CalendarReport`
  (Earnings-Kalender) liefen technisch identisch ab, aber nur einer davon
  lieferte brauchbare Daten (Frage 6) -- eine pauschale Annahme "Fundamental-
  daten sind verfuegbar" waere falsch gewesen.
- **Grobe ATM-Naeherung bei Optionskontrakten ist nur fuer den
  Machbarkeitsnachweis geeignet.** Der Greeks-Test (Frage 6) waehlte den
  Median der gelisteten Strikes als Naeherung und traf dabei zufaellig eine
  deutlich im Geld liegende Option (Delta 0,98). Ein produktiver Adapter
  muss den Strike anhand des tatsaechlichen Kurses waehlen, nicht anhand
  der Position in der sortierten Strike-Liste.
- **Drei echte, live gefundene und noch waehrend der Validierung behobene
  Bugs** (siehe jeweilige Abschnitte): Python-3.14/`eventkit`-
  Event-Loop-Inkompatibilitaet (Frage 1), ungefiltertes Logging von
  Konto-/Positionsdaten durch `ib_async.wrapper` (Frage 1,
  "Sicherheitsfund"), und eine faelschlich als `ok` gewertete, tatsaechlich
  inhaltslose Whitespace-Antwort bei Fundamentaldaten (Frage 6). Keiner
  dieser Funde war durch Lektuere der `ib_async`-Dokumentation vorhersehbar
  -- alle drei wurden erst durch echte Live-Tests sichtbar, konsistent mit
  der Erfahrung aus dem TradingView-Spike.
- **Windows-spezifischer `tzdata`-Fund** (Frage 3): Ohne das zusaetzliche
  `tzdata`-Paket schlaegt jede `ZoneInfo("America/New_York")`-Aufloesung
  unter Windows fehl, waehrend macOS/Linux das stillschweigend uebersteht --
  ein Fund, der ausschliesslich durch den Test auf dem tatsaechlichen
  Windows-Zielserver moeglich war, nicht durch lokale Entwicklung.
- **Restrisiko aus der Vorpruefung unveraendert bestehen:** Die in ADR 0013
  offen gelassenen Punkte (IBKR-Rechtstraegerschaft des Kontos, ggf.
  boersenspezifische Zusatzvereinbarungen) sind technischer Natur nicht
  pruefbar und bleiben eine eigenstaendige, vom Projektinhaber bewusst
  mitgetragene Restunsicherheit (Abschnitt 11).

## 11. Bekannte Lizenz-/Nutzungsfragen

Siehe [ADR 0013](../../docs/adr/0013-interactive-brokers-kandidat-vorschlag.md):
Vorprüfung mit GO abgeschlossen (Market Data API Supplement erlaubt
"perform analytics [...] exclusively in connection with Subscriber's
brokerage account(s)" wörtlich). Offene Restpunkte aus der Vorprüfung
(konkrete IBKR-Rechtsträgerschaft, ggf. börsenspezifische
Zusatzvereinbarungen) sind dort dokumentiert, nicht Gegenstand dieses
technischen Berichts.

## 12. Go-/No-Go-Empfehlung

**GO_WITH_LIMITATIONS.**

Diese Empfehlung bezieht sich ausschließlich auf die **technische
Stabilität** (Dimension 1). Die **lizenz-/nutzungsrechtliche Zulässigkeit**
(Dimension 2) ist -- anders als beim TradingView-Spike -- bereits vor
Spike-Beginn geprüft und vom Projektinhaber mit GO entschieden worden
(Abschnitt 11, ADR 0013); sie wird hier nicht erneut bewertet, die dort
offen gelassenen Restpunkte bleiben unverändert bestehen.

### Was für ein GO spricht

- **Alle acht Fragen (die ursprünglichen sieben plus die zusätzliche
  Koexistenzfrage) sind live gegen die echte TWS des Nutzers beantwortet**,
  nicht nur synthetisch: Verbindungsaufbau (Frage 1), 195-Minuten-
  Aggregation mit korrekter Unterscheidung abgeschlossener/laufender Kerzen
  (Frage 3/5), historische Abdeckung bis 2 Jahre ohne Einschränkung
  (Frage 4), Mehrsymbol-Stabilität über 10 Referenzaktien (Frage 7),
  gefahrlose Koexistenz mit der produktiv laufenden Anwendung TAT
  (Frage 8) und -- nach Abo-Aktivierung -- Analystenschätzungen sowie
  Optionsketten mit Greeks (Frage 6).
- **Die offizielle, dokumentierte API ist deutlich robuster als der
  TradingView-CDP-Ansatz:** keine geratenen DOM-Selektoren oder internen
  Objektpfade, jede verwendete Methode wurde live an der installierten
  `ib_async`-Version verifiziert statt angenommen. Fehlerursachen kommen
  von IBKR meist explizit benannt zurück (z. B. Fehler 10091 für die
  fehlende Optionsmarktdaten-Berechtigung) statt als stille Falschwerte.
- **Drei echte Bugs wurden durch systematisches Live-Testen gefunden und
  noch während der Validierung behoben**, bevor sie in eine
  Produktivintegration hätten einfließen können (Abschnitt 10) -- derselbe
  Prozess, der beim TradingView-Spike bereits mehrfach wirksam war.
- **Betriebliche Kopplung an eine bereits produktiv laufende Anwendung
  (TAT) ist sauber gelöst**, ohne jede Änderung an TAT oder Risiko für
  deren echte Order-Übermittlung (Frage 8).

### Was die Einschränkungen sind (das "WITH_LIMITATIONS")

1. **R2 -- unbeaufsichtigter Betrieb nach einem echten Windows-Neustart ist
   nicht gelöst, sondern bewusst durch ein manuelles Betriebsmodell
   ersetzt** (Frage 2). Eine Produktivintegration erbt damit dieselbe
   Nichtverfügbarkeit zwischen sonntäglichem Neustart und manuellem
   Montagsstart, die der Projektinhaber für seine bestehende Anwendung
   bereits akzeptiert. Windows-Autologon bleibt eine separate, weiterhin
   offene Entscheidung -- unverändert gegenüber Gate G3/Strang B des
   TradingView-Spikes.
2. **Earnings-Termine sind über IBKR nicht abgedeckt** (Frage 6) -- F9
   braucht dafür weiterhin ein eigenes ADR zur Anbieterwahl.
3. **Historischer Backfill über 15-Minuten-Bars für 5 Jahre benötigt
   Chunking**, nicht eine einzelne Großanfrage (Frage 4) -- bereits im
   Projektplan vorgesehen, hier empirisch bestätigt statt nur angenommen.
4. **Fundamentaldaten-Verfügbarkeit ist pro Report-Typ zu prüfen**, nicht
   pauschal anzunehmen (Frage 6) -- `RESC` funktioniert, `CalendarReport`
   nicht, für denselben Kontrakt und dieselbe API-Anfrage-Art.
5. **Die in ADR 0013 offen gelassenen Restpunkte der Vorprüfung**
   (IBKR-Rechtsträgerschaft, börsenspezifische Zusatzvereinbarungen) sind
   technisch nicht überprüfbar und bleiben unverändert bestehen.

### Empfehlung für die Produktarchitektur

Unverändert zum bestehenden Projektplan: `MarketDataProvider` bleibt ein
Protokoll im Domain Layer; ein `IbkrMarketDataProvider` wäre ein
austauschbarer Infrastructure-Adapter, der:

- die tiefer liegende `Client`-Klasse von `ib_async` direkt anspricht statt
  der hochleveligen `IB`-Klasse, um den automatischen Konto-/Positions-Sync
  gar nicht erst auszulösen (echte Datenminimierung statt nur
  Log-Unterdrückung, Abschnitt 3, "Sicherheitsfund"),
- historischen Backfill ausschließlich als resumierbaren, in Zeitfenster
  zerlegten Batch-Job umsetzt (Abschnitt 6/10, nie als einzelne
  Großanfrage),
- die Client-ID über Konfiguration bezieht und sich dabei um Kollisionen
  mit anderen Anwendungen an derselben TWS-Instanz kümmert, statt sie fest
  zu verdrahten (Abschnitt "4a"),
- Optionsstrike-Auswahl anhand des tatsächlichen Kurses trifft, nicht
  anhand der Position in einer sortierten Strike-Liste (Abschnitt 8/10),
- **erst nach ausdrücklicher Freigabe eines eigenen Gates/ADR für die
  produktive Integration** implementiert wird (Schritt 4 aus ADR 0013,
  unverändert weiterhin gesperrt) -- diese Empfehlung ist keine Freigabe
  für Produktivcode.
