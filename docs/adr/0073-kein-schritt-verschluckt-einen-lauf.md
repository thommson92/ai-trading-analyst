# ADR 0073: Kein einzelner Schritt verschluckt einen Lauf

- Status: Vorgeschlagen
- Datum: 2026-09-29
- Ergänzt: [ADR 0060](0060-dashboard-ausserhalb-des-servers.md),
  [ADR 0019](0019-trading-day-dispatcher.md) und
  [ADR 0071](0071-waechter-ausserhalb-des-laufs.md)

## Kontext

Vom **2026-09-23 bis zum 2026-09-28** lief der Tageslauf an vier Handelstagen
bis zur Meldung durch — die Kandidaten kamen per Telegram an — und blieb
danach stehen. In `dispatcher_runs` steht für jeden dieser Tage:

```
 session_date | status  | attempts | erster | letzter | ende
 2026-09-28   | running |        1 | 13:00  | 13:00   |
```

`finished_at` leer, `attempts` bei 1, obwohl die Aufgabenplanung zwischen
13:00 und 15:30 rund elf Mal auslöst. `begin()` zählt bei jedem Versuch hoch;
dass es bei 1 blieb, heißt: **Kein späterer Start kam bis dorthin.** Der
Prozess von 13:00 hielt den Advisory Lock über das ganze Fenster.

Stehen geblieben ist er im Dashboard-Export. Und weil `_report_overdue`
**innerhalb** derselben Sperre läuft, ging auch keine
Überfälligkeitsmeldung hinaus. Sechs Handelstage lang meldete niemand etwas.

Die Regel für diesen Schritt stand längst da, in `_publish_dashboard`:

> Der Lauf ist an dieser Stelle fertig und sein Ergebnis steht in der
> Datenbank; ein Export, der nicht schreiben kann, darf daraus keinen
> gescheiterten Lauf machen.

Sie deckte drei Ausgänge ab — Schreibfehler, Upload-Fehler, Vorschau-Befund.
Den vierten deckte sie nicht: **Der Export kommt gar nicht zurück.** Dann
macht er aus dem fertigen Lauf keinen gescheiterten, sondern gar keinen.

## Entscheidung

Der Lauf wartet auf den Exportschritt höchstens
`dashboard_export.step_timeout_seconds` (ausgeliefert 1800). Danach hängt er
ihn ab, meldet das als vierten Ausgang und gilt als erledigt.

### Warum an der Naht und nicht im Mechanismus

Der Schritt besteht aus vier Teilen — den Datenbaum rechnen, ihn schreiben,
die Oberfläche bauen, alles hochladen. Bau und Upload haben ihre eigenen
Fristen (`build_timeout_seconds`, `upload_timeout_seconds`); was keine von
beiden abdeckt, ist das Rechnen, und genau dort ist es stehen geblieben. Eine
Grenze um den ganzen Schritt deckt alle vier ab, ohne durch jeden einzelnen
hindurchgereicht zu werden — und deckt auch den fünften ab, den es heute noch
nicht gibt.

### Warum Abhängen hier ungefährlich ist

Der Faden wird nicht abgebrochen, sondern nicht länger abgewartet.

**Ein halb geschriebener Baum entsteht dabei sehr wohl** — jede *Datei* wird
atomar an ihren Platz geschoben (`os.replace`), der *Baum* als Ganzes nicht.
`snapshot.py` sagt das im eigenen Kommentar: Neue Dateien neben dem alten
Manifest, und der Browser weist sie zurück. Ungefährlich ist es trotzdem, aber
aus drei anderen Gründen:

1. **Der Upload kommt erst nach dem vollständigen Schreiben.** Draußen geht
   also nichts kaputt; das halbe Ergebnis bleibt auf dem Server liegen.
2. **Die Zielnamen sind pfadstabil**, und der Schreiber räumt Verwaistes am
   Ende auf. Der nächste vollständige Export heilt den Baum.
3. **Die Zustandsdatei entsteht erst am Ende.** Ein falscher bekannter Stand
   kann nicht zurückbleiben.

**Die Sperrdatei bleibt dagegen liegen**, und das ist ein echter
Betriebsnachteil: Der Faden ist ein Daemon, beim Ende des Prozesses wird er
hart beendet, und sein `finally` läuft nicht. Ein Export von Hand ist danach
**bis zu einer Stunde gesperrt** (`SPERRE_VERFAELLT`) — ausgerechnet in dem
Moment, in dem der Inhaber die Meldung liest und nachhelfen will. Die Meldung
sagt das deshalb ausdrücklich. Automatisch entfernt wird die Sperre nicht: Der
abgehängte Faden schreibt möglicherweise noch, und zwei gleichzeitige Exporte
in dasselbe Verzeichnis wären der schlechtere Ausgang.

Ob der Faden noch durchkommt, ist **nicht bekannt** — und meistens kommt er
nicht durch, weil CPython Daemon-Fäden beim Herunterfahren beendet und
`command_dispatch` binnen Sekunden zurückkehrt. Der Upload ist die Ausnahme:
`wrangler` ist ein Kindprozess und überlebt das Ende des Python-Prozesses.
Deshalb behauptet die Meldung nicht, draußen stehe der vorige Stand — sie
sagt, dass es nicht bekannt ist.

### Was die Grenze nicht ist

Kein Ersatz für das Beheben der Ursache. Sie greift regelmäßig nur, wenn
etwas anderes falsch ist; mit den übernommenen Kerzenserien
([ADR 0072](0072-export-uebernimmt-die-kerzenserien-des-laufs.md)) sollte der
Export weit darunter bleiben.

**Und sie sichert genau einen Schritt.** Innerhalb desselben Advisory Locks
laufen weiterhin ohne Frist: der Backfill, die Optionsanalyse in Phase 1b,
die Agenten in Phase 2 (`as_completed` ohne `timeout`) und die Meldung selbst.
Hängt einer von ihnen, ist die Lage Zeile für Zeile die des 2026-09-23. Die
Zusage dieses ADR lautet deshalb nur: **Der Exportschritt kann es nicht mehr.**

Die verbleibende Lücke bleibt offen und gehört in einen eigenen Beschluss.
Die strukturelle Antwort wäre eine Frist um den Lauf als Ganzes oder ein
Wächter **außerhalb** der Sperre, der auch „gestartet und nicht
zurückgekommen" sieht — der Wächter aus ADR 0071 sieht heute nur, dass gar
nichts lief.

Sie ersetzt auch den Wächter aus ADR 0071 nicht: Der meldet, wenn der Lauf
gar nicht erst startet. Diese Grenze meldet, wenn er startet und nicht
zurückkommt. Zwei verschiedene Ausfälle.

## Folgen

Der Lauf gilt als erledigt, auch wenn das Dashboard nicht aktualisiert wurde;
der Inhaber erfährt es per Telegram als vierten Ausgang, mit eigenem Text —
„Der Export lief noch, als seine Zeitgrenze ablief" sagt etwas anderes als
„nicht geschrieben" und als „nicht gesendet". Der Text nennt beides, was der
Lauf wirklich weiß: dass der Ausgang unbekannt ist, und dass ein Export von
Hand bis zu einer Stunde gesperrt bleibt.

`step_timeout_seconds` auf einen sehr großen Wert zu setzen stellt das
Verhalten von vorher her; im Code ist `None` dieselbe Rücknahme.

## Alternative

**Eine kooperative Frist im Erzeuger** — der Datenbaum prüft zwischen zwei
Aktien, ob seine Zeit abgelaufen ist. Sauberer, weil kein Faden zurückbleibt,
aber sie deckt nur das Rechnen ab. Bau und Upload bräuchten je eine eigene,
und der nächste Teil des Schritts wieder eine. Die Zusicherung, um die es
hier geht, ist keine über den Datenbaum, sondern eine über den Lauf.
