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
  bisher liefert nur der Fixture-Provider fertige Indikatorwerte
- Watchlisten importieren -- Quelle IBKR, nicht mehr TradingView
- historischer Backfill als resumierbarer Batch-Job mit Chunking und Pacing
  (akzeptierte Einschränkung E3)
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
  Termine für das Backtesting sind dort **nicht** abgedeckt (L9)
- historische Signalprüfung
- Kennzahlenberechnung

---

## Sprint 4

KI-Analyse

- Research Agent
- Technical Agent
- Fundamental Agent
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