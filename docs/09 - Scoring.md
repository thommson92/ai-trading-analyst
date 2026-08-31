# Bewertungssystem

> **Wozu dieses Dokument.** Es beschreibt das fachliche Soll der beiden
> Scores. Komponenten und Gewichte sind entschieden in
> [ADR 0041](adr/0041-score-komponenten-und-gewichte.md); dieses Dokument
> gibt sie wieder und erklärt sie. Bei Widersprüchen gilt das ADR.
>
> **Die frühere Fassung ist überholt.** Sie nannte fünf gewichtete
> Komponenten je Score, davon beim Investment-Score 35 % auf
> Wettbewerbsvorteile und Managementqualität — beides ohne Datengrundlage
> ([ADR 0032](adr/0032-fundamentalanalyse-deterministisch.md), L5). Der
> Widerspruch zu Doc 10 §6.11 war seit dem Audit vom 2026-08-23 als
> `WIDERSPRÜCHLICH` vermerkt und ist mit ADR 0041 aufgelöst.

## Grundprinzip

Es gibt zwei unabhängige Scores. Sie beantworten verschiedene Fragen und
werden **nie zu einer Gesamtzahl verrechnet**:

| Score | Frage |
|---|---|
| Swing Trade Score | Ist der Einstieg jetzt gut? |
| Long-Term Investment Score | Ist das Unternehmen gut? |

Ein Titel kann als Swing-Kandidat stark und als Investment schwach sein. Genau
das sichtbar zu machen ist der Zweck der Trennung.

Beide Scores liegen zwischen 0 und 10. Beide bestehen aus dokumentierten
Teilkomponenten mit konfigurierbaren, versionierten Gewichten. Beide dürfen
keine Scheingenauigkeit vortäuschen (Doc 10 §6.11).

---

## Swing Trade Score

| Komponente | Gewicht | Grundlage im System |
|---|---|---|
| Technische Signale | 25 % | `ScreeningResult.signals` — die unter Gate G1 freigegebenen Regeln |
| Historische Signalqualität | 25 % | `BacktestResult` je Kandidat ([ADR 0038](adr/0038-backtest-im-tageslauf.md)) |
| Chart-Setup | 15 % | `TechnicalSnapshot` und `TechnicalAssessment` |
| Chance-Risiko-Verhältnis | 15 % | `TechnicalSnapshot.chance_risk_ratio` |
| News- und Ereignislage | 10 % | Analystenempfehlungen ([ADR 0046](adr/0046-empfehlungsstufe-aus-beiden-scores.md)) |
| Optionsattraktivität | 10 % | Optionsanalyse |

**Die Hälfte des Gewichts liegt auf den beiden nachrechenbaren Komponenten.**
Signale und Signalstatistik sind das Einzige am Swing-Score, was sich gegen
die gespeicherten Kerzen prüfen lässt.

**Das Chance-Risiko-Verhältnis hat einen eigenen Anteil**, statt im
Chart-Setup aufzugehen. Es ist die einzige Größe, die den möglichen Gewinn
gegen den möglichen Verlust stellt, und es wird seit `technical-v3`
deterministisch aus der Zonengeometrie gerechnet — ausdrücklich, um es nicht
vom Sprachmodell schätzen zu lassen
([ADR 0026](adr/0026-technical-agent-ki-einordnung.md)).

**Die News- und Ereignislage ist der weichste Eingang** und trägt deshalb nur
10 %. [ADR 0029](adr/0029-research-qualitaet.md) belegt an zwei
Vergleichsläufen, dass die Recherchequellen real meist nur `LIMITED`
abdecken.

Sie steht deshalb **allein auf der gezählten Analystenverteilung** — dem
Anteil der Kauf-Voten am jüngsten Monatsstand, an 187 Titeln der Watchliste
kalibriert und mit einer Aktualitätsschranke von 62 Tagen versehen: Der
Endpunkt liefert den jüngsten Stand, den er kennt, auch wenn der zwei Jahre
alt ist. Die Recherche trägt nichts bei: Ihre Faktoren sind Freitext, und
aus Freitext entsteht nie ein Teilwert. Das ist eine Verengung gegenüber
ADR 0041, kein Austausch, und in
[ADR 0046](adr/0046-empfehlungsstufe-aus-beiden-scores.md) als solche
ausgewiesen.

---

## Long-Term Investment Score

| Komponente | Gewicht | Kennzahlen |
|---|---|---|
| Profitabilität | 30 % | Brutto-, Operating-, Netto- und FCF-Marge, Eigenkapital- und Gesamtkapitalrendite |
| Wachstum | 25 % | Umsatzwachstum, Gewinnwachstum |
| Bewertung | 25 % | KGV, KUV, Kurs/freier Cashflow |
| Bilanzqualität | 20 % | Verschuldungsgrad, Liquiditätsgrad, Verwässerung |

Alle vier stehen vollständig auf Kennzahlen aus SEC-Einreichungen, jede mit
Quelle, Bezugszeitraum und Einheit
([ADR 0032](adr/0032-fundamentalanalyse-deterministisch.md),
[ADR 0033](adr/0033-zwoelfmonatswerte-statt-jahresabschluss.md)).

### Was nicht bewertet wird

**Geschäftsqualität, Wettbewerbsvorteile, Marktposition, Management und die
langfristigen Chancen und Risiken tragen keinen Teilwert.** Sie bleiben
Analysebereiche nach Doc 10 §6.9 und erscheinen als Text im Bericht. Sie
werden nur nicht in eine Zahl übersetzt, solange dafür keine
deterministische Grundlage existiert — die Vergleichsgruppe fehlt, und aus
XBRL-Daten ist sie nicht abzuleiten.

Der Score ist damit **enger, als beide Dokumente ihn ursprünglich zeichneten,
und dafür belegt.** Wer ihn liest, muss wissen: Er enthält keine Aussage über
die Qualität des Geschäftsmodells.

**Die Niveaugrößen sind Kontext, keine Komponente** — Umsatz,
Jahresüberschuss, freier Cashflow, Marktkapitalisierung. Ohne
Vergleichsgruppe und ohne historischen Verlauf ist eine absolute Zahl nicht
bewertbar; „zehn Milliarden Umsatz" ist für sich weder gut noch schlecht.

Sobald die KI-Hälfte der Fundamentalanalyse Einstufungen liefert — als Enums
nach dem Muster von ADR 0026, nie als Zahl aus Freitext —, kommen die
fehlenden Bereiche als Komponenten hinzu und heben `long_term_version`.

---

## Fehlende Komponenten

Fehlende Daten werden sichtbar behandelt, nicht ersetzt.

1. Eine Komponente ist **verfügbar**, wenn ihre Kennzahlen vorliegen.
2. Die Gewichte der verfügbaren Komponenten werden auf 100 % **normiert**.
3. Deckt das verfügbare Gewicht weniger als **60 %** ab, entsteht **kein
   Score**, sondern `INSUFFICIENT_DATA`.

Die Untergrenze ist der Punkt, an dem „fehlende Daten werden sichtbar
behandelt" von einer Kennzeichnung zu einer Folge wird. Ohne sie entstünde
ein Score aus zwei von sechs Komponenten, der im Bericht aussähe wie ein
vollständiger.

Sie ist **gesetzt, nicht gemessen**, konfigurierbar und von der
Scoring-Version umfasst.

**Innerhalb einer Komponente** gilt dieselbe Regel eine Ebene tiefer: Die
Kennzahlen werden gleich gewichtet gemittelt, fehlende übersprungen, und die
Komponente gilt erst ab der Hälfte ihrer Kennzahlen als verfügbar
(ADR 0045). Beim Investment-Score sind das Profitabilität 3 von 6, Wachstum
1 von 2, Bewertung 2 von 3, Bilanzqualität 2 von 3.

### Konfidenz

Die Konfidenz eines Scores steht allein auf seiner Datenabdeckung:

| Abdeckung | Konfidenz |
|---|---|
| unter der Untergrenze | `INSUFFICIENT_DATA` — es entsteht kein Score |
| darüber, aber unter `normal_confidence_coverage` (80 %) | `LOW_COVERAGE` |
| **ab** `normal_confidence_coverage` | `NORMAL` |

Dieselbe Dreiteilung wie bei `BacktestConfidence`, und aus demselben Grund:
Ein Ergebnis auf dünner Grundlage ist nicht falsch, aber es ist etwas anderes
als eines auf voller Grundlage. Die Grenze ist **gesetzt**, konfigurierbar und
von der Scoring-Version umfasst — es gibt nichts, woran sie sich messen ließe.

---

## Score-Ergebnis

An jedem Score stehen (Doc 10 §6.11):

- Gesamtwert,
- Teilwerte,
- Gewichtungen,
- Datenabdeckung,
- Konfidenz,
- positive Faktoren,
- negative Faktoren,
- begrenzende Risiken,
- Berechnungsversion.

**Die Begründung muss mit den Teilwerten übereinstimmen.** Ein Score, dessen
Text etwas anderes sagt als seine Zahlen, ist ein Fehler, keine
Interpretation.

### Begrenzende Risiken

Kritische Risiken deckeln nicht den Score, sondern die **Empfehlungsstufe**
([ADR 0046](adr/0046-empfehlungsstufe-aus-beiden-scores.md)):

| Befund | Wirkung |
|---|---|
| kein Swing-Score | `INSUFFICIENT_DATA`, absorbierend |
| `FalseSignalRisk.HIGH` | höchstens `WATCH` |
| `EarningsFilterStatus.UNKNOWN` | höchstens `CANDIDATE` |
| `BacktestConfidence.INSUFFICIENT_DATA` | keine zusätzliche Deckelung |

Die letzte Zeile ist Absicht: Eine untragbare Stichprobe lässt die
Signalstatistik schon als Komponente entfallen (ADR 0045) und senkt damit die
Datenabdeckung. Sie ein zweites Mal durchschlagen zu lassen bestrafte
dieselbe Tatsache zweimal.

---

## Empfehlungsstufe

Berichtspunkt 16. **Der Swing-Score führt**, denn der Tageslauf sucht
Einstiege, nicht Unternehmen:

| Swing-Score | Stufe |
|---|---|
| ≥ 8 | `STRONG_CANDIDATE` |
| ≥ 6 | `CANDIDATE` |
| ≥ 4 | `WATCH` |
| darunter | `AVOID_FOR_NOW` |

Der Investment-Score **korrigiert um höchstens eine Stufe** — ab 8 hebt er,
bis 4 senkt er. Ein fehlender korrigiert nicht: Fehlende Daten bestrafen
nicht. Danach greifen die begrenzenden Risiken; sie können nur senken.

**Die beiden Scores werden dabei nicht zu einer Zahl verrechnet.** Zwei
Achsen, eine Stufe — und beide Zahlen bleiben im Bericht sichtbar.

---

## Schwellen

Aus welcher Kennzahl welcher Teilwert zwischen 0 und 10 wird, steht in
[ADR 0045](adr/0045-schwellen-der-score-teilwerte.md).

Sie sind **gemessen, nicht gesetzt**: Fünftelgrenzen aus einem Lauf über 191
Titel der Watchliste vom 2026-08-31, ausgewertet mit `cli calibrate-scores`.
Dasselbe Vorgehen wie bei den Zonen
([ADR 0025](adr/0025-deterministische-chartauswertung-und-zonen.md)) und der
Historientiefe ([ADR 0027](adr/0027-historientiefe-messen-vor-anspruch.md)).
Das war eine Voraussetzung, kein Restposten: **Ein geratener Teilwert ist eine
erfundene Zahl.**

Fünf Stufen — 2, 4, 6, 8, 10. Das oberste Fünftel der Watchliste bekommt volle
Punkte, das unterste **2 und nicht 0**: Ein Titel im untersten Fünftel der
Nettomarge hat trotzdem eine Nettomarge.

**Der Swing-Score ist die Ausnahme.** Seine Komponenten sind Enums und zwei
bereits normierte Zahlen, und es gibt noch keinen produktiven Tageslauf, aus
dem sich eine Verteilung ergäbe. Seine Abbildung ist eine **Setzung** und in
ADR 0045 als solche gekennzeichnet.

---

## Versionierung

`scoring.swing_version` und `scoring.long_term_version` stehen an jedem
gespeicherten Ergebnis. Sie steigen, wenn sich Komponenten, Gewichte oder
Schwellen ändern. Der Swing-Score steht bei `1.1`: `1.0` rechnete ohne die
News- und Ereignislage.

Zwei Änderungen sind bereits absehbar:

| Anlass | Wirkung |
|---|---|
| Optionsanalyse wird angeschlossen | Swing-Score rechnet erstmals auf 100 % statt 90 % Abdeckung (`swing-1.2`) |
| KI-Hälfte der Fundamentalanalyse | Investment-Score bekommt die heute unbewerteten Bereiche |

Bis dahin rechnet der Swing-Score auf **90 %** Abdeckung — es fehlt allein
die Optionsattraktivität. Das ist ausgewiesen; es heißt aber, dass die ersten
Scores mit späteren nicht unmittelbar vergleichbar sind.

**Ein Ausfall der KI-Einordnung kostet 30 Prozentpunkte auf einmal:**
Chart-Setup und Chance-Risiko-Verhältnis stehen beide an ihr. Übrig bleiben
60 % — genau die Leiter, die ADR 0041 vorgesehen hatte, und der Score
entsteht weiterhin. Fällt zusätzlich der Analystenabruf aus, sind es 50 %
und es entsteht keiner. Beide Fälle sind in
`tests/unit/domain/scoring/test_swing.py` festgehalten.

---

## Ausgabe

Beispiel, wie es im Bericht erscheint:

```
NVDA

Swing Trade Score          8,5 / 10    Abdeckung 90 %   Konfidenz NORMAL
  Technische Signale      10,0         Gewicht 27,8 %
  Historische Signalgüte   8,5         Gewicht 27,8 %
  Chart-Setup              9,0         Gewicht 16,7 %
  Chance-Risiko            6,0         Gewicht 16,7 %
  News- und Ereignislage   8,0         Gewicht 11,1 %
  Optionsattraktivität     —           fehlt

Empfehlung                 STRONG_CANDIDATE
  Swing-Score 8,5 ergibt STRONG_CANDIDATE
  Investment-Score 9,2 -- bereits die höchste Stufe

Long-Term Investment       9,2 / 10    Abdeckung 100 %  Konfidenz NORMAL
  Profitabilität           9,5         Gewicht 30,0 %
  Wachstum                 9,5         Gewicht 25,0 %
  Bewertung                8,5         Gewicht 25,0 %
  Bilanzqualität           9,0         Gewicht 20,0 %
```

Die Gewichte im Swing-Beispiel sind die **normierten**: Ohne die
Optionsattraktivität verteilen sich die verbleibenden 90 % auf 100 %, aus
25 % werden also 27,8 %. Die fehlende Komponente steht trotzdem in der Liste
— nicht als Null, sondern als Lücke. Sie mit 0 zu bewerten hieße zu
behaupten, die Optionen seien geprüft und unattraktiv.
