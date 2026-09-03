# Backtesting Spezifikation

> **Wozu dieses Dokument.** Es beschreibt das fachliche Soll. Maßgeblich
> bei Widersprüchen ist `docs/10 - System Architecture.md`
> ([ADR 0001](adr/0001-dokumentenhierarchie.md)); was tatsächlich
> entschieden ist, steht in `docs/adr/`.
>
> **Drei Festlegungen weichen ab; es gilt jeweils die spätere.**
> ① *Einstieg:* nicht der Schlusskurs der Signalkerze, sondern der
> Schlusskurs der Kerze, bei der die Qualifikationsregel erstmals
> erkannt wird (Projekt-`CLAUDE.md`). ② Nach jedem gezählten Ereignis
> gilt ein *Cooldown* von fünf Kerzen; rohe und deduplizierte
> Stichprobengröße werden beide ausgewiesen. ③ Trefferquote nach einem
> Horizont und dauerhaftes Halten oberhalb des Einstiegs sind **getrennte
> Kennzahlen** und werden nirgends zu einer „Erfolgsquote" verrechnet.
>
> Zu den „letzten 5 Jahren": die Tiefe ist erreichbar und gemessen
> ([ADR 0028](adr/0028-historientiefe-gemessen.md)), im Bestand liegt sie
> aber erst, wenn der Tiefen-Backfill gelaufen ist.

## Ziel

Bewertung der historischen Qualität der definierten technischen Signale.

---

# Zeitraum

Standard:

Letzte 5 Jahre

---

# Signaldefinition

Ein historisches Signal gilt als gültig, wenn:

Mindestens zwei der drei definierten Kaufsignale erfüllt waren und zusätzlich mindestens eines der beiden Zusatzkriterien (ADR 0056).

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