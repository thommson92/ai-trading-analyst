# Optionsanalyse

> **Wozu dieses Dokument.** Es beschreibt das fachliche Soll als frühe
> Skizze. Maßgeblich bei Widersprüchen ist `docs/10 - System Architecture.md`
> §6.10 ([ADR 0001](adr/0001-dokumentenhierarchie.md)); was tatsächlich
> entschieden und gebaut ist, steht in
> [ADR 0048](adr/0048-optionsanalyse-im-tageslauf.md) — inklusive
> Laufzeitfenster (21–60 Tage, Ziel 35), Delta-Band, Prämie als Mittelwert
> und der Kennzeichnung der Andienungswahrscheinlichkeit als Näherung. Die
> Beispielwerte unten sind historisch.

## Ziel

Bewertung alternativer Einstiegsmöglichkeiten über Put Selling.

---

# Strategie

Primärer Fokus:

Cash Secured Put

---

# Parameter

Das System analysiert:

- aktueller Aktienkurs
- Unterstützungszonen
- Volatilität
- Laufzeit
- Strike
- Delta
- Prämie

---

# Bewertung

Für jede Strategie:

- erwartete Rendite
- annualisierte Rendite
- Risiko
- Abstand zum aktuellen Kurs
- Wahrscheinlichkeit der Andienung

---

# Beispielausgabe

Aktie:

MSFT

Alternative:

Cash Secured Put

Strike:

400 USD

Laufzeit:

45 Tage

Delta:

0,22

Prämie:

2,50 USD

Bewertung:

Attraktive Alternative zum Direkteinstieg.