# Anbieter für Earnings-Termine, Ratings und Kursziele

Stand 2026-08-13. **Entscheidungsvorlage, kein ADR.** Das ADR zur
F9-Datenquelle entsteht erst, wenn die unter „Was noch fehlt" genannten
Punkte belegt sind.

Ausgangslage: IBKR ist als Research-Quelle ausgeschieden
([ADR 0016](../adr/0016-ibkr-keine-quelle-fuer-research-daten.md)). Gesucht
ist damit eine externe Quelle für **künftige Berichtstermine** und, seit der
RESC-Absage, zusätzlich für **Analystenratings und Kursziele**.

## Der entscheidende Punkt: das Abrufvolumen

Der Earnings-Filter greift **nicht** auf der ganzen Watchlist. Er prüft nur
Aktien, die die Signalkriterien erfüllt haben — in der Regel **10 bis 20 pro
Tag**, im beobachteten Lauf über 192 Symbole waren es 39 an einem
ungewöhnlich bewegten Tag.

Das verschiebt die Bewertung grundlegend. Bei 192 Symbolen täglich wäre das
Anfragekontingent das erste Ausschlusskriterium gewesen; bei 20 ist es bei
**keinem** der geprüften Anbieter die bindende Grenze — nicht einmal bei den
kleinsten Gratis-Stufen mit 25 Anfragen pro Tag. Entscheidend sind stattdessen:

1. **Lizenz** — ist personenbezogene, automatisierte, nicht-anzeigende
   Verarbeitung mit lokaler Speicherung und abgeleiteten Signalen erlaubt?
2. **Endpunkt-Verfügbarkeit** — ist der Earnings-Kalender in der Gratis-Stufe
   überhaupt enthalten, oder nur formal vorhanden?
3. **Datenqualität** — bestätigte oder geschätzte Termine, Vorlauf, Abdeckung.

Ein Kalenderendpunkt liefert außerdem oft **alle** Termine eines Zeitraums in
einer einzigen Anfrage. Dann ist der Verbrauch unabhängig von der Zahl der
Kandidaten: eine Anfrage pro Tag, lokal gefiltert. Das ist bei der
Bewertung mitzudenken.

## Marktüberblick

Die Angaben stammen aus öffentlich zugänglichen Quellen vom 2026-08-13 und
sind **Ausgangspunkte für die Prüfung, keine belegten Vertragsinhalte**.
Freistufen und Preise ändern sich häufig. Nach der IBKR-Erfahrung gilt: Die
Lizenzfrage wird an den tatsächlichen Nutzungsbedingungen des Anbieters
geprüft, nicht an einer Vergleichstabelle.

| Anbieter | Earnings-Kalender gratis? | Kontingent gratis | Reicht für 10–20/Tag | Anmerkung |
|---|---|---|---|---|
| **Finnhub** | **ja** | 60 Anfragen/Minute | deutlich | Vorlauf in der Gratis-Stufe auf etwa **einen Monat** begrenzt; Gratis-Stufe ausdrücklich persönlich und nicht-kommerziell |
| **Financial Modeling Prep** | **nein** — kostenpflichtiger Endpunkt | 250 Anfragen/Tag | ja, aber Endpunkt fehlt | Kalender erst im Bezahlplan; Preise je nach Quelle 29–79 USD/Monat |
| **Alpha Vantage** | **nein** — Gratis liefert Demodaten | 25 Anfragen/Tag | knapp, aber Endpunkt fehlt | `EARNINGS_CALENDAR` erst ab den großen Premium-Stufen (600+/Min.) |
| **EODHD** | **nein** | 20 Anfragen/Tag, nur Tagesschluss | Endpunkt fehlt | Kalenderpaket als Zusatz, etwa 19,99 €/Monat |

**Vorläufiges Bild:** Von den Gratis-Stufen kommt nur **Finnhub** ernsthaft
in Frage — bei den übrigen ist der Kalender gar nicht enthalten, unabhängig
vom Kontingent. Als bezahlter Rückfallweg sind EODHD (Kalenderpaket) und FMP
die naheliegenden Kandidaten, beide im Bereich zweistelliger Monatsbeträge.

## Was an Finnhub zu prüfen ist

Kein Kandidat wird ohne diese Prüfung übernommen. Die Punkte entsprechen der
Systematik, die sich bei der RESC-Frage bewährt hat.

| # | Frage | Warum sie zählt |
|---|---|---|
| P1 | Erlaubt die Lizenz automatisierte, nicht-anzeigende Verarbeitung? | Der Punkt, an dem TradingView und IBKR gescheitert sind |
| P2 | Erlaubt sie **lokale, dauerhafte Speicherung**? | Doc 10 verlangt unveränderliche, nachvollziehbare Analysen. **Hinweis: Finnhub verlangt offenbar die Löschung aller Daten am Ende des Abonnements** — das steht in direktem Konflikt mit dieser Anforderung und ist vor einer Zusage zu klären |
| P3 | Erlaubt sie die **Ableitung eigener Signale**? | Der Earnings-Filter ist genau das |
| P4 | Reicht ein Vorlauf von einem Monat? | Ein Filter „kein Einstieg N Tage vor Earnings" braucht nur wenige Wochen Vorlauf — vermutlich ja, aber festzulegen |
| P5 | **Bestätigte oder geschätzte Termine?** | Ein geschätzter Termin, der als bestätigt behandelt wird, ist ein erfundener Wert |
| P6 | Abdeckung der eigenen Watchlist | Bei RESC fehlten die Empfehlungen für `WMT` ganz — dieselbe Stichprobe ist hier zu fahren |
| P7 | Liefert derselbe Anbieter auch **Ratings und Kursziele**? | Ein Anbieter statt zwei; seit ADR 0016 ist auch das eine offene Lücke |

## Zwei getrennte Bedarfe

Das Abrufvolumen von 10–20 pro Tag gilt für den **Live-Filter**. Das
**Backtesting** braucht etwas anderes: historische Berichtstermine für viele
Symbole über Jahre, einmalig in großer Menge. Das ist bei fast jedem Anbieter
ein anderes Produkt und eine andere Preisstufe — und wird bei einer Auswahl,
die nur den Live-Fall betrachtet, regelmäßig übersehen.

Für den historischen Teil gibt es einen Weg ohne jedes Lizenzrisiko:
**SEC EDGAR**. Die Meldung der Quartalsergebnisse erfolgt in den USA über ein
`8-K` mit Item 2.02 („Results of Operations and Financial Condition"). Das
Einreichungsdatum dieser Meldung **ist** der Berichtstermin, nicht bloß eine
Näherung. EDGAR ist amtlich, kostenlos, ohne Lizenzbeschränkung und über eine
dokumentierte Schnittstelle abrufbar; verlangt wird lediglich ein
aussagekräftiger `User-Agent` und ein maßvolles Anfragetempo.

Damit ergäbe sich eine saubere Trennung: **EDGAR für die Vergangenheit,
ein Anbieter für die Zukunft.** Das reduziert den kommerziellen Bedarf auf
genau das, was EDGAR prinzipiell nicht leisten kann — künftige Termine.

Diese Idee ist hier nur festgehalten, nicht entschieden. Sie gehört mit in
die F9-Entscheidung.

## Was noch fehlt

1. Prüfung von P1 bis P3 an Finnhubs tatsächlichen Nutzungsbedingungen —
   dieselbe Sorgfalt wie bei RESC, mit wörtlichen Klauseln und Fundstellen.
2. Ein Probeabruf mit kostenlosem Schlüssel für eine Handvoll Symbole:
   P4 bis P7, insbesondere ob Termine als bestätigt gekennzeichnet sind.
3. Dasselbe für den bezahlten Rückfallweg, falls Finnhub an P1–P3 scheitert.
4. Kosten und Anfragegrenzen gegengerechnet auf 10–20 Symbole täglich sowie
   auf den einmaligen historischen Bedarf des Backtestings.

Erst danach entsteht das ADR zur F9-Datenquelle.

## Quellen

- [Finnhub — Earnings Calendar API](https://finnhub.io/docs/api/earnings-calendar)
- [Finnhub — Pricing](https://finnhub.io/pricing)
- [Financial Modeling Prep — Earnings Calendar API](https://site.financialmodelingprep.com/developer/docs/stable/earnings-calendar)
- [Financial Modeling Prep — Pricing Plans](https://site.financialmodelingprep.com/pricing-plans)
- [EODHD — Calendar API](https://eodhd.com/financial-apis/calendar-upcoming-earnings-ipos-and-splits)
- [Alpha Vantage — vollständiger Leitfaden 2026](https://alphalog.ai/blog/alphavantage-api-complete-guide)
- [Best Financial Data APIs in 2026](https://www.nb-data.com/p/best-financial-data-apis-in-2026)
