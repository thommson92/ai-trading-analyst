# ADR 0074: Der Alarm liegt nicht in der Sperre

- Status: Vorgeschlagen
- Datum: 2026-09-29
- Ergänzt: [ADR 0019](0019-trading-day-dispatcher.md),
  [ADR 0024](0024-benachrichtigungskanal-telegram.md) und
  [ADR 0073](0073-kein-schritt-verschluckt-einen-lauf.md)
- Verwandt: ADR 0071 (Wächter außerhalb des Laufs) — liegt noch auf dem Zweig
  `feature/betrieb-sicherung` und ist deshalb hier nicht verlinkt

## Kontext

Vom **2026-09-23 bis zum 2026-09-28** hing der Tageslauf an vier Handelstagen
im Dashboard-Export. Die Analyse lief durch, die Kandidaten kamen per Telegram
an — und dass der Lauf nie fertig wurde, sagte niemand. Sechs Handelstage lang.

Der Mechanismus ist in drei Zeilen erzählt:

1. Der Prozess von 13:00 ET hält den Advisory Lock, solange er lebt.
2. Jeder weitere Start bekommt ihn nicht und endet bei `IN_PROGRESS`.
3. `_report_overdue` stand **hinter** dieser Stelle, in `_dispatch()`.

Der Alarm war also genau dann eingesperrt, wenn er gebraucht wurde.

Das ist kein Versehen an einer Stelle, sondern ein Aufbaufehler: Die Meldung
über einen Lauf hing an der Fähigkeit, selbst einen Lauf zu beginnen.

[ADR 0073](0073-kein-schritt-verschluckt-einen-lauf.md) hat den Exportschritt
befristet — aber nur ihn. Ohne Frist laufen weiterhin der Backfill, die
Optionsanalyse in Phase 1b, die Agenten in Phase 2 (`as_completed` ohne
`timeout`) und die Meldung selbst. Hängt einer davon, wäre die Lage Zeile für
Zeile dieselbe.

## Entscheidung

`_report_overdue` läuft **auch dann, wenn die Sperre belegt ist** — vor dem
`IN_PROGRESS`-Ausgang, nicht dahinter.

Zwei Festlegungen dazu:

1. **Auch der heutige Lauf wird gemeldet, wenn es zu ihm noch gar keine
   Zeile gibt.** Der ganze Mechanismus hängt daran, dass `unresolved()` etwas
   findet — und die Zeile entsteht erst in `begin()`. Davor liegt genau ein
   unbefristeter Aufruf nach draußen: der Börsenkalender, und der kommt von
   der TWS. Bleibt sie in dem bekannten Zustand „Socket offen, antwortet
   nicht", hält der Prozess die Sperre, ohne dass je ein Datensatz entstanden
   wäre. Der fällige Lauf lässt sich ohne Kalender bestimmen — dieselbe
   Überlegung wie bei `_is_done_without_calendar`.

2. **Die Meldung unterscheidet zwei Lagen.** „Nicht gerechnet" und „hängt seit
   Stunden" verlangen verschiedene Handgriffe: im ersten Fall gehört die TWS
   angesehen, im zweiten der Prozess. Der falsche Hinweis ist schlimmer als
   keiner.

   **Woher diese Unterscheidung kommt, entscheidet über ihren
   Wahrheitsgehalt.** Aus der Statusspalte abgeleitet wäre sie falsch: Wird
   ein hängender Prozess von Hand beendet, bleibt seine Zeile für immer auf
   `running`, und die Meldung behauptete noch Tage später eine gehaltene
   Sperre, die niemand hält. Maßgeblich ist deshalb, ob **dieser** Start die
   Sperre bekommen hat — eine Tatsache über das Jetzt, nicht über die
   Vergangenheit. Und zusätzlich, ob es um den heutigen Tag geht: Am
   2026-09-28 waren vier Tage offen, während nur der heutige bearbeitet
   wurde.

3. **Eine Doppelmeldung wird in Kauf genommen.** Zwei Starts könnten denselben
   überfälligen Lauf melden, bevor `alert_sent_at` steht. Eine zweite Sperre
   allein fürs Melden verhinderte das — und wäre eine zweite Stelle, an der
   etwas hängen kann. Eine Telegram-Nachricht doppelt zu bekommen ist deutlich
   besser als sechs Tage Stille. Entschieden am 2026-09-29 vom Inhaber.

## Warum das die richtige Ebene ist

Die naheliegende Alternative wäre, jeden unbefristeten Schritt zu befristen.
Vier neue Zahlen, alle geraten — was ist die richtige Grenze für einen
Backfill, der mit der Watchliste wächst? — und der nächste Schritt bräuchte
wieder eine.

Diese Entscheidung hier ändert **eine** Stelle und wirkt für jeden Schritt,
auch für die, die es noch nicht gibt. Sie macht keinen hängenden Lauf kürzer;
sie macht ihn sichtbar. Das ist der Unterschied zwischen einem Ausfall, der
einen Abend kostet, und einem, der eine Woche kostet.

## Folgen

Ein hängender Lauf meldet sich beim **ersten Start nach Ablauf der
Nachholfrist** statt gar nicht. Die Frist liegt bei 14:50 New Yorker Zeit, die
Aufgabenplanung startet zur vollen und zur Viertelstunde — die Meldung kommt
also um **15:00**, am selben Abend, und danach bleiben noch 15:15 und 15:30.

Neu ist, dass ein Lauf gemeldet werden kann, der noch läuft und später doch
noch gelingt. Das ist gewollt: Er ist über seine Frist, und das ist eine
Aussage über den Abend, nicht über den Ausgang. Der Vermerk `alert_sent_at`
bleibt danach stehen; der Lauf gilt trotzdem als gelungen, wenn er es wird.

Was diese Entscheidung **nicht** tut: einen hängenden Prozess beenden. Wer die
Meldung bekommt, sieht nach, ob er noch lebt, und beendet ihn von Hand. Eine
Frist um den Lauf als Ganzes wäre ein eigener Beschluss — und ein deutlich
größerer Eingriff, weil der Abbruch an jeder Systemgrenze sauber sein müsste.

Der Wächter aus ADR 0071 (noch nicht auf `dev`, er liegt auf dem Zweig
`feature/betrieb-sicherung` — deshalb hier ohne Verweis) bleibt davon
unberührt und wird nicht überflüssig: Er sieht, dass gar nichts lief — kein
Prozess, kein Datensatz, keine Sperre, weil die Aufgabe selbst nicht startete.
Diese Entscheidung sieht, dass etwas lief und nicht zurückkam. Zwei
verschiedene Ausfälle, zwei verschiedene Wächter.
