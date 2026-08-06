# ADR 0007: Indikator-Parameter bleiben bis zur fachlichen Freigabe leer

- Status: Abgelöst durch [ADR 0010](0010-gate-g1-freigegeben.md)
- Datum: 2026-08-06

## Kontext

Doc 10 §6.4 verlangt ausdrücklich, dass die exakte Definition der drei
Kaufsignale vor der Implementierung fachlich festgelegt wird und Claude Code
dazu keine eigene Annahme dauerhaft implementieren darf. Offen sind:

- Länge und Berechnungsmethode des RSI,
- Länge und Typ des RSI-Moving-Average,
- die mathematische Definition von „Kurs durchdringt EMA20",
- die Schlussbedingung beim EMA5/EMA20-Crossover.

Diese Werte müssen am tatsächlichen TradingView-Layout des Nutzers geklärt
werden. Das ist Freigabe-Gate **G1**.

Die naheliegende Zwischenlösung — plausible Defaults setzen und später
korrigieren — ist hier besonders gefährlich: Ein RSI mit falscher Glättung
liefert keine Fehlermeldung, sondern leicht abweichende Werte. Signale
verschieben sich um einzelne Kerzen, der Backtest misst eine andere Strategie
als die gehandelte, und niemand bemerkt es, weil alles plausibel aussieht.

## Entscheidung

**Die Konfiguration bleibt an dieser Stelle nachweislich unvollständig, und der
Code macht das sichtbar.**

- `IndicatorConfig` enthält ausschließlich Pflichtfelder **ohne Default**.
- In `AppConfig` ist `indicators` optional und standardmäßig `None`.
- In `config/default.yaml` ist der Abschnitt auskommentiert. Die Platzhalter
  dort lauten `<offen>` — ausdrücklich keine Zahlenwerte, damit sie nicht durch
  Auskommentieren versehentlich aktiv werden.
- Jeder Zugriff läuft über `AppConfig.require_indicators()`. Ohne Freigabe wirft
  die Methode `GateNotClearedError` mit dem Hinweis, dass Gate G1 offen ist und
  keine Annahmen getroffen werden dürfen.

Tests sichern ab, dass `IndicatorConfig` keinerlei Defaults besitzt und die
ausgelieferte `default.yaml` den Abschnitt nicht enthält.

## Begründung

Ein Default wäre eine stillschweigende Annahme mit dem Anschein einer
Entscheidung. Ein `None` mit klarer Fehlermeldung ist eine sichtbare offene
Frage.

Die Alternative — die Felder gar nicht anzulegen — wurde verworfen: Dann wäre
zwar auch nichts geraten, aber es gäbe keinen Ort, an dem die offene
Entscheidung im Code sichtbar wird. So bricht jeder Codepfad, der Indikatoren
berechnen will, an einer benannten Stelle mit einer Begründung ab.

## Konsequenzen

- Der Screener kann bis zur G1-Freigabe nicht fachlich fertiggestellt werden.
  Interfaces, Datenmodelle, Orchestrierung und die von G1 unabhängige
  Kandidatenregel dürfen gebaut werden — der fachliche Screener-Teil gilt
  jedoch ausdrücklich nicht als abgenommen, bis die realen Signalformeln **und**
  die Golden-Master-Referenzen freigegeben sind.
- Nach der Freigabe wird der Abschnitt in `default.yaml` aktiviert und dieses
  ADR durch eines ersetzt, das die festgelegten Parameter dokumentiert.
- Die lokal berechneten Indikatoren müssen zusätzlich gegen echte
  TradingView-Werte validiert werden (Warm-up-Länge, Toleranz) — die reine
  Parameterfreigabe genügt nicht, weil RSI und EMA pfadabhängig sind.
