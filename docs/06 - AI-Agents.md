# KI-Agenten Architektur

> **Wozu dieses Dokument.** Es beschreibt das fachliche Soll. Maßgeblich
> bei Widersprüchen ist `docs/10 - System Architecture.md`
> ([ADR 0001](adr/0001-dokumentenhierarchie.md)); was tatsächlich
> entschieden ist, steht in `docs/adr/`.
>
> **Nicht alle sieben Agenten existieren.** Gebaut sind Research Agent
> ([ADR 0022](adr/0022-research-agent-quellen.md),
> [ADR 0023](adr/0023-research-agent-zitierarchitektur.md)) und Technical
> Agent ([ADR 0026](adr/0026-technical-agent-ki-einordnung.md)). Der
> Backtesting-Agent ist **kein** KI-Agent, sondern eine deterministische
> Rechnung. Fundamental-, Options-, Scoring- und Report-Agent sind nicht
> begonnen (Sprint 4–5). Anbieter und Modellprofile regelt
> [ADR 0021](adr/0021-ki-anbindung-anthropic-api.md).

## Grundprinzip

Die KI-Komponenten sind spezialisiert.

Kein einzelner Agent führt die komplette Analyse durch.

---

# Agent 1: Research Agent

Aufgabe:

Sammelt externe Informationen.

Quellen:

- Unternehmensmeldungen
- Nachrichten
- Analystenberichte
- SEC Informationen
- Finanzdaten

Ausgabe:

Strukturierter Research-Bericht.

---

# Agent 2: Technical Analysis Agent

Aufgabe:

Bewertet technische Situation.

Analysiert:

- Trend
- Momentum
- Unterstützungen
- Widerstände
- Überverkauft/Überkauft

---

# Agent 3: Fundamental Agent

Aufgabe:

Bewertet langfristige Qualität.

Analysiert:

- Umsatzwachstum
- Gewinnentwicklung
- Margen
- Bewertung
- Verschuldung

---

# Agent 4: Backtesting Agent

Aufgabe:

Bewertet historische Signalqualität.

Ausgabe:

Statistische Kennzahlen.

---

# Agent 5: Options Agent

Aufgabe:

Bewertet Put-Selling Strategien.

Analysiert:

- Laufzeit
- Strike
- Delta
- Prämie
- Risiko

---

# Agent 6: Scoring Agent

Aufgabe:

Führt alle Ergebnisse zusammen.

Erstellt:

- Swing Score
- Investment Score

---

# Agent 7: Report Agent

Aufgabe:

Erstellt finale Nutzeransicht.

Ausgabe:

- Dashboard Bericht
- Smartphone Zusammenfassung