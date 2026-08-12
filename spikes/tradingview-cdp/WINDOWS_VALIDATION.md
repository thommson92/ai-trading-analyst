# Phase B: Validierung auf dem Windows-Zielserver

Dieses Dokument fuehrt durch den Gate-G2-Spike auf dem tatsaechlichen
Windows-Zielserver. Phase A (macOS) hat die CDP-Kernmechanik des Harness
bereits gegen ein echtes Chromium-Ziel bestaetigt -- hier geht es nur noch
um TradingView-spezifische Fragen, die sich ohne echten Zugriff nicht
beantworten lassen.

**Geschaetzter Zeitrahmen:** 3-5 Arbeitstage (Nutzervorgabe). Bei fehlender
robuster Loesung innerhalb dieses Zeitrahmens: No-Go bzw. eingeschraenktes
Go, nicht unbegrenzt weiter experimentieren.

## Kurzfassung (fuer den eiligen Durchlauf)

1. Repository auschecken, Python 3.11+ installieren.
2. `cd spikes\tradingview-cdp && python -m venv .venv && .venv\Scripts\pip install -e ".[dev]"`
3. TradingView Desktop mit aktiviertem Remote-Debugging starten (Abschnitt 1).
4. Sonden ermitteln (Abschnitt 2) und als Umgebungsvariablen setzen.
5. `.venv\Scripts\tvcdp run-all` ausfuehren.
6. Den erzeugten Ordner unter `results\` zurueck ins Repository committen
   bzw. an Claude Code uebertragen.

Der Rest dieses Dokuments erklaert jeden Schritt im Detail sowie die
zusaetzlichen manuellen Tests (Neustart, RDP, Autostart), die das Harness
nicht selbst ausloesen kann.

---

## 0. Voraussetzungen

- Windows-Server bzw. eine technisch gleichwertige Windows-Umgebung
  (Nutzervorgabe -- **kein Docker-Container** fuer TradingView Desktop).
- TradingView Desktop bereits installiert und mit dem regulaeren Konto
  eingeloggt (bestehende Sitzung, siehe Abschnitt A der Aufgabenstellung).
- Python 3.11 oder neuer.
- Git.

Keine Zugangsdaten, Session-Cookies oder Tokens in dieses Dokument, in
Fixtures, Screenshots oder Logs eintragen -- das Harness ist so gebaut,
dass es diese ohnehin nie anfordert (siehe REPORT.md, Abschnitt 17).

## 1. TradingView Desktop mit aktiviertem CDP starten

TradingView Desktop ist eine Electron-Anwendung. Electron-Apps aktivieren
Remote-Debugging ueber denselben Kommandozeilenschalter wie Chrome.

**Bestaetigt funktionierender Weg auf Windows Server mit Microsoft-Store-
/MSIX-Installation** (erkennbar am Pfad
`C:\Program Files\WindowsApps\...`): Ein direkter Prozessstart
(`Start-Process`, Call-Operator `&`) gegen die `.exe` unter `WindowsApps`
scheitert dort mit "Zugriff verweigert" -- dieser Pfad ist durch
Windows-ACLs geschuetzt, unabhaengig von Administratorrechten. Stattdessen
ueber die Paket-Identitaet starten:

```powershell
$pkg = Get-AppxPackage *TradingView*
$appId = (Get-AppxPackageManifest $pkg).Package.Applications.Application.Id

Invoke-CommandInDesktopPackage `
    -PackageFamilyName $pkg.PackageFamilyName `
    -AppId $appId `
    -Command "$($pkg.InstallLocation)\TradingView.exe" `
    -Args "--remote-debugging-port=9222" `
    -PreventBreakaway
```

Erfolg zeigt sich direkt in der Konsole -- TradingView Desktop selbst gibt
beim Start diese Zeile aus (native Chromium-Bestaetigung, keine Annahme des
Harness):

```
DevTools listening on ws://127.0.0.1:9222/devtools/browser/<uuid>
```

Falls `Get-Command Invoke-CommandInDesktopPackage` nichts findet oder der
Aufruf selbst scheitert: das ist ein eigenstaendiges, dokumentierenswertes
Ergebnis (Windows-Server-Editionen unterstuetzen die Store-/AppX-
Infrastruktur nicht immer vollstaendig) -- in REPORT.md unter "Frage A.1/
A.2" vermerken, dann pruefen, ob TradingView einen klassischen
`.exe`/`.msi`-Installer ausserhalb des Microsoft Store anbietet.

**Bei klassischer (Nicht-Store-) Installation** reicht der einfachere Weg:

```powershell
$tvPath = "C:\Path\To\TradingView.exe"
Start-Process -FilePath $tvPath -ArgumentList "--remote-debugging-port=9222"
```

**Pruefen, ob es funktioniert hat:**

```powershell
Start-Sleep -Seconds 3
Invoke-RestMethod http://127.0.0.1:9222/json/list
```

(`Invoke-RestMethod` statt `curl` -- in PowerShell ist `curl` ein Alias auf
`Invoke-WebRequest`, das die Antwort nicht als geparstes JSON zurueckgibt.)

Eine JSON-Liste mit mindestens einem Eintrag bedeutet: A.1 und A.2 sind
bereits positiv beantwortet. Erscheint stattdessen ein
Verbindungsfehler, pruefen:

- **MSIX-/Store-Pakete koennen benutzerdefinierte Kommandozeilenschalter
  ignorieren.** Manche Store-verpackten Electron-Apps leiten `argv` nicht
  unveraendert an den Chromium-Prozess weiter (Sandboxing/Manifest-
  Einschraenkungen). Falls der Prozess startet, aber `/json/list` dennoch
  nicht erreichbar ist, ist das selbst ein dokumentierenswertes Ergebnis
  fuer REPORT.md Abschnitt A.1 -- keine Konfigurationsfrage, sondern ein
  moeglicher Show-Stopper fuer genau diesen Installationsweg. Gegenprobe:
  `Get-Process TradingView* | Select-Object Path,CommandLine` zeigt, ob der
  Schalter im tatsaechlich laufenden Prozess noch vorhanden ist.
- Startet TradingView Desktop ueberhaupt (manche Auto-Update-Mechanismen
  starten die App im Hintergrund neu und ueberschreiben die
  Kommandozeilenargumente)?
- Ist Port 9222 bereits belegt (`netstat -ano | findstr 9222`)? Falls ja,
  einen anderen Port waehlen und `TVCDP_PORT` entsprechend setzen.
- Blockiert eine lokale Firewall-Regel den Port (sollte bei
  `127.0.0.1`-only nicht relevant sein, aber pruefen)?

Falls der Debug-Port nach einem Auto-Update von TradingView verschwindet:
das ist ein eigenstaendiges, dokumentierenswertes Ergebnis fuer Abschnitt A.4
des Berichts (nicht stillschweigend uebergehen).

**Zielerkennung schaerfen:** `/json/list` meldet neben dem eigentlichen
Chart auch mehrere interne Electron-Renderer-Seiten der App (Titelleiste,
Tooltip, Drag-Service etc.) mit `file:///.../TradingView.Desktop_.../...`-
URLs. Der Ordnername der MSIX-Installation enthaelt selbst das Wort
"TradingView" -- der Standardwert `TVCDP_TARGET_TITLE_PATTERN=TradingView`
matcht deshalb mehrdeutig. Vor den naechsten Schritten setzen:

```powershell
$env:TVCDP_TARGET_TITLE_PATTERN = "tradingview.com"
```

Das trifft nur die echte, unter `https://[...]tradingview.com/chart/...`
laufende Chart-Seite, nicht die lokalen Installationsdateien.

## 2. Sonden ermitteln

Das Harness rate keine DOM-Selektoren oder internen TradingView-Objektpfade
(bewusste Design-Entscheidung, siehe REPORT.md Abschnitt 4). Diese muessen
einmalig manuell ermittelt werden -- am einfachsten ueber die regulaeren
Chrome-DevTools, die sich gegen denselben Debug-Port oeffnen lassen:

1. Chrome oeffnen, zu `http://127.0.0.1:9222` navigieren.
2. Den Eintrag anklicken, der zu TradingView gehoert -- das oeffnet ein
   normales DevTools-Fenster mit voller Konsole, Elements-Panel etc.,
   **verbunden mit dem laufenden TradingView-Prozess.**
3. In der Konsole experimentieren, bis ein JavaScript-Ausdruck fuer jede der
   folgenden Fragen einen brauchbaren Wert liefert:

| Umgebungsvariable | Erwarteter Rueckgabewert | Ausgangspunkte zum Ausprobieren |
|---|---|---|
| `TVCDP_PROBE_SESSION_AUTHENTICATED_JS` | `true`/`false` | **Bestaetigt funktionierend:** `window.ChartApiInstance.connected()` -- liefert einen reinen Wahrheitswert, ohne je `sessionid`/Token-Felder zu beruehren. |
| `TVCDP_PROBE_WATCHLIST_JS` | `[{name, symbols:[{symbol, exchange}]}, ...]` | Noch offen. Ansatzpunkt: `window._exposed_chartWidgetCollection` (siehe Fund unten) duerfte auch Watchlist-Widgets referenzieren, oder `Object.keys(window)` nach `watchlist`/`symbol` filtern. |
| `TVCDP_PROBE_LAYOUT_NAME_JS` | nicht-leerer String | **Zuerst ausprobieren:** `location.pathname` -- die Chart-URL enthaelt bereits eine stabile Layout-Kennung (z. B. `/chart/LAYOUT-A/`), vermutlich stabiler als DOM-Text. Alternativ Fenstertitel oder aktiver Layout-Name in der UI |
| `TVCDP_PROBE_TIMEFRAME_MINUTES_JS` | Zahl (195 erwartet) | **Bestaetigt funktionierend:** `#header-toolbar-intervals` ist eine ARIA-`radiogroup` mit einem Button je Preset (`data-value="195"`, `"1D"`, ...) und `aria-checked` am aktiven. Sichtbarer Text ("195m") existiert bei **allen** Presets gleichzeitig im DOM und zeigt nicht, welcher aktiv ist -- `aria-checked`/`data-value` abfragen, nicht Text parsen: <br>`(function(){ var v = document.querySelector('#header-toolbar-intervals [role="radio"][aria-checked="true"]').getAttribute('data-value'); return /^[0-9]+$/.test(v) ? parseInt(v, 10) : NaN; })()` |
| `TVCDP_PROBE_LAST_CLOSED_CANDLE_JS` | `{is_closed: bool, closed_timestamp: <ISO-String oder Unix-Zeit>}` | **Bestaetigt funktionierend:** <br>`(function(){ var m = window._exposed_chartWidgetCollection.activeChartWidget.value()._modelWV.value().m_model; var closeTime = m._mainSeries._lastBarCloseTime; return { is_closed: (Date.now()/1000) >= closeTime, closed_timestamp: closeTime }; })()` |
| `TVCDP_PROBE_INDICATOR_RSI_JS` / `_RSI_MA_JS` / `_EMA5_JS` / `_EMA20_JS` | Zahl | **Bestaetigt funktionierend, siehe REPORT.md Abschnitt 8 fuer die vollstaendige Herleitung.** Kurzfassung: `window._exposed_chartWidgetCollection.activeChartWidget.value()._modelWV.value().m_model._studiesWV.value()` liefert alle aktiven Studies; `study.plots()._items[items.length-1].value[N]` liefert den letzten Wert von Plot `N` (0=Zeit, 1=Hauptwert, weitere Indizes je Study -- bei RSI ist Index 3 die RSI-MA, per `study.metaInfo().styles` bestaetigt). Welche Study-Nummer welchem Indikator entspricht, ueber `study.inputs().in_0.v` (Laengenparameter) ermitteln -- **Achtung:** Study-Indizes sind pro Chart empirisch, nicht universell stabil. |
| `TVCDP_PROBE_CHANGE_SYMBOL_JS_TEMPLATE` | beliebig (Erfolg zaehlt als "kein Fehler") | Suchfeld-Interaktion simulieren; **muss** den Platzhalter `{symbol}` enthalten |

**Wichtig zu jeder gefundenen Sonde:** in REPORT.md unter Abschnitt 4
("Verwendete CDP-Methode") vermerken, **woher** der Wert stammt (DOM,
Accessibility Tree, internes JS-Objekt, WebSocket/Datenstrom, anderes) --
das beantwortet Frage E.16/E.17 der Aufgabenstellung direkt. Nach
Moeglichkeit die stabilste verfuegbare Methode waehlen; DOM-Selektoren auf
Basis obfuskierter Klassennamen gelten als hohes Wartungsrisiko (R1) und
sollten nur als letzte Option verwendet werden.

Sobald ein Ausdruck in der Konsole funktioniert, als Umgebungsvariable
setzen, z. B. (PowerShell):

```powershell
$env:TVCDP_PROBE_TIMEFRAME_MINUTES_JS = "meinGefundenerAusdruck()"
```

## 3. Watchlist-Symbole fuer den Mehrsymbol-Test angeben

```powershell
$env:TVCDP_WATCHLIST_PROBE_NAMES = "AAPL,MSFT,NVDA,TSLA,AMZN,GOOGL,META,AMD,NFLX,JPM"
```

Mindestens 10 Symbole aus einer echten Watchlist (Nutzervorgabe, Abschnitt F).

## 4. Harness ausfuehren

Einzelne Schritte (nuetzlich beim Ermitteln der Sonden):

```powershell
.venv\Scripts\tvcdp environment
.venv\Scripts\tvcdp reachability
.venv\Scripts\tvcdp target-discovery
.venv\Scripts\tvcdp session-check
.venv\Scripts\tvcdp watchlist
.venv\Scripts\tvcdp layout
.venv\Scripts\tvcdp timeframe
.venv\Scripts\tvcdp closed-candle
.venv\Scripts\tvcdp indicators
.venv\Scripts\tvcdp multi-symbol
.venv\Scripts\tvcdp error-cases
```

Vollstaendiger Durchlauf:

```powershell
.venv\Scripts\tvcdp run-all
```

Jeder Aufruf schreibt eine JSON-Logzeile pro Schritt auf die Konsole und
ein (redigiertes) Rohergebnis unter `results\<Lauf-ID>\`. Ein Exit-Code
ungleich 0 zeigt einen Fehlschlag oder ein unklares Ergebnis an
(0 = PASSED/NOT_APPLICABLE, 1 = FAILED, 2 = INCONCLUSIVE).

## 5. Referenzvergleich (Abschnitt F der Aufgabenstellung)

Fuer mindestens 10 Aktien aus echten Watchlists, fuer dieselbe vollstaendig
geschlossene 195-Minuten-Kerze:

1. `.venv\Scripts\tvcdp multi-symbol` liefert die automatisiert ausgelesenen
   Indikatorwerte (falls die Indikator-Sonden in den Mehrsymbol-Ausdruck
   integriert wurden -- sonst `indicators` nach jedem manuellen
   Symbolwechsel einzeln aufrufen).
2. Denselben Wert manuell im TradingView-UI ablesen.
3. In die Tabelle in REPORT.md Abschnitt 9 eintragen: Symbol, Candle
   Timestamp, RSI/RSI-MA/EMA5/EMA20 automatisiert vs. manuell, Abweichung.

Rundungsdifferenzen im UI nicht vorschnell als fachlichen Fehler werten
(Nutzervorgabe) -- wenn moeglich, den intern ungerundeten Wert ueber die
Sonde abrufen statt den gerundeten UI-Text zu parsen.

## 6. Manuelle Tests, die das Harness nicht selbst ausloesen kann

Fuer jeden der folgenden Tests: **vorher** `tvcdp environment` und
`tvcdp reachability` ausfuehren (Zustand protokollieren), dann die Aktion
durchfuehren, danach dieselben zwei Befehle erneut ausfuehren und beide
Ergebnisse in REPORT.md gegenueberstellen.

| Test | Durchfuehrung | Erwartete Beobachtung |
|---|---|---|
| TradingView-Neustart | TradingView schliessen, mit demselben Befehl aus Abschnitt 1 neu starten | Ist der Debug-Port erneut erreichbar, ohne manuellen Zusatzschritt? |
| Prozessabsturz | TradingView-Prozess im Task-Manager hart beenden, neu starten | Bleibt eine bestehende Sitzung erhalten (kein erneuter Login noetig)? |
| Windows-Neustart | Server neu starten | Startet TradingView automatisch mit aktiviertem CDP (siehe Autostart-Test unten), oder ist manuelles Eingreifen noetig? |
| Netzwerkunterbrechung | Netzwerkadapter kurz deaktivieren/aktivieren | Bleibt die lokale CDP-Verbindung (`127.0.0.1`) davon unberuehrt, wie erwartet? |
| Gesperrter Bildschirm | Windows-Sitzung sperren (Win+L), waehrend TradingView laeuft | Bleibt der Debug-Port waehrend der Sperre erreichbar? |
| RDP-Disconnect | Per RDP verbinden, TradingView starten, RDP-Sitzung trennen (nicht abmelden) | Bleibt TradingView aktiv und der Port erreichbar nach dem Disconnect? |
| Autostart | TradingView (mit CDP-Flag) in den Autostart-Ordner bzw. eine Aufgabenplanung eintragen, Server neu starten | Ist der Port nach dem Neustart ohne manuellen Login erreichbar? Erfordert ggf. Autologon -- separat als Sicherheitsabwaegung dokumentieren, keine Zugangsdaten in Klartext-Skripten ablegen |

Ein rein manuell im geoeffneten Desktop funktionierender Test gilt
**nicht** als Produktionsnachweis (Nutzervorgabe) -- erst der
Autostart-Test ohne interaktiv angemeldeten Nutzer beantwortet das.

## 7. Ergebnisse zurueckuebertragen

```powershell
git add spikes/tradingview-cdp/results/<Lauf-ID>/
git commit -m "Gate G2: Windows-Validierungslauf <Datum>"
git push
```

Alternativ, falls kein Git-Zugriff vom Windows-Server aus gewuenscht ist:
den Ordner `results\<Lauf-ID>\` als Zip an die Konversation mit Claude Code
uebergeben.

**Vor dem Uebertragen pruefen:** Die Redaction-Schicht des Harness entfernt
bekannte sensible Muster automatisch, ersetzt aber keine menschliche
Durchsicht bei ungewoehnlichen Sonden. Kurzer Blick in die JSON-Dateien
unter `results\<Lauf-ID>\` genuegt.

## 8. Danach

Claude Code aktualisiert REPORT.md mit den uebertragenen Ergebnissen und
spricht anschliessend die Go-/No-Go-Empfehlung aus. Keine weitere
Entwicklung (Produktivadapter, Scheduler-Integration, Sprint 1C/2) ohne
diese Empfehlung und eine gesonderte Freigabe.
