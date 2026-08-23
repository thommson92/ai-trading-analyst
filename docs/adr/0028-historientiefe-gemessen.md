# ADR 0028: Historientiefe gemessen — Anspruch bestätigt, Tiefen-Backfill beschlossen

- Status: Angenommen
- Datum: 2026-08-23

## Kontext

[ADR 0027](0027-historientiefe-messen-vor-anspruch.md) hat Weg (a) aus E2
beschlossen und die Messung zur Voraussetzung gemacht: erst feststellen, wie
weit IBKR die Historie in 15-Minuten-Auflösung hergibt, dann über den Anspruch
entscheiden. Dieses ADR hält das Messergebnis fest und zieht die Folgerungen.

## Das Messergebnis

Gemessen am 2026-08-23 auf dem Windows-Server gegen die produktive TWS, mit
`cli history-depth --provider ibkr --symbols AAPL,MSFT,KO`. Bar-Größe 15
Minuten, nur reguläre Handelszeiten, zwölf Fenster zu je `365 D`,
11 Sekunden Abstand.

| Symbol | ältester Bar | Tage | Jahre | Grenze |
|---|---|---|---|---|
| AAPL | 2009-03-25 | 6360 | 17,4 | `window_limit` |
| MSFT | 2009-03-25 | 6360 | 17,4 | `window_limit` |
| KO | 2009-03-25 | 6360 | 17,4 | `window_limit` |

Empfangen wurden 113.460 / 113.455 / 113.448 Bars. Laufzeit rund 30 Minuten,
keine Pacing-Verletzung.

**Alle drei Titel endeten an der Reißleine, nicht an IBKRs Historie.** Die
17,4 Jahre sind damit eine **Untergrenze**; wo der Anbieter tatsächlich
aufhört, ist unbekannt und wird bewusst nicht gesucht — für die Entscheidung
ist es ohne Belang.

### Nebenbefund: `365 D` zählt Handelstage, nicht Kalendertage

Dass drei verschiedene Aktien exakt beim selben Datum stehen, ist kein
Zufall, sondern die Bestätigung des Rechenwegs: Alle drei liefen dieselbe
Zahl von *Handelstagen* zurück.

| | |
|---|---|
| Bars je Fenster | 113.460 ÷ 12 = 9.455 |
| bei 26 Bars je Handelstag (390 min ÷ 15) | **364 Handelstage** |
| tatsächlich abgedeckt | 6.360 ÷ 12 ≈ **530 Kalendertage** |

Ein Fenster `365 D` deckt bei Intraday-Bars also rund **1,45 Kalenderjahre**
ab. Die [offizielle Dokumentation](https://interactivebrokers.github.io/tws-api/historical_limitations.html)
sagt dazu nichts; der Befund ist gemessen, nicht nachgelesen, und deshalb
hier festgehalten.

## Entscheidung

### 1. `backtesting.history_years: 5` bleibt — jetzt belegt

Der Wert wird **nicht** gesenkt. Er war bisher eine aus Doc 02 und Doc 07
übernommene Erwartung; er ist jetzt eine gemessene Zusage mit dreifachem
Abstand. Weg (b) aus E2 (Anspruch senken) ist damit erledigt.

Damit verschiebt sich Risiko **R1** aus dem Audit: Nicht der Anspruch war
falsch, sondern `market_data.ibkr.history_duration: 1 Y` holt zu wenig. Die
Konfiguration bleibt dort unverändert — sie steuert den *täglichen* Lauf, für
den ein Jahr mit großem Abstand genügt (Warm-up: 250 Kerzen = 125
Handelstage). Die Tiefe kommt aus einem eigenen, einmaligen Batch.

### 2. Der Tiefen-Backfill wird gebaut

Der Batch aus [ADR 0014](0014-ibkr-produktivintegration-freigegeben.md) (E3),
seit jeher vorgesehen und nie umgesetzt. Umgesetzt als
`cli deepen-history` (`application/deepen_history.py`).

Er läuft **entgegengesetzt** zum täglichen Backfill, und das ist der
entscheidende Zuschnitt:

| | täglicher Backfill | Tiefen-Backfill |
|---|---|---|
| Frage | Was fehlt *seit* dem letzten Lauf? | Wie weit reicht es *zurück*? |
| Ansatzpunkt | `latest_start` | `earliest_start` |
| Richtung | vorwärts bis heute | rückwärts in die Vergangenheit |
| Häufigkeit | jeden Handelstag | einmalig |

Dafür kommt `IntradayBarRepository.earliest_start` hinzu. Beide Jobs
schreiben in denselben Bestand und kommen sich nicht ins Gehege: Der eine
verlängert ihn nach vorn, der andere nach hinten.

### 3. Fortsetzbarkeit vor Geschwindigkeit

Jedes Fenster wird **sofort** abgelegt, nicht erst am Ende des Symbols oder
des Laufs. Weil der Ansatzpunkt der älteste gespeicherte Bar ist, wandert er
mit jedem geschriebenen Fenster weiter zurück — ein abgebrochener Lauf setzt
beim nächsten Start ohne Zutun genau dort wieder an.

Das ist bei diesem Job keine Bequemlichkeit. Der Lauf über die volle
Watchlist dauert Stunden und überschneidet sich absehbar mit dem nächtlichen
TWS-Neustart ([ADR 0018](0018-kein-windows-autologon.md): kein Autologon).
Ohne Fortsetzbarkeit wäre er praktisch nicht durchführbar.

Ein zweiter Lauf über einen bereits tiefen Bestand kostet **keine einzige
Anfrage**: Er sieht am `earliest_start`, dass nichts zu tun ist
(`already_deep_enough`).

### 4. Fensterzahl wird in Handelstagen gerechnet

Aus Befund 1 folgt: `history_years` × 252 Handelstage ÷ 365 Handelstage je
Fenster, aufgerundet, plus **ein Sicherheitsfenster**. Für fünf Jahre sind
das fünf Fenster je Aktie.

Das Sicherheitsfenster fängt Feiertage, Handelsunterbrechungen und den
Rundungsrest zwischen Kalender- und Handelstagen. Es kostet je Aktie eine
Anfrage; ein um Wochen verfehlter Anspruch kostete einen zweiten Lauf über
die ganze Watchlist.

### 5. Unter dem Ziel bleiben ist erlaubt, aber nie stillschweigend

Erreicht eine Aktie die Zieltiefe nicht, ist das **kein Fehler**: Eine
Neuemission hat keine fünfjährige Historie. Der Bericht führt solche Titel
aber einzeln auf, mit erreichter Tiefe und Grund — sie verschwinden nicht in
einer Gesamtzahl. Ihre Kennzahlen tragen ohnehin ihren tatsächlichen
`history_start` am Ergebnis.

## Begründung

Die Messung hat die Frage beantwortet, für die sie gebaut wurde, und zwar
eindeutig genug, dass keine zweite nötig ist. Dass sie an der eigenen
Reißleine endete statt an IBKRs Grenze, ist dabei kein Mangel: Gesucht war
„reichen fünf Jahre", nicht „wo ist Schluss".

Den Tiefen-Backfill als eigenen Job statt als Schalter am täglichen: Die
beiden beantworten verschiedene Fragen an verschiedenen Ansatzpunkten in
verschiedene Richtungen. Ein gemeinsames Kommando müsste beides in einer
Schleife unterbringen und hätte zwei Abbruchbedingungen, von denen je eine
tot wäre.

## Konsequenzen

- **Risiko R1 ist damit noch nicht behoben, aber eingegrenzt.** Bis der Batch
  auf dem Server gelaufen ist, stehen die Backtest-Kennzahlen weiterhin auf
  rund einem Jahr. Neu ist, dass der Weg dahin feststeht und belegt ist.
- Der Lauf über die volle Watchlist kostet rund 190 × 5 = **950 Anfragen**.
  Bei 11 Sekunden Abstand und gemessenen ~30 Sekunden Übertragung je Fenster
  sind das etwa **elf Stunden** — ein Wochenendlauf. Er ist abbrechbar und
  fortsetzbar; das ist die Antwort darauf, nicht eine Beschleunigung.
- Der Bestand wächst erheblich: knapp 33.000 Bars je Aktie für fünf Jahre,
  bei 190 Symbolen rund 6,3 Millionen Zeilen. Für PostgreSQL unkritisch, aber
  kein Nebenaspekt beim Sichern.
- **Splits.** Fünf Jahre AAPL enthalten den Split von 2020 (4:1). IBKR liefert
  `TRADES` split-bereinigt, und der Bestand wird in einem Zug geholt — für
  diesen Lauf ist das folgenlos. Würde später ein Zeitraum nachgeholt, der
  vor einem inzwischen erfolgten Split liegt, säßen zwei Preisniveaus in
  derselben Reihe. Die Ablage lässt vorhandene Bars bewusst unverändert, kann
  das also nicht von sich aus heilen. Sollte ein Split einen bereits geholten
  Zeitraum betreffen, sind die Bars der Aktie zu löschen und neu zu holen —
  ein Fall für ein eigenes ADR, sobald er eintritt.
- E1 (Backtesting im Tageslauf) und E3 (historische Earnings-Termine) waren
  laut Audit an E2 aufgehängt. Sie sind damit **nicht** entschieden, aber
  nicht länger blockiert.
- `cli history-depth` bleibt als Betriebswerkzeug bestehen. Die Tiefe eines
  Anbieters ist nichts, was einmal feststeht.
