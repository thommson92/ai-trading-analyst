# Gate G2 -- TradingView Desktop/CDP Spike

Technischer Spike zur Frage, ob die bestehende TradingView-Desktop-Umgebung
zuverlaessig als Quelle fuer Watchlists, Chartlayout und Indikatorwerte
verwendet werden kann. **Kein Produktivcode.** Siehe
[REPORT.md](REPORT.md) fuer den Stand und die Go-/No-Go-Empfehlung,
[WINDOWS_VALIDATION.md](WINDOWS_VALIDATION.md) fuer die Anleitung zur
Validierung auf dem Windows-Zielserver.

## Status: eingefroren (Stand 2026-08-12)

Der Spike ist abgeschlossen. Technisch lautete die Empfehlung
`GO_WITH_LIMITATIONS` -- **produktiv genutzt wird er trotzdem nicht**: Gate
G3 steht auf `NO_GO`, weil die Nutzungsbedingungen von TradingView die
nicht-anzeigende Weiterverarbeitung der Daten untersagen. Die Entscheidung
steht in
[ADR 0012](../../docs/adr/0012-gate-g3-strang-a-no-go-non-display-nutzung.md),
die Marktdaten kommen stattdessen von Interactive Brokers
([ADR 0014](../../docs/adr/0014-ibkr-produktivintegration-freigegeben.md)).

Der Spike liegt hier als **Nachweisartefakt**: Er ist die Beweisgrundlage
dafuer, dass die Absage an TradingView eine vertragliche und keine
technische war. Aufbewahrt wird er unter denselben Bedingungen wie der
IBKR-Spike:

- Er wird **nicht weitergepflegt**. Gate G3 wird durch neue Erkenntnisse
  hier nicht wieder geoeffnet; das braeuchte ein neues ADR.
- Er wird **nicht von der CI geprueft** (die CI laeuft ausschliesslich in
  `backend/` und `frontend/`). Die eingecheckten Tests sind manuell
  ausfuehrbar, siehe Abschnitt "Tests".
- Er wird **nicht in den Produktivcode importiert** und importiert selbst
  nichts aus `backend/` oder `frontend/`.

**Eine Aenderung gegenueber dem Arbeitsbranch:** In `REPORT.md`,
`WINDOWS_VALIDATION.md` und `tests/test_config.py` standen die
Layout-Kennungen der real verwendeten TradingView-Charts des
Projektinhabers (achtstellige IDs aus der Chart-URL). Dieses Repository ist
oeffentlich, und die Kennungen sind umgebungsbezogene Angaben ohne
Beweiswert -- sie sind durch `LAYOUT-A`, `LAYOUT-B` bzw. eine erfundene ID
ersetzt. Der belegte Befund bleibt davon unberuehrt: `location.pathname`
liefert eine stabile, von TradingView selbst vergebene Layout-Kennung.

## Sicherheitsgrenzen (nicht verhandelbar)

- Keine Zugangsdaten, Session-Cookies oder Tokens werden ausgelesen,
  gespeichert oder geloggt -- weder in Fixtures noch in Ergebnisdateien
  noch in Logs. Jede Persistenz- und Logging-Stelle laeuft durch
  `src/tvcdp/redaction.py`.
- Kein Import aus und kein Import in `backend/src` oder `frontend`. Der
  gesamte Spike-Code bleibt unter `spikes/tradingview-cdp/`.
- Keine Windows-Annahmen im Kern -- alle Verbindungsparameter sind ueber
  Umgebungsvariablen konfigurierbar, keine TradingView-spezifischen
  DOM-Selektoren oder internen Objektpfade sind fest im Code verdrahtet
  (siehe `src/tvcdp/probe_config.py`).

## Architektur

```
src/tvcdp/
  cdp_client.py       Minimaler CDP-Client (Zielliste, WebSocket, Runtime.evaluate)
  config.py            CdpConfig/SpikeConfig aus Umgebungsvariablen
  probe_config.py       TradingView-spezifische Sonden (nur konfigurierbar, keine Defaults)
  redaction.py           Entfernt sensible Daten vor Logging/Persistenz
  diagnostics.py          Plattformunabhaengige Umgebungserkennung
  logging_setup.py         Strukturiertes JSON-Logging
  results_store.py          Rohergebnisse als Dateien unter results/
  orchestration.py           Zielerkennung + Session-Aufbau (gemeinsam genutzt)
  steps/                      Ein Modul je Testschritt (A-I der Aufgabenstellung)
  cli.py                       Kommandozeile: jeder Schritt einzeln, plus run-all
```

## Nutzung (macOS/Entwicklung)

```bash
cd spikes/tradingview-cdp
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/tvcdp --help
```

Ohne echtes TradingView-Ziel liefert jeder Sonden-abhaengige Schritt ehrlich
`INCONCLUSIVE` statt eines erfundenen Ergebnisses. Fuer eine echte
Protokollpruefung waehrend der Entwicklung kann testweise ein beliebiger
Chromium-Prozess mit `--remote-debugging-port` als Ziel dienen (siehe
REPORT.md, Abschnitt "Aus Phase A gelernt") -- das ist ausdruecklich nur ein
Entwicklungs- und Explorationsnachweis, kein Ersatz fuer Phase B.

## Nutzung (Windows-Zielserver)

Siehe [WINDOWS_VALIDATION.md](WINDOWS_VALIDATION.md).

## Tests

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src tests
```
