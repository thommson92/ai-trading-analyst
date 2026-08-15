# ADR 0019: Trading-Day-Dispatcher — idempotenter Einzelstart statt Dauerprozess

- Status: Angenommen
- Datum: 2026-08-15

## Kontext

Der Analyse-Lauf wird bis heute von Hand angestoßen. [Doc 10,
§6.1](../10%20-%20System%20Architecture.md) beschreibt den Trading-Day-Scheduler
ausführlich — Zeitzone, Wochenenden, Feiertage, verkürzte Tage, höchstens ein
Lauf je Handelstag —, aber er taucht in keinem Sprint der Roadmap auf und ist
nie gebaut worden.

Die Rahmenbedingungen sind eng und stammen aus bereits getroffenen
Entscheidungen:

- **Ziel ist die erste 195-Minuten-Kerze**, 09:30 bis 12:45 `America/New_York`
  (`market.daily_candle_index: 1`). Nicht der Börsenschluss.
- **Keine feste deutsche Uhrzeit im Code** (Doc 10, §6.1). Zwei bis drei Wochen
  im Jahr stellen USA und Europa an verschiedenen Tagen um; 12:45 ET liegt dann
  auf 17:45 statt 18:45 unserer Zeit.
- **Karenz und Polling sind bereits konfiguriert**:
  `data_availability.grace_period_seconds`, `poll_interval_seconds`,
  `max_wait_seconds`. Der Lauf startet ab Kerzenschluss und rechnet erst nach
  nachgewiesener Vollständigkeit (Risiko R9).
- **Die TWS braucht eine angemeldete Sitzung** ([ADR 0018](0018-kein-windows-autologon.md),
  [ADR 0014](0014-ibkr-produktivintegration-freigegeben.md) E2). Nach dem
  sonntäglichen Neustart startet der Projektinhaber montags von Hand.
- **Der Backfill braucht die TWS, das Screening nicht.** Seit
  `market_data.source: stored` rechnet der reguläre Lauf auf dem abgelegten
  Bestand.

## Entscheidung

Ein **idempotenter Dispatcher**, den die Windows-Aufgabenplanung alle 15 Minuten
in einem großzügigen Abendfenster startet. Der Auslöser ist dumm, das Programm
entscheidet.

### 1. Zeitrechnung ausschließlich in `America/New_York`

Der Dispatcher bestimmt aus der aktuellen Zeit den Handelstag und den Schluss
der Zielkerze. Die einzige deutsche Uhrzeit im System ist das Startfenster der
Aufgabenplanung; es wird bewusst so breit gelegt, dass beide
Zeitumstellungsvarianten hineinfallen.

Der Lauf ist ab `candle_close + safety_buffer` zulässig. Der Puffer ist
konfigurierbar (`scheduler.safety_buffer_seconds`, Vorgabe 300 s, also ab
12:50 ET) und steht nicht im Code.

### 2. Börsenkalender aus IBKR, nicht aus einer gepflegten Liste

Feiertage und verkürzte Handelstage kommen aus `reqContractDetails`
(`tradingHours`, `liquidHours`) — derselben Quelle, die auch die Kurse liefert.

Ein eigener Feiertagskalender wird **nicht** eingeführt: Eine Liste, die
jährlich stimmen muss, führt bei einem Fehler zu einem übersprungenen
Handelstag, und das fällt niemandem auf.

Die datengetriebene Alternative — warten, bis `max_wait_seconds` abläuft, und
daraus auf einen Feiertag schließen — wurde verworfen. Sie kann „Feiertag" nicht
von „TWS nicht erreichbar" unterscheiden, und genau diese Unterscheidung
braucht Punkt 5.

### 3. Zustand dauerhaft und atomar

Eine Tabelle `dispatcher_runs` mit eindeutigem Schlüssel über
`(session_date, candle_close)`. Das Beanspruchen eines Laufs ist ein
`INSERT … ON CONFLICT DO NOTHING`: Wer die Zeile schreibt, führt aus; wer sie
nicht schreibt, beendet sich. Der Zustand überlebt Neustarts, weil er in der
Datenbank steht und nicht im Prozess.

Zusätzlich ein `pg_advisory_lock` für die Dauer des Laufs. Der eindeutige
Schlüssel allein schützt nicht gegen zwei Starts, die sich zeitlich
überlappen, während der erste noch arbeitet — und zwei gleichzeitige
Backfill-Läufe würden sich an der TWS gegenseitig verdrängen, weil IBKR je
Client-ID nur eine Verbindung zulässt.

### 4. Kein Lauf ohne frische Daten

Ist die TWS nicht erreichbar oder nicht angemeldet, gilt der Lauf **nicht als
erledigt**. Der nächste 15-Minuten-Start versucht es erneut, bis die
Nachholfrist (`scheduler.max_catch_up_seconds`) abgelaufen ist.

Es wird ausdrücklich **kein** Analyse-Lauf auf dem Stand des Vortages erzeugt.
Ein solcher Lauf sähe aus wie die heutige Analyse und wäre es nicht — dasselbe
Prinzip wie „keine erfundenen Werte", eine Ebene höher.

### 5. Alarm nach Frist, Kanal später

Überschreitet ein unerledigter Lauf die Nachholfrist, geht eine Meldung mit
Ursache und Zeitpunkt an die Benachrichtigungsschnittstelle. Der **Auslöser**
wird jetzt gebaut; der Kanal ist als F10 offen (`notifications.channel:
dry_run`) und bekommt ein eigenes ADR, weil ein Push-Dienst eine externe
Abhängigkeit mit Zugangsdaten ist. Bis dahin landet die Meldung im Protokoll.

### 6. Eindeutige Rückgabewerte

| Wert | Bedeutung |
|---|---|
| 0 | Lauf durchgeführt, oder nichts zu tun (zu früh, kein Handelstag, bereits erledigt) |
| 1 | Lauf versucht und gescheitert — Daten unvollständig, TWS nicht erreichbar |
| 2 | Konfigurations- oder Umgebungsfehler; erneutes Starten hilft nicht |
| 130 | Abgebrochen |

„Nichts zu tun" ist bewusst 0: Bei 15-Minuten-Takt wäre alles andere ein
Protokoll voller Fehlschläge, in dem der echte nicht mehr auffiele.

## Begründung

**Warum kein Dauerprozess.** Ein Prozess mit interner Zeitsteuerung rechnet
zwar von sich aus in New Yorker Zeit, verschwindet aber nach einem Absturz
still — und niemand merkt es bis zum nächsten Blick ins Protokoll. Er müsste
zudem nach jedem Serverneustart von Hand gestartet werden, womit er dieselbe
Schwäche hätte wie die TWS, ohne deren Notwendigkeit.

**Warum kein einzelner Tagesstart.** Ein einmaliger Start zur festen Uhrzeit
kennt kein Wiederholen. Fällt die TWS gerade in dieser Minute aus, gibt es an
diesem Tag keine Analyse. Der 15-Minuten-Takt macht das Nachholen zum
Normalfall statt zum Sonderfall — und die Zeitumstellung zum Nichtereignis.

**Warum der Zustand in der Datenbank liegt.** Eine Datei ließe sich atomar
schreiben, aber der Lauf schreibt seine Ergebnisse ohnehin in dieselbe
Datenbank. Zwei Orte für zusammengehörigen Zustand wären eine Quelle für
Widersprüche nach einem Absturz zwischen beiden Schreibvorgängen.

## Konsequenzen

- Der Dispatcher braucht **beides**: Datenbank und, für Kalender und Backfill,
  die TWS. Er ist damit das erste Bauteil, das ohne laufende TWS gar nicht
  entscheiden kann, ob heute ein Handelstag ist. Das ist hingenommen; der
  Wiederholungsmechanismus deckt es ab.
- An Feiertagen entsteht kein Lauf und keine Meldung — der Kalender sagt vorher,
  dass nichts zu tun ist. Kein Warten, kein Fehlalarm.
- Ein zusätzliches Schema-Objekt (`dispatcher_runs`) samt Migration.
- Das Startfenster der Aufgabenplanung ist die einzige Stelle mit deutscher
  Uhrzeit und gehört in die Betriebsdokumentation, nicht in den Code.
- Die Anzahl der Starts steigt auf rund ein Dutzend je Abend. Alle bis auf einen
  enden nach wenigen Millisekonden mit „nichts zu tun", ohne die TWS oder die
  Watchlist anzufassen.

## Nicht Gegenstand dieser Entscheidung

- Der **Benachrichtigungskanal** (F10) — eigenes ADR.
- Der **zweite Kerzenzeitpunkt** (16:00 ET). `daily_candle_index: 1` ist
  konfigurierbar; der Dispatcher liest ihn, und ein zweiter täglicher Lauf wäre
  eine Konfigurations-, keine Codeänderung.
- **Backtesting-Läufe** und alles, was nicht der tägliche Screening-Lauf ist.
