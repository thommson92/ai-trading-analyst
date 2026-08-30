# ADR 0042: Der Backtest bekommt keinen historischen Earnings-Filter

- Status: Angenommen
- Datum: 2026-08-30

## Kontext

Der Live-Filter schließt einen Kandidaten aus, wenn sein nächster
Berichtstermin innerhalb des konfigurierten Fensters liegt — heute 20 Kerzen,
also zehn Handelstage (Doc 10 §6.5). Der Backtest tut das nicht: Er zählt
jeden historischen Qualifikationspunkt, auch die, die der Filter verhindert
hätte.

Der Grund steht in [ADR 0017](0017-finnhub-fuer-earnings-und-ratings.md) als
Einschränkung **L9**: Finnhubs Kalender führt nur künftige Termine.
Historische gibt es dort nicht. Die Kennzahlen messen deshalb eine leicht
andere Strategie als die gehandelte — im Audit vom 2026-08-23 als Risiko
**R6** geführt, die zugehörige Entscheidung als **E3**.

[ADR 0038](0038-backtest-im-tageslauf.md) hat die Abweichung sichtbar
gemacht (`earnings_exclusion_applied` am Ergebnis, Vorbehalt im Bericht) und
E3 ausdrücklich offen gelassen — „vor Sprint 5, wenn das Scoring die Zahl
erstmals wirklich braucht". Mit
[ADR 0041](0041-score-komponenten-und-gewichte.md) ist dieser Zeitpunkt da:
Die historische Signalqualität trägt 25 % des Swing-Scores.

Der vorgemerkte Weg wäre ein Adapter auf `data.sec.gov`, der das
Einreichungsdatum jedes `8-K` mit Item 2.02 („Results of Operations and
Financial Condition") liest — lizenzfrei und kostenlos.

## Entscheidung

**Der historische Earnings-Filter wird nicht gebaut.** E3 ist damit
entschieden, nicht vertagt.

Es bleibt bei dem Zustand, den ADR 0038 hergestellt hat:

- Der Replay zählt weiterhin jeden Qualifikationspunkt.
- `BacktestResult.earnings_exclusion_applied` bleibt `False` und sagt damit
  für jede Zeile die Wahrheit über sich selbst.
- Berichtspunkt 5 führt die Abweichung als Vorbehalt.
- **R6 bleibt in der Nachverfolgung „eingegrenzt", nicht „geschlossen".** Das
  Risiko besteht fort; es ist nur belegt und sichtbar. Die Unterscheidung ist
  Absicht.

Der EDGAR-Weg bleibt vorgemerkt. Diese Entscheidung ist umkehrbar, ohne dass
etwas zurückgebaut werden müsste.

## Begründung

**Ein 8-K-Einreichungsdatum ist der realisierte Termin, nicht der zum
Signalzeitpunkt bekannte.** Das ist der Kern. Doc 10 §6.6 verlangt vom
Backtesting-Modul, „ausschließlich Informationen zu verwenden, die zum
jeweiligen historischen Signalzeitpunkt verfügbar waren". Live entscheidet
der Filter auf einer **Vorhersage** aus dem Kalender — einem Termin, der laut
ADR 0017 L1 auch ein geschätzter sein darf und sich verschieben kann. Ein
Filter auf tatsächlich eingereichten 8-K-Daten benutzt Wissen, das es an der
Entscheidungskerze nicht gab.

Der Adapter tauschte damit eine bekannte Verzerrung gegen eine andere: statt
„zählt Ereignisse, die der Filter verhindert hätte" hieße es „filtert auf
Terminen, die zum Zeitpunkt der Entscheidung noch nicht feststanden". Beide
Abweichungen sind klein, aber nur die erste ist heute vollständig beschrieben
und am Ergebnis vermerkt.

**Der Effekt ist begrenzt und gerichtet.** Vier Berichtstermine im Jahr, je
zehn Handelstage Ausschlussfenster, sind rund 40 von etwa 252 Handelstagen —
knapp 16 %. Betroffen ist die Trefferquote, nicht die Kandidatenerkennung:
Welche Signalkombination wann feuerte, ändert sich durch einen Earnings-Filter
nicht. Ein Score, der 25 % auf eine Kennzahl legt, deren Grundlage um wenige
Prozent verzerrt ist, bleibt brauchbar — solange die Verzerrung dabeisteht.

**Die Kosten wären nicht der Adapter, sondern die Folgearbeit.** `8-K` mit
Item 2.02 ist nicht durchgängig eindeutig: Nicht jede Ergebnisveröffentlichung
trägt das Item, nicht jedes Item 2.02 ist eine Quartalsmeldung, und die
`submissions`-Datei der SEC lagert ältere Einreichungen in Zusatzdateien aus.
Jede dieser Unschärfen erzeugte eine eigene Einschränkung — und eine
Filterlogik, deren Fehlerrichtung wiederum zu messen wäre, wie es bei der
Wochentagsnäherung nötig war ([ADR 0030](0030-wochentagsnaeherung-bleibt.md)).
Dem stünde eine Korrektur von wenigen Prozent an einer von sechs
Score-Komponenten gegenüber.

**Die Alternative ist nicht „ungenau statt genau", sondern „unbekannt statt
bekannt".** Die heutige Abweichung ist beschrieben, an jeder gespeicherten
Zeile vermerkt und im Bericht sichtbar. Genau das verlangt CLAUDE.md: Fehlt
eine Grundlage, bleibt sie fehlend — kein Ersatzwert, keine stille Auslassung.

## Konsequenzen

**Positiv**

- E3 ist entschieden. Die Liste offener Entscheidungen wird kürzer, statt
  einen Punkt in den nächsten Sprint zu schieben.
- Sprint 5 rechnet auf einer Grundlage, deren Grenzen benannt sind.
- Kein zusätzlicher SEC-Abruf je Kandidat und Lauf, keine weitere externe
  Abhängigkeit im Tageslauf.

**Negativ und offen**

- **Die Trefferquoten bleiben die einer ungefilterten Strategie.** Sie fallen
  tendenziell zu hoch aus, wenn Kursbewegungen um Berichtstermine im Mittel
  günstig verliefen, und zu niedrig, wenn ungünstig. Welche Richtung
  überwiegt, ist **nicht gemessen** — auch das gehört zur Entscheidung.
- **R6 besteht fort.** Es ist eingegrenzt, nicht geschlossen.
- Wer den Swing-Score über verschiedene Titel vergleicht, vergleicht
  Kennzahlen mit gleich gerichteter, aber unterschiedlich großer Verzerrung:
  Ein Titel mit stark bewegten Berichtsterminen ist stärker betroffen als
  einer ohne.
- Sollte die Kalibrierung in Sprint 5 zeigen, dass die Signalstatistik
  auffällig streut, ist diese Entscheidung der erste Ort, an dem nachzusehen
  wäre.
