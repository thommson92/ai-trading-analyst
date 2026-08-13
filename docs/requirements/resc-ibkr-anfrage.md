# Entwurf: Anfrage an IBKR zur RESC-Lizenzierung

> **Nicht abgesendet — und nach heutigem Stand auch nicht abzusenden.** Der
> Projektinhaber hat am 2026-08-13 entschieden, IBKR nicht als
> Research-Quelle zu verwenden
> ([ADR 0016](../adr/0016-ibkr-keine-quelle-fuer-research-daten.md)). Der
> Entwurf bleibt erhalten, falls die Frage je neu aufgeworfen wird; dann
> wäre er der Ausgangspunkt und nicht neu zu schreiben.

Vom Projektinhaber aus dem eigenen Konto abzusenden — Client Portal → Help →
**Secure Message Center**. Kategorie möglichst so wählen, dass die Anfrage
bei der für **Market Data / Research Licensing** oder **API** zuständigen
Stelle landet, nicht beim allgemeinen technischen Support.

Zwei Hinweise zum Absenden:

- **Vor dem Absenden** die eckigen Klammern prüfen. Wenn der genaue
  Abonnementname (V2 in der [Prüfliste](resc-lizenzpruefung.md)) bekannt
  ist, dort einsetzen; sonst die Formulierung stehen lassen — IBKR sieht das
  Konto und kann das Abonnement selbst identifizieren.
- **Eine allgemeine Supportantwort genügt nicht.** Bleibt die Antwort ohne
  Bezug auf konkrete Vertragsbedingungen, ist nachzufassen. Das ist im Text
  bereits angelegt.

Antwort anschließend vollständig zur Auswertung übergeben; das Ergebnis geht
in die Prüftabelle in Abschnitt 2 der Prüfliste.

---

**Subject:** Licensing scope for Reuters analyst estimates (`reqFundamentalData`, report type `RESC`) — personal, non-commercial automated use

---

Dear Interactive Brokers team,

please route this enquiry to the team responsible for **market data and
research licensing** and/or **API licensing**. My question is about
contractual permissions, not about technical implementation, so a general
technical support answer would unfortunately not answer it.

I retrieve analyst estimates from my own account through the TWS API using
`reqFundamentalData(contract, reportType='RESC')`. The response is XML with
the root element `REarnEstCons` and contains consensus estimates, target
prices and analyst recommendations, apparently sourced from
Reuters/Refinitiv. The relevant subscription on my account is
[**exact name of my research/estimates subscription** — or: "the research /
analyst estimates subscription currently active on my account"].

I would like to confirm, in writing, whether my intended use is covered by
the agreements I have already accepted, or whether it requires additional
permissions, subscriptions or fees.

**My use case, in full:**

1. Personal, **non-commercial** use only. I am the sole user. I am
   registered as a non-professional.
2. Access exclusively through **my own TWS instance and my own IBKR
   account**. No third-party access, no shared credentials.
3. **Automated retrieval** of `RESC` data through the TWS API, for a
   watchlist of roughly 190 US equities, at most once per trading day.
4. **Local storage** of the retrieved data in my own database, recording the
   symbol and the retrieval timestamp, retained over time so that past
   analyses remain reproducible.
5. **Automated, non-visual processing**: computing my own ratings and scores
   from the retrieved values, combined with other data I already subscribe
   to.
6. **Display** of both the source values and my derived results in a private
   dashboard that runs on my own machine and is accessible only to me.
7. **No redistribution of any kind**: no publication, no sharing with third
   parties, no resale, no external access to the dashboard, and no display
   of the data to anyone but myself.

**My questions:**

- **Q1** Please confirm or deny **each of points 1 to 7 individually**.
- **Q2** Which specific agreements govern this use? Please give the exact
  document titles, versions and where I can retrieve them, in particular any
  end-user terms of the underlying data provider.
- **Q3** Does the use described require any **additional subscription,
  licence or fee** — for example a non-display or automated-use licence? If
  so, which one and at what cost?
- **Q4** Does your confirmation also cover the rights of the **underlying
  data provider** (Reuters/Refinitiv/LSEG), or do I need a separate
  agreement or permission directly with them?
- **Q5** If any part of the above is **not** permitted, please state which
  part and which clause prohibits it.

I would rather establish this before building anything on top of the data
than discover a restriction afterwards. A clear "no" is just as useful to me
as a "yes".

Thank you very much for your help.

Kind regards
