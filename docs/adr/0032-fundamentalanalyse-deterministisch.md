# ADR 0032: Deterministische Fundamentalanalyse — Kennzahlen aus XBRL, Kurs als optionale Eingabe

- Status: Angenommen
- Datum: 2026-08-24

## Kontext

Der Fundamental Agent ist der letzte unbegonnene Posten aus Sprint 4 neben
dem Report Generator. Zwei Dinge sind bereits entschieden und werden hier
**nicht** neu verhandelt:

- **Die Quelle.** [ADR 0022](0022-research-agent-quellen.md) legt fest:
  `data.sec.gov/api/xbrl/companyfacts/CIK…json`, direkt und deterministisch
  gelesen, **kein Sprachmodell im Beschaffungspfad**.
- **Der Zuschnitt.** Wie beim Technical Agent
  ([ADR 0025](0025-deterministische-chartauswertung-und-zonen.md) /
  [ADR 0026](0026-technical-agent-ki-einordnung.md)) entstehen zwei getrennte
  Hälften: erst die gerechneten Kennzahlen, dann — in einem eigenen Schritt
  und einem eigenen ADR — die KI-Einordnung. Dieses ADR betrifft
  ausschließlich die deterministische Hälfte.

Offen ist, was zwischen „`companyfacts` lesen" und „Kennzahl" liegt. Doc 10,
Paragraph 6.9 nennt fünfzehn Analysebereiche und verlangt an jeder Kennzahl
Bezugszeitraum, Einheit, Währung, Quelle und Abrufzeitpunkt. Wie aus 500
XBRL-Tags eine belastbare Umsatzreihe wird, steht dort nicht — und genau dort
liegt die Schwierigkeit.

## Gemessen, nicht angenommen

Muster [ADR 0027](0027-historientiefe-messen-vor-anspruch.md): erst messen,
dann entscheiden. Alle Zahlen unten stammen aus echten Abrufen gegen
`data.sec.gov` am 2026-08-24.

**Die Zuordnung Symbol → CIK ist unproblematisch.**
`www.sec.gov/files/company_tickers.json` enthält 10.403 Einträge und deckt
die geprüften Symbole ab, einschließlich Sonderfällen wie `BRK-B`. Eine
Datei, ein Abruf, kein Suchdienst.

**Der Datensatz ist groß, aber handhabbar.** `companyfacts` für Apple ist
3,8 MB und führt 503 Tags in der `us-gaap`-Taxonomie.

### Befund 1: Es gibt kein Tag, das für alle Emittenten den Umsatz trägt

| Symbol | Tags gesamt | Umsatz-Tags mit 10-K-Daten |
|---|---|---|
| AAPL | 503 | `Revenues` (2016–2018), `RevenueFromContractWithCustomerExcludingAssessedTax` (2017–2026) |
| NVDA | 626 | `Revenues` (2008–2026), `RevenueFromContractWithCustomer…` (2017–2022) |
| HON | 632 | `Revenues` (2007–2011), `RevenueFromContractWithCustomer…` (2016–2025), `SalesRevenueNet` (2010–2017), `SalesRevenueGoodsNet` (2007–2017) |
| PEP | 612 | `Revenues` (2016–2025), `SalesRevenueNet` (2007–2017) |
| NFLX | 490 | `Revenues` (2007–2025) |
| BRK-B | 437 | `Revenues`, `RevenueFromContractWithCustomer…`, `SalesRevenueNet` |

Apple hat `Revenues` nach 2018 aufgegeben, NVIDIA führt es bis heute. Die
Zeiträume überlappen sich, und zwar unterschiedlich je Emittent.

### Befund 2 — der entscheidende: Überlappende Tags widersprechen sich

Für Honeywell, Geschäftsjahr 2010, denselben Zeitraum:

| Tag | Wert |
|---|---|
| `SalesRevenueNet` | 32,350 Mrd USD |
| `SalesRevenueGoodsNet` | **25,242 Mrd USD** |

**22 % Unterschied.** Der Grund ist fachlich und keine Datenpanne:
`SalesRevenueGoodsNet` ist der Warenumsatz *ohne* Dienstleistungen. Dasselbe
Bild in allen Jahren 2010–2017.

Eine Auflösung nach dem Muster „nimm das erste Tag, das Daten hat" liefert
hier je nach Reihenfolge eine um ein Fünftel falsche Umsatzreihe — und damit
falsche Wachstumsraten, falsche Margen und eine falsche Bewertung. Der Fehler
wäre **still**: Beide Zahlen sind plausibel, keine Prüfung schlägt an.

Wo dagegen `Revenues` und `RevenueFromContractWithCustomerExcludingAssessedTax`
denselben Zeitraum abdecken (NVIDIA, acht Zeiträume), stimmen sie **auf den
Cent überein**. Die Mehrdeutigkeit ist also nicht allgemein, sondern hängt am
einzelnen Tag.

### Befund 3: Derselbe Tag trägt für denselben Zeitraum verschiedene Werte

In Apples `companyfacts` gibt es **426 Zeiträume**, für die ein und dasselbe
Tag über verschiedene Einreichungen hinweg widersprüchliche Werte führt.
Beispiel `AccountsPayableCurrent` zum 2017-09-30:

```
eingereicht 2017-11-03   49.049 Mio USD   10-K
eingereicht 2018-11-05   44.242 Mio USD   10-K   <- Vergleichszahl im Folgejahr
```

Ursachen sind Neuausweise, Umgliederungen und Berichtigungen; unter den
Einreichungen finden sich auch `10-K/A`-Änderungsberichte. Jeder Zeitraum
erscheint zudem regelmäßig doppelt, weil das Folgejahr ihn als Vergleichszahl
erneut ausweist.

**Ohne eine ausdrückliche Regel hängt das Ergebnis von der Reihenfolge im
JSON ab.** Das ist keine Grundlage für eine Kennzahl.

## Entscheidung

### 1. Was jetzt deterministisch gerechnet wird — und was nicht

Doc 10 nennt fünfzehn Bereiche. Sie zerfallen in drei Gruppen:

| Gruppe | Bereiche | Wo |
|---|---|---|
| **Aus XBRL rechenbar** | Umsatzwachstum, Gewinnwachstum, Free Cashflow, Margen, Kapitalrenditen, Verschuldung, Liquidität, Verwässerung | **dieses Modul** |
| **Braucht zusätzlich einen Kurs** | Bewertung im historischen Vergleich | dieses Modul, siehe (4) |
| **Nicht aus XBRL ableitbar** | Bewertung gegenüber Wettbewerbern, Marktposition, Wettbewerbsvorteile, Managementqualität, langfristige Chancen, langfristige Risiken | **später**, siehe unten |

Die sechs Bereiche der dritten Gruppe sind **keine Rechenaufgabe**. Vier davon
sind Urteile und gehören in die KI-Hälfte, die ausschließlich einordnen darf,
was hier gerechnet wurde. Der Vergleich mit Wettbewerbern braucht eine
Vergleichsgruppe, die niemand festgelegt hat — er bleibt offen und bekommt,
wenn er kommt, ein eigenes ADR.

**Sie werden nicht stillschweigend ausgelassen.** Wie überall im Projekt gilt:
Was fehlt, bleibt als fehlend gekennzeichnet und senkt die Datenabdeckung.

### 2. Tag-Auflösung: eine benannte, geordnete Liste je Kennzahl

Je Kennzahl steht im Code eine **ausdrückliche Reihenfolge** von Tags. Für
einen Zeitraum gewinnt das erste Tag der Liste, das ihn abdeckt.

Zwei Regeln, die aus Befund 2 folgen:

- **In eine Liste gehören nur Tags, die dasselbe bedeuten.**
  `SalesRevenueGoodsNet` steht **nicht** in der Umsatzliste — es ist der
  Warenumsatz ohne Dienstleistungen und damit eine andere Größe, nicht eine
  andere Schreibweise derselben.
- **Weicht ein nachrangiges Tag für denselben Zeitraum vom gewählten ab,
  wird das vermerkt, nicht verschwiegen.** Die Abweichung ist ein Hinweis
  darauf, dass die Liste für diesen Emittenten nicht passt — genau der Fall,
  den Befund 2 zeigt und den niemand bemerkt hätte.

### 3. Zeitraum-Auflösung: die zuletzt eingereichte Angabe gewinnt

Fakten werden nach `(start, end)` zusammengefasst; innerhalb einer Gruppe
gewinnt der **höchste `filed`-Wert**. Damit steht der berichtigte Stand in der
Kennzahl, nicht der ursprünglich gemeldete.

Das ist eine Festlegung mit einer Kehrseite, und sie wird hier benannt: Eine
Kennzahl beschreibt danach die Vergangenheit **so, wie das Unternehmen sie
heute sieht** — nicht so, wie sie zum damaligen Zeitpunkt bekannt war. Für
eine langfristige Qualitätsbeurteilung ist das die richtige Wahl. Für ein
Backtesting wäre es Vorauswissen; deshalb speichert jede Kennzahl den
`accn`-Bezeichner und das Einreichungsdatum mit, aus dem sie stammt.

Ausgewertet werden Jahresabschlüsse aus `10-K` und `10-K/A`. Quartalszahlen
bleiben vorerst außen vor: Für Wachstum über Jahre tragen sie nichts bei und
brächten die Saisonalitätsfrage mit, die eigene Regeln verlangte.

### 4. Der Kurs ist eine optionale, nicht blockierende Eingabe

Bewertungskennzahlen brauchen einen Kurs; EDGAR liefert keinen. Der Kurs wird
**hineingereicht**, nicht beschafft:

1. Verwendet wird der Schlusskurs der letzten **abgeschlossenen** Kerze, die
   ohnehin schon vorliegt — keine zusätzliche Anfrage, keine laufende Kerze
   (CLAUDE.md).
2. Die Abhängigkeit ist **nicht blockierend**. Fehlt der Kurs, laufen alle
   übrigen Kennzahlen vollständig; die bewertungsabhängigen Felder werden als
   nicht verfügbar gekennzeichnet, und die Datenabdeckung sinkt entsprechend.
   Kein Ersatzwert, keine stille Auslassung.
3. Das Fundamentalmodul **beschafft keinen Kurs selbst** und leitet keinen ab.

Das ist wörtlich das Muster, das CLAUDE.md heute für Optionsanalyse und
Support-/Resistance-Zonen festlegt. Es ist damit die **zweite** gerichtete
Kopplung im System — und deshalb steht sie hier, statt sich einzuschleichen.
CLAUDE.md wird entsprechend ergänzt.

Die Aktienzahl für die Marktkapitalisierung kommt aus
`dei:EntityCommonStockSharesOutstanding`, dem Deckblattwert der jüngsten
Einreichung.

### 5. Jede Kennzahl trägt ihre Herkunft

Doc 10, Paragraph 6.9 verlangt Bezugszeitraum, Einheit, Währung, Quelle und
Abrufzeitpunkt. Das wird kein Beiwerk, sondern Teil des Wertobjekts: Eine
Kennzahl ohne diese fünf Angaben lässt sich nicht bilden. Die Quelle ist die
Einreichung selbst (`accn`), aus der sich die EDGAR-Adresse bilden lässt.

### 6. Statusmodell und Version

`FundamentalStatus` nach dem Muster von `ResearchStatus` und
`TechnicalStatus`: `COMPLETED`, `INSUFFICIENT_DATA`, `UNAVAILABLE`. Anders als
bei der Chartauswertung gibt es hier ein `UNAVAILABLE`, weil ein externer
Anbieter beteiligt ist, der ausfallen kann — Fehlerisolation je Aktie wie bei
`EarningsProviderError`.

`FUNDAMENTAL_ANALYSIS_VERSION` wird an jedem Ergebnis gespeichert. Ändert sich
eine Tag-Liste oder eine Auflösungsregel, steigt die Nummer: Eine
Umsatzwachstumsrate nach geänderter Tag-Liste ist eine andere Zahl, und man
muss einem gespeicherten Ergebnis ansehen können, nach welcher Regel sie
entstanden ist.

### 7. Umgang mit der SEC

`User-Agent` mit Kontaktadresse bei jeder Anfrage und höchstens 10 Anfragen je
Sekunde — beides verlangt die SEC ausdrücklich. Die Kontaktadresse ist
konfigurierbar und kein Geheimnis, gehört also in die Konfiguration und nicht
in eine Umgebungsvariable.

## Einschränkungen

| # | Einschränkung |
|---|---|
| **L1** | **Die Tag-Listen sind von Hand gepflegt und decken nicht jeden Emittenten ab.** Gemessen wurde an sechs Symbolen. Ein Emittent, der ein Tag außerhalb der Liste verwendet, liefert für die betroffene Kennzahl **nichts** — nicht etwas Falsches. Die Fehlerrichtung ist damit die ungefährliche, aber die Abdeckung über die volle Watchlist ist **nicht gemessen** und gehört nach der Implementierung gemessen. Dasselbe bekannte Problem wie bei den Domain- und Preislisten (Risiko R8 der Audit-Nachverfolgung). |
| **L2** | **Der Kennzahlenstand ist nur so aktuell wie die letzte Einreichung.** Zwischen Geschäftsjahresende und 10-K liegen Wochen. Die Aktienzahl vom Deckblatt war bei der Messung rund sechs Wochen alt — nach einem größeren Rückkaufprogramm ist die daraus gerechnete Marktkapitalisierung entsprechend zu hoch. |
| **L3** | **Nur US-GAAP.** Ausländische Emittenten, die per `20-F` in IFRS berichten, tragen andere Tags. Die Watchlist besteht aus US-notierten Titeln; ein IFRS-Bericht liefert nach L1 fehlende Kennzahlen statt falscher. |
| **L4** | **Die Kennzahlen beschreiben die Vergangenheit im heutigen Ausweis.** Folge der Entscheidung (3). Für die Beurteilung richtig, für ein Backtesting Vorauswissen — deshalb ist das Einreichungsdatum mitgespeichert, aber ein historisch korrekter Rückblick ist damit noch nicht gebaut. |
| **L5** | **Die Vergleichsgruppe fehlt.** „Bewertung gegenüber Wettbewerbern" aus Doc 10 bleibt unabgedeckt und wird als fehlend ausgewiesen. |
| **L6** | **`companyfacts` ist groß.** 3,8 MB je Aktie, bei rund 95 Titeln der Watchlist entsprechend viel Übertragung je Lauf. Ob das eine Zwischenspeicherung verlangt, entscheidet die Messung nach der Implementierung — nicht eine Vermutung vorab. |

## Konsequenzen

- Ein neues Domain-Modul `domain/fundamentals` — reine Berechnung, ohne
  Infrastruktur, wie `domain/technical`. Der Port `FundamentalDataProvider`
  kommt zu `domain/analysis/ports.py`, die EDGAR-Anbindung nach
  `infrastructure/edgar`.
- **CLAUDE.md wird ergänzt**: Der Abschnitt „Analysemodule sind entkoppelt"
  nennt künftig zwei gerichtete Kopplungen statt einer, mit denselben drei
  Bedingungen.
- `cli fundamental` zum Gegenprüfen an echten Filings, nach dem Muster von
  `cli technical`. Ohne diesen Schritt geht die Hälfte nicht in einen PR — die
  Verifikation an echten Kursen hat beim Technical Agent Abweichungen
  gefunden, die kein Test gezeigt hätte.
- Die KI-Einordnung folgt in einem eigenen Zweig mit eigenem ADR und bekommt
  die hier gerechneten Werte ausschließlich zur Einordnung.
- Nach der Implementierung ist die **Tag-Abdeckung über die volle Watchlist zu
  messen** (L1). Ergebnis gehört in einen Nachtrag zu diesem ADR.

## Alternativen, die nicht gewählt wurden

**Einen fertigen Fundamentaldaten-Anbieter kaufen.** Er löste L1 und L3 sofort
und brächte die Vergleichsgruppe mit. Er kostet aber laufend Geld, und ADR 0022
hat sich für EDGAR entschieden, weil dort die Nachweiskette bis zur
Originaleinreichung reicht — die ein aufbereiteter Anbieter gerade kappt.
Ändert sich die Bewertung, ist das ein neues ADR.

**Die `frames`-API von EDGAR statt `companyfacts`.** Sie liefert einen
Zeitraum über alle Unternehmen und löst das Doppelungsproblem aus Befund 3
scheinbar von selbst. Sie zwingt aber zu einem Abruf je Kennzahl **und**
Zeitraum, während `companyfacts` alles zu einer Aktie in einem Abruf liefert —
und sie trifft die Tag-Auswahl selbst, ohne offenzulegen, welche. Genau die
Entscheidung, die Befund 2 als die kritische ausweist, wäre damit
unsichtbar delegiert.

**Ein Sprachmodell die Kennzahlen aus den Filings lesen lassen.** Durch
ADR 0022 ausgeschlossen und durch die zentrale Regel aus CLAUDE.md verboten.
Befund 2 zeigt zusätzlich, warum: Die Wahl zwischen 32,350 und 25,242 Mrd ist
eine Regel, die nachvollziehbar festliegen muss — kein Urteil, das je Aufruf
neu ausfallen darf.
