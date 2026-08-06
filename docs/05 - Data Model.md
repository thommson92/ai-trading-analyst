# Datenmodell

## Grundprinzip

Alle Analysen werden revisionssicher gespeichert.

Historische Daten dürfen nicht überschrieben werden.

---

# Entity: Stock

Beschreibung:

Stammdaten einer Aktie.

Felder:

- id
- symbol
- exchange
- company_name
- sector
- industry
- currency

---

# Entity: Watchlist

Beschreibung:

TradingView Watchlisten.

Felder:

- id
- name
- tradingview_identifier
- last_sync

Relation:

Watchlist -> Stock

---

# Entity: Candle

Beschreibung:

Historische Kurskerzen.

Felder:

- id
- stock_id
- timestamp
- timeframe
- open
- high
- low
- close
- volume

---

# Entity: TechnicalSignal

Beschreibung:

Einzelne erkannte Signale.

Felder:

- id
- stock_id
- analysis_id
- signal_type
- detected_at
- candle_timestamp
- value

Signaltypen:

- RSI_CROSS
- PRICE_EMA20_BREAKOUT
- EMA5_EMA20_CROSS

---

# Entity: AnalysisRun

Beschreibung:

Ein täglicher Analysezyklus.

Felder:

- id
- started_at
- completed_at
- status
- number_of_stocks
- candidates_found

---

# Entity: StockAnalysis

Beschreibung:

Kompletter Analysebericht einer Aktie.

Felder:

- id
- analysis_run_id
- stock_id
- swing_score
- investment_score
- recommendation
- summary
- created_at

---

# Entity: BacktestResult

Felder:

- id
- stock_id
- signal_configuration
- period_start
- period_end
- sample_size
- win_rate
- avg_return
- median_return
- max_drawdown

---

# Entity: ResearchReport

Felder:

- id
- stock_analysis_id
- news_summary
- analyst_summary
- fundamental_summary
- risks
- opportunities

---

# Entity: OptionStrategy

Felder:

- id
- stock_analysis_id
- expiration_date
- strike
- delta
- premium
- annualized_return
- assignment_probability

---

# Entity: Notification

Felder:

- id
- analysis_id
- sent_at
- channel
- status