# Anbieter für Earnings-Termine, Ratings und Kursziele

Stand 2026-08-13. **Erledigt** — die Entscheidung steht in
[ADR 0017](../adr/0017-finnhub-fuer-earnings-und-ratings.md). Dieses
Dokument bleibt als Beleg erhalten: Es enthält die Messungen, auf die sich
das ADR stützt, und die Wege, die nicht gegangen wurden.

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
| **Finnhub** | **ja** | 60 Anfragen/Minute | deutlich | Gratis-Stufe ausdrücklich persönlich und nicht-kommerziell. Der behauptete Vorlauf von einem Monat hat sich als falsch erwiesen — siehe fachliche Befunde |
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
| Automatisierte Non-Visual-Auswertung | **GO** — Entscheidung des Projektinhabers vom 2026-08-13 | Keine Klausel dazu — weder Erlaubnis noch Verbot. Anders als bei TradingView, wo ein ausdrückliches Verbot stand. Die Bedingungen setzen „derived results from the data" ausdrücklich voraus, und der Dienst wird ausschließlich als API angeboten |
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

### Die Non-Display-Frage: GO durch den Projektinhaber

**Entschieden am 2026-08-13.** Die Begründung des Projektinhabers, wörtlich
festgehalten: Die nicht-anzeigende Verarbeitung wird in den Bedingungen
**nicht ausdrücklich erwähnt**, und der **private Gebrauch wird ausdrücklich
toleriert**.

Warum das hier trägt und bei den beiden anderen Quellen nicht — der
Unterschied ist der Kern der Sache:

| Quelle | Lage | Ergebnis |
|---|---|---|
| TradingView | **ausdrückliches Verbot** der Non-Display-Nutzung | `NO_GO` (ADR 0012) |
| IBKR RESC | **kein auffindbares Dokument**, weder Erlaubnis noch Verbot | `NO_GO mangels belastbarer Grundlage` (ADR 0016) |
| **Finnhub** | **Dokument vorhanden und öffentlich**, erlaubt private Nutzung ausdrücklich, schweigt zur Non-Display-Frage | **`GO`** |

Der Maßstab „Schweigen ist keine Erlaubnis" bleibt damit unangetastet: Bei
RESC fehlte der Vertrag als Ganzes. Hier liegt er vor, gewährt private
Nutzung ausdrücklich und regelt nur diesen einen Nebenaspekt nicht.

Diese Bewertung ist eine **Entscheidung des Projektinhabers, keine
Rechtsberatung** durch das Projekt oder durch Claude Code — dieselbe
Einordnung wie bei der Marktdatenbewertung in
[ADR 0014](../adr/0014-ibkr-produktivintegration-freigegeben.md).

Damit ist die Lizenzprüfung für Finnhub abgeschlossen: **fünf von fünf
Nutzungsarten gedeckt**, eine davon mit der Löschpflicht als Einschränkung.
Eine Anfrage an Finnhub ist nicht mehr nötig.

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

### P5 — Keine Kennzeichnung, und kein tragfähiger Ersatz

Es gibt kein Feld für bestätigt/geschätzt.

Aus dem ersten, noch gekürzten Datensatz sah es so aus, als könne die
Tageszeit einspringen: 46 % in der laufenden Woche, dann Abfall auf unter
10 %. Der vollständige Datensatz widerlegt das. Der Anteil fällt nicht
monoton, sondern **steigt in den Wochen 9 bis 11 wieder auf 26 bis 30 %** —
und das sind genau die Wochen der Q3-Hochsaison, in denen die großen
Unternehmen berichten.

Damit gibt es eine zweite, bessere Erklärung: **Die Tageszeit ist nicht ein
Merkmal des bestätigten Termins, sondern der Abdeckung.** Bei einem gut
beobachteten Großunternehmen ist lange im Voraus bekannt, dass es nach
Börsenschluss meldet — es tut das jedes Quartal. Bei einem kaum beobachteten
Nebenwert steht es nie dabei, egal wie nah der Termin ist.

**Die Gegenprobe bestätigt das.** Wertet man nur die eigene Watchlist aus —
durchweg große, gut abgedeckte Titel — ergibt sich:

| | Anteil mit Tageszeit |
|---|---|
| Watchlist (192 große Titel) | **64 %** |
| alle übrigen | **20 %** |

Und innerhalb der Watchlist bleibt der Anteil über **alle** Vorlaufwochen
hoch: 83 % in der laufenden Woche, 71 % in Woche 10, 67 % in Woche 16. Kein
Abfall mit dem Vorlauf. Die Ausreißer nach unten (Woche 3 mit 14 %, Woche 15
mit 25 %) betreffen sieben beziehungsweise acht Einträge und tragen nicht.

**Damit ist die erste Lesart widerlegt.** `hour` ist ein Merkmal der
Abdeckung, nicht der Bestätigung. Ein großer Titel hat die Angabe auch vier
Monate im Voraus, ein kleiner nie.

Zwei Folgerungen:

**Für die Verlässlichkeit der Termine (P5) bleibt es beim Befund: Es gibt
keine.** Der Termin steht ohne Angabe, ob er bestätigt oder geschätzt ist.
Für den Filter bleiben zwei Wege — jeder Termin zählt, auch der geschätzte
(vorsichtig, schließt gelegentlich zu Unrecht aus), oder es wird eine zweite
Quelle zur Bestätigung herangezogen. Für einen Filter, der Risiko vermeiden
soll, ist der erste Weg vertretbar: Eine verpasste Gelegenheit kostet weniger
als eine Position in eine Ergebnismeldung hinein. **Das ist eine Entscheidung
für das ADR**, und die Unsicherheit gehört ans Ergebnis.

**Die Tageszeit (P8) ist ein Nice-to-have, kein Pflichtfeld.**
Ausdrücklich so entschieden vom Projektinhaber am 2026-08-13: Dass zu einem
Termin nicht feststeht, ob vor oder nach Handelsbeginn gemeldet wird, ist
toleriert; die Quote von zwei aus drei genügt.

Damit gilt: Der Filter darf eine fehlende Tageszeit **nicht** zum
Ausschlusskriterium machen und keine annehmen. Liegt sie vor — bei 64 % der
eigenen Titel —, verfeinert sie die Zuordnung („meldet nach Schluss, also
betrifft es die Kerze des Folgetages"). Fehlt sie, wird der ganze Handelstag
als betroffen behandelt.

### P8 — Tageszeit als `bmo`/`amc`

Wo vorhanden, steht `bmo` (vor Börsenöffnung) oder `amc` (nach
Börsenschluss). Das ist die Angabe, die ein Filter auf 195-Minuten-Kerzen
braucht: Meldet ein Unternehmen `amc`, ist die betroffene Kerze die des
Folgetages.

### Die Treffergrenze liegt bei 1500 je Anfrage — und 30 Tage reichen nicht

Der Lauf über fünf Fenster zu 30 Tagen hat die Grenze reproduziert:

| Fenster | Einträge |
|---|---|
| 13.08. – 11.09. | 953 |
| 12.09. – 11.10. | 265 |
| **12.10. – 10.11.** | **1500 — gekürzt** |
| 11.11. – 10.12. | 1167 |

Die Kürzung trifft **den Anfang** des Zeitraums: In der Vorlaufanalyse
fehlen die Wochen 9 und 10 vollständig, also der 15. bis 28. Oktober — der
Höhepunkt der Q3-Saison. Ein fester Fensterzuschnitt genügt damit nicht: Im
September reichen 30 Tage, Ende Oktober nicht.

Die Sonde erkennt die Kürzung jetzt und **halbiert den Zeitraum, bis die
Antwort vollständig ist**. Das ist zugleich der Bauplan für eine spätere
produktive Anbindung: Nicht die Fenstergröße raten, sondern die Kürzung
erkennen.

### P6 — Abdeckung 97 %

Mit aufgelöster Kürzung — elf Anfragen über vier Monate, 5957 Termine für
5125 Symbole — haben **186 von 192 Watchlist-Titeln einen Termin**. Da über
vier Monate jeder Quartalsberichterstatter mindestens einmal auftauchen
muss, ist das faktisch Vollabdeckung.

**Vom Projektinhaber am 2026-08-13 akzeptiert.**

Ohne Termin bleiben sechs Titel: `BDX`, `BRK.B`, `MGA`, `NVO`, `SPCX`,
`SWKS`. Sie zerfallen erkennbar in Gruppen, und die sind aufschlussreicher
als die Zahl:

| Titel | Vermutete Ursache |
|---|---|
| `BRK.B` | Schreibweise — bei IBKR `BRK B`, hier `BRK.B`; zusätzlich ein Unternehmen ohne Analystenkonferenz |
| `NVO`, `MGA` | ausländische Emittenten (Dänemark, Kanada), oft unter der Heimatnotierung geführt |
| `SPCX` | Börsengang im Juni 2026, noch keine Berichtshistorie |
| `BDX`, `SWKS` | Geschäftsjahr endet im September/Oktober — echte Lücke oder Nebenwirkung des abweichenden Rhythmus |

Das ist eine **Vermutung anhand der Namen, keine geprüfte Ursache.**
Praktisch relevant ist die Gruppe `BDX`/`SWKS`: Ein Titel mit abweichendem
Geschäftsjahr, dessen Termin der Filter nicht kennt, ist genau der Fall, in
dem eine Ergebnismeldung unbemerkt trifft.

**Ausdrücklich entschieden am 2026-08-13:** Ein fehlender Termin wird
**nicht** als „keine Earnings in Sicht" interpretiert. Er ist fehlende
Information und steht als solche am Ergebnis — Datenabdeckung und Konfidenz
sinken entsprechend, wie es Doc 10 für jede fehlende Kennzahl vorsieht.

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

### P7 — Empfehlungen ja, Kursziele nein

Abruf am 2026-08-13 gegen `/stock/recommendation` und `/stock/price-target`
mit dem kostenlosen Schlüssel, drei Symbole:

| Endpunkt | Ergebnis |
|---|---|
| **Empfehlungen** | **HTTP 200 — in der Gratis-Stufe enthalten** |
| **Kursziele** | **HTTP 403 — kostenpflichtig** |

Die Empfehlungen kommen als vollständige Verteilung mit Zeitreihe: je
Eintrag `strongBuy`, `buy`, `hold`, `sell`, `strongSell` samt `period`, und
zwar vier Monatsstände je Symbol. Das ist mehr, als RESC geliefert hätte —
dort lag nur der aktuelle Stand vor. Die **Veränderung** der
Analystenmeinung über vier Monate ist ein eigenständiges Signal und liegt
hier ohne Zusatzaufwand vor.

Damit ist die Lücke aus ADR 0016 zu zwei Dritteln geschlossen: Termine und
Ratings sind kostenlos abgedeckt, **Kursziele fehlen**.

## Stand

| Frage | Stand |
|---|---|
| Lizenz — alle fünf Nutzungsarten | **geklärt**, GO; Löschpflicht als Einschränkung |
| P4 Vorlauf | **geklärt**, mindestens vier Monate |
| P5 bestätigt/geschätzt | **geklärt** — keine Kennzeichnung, kein Ersatz |
| P6 Abdeckung | **geklärt**, 97 %, akzeptiert |
| P7 Ratings | **geklärt**, kostenlos enthalten |
| P7 Kursziele | **kostenpflichtig — offene Entscheidung** |
| P8 Tageszeit | **geklärt**, Nice-to-have, 64 % bei den eigenen Titeln |
| Grenzen der Schnittstelle | **geklärt**, 1500 Treffer je Anfrage, stille Kürzung am Anfang |
| Historische Termine fürs Backtesting | **offene Entscheidung** — EDGAR als lizenzfreier Weg |

## Die verbleibende Entscheidung: Kursziele

Drei Wege, keiner davon zwingend:

1. **Ohne Kursziele bauen.** Die Empfehlungsverteilung samt ihrer
   Veränderung deckt die Analystenmeinung ab; das Kursziel fügt eine
   Größenordnung hinzu, keine neue Richtung. F9 liefe mit einer als fehlend
   gekennzeichneten Kennzahl — der Regelfall aus Doc 10, kein Sonderfall.
2. **Finnhub-Bezahlstufe.** Öffentliche Quellen nennen für Premium
   11,99 bis 99,99 USD im Monat, je nach Umfang; welche Stufe die Kursziele
   enthält, ist damit nicht belegt und wäre an der Preisseite zu prüfen.
3. **Zweiter Anbieter nur für Kursziele.** Vermutlich der schlechteste Weg:
   ein zweiter Vertrag, eine zweite Lizenzprüfung und eine zweite
   Fehlerquelle für eine Kennzahl, die den Ausschlag selten gibt.

**Entschieden am 2026-08-13: Weg 1.** Erst einmal ohne Kursziele bauen,
nachrüstbar in einer späteren Ausbaustufe. Ebenso zurückgestellt: EDGAR für
die historischen Termine — als Weg vorgemerkt, nicht jetzt.

Zur Löschpflicht ist festgehalten, dass sie derzeit **nicht ausgelöst** ist:
Die Gratis-Stufe läuft nicht ab, es gibt kein Abonnementende. Ausgelöst
würde sie nicht durch eine Zahlung, sondern durch das Ende des Bezugs
überhaupt — Kontoschließung, Sperrung des Schlüssels, Einstellung der
Gratis-Stufe. Bis dahin besteht keine Pflicht, gespeicherte Daten zu
löschen. Siehe ADR 0017, Einschränkung L6.

## Quellen

- [Finnhub — Earnings Calendar API](https://finnhub.io/docs/api/earnings-calendar)
- [Finnhub — Pricing](https://finnhub.io/pricing)
- [Financial Modeling Prep — Earnings Calendar API](https://site.financialmodelingprep.com/developer/docs/stable/earnings-calendar)
- [Financial Modeling Prep — Pricing Plans](https://site.financialmodelingprep.com/pricing-plans)
- [EODHD — Calendar API](https://eodhd.com/financial-apis/calendar-upcoming-earnings-ipos-and-splits)
- [Alpha Vantage — vollständiger Leitfaden 2026](https://alphalog.ai/blog/alphavantage-api-complete-guide)
- [Best Financial Data APIs in 2026](https://www.nb-data.com/p/best-financial-data-apis-in-2026)
