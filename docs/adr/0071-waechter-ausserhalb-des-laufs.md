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

Kein TWS-Zugriff, keine Watchlist, kein Modellzugang, keine Marktdaten. Alles
davon kann ausgefallen sein — und dann muss er gerade arbeiten.

Aus dem Bestand beantwortet er vier Fragen, und sie ergeben vier verschiedene
Befunde. Das ist der Kern: „Es lief nichts" ist keine Diagnose, sondern eine
Sammelkategorie.

| Lage | Befund |
|---|---|
| ein Lauf ist erledigt | still |
| der Dispatcher hat für heute bereits gemeldet | **still** — siehe 6. |
| ein Lauf steht seit weniger als drei Stunden auf `running` | still — er arbeitet |
| ein Lauf steht seit **mehr** als drei Stunden auf `running` | **er hängt und hält die Sperre** |
| Versuche vorhanden, keiner erledigt | der Lauf kam nicht durch, mit letztem Fehlertext |
| **kein einziger Versuch** | die Aufgabenplanung hat nicht gestartet, oder der Start scheiterte vor dem Programm |

Die letzten beiden führen bei der Fehlersuche an völlig verschiedene Orte —
die eine zum Lauf, die andere zur Aufgabenplanung. Sie zusammenzufassen wäre
der Unterschied zwischen einem Wächter und einer Lampe.

Die Drei-Stunden-Grenze ist dieselbe wie das Zeitlimit der geplanten Aufgabe
(Doc 14). Ein regulärer Lauf dauert rund 103 Minuten und darf bis gegen 23:15
arbeiten; ohne diese Unterscheidung wäre der Wächter ein täglicher
Fehlalarm. **Damit ist Fall 3 oben abgedeckt** — und zwar nur von ihm: Der
Lauf selbst kann einen hängenden Lauf nicht melden, weil die Meldung
innerhalb der Sperre läuft, die er hält.

Die Sicherung prüft er unabhängig vom Handelstag und unabhängig vom Lauf.
Gesichert wird täglich, auch am Wochenende — und der Dispatcher weiß von der
Sicherung nichts.

Eine Datei unter 1 KiB zählt dabei nicht als Sicherung. `sicherung.ps1`
räumt bewusst erst nach einer *erfolgreichen* Sicherung auf und lässt eine
abgebrochene Datei liegen; nach dem Alter allein gefragt, sähe genau diese
Ruine wie eine frische Sicherung aus. Es ist eine Schranke, kein Beweis —
ob ein Dump lesbar ist, weiß nur `pg_restore --list`, und das ist Sache der
Zählprobe.

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

### 6. Er schweigt, worüber der Dispatcher schon geredet hat

Hat der Dispatcher für diesen Handelstag bereits gemeldet
(`alert_sent_at` gesetzt), sagt der Wächter zum Lauf nichts mehr. Der Nutzer
weiß Bescheid; eine zweite Meldung derselben Sache wäre nur Lärm, und ein
Wächter, den man wegen Lärm ignoriert, ist keiner.

Das ist zugleich eine notwendige Korrektur: `mark_alert_sent` legt eine Zeile
mit `attempts = 0` an, wenn die Frist ablief, **ohne** dass je ein Versuch
stattfand. Ohne diese Regel meldete der Wächter „kein einziger Versuch" für
einen Tag, an dem längst gemeldet wurde — und nennte dabei zwei Ursachen, die
beide falsch wären.

Die Sicherung ist davon ausgenommen. Von ihr weiß der Dispatcher nichts.

### 7. Er meldet, er behebt nichts

Kein Nachstarten, kein Freigeben der Sperre, kein Löschen. Ein Wächter, der
eingreift, ist ein zweiter Dispatcher mit eigenen Fehlern — und der nächste
Befund wäre, dass beide sich gegenseitig stören.

### 8. Drei Rückgabewerte

| Wert | Bedeutung |
|---|---|
| 0 | nichts zu melden |
| 1 | Befund gemeldet |
| 2 | Befund vorhanden, **die Meldung ging nicht hinaus** — oder der Wächter selbst ist abgebrochen |

Der dritte Fall ist der schlechteste: Es gibt einen Befund, und niemand
erfährt davon. Ohne eigenen Rückgabewert sähe er in der Aufgabenplanung
genauso aus wie „alles in Ordnung".

Deshalb gehört auch der **abgebrochene** Wächter hierher und nicht zur 1: Eine
fehlende Tabelle nach einer Wiederherstellung ohne `alembic upgrade head`
wäre sonst von „Befund gemeldet" nicht zu unterscheiden.

Und deshalb meldet er, wenn die **Datenbank nicht erreichbar** ist, statt
still mit 2 zu enden. Er weiß dann nichts über den Lauf — aber er weiß etwas
Schlimmeres: Ohne PostgreSQL kann der Tageslauf weder arbeiten noch sich
melden. Das ist genau die Fehlerklasse, für die es ihn gibt.

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

**Zu 6.** Ein Wächter, der Bekanntes wiederholt, wird ignoriert — und dann
wird auch das Unbekannte ignoriert.

**Zu 7.** Dieselbe Linie wie bei den Analysemodulen (CLAUDE.md): Ein Modul
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
- **Ein Lauf, der zwischen drei Stunden und Mitternacht hängt, wird erst am
  Folgetag auffällig** — der Wächter läuft um 23:15, ein um 21:30 gestarteter
  Lauf hinge dann erst seit zwei Stunden. Die Lücke ist bewusst in Kauf
  genommen: Ein zweiter Wächterlauf kostete mehr, als er hier einbringt.
- **Eine zweite Stelle mit einer Uhrzeit.** Bisher war das Startfenster der
  Aufgabenplanung die einzige; jetzt kommt 23:15 dazu. Beide stehen in der
  Betriebsdokumentation und nicht im Code — die Regel aus ADR 0019 bleibt
  gewahrt.
