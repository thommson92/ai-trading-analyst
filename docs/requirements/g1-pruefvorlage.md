# G1-Prüfvorlage — konsolidierte Signal- und Kandidatenlogik

- Status: **Zur abschließenden Prüfung vorgelegt — noch keine Implementierung**
- Zweck: Diese Datei ist die einzige, vollständige und in sich geschlossene
  Grundlage, gegen die der Screener implementiert wird, sobald sie
  ausdrücklich freigegeben ist (Doc 10, Paragraph 6.4).
- Herkunft: konsolidiert aus [signal-specification.md](signal-specification.md)
  (dort mit Diskussion, Optionen und Herleitung) sowie neu formalisiert für
  diese Prüfung (Kandidatenregel-Fenster, Pseudocode).
- **Es ist noch kein Code geschrieben.** Diese Datei wird implementiert, sobald
  du sie ausdrücklich freigibst — nicht vorher.

## Kennzeichnung in diesem Dokument

- **BESTÄTIGT** — wörtlich oder sinngemäß aus deiner Nachricht vom 2026-08-06.
- **ABGELEITET — BITTE PRÜFEN** — von mir aus bereits bestätigten Regeln oder
  aus Doc 10/02/04 formalisiert, aber in dieser expliziten Form noch nicht von
  dir gegengezeichnet. Das betrifft in dieser Vorlage ausschließlich die
  Fensterinterpretation der Kandidatenregel (Abschnitt 3).

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
Indikatorwert, die für die Auswertung eines Signals oder des Fünf-Kerzen-
Fensters (Abschnitt 3) benötigt werden — fehlt auch nur einer davon, erhält
die *gesamte* Aktienprüfung für diesen Lauf den Status
`UNKNOWN_DATA_INCOMPLETE`, nicht nur das einzelne betroffene Signal.

---

## 2. Die drei Signale — vollständige Formeln und Pseudocode

### 2.1 Signal A — RSI kreuzt RSI-Moving-Average von unten nach oben

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

## 3. Die 2-aus-3-Kandidatenregel und das Fünf-Kerzen-Fenster

### 3.1 Ausgangslage

Bereits konfiguriert (`config/default.yaml`, Abschnitt `screening`):

```yaml
required_signal_count: 2
lookback_closed_candles: 5
```

Wortlaut Doc 10, Paragraph 6.4: „mindestens zwei der drei Signale erfüllt
sind, die betreffenden Signale in der aktuellen oder einer der vorherigen
fünf abgeschlossenen 195-Minuten-Kerzen aufgetreten sind." Diese Formulierung
legt zwei Dinge **nicht** explizit fest, die für eine testbare Implementierung
nötig sind — beide werden hier zur Prüfung formalisiert.

### 3.2 Fensterdefinition — ABGELEITET, BITTE PRÜFEN

**Vorgeschlagene Interpretation:** Das Fenster umfasst **6 Kerzen** —
die aktuelle (gerade abgeschlossene) Kerze **plus** die fünf unmittelbar
vorangegangenen abgeschlossenen Kerzen:

```text
Fenster = { t, t-1, t-2, t-3, t-4, t-5 }
```

Begründung: „aktuell **oder** innerhalb der letzten fünf abgeschlossenen
Kerzen" beschreibt zwei sich ergänzende, nicht überlappende Fundorte — die
aktuelle Kerze zählt als eigener Fall neben den fünf vorherigen, nicht als
Teil davon. Das entspricht auch dem Konfigurationsnamen
`lookback_closed_candles: 5` (5 zusätzliche Kerzen *zurückblickend*, zusätzlich
zur aktuellen).

**Alternative Lesart, falls das nicht gemeint ist:** Fenster = 5 Kerzen
insgesamt (`{t, t-1, t-2, t-3, t-4}`), wobei „aktuell" als eine der „fünf"
mitgezählt wird. Falls diese Lesart zutrifft, bitte hier ausdrücklich
korrigieren.

### 3.3 Unabhängigkeit der drei Signaltypen innerhalb des Fensters — ABGELEITET, BITTE PRÜFEN

**Vorgeschlagene Interpretation:** Jeder der drei Signaltypen (A, B, C) wird
**unabhängig** für jede Kerze im Fenster ausgewertet. Ein Signaltyp gilt als
„aufgetreten", wenn er auf **mindestens einer beliebigen** Kerze im Fenster
erfüllt war — nicht notwendigerweise auf derselben Kerze wie ein anderer
Signaltyp. Beispiel: Signal A tritt auf Kerze `t-4` auf, Signal C auf Kerze
`t-1` — das zählt als zwei erfüllte Signaltypen im Fenster, obwohl sie nicht
gemeinsam auf einer Kerze auftraten.

**Alternative Lesart:** Mindestens zwei Signaltypen müssen auf **derselben**
Kerze innerhalb des Fensters gemeinsam erfüllt sein. Falls das gemeint ist,
bitte hier ausdrücklich korrigieren.

### 3.4 Pseudocode

```python
def evaluate_candidate(stock, t, config):
    """Kandidatenpruefung fuer eine Aktie am Tag der Kerze t."""

    # 1. Warm-up (Abschnitt 1.3)
    if not has_full_history(stock, t, minimum_candles=config.warmup_candles):
        return Result(status="UNKNOWN_DATA_INCOMPLETE", reason="warmup_insufficient")

    # 2. Fenster bestimmen (Abschnitt 3.2 -- 6 Kerzen: aktuelle + 5 vorherige)
    window = range(t - config.lookback_closed_candles, t + 1)  # t-5 .. t

    # 3. Vollstaendigkeit der Rohdaten und Indikatorwerte im Fenster pruefen
    for i in window:
        if not candle_complete(stock, i) or not indicators_complete(stock, i):
            return Result(
                status="UNKNOWN_DATA_INCOMPLETE",
                reason="missing_candle_or_indicator",
                affected_index=i,
            )

    # 4. Jeden Signaltyp unabhaengig ueber das gesamte Fenster auswerten
    #    (Abschnitt 3.3 -- nicht auf dieselbe Kerze beschraenkt)
    fired = {
        "A": any(signal_a(stock.candles, i) for i in window),
        "B": any(signal_b(stock.candles, i) for i in window),
        "C": any(signal_c(stock.candles, i) for i in window),
    }

    # 5. 2-aus-3-Regel
    if sum(fired.values()) >= config.required_signal_count:
        return Result(status="CANDIDATE", fired_signals=fired)
    return Result(status="NOT_CANDIDATE", fired_signals=fired)
```

**Wichtige Abgrenzung — keine Vermischung mit dem Backtesting-Cooldown:**
Dieser Ablauf gilt für die **tägliche Live-Prüfung** (ein frisches Fenster pro
Handelstag, endend an der gerade abgeschlossenen Kerze). Der bereits
freigegebene Fünf-Kerzen-Cooldown des **Backtestings** (F5) ist ein separates
Konzept — er entzerrt geclusterte Qualifikationen über die 5-Jahres-Historie,
nicht die tägliche Fensterprüfung selbst. Beide verwenden zufällig dieselbe
Zahl (5), sind aber unabhängig voneinander zu implementieren.

### 3.5 Beispiel

| Kerze | Signal A | Signal B | Signal C |
|---|---|---|---|
| t-5 | — | — | — |
| t-4 | ERFÜLLT | — | — |
| t-3 | — | — | — |
| t-2 | — | — | ERFÜLLT |
| t-1 | — | — | — |
| t (aktuell) | — | — | — |

Ergebnis mit der vorgeschlagenen Interpretation (Abschnitt 3.2/3.3): Signal A
trat auf `t-4` auf, Signal C auf `t-2` — zwei von drei Signaltypen im Fenster
erfüllt, unabhängig davon, dass sie auf unterschiedlichen Kerzen auftraten und
keines davon auf der aktuellen Kerze `t` selbst → **CANDIDATE**.

---

## 4. Freigabe-Checkliste

| # | Punkt | Status |
|---|---|---|
| 1 | RSI-Parameter und interne Glättung (Abschnitt 1.2) | BESTÄTIGT |
| 2 | Signal-A-Formel (Abschnitt 2.1) | BESTÄTIGT |
| 3 | Signal-B-Formel, Option 2 (Abschnitt 2.2) | BESTÄTIGT |
| 4 | Signal-C-Formel, Option 1 (Abschnitt 2.3) | BESTÄTIGT |
| 5 | Warm-up = 250 Kerzen (Abschnitt 1.3) | BESTÄTIGT |
| 6 | Rundung / Vergleichspräzision (Abschnitt 1.4) | BESTÄTIGT |
| 7 | Umgang mit fehlenden Daten, `UNKNOWN_DATA_INCOMPLETE` (Abschnitt 1.5) | BESTÄTIGT |
| 8 | Fensterdefinition: 6 Kerzen (aktuelle + 5 vorherige) (Abschnitt 3.2) | **BITTE PRÜFEN** |
| 9 | Signaltypen dürfen auf unterschiedlichen Kerzen im Fenster auftreten (Abschnitt 3.3) | **BITTE PRÜFEN** |

Noch außerhalb dieser Vorlage offen (siehe
[signal-specification.md](signal-specification.md), Abschnitt 1): ob das
5-Jahres-Backtesting alle abgeschlossenen 195-Minuten-Kerzen auswertet oder
nur die erste Tageskerze. Diese Frage berührt nicht die Signalformeln selbst
und blockiert die Implementierung des Screeners nicht zwingend — betrifft aber
das Backtesting-Modul (Sprint 3) und sollte vor dessen Umsetzung geklärt sein.

**Erst wenn die Punkte 8 und 9 ausdrücklich bestätigt oder korrigiert sind,
gilt Gate G1 als vollständig freigegeben.**
