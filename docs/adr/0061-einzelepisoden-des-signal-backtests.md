# ADR 0061: Einzelepisoden des Signal-Backtests werden gespeichert

- Status: Angenommen
- Datum: 2026-09-18

## Kontext

Der Signal-Backtest im Tageslauf ([ADR 0038](0038-backtest-im-tageslauf.md))
speichert je Aktie, Signalkombination und Horizont **Aggregate**:
Trefferquote, mittlere und mediane Rendite, größter Verlust, Drawdown,
Anteil dauerhaft über dem Einstieg, Stichprobengröße. Die gezählten
Ereignisse dahinter — seit [ADR 0057](0057-torbedingungen-und-episoden.md)
die Episoden — entstehen nur flüchtig in `compute_horizon_metrics` und
sind nach dem Lauf nicht mehr zu sehen.

Das Dashboard-Redesign ([ADR 0063](0063-dashboard-redesign.md)) will genau
sie zeigen: den Einstieg jeder Episode als Marker im Kerzenchart, anklickbar
mit dem Ergebnis je Horizont, dazu Verteilung, Best und Worst, Trefferquote
je Zeitraum. „Welche 14 Episoden ergaben diese 71 % Trefferquote?" ist aus
den Aggregaten nicht zu beantworten. Der Optionsbacktest hat denselben Mangel
am 2026-09-05 behoben ([ADR 0058](0058-optionsvorschlaege-im-rueckblick.md),
Nachtrag zu Festlegung 9): Er speichert jeden simulierten Trade.

Zwei Befunde aus der Analyse vom 2026-09-18 prägen die Form:

1. `signal_events.candle_index` ist ein **Index in der Kerzenserie**. Der
   Tiefen-Backfill fügt ältere Bars vorn an und verschiebt damit jeden
   gespeicherten Index. Ein Einstieg, der als Index gespeichert wäre, zeigte
   nach dem nächsten Backfill auf eine andere Kerze.
2. Aggregat und Einzelwert müssen aus **derselben** Rechnung kommen. Zwei
   Fassungen derselben Formel könnten auseinanderlaufen, ohne dass ein Test
   es merkt — der Golden Master vergleicht heute nur die Aggregate.

## Entscheidung

1. **Eine Tabelle `backtest_episodes`, eine Zeile je Episode und Horizont**
   — nach dem Muster von `backtest_results` und
   `options_backtest_trades`: kein Unique-Constraint, kein Update-Pfad, jede
   Auswertung hängt an. Spalten: Aktie, Lauf (NULL bei `cli backtest`),
   Signalkombination, Regelversion, Auswertungszeitpunkt, **`entry_at` als
   Zeitstempel** der Einstiegskerze, Einstiegskurs (Schluss dieser Kerze,
   CLAUDE.md „Backtesting"), Zahl der Trigger der Episode, Zeitstempel des
   letzten Triggers, Horizont, Rendite, größter Verlust, Drawdown,
   dauerhaft über dem Einstieg.
2. **Kein Kerzenindex.** Die Episode wird über `entry_at` mit der Kerzenreihe
   verbunden — im Frontend über Epochenzahlen, nie über Zeichenketten.
3. **Eine Rechnung.** `compute_episode_outcome(series, t, horizon)` liefert
   das Ergebnis eines Ereignisses; `compute_horizon_metrics` mittelt
   ausschließlich darüber, `compute_backtest` gibt Aggregate und Episoden
   gemeinsam zurück. `compute_backtest_results` bleibt als Hülle für
   Aufrufer, die nur die Kennzahlen brauchen. Der Golden Master friert seit
   dieser Änderung auch die Episoden ein; die Aggregate blieben dabei
   byteidentisch.
4. **Erreicht die Historie einen Horizont nicht, sind seine Werte `NULL`** —
   die Zeile steht trotzdem. Ein fehlender Eintrag sähe aus wie ein nie
   gerechneter. Die Aggregate zählen solche Ereignisse wie bisher nicht mit.
5. **Persistiert in derselben Transaktion wie die Aggregate** — im Tageslauf
   mit Lauf-ID, bei `cli backtest` ohne.
6. **Export und API geben alle Auswertungen heraus.** In
   `stocks/{name}/backtest.json` und `GET /api/v1/stocks/{symbol}/backtest`
   steht `episode_evaluations`: je Auswertungszeitpunkt die Episodenliste,
   jüngste zuerst. Das war die Entscheidung des Inhabers vom 2026-09-18 —
   ältere Listen bleiben vergleichbar, auch wenn sich Regel oder Historie
   ändern. Der Preis ist bekannt: rund 35 KB je Kandidat und Lauf, bei drei
   Kandidaten am Tag etwa 25 MB im Jahr. Eine Archivgrenze bleibt eine
   spätere Entscheidung (Spike-Bericht F12, O11).
7. **Keine Rückwirkung.** Alte Auswertungen haben keine Episoden;
   `episode_evaluations` ist dann leer, und das ist eine Auskunft. Eine
   Nachrechnung mit heutigen Bars und heutiger Regel wäre nicht der damalige
   Stand und wird nicht gebaut.

## Konsequenzen

- Migration `c7d1e5a92b04` auf dem Server vor dem nächsten Lauf; die
  Episoden entstehen ab dem ersten Lauf danach.
- `SIGNAL_RULE_VERSION` bleibt: Das Verfahren ändert sich nicht, es wird
  nur zusätzlich gespeichert. Die Aggregate im Golden Master sind unverändert.
- Der Bericht (ADR 0039) bleibt unverändert; die Episoden gehören zur
  Aktienseite, nicht zum Kandidatenbericht.
- Was folgt: der Kerzenchart mit Episoden-Markern (ADR 0064, Phase 5) und
  der Backtest-Explorer (Phase 6) lesen `episode_evaluations`.
