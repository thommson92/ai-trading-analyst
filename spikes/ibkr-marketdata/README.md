# Interactive Brokers Marktdaten-Spike

Technischer Spike zur Frage, ob Interactive Brokers (IBKR) über die
offizielle API zuverlässig als Quelle für Watchlist-Kurse,
Indikatorberechnung und historische Kurse dienen kann, nachdem TradingView
als Datenquelle mit NO_GO ausgeschieden ist (siehe
[ADR 0012](../../docs/adr/0012-gate-g3-strang-a-no-go-non-display-nutzung.md)).
**Kein Produktivcode.** Freigegeben durch den Projektinhaber am 2026-08-11,
siehe [ADR 0013](../../docs/adr/0013-interactive-brokers-kandidat-vorschlag.md).

## Status: eingefroren (Stand 2026-08-11)

Der Spike ist abgeschlossen ([REPORT.md](REPORT.md), Empfehlung
`GO_WITH_LIMITATIONS`) und wurde anschliessend aus dem Arbeitsbranch
`spike/ibkr-marketdata` unveraendert nach `dev` uebernommen -- als
**eingefrorenes Nachweis- und Reproduktionsartefakt**, nicht als
weiterzuentwickelnder Code:

- Er wird **nicht weitergepflegt**. Neue Erkenntnisse gehoeren in den
  produktiven Adapter bzw. in ein ADR, nicht hierher.
- Er wird **nicht von der CI geprueft** (die CI laeuft ausschliesslich in
  `backend/` und `frontend/`). Die hier eingecheckten Tests sind manuell
  ausfuehrbar, siehe Abschnitt "Tests".
- Er wird **nicht in den Produktivcode importiert** und importiert selbst
  nichts aus `backend/` oder `frontend/`. Die produktive Anbindung
  ([ADR 0014](../../docs/adr/0014-ibkr-produktivintegration-freigegeben.md))
  ist eine **Neuimplementierung** unter `backend/src/`, die diesen Spike nur
  als Referenz nutzt -- kein kopierter Code.

Was bei der Uebernahme bewusst **nicht** mitgenommen wurde:

- Ergebnisdateien unter `results/` (`.gitignore` schliesst `results/*.json`
  aus). Die relevanten Ergebnisse stehen redigiert und zitierfaehig in
  REPORT.md; die lokal vorhandene Datei `20260811T134109Z_connectivity.json`
  wurde vor dieser Entscheidung geprueft und enthielt lediglich einen
  fehlgeschlagenen Verbindungsversuch auf `127.0.0.1:7497` ohne Konto-,
  Vertrags- oder Umgebungsbezug.
- Build- und Cache-Artefakte (`__pycache__/`, `*.egg-info/`, `.venv/`).

### Was hiervon als Referenz fuer die Produktivintegration dient

| Datei | Rolle nach dem Spike |
|---|---|
| `src/ibkrspike/timeframe.py` | Referenz fuer die 195-Minuten-Aggregation (Bucketbildung ab Sitzungseroeffnung, Vollstaendigkeitspruefung ueber die Bar-Anzahl) |
| `src/ibkrspike/ibkr_client.py` | Referenz fuer Verbindungsaufbau, Event-Loop-Absicherung ab Python 3.14 und Datenminimierung gegenueber `ib_async` |
| `src/ibkrspike/redaction.py` | Referenz fuer die Maskierung von Konto-Kennungen vor Logging/Persistenz |
| `src/ibkrspike/steps/step_historical_coverage.py`, `step_supplementary_data.py` | reine Einmal-Sonden (Pacing, F9-Zusatzdaten) -- ausschliesslich zur Reproduzierbarkeit des Berichts aufbewahrt, keine Vorlage fuer Produktivcode |

## Sicherheitsgrenzen (nicht verhandelbar)

- Keine Zugangsdaten, Tokens oder API-Keys werden ausgelesen, gespeichert
  oder geloggt. Verbindungsparameter (Host, Port, Client-ID) sind
  ausschließlich über Umgebungsvariablen konfigurierbar.
- Account-Kennungen (z. B. `U1234567`) gelten als sensibel und werden vor
  Logging/Persistenz maskiert (`src/ibkrspike/redaction.py`) -- auch wenn es
  keine Geheimnisse im engeren Sinne sind, werden sie nicht im Klartext in
  Ergebnisdateien oder Logs abgelegt.
- Kein Import aus und kein Import in `backend/src` oder `frontend`. Der
  gesamte Spike-Code bleibt unter `spikes/ibkr-marketdata/`.
- Es werden ausschließlich Lesezugriffe (Marktdaten, Kontoinformationen)
  getestet. Keine Order-Erstellung, keine Order-Ausführung -- das ist auch
  langfristig nicht Teil dieses Projekts (siehe Doc 01, "Mensch
  entscheidet"). Diese Beschränkung ist im Code verankert (kein Aufruf
  einer ordererzeugenden Methode in `ibkr_client.py`), nicht über den
  TWS-weiten "Read-Only API"-Schalter -- der würde auch andere,
  ordererzeugende Anwendungen an derselben TWS-Instanz blockieren (siehe
  REPORT.md, Frage 8).
- Die eigene `IBKRSPIKE_CLIENT_ID` muss sich von der Client-ID jeder
  anderen Anwendung unterscheiden, die dieselbe TWS-Instanz nutzt (siehe
  REPORT.md, Frage 8) -- keine Änderung an fremden Anwendungen oder deren
  TWS-Konfiguration.

## Offene technische Fragen (Schritt 3 aus ADR 0013)

Dieser Spike klärt, in aufsteigender Reihenfolge des Risikos:

1. **Verbindungsaufbau.** TWS Desktop vs. IB Gateway als Zugriffspunkt; Host/
   Port/Client-ID-Konfiguration; verlässliche Erkennung von
   Verbindungsstatus und -abbruch.
2. **Unbeaufsichtigter Neustart.** IB Gateway (headless-fähig) plus IBC
   (Interactive Brokers Controller) zur Automatisierung des
   Anmeldevorgangs -- adressiert das bei TradingView ungelöste Risiko R2.
3. **Marktdatenauflösung.** Verfügbare native Bar-Größen; ob/wie eine
   195-Minuten-Kerze aus kleineren Bars (z. B. 5/15 Minuten) sauber
   aggregiert werden kann, analog zur ursprünglich für R3 geplanten
   Aggregation.
4. **Historische Abdeckung.** Tatsächlich verfügbare Historientiefe für die
   geplanten Watchlist-Symbole; Rate-Limits/Pacing-Beschränkungen der API
   (siehe Market Data API Supplement, ADR 0013).
5. **Abgeschlossene vs. laufende Kerze.** Zuverlässige Unterscheidung, wie
   bei TradingView (Doc 10: "nur abgeschlossene Kerzen").
6. **Zusatzdaten (F9).** Ob IBKR auch Earnings-Termine, Fundamentaldaten
   oder Optionsketten mit Greeks liefert, oder ob dafür weiterhin separate
   Anbieter nötig sind.
7. **Mehrsymbol-Durchlauf.** Laufzeit, Fehlerrate und Stabilität über die
   gesamte Watchlist, analog zum Referenzvergleich aus Gate G2.

Ergebnisse werden fortlaufend in [REPORT.md](REPORT.md) nachgetragen.

## Architektur

```
src/ibkrspike/
  config.py            IbkrSpikeConfig aus Umgebungsvariablen (kein Default fuer Port/Client-ID)
  redaction.py           Maskiert Account-Kennungen vor Logging/Persistenz
  logging_setup.py         Strukturiertes JSON-Logging
  results_store.py           Rohergebnisse (redigiert) als Dateien unter results/
  ibkr_client.py               Adapter um ib_async.IB (Verbindung, Kontrakte, historische Bars)
  timeframe.py                   Reine 195-Minuten-Aggregationslogik (kein IB-Zugriff)
  steps/
    base.py                          StepStatus (OK/FAILED/INCONCLUSIVE)
    step_connectivity.py              Schritt 1: Verbindungsaufbau, Account-/Serverinfo
    step_historical_bars.py            Schritt 3: historische Bars + 195-Minuten-Aggregation
    step_historical_coverage.py          Schritt 4: Historientiefe und Pacing-Verhalten
    step_supplementary_data.py             Schritt 6: Earnings/Analystenschaetzungen/Optionsketten mit Greeks
    step_multi_symbol.py                     Schritt 7: Mehrsymbol-Durchlauf, Laufzeit/Fehlerrate
  cli.py                                Kommandozeile: ein Befehl je Schritt
```

Jeder Schritt ist über ein injizierbares Client-Interface getestet (kein
echtes IB-Gateway in den Unit-Tests nötig). Ein Schritt ohne erreichbare
Gegenstelle meldet ehrlich `FAILED` mit Fehlermeldung statt eines
erfundenen Ergebnisses.

## Nutzung

```bash
cd spikes/ibkr-marketdata
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

export IBKRSPIKE_HOST=127.0.0.1
export IBKRSPIKE_PORT=7497   # TWS Paper Trading Default -- siehe REPORT.md fuer die tatsaechlich genutzte Konfiguration
export IBKRSPIKE_CLIENT_ID=17

.venv/bin/ibkrspike connectivity
.venv/bin/ibkrspike historical-bars --symbol AAPL --duration "5 D" --bar-size "15 mins"
.venv/bin/ibkrspike historical-coverage --symbol AAPL --bar-size "15 mins"
.venv/bin/ibkrspike supplementary-data --symbol AAPL
.venv/bin/ibkrspike multi-symbol --symbols "AAPL,MSFT,AMZN" --duration "5 D" --bar-size "15 mins"
```

`supplementary-data` prueft Earnings-Kalender, Analystenschaetzungen (beide
ueber `reqFundamentalData`, benoetigt ein separates Reuters-Fundamentaldaten-
Abo) und Optionsketten mit modellierten Greeks (`reqSecDefOptParams` +
`reqTickers`, benoetigt eine separate Optionsmarktdaten-Berechtigung). Fehlt
eine dieser Berechtigungen, meldet der jeweilige Teil ehrlich
`inconclusive` statt eines erfundenen Ergebnisses -- die anderen Teile laufen
unabhaengig davon weiter.

`multi-symbol` verbindet sich **einmal** und durchlaeuft dann alle Symbole
nacheinander (Standard: 10 Referenzaktien wie beim Gate-G2-Vergleich) --
realistischer fuer einen produktiven Watchlist-Lauf als eine Verbindung pro
Symbol.

Voraussetzung: TWS oder IB Gateway läuft lokal bzw. netzwerkerreichbar,
und "Enable ActiveX and Socket Clients" ist in den API-Einstellungen
aktiviert.

**"Read-Only API" NICHT pauschal aktivieren, falls dieselbe TWS-Instanz
von einer anderen, ordererzeugenden Anwendung mitgenutzt wird** -- dieser
Schalter gilt für die gesamte TWS-Instanz, nicht pro Client-ID, und würde
auch die andere Anwendung an echten Order-Übermittlungen hindern (siehe
REPORT.md, Frage 8, "Korrekturpunkt zu Read-Only API"). Die
Lesebeschränkung dieses Spikes ist stattdessen im eigenen Code verankert
(`ibkr_client.py` ruft ausschließlich lesende Methoden auf).

## Tests

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src tests
```
