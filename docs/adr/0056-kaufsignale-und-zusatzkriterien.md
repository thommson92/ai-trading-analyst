# ADR 0056: Zwei Kaufsignale und ein Zusatzkriterium — und Signal B ohne Gap-up-Klausel

- Status: Angenommen
- Datum: 2026-09-02
- Ergänzt und ändert in Teilen: [ADR 0010](0010-gate-g1-freigegeben.md),
  [ADR 0045](0045-schwellen-der-score-teilwerte.md)

## Kontext

Seit Gate G1 ([ADR 0010](0010-gate-g1-freigegeben.md)) gilt die
2-aus-3-Kandidatenregel: Drei Signalformeln, mindestens zwei davon müssen im
Sechs-Kerzen-Fenster feuern. Der erste scharfe Verbundlauf vom 2026-09-01 hat
36 Kandidaten geliefert — für eine Watchliste von rund 190 Titeln eine hohe
Quote, und mit ihr die Frage, ob die Regel scharf genug trennt.

Der Projektinhaber hat dazu die chart-technischen Kaufsignale erneut
festgehalten — als Bild, das seinem TradingView-Layout entspricht:
[docs/trading_signals/Kaufsignale_EMA.png](../trading_signals/Kaufsignale_EMA.png).
Es definiert zwei der drei bestehenden Signale:

> **Kaufsignal 2:** Kerze (Preis) schneidet den EMA 20 (blau) von unten nach
> oben und schließt darüber.
>
> **Kaufsignal 3:** EMA 5 (schwarz) schneidet EMA 20 (blau) von unten nach
> oben und schließt darüber.

Der Abgleich mit dem Code ergab: **Signal C entspricht Kaufsignal 3 exakt.**
Signal B enthält gegenüber Kaufsignal 2 eine zusätzliche Bedingung, die im
Bild nicht steht — dazu Abschnitt 2.

Dazu kommen zwei Beobachtungen des Projektinhabers, die bisher in keiner
Regel stehen:

1. Ein RSI unter 30 zeigt einen überverkauften Zustand. Der anschließende
   Schnitt der RSI-Glättung von unten (Signal A) ist dann möglicherweise ein
   starkes Zeichen für das Ende des Abwärtstrends — die beiden zusammen sagen
   mehr als jedes für sich.
2. Hat der EMA 5 den EMA 20 kurz zuvor **von oben nach unten** geschnitten,
   ist der anschließende Schnitt nach oben wenig aussagekräftig: Das ist
   Gezappel um die Linie, kein Trendwechsel.

## Entscheidung

**Kandidat ist, wer mindestens zwei der drei Kaufsignale erfüllt *und*
zusätzlich mindestens eines der beiden neuen Zusatzkriterien.**

Die fünf Kriterien zerfallen dabei in zwei Klassen, die nicht gegeneinander
aufgerechnet werden:

**Kaufsignale** — jedes beschreibt ein *Ereignis* im Kursverlauf. Mindestens
zwei müssen feuern, wie schon vor dieser Änderung:

| # | Signaltyp | Formel | Auswertung |
|---|---|---|---|
| A | `RSI_CROSS` | `RSI[i−1] ≤ RSI_MA[i−1] ∧ RSI[i] > RSI_MA[i]` | Fenster |
| B | `PRICE_EMA20_BREAKOUT` | `close[i−1] ≤ EMA20[i−1] ∧ close[i] > EMA20[i]` | Fenster |
| C | `EMA5_EMA20_CROSS` | `EMA5[i−1] ≤ EMA20[i−1] ∧ EMA5[i] > EMA20[i]` | Fenster |

**Zusatzkriterien** — sie beschreiben die *Lage*, in der ein Kaufsignal
auftritt. Mindestens eines muss erfüllt sein:

| # | Signaltyp | Formel | Auswertung |
|---|---|---|---|
| D | `RSI_OVERSOLD` | `RSI[i] < 30` | Fenster |
| E | `NO_RECENT_EMA_DOWNCROSS` | kein `i ∈ {t−4 … t}` mit `EMA5[i−1] ≥ EMA20[i−1] ∧ EMA5[i] < EMA20[i]` | einmal an `t` |

A und C bleiben unverändert. Im Einzelnen:

### 1. Zwei Klassen von Kriterien

A bis D sind **Ereigniskriterien**: Sie werden für jede Kerze des
Sechs-Kerzen-Fensters (`t−5 … t`) geprüft und gelten als erfüllt, sobald sie
an *einer* Fensterkerze zutreffen — die Zählung bleibt pro Typ, nicht pro
Ereignis (Prüfvorlage Abschnitt 3.3). Das gilt ausdrücklich auch für das neue
Kriterium D: Gefragt ist, ob der Titel im Fenster überverkauft **war**, nicht
ob er es am Stichtag noch ist. Ein RSI, der aus dem überverkauften Bereich
heraus nach oben dreht, ist genau der beschriebene Fall — die Erholung soll
das Kriterium nicht wieder entwerten.

E ist ein **Zustandskriterium** und wird genau einmal ausgewertet, an der
Entscheidungskerze `t`. Es über das Fenster zu oderln wäre sinnlos: „In
irgendeinem der letzten sechs Fünf-Kerzen-Fenster gab es kein Abwärtskreuz"
ist fast immer wahr und trennt nichts.

Die Einteilung nach *Fenster* und *Entscheidungskerze* ist eine Aussage
darüber, **wann** ein Kriterium ausgewertet wird. Sie ist nicht dieselbe wie
die Einteilung in Kaufsignale und Zusatzkriterien, die sagt, **wie** ein
Kriterium zählt: D ist ein Fensterkriterium und trotzdem kein Kaufsignal.

### 2. Signal B verliert die Gap-up-Klausel

Bisher verlangte Signal B zusätzlich `open[t] ≤ EMA20[t]`: Die Kerze musste
unterhalb oder auf dem EMA 20 eröffnen, damit ihr Körper die Linie
tatsächlich durchdringt. Eine Kerze, die über dem EMA 20 eröffnet und
darüber schließt, feuerte nicht — sie „schneidet" die Linie geometrisch
nicht, sie springt über sie hinweg.

**Diese Bedingung entfällt.** Maßgeblich ist das Bild, und es sagt nur:
schneidet von unten nach oben und schließt darüber. Bezugspunkt ist damit
der Schlusskurs der Vorkerze, nicht die Eröffnung der aktuellen. Ein Gap-up
über den EMA 20 erfüllt das Signal ab sofort.

Der Preis dieser Entscheidung ist benannt: Signal B wird durchlässiger, und
ein Eröffnungssprung über die Linie ist ein anderer Vorgang als ein
Durchlaufen während der Sitzung. Die Gegenrechnung ist das zusätzlich
geforderte Zusatzkriterium (Abschnitt 3), und ein Gap-up bleibt ein
Kursanstieg über den gleitenden Durchschnitt. Der Fall B4 der Prüfvorlage
kehrt sich damit um.

### 3. Warum es keine „drei von fünf"-Regel ist

Der naheliegende Weg wäre gewesen, alle fünf Kriterien gleich zu zählen und
die Schwelle von zwei auf drei zu heben. Er wurde gebaut, gemessen und
verworfen.

**Gemessen am Golden Master lieferte er mehr Kandidaten als die alte Regel,
nicht weniger** — AAPL 101 → 116, MSFT 122 → 152. Der Grund: E ist in ruhiger
Lage fast immer erfüllt, und D beschreibt einen Zustand, kein Ereignis. Beide
zusammen ersetzen dann ein zweites Kaufsignal, und ein einzelnes
Kreuzungsereignis genügt zur Qualifikation. Bei MSFT hätten 26 der 152
Kandidaten auf genau einem Kaufsignal gestanden.

Deshalb zählen die Klassen getrennt. `screening.required_crossing_signals`
bleibt bei **2** und bezieht sich nur noch auf die Kaufsignale; dass
mindestens ein Zusatzkriterium hinzukommen muss, steht als Regelsemantik im
Domain-Code.

Die so entstandene Regel verlangt **mehr als die frühere**: Jeder Kandidat
erfüllt weiterhin zwei Kaufsignale, und zusätzlich muss die Lage stimmen.
Gemessen: AAPL 101 → 99, MSFT 122 → 111.

Die neue Kandidatenmenge ist deshalb aber **keine Teilmenge** der alten. Weil
Signal B im selben Schritt gelockert wurde (Abschnitt 2), kommen Titel hinzu,
die früher an der Gap-up-Klausel scheiterten — am Golden Master 11 bei AAPL
und 10 bei MSFT. Unterm Strich sinkt die Zahl, aber es ist ein Austausch und
keine reine Verengung. Wer die beiden Wirkungen getrennt sehen will, findet
sie in den zwei Golden-Master-Aufzeichnungen dieses Zweigs.

### 4. Die Schwellenwerte 30 und fünf Kerzen stehen im Code, nicht in der Konfiguration

`RSI_OVERSOLD_LEVEL = 30.0` und das Rückschaufenster von fünf Kerzen für E
(die Entscheidungskerze und ihre vier Vorgänger) sind Modulkonstanten in
`domain/screening/signals.py`.

Begründung: Sie sind Regelsemantik, keine Betriebsparameter. Was die Regel
bedeutet, hängt an `SIGNAL_RULE_VERSION` — und diese Version steht an jedem
gespeicherten Ergebnis. Wäre die RSI-Schwelle in `config/default.yaml`
verstellbar, könnten zwei Läufe dieselbe Regelversion tragen und dennoch
Verschiedenes gerechnet haben. Die Indikatorparameter (Längen, Methoden)
stehen aus dem umgekehrten Grund in der Konfiguration: Sie beschreiben, wie
gerechnet wird, und sind über Gate G1 gebunden.

### 5. Score-Teilwerte für drei bis fünf Signale

[ADR 0045](0045-schwellen-der-score-teilwerte.md) Abschnitt 4 bildet ab:
3 von 3 → 10, 2 von 3 → 6. Diese Abbildung wird ersetzt durch:

| Erfüllte Kriterien | Teilwert |
|---|---|
| 5 | 10 |
| 4 | 8 |
| 3 | 6 |

Die Endpunkte bleiben, wo sie waren: Das Maximum bekommt 10, das gerade noch
qualifizierende Minimum 6 — und drei ist tatsächlich das Minimum, denn ein
Kandidat trägt immer zwei Kaufsignale und mindestens ein Zusatzkriterium.
Dazwischen linear. Das bleibt eine **Setzung** und
keine Messung, mit derselben Begründung wie in ADR 0045 — es gibt keine
Verteilung, an der sich etwas kalibrieren ließe. Unter drei Signalen ist eine
Aktie kein Kandidat; über einen Fall, den es nicht gibt, wird weiterhin
nichts behauptet.

`scoring.swing_version` steigt deshalb von `1.2` auf **`1.3`**: Die
Versionsnummern steigen, wenn sich Komponenten, Gewichte oder Schwellen
ändern.

### 6. Neue Regelversion

`SIGNAL_RULE_VERSION` steht auf `g1-pruefvorlage-2026-09-02`. Die maßgebliche
fachliche Beschreibung bleibt
[g1-pruefvorlage.md](../requirements/g1-pruefvorlage.md); sie ist auf das
Fünf-Kriterien-Regelwerk fortgeschrieben.

## Konsequenzen

**Gemessene Wirkung auf die Kandidatenzahl.** Am Golden Master, gegen die
frühere Regel:

| Fall | vorher | nachher |
|---|---|---|
| AAPL | 101 | 99 |
| MSFT | 122 | 111 |

Der Rückgang ist moderat, und das ist erklärbar: Signal B wurde zugleich
durchlässiger, und E ist in ruhiger Lage meist ohnehin erfüllt. Die Regel
wirkt dort, wo sie wirken soll — bei Titeln, die kurz zuvor ein
Abwärtskreuz gezeigt haben und nicht überverkauft waren.

Das ist ausdrücklich eine Änderung des Verfahrens, nicht seiner Umsetzung.
Der erste Tageslauf nach dem Merge misst mit der neuen Regel; seine
Ergebnisse tragen die neue Regelversion. Alte Analysen bleiben unangetastet
(Unveränderlichkeit, Doc 10 §6.11) — sie sind mit neuen nicht unmittelbar
vergleichbar, und die Regelversion an jedem Ergebnis ist genau dafür da.

**Der Kombinationsraum des Backtests wächst von 4 auf 12.** Der Backtest
weist Kennzahlen je qualifizierender Signalkombination aus: vier
Kaufsignal-Kombinationen (drei Paare und das Tripel) mal drei Kombinationen
der Zusatzkriterien (D, E, beide). Je Aktie und Lauf entstehen damit 36 statt
12 Ergebniszeilen. Die Folge ist keine technische,
sondern eine statistische: Die Ereignisse verteilen sich auf mehr
Kombinationen, die Stichprobe je Kombination wird dünner, und die
Signalstatistik im Swing-Score (die exakt die gefeuerte Kombination sucht)
wird häufiger `LOW_SAMPLE` oder `INSUFFICIENT_DATA` melden. Das ist der
ehrliche Ausweis einer dünnen Grundlage und wird nicht durch Zusammenlegen
von Kombinationen kaschiert.

**Der Datenbank-Enum `signaltype` wird erweitert** — eine Migration mit
`ALTER TYPE … ADD VALUE`. Das ist in PostgreSQL praktisch nicht umkehrbar:
Das Downgrade baut den Typ neu auf und **bricht ab**, sobald bereits Zeilen
die neuen Werte tragen. Ein Rückbau nach dem ersten produktiven Lauf ist
damit keine Migrationsfrage mehr, sondern eine Datenfrage. Zeilen zu löschen,
um ein Downgrade zu ermöglichen, wäre ein Verstoß gegen die
Unveränderlichkeit und findet nicht statt.

**Der Golden Master wird neu aufgezeichnet.** Er hält das Verfahren fest, und
das Verfahren ändert sich hier gewollt — in zwei Schritten (erst die
B-Lockerung, dann Kriterien und Schwelle), damit die beiden Diffs zeigen, was
jeweils gewirkt hat.

**Die Meldung passt sich selbst an.** Sie zählt seit
[ADR 0055](0055-put-vorschlag-und-signalzahl-in-der-ergebnismeldung.md) gegen
`len(SignalType)` und zeigt künftig `3/5 Signale`. Die dort gemessenen
Blockgrenzen (23 volle, 82 kurze Blöcke) bleiben gültig: `x/5` ist
zeichengleich mit `x/3`.

**Der Konfigurationsschlüssel ist umbenannt.** Aus
`screening.required_signal_count` wird `screening.required_crossing_signals`
— der alte Name bezöge sich jetzt auf eine Zahl, die er nicht mehr meint.
Alle Konfigurationsabschnitte lehnen unbekannte Schlüssel ab (ein Tippfehler
soll auffallen, statt still zu einem Vorgabewert zu werden). Eine
Override-Datei auf dem Server, die den alten Namen noch führt, lässt den Lauf
deshalb beim Laden abbrechen. Das gehört vor der Inbetriebnahme geprüft.

**Was nicht berührt ist:** die Indikatorparameter aus Gate G1 (RSI 14/Wilder,
RSI-MA 14/SMA, EMA 5/20, Warm-up 250), das Sechs-Kerzen-Fenster, der Umgang
mit fehlenden Daten (eine Datenlücke ist kein negatives Signal — auch die
neuen Kriterien lösen `DataIncompleteError` aus statt `False` zu liefern),
der Einstiegszeitpunkt und der Cooldown im Backtest, sowie die Trennung von
deterministischer Rechnung und KI-Interpretation. Kein Sprachmodell ist an
dieser Regel beteiligt.
