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
  `cli technical --interpret`. An echten Kursen verifiziert (PR #35); die
  dabei gefundenen Abweichungen sind in ADR 0026 festgehalten und haben den
  Prompt auf v3 gehoben
- Fundamental Agent -- **deterministische Hälfte umgesetzt**
  ([ADR 0032](adr/0032-fundamentalanalyse-deterministisch.md)): Kennzahlen aus
  den SEC-Einreichungen über `data.sec.gov`, ohne Sprachmodell im
  Beschaffungspfad ([ADR 0022](adr/0022-research-agent-quellen.md)). Acht der
  fünfzehn Analysebereiche aus Doc 10, Paragraph 6.9 sind gerechnet, die
  Bewertung kommt hinzu, sobald ein Kurs hineingereicht wird -- als optionale,
  nicht blockierende Eingabe (CLAUDE.md, zweite gerichtete Kopplung).
  Niveauzahlen und Bewertung stehen auf den **letzten zwölf Monaten**, die
  Wachstumsraten auf Geschäftsjahren
  ([ADR 0033](adr/0033-zwoelfmonatswerte-statt-jahresabschluss.md)).
  Nachprüfbar über `cli fundamental`, an sieben echten Emittenten verifiziert;
  die dabei gefundenen vier Fehler stehen im Nachtrag zu ADR 0032. Der erste
  Lauf über die **volle Watchliste** (192 Aktien) hat drei weitere Befunde
  ergeben — darunter ein fünfzehn Jahre alter Jahresüberschuss, der als
  aktuell galt; sie sind in
  [ADR 0034](adr/0034-fundamentaldaten-nach-dem-watchlist-lauf.md) entschieden
  und heben das Verfahren auf `fundamental-v3`. Die KI-Einordnung folgt
  getrennt. **Im Tageslauf angeschlossen**
  ([ADR 0035](adr/0035-fundamentaldaten-im-tageslauf.md)): Kennzahlen
  entstehen für jeden Kandidaten, der Kurs ist der Schluss der letzten
  abgeschlossenen Kerze, und jeder Lauf speichert seinen eigenen,
  unveränderlichen Satz
- Report Generator -- **deterministische Haelfte umgesetzt**
  ([ADR 0039](adr/0039-report-generator.md)): Er fuehrt alle achtzehn
  Pflichtpunkte aus Doc 10, Paragraph 6.12 -- auch die vier, die auf
  Optionsanalyse und Scoring stehen und damit zu Sprint 5 gehoeren. Sie
  erscheinen als Abschnitt mit Begruendung, nicht als fehlender Schluessel.
  Unterschieden wird dabei, ob ein Punkt fehlt oder nur unter Vorbehalt gilt.
  Das JSON-Dokument ist die verbindliche, unveraenderlich gespeicherte
  Fassung; daraus entstehen die lesbare Ausgabe ueber `cli report` und die
  Kurzfassung fuer den Benachrichtigungskanal
  ([ADR 0040](adr/0040-inhalt-der-ergebnismeldung.md): Symbole und
  Signaltypen ja, Kurse und Kennzahlen nein). Die KI-Formulierung folgt
  getrennt, nach dem Muster von ADR 0026
- Backtest im Tageslauf -- **umgesetzt**
  ([ADR 0038](adr/0038-backtest-im-tageslauf.md)): Die historische
  Signalstatistik entsteht je Kandidat auf der ohnehin geladenen
  Kerzenserie, ohne zusaetzlichen Abruf. Sie fuellt Berichtspunkt 5 und ist
  die Grundlage, die das Scoring in Sprint 5 braucht. Dass der Replay keine
  Ereignisse nahe Berichtsterminen ausschliesst (ADR 0017, L9), steht am
  Ergebnis und im Bericht

**Getrennt folgend, beide nach dem Muster von ADR 0026** (deterministische
Haelfte zuerst, KI-Einordnung getrennt gespeichert und gegen ein Schema
validiert): die KI-Haelfte der Fundamentalanalyse und die des Report
Generators. Beide Modellprofile stehen konfiguriert bereit.

---

## Sprint 5

Optionen & Scoring

- **Scoring Engine** — **umgesetzt** (PR #58): sechs Komponenten für den
  Swing-Score, vier für den Investment-Score
  ([ADR 0041](adr/0041-score-komponenten-und-gewichte.md)). Fehlende
  Komponenten werden umgewichtet; unterhalb von 60 % Abdeckung entsteht
  `INSUFFICIENT_DATA`. Die Schwellen sind an der vollen Watchliste
  **gemessen**, nicht gesetzt
  ([ADR 0045](adr/0045-schwellen-der-score-teilwerte.md))
- **Empfehlung** (Berichtspunkt 16) — **umgesetzt** (PR #59): Der Swing-Score
  führt, der Investment-Score korrigiert um höchstens eine Stufe,
  begrenzende Risiken deckeln
  ([ADR 0046](adr/0046-empfehlungsstufe-aus-beiden-scores.md)); beide Scores
  und die Stufe gehen in die Ergebnismeldung
  ([ADR 0047](adr/0047-scores-in-der-ergebnismeldung.md))
- **Optionsanalyse** — **umgesetzt** (PR #60): Cash Secured Puts über die
  IBKR-Optionskette, ein Verfallstermin je Kandidat, drei Vorschläge nach
  annualisierter Prämienrendite; der Berichtstermin schließt Verfälle danach
  aus — die dritte gerichtete Kopplung
  ([ADR 0048](adr/0048-optionsanalyse-im-tageslauf.md)). Der Tageslauf fällt
  in den offenen Markt (12:50 New Yorker Zeit)
- **Optionsattraktivität in den Swing-Score** — **umgesetzt** (PR #60): die
  sechste Komponente, `swing_version` 1.2, Schwellen aus dem Messlauf vom
  2026-08-31 (ADR 0048)

Vorbereitet in Stufe 0: ADR 0041 bis 0043, Doc 09 neu geschrieben, und die
Analystenempfehlungen, die ADR 0017 mitentschied und die nie gebaut wurden.

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