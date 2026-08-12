# Gate G2 -- TradingView Desktop/CDP Spike: Bericht

**Status: PHASE B ABGESCHLOSSEN -- EMPFEHLUNG: GO_WITH_LIMITATIONS**
(Details und Einschraenkungen in Abschnitt 18)

Dieser Bericht wurde in zwei Phasen gefuellt. Phase A deckte ausschliesslich
die Entwicklung und den technischen Nachweis auf macOS ab. Phase B
(Windows-Zielserver) ist inzwischen abgeschlossen, bis auf zwei bewusst
zurueckgestellte Punkte (Abschnitt 18). Ein auf macOS erfolgreicher Test war
**kein Nachweis fuer die Windows-Produktivumgebung** -- das war der Grund,
warum Phase B ueberhaupt noetig war, und warum mehrere in Phase A fuer
ausreichend gehaltene Loesungen (siehe Abschnitte 10 und 13) sich bei
echten Windows-Testlaeufen als unzureichend erwiesen und ueberarbeitet
werden mussten.

## 1. Executive Summary

Das Spike-Harness (`tvcdp`) ist vollstaendig implementiert, automatisiert
getestet (82 Unit-/Integrationstests, ruff und mypy --strict ohne Befund)
und gegen ein echtes Chrome-DevTools-Protocol-Ziel auf macOS lauffaehig
verifiziert -- alle elf Testschritte melden auf Anhieb `PASSED` gegen eine
generische Chromium-Instanz. Dabei wurden zwei echte Bugs gefunden und
behoben (Details unten).

**Was das belegt:** Die CDP-Kernmechanik (Zielerkennung, WebSocket-
Verbindung, `Runtime.evaluate`, Fehlerbehandlung, Performance-Messung,
Redaction) funktioniert wie vorgesehen -- unabhaengig vom Betriebssystem,
da das Protokoll bei jeder Chromium-basierten Anwendung identisch ist.

**Was das nicht belegt:** Ob TradingView Desktop selbst mit aktiviertem
CDP startet, ob eine bestehende Sitzung nutzbar ist, ob Watchlists/Layout/
Indikatoren tatsaechlich auslesbar sind, und ob das Ganze auf dem
Windows-Zielserver unbeaufsichtigt funktioniert. Das sind die eigentlichen
Kernfragen des Spikes (Abschnitt A-I der Aufgabenstellung) -- sie sind
technisch nur mit echtem Zugriff auf TradingView Desktop beantwortbar und
folgen in Phase B.

**Phase B laeuft.** Auf dem Windows-Zielserver (Microsoft-Store-Installation
von TradingView Desktop) bereits bestaetigt:
- **A.1/A.2** -- CDP-Debug-Port startbar und erreichbar, allerdings nur ueber
  `Invoke-CommandInDesktopPackage`, da ein direkter Prozessstart an den
  MSIX-Schutzmechanismen von Windows scheitert (Abschnitt 3a).
- **C.9/C.10** -- Chartlayout eindeutig erkannt und gegen einen
  Erwartungswert verifiziert, ueber die stabile Layout-Kennung in der
  Browser-URL (Abschnitt 6).
- **D.12** -- 195-Minuten-Timeframe zuverlaessig erkannt, ueber
  `aria-checked` einer ARIA-Radiogroup statt sichtbaren Text (Abschnitt 7).
- **A.3** -- bestehende Sitzung nutzbar ueber `ChartApiInstance.connected()`,
  ohne je Zugangsdaten auszulesen (Abschnitt 3b).
- **D.13/D.14, E.15** -- Datenquelle und konkrete JavaScript-Sonden fuer
  Kerzenschluss-Zeitpunkt und alle vier Indikatoren (RSI, RSI-MA, EMA5,
  EMA20) gefunden, manuell in der Browser-Konsole verifiziert, und
  inzwischen zusaetzlich ueber das Harness selbst bestaetigt (`tvcdp run-all`
  meldet `closed_candle_detection: PASSED` und `indicators: PASSED`) --
  ueber die interne Chart-API (`_exposed_chartWidgetCollection` /
  `_studiesWV`), keine geratenen DOM-Selektoren (Abschnitte 7, 8).

Sieben echte Harness-Luecken wurden dabei gefunden und noch waehrend der
laufenden Validierung behoben (Zielerkennungs-Mehrdeutigkeit, fehlende
Layout-Verifikations-Verdrahtung, ungefangener `httpx.ConnectTimeout` im
Fehlerfall-Schritt, sowie -- ueber drei Iterationen, jede per echtem
10-Symbol-Testlauf auf dem Windows-Zielserver gefunden -- eine
Bereitschaftspruefung nach Symbolwechsel vor dem Lesen von Werten, siehe
Abschnitt 10).
**Ein vollstaendiger `tvcdp run-all`-Lauf auf dem Windows Server bestaetigt
inzwischen alle neun dafuer automatisierbaren Schritte (`environment`,
`cdp_reachability`, `target_discovery`, `session_check`, `layout_detection`,
`timeframe_195`, `closed_candle_detection`, `indicators`,
`error_case_detection`) mit `PASSED`.** **G (Mehrsymbol-Durchlauf) und F
(Referenzvergleich) sind bestaetigt:** nach drei Fix-Iterationen, jede durch
einen echten 10-Symbol-Testlauf auf dem Windows-Zielserver aufgedeckt,
lieferte der vierte Lauf alle 10 Werte korrekt -- vom Nutzer vollstaendig
gegen TradingView geprueft (Abschnitte 9 und 10), die Abnahmebedingung
"Uebereinstimmung bei ≥ 10 Referenzaktien" ist damit erfuellt. Fuer B
(Watchlist) wurde eine dokumentierte Einschraenkung festgestellt (kein
Live-Lesezugriff ueber die untersuchten internen APIs, Abschnitt 5). Von H
(Neustart-/RDP-/Autostart-Tests) sind fuenf von sechs Tests bestaetigt
(TradingView-Neustart, Prozessabsturz, gesperrter Bildschirm,
RDP-Disconnect, Netzwerkunterbrechung -- durchweg robust, TradingView laeuft
in allen fuenf Faellen unbeeintraechtigt weiter, Abschnitte 11-12).
**Windows-Neustart mit Autostart (unbeaufsichtigter Betrieb ohne Anmeldung)
wurde bewusst zurueckgestellt** -- die technische Anforderung dafuer ist
geklaert (Windows-Autologon noetig, da TradingView als GUI-Anwendung nicht
in Session 0 laufen kann), die dafuer noetige Credential-Handling-
Entscheidung trifft der Nutzer aber separat, ausserhalb dieses Spikes.
**Projektrisiko R2 bleibt damit ein bekanntes, ungeloestes Risiko**
(Abschnitt 12). **I (restliche manuelle Fehlerfaelle) ist abgeschlossen:**
"Symbol nicht geladen", "falscher Timeframe" und "Indikator fehlt" wurden
gezielt provoziert und alle drei fangen den Fehler laut ab, nie mit einem
stillen Fehlwert; die uebrigen Faelle waren bereits durch fruehere
Abschnitte belegt (Abschnitt 13). Einzige bewusst offen gelassene
Feinheit: ein Test exakt am echten 195-Minuten-Kerzenschluss (statt nur
synthetisch/statisch).

**Empfehlung: GO_WITH_LIMITATIONS.** Siehe Abschnitt 18 fuer die vollstaendige
Begruendung und die konkreten Einschraenkungen.

## 2. Testumgebung

### Phase A (macOS, abgeschlossen)

| Feld | Wert |
|---|---|
| Betriebssystem | macOS (Darwin, siehe `results/*/environment.json` je Lauf) |
| Ziel | Google Chrome mit `--remote-debugging-port`, eine `data:`-URL mit bekanntem Titel |
| Zweck | Nachweis der CDP-Kernmechanik, **nicht** TradingView-spezifisch |

### Phase B (Windows, laufend)

| Feld | Wert |
|---|---|
| Betriebssystem | Windows Server (Edition/Build noch ueber `tvcdp environment` zu erfassen) |
| Installationsweg | Microsoft Store / MSIX-Paket -- laut Nutzer der einzige auf der TradingView-Webseite angebotene Windows-Download zum Testzeitpunkt |
| Paket | `TradingView.Desktop_3.3.0.7992_x64__n534cwy3pjxzj` |

**Wichtige Umgebungsbesonderheit (dokumentierenswertes Ergebnis, kein reines
Konfigurationsdetail):** Direkter Prozessstart (`Start-Process` bzw. der
PowerShell-Call-Operator `&`) gegen die `.exe` unter
`C:\Program Files\WindowsApps\...` scheiterte mit "Zugriff verweigert" --
dieser Pfad ist durch Windows-ACLs geschuetzt und laesst sich nicht direkt
ausfuehren, unabhaengig von Administratorrechten. Funktioniert hat
`Invoke-CommandInDesktopPackage` (PowerShell-`Appx`-Modul), das die App
ueber ihre Paket-Identitaet mit eigenen Kommandozeilenargumenten startet.
Dass dieser Cmdlet auf einer Windows-**Server**-Edition ueberhaupt verfuegbar
war und funktionierte, war nicht selbstverstaendlich (Server-Editionen
unterstuetzen die Store-/AppX-Infrastruktur grundsaetzlich nicht oder nur
eingeschraenkt) -- fuer die Produktivarchitektur bedeutet das: **dieser
Startmechanismus ist selbst ein Bestandteil der Loesung**, kein einmaliger
Workaround, sofern der MSIX-Installationsweg beibehalten wird.

## 3. Verwendete TradingView-Version

TradingView Desktop 3.3.0 (Build 7992), siehe Paketname oben. Exakte
In-App-Versionsnummer noch manuell zu bestaetigen.

## 3a. Frage A.1/A.2: CDP-Start und Erreichbarkeit -- BESTAETIGT

**Ergebnis: Ja, reproduzierbar startbar, Debug-Port erreichbar.**

Beleg: TradingView Desktop selbst gibt beim Start mit
`--remote-debugging-port=9222` (uebergeben via
`Invoke-CommandInDesktopPackage -Args "--remote-debugging-port=9222"`) die
Zeile

```
DevTools listening on ws://127.0.0.1:9222/devtools/browser/d8f26240-01b0-4bf9-8bd2-1abdaa0098dd
```

aus -- das ist die native Chromium/Electron-Bestaetigung, dass der Port
gebunden wurde, nicht nur eine Annahme des Harness. Der Prozess startete
sichtbar (TradingView Desktop oeffnete sich parallel).

**Zusaetzlich bestaetigt:** `Invoke-RestMethod http://127.0.0.1:9222/json/list`
liefert eine Zielliste mit 10 Eintraegen -- genau der Endpunkt, den
`tvcdp reachability`/`target-discovery` tatsaechlich auswerten. Der
eigentliche Chart ist eindeutig darunter:

```
title: "Aktien, Indizes, Futures, Devisen und Bitcoin-Charts auf TradingView"
type:  page
url:   https://de.tradingview.com/chart/LAYOUT-A/
```

Die uebrigen neun Eintraege sind interne Electron-Renderer-Prozesse der
App selbst (Titelleiste, Tooltip-Fenster, Drag-Service, ein Web-Worker
usw.), erkennbar an `file:///.../TradingView.Desktop_.../resources/...`-
URLs oder leeren Titel-/URL-Feldern.

**Gefundene Schwachstelle in der Zielerkennung (behoben, siehe unten):**
Der Standard-Musterwert `TVCDP_TARGET_TITLE_PATTERN=TradingView` matcht
nicht nur den Chart, sondern *zusaetzlich* mehrere der internen
Renderer-Seiten -- ihre `file://`-URLs enthalten den Installationsordner-
namen `TradingView.Desktop_...`, der zufaellig ebenfalls das Wort
"TradingView" enthaelt. `step_target_discovery.run()` waehlt bislang
schlicht den ersten Treffer (`matches[0]`); in diesem Lauf war das
zufaellig der Chart, das ist aber nicht garantiert stabil ueber
Neustarts hinweg (Reihenfolge der von `/json/list` gemeldeten Ziele ist
nicht spezifiziert). **Empfehlung fuer diese Umgebung:**
`TVCDP_TARGET_TITLE_PATTERN=tradingview.com` setzen -- das trifft nur die
echte Chart-Seite, nicht die lokalen `file://`-Installationspfade.

**Interessanter Nebenfund fuer Abschnitt C (Chartlayout):** Die Chart-URL
enthaelt eine stabile Layout-Kennung (`LAYOUT-A`). `location.pathname`
bzw. `location.href`, ausgewertet in der Chart-Seite, waere damit ein
sehr naheliegender erster Kandidat fuer `TVCDP_PROBE_LAYOUT_NAME_JS` --
vermutlich stabiler als ein DOM-Text, sofern TradingView dieselbe
Layout-ID beim erneuten Oeffnen desselben gespeicherten Charts wieder
verwendet (das ist Teil dessen, was C.10 noch zu verifizieren hat).

**Noch offen (Wiederholbarkeit, Frage A.2 im engeren Sinne):**
- Bleibt der Port nach einem TradingView-Neustart (ohne Windows-Neustart)
  gleichermassen erreichbar? (Abschnitt A.4 der Aufgabenstellung)
- Bleibt die Ziel-Erkennung mit dem geschaerften Muster
  (`tradingview.com`) stabil ueber mehrere Neustarts?

## 3b. Frage A.3: Bestehende Sitzung nutzbar -- BESTAETIGT

**Ergebnis: Ja, ohne jemals Zugangsdaten auszulesen.**

Die interne Chart-API (`window.ChartApiInstance`, ein Objekt mit u. a.
`sessionid`, `_authTokenDfd`, `_authTokenManager` -- **diese Felder wurden
zu keinem Zeitpunkt gelesen oder geloggt**, siehe Sicherheitshinweis unten)
bietet eine oeffentliche Methode `connected()`, die einen reinen
Wahrheitswert liefert:

```javascript
window.ChartApiInstance.connected()
```

Ergebnis: `true`. Das beantwortet A.3 vollstaendig, ohne die
Sicherheitsgrenze des Harness zu verletzen (kein Zugriff auf `sessionid`
oder Token-Inhalte).

Zusaetzlich ueber das Harness selbst bestaetigt: `tvcdp run-all` meldet
`session_check: PASSED` mit `TVCDP_PROBE_SESSION_AUTHENTICATED_JS` gesetzt
auf den obigen Ausdruck (Ergebnis in der Ausgabe redigiert, siehe
`redaction.py`).

**Sicherheitshinweis (kein Vorfall, aber dokumentiert, weil sicherheits-
relevant):** Bei der strukturellen Erkundung von `Object.keys(window.ChartApiInstance)`
tauchte -- wie fuer eine Chart-API mit Server-Authentifizierung zu erwarten --
ein Feld namens `sessionid` sowie mehrere `_authToken*`-Felder auf. Es wurde
ausschliesslich der **Schluesselname** abgefragt (`Object.keys()`), nie der
zugehoerige **Wert** -- exakt die im Harness-Design vorgesehene Diszipin
(siehe REPORT.md Abschnitt 17). Kein Zugangsdaten-Wert wurde zu irgendeinem
Zeitpunkt in dieser Session, in Logs oder in Ergebnisdateien sichtbar.

## 4. Verwendete CDP-Methode

`Runtime.evaluate` ueber eine direkte WebSocket-Verbindung zum von
`/json/list` gemeldeten Debug-Ziel. Keine Fremdbibliothek (siehe
`src/tvcdp/cdp_client.py` fuer die Begruendung). Fuer TradingView-spezifische
Werte (Watchlist, Layout, Timeframe, Indikatoren) sind ausschliesslich
JavaScript-Ausdruecke ueber Umgebungsvariablen konfigurierbar
(`TVCDP_PROBE_*`) -- der Code enthaelt bewusst keine geratenen
DOM-Selektoren oder internen TradingView-Objektpfade (siehe
`src/tvcdp/probe_config.py`).

## 5. Watchlist-Ergebnisse

**B -- NICHT ERREICHBAR ueber die untersuchten internen APIs (dokumentierte
Einschraenkung, kein Harness-Fehler).**

| Umgebung | Ergebnis |
|---|---|
| Auf macOS nachgewiesen | Mechanik (Sonde auswerten, Struktur validieren, mehrere Listen unterscheiden, Zeitmessung) -- mit einer synthetischen Testsonde, nicht mit echten TradingView-Daten |
| Auf Windows nachgewiesen | **Kein Live-Lesezugriff gefunden.** `window.TV_WATCHLISTS_URL` ist nur eine Konstante (ein API-Endpunkt-String), keine geladenen Daten. `window.TradingViewApi.watchlist()` existiert als Methode, wirft aber in diesem Kontext `Error: not implemented`. `window.widgetbar._models` (14 Eintraege) enthaelt keine Eintraege mit watchlist-/symbolbezogenen Eigenschaften. Kein `window.watchlist` oder vergleichbares globales Objekt. |
| Fehlgeschlagen | -- (kein Fehler des Harness; die untersuchte interne API liefert selbst explizit "nicht implementiert") |

**Einordnung:** Dies ist keine Sackgasse fuer den Spike als Ganzes. Fragen
D-I (Layout, Timeframe, Kerzenschluss, Indikatoren, Mehrsymbol-Durchlauf,
Performance) haengen nicht von einer automatisiert ausgelesenen Watchlist
ab -- `SpikeConfig.watchlist_probe_names` erlaubt, eine feste Symbolliste
manuell zu konfigurieren (siehe Abschnitt 10). Eine produktive Integration
muesste fuer den Watchlist-Zugriff entweder einen anderen, noch nicht
gefundenen internen Pfad identifizieren oder auf einen expliziten
Watchlist-Export durch den Nutzer ausweichen (Fallback-Vergleich unten).

## 6. Chartlayout-Ergebnisse

**C.9/C.10 -- BESTAETIGT.**

| Umgebung | Ergebnis |
|---|---|
| Auf macOS nachgewiesen | Mechanik (Erkennung + Verifikation gegen Erwartungswert) -- mit `document.title` als Platzhaltersonde |
| Auf Windows nachgewiesen | **Ja.** Sonde `location.pathname` liefert eine stabile, von TradingView selbst vergebene Layout-Kennung in der URL (z. B. `/chart/LAYOUT-B/`). Mit `TVCDP_EXPECTED_LAYOUT` gegen denselben Wert verifiziert: `verified: true` (bestaetigt ueber `tvcdp run-all`). Damit ist sowohl die Erkennung (C.9) als auch die Bestaetigung, dass wirklich das gewuenschte Layout aktiv ist und nicht nur irgendein Chart (C.10), belegt. Ein frueherer Testlauf mit einem veralteten Erwartungswert (ein zuvor offenes, inzwischen geschlossenes Chart) hat korrekt `verified: false` gemeldet -- ein Beleg dafuer, dass die Verifikation echte Abweichungen erkennt, keine Bestaetigungs-Attrappe ist. |
| Fehlgeschlagen | -- |

**Bewertungshinweis (Frage 16/17 der Aufgabenstellung -- Herkunft und
Stabilitaet der Methode):** Die Sonde liest die Browser-URL, kein
obfuskiertes DOM-Element -- das ist die stabilste der in der Aufgabenstellung
genannten Kategorien (naeher an "andere Schnittstelle" als an DOM-Scraping).
Bleibt zu pruefen: bleibt dieselbe Kennung ueber TradingView-Neustarts und
-Updates hinweg stabil, oder aendert sie sich beim Neuladen des Layouts?
(Teil der noch ausstehenden Neustart-/Recovery-Tests, Abschnitt 11.)

**Gefundener und behobener Harness-Fehler:** Die CLI erlaubte urspruenglich
keine Uebergabe eines Erwartungswerts fuer die Layout-Verifikation --
`step_layout.run()` unterstuetzte den Parameter zwar bereits, aber weder
`SpikeConfig` noch `cli.py` reichten ihn durch. Der `layout`-Schritt konnte
dadurch nie mehr als `verified: false` liefern, unabhaengig vom tatsaechlichen
Wert. Behoben durch `TVCDP_EXPECTED_LAYOUT` (Umgebungsvariable), mit
Regressionstests.

## 7. 195-Minuten-Ergebnisse

**D.12 (Timeframe erkennen) -- BESTAETIGT.** D.13/D.14 (geschlossene Kerze)
noch offen.

| Umgebung | Ergebnis |
|---|---|
| Auf macOS nachgewiesen | Mechanik fuer Timeframe-Abgleich und Kerzenschluss-Erkennung inkl. Plausibilitaetspruefung (Timestamp darf nicht in der Zukunft liegen) |
| Auf Windows nachgewiesen | **D.12 ja.** `tvcdp timeframe` meldet `detected_minutes: 195` auf dem echten Chart. D.13/D.14 (geschlossene vs. laufende Kerze) noch nicht getestet. |
| Fehlgeschlagen | -- |

**Sonde (D.12):**

```javascript
(function(){
  var v = document.querySelector('#header-toolbar-intervals [role="radio"][aria-checked="true"]').getAttribute('data-value');
  return /^[0-9]+$/.test(v) ? parseInt(v, 10) : NaN;
})()
```

**Weg dorthin -- lehrreicher Fehlversuch, der die Design-Entscheidung des
Harness rechtfertigt:** Der erste Ansatz suchte den sichtbaren Text "195m"
irgendwo im Toolbar-Container (`.js-button-text`). Das schlug fehl, weil
der Container mehrere Preset-Buttons enthaelt (1 Tag/1 Woche/1 Monat/195
Minuten) und der erste Treffer in Dokumentreihenfolge nicht der aktive war.
Erst die Analyse des vollstaendigen `outerHTML` zeigte: die Buttons bilden
eine ARIA-`radiogroup`, jeder Button traegt ein maschinenlesbares
`data-value`-Attribut (`"195"`, `"1D"`, ...) sowie `aria-checked`, das
anzeigt, welcher **tatsaechlich aktiv** ist. Sichtbarer Text allein haette
sich als falsches Signal erwiesen, sobald mehrere Preset-Optionen mit
aehnlichem Text im DOM koexistieren -- ein konkretes Beispiel fuer das im
Projektplan (R1) beschriebene Risiko brueckiger DOM-Heuristiken und die
Begruendung, warum dieser Spike bewusst `aria-*`/`data-*`-Attribute statt
reinem Text bevorzugt, sobald beides verfuegbar ist.

**Hinweis:** Der kritischste Einzelfall des gesamten Spikes -- eine laufende
Kerze darf niemals als geschlossen durchgehen (R9) -- ist im Harness als
Zwei-Bedingungs-Pruefung umgesetzt (`is_closed`-Flag UND plausibler,
nicht-zukuenftiger Timestamp) und durch Unit-Tests sowie den Live-Smoke-Test
abgedeckt.

**D.13/D.14 -- Datenquelle gefunden, Sonde bereit zur finalen Verifikation
per `tvcdp closed-candle`.** Ueber die interne Chart-API (`ChartApiInstance`
via `window._exposed_chartWidgetCollection`, siehe Abschnitt 4) liefert
`m_model._mainSeries._lastBarCloseTime` einen Unix-Timestamp (Sekunden).
Empirisch bestaetigt: `Date.now()/1000 - lastBarCloseTime` war positiv
(~17,2 Stunden) -- der Wert bezeichnet also den Abschluss der zuletzt
**bereits geschlossenen** Kerze, nicht eine bevorstehende Deadline. Die
Differenz erklaert sich durch Handelspausen ausserhalb der Sitzungszeiten.

Sonde:

```javascript
(function(){
  var m = window._exposed_chartWidgetCollection.activeChartWidget.value()._modelWV.value().m_model;
  var closeTime = m._mainSeries._lastBarCloseTime;
  return { is_closed: (Date.now()/1000) >= closeTime, closed_timestamp: closeTime };
})()
```

Zusaetzlich ueber das Harness selbst bestaetigt: `tvcdp run-all` meldet
`closed_candle_detection: PASSED` (`is_closed: true`,
`closed_timestamp: 2026-08-07T19:59:59+00:00`, Alter beim Testlauf
~43,3 Stunden -- plausibel durch die Wochenend-Handelspause).

Noch offen: das Verhalten unmittelbar nach einem echten Kerzenschluss
(Nutzervorgabe, Abschnitt D.14) -- dafuer muss der Test zu einem Zeitpunkt
kurz vor/nach einem realen 195-Minuten-Abschluss an einem Handelstag
wiederholt werden. Der obige Testlauf fand an einem Wochenende statt.

## 8. Indikator-Ergebnisse

**E.15 -- alle vier Werte identifiziert und ueber das Harness bestaetigt.**

| Umgebung | Ergebnis |
|---|---|
| Auf macOS nachgewiesen | Mechanik fuer alle vier Indikatoren (RSI, RSI-MA, EMA5, EMA20), unabhaengig konfigurierbar, mit synthetischen Werten |
| Auf Windows nachgewiesen | **Datenquelle und Werte gefunden, zusaetzlich ueber `tvcdp run-all` bestaetigt** (`indicators: PASSED`, siehe unten) |
| Fehlgeschlagen | -- |

**Herkunft der Werte (Frage E.16/E.17): interne JS-Objekte, nicht DOM.**
Die Werte stammen aus der internen Chart-API, nicht aus dem DOM -- exakt die
von der Aufgabenstellung als bevorzugt bezeichnete, stabilste Kategorie.
Fundort: `window._exposed_chartWidgetCollection.activeChartWidget.value()`
liefert das aktive Chart-Widget; darauf `._modelWV.value().m_model`
(Datenmodell) `._studiesWV.value()` liefert ein Objekt aller aktiven
Studies (TradingViews interner Begriff fuer Indikatoren). Auf diesem Chart
sind 7 Studies aktiv: zwei EMA, RSI, sowie vier Standard-Overlays
(Dividends/Splits/Earnings/RollDatesCalculator), die nicht Teil unserer
Anforderung sind.

Zuordnung ueber die Laengenparameter (`study.inputs().in_0.v`) sowie
TradingViews eigene Plot-Bezeichnungen (`study.metaInfo().styles`, Feld
`title`) -- nicht geraten, sondern belegt:

| Index in `_studiesWV.value()` | Study | Laenge/Plot | Bezeichnung laut `metaInfo()` |
|---|---|---|---|
| 0 | EMA | `in_0.v = 20` | -- |
| 1 | EMA | `in_0.v = 5` | -- |
| 6 | RSI, Plot-Index 1 im Werte-Array | -- | `"RSI"` |
| 6 | RSI, Plot-Index 3 im Werte-Array | -- | `"RSI-based MA"` |

Empirische Werte zum Testzeitpunkt: EMA20 = 755.96, EMA5 = 767.58,
RSI = 67.87, RSI-MA = 58.70.

Sonden (Muster fuer alle vier gleich -- letzter Eintrag aus `plots()._items`,
nicht per fixem Array-Index wie `299`, da die Array-Laenge je nach geladener
Historie variiert):

```javascript
// EMA20 (Study-Index 0)
(function(){
  var studies = window._exposed_chartWidgetCollection.activeChartWidget.value()._modelWV.value().m_model._studiesWV.value();
  var items = studies[0].plots()._items;
  return items[items.length - 1].value[1];
})()

// EMA5 (Study-Index 1) -- wie oben, nur studies[1]
// RSI (Study-Index 6, Plot 1)
(function(){
  var studies = window._exposed_chartWidgetCollection.activeChartWidget.value()._modelWV.value().m_model._studiesWV.value();
  var items = studies[6].plots()._items;
  return items[items.length - 1].value[1];
})()

// RSI-MA (Study-Index 6, Plot 3) -- wie RSI, aber value[3] statt value[1]
```

**Lehrreicher Fehlversuch:** `study.lastValueData(0)` (eine Methode, die dem
Namen nach genau fuer "aktueller Wert" gedacht scheint) lieferte durchgehend
`{noData: true}` -- vermutlich, weil dieser Cache erst durch tatsaechliches
Rendern der UI-Legende befuellt wird, was in einer headless angesteuerten
CDP-Session nie angestossen wird. Der Umweg ueber die rohen Plot-Daten
(`.plots()._items`, letztes Element) war zuverlaessiger.

**Bekanntes Wartungsrisiko fuer eine spaetere Produktivintegration
(nicht mehr Teil des Spikes):** Die Study-Indizes (`0`, `1`, `6`) sind fuer
*dieses* Chart empirisch ermittelt, aber nicht grundsaetzlich stabil -- sie
haengen von der Reihenfolge ab, in der Indikatoren zum Chart hinzugefuegt
wurden. Ein produktiver Adapter sollte Studies dynamisch ueber `title()`
plus Laengenparameter suchen statt ueber einen festen Index, um robust
gegen Chart-Layout-Aenderungen zu sein.

Ueber das Harness bestaetigt: `tvcdp run-all` meldet `indicators: PASSED`
mit RSI = 71.094, RSI-MA = 63.869, EMA5 = 770.547, EMA20 = 759.028 (Werte
zum jeweiligen Testzeitpunkt, siehe Zeitstempel im Ergebnisverzeichnis --
nicht identisch mit den fruehen manuellen Werten oben, da zwischen beiden
Messungen Zeit vergangen ist).

**Noch offen:** der Referenzvergleich gegen manuell abgelesene
TradingView-Werte fuer mindestens 10 Aktien (Abschnitt 9) sowie eine
Watchlist- und Mehrsymbol-Sonde (Abschnitte 5 und 10).

## 9. Referenzvergleich (mindestens 10 Aktien) -- BESTAETIGT

Durchgefuehrt gegen den vierten (korrekten) `tvcdp multi-symbol`-Lauf auf
dem Windows-Zielserver, alle 10 Werte vom Nutzer manuell in TradingView
nachgeschlagen. Fuer `AAPL`, `MSFT` und `NVDA` wurden die manuell
abgelesenen Naeherungswerte explizit notiert; fuer die uebrigen sechs
Symbole hat der Nutzer die automatisierten Werte direkt gegen TradingView
geprueft und als uebereinstimmend bestaetigt, ohne separat eigene
Zahlenwerte zu notieren -- deshalb dort "bestaetigt" statt einer erfundenen
zweiten Zahl.

| Symbol | RSI (auto) | RSI (manuell) | RSI-MA (auto) | RSI-MA (manuell) | EMA5 (auto) | EMA5 (manuell) | EMA20 (auto) | EMA20 (manuell) | Ergebnis |
|---|---|---|---|---|---|---|---|---|---|
| AAPL | 45.192 | ≈ 45 | 42.337 | -- | 312.089 | ≈ 312 | 316.296 | ≈ 316 | uebereinstimmend |
| MSFT | 78.044 | ≈ 78 | 79.199 | ≈ 78 | 497.084 | ≈ 497 | 464.906 | ≈ 465 | uebereinstimmend |
| NVDA | 70.595 | ≈ 70 | 58.676 | ≈ 58 | 220.466 | ≈ 220 | 211.144 | ≈ 211 | uebereinstimmend |
| TSLA | 48.570 | -- | 38.817 | -- | 324.948 | -- | 325.217 | -- | vom Nutzer bestaetigt |
| GOOGL | 50.713 | -- | 58.191 | -- | 357.808 | -- | 354.836 | -- | vom Nutzer bestaetigt |
| AMZN | 65.003 | -- | 66.487 | -- | 274.096 | -- | 263.741 | -- | vom Nutzer bestaetigt |
| META | 49.561 | -- | 42.221 | -- | 590.288 | -- | 589.572 | -- | vom Nutzer bestaetigt |
| JPM | 58.369 | -- | 59.321 | -- | 357.412 | -- | 354.461 | -- | vom Nutzer bestaetigt |
| V | 47.991 | -- | 57.002 | -- | 365.587 | -- | 365.088 | -- | vom Nutzer bestaetigt |
| XOM | 50.043 | -- | 55.494 | -- | 153.485 | -- | 153.573 | -- | vom Nutzer bestaetigt |

**Ergebnis: 10/10 Symbole uebereinstimmend.** Erfuellt die Abnahmebedingung
aus dem urspruenglichen Auftrag ("Uebereinstimmung mit manueller
TradingView-Pruefung bei ≥ 10 Referenzaktien"). Rohdaten des Laufs unter
`results/` (Lauf vom 2026-08-09, Windows-Zielserver).

## 10. Performance-Messungen

**G -- BESTAETIGT.** Change-Symbol-Sonde gefunden; drei echte Bugs ueber
vier vollstaendige 10-Symbol-Testlaeufe auf dem Windows-Zielserver gefunden
und behoben, im vierten Lauf alle 10 Werte korrekt.

| Umgebung | Ergebnis |
|---|---|
| Auf macOS nachgewiesen | Mechanik (Durchschnitt/Median/langsamster Abruf/Fehlerrate) mit 2-3 synthetischen Symbolen: durchweg < 5 ms pro Symbol (keine echte TradingView-Interaktion, daher nicht uebertragbar) |
| Auf Windows nachgewiesen | **Ja.** Change-Symbol-Sonde gefunden; vier vollstaendige `tvcdp multi-symbol`-Laeufe mit denselben 10 realen Symbolen (`AAPL, MSFT, NVDA, TSLA, GOOGL, AMZN, META, JPM, V, XOM`) durchgefuehrt. Lauf 1 (fester Sleep): 5/10 Werte falsch, ohne erkennbaren Fehler. Lauf 2 (nach Fix 1, `getSymbol()`-Poll): 7/10 mit explizitem JS-Fehler, die uebrigen 3 teils erneut mit falschem, duplizierten Wert. Lauf 3 (nach Fix 2, Wertevergleich ohne Ausgangsbasis): 9/10 korrekt, `AAPL` zeigte faelschlich `XOM`s Wert. **Lauf 4 (nach Fix 3, Ausgangswert-Lesung vor dem ersten Wechsel): alle 10 Werte korrekt**, vollstaendig vom Nutzer gegen TradingView geprueft |

**Sonde (analog zum bereits bekannten Muster ueber die interne Chart-API):**

```javascript
window._exposed_chartWidgetCollection.activeChartWidget.value().setSymbol('NASDAQ:AAPL')
```

`TradingViewApi.changeSymbol(chartIndex, symbol, options)` (drei erwartete
Parameter) wurde zuerst versucht, warf aber bei jeder getesteten
Parameterreihenfolge `Error: Value is null` an derselben internen Stelle --
vermutlich, weil dieser hoehere API-Layer in diesem CDP-Kontext auf ein
nicht initialisiertes internes Objekt zugreift (aehnliches Muster wie bei
`watchlist()`, Abschnitt 5). Der tiefere Weg ueber das Chart-Widget selbst
(`setSymbol`, gefunden ueber dieselbe Methode wie die Indikator-Sonden:
`Object.getOwnPropertyNames(Object.getPrototypeOf(...))`) funktioniert ohne
Fehler.

**Vierter Bugfund (erster Versuch, durch den fuenften Fund als unzureichend
entlarvt):** Unmittelbar nach `setSymbol()` liefert `getSymbol()` bereits das
neue Symbol, aber die Studies (RSI, EMA, ...) liefern noch den Wert des
**vorherigen** Symbols -- kein Fehler, sondern ein still falscher Wert.
Erster Fix: ein fester Sleep von 3 Sekunden vor dem Lesen. In einem
isolierten manuellen Test (ein Symbolwechsel, 3s Wartezeit) schien das
ausreichend.

**Fuenfter Bugfund, empirisch ueber einen echten 10-Symbol-Lauf bestaetigt:**
Der feste 3-Sekunden-Sleep war **nicht** ausreichend. Im Testlauf lieferten
5 von 10 Symbolen (`MSFT, NVDA, TSLA, META, V`) exakt identische Werte --
die tatsaechlichen, korrekten Werte von `NVDA`. Der manuelle Soll/Ist-Vergleich
des Nutzers deckte das auf: `AAPL` stimmte (RSI ≈ 45, wie manuell abgelesen),
`MSFT` und `NVDA` zeigten aber beide RSI = 70.6 -- der reale MSFT-RSI-Wert
war laut manueller Pruefung ≈ 78. Der Chart blieb also bei mehreren
aufeinanderfolgenden Wechseln auf einem vorherigen Symbol haengen, ohne dass
dies als Fehler erkennbar gewesen waere: keine Exception, kein `null`, nur
ein plausibel aussehender, falscher Zahlenwert. Zusaetzlich normalisiert
TradingView den Symbolstring teils erst asynchron nach (beobachtet:
`NASDAQ:NVDA` wurde nach einigen Sekunden zu `BATS:NVDA`).

Dies ist genau das Risiko, dem das Fail-loud-Prinzip des Harness eigentlich
vorbeugen soll (Abschnitt 13), hier aber vom ersten Fix nicht abgedeckt war
-- ein fester Sleep kann eine variable, gelegentlich laengere Ladezeit oder
einen uebergangenen Wechsel-Aufruf nicht erkennen, nur eine typische
Ladezeit ueberbruecken.

**Erster Fix (Versuch 1, per Windows-Retest widerlegt):**
`step_multi_symbol.run()` sollte Werte nur noch lesen, nachdem eine
Verifikationssonde (`get_symbol_js`, liest `getSymbol()`) den Wechsel
bestaetigt -- gepollt bis zu einem Timeout, mit einem Wiederholungsversuch
des Wechsel-Aufrufs. Der erneute Testlauf auf dem Windows-Zielserver mit
genau denselben 10 Symbolen zeigte: **dieser Fix loeste das Problem nicht.**
`getSymbol()` erwies sich als nutzloses Bereitschaftssignal -- es
aktualisiert sich synchron mit dem Wechsel-Aufruf selbst, unabhaengig davon,
ob die Study-Daten (RSI, EMA, ...) tatsaechlich schon nachgezogen sind. Die
Verifikation war deshalb praktisch immer sofort "erfolgreich" (Laufzeiten
von 0,3 bis 4 Sekunden statt der erwarteten mehreren Sekunden Wartezeit),
ohne etwas Sinnvolles zu pruefen. Ergebnis dieses Testlaufs: 7 von 10
Symbolen scheiterten mit `TypeError: Cannot read properties of undefined
(reading 'value')` (Studies waehrend des Uebergangs voruebergehend nicht
definiert), und die zwei "erfolgreichen" Symbole (`AAPL`, `MSFT`) lieferten
wieder identische, falsche Werte.

**Zweiter Fix (aktueller Stand):** Statt auf `getSymbol()` wird direkt auf
den tatsaechlichen Ruecklesewert selbst gepollt -- ein Wert gilt erst als
bestaetigt, wenn er sich (fehlerfrei) vom zuletzt gelesenen Wert des
vorherigen Symbols unterscheidet. Ein `CdpProtocolError` waehrend des
Uebergangs (die beobachteten "Cannot read properties of undefined"-Faelle)
gilt dabei als "noch nicht bereit", nicht als endgueltiger Fehlschlag,
solange innerhalb des Timeouts (`TVCDP_MULTI_SYMBOL_SWITCH_TIMEOUT_SECONDS`,
Default 8s, `SpikeConfig.multi_symbol_switch_timeout_seconds`) noch ein
gueltiger, veraenderter Wert eintrifft. Bleibt der Wert unveraendert oder
fehlerhaft bis zum Timeout, wird **kein** Wert gemeldet -- der Eintrag gilt
als fehlgeschlagen, mit Begruendung. Die `get_symbol_js`-Sonde und der
Wiederholungsversuch des Wechsel-Aufrufs wurden ersatzlos entfernt, da
empirisch widerlegt bzw. am eigentlichen Problem vorbei. Jeder Eintrag
traegt weiterhin `symbol_switch_verified` (`true`/`false`/`null`, falls kein
Timeout konfiguriert ist -- dann wird einmalig ungeprueft gelesen, sichtbar
markiert statt stillschweigend als korrekt behandelt). Die vier bereits
konfigurierten Indikator-Sonden werden in der CLI automatisch zu einem
kombinierten Leseausdruck zusammengefasst (`_combined_indicator_read_js`).
Der Test-Doppelgaenger (`ScriptedCdpServer`) wurde um einen `JsError`-
Sentinel erweitert, um den beobachteten Uebergangsfehler in Tests zu
simulieren.

**Bekannte Grenze dieses Ansatzes:** Liefert ein neues Symbol zufaellig
exakt dieselben vier Indikatorwerte wie das vorherige (bei kontinuierlichen
Gleitkommawerten praktisch ausgeschlossen, aber nicht unmoeglich), wuerde
der Poll faelschlich bis zum Timeout warten und einen Fehlschlag melden,
obwohl der Wert korrekt waere. Fuer einen Spike akzeptabel, in einer
Produktivintegration waere ein zusaetzliches, unabhaengiges
Bereitschaftssignal (z. B. ein neuer Bar-Timestamp) robuster.

**Re-Test des zweiten Fixes auf dem Windows-Zielserver (10 Symbole):**
9 von 10 Werten korrekt, aber ein weiterer, subtilerer Fund: `AAPL` (erstes
Symbol im Lauf) und `XOM` (letztes Symbol) zeigten exakt identische Werte
bis zur letzten Nachkommastelle -- bei vier unabhaengigen Gleitkommawerten
praktisch ausgeschlossen als Zufall. Der Nutzer bestaetigte per manueller
Pruefung: `XOM`s Wert war korrekt, `AAPL` hatte faelschlich `XOM`s Wert
uebernommen. Ursache: `AAPL` war das **erste** Symbol des Laufs, und fuer
das erste Symbol gab es keinen Vergleichswert (`previous_values` startete
bei `None`) -- der allererste gelesene Wert wurde deshalb ungeprueft
akzeptiert. Da die CDP-Session eines neuen `tvcdp`-Prozesses auf das noch
laufende TradingView Desktop trifft, zeigte der Chart zu diesem Zeitpunkt
noch den Altbestand des zuletzt in einem frueheren Prozessaufruf gesetzten
Symbols (`XOM`, das letzte Symbol der Liste) -- und dieser Altwert wurde
faelschlich als "neuer, abweichender Wert" fuer `AAPL` durchgewunken, weil
er sich ja tatsaechlich von `None` unterschied.

**Dritter Fix:** Vor dem allerersten Symbolwechsel eines Laufs wird einmalig
der aktuell angezeigte Wert gelesen und als Ausgangsbasis fuer den Vergleich
verwendet -- damit hat auch das erste Symbol einen echten Vergleichswert,
nicht nur `None`. Regressionstest ergaenzt
(`test_erstes_symbol_wird_gegen_ausgangswert_vor_dem_wechsel_geprueft`), 96
lokale Tests gruen, ruff/mypy clean.

**Vierter Testlauf auf dem Windows-Zielserver (mit dem dritten Fix):**
`multi_symbol_run: PASSED`, `error_count: 0`, alle 10 Symbole mit
`symbol_switch_verified: true`. `AAPL` liefert jetzt RSI = 45.192,
RSI-MA = 42.337, EMA5 = 312.089, EMA20 = 316.296 -- deckt sich mit der
manuellen Ablesung (≈ 45 / -- / ≈ 312 / ≈ 316) und ist klar von `XOM`s Werten
unterschieden. Der Nutzer hat alle 10 Werte dieses Laufs vollstaendig gegen
TradingView geprueft (Abschnitt 9) -- **G ist damit bestaetigt.**

**Fazit zu G:** Drei Iterationen waren noetig, jede durch einen echten
10-Symbol-Testlauf auf dem Windows-Zielserver aufgedeckt -- ein Beleg dafuer,
warum Phase A (macOS, synthetische Sonden) allein nicht als Nachweis fuer
Phase B ausreicht, und warum die Nutzervorgabe eines Referenzvergleichs mit
≥10 echten Aktien (Abschnitt 9) kein Nice-to-have ist, sondern genau diese
Klasse von Fehlern faengt, die keine Exception wirft.

## 11. Neustart-/Recovery-Tests

| Test | Ergebnis |
|---|---|
| TradingView-Neustart | **BESTAETIGT.** `tvcdp environment`/`tvcdp reachability` vor und nach dem Neustart (TradingView geschlossen, mit demselben `Invoke-CommandInDesktopPackage`-Befehl aus Abschnitt 3a neu gestartet). Debug-Port danach automatisch wieder erreichbar, ohne zusaetzlichen manuellen Schritt (`target_count` 8 -> 9, neue Session-IDs, aber dasselbe zuvor offene Chart-Layout `LAYOUT-B` von TradingView selbst wiederhergestellt) |
| Prozessabsturz | **BESTAETIGT.** TradingView-Prozess im Task-Manager hart beendet (statt sauber geschlossen), mit demselben Befehl neu gestartet. Danach: `environment: PASSED`, `reachability: PASSED` (Port automatisch wieder erreichbar, dasselbe Chart-Layout wiederhergestellt), **und** `session_check: PASSED` -- die Sitzung blieb authentifiziert, kein erneuter Login noetig |
| Windows-Neustart (vollstaendig unbeaufsichtigt) | **Bewusst zurueckgestellt, nicht Teil dieses Spikes.** Siehe Abschnitt 12 fuer die Begruendung (Autologon-Entscheidung). |
| Netzwerkunterbrechung | **BESTAETIGT.** Netzwerkadapter kurz deaktiviert/aktiviert, `tvcdp reachability` davor/danach: identische Target-IDs, wie erwartet unbeeinflusst -- die CDP-Verbindung laeuft ausschliesslich ueber `127.0.0.1` (Loopback), nicht ueber die tatsaechliche Netzwerkschnittstelle |

## 12. Unbeaufsichtigter Windows-Betrieb

| Test | Ergebnis |
|---|---|
| Gesperrter Bildschirm | **BESTAETIGT.** `tvcdp reachability` vor und nach Sperren (Win+L) und Entsperren: identische Target-IDs vor und nach dem Test -- der Debug-Port blieb ueber die gesamte Sperrzeit durchgehend erreichbar, dieselbe CDP-Session, kein Neustart oder Verbindungsabbruch |
| RDP-Disconnect | **BESTAETIGT.** RDP-Sitzung getrennt (nicht abgemeldet), 1-2 Minuten gewartet, neu verbunden: `reachability: PASSED` mit identischen Target-IDs, `session_check: PASSED` -- TradingView und der Debug-Port laufen ohne aktive RDP-Verbindung unbeeintraechtigt im Hintergrund weiter |
| Windows-Neustart (unbeaufsichtigt) | **Bewusst zurueckgestellt.** Siehe Begruendung unten. |
| Autostart | **Bewusst zurueckgestellt.** Siehe Begruendung unten. |

**Begruendung fuer die Zurueckstellung (bewusste Nutzerentscheidung, kein
technisches Scheitern):** TradingView Desktop ist eine GUI-Anwendung.
Windows fuehrt Hintergrunddienste und geplante Aufgaben, die "unabhaengig
von der Anmeldung" laufen, standardmaessig in Session 0 aus -- seit der
Session-0-Isolation (ab Windows Vista) koennen GUI-Anwendungen dort nicht
mehr gerendert werden. Ein wirklich unbeaufsichtigter Betrieb (Server startet
neu, niemand meldet sich an, TradingView laeuft trotzdem mit sichtbarem
CDP-Debug-Port) erfordert deshalb technisch **Windows-Autologon**
(automatische Anmeldung an einer echten interaktiven Desktop-Sitzung beim
Boot) -- exakt das Risiko, das der urspruengliche Projektplan bereits unter
R2 vorausgesehen hat ("braucht eine dauerhaft angemeldete interaktive
Sitzung"). Autologon hinterlegt ein Passwort mehr oder weniger im Klartext
in der Registry. Der Nutzer hat entschieden, diese Credential-Handling-
Entscheidung bewusst **ausserhalb** des Zeitdrucks dieses Spikes zu treffen,
nicht als Nebeneffekt eines Testschritts. **R2 bleibt damit ein bekanntes,
ungeloestes Risiko** -- die technische Anforderung (Autologon noetig) ist
geklaert, die Sicherheitsentscheidung dazu noch offen. Eine produktive
Integration darf diesen Punkt nicht uebergehen.

## 13. Fehlerfaelle

| Fehlerfall | Status |
|---|---|
| CDP nicht erreichbar | Auf macOS und **auf Windows nachgewiesen** (automatisiert, `error_case_detection`-Schritt, `tvcdp run-all`: `detected: true`). Der auf Windows gefundene `ConnectTimeout`-Bug (siehe Kasten unten) ist behoben und der Re-Test nach dem Fix war erfolgreich. |
| TradingView nicht gestartet | Auf macOS und auf Windows nachgewiesen (identischer Mechanismus wie oben) |
| JavaScript-/Auswertungsfehler wird erkannt (Stellvertreter fuer mehrere App-Fehlerzustaende) | Auf macOS und auf Windows nachgewiesen |
| Falsches Layout | Ungeplant bereits auf Windows beobachtet: ein Testlauf mit veralteter `TVCDP_EXPECTED_LAYOUT` (zeigte auf ein zuvor offenes, inzwischen geschlossenes Chart) meldete korrekt `layout_detection: FAILED` mit `verified: false`. Nach Korrektur der Umgebungsvariable auf das tatsaechlich aktive Chart: `PASSED`, `verified: true`. Kein Harness-Fehler, sondern ein veralteter Konfigurationswert -- und zugleich ein Beleg, dass die Verifikation echte Abweichungen zuverlaessig erkennt. |
| Symbol nicht geladen | **BESTAETIGT.** `tvcdp multi-symbol` mit einem frei erfundenen, nicht existierenden Symbol (`NASDAQ:DIESSYMBOLGIBTESNICHT123`) ausgefuehrt: `setSymbol()` wirft selbst keinen Fehler, aber jeder Leseversuch innerhalb des 8-Sekunden-Timeouts scheitert konsistent mit `TypeError: Cannot read properties of undefined` -- der Schritt markiert den Eintrag korrekt als `succeeded: false` mit Begruendung, statt nach Ablauf der Wartezeit einen erfundenen Wert zu melden |
| Falscher Timeframe | **BESTAETIGT.** Timeframe manuell auf "T" (Tage) umgestellt, `tvcdp timeframe` ausgefuehrt: `INCONCLUSIVE` mit `reason: "Sonde lieferte keinen numerischen Wert."` -- der `data-value` fuer Tages-/Wochen-Timeframes ist kein reiner Minutenwert und wird deshalb korrekt als nicht auswertbar erkannt, statt einen falschen Zahlenwert zu raten |
| Indikator fehlt | **BESTAETIGT.** RSI manuell aus dem Chart entfernt, `tvcdp indicators` ausgefuehrt: `FAILED` mit `TypeError: Cannot read properties of undefined (reading 'plots')` -- das Entfernen verschiebt das `studies`-Array, der fest konfigurierte Index (`studies[6]`) zeigt danach ins Leere. Kein stiller Fehlwert, klare Fehlermeldung. Bestaetigt zugleich empirisch das in Abschnitt 8 dokumentierte Wartungsrisiko (Study-Indizes sind nicht stabil) |
| Werte noch nicht aktualisiert | **BESTAETIGT (bereits durch die G-Testlaeufe, Abschnitt 10).** Genau dieser Fehlerfall war die Ursache der drei G-Bugs: Werte, die dem vorherigen statt dem aktuellen Symbol entsprachen. Der finale Mechanismus (Wertevergleich mit Ausgangsbasis) faengt ihn zuverlaessig ab -- kein separater Test noetig, das Verhalten wurde bereits ueber vier vollstaendige 10-Symbol-Laeufe empirisch geprueft. |
| Aktuelle statt geschlossene Kerze | Mechanik auf macOS nachgewiesen (synthetisch) und auf Windows ueber `tvcdp closed-candle` bestaetigt (Abschnitt 7). Der Testzeitpunkt lag bislang nie exakt auf einer echten 195-Minuten-Kerzengrenze (12:45 oder 16:00 ET) -- ein Test unmittelbar um einen echten Kerzenschluss steht noch aus, siehe "Noch offen" unten. |
| Watchlist nicht verfuegbar | **BESTAETIGT (bereits durch Abschnitt 5).** `tvcdp run-all` meldet den `watchlist`-Schritt durchgehend als `INCONCLUSIVE` mit `reason: "Keine Sonde konfiguriert"`, da fuer B keine funktionierende interne API gefunden wurde (`watchlist()` liefert `not implemented`). Genau das gewuenschte Verhalten: kein stiller Fehlwert, sondern eine ehrliche, begruendete Nichtaussage. |

**Noch offen:** Ein Test unmittelbar um einen echten 195-Minuten-Kerzenschluss
(12:45 oder 16:00 ET) herum, um D.14 (Kerze wechselt live von "laufend" zu
"geschlossen") nicht nur synthetisch, sondern am tatsaechlichen Uebergang zu
pruefen.

Grundprinzip (durch Unit-Tests erzwungen): **kein Schritt liefert bei
fehlender Voraussetzung einen Default- oder Null-Wert.** Ein nicht
konfigurierbarer oder nicht auswertbarer Zustand fuehrt immer zu
`INCONCLUSIVE` oder `FAILED`, nie zu einem stillschweigend plausibel
aussehenden Ergebnis.

**Dritter Harness-Bug, gefunden ueber `tvcdp run-all` auf dem Windows
Server:** Der `error_case_detection`-Schritt simuliert einen nicht
erreichbaren CDP-Endpunkt, indem er absichtlich einen unbenutzten lokalen
Port anspricht, und erwartet dabei `CdpConnectionError`. `list_targets()`
hat bislang nur `httpx.ConnectError` (sofortige Verbindungsablehnung)
abgefangen. Auf dem Windows Server fuehrte derselbe Testfall stattdessen zu
`httpx.ConnectTimeout` -- vermutlich, weil dort Pakete an geschlossene
lokale Ports verworfen statt sofort abgelehnt werden (Firewall- oder
Sicherheitssoftware-Verhalten, das auf macOS in dieser Form nicht auftrat).
`ConnectTimeout` ist keine Unterklasse von `ConnectError`, wurde also nicht
abgefangen und ist ungefangen bis zur CLI durchgereicht worden (`"error":
"ConnectTimeout: timed out"`). Behoben durch Erweiterung des
`except`-Ausdrucks um `httpx.TimeoutException`; Regressionstest ergaenzt.
Dies ist ein konkretes Beispiel fuer eine Windows-spezifische
Laufzeitabweichung, die auf macOS nicht sichtbar war -- der genaue Grund,
warum Phase A allein nicht als Nachweis fuer Phase B gilt. Re-Test nach dem
Fix auf demselben Windows Server: `error_case_detection: PASSED`.

## 14. Technische Risiken

Diese Liste ist nicht mehr die Vorab-Einschaetzung aus Phase A, sondern der
Stand nach Abschluss von Phase B -- jeder Punkt ist entweder durch einen
echten Windows-Testlauf bestaetigt, entkraeftet oder bewusst offen
geblieben.

- **R1 (DOM-/interne-API-Bruechigkeit) -- bestaetigt, nicht nur theoretisch.**
  Der "Indikator fehlt"-Test (Abschnitt 13) hat gezeigt: Entfernt man einen
  Indikator im Chart, verschiebt sich das interne `studies`-Array, und ein
  fest codierter Index (`studies[6]`) zeigt danach ins Leere. Das Harness
  faengt das laut ab (`FAILED` statt Fehlwert), aber das Risiko selbst ist
  real und muss in einer Produktivintegration durch dynamisches Nachschlagen
  ueber Titel/Laengenparameter statt feste Indizes geloest werden
  (Abschnitt 8, "Bekanntes Wartungsrisiko").
- **R1 (Aenderungen an der TradingView-Desktop-App) -- neu und konkret
  bestaetigt:** Die MSIX-Verpackung ueber den Microsoft Store macht einen
  direkten Prozessstart unmoeglich; nur `Invoke-CommandInDesktopPackage`
  funktioniert (Abschnitt 3a). Ein zukuenftiges Store-Update koennte diesen
  Startweg ohne Vorwarnung aendern.
- **Interne API-Luecken sind real, nicht hypothetisch:** `TradingViewApi.watchlist()`
  und `TradingViewApi.changeSymbol()` sind in diesem Kontext nicht
  funktionsfaehig ("not implemented" bzw. `Value is null`), obwohl beide auf
  den ersten Blick die naheliegende, offiziell wirkende Loesung waeren
  (Abschnitte 5 und 10). Nur der tiefere Weg ueber das Chart-Widget selbst
  funktionierte zuverlaessig.
- **R2 (unbeaufsichtigter Betrieb) -- bestaetigt und ungeloest.** TradingView
  Desktop ist eine GUI-Anwendung und kann nicht in Session 0 laufen. Ein
  taeglicher, unbeaufsichtigter Produktivlauf (der eigentliche Zielzustand
  des Gesamtprojekts) erfordert Windows-Autologon. Diese
  Credential-Handling-Entscheidung ist bewusst nicht Teil dieses Spikes
  (Abschnitt 12) -- **eine Produktivintegration ist ohne diese Entscheidung
  nicht einsatzbereit**, unabhaengig davon, wie gut die technische Anbindung
  sonst funktioniert.
- **Symbolwechsel ist nicht sofort verlaesslich.** Drei Iterationen waren
  noetig, um Symbolwechsel zuverlaessig zu verifizieren (Abschnitt 10) --
  weder der Ruecklesewert von `getSymbol()` noch ein fester Sleep waren
  ausreichende Bereitschaftssignale. Eine Produktivintegration muss densel­ben
  Wertevergleichs-Mechanismus (oder einen gleichwertigen) uebernehmen, sonst
  drohen still falsche Indikatorwerte -- der schwerwiegendste denkbare Fehler
  fuer ein System, das auf diesen Werten Handelssignale aufbaut.
- Electron-/App-Updates koennen den Debug-Port oder das interne Objektmodell
  weiterhin ohne Vorwarnung aendern (unveraendert aus dem Projektplan, R1) --
  dieser Spike belegt nur den aktuellen Stand (App-Version siehe Abschnitt 3),
  keine dauerhafte Garantie.

## 15. Wartungsrisiken

Jede TradingView-spezifische Sonde ist eine potenzielle Bruchstelle bei
TradingView-Updates. Das Harness minimiert das Risiko strukturell (Sonden
sind austauschbar, ohne Codeänderung), verringert es aber nicht auf null.
Empirisch bestaetigt (nicht nur vermutet) durch den "Indikator
fehlt"-Test: die Study-Indizes (`studies[0]`, `studies[1]`, `studies[6]`)
sind fuer *dieses* Chart in *diesem* Zustand gueltig, aber nicht
grundsaetzlich stabil -- sie haengen von der Reihenfolge ab, in der
Indikatoren zum Chart hinzugefuegt wurden, und verschieben sich, sobald sich
diese Reihenfolge aendert. Eine Produktivintegration muss Studies dynamisch
ueber `title()` plus Laengenparameter suchen, niemals ueber einen
gespeicherten festen Index.

## 16. Bekannte Lizenz-/Nutzungsfragen

**Nicht bewertet in Phase A.** Diese Bewertung ist ausdruecklich von der
technischen Bewertung getrennt zu halten (Nutzervorgabe) und erfordert eine
Pruefung der TradingView-Nutzungsbedingungen fuer den gewaehlten
Zugriffsweg, die hier nicht als erledigt behauptet wird.

## 17. Sicherheitsrisiken

- Das Harness liest zu keinem Zeitpunkt Cookies, LocalStorage oder sonstige
  Session-Artefakte aus (Design-Entscheidung, siehe
  `src/tvcdp/steps/step_session_check.py`).
- Alle geschriebenen Log- und Ergebnisdateien laufen durch eine zentrale
  Redaction-Schicht (`src/tvcdp/redaction.py`), die Schluessel wie `token`,
  `cookie`, `secret`, `password`, `session_id` sowie Bearer-/JWT-aehnliche
  Werte in Freitext entfernt -- unabhaengig davon, ob eine einzelne Sonde
  versehentlich mehr zurueckliefert als beabsichtigt.
- Verbleibendes Risiko: eine schlecht gewaehlte, selbst konfigurierte Sonde
  (`TVCDP_PROBE_*`) koennte theoretisch dennoch versuchen, sensible Daten zu
  lesen. Das Harness verhindert das nicht auf JavaScript-Ebene (das waere
  nur mit einer eigenen, engeren CDP-Sandbox moeglich) -- es faengt es aber
  in der Persistenz-/Logging-Schicht ab. Bei der Sondenermittlung in Phase B
  ist deshalb weiterhin bewusst auf boolesche/strukturelle Signale zu achten,
  nie auf Rohinhalte.

## 18. Go-/No-Go-Empfehlung

**GO_WITH_LIMITATIONS.**

Diese Empfehlung bezieht sich ausschliesslich auf die **technische
Stabilitaet** (Dimension 1). Die **lizenz-/nutzungsrechtliche Zulaessigkeit**
(Dimension 2, Abschnitt 16) wurde in diesem Spike bewusst nicht bewertet und
bleibt eine eigenstaendige, unabhaengige Voraussetzung -- bei Unsicherheit
dort wird keine produktive Integration freigegeben, unabhaengig von diesem
technischen Ergebnis (Nutzervorgabe, siehe Sprint-0-Auftrag).

### Was fuer ein GO spricht

- **Alle neun urspruenglich gestellten technischen Kernfragen (A-I) sind auf
  dem echten Windows-Zielserver beantwortet**, nicht nur auf macOS: CDP-Start
  ueber MSIX (A.1/A.2), bestehende Sitzung ohne Zugangsdaten-Zugriff nutzbar
  (A.3), Chartlayout erkannt und verifiziert (C.9/C.10), 195-Minuten-Timeframe
  zuverlaessig erkannt (D.12), geschlossene Kerze eindeutig identifiziert
  (D.13/D.14), alle vier Indikatoren korrekt ausgelesen (E.15), Mehrsymbol-
  Durchlauf nach Fixes zuverlaessig (G), Fehlerfaelle werden laut statt still
  falsch behandelt (I).
- **Der Referenzvergleich (F) ist die staerkste einzelne Evidenz:** 10 von 10
  real gehandelten Aktien lieferten automatisiert exakt die Werte, die der
  Nutzer manuell in TradingView abgelesen hat (Abschnitt 9) -- nach drei
  Iterationen, in denen echte, sonst unbemerkte Fehler (nicht Exceptions,
  sondern plausibel aussehende falsche Zahlen) gefunden und behoben wurden.
  Das ist genau die Fehlerklasse, vor der ein Handelssignal-System am
  meisten geschuetzt werden muss, und der Prozess hat gezeigt, dass sie
  zuverlaessig auffindbar und behebbar ist, wenn systematisch gegen echte
  Referenzwerte geprueft wird.
- **Betriebliche Resilienz ist ueberdurchschnittlich gut belegt:** TradingView
  Desktop und der CDP-Debug-Port ueberstehen App-Neustart, harten
  Prozessabsturz, gesperrten Bildschirm, RDP-Disconnect und
  Netzwerkunterbrechung jeweils ohne manuellen Eingriff und ohne
  Sitzungsverlust (Abschnitte 11-12) -- fuer eine inoffizielle,
  UI-basierte Integration ein besseres Ergebnis, als der Projektplan
  urspruenglich befuerchtet hatte.
- Das Harness selbst ist sicherheitsbewusst (keine Zugangsdaten in Logs/
  Ergebnissen, zentrale Redaction, Abschnitt 17) und plattformunabhaengig
  gebaut.

### Was die Einschraenkungen sind (das "WITH_LIMITATIONS")

1. **R2 -- unbeaufsichtigter taeglicher Betrieb ist nicht bewiesen.** Der
   eigentliche Zielzustand des Gesamtprojekts (ein Scheduler startet einen
   Lauf, ohne dass jemand angemeldet ist) erfordert Windows-Autologon. Diese
   Entscheidung wurde bewusst aus diesem Spike herausgehalten (Abschnitt 12).
   **Vor einer Produktivintegration muss diese Sicherheits-/Betriebs-
   entscheidung separat getroffen und danach genau dieser Fall
   (Server-Neustart, niemand angemeldet, Lauf startet trotzdem) getestet
   werden.**
2. **Watchlist (B) ist ueber die untersuchten internen APIs nicht lesbar.**
   Eine Produktivintegration braucht entweder einen noch nicht gefundenen
   Weg oder eine manuell gepflegte/exportierte Symbolliste als Ersatz
   (Abschnitt 5).
3. **Study-Indizes sind nicht stabil** (Abschnitt 14/15, empirisch bestaetigt)
   -- ein produktiver Adapter darf niemals feste Indizes verwenden, sondern
   muss dynamisch ueber Titel/Laengenparameter suchen.
4. **Der exakte Live-Uebergang an einem echten 195-Minuten-Kerzenschluss**
   wurde nicht getestet (nur synthetisch/statisch, Abschnitt 13) -- ein
   niedrigeres, aber reales Restrisiko.
5. **Lizenz-/Nutzungsbedingungen (Dimension 2) sind ungeprueft** und stehen
   unabhaengig von allen technischen Ergebnissen ueber jeder
   Produktionsentscheidung.

### Empfehlung fuer die Produktarchitektur

Unveraendert zum bestehenden Projektplan: `MarketDataProvider` bleibt ein
Protokoll im Domain Layer; ein `TradingViewMarketDataProvider` waere ein
austauschbarer Infrastructure-Adapter, der intern denselben CDP-Mechanismus
nutzen koennte wie dieses Harness, aber:

- als Sidecar-Prozess auf dem Windows-Host liefe (R2, GUI-App nicht
  containerisierbar) -- **und darf ohne eine getroffene Autologon-/
  Credential-Entscheidung nicht fuer den unbeaufsichtigten Produktivbetrieb
  eingeplant werden**,
- die hier erprobte Redaction-/Fail-loud-Logik sowie den
  Wertevergleichs-Mechanismus fuer Symbolwechsel (Abschnitt 10) uebernehmen
  sollte,
- Studies ausschliesslich dynamisch ueber Titel/Laengenparameter ansprechen
  sollte, nie ueber feste Indizes,
- **erst nach Klaerung von Dimension 2 (Lizenz/Nutzungsbedingungen) und nur
  mit ausdruecklicher Freigabe** implementiert wird (Gate G3, unveraendert).

## Fallback-Vergleich

Da CDP in Phase B technisch funktioniert hat (GO_WITH_LIMITATIONS, Abschnitt
18), ist dieser Vergleich nicht mehr entscheidungskritisch fuer ein GO/NO_GO
der CDP-Variante -- bleibt aber relevant, falls Dimension 2 (Lizenz-/
Nutzungsbedingungen) gegen CDP spricht. Weiterhin nicht bewertet, da
ausserhalb des Auftragsumfangs dieses Spikes. Platzhalter fuer die
geforderten Varianten:

**A. TradingView Alerts/Webhooks + lokale Indikatorberechnung**
Noch nicht bewertet.

**B. TradingView-Watchlist-Export + lizenzierter Market-Data-Provider +
lokale Indikatorberechnung**
Noch nicht bewertet.

## Aus Phase A gelernt (zwei echte Bugs, live gefunden und behoben)

1. **Lauf-Verzeichnis-Kollision:** `new_run_directory()` nutzte
   Sekundenaufloesung mit `mkdir(exist_ok=False)` -- zwei schnelle
   Einzelschritt-Aufrufe hintereinander (z. B. in einem Shell-Skript ohne
   Pause) kollidierten und liessen den Prozess mit `FileExistsError`
   abstuerzen. Behoben durch Mikrosekundenaufloesung plus
   Kollisions-Fallback; Regressionstest ergaenzt.
2. **Zeitliche Reihenfolge bei der Kerzenschluss-Plausibilitaetspruefung:**
   `step_closed_candle.run()` erfasste die Referenzzeit ("jetzt") *vor* dem
   CDP-Roundtrip. Ein im Seitenkontext frisch erzeugter Timestamp (z. B.
   `new Date().toISOString()`) entsteht dadurch aus Sicht des Harness
   scheinbar "in der Zukunft" -- reine Netzwerklatenz, kein echter Fehler,
   haette aber jede frische, korrekte Kerze als `FAILED` gemeldet. Behoben,
   indem die Referenzzeit erst nach dem Roundtrip erfasst wird.

Beide Funde stammen aus dem Live-Smoke-Test gegen ein echtes CDP-Ziel, nicht
aus den Unit-Tests -- ein Beleg dafuer, warum Phase B trotz gruener Tests
notwendig bleibt, bevor eine Go-/No-Go-Entscheidung getroffen werden kann.
