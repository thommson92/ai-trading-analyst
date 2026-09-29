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

Der Faden wird nicht abgebrochen, sondern nicht länger abgewartet. Drei
Eigenschaften machen das gefahrlos:

1. Der Schreiber legt jede Datei vollständig daneben und schiebt sie dann an
   ihren Platz (`os.replace`). Ein halb geschriebener Baum entsteht nicht.
2. Die Zustandsdatei entsteht erst am Ende. Ein falscher bekannter Stand kann
   nicht zurückbleiben.
3. Die Sperrdatei des Exports verfällt von selbst.

Kommt der Faden doch noch durch, ist sein Ergebnis vollständig und richtig —
nur hat es niemand mehr abgewartet.

### Was die Grenze nicht ist

Kein Ersatz für das Beheben der Ursache. Sie greift regelmäßig nur, wenn
etwas anderes falsch ist; mit den übernommenen Kerzenserien
([ADR 0072](0072-export-uebernimmt-die-kerzenserien-des-laufs.md)) sollte der
Export weit darunter bleiben. Sie ist die Zusicherung, dass ein einzelner
Schritt **nie wieder** einen ganzen Lauf anhalten und dabei die
Überfälligkeitsmeldung mit einsperren kann.

Sie ersetzt auch den Wächter aus ADR 0071 nicht: Der meldet, wenn der Lauf
gar nicht erst startet. Diese Grenze meldet, wenn er startet und nicht
zurückkommt. Zwei verschiedene Ausfälle.

## Folgen

Der Lauf gilt als erledigt, auch wenn das Dashboard nicht aktualisiert wurde;
der Inhaber erfährt es per Telegram als vierten Ausgang, mit eigenem Text —
„Der Export lief noch, als seine Zeitgrenze ablief" sagt etwas anderes als
„nicht geschrieben" und als „nicht gesendet".

`step_timeout_seconds` auf einen sehr großen Wert zu setzen stellt das
Verhalten von vorher her; im Code ist `None` dieselbe Rücknahme.

## Alternative

**Eine kooperative Frist im Erzeuger** — der Datenbaum prüft zwischen zwei
Aktien, ob seine Zeit abgelaufen ist. Sauberer, weil kein Faden zurückbleibt,
aber sie deckt nur das Rechnen ab. Bau und Upload bräuchten je eine eigene,
und der nächste Teil des Schritts wieder eine. Die Zusicherung, um die es
hier geht, ist keine über den Datenbaum, sondern eine über den Lauf.
