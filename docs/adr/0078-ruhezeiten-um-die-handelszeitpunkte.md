# ADR 0078: Ruhezeiten um die Handelszeitpunkte

- Status: Vorgeschlagen
- Datum: 2026-10-09
- Ergänzt: [ADR 0013](0013-ibkr-spike-koexistenz.md) und
  [ADR 0014](0014-ibkr-produktivintegration-freigegeben.md)

## Kontext

Auf demselben Server handelt eine zweite Anwendung (Trade Automation Toolbox)
über dieselbe TWS-Instanz. Dass sich die beiden nicht die **Verbindung**
streiten, ist seit ADR 0013 geregelt: eigene Client-ID, hier 17, dort 99.

Die Marktdatenleitungen gehören aber dem **Konto** und nicht der Verbindung.
Gegen eine geteilte Kontoressource hilft keine Client-ID — dagegen hilft nur
Schweigen.

Der Anlass ist eine Beobachtung des Inhabers: In manchen Telegram-Meldungen
fehlen die Optionsdaten. Das ist ein Verdacht und kein Nachweis — es gibt
einen zweiten Kandidaten, den TWS-Verbindungswechsel aus
[ADR 0069](0069-backfill-und-analyse-verzahnt.md), und
`scripts/betriebsbericht.py` trennt die beiden Lagen inzwischen. Diese
Entscheidung steht trotzdem für sich: Sie ist billige Versicherung gegen eine
Störung, deren Kosten der Inhaber kennt und deren Nutzen er abschätzen kann.

## Entscheidung

Um jeden konfigurierten Handelszeitpunkt herum geht **keine** Anfrage an die
TWS. Fünf Festlegungen:

1. **Die Zeitpunkte pflegt der Inhaber**, in `config/default.yaml`, in
   Börsenzeit, mit Wochentagen. Sie hängen an seinem Handelsplan und nicht an
   einer technischen Eigenschaft — dieselbe Begründung wie für die Uhrzeit der
   Aufgabenplanung in Doc 14.

   Stand vom 2026-10-09, von ihm validiert: **jeden Wochentag 13:15 und 14:15,
   zusätzlich freitags 14:45**, jeweils fünf Minuten davor und danach.

2. **Alle IBKR-Abfragen, nicht nur die Optionsabrufe.** Die Alternative wäre
   enger und billiger gewesen — der historische Backfill konkurriert über die
   per-Verbindung gezählte Historienrate und nicht über die Marktdatenleitungen
   des Kontos. Der Inhaber hat sich für die vollständige Ruhe entschieden, und
   bei den validierten Zeiten kostet sie wenig (siehe Folgen).

3. **Gewartet wird, nicht übersprungen.** Der Backfill muss jedes Symbol
   holen; ein ausgelassenes wäre ein Loch in der Kursreihe, und das wäre
   teurer als zehn Minuten Wartezeit.

4. **Die Sperre sitzt in `_connection()`**, dem einzigen Durchgang, durch den
   jede Anfrage muss — und ausdrücklich **nicht** in `_wait_for_pacing()`.
   Die Drossel sitzt allein vor `reqHistoricalData`; die Kettenabfragen und
   `reqTickers` gehen daran vorbei. Ausgerechnet `reqTickers` belegt die
   Marktdatenleitungen, also genau die Ressource, um die es hier geht. Eine
   Sperre in der Drossel hätte den gefährlichsten Aufruf ungeschützt gelassen.

5. **Die Wartezeit wird getrennt gezählt** (`ruhesekunden` neben
   `verschlafene_sekunden`). Die Drossel schützt uns vor IBKRs Rate, die
   Ruhezeit schützt eine andere Anwendung vor uns. Zusammengezählt ließe sich
   hinterher nicht sagen, welche der beiden Ursachen einen Lauf verlängert hat.

## Folgen

Von den drei Fenstern trifft **nur 13:10–13:20 den Backfill**. Er hat ab 12:50
zwanzig freie Minuten, pausiert zehn und ist dann nach weiteren fünfzehn
fertig: **Ende gegen 13:35 statt 13:25.** Das zweite Fenster um 14:10 und das
freitägliche um 14:40 liegen hinter dem Lauf.

Der Ort eines Zeitpunkts entscheidet über seinen Preis, und das ist die eine
Zahl, die man beim Pflegen kennen muss: **Zwischen 12:50 und 13:10 liegt die
einzige durchgehende Arbeitszeit des Backfills.** Ein Fenster dort verlängert
den Lauf deutlich stärker als zehn Minuten.

Dieselbe Rechnung mit der zunächst erwogenen Spanne von −5 bis +20 Minuten
hätte die Fenster verschmelzen lassen: zwischen 13:10 und 15:05 wären drei
Lücken von je fünf Minuten geblieben, der Backfill erst gegen 15:05 fertig,
der Lauf gegen 15:20 — und ein Lauf, der um 15:00 noch arbeitet, gilt seit
[ADR 0074](0074-der-alarm-liegt-nicht-in-der-sperre.md) als überfällig und
hätte **jeden Abend** eine Meldung ausgelöst. Der Inhaber hat die Zeitpunkte
daraufhin nachgeprüft und auf ±5 Minuten festgelegt.

**Ausgeliefert ist die Sperre leer.** Wer keine zweite Anwendung an derselben
TWS betreibt, erbt keine Wartezeit. `radius_minuten: 0` schaltet sie ab, ohne
die Zeitpunkte löschen zu müssen — der Weg zurück ohne Deployment.

## Was diese Entscheidung nicht ist

**Kein Nachweis.** Ob die fehlenden Optionsdaten von dieser Überschneidung
kommen, ist nicht belegt. Die Historienrate zählt IBKR je Client-ID; dort
konkurriert nichts. Wo die beiden Anwendungen sich nachweislich teilen, sind
die Marktdatenleitungen. Bleibt der Befund nach dieser Änderung bestehen, ist
der Verbindungswechsel aus ADR 0069 der nächste Verdächtige — und dann sagt
die Spalte `LEER` im Betriebsbericht, ob es alle Kandidaten eines Abends
trifft (Verbindung) oder einzelne (Überschneidung).
