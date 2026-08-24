# Signalspezifikation — Gate G1

- Status: **Freigegeben.** Gate G1 ist fachlich freigegeben —
  [ADR 0010](../adr/0010-gate-g1-freigegeben.md), das
  [ADR 0007](../adr/0007-gate-g1-indikatorparameter.md) ablöst. Die
  Durchsicht der [G1-Prüfvorlage](g1-pruefvorlage.md) ist damit
  abgeschlossen, nicht mehr ausstehend.
- Zweck: exakte, testbare Definition der drei technischen Kaufsignale
  (Doc 10, Paragraph 6.4).
- Diese Datei ist die einzige Quelle, gegen die `IndicatorConfig`
  (`backend/src/ai_trading_analyst/config/settings.py`) und der Abschnitt
  `indicators:` in `config/default.yaml` befüllt sind. Weicht der Code von
  ihr ab, ist der Code falsch — nicht diese Datei.
- Eine Änderung an einem hier festgelegten Wert ist eine
  **Verfahrensänderung**: sie zieht eine neue Signalregelversion nach sich
  und bricht den Golden Master (`backend/tests/golden/`), der genau dafür
  da ist.

## Wie diese Datei benutzt wird

Jeder Wert trägt einen Status:

| Status | Bedeutung |
|---|---|
| **CONFIRMED** | von dir ausdrücklich bestätigt — mit Datum in der Freigabehistorie (Abschnitt 6) |
| **DOKUMENTIERT (Doc 10)** | im Fachdokument bereits so formuliert, aber noch nicht von dir für dieses Projekt gegengezeichnet |
| **OPEN** | keine Vorgabe vorhanden — hier liegt eine echte Entscheidung an |

**Kein Wert mit Status OPEN oder „DOKUMENTIERT (Doc 10)" wird implementiert.**
Ein von mir vorgeschlagener Wert ist niemals automatisch CONFIRMED — das gilt
auch dann, wenn er in einer früheren Antwort als „Vorschlag zur Prüfung"
stand. Status wechselt nur auf CONFIRMED, wenn du das an dieser Stelle explizit
tust (z. B. per Bearbeitung dieser Datei oder per Nachricht, die ich dann hier
nachtrage).

Session-Angaben (195-Minuten-Kerzen, reguläre US-Sitzung, keine Extended
Hours) sind **keine** Gate-G1-Entscheidung, sondern bereits getroffene
Architekturentscheidung (Doc 10 §6.1, §6.4) — sie werden hier nur der
Vollständigkeit halber je Signal mitgeführt, nicht zur erneuten Diskussion
gestellt.

---

## 1. Gemeinsame Parameter

Von dir bestätigt (Nachricht vom 2026-08-06):

| Parameter | Wert | Status |
|---|---|---|
| RSI-Länge | 14 | **CONFIRMED** |
| RSI-Quelle | Schlusskurs (close) | **CONFIRMED** |
| RSI-Glättung (RSI-MA) — Typ | SMA | **CONFIRMED** |
| RSI-Glättung (RSI-MA) — Länge | 14 | **CONFIRMED** |
| EMA5 — Länge | 5 | **CONFIRMED** |
| EMA5 — Quelle | Schlusskurs (close) | **CONFIRMED** |
| EMA20 — Länge | 20 | **CONFIRMED** |
| EMA20 — Quelle | Schlusskurs (close) | **CONFIRMED** |

Von dir bestätigt (Nachricht vom 2026-08-06, Punkte 1, 4, 5, 6):

| Parameter | Wert | Status |
|---|---|---|
| RSI — interne Glättung (`rsi_method`) | Wilder/RMA. Die lokale Berechnung soll TradingViews RSI-Berechnung reproduzieren. | **CONFIRMED** |
| `warmup_candles` | 250 vollständig geschlossene 195-Minuten-Kerzen vor der ersten auswertbaren Kerze. Blanket-Minimum für alle Indikatoren gemeinsam (RSI, RSI-MA, EMA5, EMA20) — deutlich über der längsten Einzellänge (20), weil Wilder/RMA-Glättung langsamer konvergiert, als die nominelle Länge vermuten lässt. Warm-up-Kerzen selbst sind keine Screening- oder Backtest-Ereignisse. Für den 5-Jahres-Backtest werden zusätzlich mindestens 250 Kerzen vor Beginn des eigentlichen Backtestzeitraums geladen. | **CONFIRMED** |
| Rundung / Gleichheitstoleranz | Keine Rundung, keine Toleranz. Alle Signalberechnungen verwenden die ungerundeten internen Werte — die im TradingView-Layout angezeigte Rundung ist für die Signalentscheidung irrelevant. Für Crossover-Vergleiche gilt einheitlich: Gleichheit auf der vorherigen Kerze ist zulässig (`<=`), auf der aktuellen Kerze muss die Überschreitung strikt sein (`>`). | **CONFIRMED** |
| Umgang mit fehlenden Kerzen/Indikatorwerten | Fehlende Daten zählen **nicht** als „Signal nicht erfüllt". Kann eine erforderliche Kerze oder ein erforderlicher Indikatorwert nicht zuverlässig bestimmt werden, erhält die betreffende Aktienprüfung den Status `UNKNOWN_DATA_INCOMPLETE` — nach Ausschöpfen der vorgesehenen Retry-Regel, ohne Klassifikation als Kandidat oder Nicht-Kandidat, ohne vertiefte Analyse, mit gespeichertem Datenfehler und sichtbar in Laufbericht und Dashboard. Vollständige Prozessbeschreibung in der [G1-Prüfvorlage](g1-pruefvorlage.md). | **CONFIRMED** |

Zusätzlich bestätigt (Nachricht vom 2026-08-06, Punkte 8–11 — Kandidatenregel
und Backtesting-Details):

| Parameter | Wert | Status |
|---|---|---|
| Historische Signalauswertung (Backtesting) | Entscheidungspunkte ausschließlich an der ersten Tageskerze — wie im Live-Betrieb. Die zweite Tageskerze ist kein eigener Entscheidungspunkt, darf aber als Kerze innerhalb des Sechs-Kerzen-Fensters eines späteren Entscheidungspunkts dienen. Die Performancemessung (Horizonte 5/10/20) zählt dagegen alle nachfolgenden abgeschlossenen Kerzen, unabhängig von erster/zweiter Tageskerze. Details und Pseudocode in der [G1-Prüfvorlage](g1-pruefvorlage.md), Abschnitt 4. | **CONFIRMED** |
| Fensterdefinition der Kandidatenregel | Sechs Kerzen: aktuelle Kerze `t` plus die fünf vorherigen `t-1` bis `t-5`. Details in der [G1-Prüfvorlage](g1-pruefvorlage.md), Abschnitt 3.2. | **CONFIRMED** |
| Zeitliche Verteilung der Signaltypen | Die mindestens zwei erforderlichen Signaltypen müssen nicht auf derselben Kerze auftreten; jeder Signaltyp zählt höchstens einmal pro Fenster, unabhängig von der Anzahl einzelner Ereignisse dieses Typs. Details in der [G1-Prüfvorlage](g1-pruefvorlage.md), Abschnitt 3.3. | **CONFIRMED** |
| Speicherung der Signalkombination (Backtesting) | Als Menge unterschiedlicher Signaltypen; die genaue Position im Fenster wird zusätzlich gespeichert, ist aber kein Kriterium für „identische Kombination". Details in der [G1-Prüfvorlage](g1-pruefvorlage.md), Abschnitt 4.3. | **CONFIRMED** |

Diese Datei enthält keine offenen Punkte mehr. Die vollständige,
konsolidierte Fassung steht in der [G1-Prüfvorlage](g1-pruefvorlage.md); sie
ist durchgesehen und mit [ADR 0010](../adr/0010-gate-g1-freigegeben.md)
freigegeben.

---

## 2. Signal A — RSI kreuzt RSI-Moving-Average von unten nach oben

### 2.1 Eingangsdaten

| Feld | Wert | Status |
|---|---|---|
| Eingangsdaten | Schlusskurse der 195-Minuten-Kerzen → RSI(14, Wilder/RMA) → RSI-MA(SMA, 14) auf den RSI-Werten | **CONFIRMED** |
| Session-Einstellung | Reguläre US-Sitzung, nur abgeschlossene Kerzen, keine Extended Hours | Architekturentscheidung, nicht Teil von Gate G1 |

### 2.2 Kerzenbedingungen

Wortlaut aus Doc 10, Paragraph 6.4:

> „der RSI in der vorherigen abgeschlossenen Kerze kleiner oder gleich seinem
> gleitenden Durchschnitt war, der RSI in der aktuellen abgeschlossenen Kerze
> größer als sein gleitender Durchschnitt ist."

| Feld | Formel | Status |
|---|---|---|
| Vorherige Kerze | `RSI[t-1] <= RSI_MA[t-1]` | **CONFIRMED** |
| Aktuelle Kerze | `RSI[t] > RSI_MA[t]` | **CONFIRMED** |
| Bedeutung von Gleichheit | `RSI[t-1] == RSI_MA[t-1]` zählt als „noch nicht gekreuzt" (erfüllt die Vorbedingung `<=`). `RSI[t] == RSI_MA[t]` (exakte Gleichheit auf der aktuellen Kerze) erfüllt die Bedingung `>` **nicht** — das Signal löst in diesem Fall nicht aus. Ungerundete interne Werte, keine Toleranz (Abschnitt 1). | **CONFIRMED** |

### 2.3 Umgang mit fehlenden Daten

Siehe gemeinsame Regel in Abschnitt 1 (`Umgang mit fehlenden Kerzen/Indikatorwerten`) — Status `UNKNOWN_DATA_INCOMPLETE`.

### 2.4 Beispiele

Illustrativ, mit angenommenen RSI-/RSI-MA-Werten, auf Basis der bestätigten
Regeln.

**Positive Beispiele (Signal löst aus):**

| # | RSI[t-1] | RSI_MA[t-1] | RSI[t] | RSI_MA[t] | Erwartetes Ergebnis | Begründung |
|---|---|---|---|---|---|---|
| A1 | 38,2 | 41,0 | 45,7 | 42,1 | **ERFÜLLT** | `38,2 <= 41,0` und `45,7 > 42,1` |
| A2 | 41,0 | 41,0 | 43,5 | 41,8 | **ERFÜLLT** | Exakte Gleichheit auf t-1 zählt als „nicht gekreuzt", Kreuzung erfolgt auf t |
| A3 | 29,9 | 30,0 | 30,05 | 30,0 | **ERFÜLLT** | Knapper, aber echter Übertritt (`30,05 > 30,0`) |

**Negative Grenzfälle (Signal löst NICHT aus):**

| # | RSI[t-1] | RSI_MA[t-1] | RSI[t] | RSI_MA[t] | Erwartetes Ergebnis | Begründung |
|---|---|---|---|---|---|---|
| A4 | 45,0 | 42,0 | 47,0 | 43,0 | **NICHT ERFÜLLT** | `RSI[t-1] > RSI_MA[t-1]` — bereits vor der Kerze oberhalb, kein Kreuzen |
| A5 | 38,0 | 41,0 | 41,0 | 41,0 | **NICHT ERFÜLLT** | `RSI[t] == RSI_MA[t]` — keine strikte Überschreitung |
| A6 | 38,0 | 41,0 | 40,5 | 41,0 | **NICHT ERFÜLLT** | Angenähert, aber `RSI[t] < RSI_MA[t]` — kein Übertritt |

---

## 3. Signal B — Kurs durchdringt EMA20 von unten nach oben und schließt darüber

### 3.1 Eingangsdaten

| Feld | Wert | Status |
|---|---|---|
| Eingangsdaten | Schlusskurse der 195-Minuten-Kerzen, EMA20 (Länge 20, Quelle close) | CONFIRMED (Parameter) |
| Session-Einstellung | Reguläre US-Sitzung, nur abgeschlossene Kerzen, keine Extended Hours | Architekturentscheidung, nicht Teil von Gate G1 |

### 3.2 Kerzenbedingungen ✅ CONFIRMED — Option 2 (Kerzenkörper)

Von drei zur Diskussion gestellten Lesarten wurde **Option 2** bestätigt:

| Feld | Formel | Status |
|---|---|---|
| Vorherige Kerze | `close[t-1] <= EMA20[t-1]` | **CONFIRMED** |
| Aktuelle Kerze — Eröffnung | `open[t] <= EMA20[t]` | **CONFIRMED** |
| Aktuelle Kerze — Schluss | `close[t] > EMA20[t]` | **CONFIRMED** |
| Bedeutung von Gleichheit | Gleichheit ist zulässig bei `close[t-1] <= EMA20[t-1]` und bei `open[t] <= EMA20[t]` (beides `<=`). Auf `close[t] > EMA20[t]` muss die Überschreitung strikt sein. | **CONFIRMED** |
| Ausdrücklich ausgeschlossen | Ein Gap-up, bei dem `open[t] > EMA20[t]` (Kerze eröffnet bereits oberhalb), zählt **nicht** als dieses Signal — unabhängig vom Schlusskurs. Eine reine Berührung/Durchdringung durch den Docht (Low unterhalb der EMA20, aber Open oberhalb) reicht **nicht** aus. | **CONFIRMED** |

Zur Einordnung: die ursprünglich zur Diskussion gestellten Alternativen —
reiner Schlusskursvergleich (vormals Option 1) und Docht-basiert (vormals
Option 3) — sind damit **nicht gewählt**.

### 3.3 Beispiel aus der Diskussion — jetzt mit bestätigtem Ergebnis

| Feld | Vortag (t-1) | Heute (t) |
|---|---|---|
| Open | — | 101,80 |
| Low | — | 99,50 |
| Close | 99,20 | 100,60 |
| EMA20 | 100,00 | 100,20 |

Mit der bestätigten Formel: `close[t-1] = 99,20 <= EMA20[t-1] = 100,00` (erfüllt),
aber `open[t] = 101,80 > EMA20[t] = 100,20` → Vorbedingung `open[t] <= EMA20[t]`
verletzt → **NICHT ERFÜLLT**. Diese Kerze eröffnet per Gap-up bereits oberhalb
der EMA20 und zählt deshalb ausdrücklich nicht als Signal B — genau der in
Abschnitt 3.2 benannte Ausschluss.

### 3.4 Beispiele

**Positive Beispiele (Signal löst aus):**

| # | close[t-1] | EMA20[t-1] | open[t] | close[t] | EMA20[t] | Ergebnis | Begründung |
|---|---|---|---|---|---|---|---|
| B1 | 99,20 | 100,00 | 99,80 | 100,60 | 100,20 | **ERFÜLLT** | `99,20<=100,00`, `99,80<=100,20`, `100,60>100,20` |
| B2 | 100,00 | 100,00 | 100,00 | 100,05 | 100,00 | **ERFÜLLT** | Gleichheit auf t-1 und bei open[t] zulässig, Schluss strikt über EMA20 |
| B3 | 98,50 | 100,00 | 100,20 | 100,21 | 100,20 | **ERFÜLLT** | Knapper, aber echter Schluss oberhalb; open[t] genau auf EMA20 (Gleichheit zulässig) |

**Negative bzw. grenzwertige Beispiele (Signal löst NICHT aus):**

| # | close[t-1] | EMA20[t-1] | open[t] | close[t] | EMA20[t] | Ergebnis | Begründung |
|---|---|---|---|---|---|---|---|
| B4 | 99,20 | 100,00 | 101,80 | 100,60 | 100,20 | **NICHT ERFÜLLT** | Gap-up: `open[t]=101,80 > EMA20[t]=100,20` — Vorbedingung verletzt (Abschnitt 3.3) |
| B5 | 99,20 | 100,00 | 99,80 | 100,20 | 100,20 | **NICHT ERFÜLLT** | `close[t] == EMA20[t]` — keine strikte Überschreitung |
| B6 | 100,50 | 100,00 | 99,80 | 100,60 | 100,20 | **NICHT ERFÜLLT** | `close[t-1]=100,50 > EMA20[t-1]=100,00` — bereits vor der Kerze oberhalb, kein Durchdringen von unten |

### 3.5 Umgang mit fehlenden Daten

Siehe gemeinsame Regel in Abschnitt 1. Fehlt `open[t]` (nicht nur `close`),
etwa bei einer unvollständig gelieferten historischen Kerze, ist die Formel
nicht auswertbar — Status `UNKNOWN_DATA_INCOMPLETE`, keine ersatzweise
Auswertung nur über `close`.

---

## 4. Signal C — EMA5 kreuzt EMA20 von unten nach oben und schließt darüber

### 4.1 Eingangsdaten

| Feld | Wert | Status |
|---|---|---|
| Eingangsdaten | EMA5 (Länge 5, Quelle close), EMA20 (Länge 20, Quelle close), Schlusskurs der Aktie | CONFIRMED (Parameter) |
| Session-Einstellung | Reguläre US-Sitzung, nur abgeschlossene Kerzen, keine Extended Hours | Architekturentscheidung, nicht Teil von Gate G1 |

### 4.2 Kerzenbedingungen ✅ CONFIRMED — Option 1 (keine zusätzliche Kursbedingung)

Wortlaut aus Doc 10, Paragraph 6.4 zur Kreuzung selbst:

> „EMA5 in der vorherigen abgeschlossenen Kerze kleiner oder gleich EMA20 war,
> EMA5 in der aktuellen abgeschlossenen Kerze größer als EMA20 ist"

| Feld | Formel | Status |
|---|---|---|
| Vorherige Kerze | `EMA5[t-1] <= EMA20[t-1]` | **CONFIRMED** |
| Aktuelle Kerze | `EMA5[t] > EMA20[t]` | **CONFIRMED** |
| Bedeutung von Gleichheit | Gleichheit auf t-1 zulässig (`<=`), auf t strikt (`>`). Ungerundete interne Werte, keine Toleranz (Abschnitt 1). | **CONFIRMED** |

Von drei zur Diskussion gestellten Lesarten der „Schlussbedingung" wurde
**Option 1** bestätigt: **keine zusätzliche Kursbedingung.** „Schließt darüber"
bedeutet, dass EMA5 auf Basis der vollständig geschlossenen Kerze oberhalb von
EMA20 liegt — ein auf Kerzenschluss bestätigtes EMA-Crossover, nicht die
zusätzliche Bedingung, dass der Aktienkurs selbst über einer oder beiden EMAs
schließen muss (vormals Option 2/3 — **nicht gewählt**).

| Feld | Regel | Status |
|---|---|---|
| Nur Kerzenschluss zählt | Ausgewertet werden ausschließlich `EMA5[t]` und `EMA20[t]` auf Basis der vollständig geschlossenen Kerze. Ein Crossover, das nur während der laufenden Kerze auftritt und bis zum Kerzenschluss wieder verschwindet, zählt nicht — es fließt gar nicht erst in `EMA5[t]`/`EMA20[t]` ein, da diese ausschließlich aus dem Schlusskurs der Kerze berechnet werden. | **CONFIRMED** |

### 4.3 Beispiel aus der Diskussion — jetzt mit bestätigtem Ergebnis

| Feld | Vortag (t-1) | Heute (t) |
|---|---|---|
| EMA5 | 99,80 | 100,90 |
| EMA20 | 100,00 | 100,50 |
| Close (Aktie) | 99,50 | 100,30 |

Kreuzung: `99,80 <= 100,00` und `100,90 > 100,50` → **ERFÜLLT**. Mit der
bestätigten Option 1 spielt es keine Rolle, dass der Aktienkurs (100,30) unter
der EMA5 (100,90) liegt — verlangt wird ausschließlich die Kreuzung der beiden
EMAs zueinander, keine zusätzliche Bedingung an den Aktienkurs.

### 4.4 Beispiele

**Positive Beispiele (Signal löst aus):**

| # | EMA5[t-1] | EMA20[t-1] | EMA5[t] | EMA20[t] | Ergebnis | Begründung |
|---|---|---|---|---|---|---|
| C1 | 99,80 | 100,00 | 100,90 | 100,50 | **ERFÜLLT** | `99,80<=100,00` und `100,90>100,50` |
| C2 | 100,00 | 100,00 | 100,30 | 100,10 | **ERFÜLLT** | Exakte Gleichheit auf t-1 zulässig, Kreuzung erfolgt auf t |
| C3 | 99,95 | 100,00 | 100,001 | 100,00 | **ERFÜLLT** | Knapper, aber echter Übertritt |

**Negative bzw. grenzwertige Beispiele (Signal löst NICHT aus):**

| # | EMA5[t-1] | EMA20[t-1] | EMA5[t] | EMA20[t] | Ergebnis | Begründung |
|---|---|---|---|---|---|---|
| C4 | 100,50 | 100,00 | 100,90 | 100,50 | **NICHT ERFÜLLT** | `EMA5[t-1] > EMA20[t-1]` — bereits vor der Kerze oberhalb, kein Kreuzen |
| C5 | 99,80 | 100,00 | 100,00 | 100,00 | **NICHT ERFÜLLT** | `EMA5[t] == EMA20[t]` — keine strikte Überschreitung |
| C6 | 99,50 | 100,00 | 99,90 | 100,00 | **NICHT ERFÜLLT** | Angenähert, aber `EMA5[t] < EMA20[t]` — kein Übertritt (auch falls eine schnellere, hier nicht verwendete Teilperiode kurzzeitig darüber gelegen hätte) |

### 4.5 Umgang mit fehlenden Daten

Siehe gemeinsame Regel in Abschnitt 1 — Status `UNKNOWN_DATA_INCOMPLETE`.

---

## 5. Nicht Teil dieser Spezifikation

Zur Abgrenzung, damit beim Ausfüllen nichts doppelt verhandelt wird:

- **Kandidatenregel** — vollständige Formeln, Pseudocode und Beispiele stehen
  in der [G1-Prüfvorlage](g1-pruefvorlage.md), Abschnitt 3, nicht in dieser
  Datei. Der Konfigurationswert `screening.lookback_closed_candles` wird bei
  der Implementierung in `signal_lookback_previous_candles` umbenannt (siehe
  G1-Prüfvorlage, Abschnitt 3.2).
- **Backtest-Einstiegspunkt und Cooldown** sind bereits freigegeben (F4, F5 —
  siehe Entwicklungsplan und `config/default.yaml`, Abschnitt `backtesting`).
- **Earnings-Filter** ist unabhängig von dieser Spezifikation (Doc 10 §6.5).

---

## 6. Freigabehistorie

| Datum | Was wurde bestätigt | Von |
|---|---|---|
| 2026-08-06 | RSI-Länge 14, RSI-Quelle close, RSI-MA Typ SMA / Länge 14, EMA5 Länge 5 / close, EMA20 Länge 20 / close | Thomas Kellner |
| 2026-08-06 | RSI-interne Glättung Wilder/RMA; Signal B = Option 2 (Kerzenkörper) mit vollständiger Formel; Signal C = Option 1 (keine Kursbedingung) mit vollständiger Formel; Vergleichspräzision (ungerundet, keine Toleranz, Gleichheitsregel für Crossover); `warmup_candles = 250`; Umgang mit fehlenden Daten (`UNKNOWN_DATA_INCOMPLETE`) | Thomas Kellner |
| 2026-08-06 | Sechs-Kerzen-Fenster (aktuelle + 5 vorherige) der Kandidatenregel; Signaltypen dürfen auf unterschiedlichen Kerzen auftreten, Zählung pro Typ statt pro Ereignis; Backtesting-Entscheidungspunkte ausschließlich an ersten Tageskerzen; Performancemessung in Kerzen statt Handelstagen; Speicherung der Signalkombination als Menge | Thomas Kellner |

Diese Tabelle wird bei jeder weiteren Bestätigung ergänzt.

**Alles davon ist eingetreten.** Die [G1-Prüfvorlage](g1-pruefvorlage.md) ist
bestätigt, Gate G1 ist vollständig freigegeben
([ADR 0010](../adr/0010-gate-g1-freigegeben.md), das
[ADR 0007](../adr/0007-gate-g1-indikatorparameter.md) ablöst), und der
Abschnitt `indicators:` in `config/default.yaml` ist gefüllt. `require_indicators()`
bricht weiterhin mit `GateNotClearedError` ab, falls er fehlt.
