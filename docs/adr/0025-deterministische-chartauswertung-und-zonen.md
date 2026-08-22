# ADR 0025: Deterministische Chartauswertung — Swing-Pivots mit Clustering für Unterstützungs- und Widerstandszonen

- Status: Angenommen
- Datum: 2026-08-22

## Kontext

Doc 10, Paragraph 6.8 beschreibt das Technical Analysis Module als zwei
getrennt zu speichernde Hälften: eine deterministische Berechnung und eine
qualitative Interpretation durch ein Sprachmodell. Bis hierher existierte
**keine** der beiden. Der Sprint-4-Agent kann nicht gebaut werden, bevor
feststeht, was er als Eingabe bekommt.

Zwei weitere Stellen hängen an derselben Berechnung:

- **Die Optionsanalyse in Sprint 5.** `CLAUDE.md` erlaubt ihr genau eine
  gerichtete Kopplung: Sie darf die *deterministisch ermittelten* Zonen der
  technischen Analyse als optionale Eingabe verwenden und leitet
  ausdrücklich **keine eigenen** Zonen ab, insbesondere nicht aus
  KI-Freitext. Ohne deterministische Zonen gibt es diese Eingabe nicht.
- **Das Scoring in Sprint 5**, das den Abstand zur nächsten Unterstützung
  verwendet (Doc 10, Paragraph 6.11).

Doc 10, Paragraph 6.8 verlangt für die Zonen zweierlei: Die Berechnung muss
**nachvollziehbar** sein, und jede ausgegebene Zone muss sieben Angaben
tragen — unterer Wert, oberer Wert, Art, Stärke, Anzahl relevanter
Berührungen, letzte Bestätigung, Abstand zum aktuellen Kurs.

Das *Verfahren* lässt Doc 10 dagegen offen. Es nennt sechs mögliche
Eingangsgrößen: Swing Highs und Swing Lows, lokale Pivot-Punkte, mehrfach
getestete Preiszonen, Volumenprofile, gleitende Durchschnitte, Gap-Zonen und
psychologische Preisniveaus. Welche davon tatsächlich verwendet werden, ist
zu entscheiden.

## Entscheidung

### 1. Eigenes Domain-Modul, getrennt vom Signalkern

Die Auswertung liegt in `domain/technical`, nicht in `domain/screening`. In
`domain/screening` liegen die unter [Gate G1](0010-gate-g1-freigegeben.md)
freigegebenen Signalformeln, die über Kandidat oder Nichtkandidat
entscheiden. Aus `domain/technical` fließt **nichts** in eine
Signalentscheidung zurück; es entsteht nur die Beschreibung der Lage, in der
eine bereits gefallene Entscheidung zustande kam.

Daraus folgt auch: Diese Parameter sind **nicht Teil von Gate G1**. Gate G1
umfasst RSI-Länge und -Berechnungsmethode, Länge und Typ des
RSI-Moving-Average, die Definition des EMA20-Kursdurchbruchs und die
Schlussbedingung beim EMA5/EMA20-Crossover. Keiner der hier festgelegten
Werte berührt eine dieser vier Größen.

### 2. Zonen aus Swing-Pivots mit Clustering

Von den sechs in Doc 10 genannten Eingangsgrößen werden **Swing Highs/Lows
und mehrfach getestete Preiszonen** verwendet — als *ein* Verfahren in drei
einzeln nachprüfbaren Schritten:

1. **Swing-Punkte.** Eine Kerze ist ein Swing-Hoch, wenn ihr Hoch von
   `pivot_reach` Kerzen auf beiden Seiten nicht übertroffen wird; analog für
   Swing-Tiefs.
2. **Bündelung.** Swing-Punkte werden nach Preisnähe zu Zonen
   zusammengefasst.
3. **Berührungszählung.** Gezählt wird, wie oft der Kurs die entstandene
   Zone im Fenster getestet hat.

Volumenprofile, Gap-Zonen, gleitende Durchschnitte und psychologische Niveaus
bleiben **bewusst außen vor**. Jede weitere Eingangsgröße wäre ein zweites
Verfahren mit eigener Stärke-Definition, eigener Berührungslogik und eigenen
Parametern. Sie sind ohne reale Läufe nicht zu kalibrieren, und ihr Beitrag
ließe sich im fertigen Bericht nicht mehr von dem des Pivot-Verfahrens
trennen. Die Erweiterung bleibt möglich; sie soll aber erst erfolgen, wenn
das erste Verfahren an echten Charts beurteilt wurde.

### 3. Fünf Festlegungen im Verfahren, die nicht offensichtlich sind

**Hoch- und Tiefpunkte werden gemeinsam gebündelt, nicht getrennt.** Eine
Preisregion, die erst als Widerstand gedient hat und nach dem Durchbruch als
Unterstützung trägt, ist dieselbe Region. Getrennte Bündelung zerlegte sie in
zwei halb belegte Zonen und verschlechterte gerade den Fall, der am
aussagekräftigsten ist.

**Die jüngsten `pivot_reach` Kerzen bilden keinen Swing-Punkt.** Ob das
gestrige Hoch ein Wendepunkt war, entscheidet sich erst, wenn der Kurs sich
davon entfernt hat. Ein Verfahren, das den letzten Balken schon als Hochpunkt
führt, meldet auf jedem neuen Hoch eine neue Widerstandszone — genau da, wo
der Kurs gerade steht.

**Bei einem Plateau gewinnt der älteste Punkt.** Nach links wird echt
größer verlangt, nach rechts größer oder gleich. Ohne diese Unterscheidung
ergäbe jedes Plateau so viele Wendepunkte, wie es Kerzen breit ist, und ließe
die Zone allein dadurch stärker erscheinen.

**Zusammenhängende Aufenthalte in der Zone zählen als eine Berührung.** Sonst
hinge die Stärke einer Zone daran, wie lange der Kurs in ihr feststeckte,
statt daran, wie oft er an ihr abgeprallt ist.

**Die Zonengrenzen sind das Toleranzband um den Bündelmittelwert**, nicht die
Spanne der Punkte selbst. Ein Bündel aus einem einzigen Punkt hätte sonst die
Breite null, und die Zahl seiner Berührungen wäre nicht mit der einer
breiteren Zone vergleichbar — die Stärke hinge dann an der Bandbreite statt
am Verhalten des Kurses. Enthielte das Band ausnahmsweise einen eigenen
Punkt nicht, wird es geweitet: Eine Zone, die einen ihrer eigenen Punkte
ausschließt, wäre nicht erklärbar.

### 4. Stärke als Stufe, nicht als Kommazahl

`ZoneStrength` ist ordinal (`WEAK`/`MODERATE`/`STRONG`) und wird allein aus
der Zahl der Berührungen abgeleitet. Eine Formel mit gewichteten Summanden
aus Berührungen, Alter und Nähe sähe präziser aus, ohne es zu sein — die
Gewichte wären frei gewählt und würden als gerechnete Größe gelesen. Die
Rohgrößen (`touch_count`, `last_confirmed_at`, `pivot_count`) stehen an jeder
Zone und lassen sich im Scoring anders verrechnen, ohne dass hier ein
Zahlenwert vorgibt, wie.

### 5. Art der Zone ist relativ zum aktuellen Kurs

`SUPPORT`, `RESISTANCE` oder `PRICE_INSIDE` — keine dauerhafte Eigenschaft
der Preisregion. `PRICE_INSIDE` ist ein eigener Wert, weil die willkürliche
Zuordnung zu einer der beiden Seiten genau in dem Moment falsch wäre, in dem
sie am meisten zählt.

### 6. Trend nur bei Übereinstimmung zweier Hinweise

`TrendDirection` folgt der Steigung des EMA20 über `trend_lookback` Kerzen
**und** der Lage des EMA5 zum EMA20. Widersprechen sie sich — der EMA20
steigt, der EMA5 ist aber schon darunter gefallen —, ist das Ergebnis
`SIDEWAYS` und nicht die Richtung des stärkeren Hinweises: In dieser Lage ist
die Richtung tatsächlich offen.

Fehlen die EMA-Werte, bleibt `trend` **`None`** und wird nicht zu `SIDEWAYS`.
„Kein erkennbarer Trend" ist ein Befund, „nicht berechenbar" ist keiner.

### 7. Volatilität über die Average True Range

Doc 10 führt die ATR als „sofern verwendet". Sie wird verwendet, mit Wilders
Glättung — derselben Funktion, die schon dem RSI zugrunde liegt. Zwei
Glättungen mit minimal unterschiedlichem Startverhalten wären im Bericht
nicht auseinanderzuhalten. Zusätzlich zur absoluten ATR wird `atr_pct`
geführt; erst das macht die Volatilität zwischen Aktien unterschiedlicher
Preisklassen vergleichbar.

### 8. Läuft für jeden Kandidaten, unabhängig von allen anderen Modulen

Die Auswertung läuft **vor** dem Earnings-Filter und unabhängig von dessen
Ergebnis. Sie rechnet allein auf der ohnehin geholten Kerzenserie; sie hinter
den Filter zu hängen machte sie ohne Not von einer externen Quelle abhängig,
die ausfallen kann. Das setzt die Regel aus `CLAUDE.md` um: Fällt Research
aus, bleiben technische Analyse und Backtesting vollständig.

Reicht die Historie nicht für das längste benötigte Fenster, ist das Ergebnis
`INSUFFICIENT_DATA` — nicht eine auf einem kürzeren Fenster gerechnete
Auswertung, der man den Unterschied später nicht ansieht.

### 9. Voreingestellte Parameter

| Parameter | Wert | Überlegung |
|---|---|---|
| `pivot_reach` | 3 | Auf der 195-Minuten-Kerze rund anderthalb Handelstage je Seite. |
| `zone_tolerance_pct` | 0,015 | Halbe Zonenbreite; rund eine halbe bis ganze Tagesspanne. |
| `min_touches` | 2 | Eine einmal berührte Preisregion ist keine Zone. |
| `moderate_touch_count` / `strong_touch_count` | 3 / 5 | Stufen der Stärke. |
| `max_zones_per_side` | 3 | Ohne Grenze meldet eine lange Historie zwei Dutzend Zonen, von denen die entfernten für die Einstiegsfrage nichts beitragen. |
| `history_candles` | 250 | Bei zwei Kerzen je Handelstag rund ein halbes Jahr — der Horizont eines Swing-Trades. |
| `atr_length` | 14 | Übliche Länge. |
| `trend_lookback` / `trend_flat_pct` | 10 / 0,005 | Fenster und Schwelle der EMA20-Steigung. |
| `extremes_lookback` | 40 | Jüngste Hoch-/Tiefpunkte über rund vier Wochen. |

**Diese Werte sind Konventionen, keine gemessenen Optima.** Sie stehen
vollständig in `config/default.yaml` und sind ohne Codeänderung nachziehbar.
Das Kommando `cli technical --symbols ...` gibt die Auswertung samt Zonen
aus, damit sie am echten Chart gegengeprüft werden kann.

`zone_tolerance_pct` und `trend_flat_pct` sind **Bruchteile, keine
Prozentwerte** — 0,015 sind 1,5 %. Beide werden gegen eine obere Grenze von 1
geprüft. Das ist nicht kosmetisch: Ab 1 wird die untere Zonenkante negativ,
alle Swing-Punkte fallen in ein einziges Bündel, und die Zonenliste bleibt
leer — der Zahlendreher ergäbe also kein Fehlerbild, sondern eine Aktie, die
aussieht, als habe sie keine mehrfach getesteten Preisregionen. Bei
`trend_flat_pct` wäre die Folge ein dauerhafter Seitwärtstrend.

### 10. Die Parameter stehen an jedem Ergebnis

`TECHNICAL_ANALYSIS_VERSION` allein genügt nicht. Die Parameter sind
konfigurierbar, und dieses ADR fordert ausdrücklich dazu auf, sie an echten
Charts nachzuziehen — zwei Ergebnisse trügen dann dieselbe `technical-v1` und
wären doch nach verschiedenen Maßstäben gerechnet. Der Unterschied ließe sich
später nicht mehr von einer Marktveränderung unterscheiden.

Jeder `TechnicalSnapshot` führt deshalb die verwendeten Parameter mit und
speichert sie als JSONB an der Zeile — auch bei `INSUFFICIENT_DATA`, weil
erst das verlangte Fenster erklärt, warum die Historie zu kurz war.

Gespeichert wird eine flache Abbildung und nicht die typisierte
Parameterklasse: Abgeschlossene Analysen werden nicht überschrieben
(`CLAUDE.md`), und ein künftig umbenannter oder entfallener Parameter darf
ein altes Ergebnis nicht unlesbar machen.

## Konsequenzen

**Positiv**

- Der Technical Agent (Sprint 4) hat eine feste, versionierte Eingabe.
- Die Optionsanalyse (Sprint 5) bekommt die von `CLAUDE.md` geforderten
  deterministischen Zonen, ohne selbst welche ableiten zu müssen.
- Die Zonenberechnung ist in drei Schritten einzeln nachprüfbar, wie Doc 10
  verlangt.
- Jedes Ergebnis trägt `TECHNICAL_ANALYSIS_VERSION` **und** die verwendeten
  Parameter. Ändert sich Verfahren oder Parametrisierung, bleiben alte
  Ergebnisse als nach altem Maßstab gerechnet erkennbar.

**Negativ / offen**

- Die Parameter sind an synthetischen Testreihen entwickelt, nicht an realen
  Kursverläufen. Sie werden sich beim Gegenprüfen an echten Charts
  voraussichtlich noch verschieben.
- Volumenprofile, Gap-Zonen und psychologische Niveaus fehlen gegenüber der
  Aufzählung in Doc 10. Das ist eine bewusste Zurückstellung, keine
  Vollständigkeit.
- `zone_tolerance_pct` ist relativ und damit für alle Aktien gleich, obwohl
  eine volatile Aktie breitere Zonen rechtfertigte. Eine Kopplung an die ATR
  wäre der naheliegende nächste Schritt, wenn sich das an echten Charts als
  Problem zeigt.

## Alternativen

**Alle sechs Eingangsgrößen aus Doc 10 umsetzen.** Vollständig gegenüber dem
Dokument, aber sechs Verfahren mit je eigener Parametrisierung und ohne
Möglichkeit, den Beitrag des einzelnen zu beurteilen. Verworfen zugunsten
eines Verfahrens, das sich zuerst bewähren muss.

**Zonen erst im Technical Agent bilden.** Widerspricht `CLAUDE.md` direkt:
Die Optionsanalyse darf Zonen nur deterministisch ermittelt verwenden und
nicht aus KI-Freitext ableiten. Verworfen.

**Numerische Zonenstärke mit gewichteter Formel.** Verworfen, siehe
Entscheidung 4.
