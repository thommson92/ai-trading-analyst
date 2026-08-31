# Entwicklungsrichtlinien — AI Trading Analyst

Ergänzt die globalen Regeln um das, was für dieses Projekt besonders gilt.
Grundlage: `docs/12 - CLAUDE.md` und `docs/10 - System Architecture.md`.

## Freigabe-Gates — Stand

Alle drei Gates sind entschieden. Sie sind historisch, nicht mehr sperrend:

| Gate | Gegenstand | Stand |
|---|---|---|
| **G1** | Indikator- und Signalparameter | **freigegeben** — [ADR 0010](docs/adr/0010-gate-g1-freigegeben.md), löst [ADR 0007](docs/adr/0007-gate-g1-indikatorparameter.md) ab |
| **G2** | TradingView-Spike | abgeschlossen mit `GO_WITH_LIMITATIONS` — `spikes/tradingview-cdp/REPORT.md` |
| **G3** | Produktive TradingView-Integration | **NO_GO** — [ADR 0012](docs/adr/0012-gate-g3-strang-a-no-go-non-display-nutzung.md), Non-Display-Nutzungsverbot. TradingView ist als Datenquelle erledigt |

Die technische Absicherung bleibt bestehen: `AppConfig.require_indicators()`
bricht mit `GateNotClearedError` ab, wenn der Indikatorblock fehlt. Die
Parameter stehen heute in `config/default.yaml`; der Mechanismus schützt
weiterhin gegen eine Konfiguration ohne sie.

Ebenfalls entschieden, wo dieses Dokument früher „braucht zuerst ein ADR" sagte:

- **Marktdaten:** Interactive Brokers, produktiv freigegeben —
  [ADR 0014](docs/adr/0014-ibkr-produktivintegration-freigegeben.md).
- **Earnings und Analystenratings:** Finnhub —
  [ADR 0017](docs/adr/0017-finnhub-fuer-earnings-und-ratings.md).
- **KI-Anbindung:** Anthropic API mit Modellprofilen je Aufgabe —
  [ADR 0021](docs/adr/0021-ki-anbindung-anthropic-api.md).

Was noch offen ist, steht nicht hier, sondern in `docs/adr/README.md` unter
„Offene Entscheidungen". Der Grundsatz gilt unverändert: **zu ungeklärten
Punkten werden keine Annahmen getroffen — auch keine „vorläufigen"** — und jede
Architekturentscheidung wird vor der Umsetzung als ADR festgehalten.

## Die zentrale Regel

**Technische Signale werden niemals durch KI verändert.**

Ein Sprachmodell darf erläutern, zusammenfassen, Risiken bewerten und
Empfehlungen begründen. Es darf nicht:

- Signalregeln verändern,
- fehlende Marktdaten erfinden,
- ein nicht erkanntes Signal nachträglich als erfüllt einstufen,
- deterministische Berechnungen ersetzen.

Deterministische Berechnungen und KI-Interpretation werden **getrennt
gespeichert**, nicht vermischt.

## Architektur

Vier Schichten. Der Domain Layer hängt von keiner Infrastruktur ab — kein
FastAPI, kein SQLAlchemy, kein Datenanbieter, kein KI-SDK.

`backend/tests/architecture/test_layer_boundaries.py` setzt das durch. Ein
Verstoß bricht die CI. Wird eine neue Infrastrukturbibliothek eingeführt,
gehört sie auf die Verbotsliste dieses Tests.

Weitere Regeln aus Doc 12:

- Keine Geschäftslogik im Frontend.
- Keine KI-Logik direkt in API-Endpunkten.
- Analysemodule bleiben getrennt.

## Analysemodule sind entkoppelt

Backtesting, technische Analyse, Research, Fundamentalanalyse und
Optionsanalyse laufen unabhängig voneinander. Zusammengeführt wird erst im
Scoring.

Insbesondere darf die deterministische Chartanalyse **nicht** auf eine
vorherige Web-Recherche warten. Fällt Research aus, bleiben technische Analyse
und Backtesting vollständig.

Es gibt genau **drei** gerichtete Kopplungen. Alle drei gehorchen denselben
drei Bedingungen: optionale Eingabe, nicht blockierend, keine eigene
Ableitung.

**Optionsanalyse und Support-/Resistance-Zonen:**

1. Die Optionsanalyse darf die **deterministisch ermittelten** Zonen der
   technischen Analyse als **optionale** Eingabe verwenden.
2. Die Abhängigkeit ist **nicht blockierend**. Fehlen belastbare Zonen, läuft
   die Optionsanalyse mit den übrigen Daten weiter; zonenabhängige Felder
   werden als nicht verfügbar gekennzeichnet, Datenabdeckung und Konfidenz
   sinken entsprechend. Kein Ersatzwert, keine stille Auslassung.
3. Die Optionsanalyse leitet **keine eigenen** Zonen ab, insbesondere nicht aus
   KI-Freitext.

**Fundamentalanalyse und Kurs** ([ADR 0032](docs/adr/0032-fundamentalanalyse-deterministisch.md)):

1. Die Fundamentalanalyse darf den Schlusskurs der letzten **abgeschlossenen**
   Kerze als **optionale** Eingabe für Bewertungskennzahlen verwenden.
2. Die Abhängigkeit ist **nicht blockierend**. Fehlt der Kurs, laufen die
   übrigen Kennzahlen vollständig; die bewertungsabhängigen Felder werden als
   nicht verfügbar gekennzeichnet, die Datenabdeckung sinkt entsprechend.
3. Die Fundamentalanalyse **beschafft keinen Kurs selbst** und leitet keinen
   ab.

**Optionsanalyse und Earnings-Termin** ([ADR 0048](docs/adr/0048-optionsanalyse-im-tageslauf.md)):

1. Die Optionsanalyse darf den nächsten bekannten Berichtstermin aus dem
   Earnings-Filter als **optionale** Eingabe verwenden. Liegt er vor dem
   Verfall, entsteht der Vorschlag nicht — die Prämie vergütet dann genau das
   Risiko, das ein Put-Verkäufer trägt.
2. Die Abhängigkeit ist **nicht blockierend**, und das heißt hier präzise:
   Ein **fehlender** Termin hält nichts auf. Ist keiner bekannt, entstehen
   alle Vorschläge vollständig. „Unbekannt" ist ausdrücklich nicht dasselbe
   wie „kein Termin" — ein unbekannter Termin ist kein belegter Nichttermin,
   darf aber auch nicht ausschließen. Ein **vorhandener** Termin darf sehr
   wohl wirken; die drei Bedingungen begrenzen, was fehlende Daten anrichten,
   nicht was vorhandene bedeuten.
3. Die Optionsanalyse **ermittelt keinen Termin selbst** und leitet keinen ab.
   Sie ändert insbesondere nichts an der Entscheidung des Earnings-Filters.

Der Aktienkurs ist **keine** vierte Kopplung: Er kommt aus derselben
Kerzenserie, auf der auch das Screening steht, und ist für die Optionsanalyse
zwingend — ohne ihn gibt es kein Strike-Band. Ein Kandidat ohne Kerzenserie
entsteht nicht, also fehlt er nie.

## Daten und Ergebnisse

- **Keine erfundenen Werte.** Fehlt eine Kennzahl, bleibt sie fehlend. Ohne
  belastbare Grundlage lautet das Ergebnis `INSUFFICIENT_DATA`.
- **Quellenbindung.** Aussagen über Nachrichten, Analystenmeinungen, Kursziele
  oder Fundamentaldaten verweisen auf gespeicherte Quellen mit URL,
  Veröffentlichungs- und Abrufzeitpunkt.
- **Unveränderlichkeit.** Abgeschlossene Analysen werden nicht überschrieben.
  Eine Neuberechnung erzeugt eine neue Version mit Referenz auf das Original.
- **Versionierung** an jedem Ergebnis: Signalregel-, Scoring-, Prompt-,
  Provider-, Berichtsschema- und Anwendungsversion.
- **Nur abgeschlossene Kerzen.** Eine laufende Kerze fließt nie in ein Signal
  ein.

## Backtesting

Zwei freigegebene Festlegungen, die von Doc 07 abweichen bzw. es ergänzen:

- **Einstieg** ist der Schlusskurs der Kerze, bei der die Qualifikationsregel
  erstmals erkannt wird — nicht der Close der Signalkerze.
- **Cooldown** von fünf Kerzen nach jedem gezählten Ereignis. Rohe und
  deduplizierte Stichprobengröße werden beide ausgewiesen.

**Trefferquote nach einem Horizont und dauerhaftes Halten oberhalb des
Einstiegs sind getrennte Kennzahlen.** Sie werden nirgends zu einer
gemeinsamen „Erfolgsquote" verrechnet — weder in der Datenhaltung noch im
Score noch im Berichtstext.

## Zeit und Zeitzonen

Der Scheduler rechnet in `America/New_York`. **Keine feste deutsche Uhrzeit im
Code.** Naive Zeitstempel sind untersagt; `ruff` erzwingt das über die
`DTZ`-Regeln.

Der Lauf startet *ab* Kerzenschluss und prüft mit Karenzzeit und Polling, ob
die geschlossene Kerze beim Anbieter vollständig vorliegt. Nie auf
unvollständigen Daten screenen.

## Sicherheit

- Keine API-Schlüssel oder Passwörter im Code oder in `config/default.yaml`.
  Geheimnisse ausschließlich über Umgebungsvariablen mit Präfix `ATA_`.
- Externe Research-Inhalte gelten als **nicht vertrauenswürdig**. Sie werden
  als markierte Daten übergeben, nie als Instruktion. Der Research-Kontext
  erhält keine Tool-Rechte. Scores werden nie direkt aus LLM-Freitext
  übernommen.

## KI-Anbindung

Anbieter, Modell und Modellversion sind ausschließlich konfigurierbar.
**Domain- und Application-Code dürfen von keinem konkreten Modell abhängen** —
sie kennen nur ein Modellprofil je Aufgabe, inklusive Fallback. Die verwendete
Modellversion wird an jedem Ergebnis gespeichert.

## Arbeitsweise

- Kleine Schritte, nach jedem sinnvollen Abschnitt ein Commit mit
  aussagekräftiger Nachricht.
- Vor jedem PR: Test-Suite lokal grün, unabhängige Code-Review, deren sinnvolle
  Vorschläge umgesetzt werden.
- Feature-Branches von `dev`, PR zurück nach `dev`. Nie direkt auf `main` oder
  `dev` arbeiten.
- Jede Architekturentscheidung als ADR in `docs/adr/`.
- Python mit Type Hints, `mypy --strict`. TypeScript im Strict Mode.
- Keine unnötigen Abhängigkeiten.

## Befehle

```bash
# Backend
cd backend
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src tests

# Frontend
cd frontend
npm run lint && npm run typecheck && npm run build
```

## Golden Master

`backend/tests/golden` rechnet die vollständige deterministische Kette —
Kerzenbildung, Indikatoren, 2-aus-3-Regel, Backtest-Kennzahlen — über
eingefrorene Bars und vergleicht das Ergebnis mit einer aufgezeichneten
Datei. Er läuft im gewöhnlichen `pytest`-Lauf mit, ohne Netz und ohne
Datenbank.

**Bricht ein Golden-Master-Test, ist das eine Aussage über das Verfahren.**
Entweder ist ein Fehler entstanden — dann wird er behoben —, oder die
Änderung ist gewollt. Dann, und nur dann, wird neu aufgezeichnet:

```bash
cd backend
ATA_GOLDEN_MASTER_RECORD=1 .venv/bin/python -m pytest tests/golden
```

Der Diff der `*.expected.json` gehört vor dem Commit angesehen: Er zeigt,
was die Änderung tatsächlich bewirkt hat. Eine gewollte Verfahrensänderung
zieht außerdem eine neue Versionsnummer nach sich.

Die eingefrorenen Bars sind **erzeugt, nicht gemessen** — der reale Bestand
liegt nur auf dem Server. Was daraus folgt, steht in
`tests/golden/generate_bars.py`. Ein echter Ausschnitt lässt sich mit
`cli export-bars` daneben legen; er wird ohne Codeänderung zum weiteren Fall.
