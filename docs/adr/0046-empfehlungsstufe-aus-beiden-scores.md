# ADR 0046: Die Empfehlungsstufe entsteht aus beiden Scores

- Status: Angenommen
- Datum: 2026-08-31

## Kontext

Berichtspunkt 16 verlangt eine **konkrete Empfehlung** (Doc 10 §6.12). Die
fünf Stufen stehen dort seit jeher — `STRONG_CANDIDATE`, `CANDIDATE`,
`WATCH`, `AVOID_FOR_NOW`, `INSUFFICIENT_DATA` —, ausdrücklich als
*beispielhaft* bezeichnet. Was fehlte, war die **Ableitung**.

Mit [ADR 0045](0045-schwellen-der-score-teilwerte.md) und Stufe 1 des
Sprints gibt es die Grundlage: Beide Scores rechnen. Zwei Punkte sind damit
fällig, und sie hängen zusammen:

1. Die **News- und Ereignislage** — 10 % des Swing-Scores. ADR 0045 §4 hat
   sie ausdrücklich „mit der Empfehlungsstufe" aufgeschoben.
2. Ein **Befund aus Stufe 1**: Fällt die KI-Einordnung aus, entfallen
   Chart-Setup und Chance-Risiko gemeinsam — beide hängen an demselben
   `TechnicalAssessment`. Mit 50 % Abdeckung entstand **kein** Swing-Score,
   obwohl die beiden nachrechenbaren Komponenten vorlagen. ADR 0041 §3 hatte
   diesen Fall bei 60 % gesehen; die fehlenden zehn Prozentpunkte **sind**
   die News-Komponente.

## Entscheidung

### 1. Die News-Komponente steht auf der gezählten Analystenverteilung

**Grundlage ist allein der Anteil der Kauf-Voten** am jüngsten Monatsstand:

```
ANALYST_BUY_SHARE = (strong_buy + buy) / total
```

Der `ResearchReport` trägt **nichts** dazu bei. Seine positiven und negativen
Faktoren sind Freitext, und aus Freitext entsteht nie ein Teilwert
(CLAUDE.md). ADR 0041 nennt für diese Komponente beide Quellen — das hier ist
also eine **Verengung, kein Austausch**, und sie gehört ausgesprochen.

**Ein gezählter Anteil, keine Konsenszahl.**
[ADR 0043](0043-analystenempfehlungen-statt-kurszielen.md) lehnt eine
Konsenszahl ab, weil deren Gewichte frei gewählt wären; ein Anteil hat keine.
Dasselbe ADR sagt zugleich, dass die Übersetzung in einen Teilwert der
Scoring-Engine zusteht — hier ist sie.

**Gemessen, nicht gesetzt.** Fünftelgrenzen aus dem Lauf über die Watchliste
vom 2026-08-31 (`cli ratings --watchlist --output`, ausgewertet mit
`cli calibrate-scores`):

| Kennzahl | n | ≥ 10 | ≥ 8 | ≥ 6 | ≥ 4 | sonst |
|---|---|---|---|---|---|---|
| Kauf-Anteil | 187 | 81,8 % | 69,9 % | 57,6 % | 43,6 % | 2 |

Spannweite 3,7 % (CLX) bis 94,1 % (NVDA, ANET). Die Komponente ist **nicht
verfügbar** bei `UNKNOWN`, `UNAVAILABLE`, bei einem Monatsstand ohne ein
einziges Votum — und bei einem **zu alten** Stand.

**Die Aktualitätsschranke liegt bei 62 Tagen** (`scoring.analyst_max_age_days`).
Sie ist nötig, weil der Endpunkt keine hat: Er liefert den jüngsten Stand, den
er kennt, und bei einem Titel, der seine Abdeckung verloren hat, ist das einer
von vor zwei Jahren. Ohne Schranke ginge er als heutige Nachrichtenlage mit
vollem Gewicht ein — ein veralteter Wert ist kein fehlender, aber er behauptet
Aktualität. Dasselbe Muster wie bei den Fundamentaldaten
([ADR 0034](0034-fundamentaldaten-nach-dem-watchlist-lauf.md)).

62 Tage sind **gesetzt**, aber nicht gegriffen: Die Voten erscheinen
monatlich; ein ausgefallener Stand geht durch, zwei nicht mehr. Gemessen wird
gegen `evaluated_at` des Ergebnisses und nicht gegen die Uhr — die Domain
kennt keine, und ein gespeichertes Ergebnis soll sich Jahre später genauso
nachrechnen lassen.

Der Monatsstand steht **auch im Erfolgsfall** in der Begründung: Ein
Kauf-Anteil von vor einem halben Jahr ist etwas anderes als der von gestern,
und im Bericht muss man das sehen.

`swing_version` steigt auf **1.1**.

### 2. Der Swing-Score führt, der Investment-Score korrigiert

Der Tageslauf ist ein **Swing-Screener**: Er sucht Einstiege, nicht
Unternehmen. Die Grundstufe kommt deshalb aus dem Swing-Score, entlang der
Skala, aus der er selbst gebaut ist (2/4/6/8/10, ADR 0045) — abgelesen, nicht
gegriffen:

| Swing-Score | Stufe |
|---|---|
| ≥ 8 | `STRONG_CANDIDATE` |
| ≥ 6 | `CANDIDATE` |
| ≥ 4 | `WATCH` |
| darunter | `AVOID_FOR_NOW` |

Der Investment-Score **korrigiert um höchstens eine Stufe**: ab 8 hebt er,
bis 4 senkt er. Ein Investment-Score mit `INSUFFICIENT_DATA` korrigiert
**nicht** — ein fehlender Wert darf nicht bestrafen (CLAUDE.md).

**Kein gemeinsamer Zahlenwert entsteht.** Doc 09 verbietet es, und nicht als
Stilfrage: Ein Titel kann als Swing-Kandidat stark und als Investment schwach
sein, und genau das sichtbar zu machen ist der Zweck der Trennung. Zwei
Achsen, eine Stufe, beide Zahlen bleiben im Bericht sichtbar.

### 3. Begrenzende Risiken — nach der Korrektur

| Befund | Wirkung |
|---|---|
| kein Swing-Score | `INSUFFICIENT_DATA`, **absorbierend** |
| `FalseSignalRisk.HIGH` | höchstens `WATCH` |
| `EarningsFilterStatus.UNKNOWN` | höchstens `CANDIDATE` |
| `BacktestConfidence.INSUFFICIENT_DATA` | **keine zusätzliche Deckelung** |

**Die Reihenfolge ist Teil der Entscheidung.** Stünde die Deckelung vor der
Korrektur, höbe ein starker Investment-Score die Stufe wieder über die
Grenze, die ein hohes Fehlsignalrisiko gerade gezogen hat.

Deckelungen **senken nur**. `AVOID_FOR_NOW` bleibt, wo es ist — eine
Obergrenze ist keine Zuweisung. Und nur *wirksame* Deckelungen werden am
Ergebnis ausgewiesen: Ein Risiko, das die Stufe nicht verändert hat, ließe
eine unveränderte Stufe wie eine gedeckelte aussehen.

Die Konfidenz der Signalstatistik deckelt **nicht** zusätzlich. Sie lässt die
Komponente schon entfallen (ADR 0045) und senkt damit bereits die
Datenabdeckung; sie ein zweites Mal durchschlagen zu lassen bestrafte
dieselbe Tatsache zweimal — das ist keine Vorsicht, sondern ein Rechenfehler.

### 4. Ort und Form

`domain/scoring/recommendation.py`. **Nicht im Report Generator**: Der erzeugt
keine neuen Fakten, er ordnet zu ([ADR 0039](0039-report-generator.md)). Das
Enum `Recommendation` zieht aus `domain.report` nach `domain.scoring` um —
andernfalls entstünde ein Importzyklus.

`RecommendationResult` trägt die **Herleitung** mit: Grundstufe, Korrektur,
angewandte Deckelungen. Doc 10 §12 verlangt für jede Empfehlung
nachvollziehbar, worauf sie beruht — und kein Satz davon stammt aus einem
Sprachmodell.

Berichtspunkt 16 gilt damit als **verfügbar, aber eingeschränkt**: Die
formulierte Zusammenfassung gehört zur KI-Hälfte des Berichts und folgt
getrennt.

### 5. Der Befund aus Stufe 1 ist erledigt

Mit gefüllter News-Komponente liegt der Ausfall der KI-Einordnung wieder bei
**60 %** — genau die Leiter aus ADR 0041 §3. Fallen Einordnung **und**
Analystenabruf gemeinsam aus, sind es 50 % und es entsteht kein Score.
Richtig so, und jetzt ausgeschrieben statt überraschend.

## Begründung

**Warum nicht der Investment-Score als gleichberechtigte Achse?** Weil der
Lauf auf technischen Signalen aufsetzt. Eine Aktie wird Kandidat, weil zwei
von drei Signalen gefeuert haben — nicht, weil ihre Bilanz gefällt. Eine
Empfehlung, die den Investment-Score gleich stark gewichtete, beantwortete
eine Frage, die der Lauf gar nicht gestellt hat.

**Warum überhaupt eine Korrektur und nicht nur der Swing-Score?** Weil der
Unterschied zwischen einem guten Einstieg in ein gutes und in ein schwaches
Unternehmen genau das ist, was zwei getrennte Scores sichtbar machen sollen.
Ihn in der Empfehlung wieder zu verschweigen hieße, die Trennung zu führen
und nicht zu nutzen.

**Warum die Grenzen bei 8, 6 und 4?** Weil der Score aus Stufen von 2, 4, 6,
8 und 10 zusammengesetzt ist. Ein Swing-Score von 8 heißt, dass die
Komponenten im Mittel im obersten Fünftel der Watchliste liegen. Die Grenzen
sind damit aus der Konstruktion abgelesen und nicht die vierte Setzung in
Folge.

## Konsequenzen

**Positiv**

- Berichtspunkt 16 ist gefüllt. Von den vier Lücken aus Sprint 5 bleibt nur
  noch Punkt 13 (Optionsanalyse).
- Der Swing-Score rechnet auf 90 % statt 80 % Abdeckung und übersteht einen
  Ausfall des Sprachmodells.
- Die Herleitung steht am Ergebnis, nicht im Logfile.

**Negativ und offen**

- **Die Stufengrenzen sind gesetzt.** Kalibrieren ließen sie sich erst an
  realisierten Ausgängen — an der Frage also, ob aus einem
  `STRONG_CANDIDATE` ein Gewinn wurde. Diese Daten gibt es nicht und wird es
  vor einem längeren Produktivbetrieb nicht geben.
- **Der Kauf-Anteil unterscheidet „hold" nicht von „sell".** Zwei Titel mit
  je der Hälfte Kauf-Voten bekommen denselben Wert, auch wenn beim einen der
  Rest hält und beim anderen verkauft. Eine Unterscheidung bräuchte Gewichte
  — und damit wäre es die Konsenszahl, die ADR 0043 ausschließt. Bekannte,
  benannte Vereinfachung, wie beim Liquiditätsgrad in ADR 0045.
- **Der Kauf-Anteil ist eine Momentaufnahme.** Er nimmt den jüngsten
  Monatsstand; die Veränderung über mehrere Monate — nach ADR 0043 „ein
  eigenständiges Signal" — bleibt ungenutzt. Sie zu verwerten wäre eine
  weitere Setzung ohne Messgrundlage.
- **`BRK B` bekommt keinen Anteil.** Finnhub führt das Symbol unter einer
  anderen Schreibweise als die IBKR-Watchliste. Dieselbe Klasse von Problem
  wie bei ADR 0017 L3; die Komponente fehlt dann, der Rest rechnet weiter.
- **Vier von 192 Abrufen scheiterten am Ratenlimit** (`429`). Finnhubs
  Gratis-Stufe deckelt bei 60 Anfragen je Minute, der Messlauf lief mit rund
  einer je Sekunde. Der Adapter hält seitdem einen Mindestabstand
  (`finnhub.max_requests_per_second: 0.8`, dieselbe Drossel wie bei EDGAR).
  Auf die gemessenen Fünftel hat der Ausfall keinen Einfluss — 187 Werte
  tragen sie.

  **Eine Drossel je Konto, nicht je Endpunkt.** Die Grenze gilt für den
  Zugangsschlüssel, und der Tageslauf fragt je Kandidat den Earnings-Kalender
  und die Empfehlungen unmittelbar nacheinander. Zwei getrennte Drosseln
  ließen beide ersten Aufrufe sofort durch und verdoppelten die Rate — genau
  der `429`, den die Drossel verhindern soll. `bootstrap` baut sie deshalb
  einmal und reicht sie in beide Adapter.
- **Die Neumessung gehört zur Pflege.** Wie die Schwellen aus ADR 0045
  beschreiben auch diese den Markt von Ende August 2026.
