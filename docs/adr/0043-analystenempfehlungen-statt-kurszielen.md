# ADR 0043: Analystenempfehlungen statt Kurszielen

- Status: Angenommen
- Datum: 2026-08-30

## Kontext

Punkt 9 des Berichtsmindestinhalts aus Doc 10 §6.12 lautet
„Analystenmeinungen **und Kursziele**". Beides fehlt heute in
deterministischer Form: Der Abschnitt speist sich allein aus dem Freitext des
Research Agent.

[ADR 0017](0017-finnhub-fuer-earnings-und-ratings.md) hat den Fall bereits
zur Hälfte entschieden. Die Evaluation vom 2026-08-13
(`docs/requirements/earnings-anbieter-evaluation.md`, Prüfpunkt P7) hat beide
Endpunkte gegen den kostenlosen Schlüssel abgerufen:

| Endpunkt | Ergebnis |
|---|---|
| `/stock/recommendation` | **HTTP 200 — in der Gratis-Stufe enthalten** |
| `/stock/price-target` | **HTTP 403 — kostenpflichtig** |

Das ADR beschloss daraufhin Finnhub „als Quelle für Earnings-Termine **und
Analystenempfehlungen**" und hielt als Abgrenzung fest: „Ohne Kursziele … in
einer späteren Ausbaustufe nachrüstbar." Einschränkung **L5** sagt dazu: „Das
Feld gilt als nicht verfügbar. Kein Ersatzwert, keine Schätzung."

Gebaut wurde davon nur der Earnings-Kalender. Die Empfehlungen sind seit
zweieinhalb Wochen entschieden und existieren nicht im Code.

Das Audit vom 2026-08-23 führt die verbliebene Frage als **E11** und knüpft
sie an eine Bedingung: „Erst entscheiden, wenn das Scoring-Design sagt, ob
Kursziele einfließen." Mit
[ADR 0041](0041-score-komponenten-und-gewichte.md) liegt diese Auskunft vor.

## Entscheidung

### 1. Kursziele bleiben dauerhaft zurückgestellt

Weder die sechs Komponenten des Swing-Scores noch die vier des
Investment-Scores enthalten ein Kursziel. Die Bedingung, an die das Audit
E11 geknüpft hat, ist damit beantwortet: **Das Scoring-Design braucht sie
nicht.**

ADR 0017 L5 bleibt unverändert gültig. Berichtspunkt 9 behält seinen
Vorbehalt — er gilt als eingeschränkt, nicht als fehlend, und die Begründung
verweist künftig auf dieses ADR statt auf einen offenen Punkt.

Ausdrücklich ausgeschlossen bleibt auch der dritte Weg: **Kursziele werden
nicht aus dem Freitext der Recherche übernommen**, auch nicht als zitierte
Zahl mit Quelle. Ein Kursziel ist eine Zahl, die Genauigkeit verspricht;
ADR 0029 belegt, dass die Recherchequellen überwiegend Sekundärpresse sind,
und CLAUDE.md untersagt, Werte dieser Art aus Modelltext zu übernehmen.

### 2. Die Analystenempfehlungen werden nachgebaut

`/stock/recommendation` liefert je Symbol vier Monatsstände mit der vollen
Verteilung `strongBuy`, `buy`, `hold`, `sell`, `strongSell`. Der Adapter holt
sie für jeden Kandidaten in Phase 1 des Tageslaufs, nach dem Muster des
Earnings-Filters.

Das Ergebnis wird **roh gespeichert**: die Verteilung je Monatsstand, dazu
Status, Quelle und Abrufzeitpunkt. **Es entsteht keine abgeleitete
Konsenszahl.** Wie aus der Verteilung ein Teilwert wird, entscheidet Sprint 5
zusammen mit den übrigen Schwellen.

Ein Ausfall ergibt `UNAVAILABLE` und hält den Lauf nicht auf — dieselbe
Fehlerisolation wie beim Earnings-Filter und bei den Fundamentaldaten. Kennt
der Anbieter das Symbol nicht, ist das `UNKNOWN` mit Grund `no_coverage`,
nicht „keine Meinung".

Die Empfehlungen fließen in Berichtspunkt 9 und in Punkt 18 (verwendete
Quellen). **Nicht** in die Ergebnismeldung:
[ADR 0040](0040-inhalt-der-ergebnismeldung.md) hält Kennzahlen aus dem
Benachrichtigungskanal heraus, und ADR 0017 L8 untersagt die Weitergabe
abgeleiteter Finnhub-Daten an Dritte.

## Begründung

**Zu 1.** Die Bezahlstufe kostet laut öffentlichen Quellen 11,99 bis 99,99
USD im Monat, und **welche Stufe die Kursziele enthält, ist unbelegt** — es
wäre also ein Abonnement auf Verdacht. Dem stünde eine Kennzahl gegenüber,
die in keinen Teilwert einginge. Sie erschiene allein im Berichtstext.

Die Evaluation hat den Nutzen schon damals eingeordnet: „Die
Empfehlungsverteilung samt ihrer Veränderung deckt die Analystenmeinung ab;
das Kursziel fügt eine Größenordnung hinzu, keine neue Richtung."

Ein zweiter Anbieter nur für Kursziele scheidet aus demselben Grund aus wie
in ADR 0017 — ein zweiter Vertrag, eine zweite Lizenzprüfung und eine zweite
Fehlerquelle für eine Kennzahl, die den Ausschlag nicht gibt.

**Zu 2.** Berichtspunkt 9 steht heute vollständig auf Modelltext. Für einen
Abschnitt, der mittelbar eine Score-Komponente speist, ist das die falsche
Grundlage: CLAUDE.md verlangt, dass Scores nie direkt aus LLM-Freitext
entstehen. Eine gezählte Verteilung von Analystenvoten mit Quelle und
Abrufzeitpunkt ist das Gegenteil davon.

Die Zeitreihe kommt ohne Zusatzaufwand mit. **Die Veränderung der
Analystenmeinung über vier Monate ist ein eigenständiges Signal** — eine
Verschiebung von `hold` nach `buy` sagt mehr über die Lage aus als der
Momentanstand. Das ist mehr, als der ursprünglich geprüfte IBKR-RESC-Weg
geliefert hätte.

**Keine Konsenszahl zu bilden** folgt derselben Überlegung wie beim
Zonenmaß (`ZoneStrength`): Eine gewichtete Summe aus fünf Votenklassen sähe
präzise aus, ohne es zu sein — die Gewichte wären frei gewählt. Die
Rohgrößen stehen am Ergebnis und lassen sich später anders verrechnen, ohne
dass hier ein Zahlenwert vorgibt, wie.

Der Aufwand ist gering, weil die Anbindung an Finnhub steht: derselbe
Schlüssel, derselbe Host, dieselbe Fehlerbehandlung. Es kommt ein Endpunkt
hinzu, kein Anbieter.

## Konsequenzen

**Positiv**

- E11 ist entschieden, und F9 ist zum ersten Mal vollständig umgesetzt,
  soweit die Datenlage es zulässt.
- Berichtspunkt 9 steht auf einer belegten, zitierbaren Grundlage — und
  **auch dann, wenn die Recherche ausgefallen ist.**
- Die Score-Komponente „News- und Ereignislage" bekommt einen Eingang, der
  nicht aus Modelltext stammt.
- Keine laufenden Kosten: Der Endpunkt ist in der Gratis-Stufe enthalten.

**Negativ und offen**

- **Punkt 9 bleibt dauerhaft eingeschränkt.** Doc 10 verlangt Kursziele, und
  es wird sie nicht geben. Das steht im Bericht, aber es bleibt eine
  unerfüllte Anforderung.
- **Ein Abruf mehr je Kandidat.** Bei 10 bis 20 Kandidaten unkritisch, aber
  der Tageslauf hängt an einer weiteren Antwort von Finnhub.
- **Die Abdeckung ist nicht gemessen.** Für die Termine liegt sie bei 97 %
  (ADR 0017); für die Empfehlungen wurde sie an drei Symbolen geprüft, nicht
  an der Watchliste. Fehlende Symbole ergeben `UNKNOWN` und senken die
  Datenabdeckung — sie werden nicht als „keine Meinung" gewertet.
- **Die Löschpflicht aus ADR 0017 L6 gilt auch für diese Daten**, falls der
  Bezug je endet.
- Die Empfehlungen sind eine Fremdmeinung, kein Messwert. Sie sagen, was
  Analysten sagen — nicht, was zutrifft.
