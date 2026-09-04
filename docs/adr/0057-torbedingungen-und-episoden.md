# ADR 0057: Torbedingungen an der Entscheidungskerze, Episoden statt Cooldown

- Status: Angenommen
- Datum: 2026-09-03
- Ergänzt und ändert in Teilen: [ADR 0056](0056-kaufsignale-und-zusatzkriterien.md)

## Kontext

Mit [ADR 0056](0056-kaufsignale-und-zusatzkriterien.md) ist die Kandidatenregel
zweistufig geworden. Der Validierungschart hat sie erstmals an echten Kursen
sichtbar gemacht — AAPL, 830 Kerzen aus dem Bestand des Servers, **51 rohe
Entscheidungspunkte**, an denen die Regel zutraf. Der Projektinhaber hat vier
Stellen herausgegriffen; sie liegen als Bildbelege in
[docs/backtesting/](../backtesting/). Alle vier sind nachgerechnet worden.

**① `Zusammenfassung.png` — 01./02./06.07.2026.** Drei Trigger auf einer
einzigen Aufwärtsbewegung. Nachgerechnet teilen sie dieselben Signalereignisse:
Das RSI-Kreuz auf Kerze 741, der EMA20-Durchbruch auf 742 und das EMA-Kreuz auf
744 tauchen in allen drei Auswertungsfenstern auf. Der Backtest zählt sie über
den Fünf-Kerzen-Cooldown schon heute als **ein** Ereignis — der Chart zeigte
die rohen Punkte und war darin missverständlich.

**② `Fraglich.png` — 28.08.2026 (Kerze 825).** Alle drei Kaufsignale feuerten
am 26.08., **vier Kerzen vor** der Entscheidungskerze; an ihr selbst kreuzte
nichts. Der Trigger steht ausschließlich auf Vergangenem.

**③ `Negativkerze.png` — 16./17.06.2026, unmittelbar vor dem Absturz von 300
auf 275.** Der 16.06. steht auf einer Kreuzung an der Entscheidungskerze
selbst, die den EMA20 aber nur um **0,04 ATR** überschreitet. Der 17.06. trägt
gar keine frische Kreuzung mehr, ist eine rote Kerze und schließt bereits
**unter** dem EMA20.

**④ `Gruppierung.png` — 18. bis 25.08.2026.** Die ersten drei Trigger sind
derselbe Fall wie ①. Die letzten beiden werden **nicht** vom vorherigen
Ereignis begünstigt — gemessen teilen sie mit ihm kein einziges Signalereignis;
sie stehen auf eigenen, frischen Mini-Kreuzungen vom 24.08.

Zwei Muster ziehen sich durch: Ein Trigger kann **ausschließlich auf alten
Signalen** stehen (②, ④ zweiter Teil), und er kann in einer Lage entstehen, die
zum Zeitpunkt der Entscheidung **gar nicht mehr aufwärts zeigt** (③). Beides
ist mit der Regel aus ADR 0056 vereinbar, weil sie nur fragt, *ob* etwas im
Fenster geschehen ist, nie *wann* und nie, *wie die Lage jetzt ist*.

## Entscheidung

### 1. Zwei Torbedingungen an der Entscheidungskerze

Eine Aktie, deren Signalmenge die Regel aus ADR 0056 erfüllt, wird nur dann
Kandidat, wenn zusätzlich **beide** Torbedingungen gelten:

| | Torbedingung | Formel |
|---|---|---|
| **T1** | **Frische** — mindestens ein Kaufsignal feuert an der Entscheidungskerze oder ihrer Vorkerze | ein `s ∈ CROSSING_SIGNALS` mit `s(t)` oder `s(t−1)` |
| **T2** | **Bestätigung** — der Schlusskurs liegt über dem EMA 20 | `close[t] > EMA20[t]` |

Maßgeblich für T1 ist das **tatsächliche Feuern an der Kerze**, nicht die
gespeicherte früheste Fundstelle des Signaltyps (Prüfvorlage Abschnitt 4.3).
Feuert ein Typ erst auf `t−4` und erneut auf `t`, ist er frisch. Die
gespeicherte Position dient dem Audit; sie ist keine Aussage darüber, ob das
Signal noch anliegt.

T2 vergleicht strikt (`>`), nach derselben Konvention wie jede andere
Überschreitung in Abschnitt 1.4. Gleichstand genügt nicht.

`MAX_CROSSING_SIGNAL_AGE_CANDLES = 1` steht als Modulkonstante im Code, nicht
in der Konfiguration — dieselbe Begründung wie für die Schwellen aus ADR 0056
Abschnitt 4: Regelsemantik hängt an `SIGNAL_RULE_VERSION`, und ein
verstellbarer Wert entkoppelte das Verhalten von der Version, die an jedem
gespeicherten Ergebnis steht.

### 2. Torbedingungen sind Filter, keine gezählten Kriterien

Sie werden **nicht** zu `SignalType` hinzugefügt und zählen nicht in
`fired_signal_types`. Ein Kandidat trägt weiterhin drei bis fünf erfüllte
Kriterien; die Score-Teilwerte aus ADR 0056 bleiben unverändert gültig, und
`scoring.swing_version` steigt **nicht** — die Abbildung hat sich nicht
geändert, nur die Menge dessen, was überhaupt bewertet wird. Diese trägt die
Signalregel-Version.

Die Folge: **keine Datenbankmigration.** Der Enumtyp `signaltype` bleibt bei
fünf Werten, `signal_events` und `backtest_results.signal_types` bleiben
unberührt. Scheitert eine Torbedingung, entsteht ein gewöhnliches
`NOT_CANDIDATE` mit einer Begründung in der bestehenden Spalte `reason`
(`gate:stale_crossing_signals`, `gate:close_not_above_ema20`, bei beidem
zusammengesetzt). Die gefeuerten Signale bleiben am Ergebnis erhalten — es
soll nachlesbar sein, *was* erfüllt war und *woran* es dennoch scheiterte.

Geprüft werden die Torbedingungen nur, wenn die Signalmenge die Regel erfüllt.
Ein Ergebnis, das schon an der Signalzahl scheitert, trägt wie bisher keine
Begründung; „zu wenige Signale" ist keine verworfene Qualifikation.

### 3. Gemessene Wirkung

An den beiden echten Kursreihen des Golden Masters, gegen die rohen
Entscheidungspunkte:

| | AAPL | MSFT |
|---|---|---|
| ohne Torbedingungen (ADR 0056) | 51 | 55 |
| nur T1 (Frische) | 30 | 30 |
| nur T2 (Bestätigung) | 45 | 49 |
| **T1 und T2 zusammen** | **29** | **27** |

T1 trägt den weitaus größten Teil, aber nicht alles: Über die Frische hinaus
entfernt die Bestätigung noch einen weiteren Punkt bei AAPL und drei bei
MSFT. Beide Tore werden gebraucht.

Von den vier beanstandeten Stellen fallen der 28.08. (②) sowie die Nachzügler
vom 17.06. und 25.08. weg. Die vier klar guten Ausbrüche der Reihe —
17.07.2025, 06.08.2025, 01.07.2026, 18.08.2026 — bleiben sämtlich erhalten.

**Nicht gefangen werden der 16.06. und der 24.08.**, weil beide eine frische
Kreuzung an der Entscheidungskerze tragen und über dem EMA 20 schließen. Sie
sind der Preis dieser Entscheidung, und sie sind benannt.

### 4. Verworfen: ein Stärkefilter über den ATR

Naheliegend wäre gewesen, zusätzlich einen Mindestabstand zum EMA 20 zu
fordern. `close[t] − EMA20[t] ≥ 0,4 · ATR(14)` entfernt alle vier
beanstandeten Stellen (AAPL 34, MSFT 38).

**Trotzdem nicht übernommen.** Die Schwelle 0,4 ist an genau diesen vier
Beispielen abgelesen — der 16.06. liegt bei 0,04, der 24.08. bei 0,35, die
guten Fälle bei 0,53 bis 1,86. Eine Grenze, die zwischen zwei Messpunkten
hindurchgelegt wird, ist keine gemessene Grenze, sondern eine an die
Stichprobe angepasste. Der Fehler wäre derselbe, den ADR 0045 für die
Score-Schwellen ausdrücklich vermeidet.

Hinzu kommt: Der ATR ist heute kein Bestandteil des Signalkerns. Er lebt in
`domain/technical`, das seinerseits auf `domain/screening` aufsetzt; ein ATR
im Screening wäre eine neue deterministische Kennzahl an einer Stelle, die
bewusst schmal gehalten ist.

Die Option bleibt offen und ist hier festgehalten. Sie wird wieder
aufgenommen, wenn eine Messung außerhalb dieser vier Beispiele vorliegt —
etwa aus mehreren Titeln über die volle Historie.

### 5. Im Backtest zählt die Episode, nicht der einzelne Trigger

Der pauschale Fünf-Kerzen-Cooldown **entfällt**. An seine Stelle tritt die
Ereignis-Verkettung:

> Zwei aufeinanderfolgende Entscheidungspunkte gehören zur selben **Episode**,
> wenn sie mindestens eine **identische Feuerung** teilen — denselben
> Signaltyp an derselben Kerze. Gezählt wird der **erste** Trigger einer
> Episode.

Das ist der Unterschied zwischen „liegt nahe beieinander" und „beruht auf
demselben". Fall ① wird zu einer Episode, weil die drei Trigger nachweislich
dieselben Kreuzungen auswerten. Die letzten beiden Trigger aus ④ bleiben ein
eigenes Ereignis, weil sie keine Feuerung mit den vorherigen teilen — obwohl
sie zeitlich dicht folgen. Ein Cooldown hätte hier nach Kalender getrennt oder
zusammengefasst, ohne den Grund zu kennen.

**Verglichen werden alle tatsächlichen Feuerungen**, genau wie bei T1 und aus
demselben Grund. Die für Bericht und Audit gespeicherte Position nennt je
Signaltyp nur die **früheste** Fundstelle im Fenster; zwei Entscheidungspunkte
können deshalb dieselbe Kreuzung auswerten und dort trotzdem verschiedene
Zahlen tragen, wenn einer von beiden zusätzlich eine ältere Fundstelle sieht.
Nach der gespeicherten Position zerfiele die Episode genau dort, wo sie hält —
gemessen an der eingefrorenen Reihe `synthetic-range` in zwei von 79 Fällen,
und die Abweichung geht immer in dieselbe Richtung: zu viele gezählte
Ereignisse, also genau das, was die Regel verhindern soll.

Der Nachbarvergleich genügt für die transitive Hülle: Teilen sich der erste
und der dritte Punkt eine Feuerung `(X, k)`, so liegt `k` auch im Fenster des
mittleren — die Fenster sind zusammenhängende Kerzenbereiche —, `X` feuert
dort ebenfalls an `k`, und die Kette schließt sich über die Nachbarn. Dieser
Schluss hält nur, weil **jede** Feuerung geführt wird; mit der frühesten
Fundstelle wäre er falsch.

Gemessen ergibt das für AAPL **21 Episoden** aus 51 rohen Triggern; der
Cooldown kam auf 22. Die Zahl ist fast dieselbe — der Gewinn liegt nicht in
ihr, sondern darin, dass sie begründbar ist.

Rohe und gezählte Stichprobengröße werden weiterhin **beide** ausgewiesen.
Der Konfigurationsschlüssel `backtesting.cooldown_candles` verschwindet
ersatzlos; die Verkettung hat keinen Zahlenparameter.

### 6. Was unberührt bleibt

- **Die Live-Wiederholsperre** ([ADR 0054](0054-wiederholsperre-im-tageslauf.md),
  sieben Tage) bleibt, wie sie ist. Sie ist ein anderes Mittel für einen
  anderen Zweck: Sie verhindert Wiederholmeldungen unabhängig davon, ob ein
  neues Signal vorliegt. Die Episodenlogik dorthin zu übertragen wäre eine
  **Lockerung** — der 24.08. stand auf frischen Ereignissen und wäre sechs
  Tage nach dem 18.08. erneut gemeldet worden. Gate-Ergebnisse sperren
  ohnehin nie: Sie sind `NOT_CANDIDATE`, und die Sperre hängt an
  `CANDIDATE`.
- Die Signalformeln, das Sechs-Kerzen-Fenster, der Warm-up von 250 Kerzen, die
  Zählung pro Typ, die Speicherung der Signalkombination und der
  Einstiegszeitpunkt im Backtest.

### 7. Neue Regelversion

`SIGNAL_RULE_VERSION` steht auf `g1-pruefvorlage-2026-09-03`. Sie umfasst
beides — die Torbedingungen **und** die geänderte Zählung im Backtest —, weil
beide in derselben Auslieferung wirksam werden. Eine eigene
„Backtest-Verfahrensversion" entsteht nicht; sie hätte keinen Fall, den die
Regelversion nicht schon trennt.

## Konsequenzen

**Weniger Kandidaten, dünnere Stichproben.** Die Zahl der Entscheidungspunkte
sinkt um gut vierzig Prozent. Im Backtest verteilen sich damit weniger
Ereignisse auf die zwölf Signalkombinationen; `LOW_SAMPLE` und
`INSUFFICIENT_DATA` werden häufiger. Das ist der ehrliche Ausweis einer
dünneren Grundlage und wird nicht durch Zusammenlegen von Kombinationen
kaschiert.

**`deduplicated_event_count` behält seinen Namen und ändert seine Bedeutung** —
aus „nach Cooldown" wird „gezählte Episoden-Ereignisse". Die Spalte wird nicht
migriert; welche Bedeutung eine Zeile trägt, sagt ihre Signalregel-Version.
Ein Umbenennen der Spalte hätte alte Zeilen nicht wahrer gemacht.

**Der Konfigurationsschlüssel `backtesting.cooldown_candles` entfällt.** Alle
Abschnitte lehnen unbekannte Schlüssel ab — eine Override-Datei auf dem
Server, die ihn noch führt, lässt den Lauf beim Laden abbrechen. Dieselbe
Situation wie bei der Umbenennung aus ADR 0056; vor der Inbetriebnahme zu
prüfen.

**Abgelöst werden** die Cooldown-Festlegung in der Projekt-`CLAUDE.md`
(Abschnitt „Backtesting"), die Abweichung ② in
[Doc 07](../07%20-%20Backtesting.md) und die Abgrenzung in
[g1-pruefvorlage.md](../requirements/g1-pruefvorlage.md) Abschnitt 3.4. Der
Satz in ADR 0056, der Einstieg und Cooldown ausdrücklich als unberührt
bezeichnet, gilt für den Cooldown nicht mehr; der Einstiegszeitpunkt bleibt.

**Der Golden Master wird dreimal neu aufgezeichnet** — Torbedingungen,
Snapshot-Erweiterung, Episodenzählung —, damit jeder Diff genau einen Grund
hat.

**Der Validierungschart wird Teil des Projekts** (`cli chart`), damit die
nächste Regeländerung an denselben Bildern geprüft werden kann wie diese.
Er unterscheidet künftig rohe Trigger, gezählte Episoden-Erste und die an
einer Torbedingung gescheiterten Punkte samt Grund.
