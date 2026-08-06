# Product Requirements Document (PRD)

## 1. Produktbeschreibung

Der AI Trading Analyst ist eine Webanwendung, welche täglich automatisch Aktien analysiert und potenzielle Handelsmöglichkeiten identifiziert.

Die Anwendung läuft auf einem privaten Windows-Server.

---

# 2. Hauptfunktionalitäten

## 2.1 Automatische Analyse

Das System führt automatisch einmal täglich eine Analyse aus.

Zeitpunkt:

Nach Abschluss der ersten regulären 195-Minuten-Kerze des US-Handelstages.

Zeitpunkt:

12:45 ET

Entsprechend:

- 18:45 MESZ
- 17:45 MEZ

---

# 2.2 Datenquelle

Primäre Marktdatenquelle:

TradingView

Die Anwendung soll TradingView verwenden für:

- Watchlisten
- Kursdaten
- technische Indikatoren

Falls einzelne Daten nicht verfügbar sind, dürfen kompatible Ersatzdatenquellen verwendet werden.

---

# 2.3 Technischer Screener

Der Screener analysiert jede Aktie aus den definierten Watchlisten.

Aktuell definierte Kaufsignale:

## Signal 1

RSI kreuzt seinen gleitenden Durchschnitt von unten nach oben.

---

## Signal 2

Der Kurs durchdringt EMA20 von unten nach oben und schließt die Kerze oberhalb EMA20.

---

## Signal 3

EMA5 kreuzt EMA20 von unten nach oben und schließt darüber.

---

## Qualifikation

Eine Aktie wird weiter analysiert, wenn:

Mindestens zwei der drei Signale aktuell oder innerhalb der letzten fünf abgeschlossenen 195-Minuten-Kerzen erfüllt wurden.

---

# 2.4 Earnings Filter

Aktien werden ausgeschlossen, wenn innerhalb der nächsten 10–20 195-Minuten-Kerzen Quartalszahlen erwartet werden.

---

# 2.5 Historisches Backtesting

Für jedes qualifizierte Signal wird geprüft:

Zeitraum:

Letzte 5 Jahre

Analyse:

Identische Signalkombinationen

Kennzahlen:

- Anzahl historischer Signale
- Trefferquote
- durchschnittliche Performance
- Medianperformance
- maximale Verluste
- Drawdown
- Performance nach 10 Kerzen
- Performance nach 20 Kerzen

---

# 2.6 KI-Research

Für qualifizierte Aktien wird eine umfassende Recherche durchgeführt.

Analysebereiche:

## Nachrichten

- aktuelle News
- Unternehmensmeldungen
- relevante Ereignisse

## Analysten

- Kursziele
- Empfehlungen
- Änderungen

## Fundamentaldaten

- Wachstum
- Bewertung
- Profitabilität
- Verschuldung

## Marktumfeld

- Branche
- Konkurrenz
- Makrofaktoren

---

# 2.7 Technische Analyse

Die technische Analyse umfasst:

- Trend
- Momentum
- Überkauft/Überverkauft
- Unterstützungen
- Widerstände
- Chartformationen
- Volatilität

---

# 2.8 Optionsanalyse

Für interessante Kandidaten sollen mögliche Put-Selling-Strategien bewertet werden.

Ausgabe:

- Strike
- Laufzeit
- Delta
- erwartete Prämie
- annualisierte Rendite
- Abstand zum aktuellen Kurs
- Risiko einer Andienung

---

# 2.9 Bewertungssystem

Jede Aktie erhält zwei getrennte Bewertungen.

## Swing Trade Bewertung

Bewertet:

- kurzfristiges Momentum
- technische Signale
- historische Trefferquote
- Timing

---

## Langfristige Investmentbewertung

Bewertet:

- Wachstum
- Qualität
- Bewertung
- Wettbewerbsvorteile
- Zukunftsaussichten

---

# 2.10 Speicherung

Alle Analysen müssen dauerhaft gespeichert werden.

Gespeichert werden:

- Zeitpunkt
- Aktie
- Signale
- Rohdaten
- Rechercheergebnisse
- Scores
- Analysebericht
- spätere Performanceentwicklung

---

# 2.11 Dashboard

Die Anwendung benötigt ein Web-Dashboard.

Funktionen:

- aktuelle Analysen
- historische Analysen
- Aktienvergleich
- Scores
- Detailberichte
- Backtesting-Ergebnisse

---

# 2.12 Benachrichtigung

Nach Abschluss der Analyse wird eine Smartphone-Benachrichtigung gesendet.

Die Nachricht enthält:

- Aktie
- Score
- kurze Zusammenfassung
- Link zum Dashboard