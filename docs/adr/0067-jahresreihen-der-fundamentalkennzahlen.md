# ADR 0067: Jahresreihen der Fundamentalkennzahlen

- Status: Angenommen
- Datum: 2026-09-19

## Kontext

Der Kandidatenbericht zeigt je Fundamentalkennzahl **eine** Zahl: den
Zwölfmonatswert oder, wo keiner vorliegt, den jüngsten Jahreswert
([ADR 0033](0033-zeitbezug-der-fundamentalkennzahlen.md)). Ob eine
Nettomarge von 20 Prozent den Höhepunkt einer Erholung oder das Ende eines
Verfalls beschreibt, steht nirgends. Der Inhaber hat am 2026-09-19 Charts
über die letzten Jahre verlangt — Nettomarge, Nettogewinn, Umsatz.

Die Grundlage liegt vor und wird heute weggeworfen: `_Rechner` baut aus den
Einreichungen eine vollständige Jahresreihe je Rohgröße (`self._jahre`) und
nutzt sie nur für die Wachstumsraten und den Rückfall auf den jüngsten
Jahreswert. Gespeichert wird von ihr allein die Liste der Geschäftsjahre
(`fiscal_years`) — Jahreszahlen ohne Werte.

## Entscheidung

1. **`FundamentalSnapshot.history`** — je abgeschlossenem Geschäftsjahr ein
   `FiscalYearMetrics(period_end, metrics)`, ältestes zuerst. `metrics` ist
   dieselbe Abbildung `MetricName -> Metric` wie der aktuelle Stand.
2. **Dieselbe Rechnung.** Die Kennzahlenkette steht in `_niveaukennzahlen`
   und läuft für den aktuellen Stand wie für jedes Jahr. Der Rechner wird
   je Jahr über `nur_stichtag` festgelegt: Jede Rohgröße ist der Wert
   **dieses** Jahres oder gar keiner. Zwei Fassungen derselben Formel liefen
   sonst auseinander, ohne dass ein Test es merkte — dasselbe Argument wie
   in [ADR 0061](0061-einzelepisoden-des-signal-backtests.md), Punkt 3.
3. **Ohne Bewertung und ohne Wachstumsraten.** Ein Kurs-Gewinn-Verhältnis
   von 2022 bräuchte den Kurs von 2022; den hat das Modul nicht, und der
   heutige Kurs gegen einen alten Gewinn wäre keine historische Bewertung.
   Wachstumsraten sind selbst Mehrjahresgrößen (ADR 0033, Entscheidung 4);
   eine Reihe von Dreijahresraten je Jahr sähe aus wie Jahreswachstum und
   wäre es nicht. Die Umsatzreihe daneben zeigt die Entwicklung unmittelbar.
4. **Fünf Jahre** (`FundamentalParameters.history_years`), am aktuellen Rand
   endend. Ein 10-K weist drei Jahre aus, ältere Einreichungen tragen
   ältere Tags; mehr ist nicht verlässlich zu haben. Wo weniger vorliegt,
   steht weniger — aufgefüllt wird nichts.
5. **Ein Jahr ohne eine einzige rechenbare Kennzahl entsteht nicht.** Ein
   Eintrag mit leerer Abbildung sähe aus wie ein Jahr, in dem alles null war.
6. **Gespeichert als JSONB** in `screening_results.fundamentals_history`
   (Migration `e8b3c5d71a06`) — derselbe Grund wie bei
   `fundamentals_tag_conflicts`: Die Reihe wird im Ganzen geschrieben und im
   Ganzen gelesen, nie einzeln abgefragt.
7. **Keine Rückwirkung.** Alte Auswertungen haben keine Historie; das Feld
   ist dann leer, und das ist eine Auskunft. Eine Nachrechnung aus heutigen
   Einreichungen wäre nicht der damalige Stand.

## Konsequenzen

- **Das Dokument wächst.** Gemessen an der Vorlage: 30 KB für den
  Fundamentalabschnitt, davon 21 KB Historie — vier Jahre, elf Kennzahlen,
  jede mit ihrer Quellenbindung. Bei drei Kandidaten am Tag sind das rund
  15 MB im Jahr, dieselbe Größenordnung wie die Episoden aus ADR 0061. Der
  Preis ist die Quellenbindung aus CLAUDE.md: Jede Zahl eines Charts nennt
  die Einreichung, aus der sie stammt. Eine Archivgrenze bleibt eine
  spätere Entscheidung (Spike-Bericht F12, O11).
- `FUNDAMENTAL_ANALYSIS_VERSION` bleibt: Keine gerechnete Zahl ändert sich,
  es wird nur zusätzlich gespeichert.
- Migration auf dem Server vor dem nächsten Lauf; Reihen ab dem ersten Lauf
  danach.
- Der Fundamental-Reiter zeichnet die Reihen; fehlt die Historie, steht dort
  der Hinweis, dass sie erst ab Läufen nach dieser Änderung entsteht.
