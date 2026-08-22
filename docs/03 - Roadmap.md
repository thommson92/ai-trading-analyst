# Roadmap

# Phase 1 – MVP

Ziel:

Ein vollständig nutzbarer persönlicher Trading-Assistent.

---

## Sprint 1

Projektgrundlage

- Repository erstellen
- Architektur definieren
- Datenbank einrichten
- Logging implementieren

---

## Sprint 2

Marktdaten & Screener

Marktdatenquelle ist **Interactive Brokers (TWS API)** --
[ADR 0014](adr/0014-ibkr-produktivintegration-freigegeben.md) hat die
produktive Integration freigegeben (technisch GO_WITH_LIMITATIONS,
vertraglich GO). Sprint 2 ist damit nicht mehr gegated. TradingView ist per
[ADR 0012](adr/0012-gate-g3-strang-a-no-go-non-display-nutzung.md) mit NO_GO
ausgeschieden.

- `IbkrMarketDataProvider` -- Verbindung zur TWS, historische Bars, Fehler-
  und Nichtverfügbarkeitsverhalten (akzeptierte Einschränkung E2: manueller
  Start nach Neustart)
- 195-Minuten-Kerzen verarbeiten -- Aggregation aus nativen 15-Minuten-Bars,
  ausschließlich abgeschlossene Kerzen
- Indikatorberechnung (RSI, RSI-MA, EMA5, EMA20) nach den in
  [ADR 0010](adr/0010-gate-g1-freigegeben.md) freigegebenen Parametern --
  **umgesetzt**, der IBKR-Provider rechnet sie aus den Kerzen
- Watchlisten importieren -- Quelle IBKR, nicht mehr TradingView
- historischer Backfill als resumierbarer Batch-Job mit Chunking und Pacing
  (akzeptierte Einschränkung E3) -- **umgesetzt**: `cli backfill` holt nur die
  Lücke seit dem letzten Lauf und ist über `(symbol, start)` idempotent;
  `cli screen --source stored` rechnet auf dem Bestand
- Trading-Day-Scheduler -- **umgesetzt**: `cli dispatch` entscheidet in
  `America/New_York`, holt die Lücke und rechnet, höchstens einmal je
  Handelstag ([ADR 0019](adr/0019-trading-day-dispatcher.md)). Ausgelöst von
  der Windows-Aufgabenplanung
- Earnings-Termine -- nicht über IBKR verfügbar (akzeptierte Einschränkung
  E1). **Abgeschlossen:** Auch RESC scheidet aus
  ([ADR 0016](adr/0016-ibkr-keine-quelle-fuer-research-daten.md)); Quelle für
  Termine und Analystenratings ist Finnhub
  ([ADR 0017](adr/0017-finnhub-fuer-earnings-und-ratings.md)). Die
  Implementierung des Filters gehört nach Sprint 3

---

## Sprint 3

Filter & Backtesting

- Earnings Filter -- Quelle und akzeptierte Einschränkungen stehen in
  [ADR 0017](adr/0017-finnhub-fuer-earnings-und-ratings.md); historische
  Termine für das Backtesting sind dort **nicht** abgedeckt (L9). **Umgesetzt:**
  reduziertes Statusmodell und Wochentagsnäherung für die Kerzenzählung
  nach [ADR 0020](adr/0020-earnings-filter-status-und-handelstagskalender.md),
  `FinnhubEarningsProvider` und `FixtureEarningsProvider` hinter dem
  gemeinsamen `EarningsProvider`-Port, Auswertung in `RunAnalysisUseCase`
  für jede als Kandidat eingestufte Aktie
- historische Signalprüfung
- Kennzahlenberechnung

---

## Sprint 4

KI-Analyse

- Research Agent -- **umgesetzt**, mit Quellenbindung und Kostensteuerung
  ([ADR 0022](adr/0022-research-agent-quellen.md),
  [ADR 0023](adr/0023-research-agent-zitierarchitektur.md))
- Technical Agent -- **umgesetzt**, beide Hälften des Moduls (Doc 10,
  Paragraph 6.8). Deterministisch: Trend, Volatilität über die ATR, jüngste
  Extrempunkte, Unterstützungs-/Widerstandszonen aus Swing-Pivots und das
  Chance-Risiko-Verhältnis
  ([ADR 0025](adr/0025-deterministische-chartauswertung-und-zonen.md)).
  Darauf die KI-Einordnung der sechs Punkte aus Paragraph 6.8, getrennt
  gespeichert und gegen ein festes Schema validiert
  ([ADR 0026](adr/0026-technical-agent-ki-einordnung.md)). Nachprüfbar über
  `cli technical --interpret`; der Lauf gegen echte Kurse steht noch aus
- Fundamental Agent -- Quelle entschieden (SEC EDGAR XBRL, deterministisch,
  [ADR 0022](adr/0022-research-agent-quellen.md)), noch nicht begonnen
- Report Generator

---

## Sprint 5

Optionen & Scoring

- Optionsanalyse
- Swing Score
- Investment Score

---

## Sprint 6

Dashboard & Benachrichtigung

- Webinterface
- Smartphone Push
- Analysehistorie


---

# Phase 2 – Erweiterungen

Mögliche Erweiterungen:

- Short-Strategien
- weitere Märkte
- weitere Zeitintervalle
- Portfolioanalyse
- automatische Performancebewertung
- Strategieoptimierung
- Marktregimeanalyse
- automatische Watchlist-Verbesserungen

---

# Nicht Bestandteil Phase 1

- automatische Orderausführung
- Brokerintegration
- autonome Handelsentscheidungen
- Hochfrequenzhandel