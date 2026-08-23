# Vision

> **Wozu dieses Dokument.** Es beschreibt das fachliche Soll. Maßgeblich
> bei Widersprüchen ist `docs/10 - System Architecture.md`
> ([ADR 0001](adr/0001-dokumentenhierarchie.md)); was tatsächlich
> entschieden ist, steht in `docs/adr/`.
>
> Diese Datei hält die Zielsetzung fest und ist bewusst nicht auf den
> Umsetzungsstand nachgeführt.

## Projektname (Arbeitstitel)

AI Trading Analyst

---

# 1. Überblick

Der AI Trading Analyst ist ein persönliches, KI-gestütztes Trading-Analyse-System zur Identifikation und Bewertung potenzieller Long-Swing-Trades auf Basis technischer Handelssignale, historischer Wahrscheinlichkeiten, fundamentaler Informationen und Optionsstrategien.

Das System kombiniert einen regelbasierten technischen Screener mit mehreren spezialisierten KI-Analysekomponenten.

Das Ziel ist nicht die vollständige Automatisierung des Tradings, sondern die Bereitstellung einer hochwertigen Entscheidungsgrundlage für den Nutzer.

---

# 2. Problemstellung

Die manuelle Analyse zahlreicher Aktien-Watchlisten ist zeitaufwendig und führt dazu, dass potenzielle Chancen entweder verspätet erkannt oder aufgrund fehlender Zeit nicht ausreichend analysiert werden.

Gleichzeitig erfordert eine fundierte Handelsentscheidung die Kombination verschiedener Informationsquellen:

- technische Chartanalyse
- historische Signalqualität
- Unternehmensnachrichten
- Analystenmeinungen
- Fundamentaldaten
- Optionsbewertung
- Risikoeinschätzung

Diese Informationen müssen aktuell, strukturiert und vergleichbar zusammengeführt werden.

---

# 3. Zielsetzung

Das System soll täglich automatisch:

1. bestehende TradingView-Watchlisten analysieren,
2. Aktien anhand definierter technischer Kaufsignale filtern,
3. nur relevante Kandidaten einer tiefgehenden Analyse zuführen,
4. einen strukturierten Analysebericht erzeugen,
5. die Ergebnisse speichern,
6. den Nutzer über relevante Chancen informieren.

---

# 4. Kernidee

Die Anwendung besteht aus zwei Analyseebenen.

## Ebene 1: Technischer Screener

Der Screener prüft alle Aktien der Watchlisten anhand klar definierter Regeln.

Ziel:

Reduktion einer großen Anzahl von Aktien auf ca. 2–3 relevante Kandidaten pro Handelstag.

Der Screener verwendet ausschließlich abgeschlossene 195-Minuten-Kerzen.

---

## Ebene 2: KI Trading Analyst

Nur Aktien, welche den technischen Filter bestehen, werden umfangreich analysiert.

Die KI bewertet:

- technische Situation
- historische Signalqualität
- aktuelle Nachrichtenlage
- Analysteneinschätzungen
- Fundamentaldaten
- Risiken
- Optionsmöglichkeiten

---

# 5. Zielgruppe

Der Nutzer selbst.

Das System ist für einen erfahrenen Privatanleger entwickelt, der:

- eigene TradingView-Watchlisten verwendet,
- technische Strategien besitzt,
- fundierte Entscheidungen treffen möchte,
- keine vollautomatische Handelsausführung benötigt.

---

# 6. Anlagefokus

Primärer Fokus:

- US-Aktien
- Long-Positionen
- Swing-Trading

Sekundärer Fokus:

- langfristige Investmentbewertung

Die Architektur soll zukünftige Erweiterungen ermöglichen:

- Short-Strategien
- weitere Märkte
- weitere technische Strategien
- Portfolioanalyse

---

# 7. Grundprinzipien

## Transparenz

Jede Bewertung muss nachvollziehbar sein.

Die Anwendung soll nicht nur eine Bewertung ausgeben, sondern erklären:

- warum eine Aktie interessant ist,
- welche Faktoren positiv sind,
- welche Risiken bestehen.

---

## Keine Black Box

Jeder Score muss aus nachvollziehbaren Einzelbewertungen bestehen.

---

## Datenbasierte Entscheidungen

Historische Signalqualität und statistische Auswertungen sollen Bestandteil jeder Analyse sein.

---

## Mensch entscheidet

Das System liefert Empfehlungen und Einschätzungen.

Die finale Handelsentscheidung verbleibt beim Nutzer.

---

# 8. Langfristige Vision

Der AI Trading Analyst soll sich zu einem persönlichen Investment-Research-System entwickeln.

Mögliche spätere Erweiterungen:

- Portfolioüberwachung
- automatische Watchlist-Erstellung
- Strategie-Vergleich
- Performance-Tracking
- zusätzliche Handelsstrategien
- Marktregime-Erkennung
- KI-basierte Strategieoptimierung