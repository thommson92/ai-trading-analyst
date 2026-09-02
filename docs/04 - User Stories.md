# User Stories & Akzeptanzkriterien

> **Wozu dieses Dokument.** Es beschreibt das fachliche Soll. Maßgeblich
> bei Widersprüchen ist `docs/10 - System Architecture.md`
> ([ADR 0001](adr/0001-dokumentenhierarchie.md)); was tatsächlich
> entschieden ist, steht in `docs/adr/`.
>
> **Das US-007-Kriterium „relevante Chartmuster" ist gestrichen**
> ([ADR 0050](adr/0050-us-007-chartmuster-gestrichen.md)): ohne
> deterministische Mustererkennung wäre jede von der KI benannte Formation
> eine Erfindung ([ADR 0026](adr/0026-technical-agent-ki-einordnung.md)).
> Eine Wiedereinführung begänne mit einer deterministischen Grundlage,
> nicht mit einem Prompt.

## 1. Übersicht

Dieses Dokument beschreibt die fachlichen Anforderungen aus Nutzersicht.

Jede Funktion wird durch eine User Story und überprüfbare Akzeptanzkriterien definiert.

---

# Epic 1: Automatische Marktanalyse

## US-001 Automatischer Analysebeginn

### Beschreibung

Als Nutzer möchte ich, dass das System jeden Handelstag automatisch startet, damit ich keine manuelle Analyse durchführen muss.

### Akzeptanzkriterien

- Das System startet automatisch nach Abschluss der ersten regulären 195-Minuten-Kerze.
- Die Startzeit berücksichtigt US-Sommerzeit und europäische Zeitzonen.
- Es werden ausschließlich abgeschlossene Kerzen verwendet.
- Bei Feiertagen oder Börsenschließungen erfolgt keine Analyse.

---

# Epic 2: Watchlistenverwaltung

## US-002 TradingView Watchlisten laden

### Beschreibung

Als Nutzer möchte ich meine bestehenden TradingView-Watchlisten verwenden, damit ich keine Aktien manuell pflegen muss.

### Akzeptanzkriterien

- Das System kann definierte Watchlisten abrufen.
- Jede Aktie wird eindeutig über Symbol und Börsenplatz identifiziert.
- Änderungen in TradingView werden übernommen.
- Fehlerhafte Symbole werden protokolliert.

---

# Epic 3: Technischer Screener

## US-003 Technische Signale prüfen

### Beschreibung

Als Nutzer möchte ich meine definierten Kaufsignale automatisch prüfen lassen.

### Akzeptanzkriterien

Für jede Aktie werden geprüft:

Signal A:
RSI kreuzt RSI-Moving-Average von unten nach oben.

Signal B:
Preis durchbricht EMA20 von unten und schließt darüber.

Signal C:
EMA5 kreuzt EMA20 von unten und schließt darüber.

---

## US-004 Kandidaten auswählen

### Beschreibung

Als Nutzer möchte ich nur hochwertige Kandidaten analysieren lassen.

### Akzeptanzkriterien

Eine Aktie qualifiziert sich, wenn:

- mindestens drei von fünf Kriterien erfüllt sind (ADR 0056)
- Signale aktuell oder innerhalb der letzten fünf abgeschlossenen Kerzen aufgetreten sind
- kein Ausschluss durch Earnings Filter erfolgt

---

# Epic 4: Historische Bewertung

## US-005 Signalqualität analysieren

### Beschreibung

Als Nutzer möchte ich wissen, wie erfolgreich dieses Signal historisch war.

### Akzeptanzkriterien

Das System analysiert:

- identische Signalkombinationen
- letzte fünf Jahre
- gleiche Aktie

Es berechnet:

- Trefferquote
- durchschnittliche Rendite
- Medianrendite
- maximale Verluste
- Performance nach 10 und 20 Kerzen

---

# Epic 5: KI Aktienanalyse

## US-006 Unternehmensanalyse erzeugen

### Beschreibung

Als Nutzer möchte ich eine umfassende Analyse erhalten.

### Akzeptanzkriterien

Der Bericht enthält:

- Unternehmensübersicht
- aktuelle Nachrichten
- Analystenmeinungen
- Kursziele
- Risiken
- Chancen
- Fundamentaldaten

---

# Epic 6: Chartanalyse

## US-007 Technische Bewertung erhalten

### Beschreibung

Als Nutzer möchte ich eine professionelle Chartbewertung erhalten.

### Akzeptanzkriterien

Der Bericht enthält:

- Trendbewertung
- Momentum
- RSI-Situation
- Unterstützungen
- Widerstände
- ~~relevante Chartmuster~~ — gestrichen
  ([ADR 0050](adr/0050-us-007-chartmuster-gestrichen.md)); Wiedereinführung
  nur als spätere Ausbaustufe mit deterministischer Mustererkennung

---

# Epic 7: Optionsanalyse

## US-008 Put-Selling Möglichkeiten bewerten

### Beschreibung

Als Nutzer möchte ich alternative Einstiegsstrategien über Optionen erhalten.

### Akzeptanzkriterien

Das System analysiert:

- passende Laufzeiten
- mögliche Strikes
- Delta
- Prämien
- Rendite
- Risiko

---

# Epic 8: Bewertung

## US-009 Aktie bewerten

### Beschreibung

Als Nutzer möchte ich eine klare Einschätzung erhalten.

### Akzeptanzkriterien

Es werden zwei getrennte Bewertungen erzeugt:

Swing Trade Score

und

Long-Term Investment Score

---

# Epic 9: Historie

## US-010 Analysen speichern

### Beschreibung

Als Nutzer möchte ich vergangene Analysen nachvollziehen können.

### Akzeptanzkriterien

Gespeichert werden:

- Analysezeitpunkt
- Eingangsdaten
- Ergebnisse
- Scores
- Empfehlungen
- spätere Kursentwicklung