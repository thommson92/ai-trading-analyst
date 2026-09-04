# ADR 0058: Optionsvorschläge im Rückblick — modelliert, gekennzeichnet, gemessen

- Status: Angenommen
- Datum: 2026-09-04
- Baut auf: [ADR 0048](0048-optionsanalyse-im-tageslauf.md) (Optionsanalyse),
  [ADR 0057](0057-torbedingungen-und-episoden.md) (Episoden liefern die
  Einstiegspunkte), [ADR 0038](0038-backtest-im-tageslauf.md) (Backtest im
  Tageslauf), [ADR 0028](0028-historientiefe-gemessen.md) (das Muster: erst
  messen, dann behaupten)

## Kontext

Der History-Backtest misst heute ausschließlich die **Aktienseite**: Was der
Kurs nach einem Trigger tat. Das ist exakt — die Kerzen liegen im Bestand, der
Einstieg ist der Schluss der Trigger-Kerze, der Pfad danach ist gemessen.

Gehandelt wird aber nicht die Aktie, sondern ein **Cash Secured Put**. Zwei
Fragen bleiben damit unbeantwortet:

1. Wie wäre der vorgeschlagene Put-Verkauf an jedem historischen Trigger
   gelaufen?
2. Wäre im Einzelfall der Verkauf mit Rückkaufregel oder der Verkauf mit
   gekauftem Put als Absicherung besser gewesen — und woran macht man das fest?

### Der harte Kern: es gibt keine historischen Optionsdaten

Optionsnotierungen sind nicht rückwirkend abrufbar. IBKR liefert historische
Bars für Kontrakte, die **noch existieren**; ein Put mit Verfall im März 2023
existiert nicht mehr. Es gibt keinen Abruf, der die damalige Notierung
zurückholt.

Vorhanden sind:

| Größe | Quelle | Reicht zurück? |
|---|---|---|
| Kurspfad des Basiswerts | 195-Minuten-Kerzen im Bestand | ja, Tiefen-Backfill auf fünf Jahre (ADR 0028) |
| Verfallskalender | Kalenderregel | ja, als Regel — nicht als Abruf |
| Strike-Raster | Börsenkonvention | ja, als Regel |
| Prämie, Delta, implizite Volatilität | — | **nein**, erst ab dem 2026-09-01 aus dem Tageslauf |
| Zinssatz | — | nein |

Jede Prämie dieses Backtests ist folglich eine **Modellzahl**. Das verträgt
sich mit der Regel „keine erfundenen Werte" (`CLAUDE.md`) nur unter einer
Bedingung: Sie muss an jeder gespeicherten Zeile als solche erkennbar sein und
darf nirgends neben einer notierten Prämie stehen, ohne dass man beide
unterscheiden kann.

### Zwei Verzerrungen, die in entgegengesetzte Richtungen ziehen

Ein naives Modell — Black-Scholes mit einer einzigen, über Strikes und
Laufzeit konstanten Volatilität — verzerrt ausgerechnet den Vergleich, um den
es in Frage 2 geht:

| Vereinfachung | Wirkung | Bevorzugt |
|---|---|---|
| flache Volatilität über alle Strikes (kein Skew) | der weit aus dem Geld liegende Absicherungs-Put wird zu billig gerechnet — dort ist der Skew am steilsten | den **Spread** |
| konstante Volatilität über die Laufzeit | der Rückkauf nach einem Kursrutsch wird zu billig gerechnet — in Wirklichkeit steigt die Volatilität, wenn der Kurs fällt | den **CSP mit Stop** |

Ein solcher Vergleich wäre eine Aussage über die Annahmen, nicht über den
Markt. Beide Verzerrungen sind deshalb Gegenstand eigener Festlegungen.

### Was seit dem 1. September entsteht

Der Tageslauf notiert für jeden Kandidaten echte Optionsketten. Daraus lassen
sich die beiden fehlenden Größen **am eigenen Universum messen** statt aus der
Literatur zu übernehmen: das Verhältnis impliziter zu realisierter Volatilität
und die Steigung des Skew. Und es lässt sich prüfen, ob das Modell überhaupt
taugt — indem man für jede gespeicherte Notierung die Prämie allein aus den
damals verfügbaren Kerzen rechnet und mit dem tatsächlich gestellten
Mittelwert vergleicht.

Das ist dasselbe Vorgehen wie bei der Historientiefe (ADR 0027/0028): Der
Anspruch wird gemessen, bevor er erhoben wird.

## Entscheidung

Elf Festlegungen, alle vom Projektinhaber am 2026-09-04 entschieden.

### 1. Die abgerufenen Rohnotierungen werden gespeichert

Der Tageslauf fragt bis zu `options.max_strikes` (heute 12) Kontrakte je
Kandidat ab und speichert die höchstens drei Vorschläge. Die übrigen werden
nach der Auswertung verworfen — bei rund 36 Kandidaten etwa **400 echte
Notierungen je Handelstag**, die es nie wieder geben wird. Genau sie sind die
Kalibrierungsgrundlage aus Festlegung 2 und 3.

Ab sofort wird jede abgerufene Notierung gespeichert: Verfall, Strike, Geld,
Brief, Delta, implizite Volatilität, Open Interest, Volumen, dazu Zeitpunkt
und Aktienkurs. Das kostet **keine einzige zusätzliche Marktdatenanfrage** —
die Daten kommen ohnehin an — und rund 100.000 Zeilen im Jahr.

Diese Festlegung ist von allen anderen unabhängig und wird **zuerst**
ausgeliefert. Jeder Tag ohne sie ist ein verlorener Messtag.

### 2. Die Volatilität kommt aus der Historie, mit Aufschlag und als Band

Grundlage ist die **realisierte** Volatilität aus den eigenen Kerzen, gerechnet
über ein Fenster, das ausschließlich Kerzen **vor** der Entscheidungskerze
enthält (Look-ahead-Verbot, Doc 10 §6.6).

Verkauft wird aber zur **impliziten**, und die liegt bei Aktienoptionen
systematisch darüber. Auf die realisierte Volatilität wirkt deshalb ein
konfigurierter Aufschlag. Er ist zunächst gesetzt, nicht gemessen — und
deshalb gilt:

> Das Ergebnis wird grundsätzlich als **Band** über mehrere Aufschläge
> ausgewiesen, nie als eine Zahl. Kippt eine Aussage innerhalb des Bandes, ist
> sie nicht belastbar und wird als solche gekennzeichnet.

Sobald genügend Tage aus Festlegung 1 vorliegen, **ersetzt der gemessene
Aufschlag den gesetzten**. Der Konfigurationswert bleibt, seine Herkunft
ändert sich; die Modellversion steigt.

Kein VIX. Er wäre eine neue externe Datenquelle für eine Größe, die wir am
eigenen Universum genauer messen können.

### 3. Der Strukturvergleich läuft zuerst nur live

Der gesamte Kostenunterschied zwischen den beiden Strukturen steckt im Skew.
Ohne belastbare Skew-Messung wäre ein historischer Vergleich eine Aussage über
die Annahme. Deshalb gestuft:

- **Historisch** wird zunächst **nur der Cash Secured Put** gerechnet. Für ihn
  genügt eine Volatilität am gewählten Strike; es gibt keinen zweiten Strike,
  dessen relativer Preis die Aussage trägt.
- **Der Vergleich beider Strukturen läuft live**, auf echten Ketten, wo beide
  Prämien notiert sind und nichts modelliert werden muss.
- **Sobald die Skew-Messung aus Festlegung 1 trägt**, kommt der Spread auch in
  den historischen Lauf. Das ist eine eigene Auslieferung mit eigener
  Modellversion, keine stillschweigende Erweiterung.

### 4. Verfallskalender: nur Monatsverfälle

Rückwirkend gilt der **dritte Freitag** als einziger Verfallstermin. Das ist
die einzige Annahme, die über fünf Jahre für jeden optionsfähigen US-Titel
trägt; Wochenoptionen gab es weder durchgehend noch für jeden Titel, und
welcher Titel wann welche hatte, ist nicht belegbar.

Feiertagsverschiebungen bleiben unberücksichtigt — dieselbe Wochentagsnäherung
wie in [ADR 0030](0030-wochentagsnaeherung-bleibt.md), aus demselben Grund: Der
Handelskalender reicht nicht weit genug zurück, und die Näherung ist an jedem
Ergebnis vermerkt.

Die Kalenderannahme wird **am Ergebnis gespeichert**. Sie unterscheidet sich
vom Live-Betrieb, der Wochenoptionen sieht und regelmäßig nutzt; wer die
Kennzahlen liest, muss das wissen können.

### 5. Der Strike wird nach modelliertem Delta gewählt

Live entscheidet das Delta-Band (`min_delta` bis `max_delta`, heute 0,10 bis
0,40). Der Backtest wählt deshalb ebenfalls nach Delta — dem aus demselben
Modell, das auch die Prämie liefert, mit Ziel in der Mitte des Bandes. Eine
Auswahl nach reiner Moneyness bräuchte kein Modell, würde aber eine **andere
Strategie messen als die gehandelte**.

Der gewählte Strike wird auf ein konfiguriertes, realistisches Raster gerundet.
Das Raster ist eine Annahme wie der Kalender und wird ebenso am Ergebnis
vermerkt; ihre Wirkung ist gering, weil die Rundung das Delta nur wenig
verschiebt.

### 6. Die Verzinsung der Sicherheitsleistung bleibt draußen

Der Projektinhaber hat gefragt, ob diese Zinsen bei IBKR überhaupt anfallen —
sein Jahresreport weise keine aus.

**Die Frage deckt einen Denkfehler in der Vorlage auf.** Dort stand der Zins
als *Ertrag* auf die hinterlegte Sicherheit, nicht als Kosten. Bezahlt wird bei
einem Cash Secured Put nichts: Es wird nichts geliehen, also entstehen keine
Sollzinsen. Die Frage ist allein, ob das gebundene Geld etwas **einbringt** —
und ob IBKR Habenzinsen gutschreibt, hängt an Kontotyp, Guthabenhöhe und
Freibetrag, nicht an der Strategie.

Und genau darin liegt der eigentliche Grund für die Entscheidung:

> Zinsen auf Barbestand sind eine Eigenschaft des **Kontos**, nicht des
> Trades. Sie dem Put zuzurechnen hieße, der Strategie etwas gutzuschreiben,
> das das Konto ohnehin tut.

Ob der Verkauf „cash-secured" ist, ändert daran nichts Grundsätzliches: In
einem Margin-Konto verlangt ein Short Put nur einen Bruchteil des Strikes als
Sicherheit; die volle Deckung ist eine selbst auferlegte Disziplin, keine
Forderung des Brokers. Was sie kostet, ist **gebundenes Kapital** — und das
steht ohnehin als eigene Zahl am Ergebnis.

Es wird deshalb **kein Zinssatz modelliert**. Stattdessen werden zwei Größen
getrennt ausgewiesen, und keine ersetzt die andere:

- der **absolute** Ertrag je Kontrakt, und
- die **Rendite auf das gebundene Kapital**.

Die zweite macht den Unterschied zwischen den Strukturen vollständig sichtbar,
ohne dass eine Zinsannahme nötig wäre. Der Verzicht wird am Ergebnis vermerkt.

### 7. Simuliert werden zwei Varianten

| Variante | Regel |
|---|---|
| **Grundlinie** | halten bis Verfall |
| **Gemanagt** | Gewinnmitnahme bei **33 %** der Prämie; Rückkauf, wenn der Optionspreis das **Dreifache** der vereinnahmten Prämie erreicht |

Die Grundlinie ist kein Beiwerk: Ohne sie hätte die gemanagte Variante keinen
Bezugspunkt. Erst der Abstand zwischen beiden sagt, ob das Management etwas
beiträgt oder nur Transaktionskosten erzeugt.

**Ein chartbasierter Ausstieg** — Schluss unter dem EMA 20 oder unter der
Unterstützungszone — wird **nicht** simuliert. Er war vorgeschlagen und ist
verworfen worden. Das ist zugleich eine architektonische Vereinfachung: Der
Options-Replay braucht damit für den Ausstieg **keine Indikatoren und keine
Zonen**, sondern allein den Kurspfad und das Preismodell. Er hängt damit an
nichts aus `domain/technical`; die Einstiegspunkte kommen weiterhin aus dem
Screening-Replay.

**Was die gewählten Parameter verlangen.** Bei Gewinnmitnahme über `+0,33 ×
Prämie` und Rückkauf bei `−2,00 × Prämie` — das Dreifache zahlen, das Einfache
behalten — liegt die rechnerische Grenze bei einer Trefferquote von rund
**86 %**. Das ist als Orientierung zu lesen, nicht als Einwand: Die tatsächliche
Verteilung enthält auch Trades, die keine der beiden Marken erreichen, und
genau sie zu messen ist der Zweck dieses Backtests. Aber es ist die Zahl, auf
die beim Lesen der ersten Ergebnisse zu achten ist.

### 8. Ein Ausführungsabschlag je Seite und Transaktion

Live wird mit dem Mittelwert gerechnet (ADR 0048, Festlegung 6). Historisch ist
schon der Mittelwert modelliert; ohne Abschlag entstünde ein doppelt
optimistisches Ergebnis.

Der Abschlag ist konfiguriert und wirkt **je Seite und je Transaktion**. Das
ist der einzige Weg, auf dem sichtbar wird, dass ein Spread doppelt so viele
Geld-Brief-Spannen überquert wie ein einzelner Verkauf — und dass jede
Managementregel aus Festlegung 7 eine zusätzliche Transaktion kostet.
Ergebnisse werden **mit und ohne** Abschlag ausgewiesen.

### 9. Eigener Messlauf, eigene Tabelle, eigene Version

Die Simulation läuft **nicht** im Tageslauf, sondern als eigener Messlauf über
die Watchliste — wie die bestehenden. Sie ist eine Untersuchung, keine
tägliche Entscheidungsgrundlage; der Tageslauf liest allenfalls ihr Ergebnis
und behält sein Zeitbudget.

Die Ergebnisse landen in einer **eigenen Tabelle mit eigener Versionsnummer**,
nie in den Spalten der echten Optionsanalyse. Eine modellierte Prämie darf an
keiner Stelle neben einer notierten stehen, ohne dass man beide unterscheiden
kann. An jeder Zeile stehen die Modellversion, die Volatilitätsannahme samt
Aufschlag, die Kalender- und Rasterannahme sowie die Signalregel-Version des
zugrunde liegenden Triggers.

### 10. Woran die Strukturwahl live festgemacht wird

Die beiden Strukturen unterscheiden sich in genau drei Dingen: **was den
Verlust begrenzt** (eine Regel, die man ausführt, gegen einen Kontrakt, den man
besitzt), **was das kostet**, und **wieviel Kapital es bindet**. Die Kriterien
folgen daraus.

Als **Kern**, alle heute deterministisch rechenbar:

1. **Kurslückenrisiko des Titels** — Häufigkeit und Größe der Eröffnungslücken
   über die eigene Historie. Ein Titel, der regelmäßig mehrere Prozent tiefer
   eröffnet, macht jeden Rückkauf-Stop zur Illusion; dort ist der gekaufte Put
   die einzige Begrenzung, die hält.
2. **Rendite auf tatsächlich riskiertes Kapital** — die eine Zahl, die beide
   Strukturen vergleichbar macht.
3. **Anteil der Prämie, den die Absicherung kostet** — bei steilem Skew wird
   der Schutz teuer erkauft.
5. **Empfehlungsstufe und Score** — ist die Andienung erwünscht? Ein CSP auf
   einen Titel, den man ohnehin gerne besäße, hat im Andienungsfall keinen
   Verlust, sondern einen Einstieg zum Wunschkurs. Ein CSP auf einen Titel, den
   man nur wegen der Prämie geschrieben hat, hat einen echten. Das ist der
   Punkt, an dem dieses Projekt etwas beitragen kann, was ein reiner
   Optionsrechner nicht kann.

Als **Zusatz**, sobald der Absicherungs-Strike notiert wird (Festlegung 11):

4. **Liquidität des Absicherungs-Strikes** — ist die zweite Seite dünn, ist der
   Spread eine Rechnung und kein Handel.
6. **Abstand des Strikes zur Unterstützungszone** (`distance_to_support_pct`,
   existiert bereits) — eine Aussage über die **Lage des Strikes**, nicht über
   einen Ausstieg: Ein Strike über einer belastbaren Zone muss erst durch sie
   hindurch angedient werden, ein Strike darunter nicht. Die ursprüngliche
   Begründung — die Zone als chartbarer Stop-Auslöser — ist mit Festlegung 7
   entfallen; das Kriterium bleibt, weil es auch ohne Ausstiegsregel etwas
   Wahres über den gewählten Kontrakt sagt.

**Später:** das Volatilitätsregime (sobald die IV-Historie aus Festlegung 1
trägt) und die gemessene Backtest-Evidenz je Signalkombination.

Kurzform der Regel, die daraus folgt: **Der Spread ist die richtige Struktur,
wenn der Stop nicht verlässlich greifen kann oder die Aktie nicht gewollt ist.
Der Cash Secured Put ist sie, wenn beides andersherum liegt und die
Absicherung teuer wäre.**

### 11. Der Absicherungs-Strike wird gezielt nachgefragt

Heute werden Strikes zwischen 80 % und 99 % des Kurses notiert, höchstens
zwölf. Der Absicherungs-Strike liegt je nach Volatilität darunter, und das
Kontingent ist bereits ausgeschöpft.

Statt das Band zu verbreitern und für **jeden** Kandidaten mehr Kontrakte
abzufragen, wird der Absicherungs-Strike in einem **zweiten, gezielten Abruf**
notiert — erst, nachdem der Verkaufs-Strike feststeht. Das ist sparsamer und
deckt jeden Fall ab. Nichts zu ändern schiede aus: Dann entstünde eine
Empfehlung, die mal da ist und mal nicht, ohne dass der Grund im Ergebnis
steht.

## Was bewusst nicht gebaut wird

- **Amerikanische Optionsbewertung.** Der Aufschlag gegenüber der europäischen
  ist bei aus dem Geld liegenden Puts mit 21 bis 60 Tagen klein und
  **einseitig** — er unterschätzt die Prämie leicht. Ein dokumentierter
  Vereinfachungsfehler mit bekannter Richtung ist keinen Binomialbaum wert.
- **Ein zugekaufter historischer Optionsdatensatz.** Löste das Problem sauber
  und kostet Geld. Die Entscheidung ist umkehrbar; sie ändert dieses ADR
  vollständig, sobald sie anders ausfällt.
- **Ein Sprachmodell für die Strukturwahl.** Verstößt gegen die zentrale Regel
  (`CLAUDE.md`): Technische Signale werden nicht durch KI verändert. Das
  Ergebnis erläutern darf es.
- **Dividenden im Modell.** Sie erhöhen den Wert eines Puts; bei den Renditen
  der Watchliste liegt der Effekt unter der Modellunsicherheit. Bekannte
  Vereinfachung, vermerkt statt halbherzig eingebaut.

## Konsequenzen

**Die Auslieferung ist gestuft, und die erste Stufe entscheidet über die
übrigen.** Festlegung 1 kommt zuerst und allein. Danach das Bewertungsmodell
samt Messwerkzeug, das die modellierte Prämie gegen jede gespeicherte echte
Notierung hält. Liegt der Fehler dort bei vierzig Prozent, ist der historische
Lauf Dekoration — und man weiß es, bevor man ihn baut. Erst danach der
CSP-Backtest, und erst nach tragfähiger Skew-Messung der Spread.

**Das Bewertungsmodell ist eine reine Domain-Funktion ohne neue Abhängigkeit.**
Die Normalverteilung kommt aus `math.erf`; scipy wird nicht eingeführt
(`CLAUDE.md`: keine unnötigen Abhängigkeiten). Live-Analyse und Backtest rufen
**dieselben** Funktionen — das Muster aus
[`strategies.py`](../../backend/src/ai_trading_analyst/domain/options/strategies.py),
dessen Modul-Docstring den Grund nennt: Zwei Formeln ergäben Schwellen, die zu
den gemessenen Werten nicht passen.

**Es entsteht keine vierte gerichtete Kopplung.** Das Preismodell ist eine
Funktionsbibliothek, kein Analysemodul — wie `qualifies()`, das Live-Prüfung
und Replay gleichermaßen benutzen. Die drei Kopplungen aus `CLAUDE.md` bleiben,
wie sie sind.

**Die Kennzahlen sind Modellzahlen und heißen auch so.** Sie stehen in einer
eigenen Tabelle, tragen ihre Annahmen mit und erscheinen im Bericht nie ohne
den Hinweis, dass keine dieser Prämien je notiert wurde. Wo eine Aussage
innerhalb des Volatilitätsbandes kippt, wird sie als nicht belastbar
gekennzeichnet statt als Zahl ausgegeben.

**Der Live-Betrieb wird geringfügig teurer.** Je Kandidat kommt ein zweiter,
gezielter Marktdatenabruf hinzu (Festlegung 11) und je Kandidat werden statt
höchstens drei nun alle abgerufenen Notierungen gespeichert (Festlegung 1).
Beides ist gemessen klein; die zusätzliche Anfrage fällt nur für Kandidaten an,
für die überhaupt ein Verkaufs-Strike gefunden wurde.

**Risiko: die Kalibrierung ist zunächst dünn.** Am 2026-09-04 liegen wenige
Tage echter Ketten vor, und die gespeicherten drei Vorschläge je Kandidat
liegen sämtlich im Delta-Band 0,10 bis 0,40 — für eine Skew-Steigung zu wenig
und zu einseitig. Genau deshalb steht Festlegung 1 am Anfang und Festlegung 3
auf „zuerst nur live".
