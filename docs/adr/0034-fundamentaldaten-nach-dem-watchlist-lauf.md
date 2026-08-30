# ADR 0034: Aktualitaetsschranke, Umsatz ohne Vetorecht, drei zugelassene Abweichler

- Status: Angenommen (ergaenzt [ADR 0032](0032-fundamentalanalyse-deterministisch.md)
  und [ADR 0033](0033-zwoelfmonatswerte-statt-jahresabschluss.md))
- Datum: 2026-08-26

## Kontext

ADR 0032 und ADR 0033 sind an sieben Emittenten verifiziert worden. Der erste
Lauf ueber die **volle Watchliste** -- 192 Aktien am 2026-08-26 -- hat vier
Dinge gezeigt, die sieben Faelle nicht zeigen konnten. Drei davon sind
Entscheidungen, eine ist ein Fehler.

Alle Zahlen unten sind an den echten Einreichungen nachgerechnet, nicht
geschaetzt.

### Der Fehler: ein aufgegebenes Tag konserviert eine alte Zahl

Cummins (CMI) stand mit 28 Prozent Abdeckung im Lauf. Nachgerechnet:

```
CMI  COMPLETED  28%
  REVENUE              33.670.000.000  GJ bis 2025-12-31
  NET_INCOME            1.040.000.000  GJ bis 2010-12-31
  NET_INCOME_GROWTH              0,12  GJ bis 2010-12-31
```

Cummins hat ``NetIncomeLoss`` nach 2010 aufgegeben. Der tatsaechliche
Jahresueberschuss 2025 liegt bei rund 3,9 Milliarden. Es stand also ein
fuenfzehn Jahre alter Wert als aktuell im Ergebnis, mit Status ``COMPLETED``,
ohne Kennzeichnung -- und die Wachstumsrate daneben beschrieb die Jahre 2008
bis 2010.

Die Aktualitaetsschranke aus ADR 0033 prueft nur den **Zwoelfmonatswert**.
Der Rueckfall auf die Jahresreihe nahm ungeprueft den juengsten Wert
*derselben* Rohgroesse -- und der ist bei einem aufgegebenen Tag genauso alt
wie das Tag.

Das ist derselbe Fehlertyp wie die Marktkapitalisierung von Berkshire
Hathaway aus der Review zu ADR 0033: eine veraltete Zahl ohne Hinweis, in
einem als vollstaendig gemeldeten Ergebnis. Er verstoesst gegen CLAUDE.md
(„Keine erfundenen Werte") und braucht keine Abwaegung.

Die Schranke hat an anderer Stelle **funktioniert**: Microsoft und Cummins
liefern aus dem aufgegebenen ``SalesRevenueNet`` je einen Zwoelfmonatsumsatz
per 2018, beide wurden verworfen. Sie war nur nicht ueberall angebracht.

### Goldman Sachs verliert alles wegen einer Groesse

```
GS  INSUFFICIENT_DATA  0%
```

bei vollstaendig vorliegender Einreichung: ``NetIncomeLoss`` mit 20
Geschaeftsjahren und einem Zwoelfmonatswert per 2026-06-30, ``Assets``,
``StockholdersEquity``, ``NetCashProvidedByUsedInOperatingActivities``,
``PaymentsToAcquirePropertyPlantAndEquipment`` -- alles da. Der Umsatz war
Bedingung der ganzen Auswertung, und Banken tragen ihre Ertraege als
``RevenuesNetOfInterestExpense``.

### Zwei Standardwerte fehlen wegen zu enger Tag-Listen

| Emittent | taggt | wir suchten |
|---|---|---|
| Illinois Tool Works | nur ``ProfitLoss`` | nur ``NetIncomeLoss`` |
| Monster Beverage | ``NetIncomeLossAvailableToCommonStockholdersBasic`` | nur ``NetIncomeLoss`` |

Beide hatten deshalb **keinen Jahresueberschuss** -- und damit keine
Nettomarge, keine Eigenkapital- und keine Gesamtkapitalrendite. ITW stand bei
39, Monster bei 44 Prozent Abdeckung.

Das ist kein Fehler, sondern der Preis der Gleichbedeutungsregel aus ADR 0032,
Entscheidung 2. Die Frage ist, ob er hier richtig bezahlt ist.

## Entscheidung

### 1. Ein Zeitraumrueckstand von 180 Tagen macht einen Wert ueberholt

Bezugspunkt ist das Ende des juengsten Zeitraumwerts des **ganzen Berichts**,
nicht der jeweiligen Rohgroesse -- sonst ginge der Vergleich bei einem
aufgegebenen Tag immer aus, weil dessen eigene Reihe genauso alt ist. Das ist
derselbe Bezugspunkt, den ADR 0033 fuer den Zwoelfmonatswert eingefuehrt hat;
er gilt jetzt fuer beide Wege und zusaetzlich fuer die Wachstumsrate, die die
Jahresreihe unmittelbar liest.

Ein ueberholter Wert **fehlt**. Es gibt keinen Ersatz und keine Kennzeichnung
„veraltet, aber verwendet".

Die Grenze von 180 Tagen ist gesetzt, nicht gemessen: Darunter koennen nur
Kalenderartefakte liegen, weil ein Geschaeftsjahr mit 52 oder 53 Wochen das
Jahresende um Tage verschiebt, nicht um Monate. Ein halbes Jahr oder mehr
heisst, dass die juengste Einreichung diese Groesse nicht mehr getragen hat.

Sie gilt auch fuer Bestandsgroessen. Im Normalfall greift sie dort nie --
Bilanzstichtage stammen aus dem juengsten Quartalsbericht und liegen vor dem
Bezugspunkt. Wo sie doch greift, ist es derselbe Fall: eine Bilanzposition,
die der Emittent nicht mehr taggt. Ein Liquiditaetsgrad aus einem
Umlaufvermoegen von 2015 waere so falsch wie ein Jahresueberschuss von 2010.

### 2. Der Umsatz gibt den Stichtag vor, hat aber kein Vetorecht

Liegt ein Umsatz vor, definiert sein Periodenende weiterhin den Stichtag, an
dem alle uebrigen Groessen ausgerichtet werden. Fehlt er, uebernimmt das Ende
des juengsten vorliegenden Zeitraumwerts diese Rolle, und es entstehen alle
Kennzahlen, die keinen Umsatz brauchen: Jahresueberschuss, Eigenkapital- und
Gesamtkapitalrendite, Verschuldungsgrad, Liquiditaetsgrad, Verwaesserung,
Gewinnwachstum, Kurs-Gewinn-Verhaeltnis.

Die umsatzabhaengigen Kennzahlen -- alle drei Margen, die
Cashflow-Marge, Umsatzwachstum und Kurs-Umsatz-Verhaeltnis -- fehlen dann
sichtbar, und die Abdeckung sinkt entsprechend.

``INSUFFICIENT_DATA`` bleibt fuer den Fall, dass **gar kein** Zeitraumwert
vorliegt. Nur Bilanzstichtage sind keine Auswertung: Es gaebe keinen
Zeitraum, auf den sich eine Kennzahl beziehen koennte.

Das ist dieselbe Konstruktion, die CLAUDE.md fuer den Kurs vorschreibt --
optionale, nicht blockierende Eingabe, kein Ersatzwert, sichtbare Luecke --
angewandt auf eine zweite Groesse.

### 3. Drei Tags werden nachrangig zugelassen, obwohl sie abweichen

| Rohgroesse | Rang | Tag | Weicht ab um |
|---|---|---|---|
| Jahresueberschuss | 1 | ``NetIncomeLossAvailableToCommonStockholdersBasic`` | Vorzugsdividenden |
| Jahresueberschuss | 2 | ``ProfitLoss`` | Minderheitenanteile |
| Umsatz | 4 | ``RevenuesNetOfInterestExpense`` | Zinsaufwand |

Sie greifen ausschliesslich, wenn kein Tag hoeherer Ordnung etwas hergibt.
Ihre Stelle in der Liste ist die ganze Absicherung: Stuende ``ProfitLoss``
vorn, bekaeme jeder Konzern mit Minderheitenanteilen stillschweigend das
falsche Ergebnis, obwohl das richtige danebenliegt.

Die Abweichung bleibt sichtbar. Der verwendete Tag steht an jedem Wert, und
wo zwei Tags derselben Liste sich fuer denselben Zeitraum widersprechen, wird
das weiterhin gemeldet.

### 4. Die Summe der Verbindlichkeiten wird nicht abgeleitet

Etliche Emittenten -- ITW, Monster, Coca-Cola -- taggen keine Summe
``Liabilities``; der Verschuldungsgrad fehlt dort. Bilanzsumme minus
Eigenkapital waere rechnerisch erreichbar und wird **nicht** gerechnet.

Die Gleichung stimmt nur ohne Minderheitenanteile exakt. Bei einem Konzern
mit Minderheiten erzeugte sie einen systematisch zu hohen Verschuldungsgrad,
der plausibel aussieht -- derselbe Fehler, an dem ADR 0032 die Ableitung des
Rohertrags verworfen hat, nur auf der Bilanzseite.

## Begruendung

Entscheidung 1 ist keine Abwaegung: Eine fuenfzehn Jahre alte Zahl als
aktuell auszuweisen, ist genau das, was das ganze Modul verhindern soll.

Entscheidung 2 und 3 verschieben denselben Regler in dieselbe Richtung --
weg von „nur exakt Gleichbedeutendes", hin zu „fehlend erst, wenn wirklich
nichts da ist". Beide Male gilt: Der Fehler, den die bisherige Strenge
verhinderte, ist ein **verdeckter** (eine falsche Zahl, die richtig
aussieht); der Fehler, den sie erzeugte, ist ein **offener** (eine Luecke,
die man sieht). Wo die Abweichung sichtbar am Wert klebt und der bessere Tag
Vorrang behaelt, ist der verdeckte Fehler nicht mehr moeglich, und dann bleibt
die Strenge nur noch teuer.

Entscheidung 4 zieht die Grenze: Zwischen „anderer Umfang derselben Groesse,
vom Emittenten selbst so berichtet" und „von uns errechnete Groesse, die der
Emittent nicht berichtet" verlaeuft der Unterschied zwischen Rang 2 und
Ablehnung.

## Konsequenzen

**Die Verfahrensversion steigt auf ``fundamental-v3``.** Aeltere Ergebnisse
werden nicht zurueckgerechnet (CLAUDE.md: Unveraenderlichkeit).

Gemessen an acht Emittenten, vorher gegen nachher:

| | vorher | nachher |
|---|---|---|
| GS | INSUFFICIENT_DATA, 0 % | COMPLETED, 61 % |
| CMI Jahresueberschuss | 1,04 Mrd (2010) | 2,72 Mrd (12M bis 2026-06-30) |
| ITW | 39 % | 61 % |
| MNST | 44 % | 72 % |
| JPM | 28 % | 50 % |
| AAPL | 100 %, 0 Widersprueche | **unveraendert** |
| MSFT | 78 % | **unveraendert** |
| KO | 56 % | **unveraendert** |

**Die Zahl gemeldeter Widersprueche steigt deutlich.** Bei Goldman Sachs
21, bei JPMorgan 20 -- saemtlich ``NetIncomeLoss`` gegen
``NetIncomeLossAvailableToCommonStockholdersBasic``. Das ist inhaltlich
richtig (beide Haeuser zahlen Vorzugsdividenden) und war vorher unsichtbar,
verduennt aber das Signal: Ein Widerspruch heisst kuenftig oefter „dieser
Emittent hat Minderheiten oder Vorzugsaktien" und seltener „hier ist die
Tag-Wahl heikel". Apple bleibt bei null.

**LHX bleibt bei 17 Prozent**, jetzt aber aus dem richtigen Grund: Der
Umsatz per 2025-01-03 liegt 364 Tage hinter dem uebrigen Bericht und faellt
unter Entscheidung 1 weg, statt als aktuell zu gelten und alle
umsatzabhaengigen Kennzahlen auf ein altes Datum zu ziehen.

### Akzeptierte Einschraenkungen

- **L1 -- Der Jahresueberschuss ist nicht mehr emittentenuebergreifend
  vergleichbar.** Wo Rang 1 oder 2 gegriffen hat, steht eine leicht andere
  Groesse als bei Rang 0. Der Tag am Wert sagt, welche; ein Vergleich zweier
  Emittenten muss das lesen. Die Alternative war, bei ITW und Monster gar
  nichts zu haben.
- **L2 -- 180 Tage sind eine gesetzte Grenze.** Ein Emittent, der ein Tag
  aufgibt und dessen letzter Wert weniger als ein halbes Jahr zurueckliegt,
  passiert die Schranke. Gemessen ist kein solcher Fall aufgetreten; ein
  Rueckstand entsteht praktisch nur in ganzen Berichtsperioden.
- **L3 -- Kennzahlen mit zwei Bestandsgroessen haengen weiterhin am
  Umsatzstichtag.** Verschuldungsgrad und Liquiditaetsgrad stehen auf zwei
  Werten desselben Bilanzstichtags; sie muessen trotzdem mit dem Stichtag
  des Umsatzes zusammenfallen, sonst entstehen sie nicht. Bei
  Kalenderjahr-Bilanzierern, deren juengster Quartalsbericht mitten im Jahr
  liegt, faellt der Liquiditaetsgrad dadurch aus -- Coca-Cola ist der
  gemessene Fall. Das ist **nicht** entschieden und in ADR 0032/0033 auch
  nicht bedacht; es ist als eigener Punkt offen.
- **L4 -- Die Wirkung auf die volle Watchliste ist nicht nachgemessen.** Die
  Zahlen oben stammen aus acht gezielt ausgewaehlten Emittenten. Der
  Vergleichslauf ueber alle 192 steht aus.

## Nachtrag 2026-08-27: der Vergleichslauf, und was er noch gezeigt hat

Einschraenkung L4 ist eingeloest. Der Lauf ueber alle 192 Symbole ist mit dem
``fundamental-v3``-Stand wiederholt worden; die Zahlen unten stammen aus einer
unabhaengigen Nachrechnung, die den Serverlauf **Zeile fuer Zeile
reproduziert** -- gleicher Median, gleiche Maxima, dieselben 18 Aktien ohne
Zwoelfmonatswert, derselbe eine Fehlschlag.

### Damit ist ADR 0032 L1 beantwortet

191 auswertbare Aktien, ein Fehlschlag (Novo Nordisk, IFRS). Abdeckung:
niedrigste 0 Prozent, Median 67, hoechste 78 -- und 78 ist zugleich das
Erreichbare, weil ohne Kurs die vier bewertungsabhaengigen Kennzahlen bei
jeder Aktie entfallen.

Der mittlere Emittent verliert also **zwei** Kennzahlen ueber die vier
kursabhaengigen hinaus. Welche, ist eindeutig:

| Kennzahl | fehlt bei | Ursache |
|---|---|---|
| Bruttomarge | 110 von 191 (58 %) | ``GrossProfit`` nicht getaggt; ADR 0032 leitet den Rohertrag nicht ab |
| Verschuldungsgrad | 84 von 191 (44 %) | ``Liabilities`` nicht getaggt (Entscheidung 4) und die Stichtagsbindung aus L3 |
| Operative Marge | 41 (21 %) | ``OperatingIncomeLoss`` fehlt bei Banken und Versicherern |
| Eigenkapitalrendite | 33 (17 %) | Stichtagsbindung |
| Freier Cashflow und seine Marge | 27 / 28 (14 / 15 %) | fehlender Investitions- oder Cashflow-Tag |
| Umsatz, Jahresueberschuss | 6 / 5 (3 %) | im Wesentlichen die Nicht-US-Emittenten |

**Zwei Ablehnungen von Ableitungen kosten zusammen die Haelfte der Luecke.**
Das ist der Preis von ADR 0032 L1, jetzt beziffert statt behauptet. Er wird
nicht neu verhandelt: Beide Ableitungen erzeugten eine plausibel aussehende
falsche Zahl.

### Damit ist ADR 0033 L3 beantwortet

19 Aktien ohne einen einzigen Zwoelfmonatswert. Sie zerfallen in vier
Gruppen, und keine davon ist ein Mangel des Verfahrens:

- **Elf** Emittenten mit Geschaeftsjahresende im Mai oder Juni, deren
  Abschluss gerade erst geschlossen hat und fuer die es noch kein Teilstueck
  gibt (ADP, CAH, CTAS, FDX, KLAC, LRCX, MSFT, NKE, ORCL, PG, STX). Der
  Rueckfall auf das Geschaeftsjahr ist dort der **aktuellere** Wert, nicht
  der aeltere.

  Cintas ist der Fall, an dem sich das im Lauf beobachten liess: Zwischen
  zwei Laeufen im Abstand eines Tages wechselten alle neun Kennzahlen von
  ``12M`` auf ``GJ``, bei unveraenderter Abdeckung. Der Zwoelfmonatswert
  endete auf demselben Datum wie das neu in ``companyfacts`` erschienene
  Geschaeftsjahr -- alle drei Jahresperioden tragen das Einreichungsdatum
  2026-07-29. Ein Fenster, das keine zusaetzliche Aktualitaet bringt, weicht
  dem geprueften Abschluss (ADR 0033, Entscheidung 6).
- **Vier** ohne US-GAAP-Daten (CHKP, DOX, MGA, SPCX) -- ADR 0032 L3.
- **Drei** Kalenderjahr-Bilanzierer, deren Umsatz- oder Gewinn-Tag im
  Teilstueck nicht gefuehrt wird (C, KO, XOM).
- **Einer** (LHX), dessen Zwoelfmonatsumsatz unter Entscheidung 1 als
  ueberholt herausfaellt.

### Die Aktualitaetsschranke greift jetzt auch bei der Aktienzahl

Ein dritter Weg an ihr vorbei ist im Vergleichslauf aufgefallen: Die
Verwaesserung bildet ihre eigene Reihe -- eine Einreichung, mehrere
Geschaeftsjahre -- und laeuft weder ueber den aktuellen Wert noch ueber die
Jahresspanne. Bei Exxon endet die verwaesserte Aktienzahl **2013**, der
uebrige Bericht 2025; minus 4,8 Prozent im Jahr standen unbeschriftet neben
Kennzahlen per 2026-03-31.

Dieselbe Schranke, dieselbe Folge: Der Wert fehlt. Die Abdeckung von Exxon
faellt dadurch von 67 auf 61 Prozent -- sechs Punkte, die vorher eine Zahl
aus einem anderen Jahrzehnt waren.

Im Bestaetigungslauf ueber die volle Watchliste steigt die Zahl der Aktien
ohne Verwaesserungsrate von 9 auf 11. Zwei sind neu (Hershey und Lennar),
und beide hatten vorher eine Rate aus einer Einreichung, die der Rest des
Berichts um mehr als ein halbes Jahr ueberholt hatte.

### Ein Ticker kann auf einen Nachfolger ohne Historie zeigen

Exxon Mobil steht im Lauf mit 0 Prozent. Das ist keine Aufloesungsschwaeche:
Der SEC-Index fuehrt ``XOM`` seit einer Umstrukturierung auf CIK 2115436,
``ExxonMobil Holdings Corp``, und dieser Registrant hat bislang
**ausschliesslich 10-Q eingereicht**. Es gibt keinen Jahresabschluss, also
keine Jahresreihe und keinen Baustein fuer ein Zwoelfmonatsfenster. Die
Historie liegt beim Vorgaenger-CIK 34088, den der Index nicht mehr nennt.

Der Lauf meldet dafuer ``INSUFFICIENT_DATA``, und das ist richtig. Ein
Rueckgriff auf den Vorgaenger-CIK waere eine eigene Entscheidung: Er hiesse,
Zahlen einer rechtlich anderen Gesellschaft unter dem Ticker der neuen
auszuweisen.

### Die Begruendung zum zweiten Investitions-Tag war falsch

ADR 0032 hat ``PaymentsToAcquireProductiveAssets`` mit der Messung behalten,
ueber sechs Emittenten hinweg gebe es **keinen** Zeitraum, in dem beide
Capex-Tags verschiedene Werte tragen. Ueber 191 Emittenten stimmt das nicht:

```
PCAR 2015   PropertyPlantAndEquipment  ... ProductiveAssets   660 % Abweichung
ABT  2014   1.077 Mio                  ... 5.290 Mio          391 %
PANW                                                          289 %
ISRG                                                          105 %
```

17 Aktien melden ueberhaupt Capex-Widersprueche. **Die Entscheidung bleibt
trotzdem**, aber mit tragfaehiger Begruendung statt der widerlegten:

- Wo beide Tags vorliegen, gewinnt der erste, und die Abweichung wird
  gemeldet. Der Fehler ist dort sichtbar und wirkungslos.
- Wo nur der zweite vorliegt, macht der Emittent die Unterscheidung gar nicht
  -- 19 der 31 betroffenen Aktien fuehren **keinen** anderen Capex-Tag,
  darunter Home Depot, PepsiCo, Visa, Qualcomm, Chevron und Kroger.
- Wo beide vorliegen und sich ueberlappen, stimmen sie bei 6 von 11
  gemessenen Emittenten auf den Cent ueberein.

Ihn zu streichen kostete 19 Aktien ihren freien Cashflow, seine Marge und das
Kurs-Cashflow-Verhaeltnis -- um einen Fehler zu vermeiden, der genau dort
auftritt, wo er ohnehin erkannt wird.

**L5 (neu):** Wo ausschliesslich ``PaymentsToAcquireProductiveAssets``
vorliegt, laesst sich nicht pruefen, ob der Emittent darunter mehr als
Sachanlagen fasst. Ein zu hoher Investitionsbetrag ergaebe einen zu
niedrigen freien Cashflow -- fehlerhaft in die vorsichtige Richtung, aber
unbemerkt.
