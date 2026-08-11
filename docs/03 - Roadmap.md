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
  `spikes/ibkr-marketdata/` abgeschlossen mit GO_WITH_LIMITATIONS (technische
  Ebene), siehe [ADR 0013](adr/0013-interactive-brokers-kandidat-vorschlag.md)
  -- produktive Integration (`IbkrMarketDataProvider`) bleibt bis zur
  gesonderten Freigabe von Schritt 4 gesperrt
- Watchlisten importieren -- Quelle IBKR (vorbehaltlich Schritt-4-Freigabe), nicht mehr TradingView
- Earnings-Termine -- nicht über IBKR verfügbar (ADR 0013), separater Anbieter noch zu evaluieren (F9)
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