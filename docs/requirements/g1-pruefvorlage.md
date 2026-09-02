# G1-Prüfvorlage — konsolidierte Signal- und Kandidatenlogik

- Status: **Gate G1 fachlich freigegeben** (2026-08-06, siehe
  [ADR 0010](../adr/0010-gate-g1-freigegeben.md)).
- Zweck: Diese Datei ist die einzige, vollständige und in sich geschlossene
  Grundlage, gegen die der Screener und das Backtesting-Modul implementiert
  werden (Doc 10, Paragraph 6.4).
- Herkunft: konsolidiert aus [signal-specification.md](signal-specification.md)
  (dort mit Diskussion, Optionen und Herleitung) und den Festlegungen aus
  deinen Nachrichten vom 2026-08-06.
- **Am 2026-09-02 auf fünf Kriterien fortgeschrieben**
  ([ADR 0056](../adr/0056-kaufsignale-und-zusatzkriterien.md)): Signal B verliert
  die Gap-up-Klausel, `RSI_OVERSOLD` und `NO_RECENT_EMA_DOWNCROSS` kommen
  hinzu, und zu den zwei geforderten Kaufsignalen tritt mindestens eines
  der beiden Zusatzkriterien. Die zugehörige Regelversion
  ist `g1-pruefvorlage-2026-09-02`; die Indikatorparameter aus Gate G1
  gelten unverändert fort.
- **Die Signalformeln und die Kandidatenregel sind implementiert**
  (`backend/src/ai_trading_analyst/domain/screening`, Sprint 1A, Tag
  `sprint-1a-baseline`). Die Backtesting-Regeln aus Abschnitt 4 sind weiterhin
  unimplementiert und bleiben bis Sprint 3 verbindliche Grundlage.
- **Die Indikatorberechnung ist am 2026-08-12 gegen das reale
  TradingView-Layout bestätigt** (Sprint 2): Für AAPL stimmten Schlusskurs,
  RSI, RSI-MA, EMA5 und EMA20 der 195-Minuten-Kerze vom 2026-08-11, 12:45 ET
  — berechnet aus 15-Minuten-Bars von Interactive Brokers — mit den im Chart
  abgelesenen Werten überein. Damit ist Abschnitt 1.2 („reproduziert
  TradingViews RSI-Berechnung") nicht nur gegen selbst gerechnete
  Referenzfälle, sondern gegen die Anzeige geprüft, auf die sich die
  Freigabe bezieht. Nachvollziehbar mit
  `python -m ai_trading_analyst.cli screen --provider ibkr --symbols AAPL --details`.

## Kennzeichnung in diesem Dokument

Jede Regel trägt **BESTÄTIGT** und das Datum ihrer Bestätigung. Wo eine Regel
von mir formalisiert wurde (z. B. Pseudocode, Datenstruktur-Skizzen), ist sie
als **Formalisierung von** der jeweiligen fachlichen Festlegung gekennzeichnet
— inhaltlich nichts Neues, nur die technische Ausformulierung einer bereits
bestätigten Regel.

---

## 1. Gemeinsame Grundlagen

### 1.1 Eingangsdaten

Alle fünf Kriterien arbeiten ausschließlich auf **vollständig geschlossenen
195-Minuten-Kerzen der regulären US-Sitzung** (keine Extended Hours). Jede
Kerze liefert Open, High, Low, Close, Volume; die Auswertung verwendet
ausschließlich **Close** — sowohl als Preisquelle für die
Indikatorberechnung als auch als einzigen unmittelbar verglichenen Kurswert.
Open, High und Low gehen seit
[ADR 0056](../adr/0056-kaufsignale-und-zusatzkriterien.md) in kein Kriterium mehr
ein (zuvor Open bei Signal B).

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

## 2. Die fünf Kriterien — vollständige Formeln und Pseudocode

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

### 2.2 Signal B — Kurs kreuzt EMA20 von unten nach oben

`signal_type: PRICE_EMA20_BREAKOUT` (Doc 05)

**Geändert am 2026-09-02 durch [ADR 0056](../adr/0056-kaufsignale-und-zusatzkriterien.md):**
Die frühere Zusatzbedingung `open[t] <= EMA20[t]` ist entfallen. Maßgeblich
ist das Bild des Projektinhabers
([Kaufsignale_EMA.png](../trading_signals/Kaufsignale_EMA.png), Kaufsignal 2):
„Kerze (Preis) schneidet den EMA 20 von unten nach oben und schließt
darüber." Bezugspunkt der Kreuzung ist damit der Schlusskurs der Vorkerze,
nicht die Eröffnung der aktuellen Kerze.

**Formel:**

```text
close[t-1] <= EMA20[t-1]   UND   close[t] > EMA20[t]
```

Ein Gap-up über den EMA 20 erfüllt das Signal, sofern die Vorkerze auf oder
unter dem EMA 20 geschlossen hat. Eine reine Docht-Berührung ohne
Schlusskurs oberhalb reicht weiterhin nicht aus.

**Pseudocode:**

```python
def signal_b(candles, t):
    """Schlusskurs kreuzt EMA20 von unten nach oben."""
    close_prev, ema20_prev = candles.close[t - 1], candles.ema20[t - 1]
    close_curr, ema20_curr = candles.close[t], candles.ema20[t]

    if any(v is None for v in (close_prev, ema20_prev, close_curr, ema20_curr)):
        raise DataIncomplete(candle_index=t, required=["CLOSE", "EMA20"])

    return close_prev <= ema20_prev and close_curr > ema20_curr
```

**Beispiele:**

| # | close[t-1] | EMA20[t-1] | open[t] | close[t] | EMA20[t] | Ergebnis | Begründung |
|---|---|---|---|---|---|---|---|
| B1 | 99,20 | 100,00 | 99,80 | 100,60 | 100,20 | ERFÜLLT | `99,20<=100,00` und `100,60>100,20` |
| B2 | 100,00 | 100,00 | 100,00 | 100,05 | 100,00 | ERFÜLLT | Gleichheit auf t-1 zulässig |
| B3 | 98,50 | 100,00 | 100,20 | 100,21 | 100,20 | ERFÜLLT | Knapper, aber echter Übertritt |
| B4 | 99,20 | 100,00 | 101,80 | 100,60 | 100,20 | ERFÜLLT | Gap-up zählt seit ADR 0056; `open[t]` ist ohne Wirkung |
| B5 | 99,20 | 100,00 | 99,80 | 100,20 | 100,20 | NICHT ERFÜLLT | `close[t]==EMA20[t]` — keine strikte Überschreitung |
| B6 | 100,50 | 100,00 | 99,80 | 100,60 | 100,20 | NICHT ERFÜLLT | bereits vor der Kerze oberhalb — kein Kreuzen von unten |

Die Spalte `open[t]` bleibt in der Tabelle stehen, damit der Vergleich mit
der früheren Fassung möglich ist; sie geht nicht mehr in die Auswertung ein.

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

### 2.4 Signal D — RSI im überverkauften Bereich

`signal_type: RSI_OVERSOLD` — **neu am 2026-09-02**
([ADR 0056](../adr/0056-kaufsignale-und-zusatzkriterien.md))

**Formel:**

```text
RSI[t] < 30
```

Das einzige Kriterium ohne Bezug auf eine Vorkerze: Es beschreibt einen
Zustand, keinen Übergang. Die Schwelle ist strikt — `RSI == 30` erfüllt das
Kriterium nicht, dieselbe Konvention wie bei den Kreuzungen in Abschnitt 1.4.

Ausgewertet wird es dennoch wie A bis C **über das gesamte
Sechs-Kerzen-Fenster** (Abschnitt 3.3): Erfüllt ist es, sobald *eine*
Fensterkerze darunter liegt. Gefragt ist, ob der Titel im Fenster
überverkauft **war** — dreht der RSI aus dem überverkauften Bereich nach oben
(Signal A), soll die Erholung das Kriterium nicht wieder entwerten.

**Pseudocode:**

```python
def signal_d(candles, t):
    """RSI(14, Wilder) liegt unter 30 -- ueberverkaufter Zustand."""
    rsi_curr = candles.rsi[t]

    if rsi_curr is None:
        raise DataIncomplete(candle_index=t, required=["RSI"])

    return rsi_curr < 30.0
```

**Beispiele:**

| # | RSI[t] | Ergebnis | Begründung |
|---|---|---|---|
| D1 | 22,4 | ERFÜLLT | deutlich überverkauft |
| D2 | 29,99 | ERFÜLLT | knapp, aber unter der Schwelle |
| D3 | 30,00 | NICHT ERFÜLLT | Gleichheit genügt nicht — strikte Unterschreitung gefordert |
| D4 | 30,01 | NICHT ERFÜLLT | knapp darüber |
| D5 | 47,0 | NICHT ERFÜLLT | neutral |
| D6 | `None` | `DataIncomplete` | fehlender Wert ist kein negatives Signal (Abschnitt 1.5) |

### 2.5 Signal E — kein frisches Abwärtskreuz von EMA5 durch EMA20

`signal_type: NO_RECENT_EMA_DOWNCROSS` — **neu am 2026-09-02**
([ADR 0056](../adr/0056-kaufsignale-und-zusatzkriterien.md))

**Formel:**

```text
für kein i aus {t-4, t-3, t-2, t-1, t} gilt:
    EMA5[i-1] >= EMA20[i-1]   UND   EMA5[i] < EMA20[i]
```

Das einzige **Ausschlusskriterium**: Es ist erfüllt, wenn etwas *nicht*
stattgefunden hat. Hat der EMA 5 den EMA 20 kurz zuvor nach unten geschnitten,
ist der anschließende Schnitt nach oben Gezappel um die Linie und kein
Trendwechsel.

Die Abwärtskreuzung ist die exakte Spiegelung von Signal C: Gleichheit ist
auf der Vorkerze zulässig (`>=`), die Unterschreitung auf der aktuellen Kerze
muss strikt sein (`<`).

**Ausgewertet wird E genau einmal, an der Entscheidungskerze `t`** — anders
als A bis D, die über das Fenster laufen (Abschnitt 3.3). Über das Fenster
geodert wäre es sinnlos: „In irgendeinem der sechs Fünf-Kerzen-Fenster gab es
kein Abwärtskreuz" ist fast immer wahr. Geprüft werden fünf
Kreuzungspositionen (`t-4` bis `t`); berührt werden dadurch die Kerzen `t-5`
bis `t`, die alle innerhalb des ohnehin auf Vollständigkeit geprüften
Bereichs liegen (Abschnitt 3.2).

**Pseudocode:**

```python
def signal_e(candles, t):
    """Kein Abwaertskreuz EMA5/EMA20 in den letzten fuenf Kerzen."""
    for i in range(t - 4, t + 1):
        ema5_prev, ema20_prev = candles.ema5[i - 1], candles.ema20[i - 1]
        ema5_curr, ema20_curr = candles.ema5[i], candles.ema20[i]

        if any(v is None for v in (ema5_prev, ema20_prev, ema5_curr, ema20_curr)):
            raise DataIncomplete(candle_index=i, required=["EMA5", "EMA20"])

        if ema5_prev >= ema20_prev and ema5_curr < ema20_curr:
            return False

    return True
```

**Beispiele** (jeweils die Lage im Prüfbereich `t-4 … t`):

| # | Lage | Ergebnis | Begründung |
|---|---|---|---|
| E1 | EMA5 durchgehend über EMA20 | ERFÜLLT | kein Kreuzen in irgendeine Richtung |
| E2 | EMA5 durchgehend unter EMA20 | ERFÜLLT | dauerhaft darunter ist kein *frisches* Abwärtskreuz |
| E3 | Aufwärtskreuz bei `t-2` | ERFÜLLT | falsche Richtung — nur Abwärtskreuze schließen aus |
| E4 | Abwärtskreuz bei `t-4` | NICHT ERFÜLLT | älteste geprüfte Position, liegt noch im Bereich |
| E5 | Abwärtskreuz bei `t` | NICHT ERFÜLLT | die Entscheidungskerze zählt mit |
| E6 | Abwärtskreuz bei `t-5` | ERFÜLLT | eine Position vor dem Prüfbereich |
| E7 | `EMA5[i-1] == EMA20[i-1]` und `EMA5[i] == EMA20[i]` | ERFÜLLT | keine strikte Unterschreitung — kein Kreuzen |
| E8 | EMA-Wert bei `t-5` fehlt | `DataIncomplete` | gemeldet wird die **Kreuzungsposition** `t-4`, deren Vorkerze fehlt — nicht der Index des fehlenden Wertes (Abschnitt 1.5) |

---

## 3. Die Kandidatenregel und das Sechs-Kerzen-Fenster

### 3.1 Ausgangslage

Bereits konfiguriert (`config/default.yaml`, Abschnitt `screening`):

```yaml
required_crossing_signals: 2
lookback_closed_candles: 5   # wird umbenannt, siehe Abschnitt 3.2
```

Wortlaut Doc 10, Paragraph 6.4: „mindestens zwei der drei Signale erfüllt
sind, die betreffenden Signale in der aktuellen oder einer der vorherigen
fünf abgeschlossenen 195-Minuten-Kerzen aufgetreten sind." Diese Formulierung
ließ zwei Dinge offen, die für eine testbare Implementierung nötig sind —
beide sind jetzt bestätigt (Abschnitt 3.2, 3.3).

**Geändert am 2026-09-02 durch [ADR 0056](../adr/0056-kaufsignale-und-zusatzkriterien.md):**
Die geforderten zwei Signale beziehen sich jetzt ausdrücklich auf die drei
**Kaufsignale** (A, B, C); der Konfigurationsschlüssel heißt deshalb
`required_crossing_signals`. Hinzu kommt eine zweite Bedingung: **mindestens
eines der beiden Zusatzkriterien** (D, E) muss erfüllt sein. Beide Bedingungen
gelten gemeinsam; die Regel ist damit strikt schärfer als zuvor. Das
Sechs-Kerzen-Fenster und die Zählung pro Signaltyp bleiben unverändert.

Ausdrücklich **nicht** gewählt wurde „drei von fünf" mit gleichrangigen
Kriterien: Gemessen am Golden Master ließ diese Variante *mehr* Titel durch
als die frühere Regel, weil D und E zusammen ein zweites Kaufsignal ersetzten
(Begründung in ADR 0056, Abschnitt 3).

### 3.2 Fensterdefinition — BESTÄTIGT

Das Fenster umfasst **sechs vollständig abgeschlossene 195-Minuten-Kerzen**:
die aktuell betrachtete Kerze `t` sowie die fünf unmittelbar vorherigen Kerzen
`t-1` bis `t-5`. Die aktuelle Kerze wird **zusätzlich und immer** einbezogen —
„aktuell oder innerhalb der letzten fünf abgeschlossenen Kerzen" ist wörtlich
zu verstehen: current candle + 5 previous candles = 6 candles total.

```text
Fenster = { t, t-1, t-2, t-3, t-4, t-5 }
```

**Namensklärung (Umsetzungshinweis, kein fachlicher Punkt):** Der frühere
Konfigurationsname `lookback_closed_candles` war mehrdeutig — er könnte als
„Gesamtgröße des Fensters" oder als „Anzahl der Kerzen vor der aktuellen"
gelesen werden. Er wurde in `signal_lookback_previous_candles: 5` umbenannt,
um eindeutig auszudrücken: fünf *zusätzliche, vorherige* Kerzen, die aktuelle
Kerze kommt immer und unabhängig davon hinzu. Umgesetzt in
`backend/src/ai_trading_analyst/config/settings.py` und
`config/default.yaml` (Sprint 1A, Tag `sprint-1a-baseline`).

### 3.3 Zeitliche Verteilung und Zählung der Signaltypen — BESTÄTIGT

Die erforderlichen Signaltypen müssen **nicht auf derselben Kerze**
auftreten. Eine Aktie qualifiziert sich, wenn mindestens zwei verschiedene
**Kaufsignale** innerhalb des Sechs-Kerzen-Fensters erfüllt sind — unabhängig
davon, auf welcher der sechs Kerzen jeweils — und zusätzlich mindestens eines
der beiden **Zusatzkriterien**.

Beispiel: RSI-Crossover (`RSI_CROSS`) auf `t-4`, Kursdurchbruch durch EMA20
(`PRICE_EMA20_BREAKOUT`) auf `t-1`, kein EMA5-/EMA20-Crossover
(`EMA5_EMA20_CROSS`) im gesamten Fenster, dazu ein erfülltes
`NO_RECENT_EMA_DOWNCROSS` → zwei Kaufsignale und ein Zusatzkriterium, die
Regel ist erfüllt.

**Zwei Klassen von Kriterien** (seit
[ADR 0056](../adr/0056-kaufsignale-und-zusatzkriterien.md)):

- **Ereigniskriterien A bis D** werden für jede Kerze des Fensters geprüft
  und gelten als erfüllt, sobald sie an einer davon zutreffen.
- **Das Ausschlusskriterium E** wird **genau einmal** ausgewertet, an der
  Entscheidungskerze `t` (Begründung in Abschnitt 2.5). Es ist damit das
  einzige Kriterium, dessen Erfülltsein nicht an einer Fensterposition hängt;
  sein Signalereignis wird auf `t` festgeschrieben.

**Zählung pro Signaltyp, nicht pro Signalereignis:** Jeder Signaltyp zählt
innerhalb eines Entscheidungsfensters **höchstens einmal**, auch wenn derselbe
Signaltyp mehrfach im Fenster auftritt (z. B. `RSI_CROSS` sowohl auf `t-4` als
auch erneut auf `t-2`). Beide Bedingungen der Regel werden aus der Menge der
**unterschiedlichen** erfüllten Signaltypen gebildet, nicht aus der Anzahl
einzelner Signalereignisse.

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

    # 4. Ereigniskriterien unabhaengig ueber das gesamte Fenster auswerten
    #    (Abschnitt 3.3 -- nicht auf dieselbe Kerze beschraenkt; jeder Typ
    #    zaehlt hoechstens einmal, auch bei mehrfachem Auftreten im Fenster)
    fired = {
        "RSI_CROSS": any(signal_a(stock.candles, i) for i in window),
        "PRICE_EMA20_BREAKOUT": any(signal_b(stock.candles, i) for i in window),
        "EMA5_EMA20_CROSS": any(signal_c(stock.candles, i) for i in window),
        "RSI_OVERSOLD": any(signal_d(stock.candles, i) for i in window),
    }

    # 5. Ausschlusskriterium genau einmal an der Entscheidungskerze auswerten
    #    (Abschnitt 2.5 -- ueber das Fenster geodert waere es sinnlos)
    fired["NO_RECENT_EMA_DOWNCROSS"] = signal_e(stock.candles, t)

    # 6. Beide Bedingungen der Kandidatenregel -- unterschiedliche
    #    Signaltypen, nicht einzelne Signalereignisse
    kaufsignale = {typ for typ in fired if fired[typ] and typ in CROSSING_SIGNALS}
    zusatzkriterien = {typ for typ in fired if fired[typ] and typ in CONFIRMATION_SIGNALS}

    if len(kaufsignale) >= config.required_crossing_signals and zusatzkriterien:
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

Fortgeschrieben auf das Fünf-Kriterien-Regelwerk:

| Kerze | RSI_CROSS | PRICE_EMA20_BREAKOUT | EMA5_EMA20_CROSS | RSI_OVERSOLD |
|---|---|---|---|---|
| t-5 | — | — | — | ERFÜLLT |
| t-4 | ERFÜLLT | — | — | — |
| t-3 | — | — | — | — |
| t-2 | — | — | — | — |
| t-1 | — | ERFÜLLT | — | — |
| t (aktuell) | — | — | — | — |

`NO_RECENT_EMA_DOWNCROSS` wird nicht je Kerze geführt, sondern einmal an `t`
ausgewertet: Im Bereich `t-4 … t` gibt es kein Abwärtskreuz → ERFÜLLT.

Ergebnis: `RSI_CROSS` auf `t-4`, `PRICE_EMA20_BREAKOUT` auf `t-1`,
`RSI_OVERSOLD` auf `t-5`, dazu `NO_RECENT_EMA_DOWNCROSS` an `t` — **vier von
fünf** Signaltypen erfüllt, unabhängig davon, dass sie auf unterschiedlichen
Kerzen auftraten und keines der Ereigniskriterien auf der aktuellen Kerze `t`
selbst → **CANDIDATE**.

Ohne `RSI_OVERSOLD` wären es drei Typen — ebenfalls CANDIDATE, aber genau an
der Schwelle. Fiele zusätzlich `NO_RECENT_EMA_DOWNCROSS` weg (also ein
frisches Abwärtskreuz im Bereich `t-4 … t`), blieben zwei Typen →
**NOT_CANDIDATE**.

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
Qualifizierend ist **jede Teilmenge, welche die Kandidatenregel erfüllt** —
die erzeugende Regel, nicht eine gepflegte Liste: vier
Kaufsignal-Kombinationen (die drei Paare und das Tripel) mal drei
Kombinationen der Zusatzkriterien (nur D, nur E, beide), zusammen **12**. Die
Menge folgt der Regel; wird die Schwelle geändert, ändert sie sich mit, ohne
dass hier etwas nachgetragen werden müsste.

Der Backtest weist seine Kennzahlen je Kombination und Horizont aus. Bei 12
statt zuvor 4 Kombinationen verteilen sich die historischen Ereignisse auf
mehr Gruppen; dünne Stichproben werden über `BacktestConfidence` als solche
ausgewiesen und nicht durch Zusammenlegen kaschiert
([ADR 0056](../adr/0056-kaufsignale-und-zusatzkriterien.md)).

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
| 13 | Signal-B-Formel ohne Gap-up-Klausel (Abschnitt 2.2) | BESTÄTIGT 2026-09-02 |
| 14 | Signal-D-Formel — `RSI_OVERSOLD`, Schwelle 30, Fensterauswertung (Abschnitt 2.4) | BESTÄTIGT 2026-09-02 |
| 15 | Signal-E-Formel — `NO_RECENT_EMA_DOWNCROSS`, Bereich `t-4 … t`, Auswertung an `t` (Abschnitt 2.5) | BESTÄTIGT 2026-09-02 |
| 16 | Kandidatenregel: zwei Kaufsignale **und** ein Zusatzkriterium (Abschnitt 3.1) | BESTÄTIGT 2026-09-02 |

Die Umbenennung von `lookback_closed_candles` zu
`signal_lookback_previous_candles` (Abschnitt 3.2) ist umgesetzt.

**Alle sechzehn fachlichen Punkte sind bestätigt.** Die Punkte 1 bis 12
stammen aus der Freigabe von Gate G1
([ADR 0010](../adr/0010-gate-g1-freigegeben.md), 2026-08-06); die Punkte 13
bis 16 aus der Überarbeitung des Regelwerks
([ADR 0056](../adr/0056-kaufsignale-und-zusatzkriterien.md), 2026-09-02).
