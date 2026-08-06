# Signalspezifikation — Gate G1

- Status: **OPEN — teilweise bestätigt**
- Zweck: exakte, testbare Definition der drei technischen Kaufsignale, bevor
  der Screener implementiert wird (Doc 10, Paragraph 6.4; siehe auch
  [ADR 0007](../adr/0007-gate-g1-indikatorparameter.md))
- Diese Datei ist die einzige Quelle, gegen die `IndicatorConfig`
  (`backend/src/ai_trading_analyst/config/settings.py`) und der Abschnitt
  `indicators:` in `config/default.yaml` befüllt werden, sobald Gate G1
  vollständig bestätigt ist.

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

Noch offen — nicht durch die obige Nachricht abgedeckt:

| Parameter | Frage | Status |
|---|---|---|
| RSI — interne Glättung (`rsi_method`) | Wilder/RMA, SMA oder EMA? Das ist die Glättung *innerhalb* der RSI-Formel (Mittelung von Gains/Losses) — nicht dasselbe wie die RSI-MA aus der Zeile oben, die *auf* den fertigen RSI-Werten liegt. Der Marktstandard und TradingViews einzige verfügbare Variante ist Wilder/RMA; falls die Indikatorwerte künftig aus dem TradingView-Layout übernommen werden (§6.3), ist das ohnehin faktisch festgelegt. Für den Fallback-Pfad der lokalen Berechnung (§6.3 Fallback-Verhalten) muss der Wert trotzdem explizit hier stehen. | OPEN |
| `warmup_candles` | Wie viele Kerzen Vorlauf, bevor ein Signal als gültig bewertet wird? RSI und EMA sind pfadabhängig (Risiko R4 des Entwicklungsplans) — ein zu kurzer Vorlauf erzeugt Werte, die von TradingView abweichen, ohne dass das auffällt. Richtwert aus dem Plan: ≥ 200 Kerzen. | OPEN |
| Rundung / Gleichheitstoleranz | Vergleiche wie `RSI[t-1] <= RSI_MA[t-1]` werden exakt oder mit einer kleinen Tolerenz (z. B. 1e-8) ausgewertet? Ohne Toleranz kann Gleitkomma-Rauschen aus unterschiedlichen Datenquellen eine „Gleichheit" in ein „kleiner" oder „größer" kippen. | OPEN |
| Umgang mit fehlenden Kerzen | Fehlt eine Kerze (Datenausfall, Handelsunterbrechung), wird das Signal für diesen Tag **A)** stillschweigend als „nicht erfüllt" gewertet, oder **B)** mit explizitem Status `SIGNAL_UNKNOWN_MISSING_DATA` versehen und im Bericht als Datenrisiko ausgewiesen (analog zum Earnings-Status `UNKNOWN`, Doc 10 §6.5)? | OPEN |
| Historische Signalauswertung (Backtesting) | Werden für die 5-Jahres-Historie **alle** abgeschlossenen 195-Minuten-Kerzen ausgewertet (auch die zweite Tageskerze), oder ausschließlich die erste Tageskerze (`daily_candle_index: 1`), auf der auch der Live-Lauf screent? Das bestimmt die Stichprobengröße des Backtests und ob Live- und Backtest-Bedingungen exakt übereinstimmen. | OPEN |

---

## 2. Signal A — RSI kreuzt RSI-Moving-Average von unten nach oben

### 2.1 Eingangsdaten

| Feld | Wert | Status |
|---|---|---|
| Eingangsdaten | Schlusskurse der 195-Minuten-Kerzen → RSI(14) → RSI-MA(SMA, 14) auf den RSI-Werten | CONFIRMED (Parameter), OPEN (RSI-Glättung, siehe Abschnitt 1) |
| Session-Einstellung | Reguläre US-Sitzung, nur abgeschlossene Kerzen, keine Extended Hours | Architekturentscheidung, nicht Teil von Gate G1 |

### 2.2 Kerzenbedingungen

Wortlaut aus Doc 10, Paragraph 6.4:

> „der RSI in der vorherigen abgeschlossenen Kerze kleiner oder gleich seinem
> gleitenden Durchschnitt war, der RSI in der aktuellen abgeschlossenen Kerze
> größer als sein gleitender Durchschnitt ist."

| Feld | Formel | Status |
|---|---|---|
| Vorherige Kerze | `RSI[t-1] <= RSI_MA[t-1]` | DOKUMENTIERT (Doc 10 §6.4) |
| Aktuelle Kerze | `RSI[t] > RSI_MA[t]` | DOKUMENTIERT (Doc 10 §6.4) |
| Bedeutung von Gleichheit | `RSI[t-1] == RSI_MA[t-1]` zählt als „noch nicht gekreuzt" (erfüllt die Vorbedingung `<=`). `RSI[t] == RSI_MA[t]` (exakte Gleichheit auf der aktuellen Kerze) erfüllt die Bedingung `>` **nicht** — das Signal löst in diesem Fall nicht aus. | DOKUMENTIERT (Doc 10 §6.4), Gleichheitstoleranz siehe Abschnitt 1 |

### 2.3 Umgang mit fehlenden Daten

Siehe gemeinsame Frage in Abschnitt 1 (`Umgang mit fehlenden Kerzen`).

### 2.4 Beispiele — vorbehaltlich Bestätigung der offenen Punkte in Abschnitt 1

Illustrativ, mit angenommenen RSI-/RSI-MA-Werten. Verbindlich erst nach
Bestätigung der RSI-internen Glättung.

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

### 3.2 Kerzenbedingungen — vollständig OPEN

Doc 10, Paragraph 6.4 legt sich hier ausdrücklich nicht fest: „Die exakte
Definition von „durchdringt" muss vor der Implementierung als testbare Formel
dokumentiert werden." Drei mögliche Lesarten, keine davon gewählt:

| Option | Vorherige Kerze | Aktuelle Kerze | Bemerkung |
|---|---|---|---|
| **B-Option 1: reiner Schlusskurs-Vergleich** | `close[t-1] <= EMA20[t-1]` | `close[t] > EMA20[t]` | Ignoriert den Kerzenverlauf innerhalb der Kerze vollständig; einzige Grundlage sind zwei aufeinanderfolgende Schlusskurse. |
| **B-Option 2: Kerzenkörper** | `close[t-1] <= EMA20[t-1]` (wie oben) | `open[t] <= EMA20[t]` **und** `close[t] > EMA20[t]` | Verlangt zusätzlich, dass die aktuelle Kerze *unterhalb* der EMA20 eröffnet — die Kerze selbst „durchdringt" die Linie. |
| **B-Option 3: Docht-basiert** | — | `low[t] <= EMA20[t]` **und** `close[t] > EMA20[t]` | Die Kerze muss die EMA20 während der Kerze berührt oder unterschritten haben (Low reicht bis an oder unter die Linie), unabhängig vom Vortag. |

| Feld | Status |
|---|---|
| Gewählte Option | OPEN |
| Bedeutung von Gleichheit (`close[t-1] == EMA20[t-1]` bzw. `low[t] == EMA20[t]`) | OPEN — abhängig von der gewählten Option |

### 3.3 Warum die Wahl der Option den Ausgang konkret ändert

Ein einziges Kerzen-Beispiel, drei unterschiedliche Ergebnisse:

| Feld | Vortag (t-1) | Heute (t) |
|---|---|---|
| Open | — | 101,80 |
| Low | — | 99,50 |
| Close | 99,20 | 100,60 |
| EMA20 | 100,00 | 100,20 |

- **Option 1** (nur Close): `99,20 <= 100,00` und `100,60 > 100,20` → **ERFÜLLT**
- **Option 2** (Kerzenkörper): `open[t] = 101,80 > EMA20[t] = 100,20` → Vorbedingung `open <= EMA20` verletzt → **NICHT ERFÜLLT**
- **Option 3** (Docht): `low[t] = 99,50 <= EMA20[t] = 100,20` und `close[t] = 100,60 > 100,20` → **ERFÜLLT**

Dieses Beispiel zeigt, dass eine Kerze, die mit einer Kurslücke nach oben
eröffnet (Gap-up über die EMA20) und darüber schließt, nach Option 1 und 3 ein
Signal auslöst, nach Option 2 dagegen nicht — weil sie nie „von unten"
eröffnet hat.

### 3.4 Beispiele — Platzhalter, abhängig von der gewählten Option

Wird nach Festlegung der Option in Abschnitt 3.2 mit mindestens drei positiven
und drei negativen Fällen ergänzt (analog zu Abschnitt 2.4).

### 3.5 Umgang mit fehlenden Daten

Siehe gemeinsame Frage in Abschnitt 1. Zusätzlich bei Option 2/3 relevant:
Was gilt, wenn `open` oder `low` für eine historische Kerze fehlt, `close`
aber vorhanden ist? OPEN.

---

## 4. Signal C — EMA5 kreuzt EMA20 von unten nach oben und schließt darüber

### 4.1 Eingangsdaten

| Feld | Wert | Status |
|---|---|---|
| Eingangsdaten | EMA5 (Länge 5, Quelle close), EMA20 (Länge 20, Quelle close), Schlusskurs der Aktie | CONFIRMED (Parameter) |
| Session-Einstellung | Reguläre US-Sitzung, nur abgeschlossene Kerzen, keine Extended Hours | Architekturentscheidung, nicht Teil von Gate G1 |

### 4.2 Kerzenbedingungen — Kreuzung dokumentiert, Schlussbedingung OPEN

Wortlaut aus Doc 10, Paragraph 6.4 zur Kreuzung selbst:

> „EMA5 in der vorherigen abgeschlossenen Kerze kleiner oder gleich EMA20 war,
> EMA5 in der aktuellen abgeschlossenen Kerze größer als EMA20 ist"

| Feld | Formel | Status |
|---|---|---|
| Vorherige Kerze | `EMA5[t-1] <= EMA20[t-1]` | DOKUMENTIERT (Doc 10 §6.4) |
| Aktuelle Kerze | `EMA5[t] > EMA20[t]` | DOKUMENTIERT (Doc 10 §6.4) |

Doc 10 lässt die **Schlussbedingung** („schließt darüber") ausdrücklich offen
und untersagt eine eigenmächtige Annahme:

> „Bis zur fachlichen Freigabe darf Claude Code hierzu keine eigene Annahme
> dauerhaft implementieren."

| Option | Zusätzliche Bedingung | Bemerkung |
|---|---|---|
| **C-Option 1: EMA5 über EMA20** | keine zusätzliche Bedingung | Ist durch `EMA5[t] > EMA20[t]` bereits erfüllt — die „Schlussbedingung" wäre in diesem Fall deckungsgleich mit der Kreuzungsbedingung und würde nichts Neues verlangen. |
| **C-Option 2: Aktienkurs über EMA20** | zusätzlich `close[t] > EMA20[t]` | Der Aktienkurs selbst muss oberhalb der langsamen EMA schließen — kann bei sehr volatilen Kerzen von der EMA5-Kreuzung abweichen. |
| **C-Option 3: Aktienkurs über beiden EMAs** | zusätzlich `close[t] > EMA5[t]` **und** `close[t] > EMA20[t]` | Strengste Variante — verlangt, dass der Kurs selbst über beiden gleitenden Durchschnitten liegt, nicht nur die EMA5 über der EMA20. |

| Feld | Status |
|---|---|
| Gewählte Option | OPEN |
| Bedeutung von Gleichheit (`EMA5[t-1] == EMA20[t-1]`, ggf. `close[t] == EMA20[t]` / `close[t] == EMA5[t]`) | OPEN — abhängig von der gewählten Option |

### 4.3 Warum die Wahl der Option den Ausgang konkret ändert

| Feld | Vortag (t-1) | Heute (t) |
|---|---|---|
| EMA5 | 99,80 | 100,90 |
| EMA20 | 100,00 | 100,50 |
| Close (Aktie) | 99,50 | 100,30 |

- Kreuzung: `99,80 <= 100,00` und `100,90 > 100,50` → Kreuzung **erfüllt** (Doc-10-Teil)
- **Option 1** (keine Zusatzbedingung): bereits durch die Kreuzung erfüllt → **ERFÜLLT**
- **Option 2** (`close > EMA20`): `100,30 > 100,50`? Nein → **NICHT ERFÜLLT**
- **Option 3** (`close > EMA5` und `close > EMA20`): `100,30 > 100,90`? Nein → **NICHT ERFÜLLT**

Dieses Beispiel — EMA5 kreuzt EMA20 klar nach oben, aber der tatsächliche
Aktienkurs bleibt darunter (z. B. durch einen langen oberen Docht oder eine
volatile Kerze) — ist genau der Fall, für den Doc 10 die Klärung verlangt:
Nach Option 1 ein gültiges Signal, nach Option 2/3 nicht.

### 4.4 Beispiele — Platzhalter, abhängig von der gewählten Option

Wird nach Festlegung der Option in Abschnitt 4.2 mit mindestens drei positiven
und drei negativen Fällen ergänzt (analog zu Abschnitt 2.4).

### 4.5 Umgang mit fehlenden Daten

Siehe gemeinsame Frage in Abschnitt 1.

---

## 5. Nicht Teil dieser Spezifikation

Zur Abgrenzung, damit beim Ausfüllen nichts doppelt verhandelt wird:

- **Kandidatenregel** („mindestens 2 von 3 Signalen in den letzten 5
  abgeschlossenen Kerzen") ist unabhängig von den einzelnen Signalformeln
  bereits konfiguriert (`screening.required_signal_count`,
  `screening.lookback_closed_candles` in `config/default.yaml`) und nicht Teil
  von Gate G1.
- **Backtest-Einstiegspunkt und Cooldown** sind bereits freigegeben (F4, F5 —
  siehe Entwicklungsplan und `config/default.yaml`, Abschnitt `backtesting`).
- **Earnings-Filter** ist unabhängig von dieser Spezifikation (Doc 10 §6.5).

---

## 6. Freigabehistorie

| Datum | Was wurde bestätigt | Von |
|---|---|---|
| 2026-08-06 | RSI-Länge 14, RSI-Quelle close, RSI-MA Typ SMA / Länge 14, EMA5 Länge 5 / close, EMA20 Länge 20 / close | Thomas Kellner |

Diese Tabelle wird bei jeder weiteren Bestätigung ergänzt. Sobald alle
Positionen in Abschnitt 1–4 den Status CONFIRMED tragen, gilt Gate G1 als
freigegeben; ein neues ADR löst dann [ADR 0007](../adr/0007-gate-g1-indikatorparameter.md)
ab und der Abschnitt `indicators:` in `config/default.yaml` wird aktiviert.
