# ADR 0048: Cash Secured Puts aus der IBKR-Optionskette

- Status: Angenommen
- Datum: 2026-08-31

## Kontext

Berichtspunkt 13 (Doc 10 §6.10) verlangt konkrete **Put-Strategien** zu jedem
Kandidaten. Er war seit dem ersten Bericht leer, und mit ihm die sechste
Komponente des Swing-Scores — die **Optionsattraktivität**, 10 % nach
[ADR 0041](0041-score-komponenten-und-gewichte.md). Der Score rechnete
zuletzt auf 90 % Abdeckung ([ADR 0046](0046-empfehlungsstufe-aus-beiden-scores.md)).

Zwei Dinge unterscheiden diesen Punkt von den übrigen des Sprints. Er ist der
einzige mit einer **Laufzeitabhängigkeit von der TWS** — alles andere rechnet
auf bereits geholten Daten. Und er löst die gerichtete Kopplung endlich ein,
die seit Sprint 1 in CLAUDE.md steht: „Die Optionsanalyse darf die
deterministisch ermittelten Zonen als optionale Eingabe verwenden."

## Entscheidung

### 1. Quelle, Zeitpunkt und Umfang

IBKR über **dieselbe TWS-Verbindung** wie die Kerzen — eine Client-ID, ein
Lock, `IbAsyncBarSource` serialisiert bereits. Nur Lesezugriffe
([ADR 0014](0014-ibkr-produktivintegration-freigegeben.md), Dimension 1).

**Nur Cash Secured Puts, und nur für Kandidaten.** Keine anderen Strategien
(Doc 08), und kein Abruf für Titel, die das Screening nicht bestanden haben —
sonst kostete jeder Lauf 190 Ketten statt einer Handvoll.

**Der Lauf fällt in den offenen Markt.** `market.daily_candle_index: 1` stellt
den Tageslauf auf den Schluss der **ersten** 195-Minuten-Kerze, 12:45 New
Yorker Zeit; mit `scheduler.max_catch_up_seconds: 7200` liegt das ganze
Fenster in der Handelszeit. Der Marktdatentyp ist trotzdem `2` („frozen"):
Bei offenem Markt verhält er sich wie live, und er macht eine Einzelprobe am
Abend brauchbar.

### 2. Ein Verfallstermin je Kandidat, in drei Abrufen

Die Reihenfolge ist der Kern und keine Bequemlichkeit:

| Schritt | Aufruf | Kosten |
|---|---|---|
| Terminliste der Kette | `reqSecDefOptParams` | keine Marktdaten |
| **Ein Termin gewählt** | Domäne | — |
| Gelistete Strikes zu **diesem** Termin | `reqContractDetails` | keine Marktdaten |
| Bis zu 12 Strikes im Moneyness-Band | `reqTickers` | 12 Marktdatenzeilen |

Der dritte Schritt ist ein eigener Abruf, weil ein **gemessener** Befund ihn
verlangt: `reqSecDefOptParams` liefert die *Vereinigung* aller Strikes über
alle Termine, und Wochenoptionen haben engere Abstände als Monatstermine. Ohne
ihn gingen am 2026-08-31 bei AAPL sechs von zwölf Anfragen an Kontrakte, die
es zu diesem Termin gar nicht gibt.

**Der Delta-Filter greift erst danach.** Ein geschätztes Delta vor dem
Snapshot drehte die Reihenfolge um und wäre ein erfundener Wert (CLAUDE.md).
Vorausgewählt wird deshalb über Moneyness (80–99 % des Kurses), gefiltert
über das **tatsächlich gelieferte** Delta.

**Und es ist genau eine Kette, ein Datum.** Die drei Vorschläge sind drei
Strikes desselben Termins. Mehrere Laufzeiten nebeneinander wären ein anderes
Vorhaben — und dreimal so viele Marktdatenanfragen.

### 3. Das Laufzeitfenster ist 21 bis 60 Tage, Ziel 35

Gewählt wird der dem Ziel nächste zulässige Termin. Die Obergrenze ist
**gerechnet, nicht gegriffen**: Dritte Freitage liegen 28 oder 35 Tage
auseinander, ein Fenster ab 21 Tagen muss deshalb mindestens 56 Tage weit
reichen, damit es nie zwischen zwei Monatsverfälle fällt.

Das ist keine Theorie. Der erste Messlauf am 2026-08-31 lief mit 21–45 und
verlor **77 von 192 Titeln** — dritter Freitag September lag 18 Tage
entfernt, Oktober 46. Mit 21–60 fielen im zweiten Lauf noch **6 von 192**
aus, und keiner davon am Termin.

Die Obergrenze *erlaubt* nur; gewählt wird nach dem Ziel von 35 Tagen. Sie
wirkt also allein dort, wo die Alternative „keine Optionsanalyse" hieße.

### 4. Der Berichtstermin schließt Termine aus — die dritte gerichtete Kopplung

**Liegt der nächste bekannte Berichtstermin vor einem Verfall, entsteht zu
diesem Verfall kein Vorschlag.** Gewählt wird der nächstfrühere Termin davor.
Die Prämie über Quartalszahlen hinweg vergütet genau das Risiko, das ein
Put-Verkäufer trägt; sie als Attraktivität zu zählen kehrte die Aussage um.

Verglichen wird strikt (`termin < berichtstermin`), nicht `<=`: Die Quelle
weiß nicht, ob vor der Eröffnung oder nach dem Schluss berichtet wird.

Die drei Bedingungen der gerichteten Kopplungen gelten, und die zweite
präzise: Ein **fehlender** Termin hält nichts auf — „unbekannt" ist kein
belegter Nichttermin. Ein **vorhandener** darf sehr wohl wirken. Die
Bedingungen begrenzen, was fehlende Daten anrichten, nicht was vorhandene
bedeuten. Die Optionsanalyse ermittelt keinen Termin selbst und ändert nichts
an der Entscheidung des Earnings-Filters.

CLAUDE.md wird von „genau zwei" auf **drei** Kopplungen gezogen.

### 5. Die Rechenwege

Alle einfach, keiner mit einem freien Parameter:

| Größe | Formel |
|---|---|
| Kapitalbindung | `strike × 100` |
| Einfache Rendite | `prämie / strike` |
| Annualisierte Rendite | `einfache Rendite × 365 / dte` |
| Break-even | `strike − prämie` |
| Abstand zum Kurs | `(kurs − strike) / kurs` |
| Andienungswahrscheinlichkeit | `abs(delta)`, als **Näherung** gekennzeichnet |
| Abstand zur Unterstützung | aus den Zonen des `TechnicalSnapshot`, sonst leer |

Die Annualisierung ist **linear, nicht aufgezinst** — eine Aufzinsung
unterstellte, dass sich derselbe Verkauf beliebig wiederholen lässt.

**Die Prämie ist der Mittelwert aus Geld- und Briefkurs.** Bei liquiden
Optionen füllt ein Limit meist nahe am Mid; das Geld allein untertriebe die
Rendite bei weitem Spread um zweistellige Prozentsätze. Fehlt eine der beiden
Seiten, entsteht kein Vorschlag — ein halber Mittelwert ist keiner. Geld,
Brief und Mid stehen ohnehin alle drei am Vorschlag.

**Der Aktienkurs** ist der Schluss der letzten abgeschlossenen Kerze, dieselbe
Grundlage wie bei Screening, Chartauswertung und Fundamentalbewertung. Er ist
hier **nicht optional** — ohne ihn gibt es kein Strike-Band —, und er ist
deshalb auch keine vierte Kopplung: Ein Kandidat ohne Kerzenserie entsteht
nicht.

### 6. Liquidität warnt, sie rechnet nicht

`GOOD` / `ACCEPTABLE` / `POOR` aus relativem Spread, Open Interest und
Volumen. Die Schwellen sind **gesetzt**, und die Stufe trägt keinen Teilwert:
Sie erzeugt Warnungen. Doc 10 §6.10 verlangt genau das — unzureichende
Liquidität wird nicht verschwiegen.

### 7. Optionsattraktivität: die annualisierte Rendite des besten Vorschlags

Fünftelgrenzen aus dem Lauf über die Watchliste vom 2026-08-31
(`cli options --watchlist --output`, ausgewertet mit `cli calibrate-scores`):

| Kennzahl | n | ≥ 4 | ≥ 6 | ≥ 8 | ≥ 10 |
|---|---|---|---|---|---|
| Annualisierte Prämienrendite | 186 | 13,88 % | 19,68 % | 24,64 % | 32,44 % |

Spannweite 6,6 % (BRK B) bis 73,8 % (STX). `swing_version` steigt auf **1.2**,
die volle Abdeckung damit auf **100 %**.

**Bewertet wird der bestbewertete Vorschlag**, nicht der Mittelwert über alle
drei. Ein Mittelwert bezöge den weit aus dem Geld liegenden Vorschlag mit ein,
den niemand nimmt, und senkte den Teilwert eines Titels dafür, dass er mehr
Auswahl bietet.

**Ohne gemessene Schwellen entfällt die Komponente** mit benanntem Grund. Der
Fall bleibt vorgesehen: Ein vorläufiger Satz Schwellen trüge eine Zahl in den
Score, die aussähe wie die gemessenen daneben.

## Konsequenzen

**Positiv**

- Berichtspunkt 13 ist gefüllt. Der Bericht ist damit zum ersten Mal
  vollständig — alle vier Lücken aus Sprint 5 sind zu.
- Der Swing-Score rechnet auf 100 % Abdeckung.
- Die erste gerichtete Kopplung aus CLAUDE.md ist nach vier Sprints
  tatsächlich ausgeführt, nicht nur beschrieben.
- Der Messlauf geht durch **denselben Codepfad** wie der Tageslauf: dieselbe
  Terminwahl, dasselbe Strike-Band, derselbe Delta-Filter, dieselbe
  Renditeformel. Die Lehre aus ADR 0045 — zwei Formeln hätten Schwellen
  ergeben, die zu den gemessenen Werten nicht passen.

**Negativ und offen**

- **Der oberste Vorschlag liegt fast immer am oberen Rand des Delta-Bandes.**
  Innerhalb eines Termins steigt die annualisierte Rendite nahezu monoton mit
  dem Delta, und sortiert wird nach Rendite. Das ist kein Fehler, sondern die
  Definition von „attraktiv" bei dieser Sortierung — und der Grund, warum es
  drei Vorschläge sind und nicht einer. Delta, Abstand zum Kurs und Abstand
  zur Unterstützung stehen an jedem; die Wahl zwischen Prämie und
  Sicherheitsabstand bleibt beim Leser.
- **Diese Schwellen sind kurzlebiger als die aus ADR 0045.** Prämien steigen
  und fallen mit der Marktvolatilität gemeinsam, während sich
  Fundamentalkennzahlen quartalsweise bewegen. Eine unruhige Phase verschiebt
  die ganze Verteilung nach oben. Die Neumessung gehört zur Pflege, und hier
  häufiger.
- **Sechs von 192 Titeln lieferten kein Delta** (ADM, ALGN, AME, COR, HRL,
  WST). Die Kette ist da, die Notierungen kommen, `modelGreeks` bleibt leer —
  dünn gehandelte Kontrakte. Die Analyse meldet dann `INSUFFICIENT_DATA` mit
  Grund, der Score rechnet ohne die Komponente weiter.
- **Der Ausschluss über den Berichtstermin kostet Vorschläge.** Wie viele, ist
  noch nicht gemessen: `cli options` ruft den Earnings-Kalender nicht ab, weil
  die Schwellen auf der vollen Verteilung stehen sollen. Im Tageslauf wirkt er.
- **Die Andienungswahrscheinlichkeit ist eine Näherung.** `abs(delta)` ist
  nicht die Wahrscheinlichkeit, im Geld zu verfallen; sie wird deshalb als
  Näherung gekennzeichnet und nicht als Prozentsatz ausgegeben.
- **Die Liquiditätsschwellen sind gesetzt.** Sie ließen sich messen wie die
  Renditegrenzen — aber sie tragen keinen Teilwert, und eine Messung wäre
  Aufwand ohne Folge für eine Zahl.
