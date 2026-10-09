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

Der Anlass war eine Beobachtung des Inhabers: In manchen Telegram-Meldungen
fehlen die Optionsdaten.

**Dieser Anlass ist inzwischen widerlegt.** Die Messung über zwanzig
Handelstage (2026-09-09 bis 2026-10-08) zeigt in der Spalte „ohne
Optionsstatus" **null** — an jedem einzelnen Tag. Die Optionsanalyse ist nie
ausgefallen, weder durch eine Überschneidung noch durch den
Verbindungswechsel aus [ADR 0069](0069-backfill-und-analyse-verzahnt.md).
Was fehlt, ist `INSUFFICIENT_DATA`: Die Kette kam an, es qualifizierte sich
kein Put. Das ist eine Aussage über den Markt oder über einen Filter und hat
mit der TWS nichts zu tun.

Diese Entscheidung bleibt trotzdem stehen, und zwar mit geänderter
Begründung: **nicht als Behebung eines gemessenen Fehlers, sondern als
Versicherung.** Die Marktdatenleitungen sind nachweislich eine geteilte
Kontoressource; dass bisher nichts ausgefallen ist, heißt nicht, dass nichts
ausfallen kann. Die Kosten kennt der Inhaber (zehn Minuten), den Nutzen kann
er abschätzen, und er hat die Zeitpunkte am 2026-10-09 ausdrücklich validiert
und für verbindlich erklärt.

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

   **Die Wartezeit lässt sich aber abbrechen**, und das ist keine Zugabe. Der
   verzahnte Lauf ([ADR 0069](0069-backfill-und-analyse-verzahnt.md)) beendet
   den Backfill-Thread über ein Signal und wartet in `faden.join()` auf ihn,
   während er die Dispatcher-Sperre hält. Ohne Abbruchhaken liefe der Thread
   nach einem früh abgebrochenen Lauf das ganze Fenster zu Ende, und der
   nächste Start in fünfzehn Minuten endete mit „in Arbeit" — genau die Zeit,
   die das frühe Datengate sparen soll. Die Warteschleife fragt das Signal
   deshalb zwischen ihren Fünf-Sekunden-Schritten ab.

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
fertig: **Ende gegen 13:35 statt 13:25.**

Dass das zweite Fenster um 14:10 und das freitägliche um 14:40 hinter dem Lauf
liegen, ist eine Aussage über **heute** und keine dauerhafte. Die Schwellen,
weil die Watchliste wachsen soll:

| Ab … Symbolen | passiert |
|---|---|
| 110 | das Fenster 13:10 wird erreicht (heute: 192, also längst) |
| ~383 | das Fenster 14:10 wird erreicht und kostet weitere zehn Minuten |
| ~546 | der Backfill erreicht die Nachholfrist 14:50 von sich aus |

Bei den heutigen 192 Symbolen liegt zwischen uns und der zweiten Schwelle
etwa der doppelte Bestand.

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

**Im Code ist die Sperre leer voreingestellt**, in `config/default.yaml`
stehen aber die Zeitpunkte des Inhabers. Wer dieses Repository klont und
`provider: ibkr` einschaltet, erbt damit einen fremden Handelsplan — das ist
in Kauf genommen, weil die Datei ohnehin der Ort ist, an dem der Betrieb
dieses einen Servers beschrieben wird (wie die Watchlist-Dateien und die
Zeitzone). `radius_minuten: 0` schaltet die Sperre ab, ohne die Zeitpunkte
löschen zu müssen — der Weg zurück ohne Deployment.

Der Radius ist nach oben auf 30 Minuten begrenzt. Nicht aus technischer Not,
sondern weil diese Datei von Hand gepflegt wird: Ein `50` statt `5` ließe die
drei Fenster zu einer Sperre von 11:35 bis 16:25 verschmelzen, der Lauf
begänne mitten darin, screente nie und meldete sich jeden Abend als
überfällig. Beim Aufbau steht die geltende Sperre als Zeile im Protokoll —
der einzige Ort, an dem ein solcher Fehler **vor** dem Lauf auffällt.

## Was diese Entscheidung nicht ist

**Keine Behebung des beobachteten Befundes.** Dass in Meldungen
Optionsdaten fehlen, hat eine andere Ursache — siehe Kontext. Diese
Entscheidung verhindert eine Störung, die eintreten *könnte*, und keine, die
eingetreten *ist*.

**Und kein Ersatz für die offene Frage.** Warum sich seit Ende September
deutlich weniger Puts qualifizieren — am 2026-10-06 nur einer von zwanzig
Kandidaten, davor fast alle —, ist unbeantwortet. `options_reason` nennt den
Grund im Wortlaut, und der entscheidet, ob es der Markt ist oder ein
Parameter. Das gehört in einen eigenen Beschluss und nicht hierher.
