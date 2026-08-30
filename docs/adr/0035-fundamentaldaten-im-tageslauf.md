# ADR 0035: Fundamentaldaten im Tageslauf -- Umfang, Kurs und Speicherung

- Status: Angenommen
- Datum: 2026-08-27

## Kontext

Die deterministische Fundamentalanalyse ist gebaut, an 191 Emittenten
gemessen und ueber `cli fundamental` nachpruefbar
([ADR 0032](0032-fundamentalanalyse-deterministisch.md),
[0033](0033-zwoelfmonatswerte-statt-jahresabschluss.md),
[0034](0034-fundamentaldaten-nach-dem-watchlist-lauf.md)). Was fehlt, ist der
Anschluss an den taeglichen Lauf: Bisher entsteht kein einziger gespeicherter
Fundamentalwert, und die vier bewertungsabhaengigen Kennzahlen fehlen
grundsaetzlich, weil ihnen niemand einen Kurs reicht.

Drei Fragen sind zu entscheiden, und alle drei sind spaeter teuer zu aendern.

## Entscheidung

### 1. Fundamentaldaten entstehen nur fuer Kandidaten

Dasselbe Muster wie die deterministische Chartauswertung und der
Earnings-Filter: Sie laufen, sobald `evaluate_candidate` den Status
`CANDIDATE` ergibt, und sonst nicht.

Der Grund ist derselbe wie dort -- die Fundamentaldaten beschreiben die Lage
eines **Kandidaten** und fliessen ins Scoring. Dazu kommt ein gemessener:
Ein `companyfacts`-Abruf sind rund 4 MB und etwa 1,3 Sekunden. Ueber die
volle Watchliste waeren das taeglich 800 MB und rund vier Minuten, fuer
Zahlen, die sich vierteljaehrlich aendern. Ueber eine Handvoll Kandidaten
sind es rund 20 MB und wenige Sekunden.

Damit stellt sich die Zwischenspeicherungsfrage aus ADR 0032 L6 vorerst
nicht. Sie bleibt offen, nicht beantwortet.

### 2. Der Kurs ist der Schluss der letzten abgeschlossenen Kerze

`series.candles[decision_index].close` -- genau der Kurs, auf dem auch das
Screening und die Chartauswertung stehen. Keine laufende Kerze (CLAUDE.md),
keine zweite Quelle, keine eigene Beschaffung durch das Fundamentalmodul.

Das ist die zweite gerichtete Kopplung aus CLAUDE.md, und sie gehorcht
denselben drei Bedingungen wie die erste:

1. **Optionale Eingabe.** Der Kurs wird hineingereicht, nicht geholt.
2. **Nicht blockierend.** Faellt er weg, entstehen die uebrigen vierzehn
   Kennzahlen vollstaendig; die vier bewertungsabhaengigen fehlen sichtbar.
3. **Keine eigene Ableitung.** Das Fundamentalmodul kennt weder Kerzen noch
   Anbieter.

Der verwendete Kurs wird **am Ergebnis gespeichert** (`price_used`). Ohne ihn
liesse sich ein Kurs-Gewinn-Verhaeltnis spaeter nicht nachrechnen, und die
Kennzahl waere eine Behauptung statt eines Belegs.

### 3. Ein Ausfall der Quelle kostet nur die Fundamentaldaten

`FundamentalDataProviderError` wird **je Aktie** gefangen, innerhalb der
Vorbereitung und nicht erst an ihrem Rand. Das ist der Unterschied, auf den
es ankommt: Die umgebende Fehlerisolation macht aus einer Ausnahme einen
`_PreparedError` und wirft damit das **ganze** Ergebnis der Aktie weg --
Screening, Chartauswertung, Earnings-Filter inklusive. Ein nicht erreichbares
EDGAR ist aber ein normaler Betriebszustand, kein Grund, ein gueltiges
Screening zu verlieren (CLAUDE.md: Analysemodule sind entkoppelt).

Fehlen die Fundamentaldaten, bleibt das Feld leer. Es gibt keinen
Ersatzwert und keinen Platzhalter.

### 4. Gerechnet wird sequentiell in der ersten Phase

Nicht im Nebenlaeufigkeitspool der beiden KI-Agenten. Der Abruf ist eine
gewoehnliche HTTP-Anfrage von reichlich einer Sekunde, kein Modellaufruf von
fuenfzehn Minuten, und die Drossel der SEC (8 Anfragen je Sekunde,
prozessweit) reihte nebenlaeufige Abrufe ohnehin wieder auf. Bei einer
Handvoll Kandidaten kostet das wenige Sekunden.

### 5. Gespeichert wird je Lauf neu

Ein Satz Kennzahlen je Screening-Ergebnis, nach dem Muster von
`technical_zones` und `research_citations`:

- **Kopfdaten als Spalten** auf `screening_results` -- Status, Verfahrens-
  version, Auswertungs- und Abrufzeitpunkt, verwendeter Kurs, Grund,
  Geschaeftsjahre, Abdeckung.
- **Eine Zeile je Kennzahl** in `fundamental_metrics` mit Wert, Einheit,
  Basis, Zeitraum und Herkunft. Die Zahl der Kennzahlen ist nicht fest --
  fehlende entstehen gar nicht --, und jede traegt ihren eigenen Zeitbezug
  (ADR 0033 L2).

Kein Wiederverwenden ueber Laeufe hinweg. Der Preis ist Redundanz: Dieselben
Quartalszahlen stehen an mehreren Tagen mehrfach in der Tabelle. Der Gewinn
ist die Unveraenderlichkeit aus CLAUDE.md -- ein abgeschlossenes Ergebnis
wird nie ueberschrieben, und man sieht jedem Lauf an, worauf er stand.
Geteilte Zeilen haetten genau diese Eigenschaft nicht: Ein spaeterer Lauf mit
geaenderten Daten muesste entweder versionieren oder aendern, und das zweite
waere ein Verstoss.

### 6. Die Herkunft steht an der Kennzahl, die Widersprueche am Ergebnis

Die Quellen einer Kennzahl -- bis zu drei, weil eine Marge auf zwei Tags und
der freie Cashflow auf zwei weiteren steht -- liegen als JSONB an der
Kennzahlenzeile. Sie werden geschrieben und im Ganzen gelesen, nie gefiltert.

Die Tag-Widersprueche liegen als JSONB am Screening-Ergebnis, aus demselben
Grund und einem zweiten: Es sind im Mittel zehn je Aktie und bei einzelnen
ueber vierzig. Als Kindtabelle waeren das mehr Zeilen als fuer alle uebrigen
Analysemodule zusammen, fuer eine rein diagnostische Angabe.

## Begruendung

Entscheidung 1 bis 4 folgen jeweils einem Muster, das im Projekt bereits
steht und sich bewaehrt hat. Neu ist allein die Groessenordnung des Abrufs,
und die spricht in dieselbe Richtung.

Entscheidung 5 ist die einzige, bei der zwei vertretbare Wege gegeneinander
standen. Den Ausschlag gab, dass die Unveraenderlichkeit im Projekt keine
Empfehlung ist, sondern eine Regel -- und dass Speicherplatz die billigste
Groesse in dieser Rechnung ist.

## Konsequenzen

- Ein Kandidat traegt kuenftig alle achtzehn Kennzahlen, die seine
  Einreichungen hergeben, einschliesslich der vier bewertungsabhaengigen.
  Im Watchlist-Lauf ohne Kurs lag die Abdeckung im Median bei 67 Prozent;
  mit Kurs sind bis zu 100 Prozent erreichbar (Apple im Serverlauf).
- Der Tageslauf wird je Kandidat um gut eine Sekunde laenger.
- Eine neue Migration auf `a4c7e91f30b2`.

### Akzeptierte Einschraenkungen

- **L1 -- Keine Fundamentaldaten fuer Nicht-Kandidaten.** Wer wissen will,
  wie eine Aktie ausserhalb eines Signals fundamental dasteht, ruft
  `cli fundamental` auf. Eine spaetere Auswertung ueber den ganzen Bestand
  braucht einen eigenen Lauf.
- **L2 -- Redundanz in der Datenhaltung.** Ein Kandidat an fuenf Tagen
  hintereinander erzeugt fuenf identische Kennzahlensaetze. Bewusst in Kauf
  genommen (Entscheidung 5).
- **L3 -- Die Zwischenspeicherung bleibt offen.** ADR 0032 L6 ist durch
  Entscheidung 1 entschaerft, nicht beantwortet. Sollte der Umfang je auf die
  volle Watchliste wachsen, muss sie vorher entschieden werden.
- **L4 -- Der Kurs stammt aus einer 195-Minuten-Kerze, die Kennzahl aus einem
  Quartalsbericht.** Das Kurs-Gewinn-Verhaeltnis eines Kandidaten ist damit
  taggenau, sein Nenner bis zu drei Monate alt. Das ist die Natur der
  Kennzahl und kein Mangel der Umsetzung -- die Basis am Ergebnis sagt, auf
  welchen Zeitraum sich der Nenner bezieht.

## Nachtrag 2026-08-30: die Bewertung braucht eine zweite Schranke

Die unabhaengige Review hat eine Luecke gefunden, die erst durch diesen Zweig
entsteht -- vorher gab es keinen Kurs, also auch keine Bewertung im Lauf.

**Die Aktualitaetsschranke aus ADR 0034 misst berichtsintern.** Sie
vergleicht eine Rohgroesse mit dem juengsten Zeitraumwert **desselben**
Berichts. Ein Emittent, der seit Jahren nichts mehr einreicht, ist darin
vollkommen stimmig: Alle seine Zahlen enden 2016, keine liegt hinter einer
anderen zurueck.

Gegen einen heutigen Kurs gerechnet ergab das:

```
ALT  COMPLETED  33%
  MARKET_CAPITALIZATION  200.000.000,00  Stg bis 2026-07-01
  PRICE_EARNINGS_RATIO       769.230,77  GJ  bis 2016-12-31
```

Die Marktkapitalisierung von heute, geteilt durch den Gewinn von 2016, mit
Status ``COMPLETED``. Die vorhandene Pruefung in ``_bewertung`` faengt den
umgekehrten Fall -- eine Aktienzahl, die **aelter** ist als der Stichtag
(der Berkshire-Fehler aus ADR 0033) --, nicht diesen.

**Entscheidung 7: Der Kurs wird nur gegen Zahlen der letzten 455 Tage
gerechnet.** Ein Geschaeftsjahr plus die laengste regulaere 10-K-Frist der
SEC. Wer fristgerecht einreicht, unterschreitet das immer; spaetestens dann
liegt der naechste Abschluss vor.

Ist die Spanne ueberschritten, entstehen die vier kursabhaengigen Kennzahlen
nicht. Die uebrigen bleiben: Sie mischen nichts, tragen ihren Zeitraum an
sich und sind alt, aber nicht falsch.

## Nachtrag 2026-08-30: eine Aktienzahl je Gattung ist keine Aktienzahl

Aus derselben Review. ``_resolve_shares_outstanding`` waehlte bei gleichem
Stichtag **und** gleichem Einreichungsdatum nach der Reihenfolge im JSON --
also nach nichts. Das Deckblatt eines Emittenten mit mehreren
Aktiengattungen nennt je Gattung eine Zahl, und welche zum gehandelten
Papier gehoert, steht dort nicht.

Die Folge waere keine kleine Abweichung: Bei Berkshire Hathaway liegen die
Gattungen um den Faktor 1.500 auseinander, und die Marktkapitalisierung
traegt das unveraendert in alle vier Bewertungskennzahlen weiter.

**Entscheidung 8: Sind mehrere Aktienzahlen desselben Stands verschieden
gross, fehlt die Aktienzahl** -- und mit ihr die Bewertung. Fehlend statt
falsch (CLAUDE.md).

Gemessen am 2026-08-30 ueber alle 192 Symbole der Watchliste: **kein
einziger** Emittent faellt darunter (177 eindeutig, 15 ohne Angabe). Die
Schranke kostet heute nichts und schuetzt gegen den Tag, an dem ein
Mehrklassen-Papier in die Watchliste kommt.
