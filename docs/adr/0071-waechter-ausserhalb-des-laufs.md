# ADR 0071: Ein Wächter außerhalb des Laufs, den er überwacht

- Status: Vorgeschlagen
- Datum: 2026-09-22
- Ergänzt: [ADR 0019](0019-trading-day-dispatcher.md) und
  [ADR 0024](0024-benachrichtigungskanal-telegram.md)

## Kontext

Der Tageslauf meldet seinen eigenen Ausfall. `_report_overdue` prüft bei
**jedem** Start alle unerledigten Läufe, nicht nur den heutigen, und eine
gescheiterte Zustellung setzt keinen Vermerk — die Meldung gilt dann als
offen und wird erneut versucht. Das ist sorgfältig gebaut und funktioniert.

Es funktioniert nur unter einer Bedingung: **Der Lauf muss bis zu seiner
Meldelogik kommen.** Das Audit vom 2026-09-20 führt drei Fälle, in denen er
das nicht tut (AUDIT-003-014):

1. **Rückgabewert 2 vor der Dispatcher-Logik.** `command_dispatch` kehrt bei
   Konfigurationsfehlern zurück, bevor `execute()` je läuft.
2. **Kein Start.** Server aus, Aufgabe deaktiviert und nicht wieder
   eingeschaltet. Doc 14 nennt das Deaktivieren als regulären Handgriff für
   Einzelproben.
3. **Hängender Lauf.** Er hält den Advisory Lock; alle weiteren Starts enden
   bei `IN_PROGRESS`, und weil `_report_overdue` **innerhalb** der Sperre
   läuft, geht auch die Überfälligkeitsmeldung nie hinaus.

Am **2026-09-22** ist Fall 1 eingetreten, und zwar in einer Form, die das
Audit nicht vorhergesehen hatte: Nicht ein Konfigurationsfehler, sondern ein
Argumentfehler. In den Task-Argumenten stand `--log-file` ohne Pfad. `argparse`
beendet Usage-Fehler ebenfalls mit Rückgabewert 2 — **bevor eine einzige
Zeile dieses Programms läuft**. Ergebnis: rund 17 Startversuche zwischen
11:30 und 15:30, keine Zeile in `dispatcher_runs`, keine Meldung, ein
verlorener Handelstag. Bemerkt wurde es, weil dem Inhaber am Abend auffiel,
dass keine Telegram-Nachricht gekommen war.

Erschwerend: `notifications.send_when_no_candidates` steht auf `false`, und
seit der Wiederholsperre ([ADR 0054](0054-wiederholsperre-im-tageslauf.md))
sind kandidatenlose Tage der Normalfall. **„Keine Nachricht" heißt damit
sowohl „alles gut, nichts gefunden" als auch „nichts gelaufen".**

## Entscheidung

### 1. Ein eigener Vorgang, kein Teil des Laufs

`cli watchdog`, als eigene geplante Aufgabe, täglich **23:15** Börsenzeit.

Ein Wächter im überwachten Prozess schweigt in allen drei Fällen oben. Das
ist keine Geschmacksfrage, sondern die Eigenschaft, die ihn überhaupt
nützlich macht.

### 2. Er liest den Bestand und die Sicherungsablage — sonst nichts

Zwei Fragen: Gibt es für den heutigen Handelstag einen erledigten Lauf? Und
wie alt ist die jüngste Sicherung?

Kein TWS-Zugriff, keine Watchlist, kein Modellzugang, keine Marktdaten. Alles
davon kann ausgefallen sein — und dann muss er gerade arbeiten.

### 3. Er bekommt ein schmales, lesendes Protokoll

`DailyRunLookup` mit genau einer Methode, nicht der volle
`DispatcherRunRepository`.

**Der Wächter soll den Advisory Lock nicht einmal anfassen können.** Ein
Wächter, der die Sperre nimmt, blockiert den Lauf, den er überwacht — und
Fall 3 oben wäre dann nicht mehr ein seltener Ausnahmezustand, sondern ein
täglicher. Was er nicht kann, kann er auch nicht versehentlich tun.

### 4. Kein Börsenkalender — die Wochentagsnäherung

Der Kalender kommt von der TWS. Ein Wächter, der ihn braucht, wäre genau
dann stumm, wenn die TWS ausgefallen ist — also in einem der Fälle, für die
er gebaut ist.

Stattdessen `assumed_session`, mit dessen eigener Begründung: *„Fällt der Tag
in Wahrheit auf einen Feiertag, entsteht dadurch eine Meldung zu viel — die
umgekehrte Verwechslung, ein echter Ausfall gehalten für einen Feiertag, wäre
schlimmer."* Die Meldung sagt das ausdrücklich dazu.

Neun Fehlalarme im Jahr sind der Preis. Sie sind sichtbar, benannt und
sofort als solche erkennbar.

### 5. Er meldet erst nach Ablauf der Nachholfrist

Sonst meldete ein Wächter, der aus Versehen mittags läuft, einen Lauf als
ausgefallen, der noch gar nicht fällig ist. Geprüft wird über dieselbe
`ScheduledRun.decide`-Logik, die der Dispatcher benutzt.

### 6. Er meldet, er behebt nichts

Kein Nachstarten, kein Freigeben der Sperre, kein Löschen. Ein Wächter, der
eingreift, ist ein zweiter Dispatcher mit eigenen Fehlern — und der nächste
Befund wäre, dass beide sich gegenseitig stören.

### 7. Drei Rückgabewerte

| Wert | Bedeutung |
|---|---|
| 0 | nichts zu melden |
| 1 | Befund gemeldet |
| 2 | Befund vorhanden, **die Meldung ging nicht hinaus** |

Der dritte Fall ist der schlechteste: Es gibt einen Befund, und niemand
erfährt davon. Ohne eigenen Rückgabewert sähe er in der Aufgabenplanung
genauso aus wie „alles in Ordnung".

## Begründung

**Zu 1 und 3.** Die beiden hängen zusammen. Die Trennung nützt nur, wenn sie
auch technisch trägt: Ein Wächter im selben Prozess oder mit denselben
Rechten wäre eine Trennung auf dem Papier.

**Zu 2.** Jede zusätzliche Abhängigkeit ist ein zusätzlicher Weg, auf dem der
Wächter selbst ausfällt — und sein Ausfall fällt niemandem auf, weil Stille
sein Normalzustand ist. Deshalb so wenig wie möglich.

**Zu 4.** Die Alternative wäre, die Handelstage zu speichern, wenn der
Dispatcher sie ohnehin abruft. Das wäre genauer, verlagert aber die
Zuverlässigkeit des Wächters auf einen Bestand, den der überwachte Vorgang
pflegt. Genau diese Abhängigkeit soll es nicht geben.

**Zu 6.** Dieselbe Linie wie bei den Analysemodulen (CLAUDE.md): Ein Modul
tut eine Sache. Melden und Eingreifen sind zwei.

## Konsequenzen

**Positiv**

- Die Unterscheidung aus dem Auditauftrag wird beantwortbar: „Task gestartet
  ≠ Pipeline ausgeführt ≠ Pipeline erfolgreich" — der Wächter sagt, welche
  Stufe gerissen ist, und unterscheidet insbesondere „kein einziger Versuch"
  von „Versuche ohne Erfolg". Die beiden führen bei der Fehlersuche an
  völlig verschiedene Orte.
- Stille bedeutet künftig etwas: Wer nichts hört, hat einen Wächter, der
  nichts gefunden hat — nicht einen Kanal, der nichts sagt.
- Die Sicherung bekommt zum ersten Mal überhaupt eine Überwachung.

**Negativ und offen**

- **Der Wächter selbst wird von niemandem überwacht.** Fällt seine Aufgabe
  aus, ist alles wieder still. Das ist kein gelöstes Problem, sondern ein
  verschobenes — die nächste Stufe wäre ein Dienst außerhalb des Servers
  (ein „Dead Man's Switch"). Für den MVP ist die Verschiebung vertretbar,
  weil sie den wahrscheinlichsten Fall abdeckt und der unwahrscheinlichere
  beim Pflegetermin auffällt.
- **Neun Fehlalarme im Jahr** an Börsenfeiertagen (Punkt 4).
- **Der hängende Lauf wird gemeldet, nicht beendet.** Das Zeitlimit von drei
  Stunden am Tageslauf-Task ist die Gegenmaßnahme; sie steht in Doc 14 und
  ist keine Entscheidung dieses ADR.
- **Eine zweite Stelle mit einer Uhrzeit.** Bisher war das Startfenster der
  Aufgabenplanung die einzige; jetzt kommt 23:15 dazu. Beide stehen in der
  Betriebsdokumentation und nicht im Code — die Regel aus ADR 0019 bleibt
  gewahrt.
