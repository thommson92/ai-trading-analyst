# ADR 0062: Kurzlisten aus dem gespeicherten Bericht, Sperrstatus rekonstruiert, zwei Übersichtsdateien

- Status: Angenommen
- Datum: 2026-09-18

## Kontext

Das Dashboard-Redesign ([ADR 0063](0063-dashboard-redesign.md)) braucht für
Übersicht, Tagesläufe und Aktienliste mehr, als die Kurzliste eines Laufs
heute hergibt: Sie nennt nur Empfehlung und beide Scores. Die Kandidatenkarte
soll zuerst die Nähe zum Berichtstermin und den besten Put-Vorschlag zeigen,
dazu Signalbuchstaben, Fehlsignalrisiko und den Kurs zum Zeitpunkt der
Entscheidung. Drei weitere Lücken aus der Analyse vom 2026-09-18:

1. **Die Wiederholsperre lässt Symbole spurlos verschwinden.** Ein kürzlich
   voll analysierter Titel verlässt den Lauf, bevor irgendetwas für ihn
   gerechnet wird ([ADR 0054](0054-wiederholsperre-im-tageslauf.md)). Er
   hinterlässt keine Zeile; „gesperrt" und „kein Kandidat" sind in den Daten
   nicht zu unterscheiden.
2. **Es gibt keine Aktienliste.** Das Manifest kennt nur Symbole; welchen
   letzten Stand eine Aktie hat, verlangte 192 Einzeldateien.
3. **Es gibt keinen Signal-Backtest über alle Aktien.** Die Backtest-Seite
   zeigt nur den Optionsbacktest; der Signal-Backtest liegt je Aktie.

Außerhalb des Servers gibt es keine Abfrage — jede Datei wird als Ganzes
geladen ([ADR 0060](0060-dashboard-ausserhalb-des-servers.md)). Der Schnitt
der Dateien ist damit eine Architekturfrage, keine Darstellungsfrage.

## Entscheidung

1. **Die Kurzliste liest aus dem gespeicherten Dokument, nicht aus den
   Analysezeilen daneben.** `domain/report/summary.py` kennt den Aufbau des
   Dokuments und liest defensiv: Ein Abschnitt mit `verfuegbar: false` oder
   ein Feld, das eine ältere Schemafassung nicht hat, ergibt `None` — kein
   Fehler, kein Ersatzwert. Grund: Das Dokument ist der eingefrorene Stand
   des Laufs ([ADR 0039](0039-report-generator.md)); eine Liste, die etwas
   anderes zeigte als die Einzelsicht, wäre eine zweite Wahrheit. Die
   Kurzfassung trägt Unternehmen, Kurs und Zeitstempel der
   Entscheidungskerze, Signalbuchstaben (dieselbe Zuordnung wie im
   Backtest), Fehlsignalrisiko, Earnings-Status mit Termin und Kerzen bis
   dahin, Optionsstatus mit Grund und den ersten Put-Vorschlag. Die Prämie
   steht je Aktie, wie im Bericht — das Frontend rechnet keine Kontrakte.
2. **Der Sperrstatus je Lauf wird rekonstruiert, nicht aufgezeichnet.**
   Dieselbe Rechnung wie im Lauf — Sperrfenster ab dem Startzeitpunkt des
   Laufs in Börsenzeit, jüngste volle Analyse je Symbol — minus die Symbole,
   die der Lauf tatsächlich bewertet hat. Jeder Eintrag nennt den Lauf, der
   die Sperre ausgelöst hat. `suppression_window_days` sagt, mit welchem
   Fenster gerechnet wurde, und `null`, dass nicht gerechnet wurde.
   **Die Grenzen sind bekannt:** Das
   Fenster ist das heutige, nicht das von damals; ein Symbol, das die
   Watchlist verlassen hat und kurz zuvor Kandidat war, erschiene als
   gesperrt; Läufe vor ADR 0054 zeigen keine Sperren. Ein Lauf ohne eine
   einzige Ergebniszeile — gescheitert vor dem Screening oder noch
   unterwegs — wird nicht gerechnet (`suppression_window_days: null`),
   sonst stünde dort „alles im Fenster". Damit Lauf und Rekonstruktion
   dasselbe Fenster sehen, rechnet auch der Lauf seit diesem ADR vom
   gespeicherten Startzeitpunkt, nicht von „jetzt". Exakt wäre eine
   JSONB-Spalte an `analysis_runs`, die der Lauf selbst füllt — das wäre eine
   Migration und gälte nur ab dann. Der Inhaber hat sich am 2026-09-18 gegen
   die Migration entschieden; die Alternative bleibt hier notiert.
3. **Zwei Übersichtsdateien:** `data/stocks.json` (alle Aktien mit
   Stammdaten, Zahl der Berichte, letztem Bericht als Kurzfassung, Stand der
   jüngsten Backtest-Auswertung, ob Episoden vorliegen) und
   `data/signal-backtests.json` (je Aktie die jüngste Auswertung mit allen
   Kombinationen). Beide entstehen aus je einer Abfrage pro Quelle, nicht
   aus einer je Aktie, und stehen als `GET /api/v1/stocks` und
   `GET /api/v1/signal-backtests` auch in der Lese-API — derselbe Code in
   `presentation/api/views.py`, wie bei allem, was der Export schreibt.
4. **Die Kurzliste trägt den Lauf.** `analysis_run_id` ist eine Spalte an
   `stock_reports` und steht jetzt an jedem Listeneintrag, damit eine
   Aktienhistorie in den Tageslauf springen kann.

## Konsequenzen

- Eine Migration nur für einen Index auf `screening_results(status,
  evaluated_at)`: Die Sperrabfrage läuft jetzt je Lauf statt einmal am Tag.
  Sonst ist die Änderung rein lesend. Export und API bleiben im
  Schnitt kompatibel, es kommen Felder und zwei Dateien hinzu.
- `latest_candidate_analyses` liefert zum Zeitpunkt jetzt auch den Lauf;
  der Tageslauf nutzt weiterhin nur den Zeitpunkt.
- `stocks.json` wächst mit der Watchlist (~120 KB bei 192 Titeln),
  `signal-backtests.json` mit Aktien × Kombinationen (~400 KB). Beide werden
  je Sitzung einmal geladen.
- Was folgt: Übersicht, Tagesläufe und Aktienliste des Redesigns lesen genau
  diese Felder; der Backtest-Explorer liest `signal-backtests.json`.
