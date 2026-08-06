# Backtesting Spezifikation

## Ziel

Bewertung der historischen Qualität der definierten technischen Signale.

---

# Zeitraum

Standard:

Letzte 5 Jahre

---

# Signaldefinition

Ein historisches Signal gilt als gültig, wenn:

Mindestens zwei der drei definierten Kaufsignale erfüllt waren.

---

# Einstieg

Der Einstiegspreis entspricht:

Schlusskurs der Signalkerze.

---

# Bewertungshorizonte

Bewertet werden:

- 5 Kerzen
- 10 Kerzen
- 20 Kerzen

---

# Kennzahlen

## Trefferquote

Anteil der Fälle, bei denen Kurs nach Zeitraum über Einstieg lag.

---

## Durchschnittsrendite

Mittlere Kursentwicklung.

---

## Medianrendite

Robuster Wert gegen Ausreißer.

---

## Maximaler Verlust

Größter negativer Verlauf nach Einstieg.

---

## Drawdown

Maximaler Rückgang vor Erreichen des Zielzeitraums.

---

# Ausgabe Beispiel

Aktie:

AAPL

Signal:

RSI Cross + EMA Breakout

Historie:

Signale:
34

Trefferquote 20 Kerzen:
71 %

Durchschnitt:
+6,4 %

Max Verlust:
-8,2 %