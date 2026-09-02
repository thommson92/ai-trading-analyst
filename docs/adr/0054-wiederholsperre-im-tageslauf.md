# ADR 0054: Wiederholsperre im Tageslauf — sieben Tage je voll analysiertem Symbol

- Status: Angenommen
- Datum: 2026-09-01

## Kontext

Der Tageslauf kennt keine Erinnerung über Läufe hinweg. Jeder Lauf prüft die
volle Watchlist neu, und jeder 2-aus-3-Signaltreffer durchläuft die
vollständige Analyse — SEC EDGAR (mehrere Anfragen), zweimal Finnhub, die
Optionskette als teuerster IBKR-Block und eine KI-Einordnung je Titel. Die
Empfehlungsstufe entsteht erst danach; auch ein Titel, der am Ende nur WATCH
ist, hat den vollen Preis gekostet und steht in der Ergebnismeldung.

Ein Signal wie der EMA-Breakout bleibt aber oft tagelang aktiv. Der erste
scharfe Verbundlauf (2026-09-01, 36 Kandidaten) hätte an den Folgetagen
weitgehend dieselben Titel erneut analysiert und gemeldet — dieselben
API-Kosten, dieselben Meldungszeilen, ohne neue Information.

Der Projektinhaber hat entschieden: **Jede Aktie kommt höchstens einmal alle
sieben Tage als Kandidat in Frage.** Wurde sie innerhalb dieser Frist bereits
voll analysiert, wird sie im Tageslauf komplett ignoriert.

## Entscheidung

1. **Sperrfrist.** Ein Symbol, dessen jüngste volle Analyse in das
   Sperrfenster fällt (`repeat_suppression.window_days`, Default **7**, `0`
   schaltet ab), wird vom Lauf **komplett übersprungen**: keine
   Signalprüfung, keine Analyse, keine Zeile in Ergebnis und Meldung.
2. **Auslöser ist jede volle Analyse.** Anker ist das jüngste `evaluated_at`
   einer `screening_results`-Zeile mit `status = CANDIDATE` — also jeder
   2-aus-3-Treffer, unabhängig von der späteren Empfehlungsstufe. Auch ein
   WATCH-Titel sperrt: Er hat die volle Analyse verbraucht und stand in der
   Meldung. Bewusst in Kauf genommen: Ein WATCH-Titel kann während der Sperre
   nicht als CANDIDATE wiederkommen. Die Alternative (nur STRONG_CANDIDATE/
   CANDIDATE sperren) wurde verworfen — sie hätte die täglichen
   WATCH-Wiederholungen samt Kosten unverändert gelassen. Für die verworfene
   Variante entsteht weder ein Konfig-Schalter noch ein Port-Parameter
   (YAGNI); bei Bedarf wäre sie eine zusätzliche WHERE-Klausel auf der
   Spalte `recommendation`.
3. **Kalendertag-Fenster, der laufende Tag sperrt nicht.** Das Fenster
   zählt in Kalendertagen der Börsenzeit und umfasst die `window_days − 1`
   Tage **vor** dem heutigen; `window_days` zählt den Analysetag mit (`1`
   wirkt damit faktisch wie aus). Zwei Gründe:
   - **Planbare Rückkehr:** Tag 0 analysiert, Tag `window_days` wieder dran
     — ein Uhrzeitvergleich („jünger als 7 × 24 h") machte daraus je nach
     Minuten-Jitter des Schedulers unvorhersehbar acht Tage.
   - **Absturzfestigkeit:** Bricht ein Lauf nach teilweiser Persistenz ab
     und wiederholt der Dispatcher am selben Tag, dürfen die Zeilen des
     abgebrochenen Laufs den Wiederholungslauf nicht beschneiden — sonst
     fehlten dem angenommenen Lauf des Tages genau diese Kandidaten, und
     zwar für sieben Tage.
4. **Ein unterdrücktes Wiederauftreten verlängert die Sperre nicht.** Das
   ergibt sich konstruktiv: Für übersprungene Symbole entsteht keine neue
   Analysezeile, der Anker bleibt die letzte volle Analyse.
5. **Ort: die Application-Schicht**, zwischen `list_stocks()` und der
   Verarbeitung je Aktie — ausdrücklich **nicht** an der Watchlist im
   Dispatch-Aufbau. Dort würde der Ausschluss auch den Kerzen-Backfill
   kappen; nach Ablauf der Sperre stünde der Titel mit Kurslücke da
   (`StaleDataError`). Die Bars gesperrter Titel werden also weiter
   nachgeführt, nur analysiert wird nicht.
6. **Sichtbarkeit.** Je übersprungenem Symbol eine INFO-Logzeile mit dem
   Zeitpunkt der letzten Analyse, dazu eine Summenzeile.
   `AnalysisRun.number_of_stocks` trägt die **gefilterte** Zahl: Der
   Laufdatensatz beschreibt, was der Lauf gerechnet hat, und
   `completion_ratio`, Meldungstext und Zeilenzahl bleiben konsistent. Die
   Sperrentscheidung ist aus der Datenbank jederzeit rekonstruierbar
   (Konfiguration plus Vortageszeilen).
7. **Datenquelle der Abfrage ist `screening_results`**, nicht
   `stock_reports`: Der Anker ist die Analyse, nicht das Berichtsartefakt —
   Berichte können isoliert scheitern, und `created_at` eines Berichts ist
   der Berichtszeitpunkt. `screening_results` trägt `status` **und**
   `recommendation`; auch die verworfene Auslöser-Variante bliebe damit
   dieselbe Abfrage. Kein neuer Index: Rund 192 Zeilen je Lauf, die Abfrage
   läuft einmal am Tag — ein Index wäre geraten statt gemessen.

## Konsequenzen

- **Deployment-Effekt:** Unmittelbar nach dem Rollout sind alle 36 am
  2026-09-01 (Lauf 7c88d78c) voll analysierten Titel für sieben Tage
  gesperrt. Der erste Lauf danach meldet erwartbar deutlich weniger oder
  keine Kandidaten. Das ist der gewollte Zustand, kein Fehler.
- Eine drastische Lageänderung eines gesperrten Titels innerhalb der Frist
  wird nicht gemeldet — der bewusste Preis der Entscheidung.
- Eine vollständig gesperrte (Kleinst-)Watchlist ergäbe `completion_ratio`
  0.0; der Dispatcher wertete den Lauf als nicht erledigt und meldete nach
  Fristablauf einen Ausfall. Hingenommen: Bei 192 Titeln und ~36 Sperren je
  Woche praktisch unerreichbar, und bei einer Fehlkonfiguration ist eine
  laute Meldung besser als ein stiller Leerlauf.
- Die Sperre wirkt im Tageslauf (`cli dispatch` → `RunAnalysisUseCase`).
  `cli screen` nutzt den Use case nicht und bleibt unberührt.
- Manuelle Läufe über den Use case zählen als volle Analyse und sperren
  ebenso — gewollt, sie kosten dasselbe.
