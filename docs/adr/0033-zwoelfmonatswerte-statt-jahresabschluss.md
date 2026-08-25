# ADR 0033: Niveauzahlen und Bewertung auf die letzten zwölf Monate

- Status: Angenommen
- Datum: 2026-08-25
- Löst ab: Entscheidung 3 aus [ADR 0032](0032-fundamentalanalyse-deterministisch.md), soweit sie Quartalszahlen ausschließt

## Kontext

[ADR 0032](0032-fundamentalanalyse-deterministisch.md), Entscheidung 3, hat
das Modul auf Jahresabschlüsse gestellt und den Ausschluss von
Quartalszahlen so begründet:

> Quartalszahlen bleiben vorerst außen vor: Für Wachstum über Jahre tragen
> sie nichts bei und brächten die Saisonalitätsfrage mit, die eigene Regeln
> verlangte.

**Der erste Satz stimmt, der Schluss daraus nicht.** Für Wachstumsraten über
mehrere Jahre ist die Jahresbasis richtig. Umsatz, Margen und vor allem die
Bewertung sind aber keine Mehrjahresbetrachtung, sondern eine Momentaufnahme
— und für die ist ein Jahresabschluss bis zu zwölf Monate alt. Die
Begründung vermengt zwei verschiedene Arten von Kennzahl.

Aufgefallen ist es beim Lesen der Ausgabe: Der Serverlauf vom 2026-08-25
meldete für Apple durchgehend Zahlen zum **2025-09-27**.

## Was der Verzicht kostet

Gemessen am 2026-08-25 gegen `data.sec.gov`. Apples jüngste Einreichung ist
ein 10-Q vom 2026-07-31 mit Zahlen bis zum 2026-06-27:

| | Geschäftsjahr 2025 | Letzte zwölf Monate | Unterschied |
|---|---|---|---|
| Umsatz | 416,2 Mrd | **466,8 Mrd** | **+12,2 %** |
| Nettoergebnis | 112,0 Mrd | **128,9 Mrd** | **+15,1 %** |
| Bilanzsumme | 359,2 Mrd (27.09.2025) | 383,3 Mrd (27.06.2026) | +6,7 % |

Über die sieben geprüften Emittenten hinweg ist der Abstand unterschiedlich
groß, aber nirgends vernachlässigbar — NVIDIA 215,9 gegen **253,5** Mrd
(+17,4 %), Netflix 45,2 gegen 48,4, Uber 52,0 gegen 55,2, Berkshire 371,4
gegen 384,7.

**Am stärksten trifft es die Bewertung**, also genau die Kennzahlen, für die
das Modul den Kurs überhaupt hereinnimmt. Apples gemeldetes KGV von 30,25
setzt den heutigen Kurs gegen ein elf Monate altes Ergebnis; auf
Zwölfmonatsbasis sind es rund **26,3**. Die Aktie sieht im Bericht etwa 15 %
teurer aus, als sie ist.

Gelogen wird dabei nichts — jede Kennzahl trägt ihren Bezugszeitraum, und
`2025-09-27` steht in jeder Zeile. Aber „nicht gelogen" ist der falsche
Maßstab, wenn die aktuelle Zahl vorliegt.

## Entscheidung

### 1. Stromgrößen kommen aus den letzten zwölf Monaten

Umsatz, Ergebnis, Rohertrag, Betriebsergebnis, operativer Cashflow und
Investitionen werden nach der üblichen Formel gebildet:

```
Zwölfmonatswert = Geschäftsjahr
                + laufendes Jahresteilstück
                − Vorjahresteilstück gleicher Länge
```

**Bewusst nicht durch Addition einzelner Quartale.** Ein 10-K weist das
vierte Quartal nicht gesondert aus, es müsste gerechnet werden. Vor allem
aber führt `companyfacts` kumulierte und diskrete Zeiträume nebeneinander:
In Apples Daten stehen zum selben Enddatum ein 90-Tage- und ein
272-Tage-Zeitraum. Wer sie verwechselt, addiert ein Neunmonatsstück zu
Quartalen — wieder eine plausibel aussehende falsche Zahl, derselbe
Fehlertyp, der in ADR 0032 schon dreimal auftrat. Die Formel oben fasst
Zeiträume nie zusammen; sie verrechnet nur Angaben, die der Emittent selbst
so ausgewiesen hat.

### 2. Alle drei Bestandteile stammen aus demselben Tag

Sonst könnte die Subtraktion einen Vertragsumsatz von einem Gesamtumsatz
abziehen — der Berkshire-Fehler aus ADR 0032, nur eine Rechenstufe später
und mit größerem Hebel, weil er als Differenz auftritt.

Erst wird je Tag ein Zwölfmonatswert gebildet, dann entscheidet die
bestehende Tag-Reihenfolge unter denen, bei denen das gelungen ist.
Gemessen: Bei allen sieben Emittenten gelingt es für Umsatz, Ergebnis und
operativen Cashflow **innerhalb eines einzigen Tags**.

### 3. Bestandsgrößen kommen vom jüngsten Stichtag, gleich aus welchem Formular

Bilanzpositionen gelten zu einem Stichtag; der aus dem jüngsten 10-Q ist dem
aus dem letzten 10-K ohne Einschränkung vorzuziehen. Gemessen liegen die
Bilanzstichtage aller sieben Emittenten zwischen dem 2026-04-26 und dem
2026-06-30 — und fallen jeweils mit dem Ende des Zwölfmonatszeitraums
zusammen, weil beides aus derselben Einreichung stammt.

### 4. Wachstumsraten bleiben auf Geschäftsjahren

Hier war ADR 0032 richtig. Eine Dreijahresrate aus Zwölfmonatsfenstern wäre
gegenüber Geschäftsjahren nicht besser, nur schwerer zu prüfen.

### 5. Der Jahreswert ist der Rückfall, nicht der Regelfall

Lässt sich kein Zwölfmonatswert bilden — fehlendes Vorjahresteilstück,
Erstnotiz, unvollständige 10-Q —, trägt die Kennzahl den Jahreswert. Sie ist
davon nicht zu unterscheiden **außer an ihrem Bezugszeitraum**, und genau
den trägt jede Kennzahl seit ADR 0032.

Das ist die Abwägung gegen die strengere Variante („kein
Zwölfmonatswert, keine Kennzahl"): Sie wäre eindeutiger, kostete aber
Abdeckung bei jedem Emittenten mit lückenhaften Quartalsmeldungen — und der
Jahreswert ist nicht falsch, nur älter.

### 6. Kennzahlen mischen die Basis nicht

Eine Marge aus Zwölfmonatsumsatz und Jahresrohertrag wäre falsch. Sie
entsteht gar nicht erst: Die bestehende Regel aus ADR 0032 — beide
Rohgrößen müssen **denselben Stichtag** tragen — greift hier unverändert.
Fällt eine der beiden auf den Jahreswert zurück und die andere nicht, haben
sie verschiedene Stichtage, und die Kennzahl entfällt.

Dass diese Regel den neuen Fall ohne Zutun abdeckt, ist kein Zufall: Sie war
von Anfang an als Schutz gegen genau diese Art Vermischung gedacht.

### 7. `FUNDAMENTAL_ANALYSIS_VERSION` steigt auf `fundamental-v2`

Ein Umsatz nach neuer Regel ist eine andere Zahl. Ein gespeichertes Ergebnis
muss erkennen lassen, nach welchem Verfahren es entstanden ist; alte
Ergebnisse bleiben als `fundamental-v1` erkennbar und werden **nicht**
zurückgerechnet.

## Einschränkungen

| # | Einschränkung |
|---|---|
| **L1** | **Zwölfmonatswerte sind ungeprüft im Sinne des Abschlusses.** Ein 10-Q ist nicht testiert, ein 10-K schon. Der Zugewinn an Aktualität wird mit einem Verlust an Prüfungssicherheit bezahlt. Für eine Bewertungskennzahl ist das der richtige Tausch, für eine langfristige Qualitätsaussage weniger — deshalb bleiben die Wachstumsraten auf Geschäftsjahren (Entscheidung 4). |
| **L2** | **Die Basis kann je Kennzahl verschieden sein.** Entscheidung 5 lässt den Rückfall zu, Entscheidung 6 verhindert nur die Vermischung *innerhalb* einer Kennzahl. Zwei Kennzahlen desselben Berichts können damit verschiedene Zeiträume meinen. Beide tragen ihn; wer sie nebeneinanderstellt, muss ihn lesen. |
| **L3** | **Gemessen an sieben Emittenten.** Wie bei ADR 0032 L1: Die Abdeckung über die volle Watchlist ist nicht gemessen. Beides gehört in denselben Lauf, und dieser ist der Grund, ihn erst jetzt zu machen — eine Messung des alten Verfahrens wäre in dem Moment wertlos geworden, in dem dieses ADR umgesetzt ist. |
| **L4** | **Mehr Abrufe entstehen nicht.** `companyfacts` liefert Jahres- und Quartalsangaben in derselben Antwort. Der Umbau kostet Rechenzeit, keine zusätzliche Übertragung. |

## Konsequenzen

- `domain/fundamentals` bekommt die Zwölfmonatsrechnung; sie ist reine
  Arithmetik und bleibt ohne Infrastruktur.
- `infrastructure/edgar` liest künftig auch `10-Q` und löst Zeiträume nicht
  mehr nur auf Jahre auf. Die Tag-Reihenfolge, die Regel „zuletzt
  eingereicht gewinnt" und die Widerspruchsmeldung bleiben unverändert —
  sie waren nie an die Jahresbasis gebunden.
- Die Ausgabe von `cli fundamental` zeigt den Bezugszeitraum je Kennzahl
  bereits an. Sie muss zusätzlich erkennbar machen, **ob** ein Wert auf
  Zwölfmonats- oder Jahresbasis steht, sonst ist L2 im Bericht nicht
  auflösbar.
- ADR 0032 bleibt unverändert. Entscheidung 3 wird durch dieses ADR
  abgelöst, nicht rückwirkend korrigiert; alle übrigen Entscheidungen und
  Einschränkungen dort gelten fort.

## Alternativen, die nicht gewählt wurden

**Vier diskrete Quartale addieren.** Näher an der Anschauung, aber es
verlangt, das vierte Quartal aus Jahr minus Neunmonatsstück zu rechnen, und
es setzt voraus, diskrete von kumulierten Zeiträumen sauber zu trennen —
zwei zusätzliche Fehlerquellen für dasselbe Ergebnis.

**Jahres- und Zwölfmonatswert nebeneinander ausweisen.** Am transparentesten
und vom Projektinhaber erwogen. Er verdoppelt aber die Felder und die
Persistenz, und das Scoring müsste sich später doch für eines entscheiden —
diese Entscheidung dann ungeschrieben im Scoring-Code statt hier.

**Beim Jahresabschluss bleiben und die Alterung im Bericht ausweisen.** Der
Bericht sagt heute schon, wie alt die Zahl ist. Das Problem ist nicht, dass
niemand es erfährt, sondern dass eine aktuellere Zahl vorliegt und nicht
verwendet wird.

---

### Nachtrag: zwei Fehler aus dem Umbau (2026-08-25)

Beide hat der Lauf gegen echte Einreichungen gezeigt, keiner wäre in einem
Test aufgefallen, der die Annahme des Umbaus geteilt hätte.

**1. Ein aufgegebenes Tag lieferte einen vierzehn Jahre alten
Zwölfmonatswert.** Entscheidung 2 sagt, der Zwölfmonatswert entstehe je Tag
und die Tag-Reihenfolge entscheide anschließend. Bei Honeywell endet
`Revenues` im Jahr 2011 — und weil es in der Liste vorn steht, gewann ein
Zwölfmonatsumsatz **per 2012-06-30**. Die Abdeckung fiel auf 39 Prozent, und
die aktuellste Zahl war die älteste im ganzen Bericht: das genaue Gegenteil
dessen, wozu dieses ADR angetreten ist.

Entscheidung 2 gilt unverändert für die *Bildung*. Für die *Auswahl* gewinnt
jetzt das **jüngste Fenster**; nur bei gleichem Ende entscheidet die
Reihenfolge der Liste, denn dann geht es wieder um die Bedeutung. Zusätzlich
verwirft die Domain einen Zwölfmonatswert, der nicht jünger ist als der
letzte Jahresabschluss — er brächte keine Aktualität und kostete nur die
Prüfungssicherheit aus L1.

**2. Der Jahresreihe kamen zwei Geschäftsjahre abhanden.** Apple wies
plötzlich 17 statt 19 Jahre aus. Ursache war die Reihenfolge von Filtern:
Erst über alle Formulare zusammenfassen und dann auf Jahresabschlüsse
filtern wirft einen Zeitraum **ganz** heraus, sobald ein 10-Q ihn zuletzt als
Vergleichszahl nachgetragen hat. Richtig ist: erst filtern, dann
zusammenfassen.

Der Fehler zeigte in die ungefährliche Richtung — fehlende Jahre statt
falscher Werte —, hätte aber die Wachstumsraten stillschweigend über eine
andere Spanne gerechnet, als sie behaupten.

### Gemessene Wirkung

Alle sieben Emittenten, am 2026-08-25 mit einem Kurs von 100:

| Symbol | Zwölfmonatsende | Umsatz Geschäftsjahr | Umsatz zwölf Monate | Abdeckung |
|---|---|---|---|---|
| AAPL | 2026-06-27 | 416,2 Mrd | **466,8 Mrd** | 100 % |
| NVDA | 2026-04-26 | 215,9 Mrd | **253,5 Mrd** | 100 % |
| PEP | 2026-06-13 | 93,9 Mrd | **96,9 Mrd** | 100 % |
| NFLX | 2026-06-30 | 45,2 Mrd | **48,4 Mrd** | 94 % |
| HON | 2026-06-30 | 37,4 Mrd | **38,1 Mrd** | 89 % |
| UBER | 2026-06-30 | 52,0 Mrd | **55,2 Mrd** | 89 % |
| BRK-B | 2026-06-30 | 371,4 Mrd | **384,7 Mrd** | 50 % |

Apples Kurs-Gewinn-Verhältnis fällt von 30,25 auf **26,28** — die Aktie sah
im Bericht gut 15 Prozent teurer aus, als sie ist.

Berkshires 50 Prozent sind unverändert und haben nichts mit diesem ADR zu
tun: Dort fehlen die Bewertungskennzahlen wegen der veralteten Aktienzahl
(ADR 0032, Korrektur 5) und die Bilanzkennzahlen mangels klassifizierter
Bilanz.

---

### Nachtrag: Befunde der unabhängigen Review (2026-08-25)

Die Review hat alle Messwerte beider Tabellen unabhängig gegen
`data.sec.gov` nachgerechnet — sie reproduzieren sich exakt. Acht Befunde,
alle übernommen; drei davon ändern das Verfahren und gehören deshalb hierher.

**1. Der Widerspruch zwischen zwei Tags wurde beim Zwölfmonatswert nicht
gemeldet.** Entscheidung 2 regelt nur die *Bildung* innerhalb eines Tags, die
*Auswahl* zwischen Tags blieb ungeprüft. Gemessen bei Berkshire Hathaway, für
dasselbe Fenster bis 2026-06-30:

| Tag | Wert |
|---|---|
| `Revenues` | 384,7 Mrd |
| `RevenueFromContractWithCustomerExcludingAssessedTax` | **259,7 Mrd** |

**32 Prozent Unterschied.** Heute gewinnt der richtige — aber nur, weil beide
Fenster am selben Tag enden und dann die Tag-Reihenfolge entscheidet. Endete
der Vertragsumsatz einmal später, gewänne er still, und Umsatz, drei Margen
und zwei Bewertungskennzahlen lägen um ein Drittel daneben. Die Meldung, die
ADR 0032 als Gründungsargument führt, gilt jetzt auch hier.

**2. Bausteine der Zwölfmonatsrechnung stammten teils aus
Vollmachtserklärungen.** `_annual_facts` verlangt einen Jahresabschluss, die
Zwölfmonatsrechnung verlangte gar nichts. Gemessen kam der Jahresbaustein des
Ergebnisses bei **NVIDIA, Netflix und Uber aus einer `DEF 14A`**, Apples
Investitionen aus einem `8-K`. Bei NVIDIA stimmt der Wert der
Vollmachtserklärung auf den Cent mit dem 10-K überein — aber eine Tabelle zur
Vorstandsvergütung ist keine Rechnungslegung. Bausteine und Bilanzstichtage
kommen jetzt ausschließlich aus `10-K`, `10-K/A`, `10-Q` und `10-Q/A`.

Entscheidung 3 sagte „gleich aus welchem Formular". Das ist damit
eingeschränkt auf regelmäßige Finanzberichte.

**3. Die Verwerfung veralteter Fenster prüfte gegen den falschen
Bezugspunkt.** Sie verglich mit der Jahresreihe *derselben* Rohgröße — und
hat ein Tag der Emittent aufgegeben, ist dessen Jahresreihe genauso alt wie
sein Fenster. Gemessen überlebten so ein Rohertragsfenster bis **2012-09-30**
bei Netflix und ein Betriebsergebnisfenster bis **2013-03-31** bei Berkshire.
In den Bericht kam davon nichts, weil die Stichtagsregel aus Entscheidung 6
sie abfing — aber das war Glück der Zusammensetzung, nicht die Prüfung.
Maßgeblich ist jetzt der jüngste Jahresabschluss des **ganzen Berichts**.

Dabei ist ein zweiter Fehler entstanden und behoben worden: Zählt man die
Bilanzstichtage mit, liegt der Bezugspunkt seit Entscheidung 3 auf demselben
Datum wie das Fensterende — und *kein* Fenster wäre je jünger. Der Bezugspunkt
zählt deshalb nur Zeitraumgrößen.

**Kleinere Befunde**, ohne Wirkung auf das Verfahren: Der Fensteranfang war
aus der Jahreslänge zurückgerechnet statt aus der tatsächlichen Grenze des
Vorjahresstücks (bei Honeywell ein Tag daneben, ein Datum, das nirgends
steht); unter mehreren Vorjahresstücken innerhalb der Toleranz entschied die
Reihenfolge im JSON; `float("NaN")` hätte jede Schutzregel überlebt, weil
alle Vergleiche mit NaN falsch sind.

**Was die Review bestätigt hat:** Die Formel kann kumulierte und diskrete
Quartale nicht verwechseln — `laufend` wählt immer das längste Stück ab
Jahresbeginn, und das Gegenstück wird über die Länge gesucht. Keine Kennzahl
kann Zwölfmonats- und Jahreswerte mischen. Wachstumsraten und Verwässerung
rechnen unverändert auf Geschäftsjahren.
