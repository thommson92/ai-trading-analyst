# G1-Prüfvorlage — konsolidierte Signal- und Kandidatenlogik

- Status: **Alle Festlegungen bestätigt — zur finalen Durchsicht vorgelegt,
  noch keine Implementierung.**
- Zweck: Diese Datei ist die einzige, vollständige und in sich geschlossene
  Grundlage, gegen die der Screener und das Backtesting-Modul implementiert
  werden, sobald du diese finale Fassung ausdrücklich freigibst
  (Doc 10, Paragraph 6.4).
- Herkunft: konsolidiert aus [signal-specification.md](signal-specification.md)
  (dort mit Diskussion, Optionen und Herleitung) und den Festlegungen aus
  deinen Nachrichten vom 2026-08-06.
- **Es ist noch kein Code geschrieben.** Diese Datei wird implementiert, sobald
  du sie ausdrücklich freigibst — nicht vorher.

## Kennzeichnung in diesem Dokument

Jede Regel trägt **BESTÄTIGT** und das Datum ihrer Bestätigung. Wo eine Regel
von mir formalisiert wurde (z. B. Pseudocode, Datenstruktur-Skizzen), ist sie
als **Formalisierung von** der jeweiligen fachlichen Festlegung gekennzeichnet
— inhaltlich nichts Neues, nur die technische Ausformulierung einer bereits
bestätigten Regel.

---

## 1. Gemeinsame Grundlagen

### 1.1 Eingangsdaten

Alle drei Signale arbeiten ausschließlich auf **vollständig geschlossenen
195-Minuten-Kerzen der regulären US-Sitzung** (keine Extended Hours). Jede
Kerze liefert Open, High, Low, Close, Volume; alle drei Signale verwenden
ausschließlich **Close** als Preisquelle für die Indikatorberechnung — Open
fließt bei Signal B zusätzlich als eigener Vergleichswert ein (nicht als
Indikator-Input).

### 1.2 Indikatorparameter — BESTÄTIGT

| Indikator | Länge | Quelle | Glättung |
|---|---|---|---|
| RSI | 14 | Close | Wilder/RMA (reproduziert TradingViews RSI-Berechnung) |
| RSI-MA | 14 | RSI-Werte (nicht Preis) | SMA |
| EMA5 | 5 | Close | Exponentiell |
| EMA20 | 20 | Close | Exponentiell |

### 1.3 Warm-up — BESTÄTIGT

- Mindestens **250 vollständig geschlossene 195-Minuten-Kerzen** müssen vor der
  ersten auswertbaren Kerze vorliegen.
- Ein einziger Blanket-Wert für alle vier Indikatoren gemeinsam — nicht separat
  pro Indikator kürzer bemessen — weil Wilder/RMA-Glättung deutlich langsamer
  konvergiert, als die nominelle Länge (14) vermuten lässt.
- Warm-up-Kerzen selbst werden **nicht** als Screening- oder
  Backtest-Ereignisse ausgewertet — sie dienen ausschließlich der
  Indikator-Initialisierung.
- Für den 5-Jahres-Backtest werden zusätzlich mindestens 250 Kerzen **vor**
  dem eigentlichen Backtestzeitraum geladen, damit bereits die erste
  ausgewertete Kerze des Backtestfensters vollen Warm-up-Vorlauf hat.

### 1.4 Rundung und Vergleichspräzision — BESTÄTIGT

- Alle Signalberechnungen verwenden die **ungerundeten internen Werte**.
- Die im TradingView-Layout angezeigte, gerundete Darstellung ist für die
  Signalentscheidung **nicht** maßgeblich.
- **Keine Gleichheitstoleranz** (kein Epsilon) — Vergleiche erfolgen exakt.
- Einheitliche Regel für jeden Crossover-Vergleich in diesem Dokument:
  - **Vorherige Kerze:** Gleichheit ist zulässig (`<=`).
  - **Aktuelle Kerze:** die Überschreitung muss strikt sein (`>`).

### 1.5 Umgang mit fehlenden Daten — BESTÄTIGT

Fehlende Daten zählen **nicht** als „Signal nicht erfüllt". Ablaufmodell:

```text
1. Datenabruf schlägt fehl oder liefert unvollständige Werte
   (fehlende Kerze, fehlender Indikatorwert)
        │
        ▼
2. Retry gemäß der vorgesehenen Retry-Regel
   (nur temporäre Fehler: Netzwerk, Rate Limit, Timeout — Doc 10 §11)
        │
        ▼
3. Weiterhin unvollständig?
        │
   ┌────┴────┐
   │ Ja       │ Nein → normale Signalauswertung (Abschnitt 2/3)
   ▼
4. Status der Aktienprüfung für diesen Lauf:
   UNKNOWN_DATA_INCOMPLETE
        │
        ▼
5. Konsequenzen:
   - keine Klassifikation als Kandidat
   - keine Klassifikation als Nicht-Kandidat
   - keine vertiefte Analyse (Backtesting/Research/Scoring) wird gestartet
   - exakter Datenfehler und betroffener Zeitraum werden gespeichert
   - sichtbar im Laufbericht und im Dashboard als Datenrisiko
```

**Eine Datenlücke wird an keiner Stelle stillschweigend als negatives Signal
behandelt.** Dies gilt für jede einzelne Kerze und jeden einzelnen
Indikatorwert, die für die Auswertung eines Signals oder des Sechs-Kerzen-
Fensters (Abschnitt 3) benötigt werden — fehlt auch nur einer davon, erhält
die *gesamte* Aktienprüfung für diesen Lauf den Status
`UNKNOWN_DATA_INCOMPLETE`, nicht nur das einzelne betroffene Signal.

---

## 2. Die drei Signale — vollständige Formeln und Pseudocode

### 2.1 Signal A — RSI kreuzt RSI-Moving-Average von unten nach oben

`signal_type: RSI_CROSS` (Doc 05)

**Formel:**

```text
RSI[t-1] <= RSI_MA[t-1]   UND   RSI[t] > RSI_MA[t]
```

**Pseudocode:**

```python
def signal_a(candles, t):
    """RSI(14, Wilder) kreuzt SMA(RSI, 14) von unten nach oben."""
    rsi_prev, rsi_curr = candles.rsi[t - 1], candles.rsi[t]
    rsi_ma_prev, rsi_ma_curr = candles.rsi_ma[t - 1], candles.rsi_ma[t]

    if any(value is None for value in (rsi_prev, rsi_curr, rsi_ma_prev, rsi_ma_curr)):
        raise DataIncomplete(candle_index=t, required=["RSI", "RSI_MA"])

    return rsi_prev <= rsi_ma_prev and rsi_curr > rsi_ma_curr
```

**Beispiele:**

| # | RSI[t-1] | RSI_MA[t-1] | RSI[t] | RSI_MA[t] | Ergebnis | Begründung |
|---|---|---|---|---|---|---|
| A1 | 38,2 | 41,0 | 45,7 | 42,1 | ERFÜLLT | `38,2<=41,0` und `45,7>42,1` |
| A2 | 41,0 | 41,0 | 43,5 | 41,8 | ERFÜLLT | Gleichheit auf t-1 zulässig, Kreuzung auf t |
| A3 | 29,9 | 30,0 | 30,05 | 30,0 | ERFÜLLT | Knapper, aber echter Übertritt |
| A4 | 45,0 | 42,0 | 47,0 | 43,0 | NICHT ERFÜLLT | bereits vor der Kerze oberhalb — kein Kreuzen |
| A5 | 38,0 | 41,0 | 41,0 | 41,0 | NICHT ERFÜLLT | `RSI[t]==RSI_MA[t]` — keine strikte Überschreitung |
| A6 | 38,0 | 41,0 | 40,5 | 41,0 | NICHT ERFÜLLT | angenähert, aber `RSI[t]<RSI_MA[t]` |

### 2.2 Signal B — Kurs durchdringt EMA20 von unten nach oben (Kerzenkörper)

`signal_type: PRICE_EMA20_BREAKOUT` (Doc 05)

**Formel:**

```text
close[t-1] <= EMA20[t-1]   UND   open[t] <= EMA20[t]   UND   close[t] > EMA20[t]
```

Ein Gap-up (`open[t] > EMA20[t]`) erfüllt das Signal nicht, unabhängig vom
Schlusskurs. Eine reine Docht-Berührung ohne körperliches Durchdringen reicht
nicht aus.

**Pseudocode:**

```python
def signal_b(candles, t):
    """Kerzenkörper durchdringt EMA20 von unten und schliesst darueber."""
    close_prev, ema20_prev = candles.close[t - 1], candles.ema20[t - 1]
    open_curr, close_curr, ema20_curr = candles.open[t], candles.close[t], candles.ema20[t]

    if any(v is None for v in (close_prev, ema20_prev, open_curr, close_curr, ema20_curr)):
        raise DataIncomplete(candle_index=t, required=["OPEN", "CLOSE", "EMA20"])

    return close_prev <= ema20_prev and open_curr <= ema20_curr and close_curr > ema20_curr
```

**Beispiele:**

| # | close[t-1] | EMA20[t-1] | open[t] | close[t] | EMA20[t] | Ergebnis | Begründung |
|---|---|---|---|---|---|---|---|
| B1 | 99,20 | 100,00 | 99,80 | 100,60 | 100,20 | ERFÜLLT | alle drei Teilbedingungen erfüllt |
| B2 | 100,00 | 100,00 | 100,00 | 100,05 | 100,00 | ERFÜLLT | Gleichheit auf t-1 und open[t] zulässig |
| B3 | 98,50 | 100,00 | 100,20 | 100,21 | 100,20 | ERFÜLLT | open[t] genau auf EMA20 (Gleichheit zulässig) |
| B4 | 99,20 | 100,00 | 101,80 | 100,60 | 100,20 | NICHT ERFÜLLT | Gap-up: `open[t]>EMA20[t]` |
| B5 | 99,20 | 100,00 | 99,80 | 100,20 | 100,20 | NICHT ERFÜLLT | `close[t]==EMA20[t]` — keine strikte Überschreitung |
| B6 | 100,50 | 100,00 | 99,80 | 100,60 | 100,20 | NICHT ERFÜLLT | bereits vor der Kerze oberhalb — kein Durchdringen von unten |

### 2.3 Signal C — EMA5 kreuzt EMA20 von unten nach oben

`signal_type: EMA5_EMA20_CROSS` (Doc 05)

**Formel:**

```text
EMA5[t-1] <= EMA20[t-1]   UND   EMA5[t] > EMA20[t]
```

Keine zusätzliche Bedingung an den Aktienkurs. Ausgewertet wird ausschließlich
der auf Kerzenschluss berechnete EMA-Wert — ein nur intrabar auftretendes und
bis zum Kerzenschluss wieder verschwundenes Crossover fließt gar nicht erst
ein, da EMA5/EMA20 ausschließlich aus dem Schlusskurs der Kerze berechnet
werden.

**Pseudocode:**

```python
def signal_c(candles, t):
    """EMA5 kreuzt EMA20 von unten nach oben, auf Kerzenschluss bestaetigt."""
    ema5_prev, ema20_prev = candles.ema5[t - 1], candles.ema20[t - 1]
    ema5_curr, ema20_curr = candles.ema5[t], candles.ema20[t]

    if any(v is None for v in (ema5_prev, ema20_prev, ema5_curr, ema20_curr)):
        raise DataIncomplete(candle_index=t, required=["EMA5", "EMA20"])

    return ema5_prev <= ema20_prev and ema5_curr > ema20_curr
```

**Beispiele:**

| # | EMA5[t-1] | EMA20[t-1] | EMA5[t] | EMA20[t] | Ergebnis | Begründung |
|---|---|---|---|---|---|---|
| C1 | 99,80 | 100,00 | 100,90 | 100,50 | ERFÜLLT | `99,80<=100,00` und `100,90>100,50` |
| C2 | 100,00 | 100,00 | 100,30 | 100,10 | ERFÜLLT | Gleichheit auf t-1 zulässig |
| C3 | 99,95 | 100,00 | 100,001 | 100,00 | ERFÜLLT | Knapper, aber echter Übertritt |
| C4 | 100,50 | 100,00 | 100,90 | 100,50 | NICHT ERFÜLLT | bereits vor der Kerze oberhalb — kein Kreuzen |
| C5 | 99,80 | 100,00 | 100,00 | 100,00 | NICHT ERFÜLLT | `EMA5[t]==EMA20[t]` — keine strikte Überschreitung |
| C6 | 99,50 | 100,00 | 99,90 | 100,00 | NICHT ERFÜLLT | angenähert, aber `EMA5[t]<EMA20[t]` |

---

## 3. Die 2-aus-3-Kandidatenregel und das Sechs-Kerzen-Fenster

### 3.1 Ausgangslage

Bereits konfiguriert (`config/default.yaml`, Abschnitt `screening`):

```yaml
required_signal_count: 2
lookback_closed_candles: 5   # wird umbenannt, siehe Abschnitt 3.2
```

Wortlaut Doc 10, Paragraph 6.4: „mindestens zwei der drei Signale erfüllt
sind, die betreffenden Signale in der aktuellen oder einer der vorherigen
fünf abgeschlossenen 195-Minuten-Kerzen aufgetreten sind." Diese Formulierung
ließ zwei Dinge offen, die für eine testbare Implementierung nötig sind —
beide sind jetzt bestätigt (Abschnitt 3.2, 3.3).

### 3.2 Fensterdefinition — BESTÄTIGT

Das Fenster umfasst **sechs vollständig abgeschlossene 195-Minuten-Kerzen**:
die aktuell betrachtete Kerze `t` sowie die fünf unmittelbar vorherigen Kerzen
`t-1` bis `t-5`. Die aktuelle Kerze wird **zusätzlich und immer** einbezogen —
„aktuell oder innerhalb der letzten fünf abgeschlossenen Kerzen" ist wörtlich
zu verstehen: current candle + 5 previous candles = 6 candles total.

```text
Fenster = { t, t-1, t-2, t-3, t-4, t-5 }
```

**Namensklärung (Umsetzungshinweis, kein fachlicher Punkt):** Der bestehende
Konfigurationsname `lookback_closed_candles` ist mehrdeutig — er könnte als
„Gesamtgröße des Fensters" oder als „Anzahl der Kerzen vor der aktuellen"
gelesen werden. Er wird bei der Implementierung umbenannt in
`signal_lookback_previous_candles: 5`, um eindeutig auszudrücken: fünf
*zusätzliche, vorherige* Kerzen, die aktuelle Kerze kommt immer und
unabhängig davon hinzu. Diese Umbenennung ist noch **nicht** vorgenommen
worden — sie betrifft `backend/src/ai_trading_analyst/config/settings.py` und
`config/default.yaml`, beide aktuell Teil des noch nicht gemergten PR #1, und
wird zusammen mit der übrigen Screener-Implementierung nachgezogen, um keine
Änderung auf einer instabilen Basis vorzunehmen.

### 3.3 Zeitliche Verteilung und Zählung der Signaltypen — BESTÄTIGT

Die mindestens zwei erforderlichen Signaltypen müssen **nicht auf derselben
Kerze** auftreten. Eine Aktie qualifiziert sich, wenn mindestens zwei
verschiedene der drei Signaltypen irgendwo innerhalb des Sechs-Kerzen-Fensters
aufgetreten sind — unabhängig davon, auf welcher der sechs Kerzen jeweils.

Beispiel: RSI-Crossover (`RSI_CROSS`) auf `t-4`, Kursdurchbruch durch EMA20
(`PRICE_EMA20_BREAKOUT`) auf `t-1`, kein EMA5-/EMA20-Crossover
(`EMA5_EMA20_CROSS`) im gesamten Fenster → die 2-aus-3-Regel ist erfüllt.

**Zählung pro Signaltyp, nicht pro Signalereignis:** Jeder Signaltyp zählt
innerhalb eines Entscheidungsfensters **höchstens einmal**, auch wenn derselbe
Signaltyp mehrfach im Fenster auftritt (z. B. `RSI_CROSS` sowohl auf `t-4` als
auch erneut auf `t-2`). Die Anzahl erfüllter Signale für die 2-aus-3-Regel wird
aus der Menge der **unterschiedlichen** erfüllten Signaltypen gebildet, nicht
aus der Anzahl einzelner Signalereignisse.

### 3.4 Pseudocode

```python
def evaluate_candidate(stock, t, config):
    """Kandidatenpruefung fuer eine Aktie am Tag der Kerze t."""

    # 1. Warm-up (Abschnitt 1.3)
    if not has_full_history(stock, t, minimum_candles=config.warmup_candles):
        return Result(status="UNKNOWN_DATA_INCOMPLETE", reason="warmup_insufficient")

    # 2. Fenster bestimmen (Abschnitt 3.2 -- 6 Kerzen: aktuelle + 5 vorherige)
    #    config-Feld heisst nach der Umbenennung signal_lookback_previous_candles
    window = range(t - config.signal_lookback_previous_candles, t + 1)  # t-5 .. t

    # 3. Vollstaendigkeit der Rohdaten und Indikatorwerte im Fenster pruefen
    for i in window:
        if not candle_complete(stock, i) or not indicators_complete(stock, i):
            return Result(
                status="UNKNOWN_DATA_INCOMPLETE",
                reason="missing_candle_or_indicator",
                affected_index=i,
            )

    # 4. Jeden Signaltyp unabhaengig ueber das gesamte Fenster auswerten
    #    (Abschnitt 3.3 -- nicht auf dieselbe Kerze beschraenkt; jeder Typ
    #    zaehlt hoechstens einmal, auch bei mehrfachem Auftreten im Fenster)
    fired = {
        "RSI_CROSS": any(signal_a(stock.candles, i) for i in window),
        "PRICE_EMA20_BREAKOUT": any(signal_b(stock.candles, i) for i in window),
        "EMA5_EMA20_CROSS": any(signal_c(stock.candles, i) for i in window),
    }

    # 5. 2-aus-3-Regel -- Anzahl unterschiedlicher erfuellter Signaltypen,
    #    nicht Anzahl einzelner Signalereignisse
    if sum(fired.values()) >= config.required_signal_count:
        return Result(status="CANDIDATE", fired_signal_types=fired)
    return Result(status="NOT_CANDIDATE", fired_signal_types=fired)
```

**Wichtige Abgrenzung — keine Vermischung mit dem Backtesting-Cooldown:**
`evaluate_candidate` gilt sowohl für die **tägliche Live-Prüfung** als auch je
Entscheidungspunkt im **Backtesting** (Abschnitt 4.1 legt fest, dass im
Backtesting nur erste Tageskerzen ein solcher Entscheidungspunkt sind). Der
bereits freigegebene Fünf-Kerzen-Cooldown des Backtestings (F5) ist davon
unabhängig ein drittes, separates Konzept — er entzerrt geclusterte
Qualifikationen über die 5-Jahres-Historie erst *nach* der
Kandidatenermittlung, nicht die Fensterprüfung selbst. Drei unterschiedliche
Zahlen (6-Kerzen-Fenster, 5-Kerzen-Cooldown, 250-Kerzen-Warm-up) sind bewusst
nicht zu verwechseln, auch wenn zwei davon zufällig denselben Zahlenwert 5
in ihrer Definition verwenden.

### 3.5 Beispiel

Aus deiner Bestätigung übernommen:

| Kerze | RSI_CROSS | PRICE_EMA20_BREAKOUT | EMA5_EMA20_CROSS |
|---|---|---|---|
| t-5 | — | — | — |
| t-4 | ERFÜLLT | — | — |
| t-3 | — | — | — |
| t-2 | — | — | — |
| t-1 | — | ERFÜLLT | — |
| t (aktuell) | — | — | — |

Ergebnis: `RSI_CROSS` trat auf `t-4` auf, `PRICE_EMA20_BREAKOUT` auf `t-1` —
zwei von drei Signaltypen im Fenster erfüllt, unabhängig davon, dass sie auf
unterschiedlichen Kerzen auftraten und keines davon auf der aktuellen Kerze
`t` selbst → **CANDIDATE**.

---

## 4. Backtesting — Entscheidungszeitpunkte, Performancemessung, Signalkombination

Dieser Abschnitt betrifft nicht die Signalformeln selbst, sondern wie sie im
5-Jahres-Backtesting (Sprint 3) angewendet werden. Er schließt die zuvor
offene Frage aus [signal-specification.md](signal-specification.md),
Abschnitt 1 ("Historische Signalauswertung") ab.

### 4.1 Entscheidungszeitpunkte — BESTÄTIGT

Das Backtesting reproduziert die tatsächlich handelbare tägliche Ausführung
des Systems. Eine historische Kandidatenentscheidung wird deshalb **nur
einmal pro regulärem US-Handelstag** bewertet — unmittelbar nach Abschluss der
**ersten** regulären 195-Minuten-Kerze (`daily_candle_index: 1`, wie im Live-
Betrieb).

- Die **zweite** 195-Minuten-Kerze eines Handelstages ist **kein eigener
  Entscheidungszeitpunkt** — an ihr wird im Backtesting nie eine
  Kandidatenprüfung durchgeführt.
- Sie darf jedoch als historische Kerze **innerhalb** des Sechs-Kerzen-Fensters
  eines *späteren* Entscheidungszeitpunkts verwendet werden. Ein Signal, das
  auf der zweiten Kerze eines vorherigen Handelstages auftrat, kann so zur
  Qualifikation eines nachfolgenden täglichen Laufs beitragen.

**Formalisierung — Pseudocode für den historischen Replay:**

```python
def backtest_replay(stock, all_candles, config):
    """Iteriert ausschliesslich ueber erste Tageskerzen als Entscheidungspunkte;
    das Sechs-Kerzen-Fenster durchlaeuft dagegen die vollstaendige,
    tagesgrenzenunabhaengige Kerzenfolge."""
    decisions = []
    for t in all_candles.indices:
        if all_candles.daily_candle_index[t] != 1:
            continue  # zweite Tageskerze: kein Entscheidungspunkt (4.1)

        result = evaluate_candidate(stock, t, config)  # Abschnitt 3.4
        if result.status == "CANDIDATE":
            decisions.append(historical_decision(stock, t, result, all_candles))
    return decisions
```

### 4.2 Performancemessung — BESTÄTIGT

Die zukünftige Performance nach einem historischen Einstieg wird über **alle**
nachfolgenden vollständig abgeschlossenen 195-Minuten-Kerzen gemessen —
unabhängig davon, ob es sich um die erste oder zweite Kerze eines
Handelstages handelt. Die Horizonte 5, 10 und 20 zählen **Kerzen**, nicht
Handelstage und nicht ausschließlich erste Tageskerzen.

```python
def performance_at_horizon(all_candles, decision_index, horizon):
    """horizon in Kerzen, nicht in Handelstagen -- zaehlt ueber
    Tagesgrenzen hinweg durch die Kerzenfolge, erste wie zweite Tageskerzen."""
    entry_price = all_candles.close[decision_index]
    exit_price = all_candles.close[decision_index + horizon]
    return (exit_price - entry_price) / entry_price
```

Da eine Entscheidung (4.1) immer auf einer ersten Tageskerze liegt, fällt z. B.
Horizont 5 (`t+5`) je nach Zählung auf eine zweite Tageskerze zwei Handelstage
später — das ist beabsichtigt und keine Inkonsistenz.

### 4.3 Speicherung der Signalkombination — BESTÄTIGT

Die Signalkombination wird als **Menge unterschiedlicher Signaltypen** am
historischen Entscheidungszeitpunkt gespeichert, nicht als geordnete Liste und
nicht als Anzahl einzelner Signalereignisse (konsistent mit Abschnitt 3.3).
Mögliche Kombinationen, die die 2-aus-3-Regel erfüllen können:

- `RSI_CROSS` + `PRICE_EMA20_BREAKOUT`
- `RSI_CROSS` + `EMA5_EMA20_CROSS`
- `PRICE_EMA20_BREAKOUT` + `EMA5_EMA20_CROSS`
- alle drei Signaltypen

Die genaue Position jedes einzelnen Signalereignisses innerhalb des
Sechs-Kerzen-Fensters (z. B. „`RSI_CROSS` auf `t-4`") wird **zusätzlich**
gespeichert — für Audit und Bericht — ist aber **zunächst kein Kriterium**
dafür, ob zwei historische Instanzen als „identische Signalkombination"
gelten (Doc 07: „identische Signalkombinationen"). Für die Gruppierung im
Backtesting zählt ausschließlich die Menge der aufgetretenen Signaltypen.

**Beispielhafte Datenstruktur:**

```python
historical_decision = {
    "decision_candle_index": t,
    "signal_types": frozenset({"RSI_CROSS", "PRICE_EMA20_BREAKOUT"}),
    "signal_positions": {"RSI_CROSS": t - 4, "PRICE_EMA20_BREAKOUT": t - 1},
}
```

Zwei Instanzen mit demselben `signal_types` gelten für die
Backtest-Statistik als identische Kombination, auch wenn ihre
`signal_positions` unterschiedlich sind.

---

## 5. Freigabe-Checkliste

| # | Punkt | Status |
|---|---|---|
| 1 | RSI-Parameter und interne Glättung (Abschnitt 1.2) | BESTÄTIGT |
| 2 | Signal-A-Formel — `RSI_CROSS` (Abschnitt 2.1) | BESTÄTIGT |
| 3 | Signal-B-Formel, Option 2 — `PRICE_EMA20_BREAKOUT` (Abschnitt 2.2) | BESTÄTIGT |
| 4 | Signal-C-Formel, Option 1 — `EMA5_EMA20_CROSS` (Abschnitt 2.3) | BESTÄTIGT |
| 5 | Warm-up = 250 Kerzen (Abschnitt 1.3) | BESTÄTIGT |
| 6 | Rundung / Vergleichspräzision (Abschnitt 1.4) | BESTÄTIGT |
| 7 | Umgang mit fehlenden Daten, `UNKNOWN_DATA_INCOMPLETE` (Abschnitt 1.5) | BESTÄTIGT |
| 8 | Fensterdefinition: 6 Kerzen, aktuelle + 5 vorherige (Abschnitt 3.2) | BESTÄTIGT |
| 9 | Signaltypen dürfen auf unterschiedlichen Kerzen auftreten; Zählung pro Typ, nicht pro Ereignis (Abschnitt 3.3) | BESTÄTIGT |
| 10 | Backtesting-Entscheidungszeitpunkte: nur erste Tageskerze (Abschnitt 4.1) | BESTÄTIGT |
| 11 | Performancemessung in Kerzen, nicht in Handelstagen (Abschnitt 4.2) | BESTÄTIGT |
| 12 | Signalkombination als Menge, Position separat gespeichert (Abschnitt 4.3) | BESTÄTIGT |

Nicht Teil der fachlichen Freigabe, sondern reiner Umsetzungshinweis: die
Umbenennung von `lookback_closed_candles` zu
`signal_lookback_previous_candles` (Abschnitt 3.2) ist noch nicht im Code
vorgenommen — sie erfolgt zusammen mit der Screener-Implementierung.

**Alle zwölf fachlichen Punkte sind bestätigt. Gate G1 gilt als freigegeben,
sobald du diese konsolidierte Fassung als exakt und widerspruchsfrei
bestätigst.**
