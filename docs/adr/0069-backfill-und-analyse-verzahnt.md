# ADR 0069: Backfill und Analyse laufen verzahnt statt nacheinander

- Status: Vorgeschlagen
- Datum: 2026-09-20

## Kontext

Gemessen über dreizehn Läufe (`scripts/laufzeiten.py`, 2026-09-20):

| Abschnitt | Median |
|---|---|
| Backfill + Datengate | **35,2 min** |
| Analyse (Phasen 1–3) | 18,3 min |

Der Backfill ist dabei **konstant 35,2 Minuten, unabhängig von der Zahl der
analysierten Aktien** — bei 121 Titeln genauso wie bei 192. Die Erklärung
steht in der Konfiguration: 192 Symbole × 11 s = 2112 s. Der Backfill läuft
immer über die volle Watchliste; die Wiederholsperre filtert erst die Analyse
([ADR 0054](0054-wiederholsperre-im-tageslauf.md), so gewollt).

IBKR lässt 60 Historienanfragen je zehn Minuten zu und sperrt bei
Überschreitung die **ganze Verbindung**
(`infrastructure/ibkr/bar_source.py`). Das sind 10 Sekunden je Anfrage; der
Code hält 11 s. Damit läuft der Backfill bereits bei rund 91 % des erlaubten
Durchsatzes, und **fast die gesamten 35 Minuten sind `time.sleep`**.

Die Grenze ist eine *Rate*, keine Nebenläufigkeit: Mehr Threads stünden nur
am Lock an, und IBKR lässt je Client-ID ohnehin nur eine Verbindung zu. Der
Backfill lässt sich nicht beschleunigen.

**Beschleunigen lässt sich nur, was währenddessen stillsteht.** Und das ist
alles andere: Seit `market_data.source: stored` rechnet der Screener auf dem
Bestand in PostgreSQL, ohne Netz und ohne TWS. Dass der komplette Backfill
über alle 192 Titel abgeschlossen sein muss, bevor die erste Aktie gerechnet
wird, ist keine fachliche Abhängigkeit — hart ist nur: *Aktie X braucht die
Bars von Aktie X.*

## Entscheidung

### 1. Der Backfill läuft in einem eigenen Thread, die Analyse wartet je Aktie

`DispatchDailyRunUseCase` startet den Backfill und die Analyse gemeinsam. Der
Backfill bleibt unverändert **seriell mit 11 Sekunden Abstand auf einer
Verbindung**; er meldet jedes gesicherte Symbol. Die Analyse geht die
Watchliste in ihrer Reihenfolge durch und wartet vor jeder Aktie, bis deren
Bars liegen.

**Kein Analyse-Pool.** Die Analyse muss nicht je Symbol Schritt halten,
sondern nur in Summe: 18 Minuten passen in 35. Ein Pool brächte hier nichts
als Nebenläufigkeit, die niemand braucht — und jede Nebenläufigkeit, die
nicht gebraucht wird, ist eine Fehlerquelle ohne Gegenwert.

### 2. Die Optionsanalyse wandert hinter den Backfill

Sie ist der einzige Teil der Aktienschleife, der die TWS anfasst, und sie
benutzt **dieselbe Verbindung** wie der Backfill. Zwei Threads an einer
`IbAsyncBarSource` wären nicht nur durch deren Lock serialisiert — die
Verbindung ist an den Thread gebunden, der sie aufgebaut hat
(`_owner_thread`), und ein Wechsel verwirft sie und baut sie neu auf. Bei
abwechselnden Aufrufen also ein Verbindungsaufbau *je Abruf*.

`_prepare_stock` zerfällt deshalb in zwei Teile: alles ohne TWS läuft
verzahnt, die Optionsanalyse läuft danach in einem eigenen Durchgang über die
bis dahin gefundenen Kandidaten.

Die dritte gerichtete Kopplung aus CLAUDE.md bleibt unberührt: Die
Optionsanalyse bekommt den Earnings-Termin weiterhin als optionale Eingabe
gereicht und ermittelt keinen eigenen.

### 3. Das Datengate prüft früher, nicht später

`_require_target_candle` prüft heute **nach** dem vollständigen Backfill, ob
die Zielkerze überhaupt angekommen ist, und bricht sonst ab, bevor gerechnet
wird. Die Prüfung bleibt und behält ihren Zweck — sie wandert nur nach vorn:
**nach den ersten gesicherten Symbolen** statt nach allen.

Sie prüft weiterhin den jüngsten Bar im **gesamten** Bestand, nicht den einer
bestimmten Aktie: Ein einzelner ausgesetzter Titel darf den Lauf nicht
verhindern. Je Aktie greift ohnehin weiterhin `_require_expected_candle`.

### 4. Ein Symbol, das der Backfill nie meldet, hält nichts auf

Die Wartestelle kennt drei Ausgänge: das Symbol ist da, der Backfill ist
fertig (dann kommt es nicht mehr), oder der Backfill ist gescheitert. In den
letzten beiden Fällen rechnet die Analyse sofort weiter — auf dem Bestand,
den es gibt. Ist er zu alt, fällt die Aktie in die bestehende
Fehlerisolation; ist er aktuell genug, ist sie ein reguläres Ergebnis.

**Es gibt keine Zeitgrenze je Symbol.** Eine wäre eine zweite Stelle, an der
über die Vollständigkeit eines Laufs entschieden wird — das entscheidet
`scheduler.minimum_completion_ratio`, und zwar am Ende und nicht mittendrin.

### 5. Reihenfolge, Isolation und Persistenz bleiben unverändert

`outcomes` und `errors` kommen weiterhin in Watchlist-Reihenfolge, die
Fehlerisolation bleibt je Aktie, und Phase 3 persistiert weiterhin seriell im
Hauptthread. Der Analyse-Thread liest nur.

## Begründung

**Zu 1.** Die Verschränkung beschleunigt nichts — sie verlagert vorhandene
Arbeit in vorhandenen Leerlauf. Keine zusätzliche Anfrage, kein Token mehr,
keine geänderte Rechnung. Das ist der Grund, warum sie vor jeder anderen
Optimierung kommt: Sie hat keine Kostenseite.

Die Alternative, den Backfill zu beschleunigen, ist bei 91 % des erlaubten
Durchsatzes nicht vorhanden. Die Alternative, weniger Symbole zu holen, wäre
eine fachliche Änderung (ADR 0054 hält fest, dass der Backfill bewusst auch
gesperrte Titel nachführt).

**Zu 2.** Sie ist die unangenehmste Stelle des Entwurfs, und sie ist nicht
zu umgehen: Eine zweite Client-ID wäre eine Entscheidung über IBKRs
Pacing-Regeln, die dieses Projekt nicht belegt hat. Der Preis ist, dass die
Optionsabrufe der Kandidaten nicht mehr im Leerlauf verschwinden, sondern
hinten anstehen — bei 10 bis 36 Kandidaten sind das wenige Minuten.

**Zu 4.** Die Versuchung wäre, je Symbol eine Frist zu setzen und die Aktie
sonst als Fehler zu führen. Das verschöbe eine Entscheidung über die
Vollständigkeit des Laufs an eine Stelle, die sie nicht überblickt: Ein
langsamer Backfill ist kein Befund über eine einzelne Aktie.

## Konsequenzen

**Positiv**

- Die Analyse verschwindet weitgehend in einem Leerlauf, der ohnehin
  stattfindet. Erwartet: von rund 53 auf rund 37 Minuten bei 192 Titeln.
- Die Decke für eine wachsende Watchliste steigt: Nicht mehr
  Backfill **plus** Analyse müssen ins Fenster passen, sondern im
  Wesentlichen nur noch der Backfill.
- Der Regler `screening.max_concurrent_stocks` gibt es **nicht** — es gibt
  nichts zu regeln. Wer die Verzahnung abschalten will, setzt
  `scheduler.verzahnter_backfill: false`.

**Negativ und offen**

- **Der Tageslauf hat einen zweiten Thread.** Er tut genau eine Sache
  (Bars holen und ablegen) und teilt mit dem Hauptthread nur die
  Datenbank — über getrennte Sitzungen, wie schon bisher. Aber es ist
  Nebenläufigkeit, und die war vorher an dieser Stelle nicht.
- **Ein Fehler im Backfill wird später sichtbar.** Bisher brach er den Lauf
  ab, bevor gerechnet wurde; jetzt läuft die Analyse auf dem vorhandenen
  Bestand weiter. Das Datengate aus Punkt 3 fängt den Hauptfall (gar keine
  neuen Daten) weiterhin früh ab.
- **Die Optionsanalyse läuft nicht mehr in derselben Schleife** wie der Rest
  der Kandidatenarbeit. Die Reihenfolge innerhalb einer Aktie ändert sich
  damit; die Eingaben nicht.
- **Die erwartete Ersparnis ist hergeleitet, nicht gemessen.** Sie steht und
  fällt damit, dass die Analyse in Summe kürzer ist als der Backfill. Heute
  ist sie das mit Abstand (18 gegen 35 Minuten); bei einer deutlich größeren
  Watchliste bleibt das so, weil beide mit der Symbolzahl wachsen — der
  Backfill aber steiler (11 s gegen rund 7 s je Aktie).
