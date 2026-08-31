# ADR 0041: Komponenten und Gewichte der beiden Scores

- Status: Angenommen
- Datum: 2026-08-30

## Kontext

Sprint 5 baut Optionsanalyse, Swing Score und Investment Score. Aus welchen
Komponenten die beiden Scores bestehen, sagen zwei Dokumente
unterschiedlich:

| | `docs/09 - Scoring.md` | `docs/10 - System Architecture.md` §6.11 |
|---|---|---|
| Swing Trade Score | fünf, gewichtet | sechs, ohne Gewichte |
| Long-Term Investment Score | fünf, gewichtet | acht, ohne Gewichte |

Der übliche Ausweg greift nicht.
[ADR 0001](0001-dokumentenhierarchie.md) macht Doc 10 bei Widersprüchen
maßgeblich, nimmt aber **genau diesen Punkt ausdrücklich aus**: „Der offene
Punkt beim Swing-Score (fünf oder sechs Komponenten) bleibt eine fachliche
Frage und wird nicht durch diese Rangfolge entschieden."

Das Audit vom 2026-08-23 führt `docs/09` seither als `WIDERSPRÜCHLICH` mit
der Auflage, vor Sprint 5 zu entscheiden. Zwei Feststellungen aus der
Durchsicht kommen hinzu, die das Audit so nicht führt:

- **Der Widerspruch betrifft beide Scores**, nicht nur den Swing-Score. Das
  Audit nennt nur die fünf gegen sechs.
- **Doc 09 legt 35 % des Investment-Scores auf Komponenten ohne
  Datengrundlage.** Wettbewerbsvorteile (20 %) und Managementqualität (15 %)
  sind nicht gerechnet und auch nicht rechenbar:
  [ADR 0032](0032-fundamentalanalyse-deterministisch.md) L5 hält fest, dass
  die Vergleichsgruppe fehlt. Doc 10s zusätzliche Komponenten Profitabilität
  und Bilanzqualität stehen dagegen als `MetricName`-Kennzahlen bereit.

Ein dritter Punkt ist eine Beobachtung am Code: Das Chance-Risiko-Verhältnis
steht nur in Doc 10 — und wird seit `technical-v3` deterministisch berechnet,
weil [ADR 0026](0026-technical-agent-ki-einordnung.md) es als
Scoring-Komponente aus Doc 10 §6.11 aufgegriffen hat. Der Code folgt in
diesem Punkt bereits Doc 10.

## Entscheidung

### 1. Swing Trade Score — sechs Komponenten nach Doc 10

| Komponente | Gewicht | Grundlage |
|---|---|---|
| Technische Signale | 25 % | `ScreeningResult.signals` (Gate G1) |
| Historische Signalqualität | 25 % | `BacktestResult` je Kandidat (ADR 0038) |
| Chart-Setup | 15 % | `TechnicalSnapshot` und `TechnicalAssessment` |
| Chance-Risiko-Verhältnis | 15 % | `TechnicalSnapshot.chance_risk_ratio` |
| News- und Ereignislage | 10 % | `ResearchReport`, Analystenempfehlungen |
| Optionsattraktivität | 10 % | Optionsanalyse (Sprint 5) |

### 2. Long-Term Investment Score — vier Komponenten

| Komponente | Gewicht | Kennzahlen |
|---|---|---|
| Profitabilität | 30 % | Brutto-, Operating-, Netto- und FCF-Marge, ROE, ROA |
| Wachstum | 25 % | Umsatzwachstum, Gewinnwachstum |
| Bewertung | 25 % | KGV, KUV, Kurs/FCF |
| Bilanzqualität | 20 % | Verschuldungsgrad, Liquiditätsgrad, Verwässerung |

Wettbewerbsvorteile, Managementqualität, Marktposition und die langfristigen
Chancen und Risiken **werden nicht bewertet**. Sie bleiben Analysebereiche in
Doc 10 §6.9 und stehen als Text im Bericht — sie tragen nur keinen Teilwert,
solange es keine deterministische Grundlage für einen gibt.

Die Niveaugrößen — Umsatz, Jahresüberschuss, freier Cashflow,
Marktkapitalisierung — sind **Kontext, keine Komponente.** Ohne
Vergleichsgruppe und ohne historischen Verlauf ist eine absolute Zahl nicht
bewertbar; „zehn Milliarden Umsatz" ist für sich weder gut noch schlecht.

### 3. Fehlende Komponenten werden umgewichtet, mit Untergrenze

- Eine Komponente ist verfügbar, wenn ihre Kennzahlen vorliegen.
- Die Gewichte der verfügbaren Komponenten werden auf 100 % normiert.
- Am Ergebnis stehen Gesamtwert, Teilwerte, Gewichte, Datenabdeckung,
  Konfidenz und die Liste der fehlenden Komponenten (Doc 10 §6.11
  „Score-Ergebnis").
- Deckt das verfügbare Gewicht weniger als **60 %** ab, entsteht **kein
  Score**, sondern `INSUFFICIENT_DATA`. Die Schwelle ist konfigurierbar und
  von der Scoring-Version umfasst.

Wirkung auf den Swing-Score: Ohne Optionsanalyse bleiben 90 % — er rechnet ab
dem ersten Tag. Fällt zusätzlich die Recherche aus, 80 %. Fehlt darüber
hinaus die Signalstatistik, 55 %, und es gibt keinen Score.

### 4. Was dieses ADR ausdrücklich nicht entscheidet

- **Die Schwellen**, mit denen eine Kennzahl zu einem Teilwert zwischen 0 und
  10 wird. Sie entstehen in Sprint 5 und werden an einem Lauf über die volle
  Watchliste kalibriert — dasselbe Vorgehen wie bei den Zonen
  ([ADR 0025](0025-deterministische-chartauswertung-und-zonen.md), Revision
  nach dem ersten Realllauf) und der Historientiefe
  ([ADR 0027](0027-historientiefe-messen-vor-anspruch.md)). **Das ist eine
  Voraussetzung, kein Restposten:** Ohne die Messung wären die Schwellen
  geraten, und ein geratener Teilwert ist eine erfundene Zahl.
- **Die Ableitung der Empfehlungsstufe** (Berichtspunkt 16) aus beiden
  Scores.
- **Die Regel für begrenzende Risiken.** Doc 10 §6.11 verlangt, dass
  kritische Risiken einen Score deckeln können. Kandidaten sind
  `FalseSignalRisk.HIGH`, `EarningsFilterStatus.UNKNOWN` und
  `BacktestConfidence.INSUFFICIENT_DATA`; die Regel folgt mit den Schwellen.

## Begründung

**Zu 1 — warum die Gewichte von Doc 09 abweichen.** Doc 09 nennt Gewichte,
aber keine Herleitung; sie sind der einzige vorhandene Anhaltspunkt, kein
Messergebnis. Drei Verschiebungen:

Die beiden deterministischen Komponenten — die unter Gate G1 freigegebenen
Signale und die am Bestand gemessene Signalstatistik — behalten zusammen die
Hälfte des Gewichts. Sie sind das Einzige am Swing-Score, was nachgerechnet
werden kann.

Das Chance-Risiko-Verhältnis bekommt einen eigenen Anteil statt im
Chart-Setup aufzugehen. Es ist die einzige Größe, die den möglichen Gewinn
gegen den möglichen Verlust stellt — für eine Einstiegsentscheidung die
Kernfrage. Es aus der Zonengeometrie zu rechnen war bereits eine bewusste
Entscheidung gegen eine Schätzung durch das Sprachmodell (ADR 0026); ihm
kein Gewicht zu geben, machte diese Arbeit folgenlos.

Die News- und Ereignislage sinkt von 15 auf 10 %. Sie ist der weichste
Eingang, und [ADR 0029](0029-research-qualitaet.md) belegt an zwei
Vergleichsläufen, dass die Abdeckung real meist `LIMITED` ist. Ein hohes
Gewicht auf einer dünn belegten Größe erzeugt Scheingenauigkeit — genau das,
was Doc 10 §6.11 untersagt.

**Zu 2 — warum vier statt acht oder fünf.** Beide Dokumente führen
Komponenten, die das System nicht messen kann. Doc 09 gibt ihnen 35 % des
Investment-Scores. Ein Score, dessen größter Einzelblock dauerhaft leer
bliebe, wäre entweder ständig `INSUFFICIENT_DATA` oder er würde die
verbleibenden 65 % hochnormieren und dabei so tun, als hätte er die Frage
nach Wettbewerbsvorteilen beantwortet.

Die vier gewählten Komponenten stehen dagegen vollständig auf gerechneten
Kennzahlen aus SEC-Einreichungen mit Quelle, Bezugszeitraum und Einheit
(ADR 0032, ADR 0033). Der Score ist damit kleiner als in beiden Dokumenten
vorgesehen — und dafür belegt.

Bilanzqualität kommt neu hinzu, obwohl Doc 09 sie nicht kennt: Verschuldung
und Liquidität sind zwei der fünfzehn Analysebereiche aus Doc 10 §6.9, sie
sind gerechnet, und ein Investment-Score, der die Bilanz übergeht, wäre bei
einem hoch verschuldeten Titel offensichtlich falsch.

**Zu 3 — warum umgewichten und nicht aussetzen.** Ohne Umgewichtung gäbe es
bis zum Ende von Sprint 5 überhaupt keinen Swing-Score, weil die
Optionsattraktivität fehlt. Ohne Untergrenze entstünde umgekehrt ein Score
aus zwei von sechs Komponenten, der im Bericht aussähe wie ein vollständiger.
Die Untergrenze ist die Stelle, an der „fehlende Daten werden sichtbar
behandelt" (Doc 10 §6.11) von einer Kennzeichnung zu einer Folge wird.

60 % ist gewählt, nicht gemessen. Der Wert lässt den Swing-Score ohne
Optionsanalyse und ohne Recherche noch rechnen, verweigert ihn aber, sobald
zusätzlich die Signalstatistik fehlt — der Punkt, ab dem vom Score nichts
Deterministisches mehr übrig ist. Er ist konfigurierbar und wird mit den
Schwellen überprüft.

## Konsequenzen

**Positiv**

- Sprint 5 beginnt ohne offene Grundfrage.
- `docs/09` und Doc 10 §6.11 widersprechen sich nicht mehr; der Punkt, den
  ADR 0001 offen gelassen hat, ist geschlossen.
- Jede Komponente beider Scores hat eine benannte Datenquelle. Es gibt keine,
  die auf ein nicht existierendes Modul zeigt — außer der Optionsattraktivität,
  und die kommt im selben Sprint.
- Der Investment-Score steht vollständig auf zitierbaren SEC-Zahlen.

**Negativ und offen**

- **Der Investment-Score ist enger als beide Dokumente ihn zeichnen.** Er
  bewertet, was gerechnet ist, und schweigt zu Marktposition, Wettbewerbs-
  vorteilen und Management. Wer ihn liest, muss wissen, dass er keine Aussage
  über die Qualität des Geschäftsmodells enthält. Der Bericht führt diese
  Bereiche weiterhin als Text.
- **Die Gewichte sind gesetzt, nicht hergeleitet.** Sie sind besser begründet
  als die aus Doc 09, aber an keiner Ergebnisreihe geprüft. Erst eine
  Auswertung realer Läufe kann zeigen, ob die Verteilung trägt; sie hebt dann
  `scoring.swing_version` beziehungsweise `scoring.long_term_version`.
- **Ohne die Kalibrierung ist das ADR nicht umsetzbar.** Komponenten und
  Gewichte allein ergeben keinen Score.
- **Der Swing-Score rechnet bis zum Ende von Sprint 5 auf 90 % Abdeckung.**
  Das ist ausgewiesen, aber es heißt, dass die ersten Scores nicht mit
  späteren vergleichbar sind.
