# API Design

## Grundprinzip

REST API zwischen Frontend und Backend.

---

# Analyse

GET

/api/analyses


Antwort:

Liste aller aktuellen Analysen


---

# Detailanalyse

GET

/api/analysis/{id}


liefert:

- technische Signale
- Scores
- Research
- Optionen
- Bericht

---

# Aktien

GET

/api/stocks


---

# Backtesting

GET

/api/backtest/{symbol}


---

# Dashboard

GET

/api/dashboard


liefert:

- heutige Kandidaten
- Scores
- Performance

---

# Trigger Analyse

POST

/api/run-analysis


Nur Administrator.
