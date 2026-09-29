# ADR 0072: Der Export übernimmt die Kerzenserien des Laufs

- Status: Vorgeschlagen
- Datum: 2026-09-29
- Ergänzt: [ADR 0068](0068-export-rechnet-abgeschlossene-laeufe-nicht-neu.md) und
  [ADR 0069](0069-backfill-und-analyse-verzahnt.md)

## Kontext

Der Export zeichnet für jede Aktie einen Chart und leitet dafür die
Kerzenserie ab — aus denselben Bars, mit denselben Parametern, zum selben
Ergebnis wie die Analyse eine halbe Stunde vorher.

**Gemessen am 2026-09-29 auf dem Server**, `cli publish` allein:

```
export_zerlegung: chart_kerzenserie 655.4 s (192x), chart_aufbau 67.7 s (191x),
aktie_backtest 9.0 s (192x), optionsmessung 2.5 s (1x),
aktie_berichtsliste 2.4 s (192x), uebersichten 2.1 s (1x), bericht 1.9 s (216x), …
Dashboard-Export fertig nach 771.0 s
```

**723 der 771 Sekunden sind die Charts**, davon 655 das bloße Ableiten der
Serien. Alles andere zusammen kostet keine 50 Sekunden.

ADR 0068 hat den Übersprung für die *Berichte* gebaut und die Charts nicht
angefasst — sie ändern sich täglich, ein Übersprung wäre dort falsch. Damit
blieb der größte Posten unberührt, und der Export ist seit dem 2026-09-23 der
Grund, aus dem der Tageslauf sein Zeitfenster nicht mehr schafft: Analyse und
Meldung sind fertig, `dispatcher_runs` bleibt trotzdem auf `running`.

Die Serien liegen zu diesem Zeitpunkt bereits vor. Der Lauf hält sie bis zum
Schluss, weil die Optionsanalyse in Phase 1b Kurs und Datum der
Entscheidungskerze daraus nimmt (ADR 0069).

## Entscheidung

Die Analyse legt ihre gerechneten Kerzenserien in einem `Kerzenvorrat` ab;
der Export nimmt sie von dort, statt sie ein zweites Mal abzuleiten.

Vier Festlegungen:

1. **Der Vorrat ist eine Abkürzung, keine Quelle.** Was nicht darin liegt,
   wird gerechnet wie bisher. Die Wiederholsperre ([ADR 0054](0054-wiederholsperre-im-tageslauf.md))
   nimmt der Analyse täglich ein paar Dutzend Titel ab, und die brauchen
   trotzdem einen Chart. Ein Fehltreffer ist der Normalfall.

2. **Er lebt genau einen Lauf lang.** Kein Zwischenspeicher über Tage —
   jeder Handelstag bringt eine neue Kerze.

3. **Übernommen wird nur bei nachweislich gleicher Quelle:**
   `market_data.provider == "ibkr"` **und** `market_data.source == "stored"`.
   Darüber entscheidet der Composition Root, nicht der Vorrat.

4. **Er kostet keinen zusätzlichen Speicher.** Die Serien hält der Lauf
   ohnehin; der Vorrat verweist auf dieselben Objekte.

### Warum Punkt 3 nicht verhandelbar ist

`build_chart_market_data` liest **immer** den Bestand und liest
`market_data.provider` ausdrücklich *nicht*. Der Grund steht in seinem
Docstring: Auf dem Server steht dort `fixture`, damit `git pull` keinen
lokalen Diff vorfindet; die produktive Quelle wird je Lauf über die
Kommandozeile geschaltet. Wer den Wert dort erbte, baute Charts aus
**erfundenen Kursen**, die neben echten Analyseergebnissen stünden und nicht
als erfunden zu erkennen wären. Das verbietet Doc 12 („Keine erfundenen
Werte"), und es ist beim ersten Export auf dem Server tatsächlich passiert.

Eine Übernahme hätte genau dieses Tor umgangen: Die Serien kämen dann nicht
aus der Chartquelle, sondern aus der Analyse — und die läuft auf dem
Fixture-Anbieter, wenn er eingestellt ist.

`source: live` ist aus demselben Grund ausgeschlossen: Die Analyse holte ihre
Kerzen dann direkt von der TWS, die Chartquelle nimmt sie aus dem Bestand.
Dass beide zum selben Ergebnis kommen, ist wahrscheinlich und nicht
zugesichert — und „wahrscheinlich" ist hier zu wenig.

## Folgen

Bei 192 Titeln und rund 40 gesperrten übernimmt der Export etwa 150 Serien
und leitet 40 selbst ab. Erwartet: **655 s → rund 140 s**, der Export damit
von knapp 13 auf gut 4 Minuten.

Die Zahl steht noch nicht fest. Sie gehört in die nächste Messung, und
`export_zerlegung` weist sie aus: Das Feld `uebernommene_serien` sagt, wie
viele Ableitungen entfallen sind.

**Was dieses ADR ausdrücklich nicht erklärt:** Derselbe Export braucht
innerhalb des Tageslaufs rund 45 Sekunden je Symbol statt der 3,4, die er
allein braucht (Protokoll vom 2026-09-28, 19:54–19:59 UTC). Der Faktor ist
gemessen und unerklärt; Vermutungen gibt es (Speicherdruck, eine nach der
Optionsanalyse offen gebliebene TWS-Verbindung), Belege nicht. Diese
Entscheidung verringert die Arbeit; sie erklärt den Faktor nicht und ersetzt
seine Klärung nicht.

## Alternativen

**Den Chart schon in der Analyse bauen und nur das fertige JSON
weiterreichen.** Der ursprüngliche Plan sah das vor, um kein Speicherrisiko
einzugehen. Es ist keines: Die Serien bleiben ohnehin bis zum Ende des Laufs
im Speicher. Der Chart-Aufbau kostet zudem nur 67,7 s von 723 — die
Verlagerung brächte fast nichts und zöge den Präsentationscode in die
Analyse.

**Die Serie flacher ableiten** (weniger Historie je Chart). Das änderte den
Chart und damit das, was der Inhaber sieht. Eine Beschleunigung, die das
Ergebnis verändert, ist in diesem Zusammenhang keine.
