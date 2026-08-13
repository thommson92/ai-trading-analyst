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

## Finnhub — Lizenzprüfung

Erhoben am 2026-08-13 aus <https://finnhub.io/terms-of-service>. Die
Abschnittsnamen der Seite lauten unter anderem *Intellectual Property*,
*Redistribution Rights and Personal Use* und *API Limit and Access*.

**Der entscheidende Unterschied zu IBKR: Die Bedingungen sind auffindbar,
öffentlich und adressieren den Anwendungsfall überwiegend.** Bei RESC gab es
kein auffindbares Dokument — das war der Grund für das `NO_GO`.

| Nutzungsart | Ergebnis | Klausel |
|---|---|---|
| Abruf über die API | **GO** | „All plan listed on Finnhub website is strictly for personal use unless explicitly stated otherwise." Persönliche Nutzung ist genau unser Fall, und das Produkt **ist** eine API |
| Automatisierte Non-Visual-Auswertung | **UNKLAR, tendenziell unproblematisch** | Keine Klausel dazu — weder Erlaubnis noch Verbot. Anders als bei TradingView, wo ein ausdrückliches Verbot stand. Die Bedingungen setzen „derived results from the data" ausdrücklich voraus, und der Dienst wird ausschließlich als API angeboten |
| Lokale dauerhafte Speicherung | **GO_WITH_LIMITATIONS** | „All data must be deleted should your subscription to that data ends." Speicherung während des Abonnements ist nicht untersagt, die Löschung danach schon vorgeschrieben |
| Ableitung eigener Scores und Signale | **GO (implizit)** | „…not redistribute or share access to data **or derived results from the data** obtained from Finnhub" — die Ableitung wird vorausgesetzt, untersagt ist nur ihre Weitergabe |
| Anzeige im ausschließlich persönlichen Dashboard | **GO** | persönliche Nutzung, s. o. |
| Keine Weitergabe an Dritte | **bestätigt — und vertraglich gefordert** | dieselbe Klausel |

### Drei Punkte, die daraus folgen

**Die Löschpflicht kollidiert mit Doc 10.** Abgeschlossene Analysen sollen
unveränderlich und nachvollziehbar bleiben; endet das Abonnement, wären die
zugrunde liegenden Termine zu löschen. Das ist kein Ausschlussgrund, aber
eine Festlegung: Entweder wird die Konsequenz akzeptiert, oder es wird
entschieden, was genau am Ergebnis gespeichert wird. Diese Frage gehört ins
ADR, nicht in eine stillschweigende Implementierungsentscheidung.

**F12 wird davon berührt.** Ein von außen erreichbares Dashboard, das
Finnhub-Daten oder daraus abgeleitete Ergebnisse zeigt, wäre ohne
schriftliche Zustimmung eine untersagte Weitergabe. Das ist beim Entwurf von
F12 mitzudenken.

**Der Personal-Plan setzt Nicht-Professionalität voraus.** Er steht laut
Bedingungen nicht zur Verfügung für Wertpapierprofis, für geschäftliche
Nutzung oder wenn die Kosten als Betriebsausgabe abgesetzt werden; die
Nicht-Professionalität wird über eine Erklärung bestätigt. Das ist vom
Projektinhaber selbst zu prüfen — voraussichtlich unkritisch, aber es ist
eine Zusicherung, keine Formalie.

### Bewertung

Das ist deutlich mehr Klarheit als bei RESC. Offen bleibt allein die
Non-Display-Frage, und dort ist die Lage sachlich anders als bei
TradingView: Dort stand ein Verbot, hier steht nichts, und der Dienst wird
ausschließlich maschinenlesbar ausgeliefert.

Trotzdem gilt derselbe Maßstab wie bisher — Schweigen ist keine Erlaubnis.
Die Frage lässt sich hier allerdings billig klären: Finnhub hat einen
Support- und Vertriebskanal. Eine kurze schriftliche Anfrage vor einer
Festlegung ist der konsequente Weg, deutlich kürzer als der
[IBKR-Entwurf](resc-ibkr-anfrage.md), weil nur ein Punkt offen ist.

## Was fachlich zu prüfen ist

| # | Frage | Warum sie zählt |
|---|---|---|
| P4 | Reicht ein Vorlauf von einem Monat? | Ein Filter „kein Einstieg N Tage vor Earnings" braucht nur wenige Wochen Vorlauf — vermutlich ja, aber festzulegen |
| P5 | **Bestätigte oder geschätzte Termine?** | Ein geschätzter Termin, der als bestätigt behandelt wird, ist ein erfundener Wert |
| P6 | Abdeckung der eigenen Watchlist | Bei RESC fehlten die Empfehlungen für `WMT` ganz — dieselbe Stichprobe ist hier zu fahren |
| P7 | Liefert derselbe Anbieter auch **Ratings und Kursziele**? | Ein Anbieter statt zwei; seit ADR 0016 ist auch das eine offene Lücke |
| P8 | Vor oder nach Börsenschluss? | Ein Termin ohne Tageszeit ist für einen Filter auf 195-Minuten-Kerzen unscharf — meldet ein Unternehmen nach Schluss, ist die betroffene Kerze die des Folgetages |

Beantwortet werden diese Fragen durch die Sonde unter
[`spikes/earnings-anbieter/`](../../spikes/earnings-anbieter/).

## Finnhub — fachliche Befunde

Erhoben am 2026-08-13 mit einem kostenlosen Schlüssel, zwei Abrufe über
30 und 120 Tage.

### Die Antwort enthält neun Felder

`date`, `symbol`, `year`, `quarter`, `hour`, `epsEstimate`,
`revenueEstimate`, `epsActual`, `revenueActual`.

Der Füllgrad ist aufschlussreich: `epsActual` und `revenueActual` sind für
künftige Termine **durchweg leer** — sie werden erst nach der Meldung
gefüllt. Schätzwerte liegen für etwa 60 % der Termine vor. Der Termin selbst
ist immer da.

### P4 — Der Vorlauf ist nicht die Grenze, die Trefferzahl ist es

Die Gratis-Stufe liefert Termine bis mindestens vier Monate voraus, nicht
nur einen Monat wie in Vergleichsquellen behauptet.

**Aber:** Ein einzelner Abruf über 120 Tage lieferte **genau 1500
Einträge** — eine verdächtig runde Zahl — und darin ausschließlich Termine
der **letzten sechs Wochen** des angefragten Zeitraums. Die nahen Termine,
also genau die, auf die es ankommt, fehlten vollständig. Die Antwort hat das
mit keinem Feld kenntlich gemacht.

Das ist der gefährlichste Befund dieser Prüfung: Wer einen langen Zeitraum
am Stück anfragt, bekommt stillschweigend einen Ausschnitt und hält ihn für
das Ganze. Ein Earnings-Filter auf dieser Grundlage würde die betroffenen
Aktien wortlos durchwinken.

Umgehen lässt sich das mit kurzen Anfragefenstern. Die Sonde tut das jetzt
(`--fenster`, Standard 30 Tage) und meldet jede verdächtig runde
Trefferzahl.

### P5 — Keine Kennzeichnung, aber ein einseitiger Ersatz

Es gibt kein Feld für bestätigt/geschätzt. Die Vermutung, dass eine gefüllte
Tageszeit einen bestätigten Termin anzeigt, wird von den Daten **gestützt**:

| Vorlauf | Anteil mit Tageszeit |
|---|---|
| diese Woche | 46 % |
| in 1 Woche | 19 % |
| in 2 Wochen | 12 % |
| in 3 Wochen | 8 % |
| in 12–17 Wochen | 6–19 % |

Der Abfall von 46 % auf rund 10 % ist deutlich. **Eine gefüllte Tageszeit
ist damit ein brauchbarer Hinweis auf einen bestätigten Termin.**

Der Umkehrschluss gilt aber **nicht**: Auch bei unmittelbar bevorstehenden
Terminen fehlt die Tageszeit in mehr als der Hälfte der Fälle. Aus einem
leeren `hour` folgt „unbekannt", nicht „unbestätigt".

Für den Filter heißt das: Ein vollständiger „nur bestätigte Termine"-Filter
ist mit dieser Quelle nicht baubar. Bleiben zwei Wege — jeder Termin zählt,
auch der geschätzte (vorsichtig, schließt gelegentlich zu Unrecht aus), oder
nur bestätigte zählen (übersieht die Mehrheit). Für einen Filter, der Risiko
vermeiden soll, ist der erste Weg der richtige: Eine verpasste Gelegenheit
kostet weniger als eine Position in eine Ergebnismeldung hinein. **Das ist
eine Entscheidung für das ADR, keine stillschweigende Festlegung im Code**,
und die geringere Konfidenz gehört ans Ergebnis.

### P8 — Tageszeit als `bmo`/`amc`

Wo vorhanden, steht `bmo` (vor Börsenöffnung) oder `amc` (nach
Börsenschluss). Das ist die Angabe, die ein Filter auf 195-Minuten-Kerzen
braucht: Meldet ein Unternehmen `amc`, ist die betroffene Kerze die des
Folgetages.

### P6 — noch offen

Die Abdeckung der eigenen Watchlist lässt sich aus den bisherigen Läufen
**nicht** beantworten: Der 30-Tage-Lauf traf 31 von 192 Titeln, der
120-Tage-Lauf 32 — aber letzterer deckte wegen der Kürzung nur sechs Wochen
im November und Dezember ab. Nötig ist ein Lauf über mehrere kurze Fenster.

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
