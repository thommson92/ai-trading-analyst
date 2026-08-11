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

- Marktdatenanbindung -- TradingView per [ADR 0012](adr/0012-gate-g3-strang-a-no-go-non-display-nutzung.md)
  mit NO_GO entschieden (Non-Display-Nutzungsverbot der TradingView-Nutzungsbedingungen);
  Interactive Brokers als Kandidat mit GO freigegeben, Spike unter
  `spikes/ibkr-marketdata/` gestartet, siehe [ADR 0013](adr/0013-interactive-brokers-kandidat-vorschlag.md)
- Watchlisten importieren -- Quelle abhängig vom Ausgang des IBKR-Spikes, nicht mehr TradingView
- 195-Minuten-Kerzen verarbeiten
- technische Signale implementieren

---

## Sprint 3

Filter & Backtesting

- Earnings Filter
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