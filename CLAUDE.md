# Entwicklungsrichtlinien — AI Trading Analyst

Ergänzt die globalen Regeln um das, was für dieses Projekt besonders gilt.
Grundlage: `docs/12 - CLAUDE.md` und `docs/10 - System Architecture.md`.

## Freigabe-Gates

Drei Punkte sind gesperrt. Hier wird nicht weitergearbeitet, bevor eine
ausdrückliche Freigabe des Nutzers vorliegt:

| Gate | Gesperrt ist | Freigabe durch |
|---|---|---|
| **G1** | Implementierung der Signalformeln | Klärung von RSI- und EMA-Parametern am realen TradingView-Layout |
| **G2** | Start des TradingView-Spikes | Gesonderte Freigabe |
| **G3** | Produktive TradingView-Integration | Entscheidung nach Vorlage des Spike-Testberichts |

Zu G1 gehören: RSI-Länge und -Berechnungsmethode, Länge und Typ des
RSI-Moving-Average, die mathematische Definition des EMA20-Kursdurchbruchs und
die Schlussbedingung beim EMA5/EMA20-Crossover.

**Zu diesen Punkten werden keine Annahmen getroffen — auch keine
„vorläufigen".** Technisch abgesichert über `AppConfig.require_indicators()`,
das ohne Freigabe mit `GateNotClearedError` abbricht. Siehe
[ADR 0007](docs/adr/0007-gate-g1-indikatorparameter.md).

Ebenfalls noch nicht zu beginnen: produktive Datenprovider und die
KI-Integration. Beide brauchen zuerst ein ADR.

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

Einzige gerichtete Kopplung — Optionsanalyse und Support-/Resistance-Zonen:

1. Die Optionsanalyse darf die **deterministisch ermittelten** Zonen der
   technischen Analyse als **optionale** Eingabe verwenden.
2. Die Abhängigkeit ist **nicht blockierend**. Fehlen belastbare Zonen, läuft
   die Optionsanalyse mit den übrigen Daten weiter; zonenabhängige Felder
   werden als nicht verfügbar gekennzeichnet, Datenabdeckung und Konfidenz
   sinken entsprechend. Kein Ersatzwert, keine stille Auslassung.
3. Die Optionsanalyse leitet **keine eigenen** Zonen ab, insbesondere nicht aus
   KI-Freitext.

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
