# ADR 0045: Schwellen der Score-Teilwerte

- Status: Angenommen
- Datum: 2026-08-31

## Kontext

[ADR 0041](0041-score-komponenten-und-gewichte.md) legt Komponenten und
Gewichte beider Scores fest und schiebt einen Punkt ausdrücklich auf:

> **Die Schwellen**, mit denen eine Kennzahl zu einem Teilwert zwischen 0 und
> 10 wird. Sie entstehen in Sprint 5 und werden an einem Lauf über die volle
> Watchliste kalibriert […] **Das ist eine Voraussetzung, kein Restposten:**
> Ohne die Messung wären die Schwellen geraten, und ein geratener Teilwert ist
> eine erfundene Zahl.

Die Messung liegt jetzt vor.

**Messlauf vom 2026-08-31**, `cli fundamental --watchlist --price-from-bars
--market-data-provider ibkr --provider edgar`, ausgewertet mit
`cli calibrate-scores`:

- 191 Titel der Watchliste, Fundamentaldaten aus SEC-Einreichungen.
- Kurse aus dem gespeicherten Bestand, Kerze vom **2026-08-21** — für **192
  von 192** Titeln vorhanden.
- **Fünf Titel ohne jede Kennzahl:** CHKP, DOX, MGA (ausländische Emittenten,
  Formular 20-F statt 10-K), SPCX (SpaceX, frisch registriert) und XOM. Bei
  XOM zeigt das SEC-Symbolverzeichnis inzwischen auf die neu gegründete
  *ExxonMobil Holdings Corp* (CIK 2115436, 94 Tags, nur Quartalsberichte); die
  Historie liegt unter der alten CIK 34088 (438 Tags). Kein Fehler der
  Auflösung — eine Umstrukturierung.

Der Swing-Score lässt sich **nicht** auf dieselbe Weise kalibrieren: Seine
Komponenten sind Enums und zwei bereits normierte Zahlen, und es gibt bislang
keinen einzigen produktiven Tageslauf, aus dem sich eine Verteilung ergäbe.
Seine Abbildung ist deshalb eine Setzung — und wird hier als solche
gekennzeichnet.

## Entscheidung

### 1. Fünf Stufen: 2 / 4 / 6 / 8 / 10

Jede Kennzahl fällt in eines der fünf gemessenen Fünftel und bekommt den
zugehörigen Teilwert. Das oberste Fünftel bekommt **10**, wie ADR 0041 es
verlangt; das unterste bekommt **2**, nicht 0.

Der Unterschied ist Absicht. Die Watchliste besteht aus rund 190
Großunternehmen. Ein Titel im untersten Fünftel der Nettomarge hat trotzdem
eine Nettomarge — ihm 0 zu geben behauptete, die Kennzahl trage nichts bei.
2 hält die Rangfolge und verschweigt nicht, dass wir relativ zu **dieser
Liste** messen und nicht absolut.

### 2. Investment-Score: gemessene Schwellen

Fünftelgrenzen aus dem Lauf vom 2026-08-31. `n` ist die Zahl der Titel, für
die die Kennzahl vorlag — sie ist Teil des Ergebnisses, nicht Beiwerk.

**Profitabilität (30 %)** — höher ist besser:

| Kennzahl | n | ≥ 10 | ≥ 8 | ≥ 6 | ≥ 4 | sonst |
|---|---|---|---|---|---|---|
| Bruttomarge | 81 | 68,3 % | 58,3 % | 43,9 % | 33,4 % | 2 |
| Operative Marge | 150 | 33,0 % | 21,5 % | 15,0 % | 8,4 % | 2 |
| Nettomarge | 184 | 27,5 % | 17,3 % | 10,9 % | 6,6 % | 2 |
| FCF-Marge | 163 | 28,3 % | 18,2 % | 12,2 % | 6,7 % | 2 |
| Eigenkapitalrendite | 158 | 38,1 % | 24,4 % | 15,9 % | 9,6 % | 2 |
| Gesamtkapitalrendite | 183 | 15,8 % | 9,9 % | 6,2 % | 3,1 % | 2 |

**Wachstum (25 %)** — höher ist besser:

| Kennzahl | n | ≥ 10 | ≥ 8 | ≥ 6 | ≥ 4 | sonst |
|---|---|---|---|---|---|---|
| Umsatzwachstum | 182 | 13,2 % | 8,6 % | 5,1 % | 1,5 % | 2 |
| Gewinnwachstum | 165 | 26,2 % | 11,5 % | 3,6 % | −6,2 % | 2 |

**Bewertung (25 %)** — **niedriger ist besser**, die Skala ist umgekehrt:

| Kennzahl | n | ≤ 10 | ≤ 8 | ≤ 6 | ≤ 4 | sonst |
|---|---|---|---|---|---|---|
| KGV | 157 | 16,4 | 23,3 | 31,2 | 39,8 | 2 |
| KUV | 161 | 1,57 | 2,92 | 4,88 | 7,46 | 2 |
| Kurs/FCF | 134 | 15,2 | 20,5 | 27,2 | 40,1 | 2 |

**Bilanzqualität (20 %)** — Verschuldung und Verwässerung umgekehrt,
Liquiditätsgrad aufsteigend:

| Kennzahl | Richtung | n | Grenzen (20/40/60/80 %) |
|---|---|---|---|
| Verschuldungsgrad | niedriger besser | 107 | 0,61 / 1,07 / 1,71 / 3,40 |
| Liquiditätsgrad | höher besser | 164 | 0,87 / 1,12 / 1,47 / 2,28 |
| Aktienzahl-Wachstum | niedriger besser | 180 | −2,6 % / −1,6 % / −0,4 % / +0,5 % |

### 3. Innerhalb einer Komponente: gleich gewichtet, mit Mindestbesetzung

- Die Kennzahlen einer Komponente werden **gleich gewichtet** gemittelt.
- Fehlende Kennzahlen werden übersprungen; gemittelt wird über die
  vorhandenen — dieselbe Regel wie ADR 0041 sie für die Komponenten setzt.
- Eine Komponente gilt als **verfügbar**, wenn mindestens die **Hälfte** ihrer
  Kennzahlen vorliegt: Profitabilität 3 von 6, Wachstum 1 von 2, Bewertung 2
  von 3, Bilanzqualität 2 von 3.

Das präzisiert ADR 0041, das nur sagt: „Eine Komponente ist verfügbar, wenn
ihre Kennzahlen vorliegen."

### 4. Swing-Score: Setzungen, keine Messung

Ausdrücklich **gesetzt und nicht gemessen** — es gibt keine Verteilung, an
der sich etwas kalibrieren ließe.

| Komponente | Abbildung |
|---|---|
| Technische Signale (25 %) | 3 von 3 Signalen → **10**, 2 von 3 → **6** |
| Historische Signalqualität (25 %) | Trefferquote des **kürzesten** Horizonts × 10 |
| Chart-Setup (15 %) | Mittel aus Trendstärke, Ausbruchsqualität, Einstiegsplausibilität |
| Chance-Risiko (15 %) | `FAVOURABLE` 10, `BALANCED` 6, `UNFAVOURABLE` 2, `NOT_ASSESSABLE` fehlt |
| News- und Ereignislage (10 %) | folgt mit der Empfehlungsstufe (ADR 0046) |
| Optionsattraktivität (10 %) | folgt mit der Optionsanalyse (ADR 0048) |

Die Enums des Chart-Setups:

| Enum | Werte |
|---|---|
| `TrendStrength` | `STRONG` 10, `MODERATE` 7, `WEAK` 4, `ABSENT` 1 |
| `BreakoutQuality` | `CONFIRMED` 10, `TENTATIVE` 6, `NO_BREAKOUT` 4, `FAILED` 1 |
| `SwingEntryPlausibility` | `PLAUSIBLE` 10, `QUESTIONABLE` 5, `IMPLAUSIBLE` 1 |

**Die Signalstatistik wird von ihrer Konfidenz gedeckelt.** Bei
`BacktestConfidence.LOW_SAMPLE` ist der Teilwert auf **6** begrenzt; bei
`INSUFFICIENT_DATA` gilt die Komponente als **nicht verfügbar** — eine
Trefferquote aus drei Ereignissen ist keine Trefferquote. Das ist die erste
der begrenzenden Regeln, die ADR 0041 §4 angekündigt hat; die übrigen folgen
mit ADR 0046.

`NO_BREAKOUT` bekommt 4 und nicht 1: „Es gibt keinen Ausbruch" ist ein
anderer Befund als „der Ausbruch ist gescheitert" — der Docstring des Enums
sagt das ausdrücklich, und die Abbildung soll ihn nicht wieder einebnen.

### 5. Versionierung und Neumessung

Die Schwellen stehen in `config/default.yaml` und sind von
`scoring.long_term_version` umfasst. Sie werden neu gemessen, wenn

- sich die Watchliste wesentlich ändert (Vergleichsraum verschoben) oder
- eine Berichtssaison durch ist, spätestens jährlich.

Eine Neumessung hebt die Version. Alte Ergebnisse bleiben, was sie waren
(Unveränderlichkeit, Doc 10 §6.11).

## Begründung

**Warum Quantile und keine absoluten Schwellen.** Der Lauf enthält eine
Eigenkapitalrendite von **13 587 %** (GDDY, Eigenkapital nahe null) und ein
KGV von **4 368** (CRWD). Ein Mittelwert wäre davon unbrauchbar — das
Durchschnitts-KGV der Liste liegt bei etwa 45, der Median bei 23. Die
Rangfolge stört das nicht. Eine absolute Schwelle wie „Eigenkapitalrendite
über 20 % ist gut" wäre außerdem genau die geratene Zahl, die ADR 0041
ausschließt.

**Warum die Watchliste der Vergleichsraum ist.** [ADR 0032](0032-fundamentalanalyse-deterministisch.md)
L5 hält fest, dass eine Branchen-Vergleichsgruppe fehlt. Die Watchliste ist
die einzige Menge, gegen die verglichen werden kann — und sie ist nicht
Stichprobe eines größeren Marktes, sondern **ist** der Raum, aus dem
Kandidaten kommen. Deshalb rechnet `calibrate-scores` mit
`method="inclusive"`: die Stichprobe als Grundgesamtheit.

**Warum verlustbringende Titel kein billiges KGV bekommen.** Bei negativem
Jahresüberschuss entsteht gar kein KGV (n = 157 statt 191; CNC, GPN, INTC,
KHC und SNAP fehlen). Ein negatives KGV würde in einer umgekehrten Skala als
„sehr günstig" durchgehen. Das Verhalten war schon vorher richtig; hier steht
es als Zusicherung.

## Konsequenzen

**Positiv**

- Beide Scores sind rechenbar. Die letzte Voraussetzung aus ADR 0041 ist
  erfüllt.
- Der Investment-Score steht auf einer nachvollziehbaren Messung, die
  jederzeit mit einem Befehl wiederholbar ist.
- Die Setzungen des Swing-Scores sind als Setzungen benannt und nicht als
  Messergebnis getarnt.

**Negativ und offen**

- **Die Bruttomarge liegt nur für 81 von 191 Titeln vor** — die dünnste
  Kennzahl der Liste, und sie ist eine von sechs Säulen der Profitabilität.
  Bei Banken, Versicherern und Versorgern gibt es sie nicht. Die
  Mindestbesetzung von 3 aus 6 fängt das auf, aber die Profitabilität ist bei
  diesen Titeln auf vier Kennzahlen gestützt.
- **Der Verschuldungsgrad fehlt bei 84 Titeln** (107 von 191). Er ist ein
  Drittel der Bilanzqualität; die Umgewichtung wird dort zum **Regelfall**,
  nicht zur Ausnahme.
- **Der Liquiditätsgrad wird monoton steigend bewertet, obwohl er das nicht
  ist.** Ein Wert von 7,6 (CPRT) ist nicht besser als 2,5, sondern
  gebundenes Kapital. Eine Abbildung mit Optimum bräuchte eine Setzung, wo
  das Optimum liegt — bewusst nicht getroffen, sondern als bekannte
  Vereinfachung ausgewiesen.
- **Die Kurse des Messlaufs sind vom 2026-08-21**, zehn Tage alt, weil der
  Tageslauf noch nie automatisch lief. Für Quantile ist das unerheblich — die
  Rangfolge verschiebt sich in zehn Tagen kaum —, für einen Tageslauf wäre es
  zu alt.
- **Die Schwellen sind eine Momentaufnahme.** Sie beschreiben den Markt von
  Ende August 2026. In einer anderen Bewertungslage verschieben sich die
  Fünftel; deshalb die Neumessung mit Versionssprung.
- **Fünf Titel bekommen dauerhaft keinen Investment-Score**, solange ihre
  Zahlen nicht unter der verlinkten CIK liegen. Ob eine Übersteuerung der
  CIK je Symbol erlaubt wird, ist offen und braucht ein eigenes ADR — sie
  öffnet die Tür zu handgepflegten Zuordnungen.

## Nachtrag vom 2026-08-31: zwei Befunde aus der Umsetzung

Die unabhängige Review der Scoring-Engine hat zwei Punkte aufgeworfen, die
zum ADR gehören und nicht in den Code.

**1. Das Chance-Risiko-Verhältnis geht als Einstufung ein, nicht als Zahl.**

[ADR 0041](0041-score-komponenten-und-gewichte.md) nennt als Grundlage dieser
Komponente `TechnicalSnapshot.chance_risk_ratio` — die aus der Zonengeometrie
gerechnete Zahl. Abschnitt 4 dieses ADR bildet stattdessen
`RiskRewardRating` ab, also die Enum-Einstufung des Sprachmodells. Das ist
Absicht und bleibt so:

- Für die *Zahl* gibt es keine gemessenen Schwellen. Sie war nicht Teil des
  Kalibrierungslaufs, und vier aus der Luft gegriffene Grenzen wären genau
  der geratene Teilwert, den ADR 0041 ausschließt.
- Die Einstufung ist kein Freitext, sondern ein Enum über einer bereits
  gerechneten Zahl (ADR 0026), und `NOT_ASSESSABLE` wird vom Adapter
  **erzwungen**, sobald die Zahl fehlt. Ein Modell kann also nicht einstufen,
  was nicht berechnet wurde.

Der Preis steht im nächsten Punkt. Sobald eine Verteilung der Verhältniszahl
aus produktiven Läufen vorliegt, ist die Ablösung durch gemessene Schwellen
der nächste Schritt — dann wäre die Komponente unabhängig vom Sprachmodell.

**2. Ein Ausfall der KI-Einordnung kostet heute den ganzen Swing-Score.**

Gemessen: Chart-Setup (15 %) und Chance-Risiko (15 %) stehen beide am selben
`TechnicalAssessment`. Fällt es aus, bleiben Signale und Signalstatistik mit
zusammen 50 % — unter der Untergrenze von 60 %, also `INSUFFICIENT_DATA`.

ADR 0041 §3 hatte diesen Fall bei 60 % gesehen, gerade noch oberhalb. Die
fehlenden zehn Prozentpunkte sind die News- und Ereignislage, die bis
[ADR 0046](README.md) nicht gerechnet wird. Es ist damit keine Ausnahme von
der Untergrenze, sondern ihre Anwendung — aber die Folge ist unbeabsichtigt:
Ausgerechnet die beiden Komponenten, die ADR 0041 als „das Einzige, was sich
nachrechnen lässt" bezeichnet, liegen dann vor und werden verworfen.

**Bewusst nicht geändert.** Die Untergrenze zu senken oder die noch nicht
gebauten Komponenten aus dem Nenner zu nehmen wären beides Entscheidungen
über den Zuschnitt des Scores, und die gehören nach ADR 0046 — nicht in eine
stille Anpassung. Bis dahin ist der Fall in
`tests/unit/domain/scoring/test_swing.py` festgehalten, damit er eine
Entscheidung bleibt und keine Überraschung im Tageslauf wird.

**Erledigt am 2026-08-31 durch
[ADR 0046](0046-empfehlungsstufe-aus-beiden-scores.md)** — und zwar ohne
zweite Setzung: Die News- und Ereignislage, deren Abbildung Abschnitt 4
dieses ADR aufgeschoben hatte, füllt genau die zehn Prozentpunkte, die
fehlten. Ein Ausfall der KI-Einordnung liegt damit wieder bei 60 %, und der
Score entsteht. Fallen Einordnung und Analystenabruf gemeinsam aus, bleibt es
bei 50 % und keinem Score.

Auch die Abbildung selbst ist damit nachgetragen: Die Komponente steht auf
dem Anteil der Kauf-Voten, an 187 Titeln derselben Watchliste gemessen. Die
Zeile „folgt mit der Empfehlungsstufe" in Abschnitt 4 ist eingelöst.
