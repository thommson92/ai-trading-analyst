# ADR 0010: Gate G1 fachlich freigegeben -- Indikator- und Signalparameter

- Status: Angenommen
- Datum: 2026-08-06
- Löst ab: [ADR 0007](0007-gate-g1-indikatorparameter.md)
- Teilweise abgelöst durch [ADR 0056](0056-kaufsignale-und-zusatzkriterien.md)
  (2026-09-02): Die Formel von Signal B und die 2-aus-3-Kandidatenregel
  gelten nicht mehr — es sind fünf Kriterien, von denen drei erfüllt sein
  müssen. Die hier freigegebenen **Indikatorparameter** gelten unverändert
  fort, ebenso das Sechs-Kerzen-Fenster und der Umgang mit fehlenden Daten.

## Kontext

ADR 0007 hielt fest, dass RSI-Länge und -Methode, Länge und Typ des
RSI-Moving-Average, die mathematische Definition des EMA20-Kursdurchbruchs
und die Schlussbedingung des EMA5/EMA20-Crossovers am realen
TradingView-Layout des Nutzers geklärt werden müssen, bevor Signalcode
implementiert wird (Gate G1, Doc 10 Paragraph 6.4).

Diese Klärung ist inzwischen abgeschlossen. Der Nutzer hat die Parameter,
die drei Signalformeln, die 2-aus-3-Kandidatenregel mit dem
Sechs-Kerzen-Fenster, den Umgang mit fehlenden Daten sowie die
Backtesting-Entscheidungszeitpunkte und Performancemessung bestätigt. Die
vollständige, widerspruchsfreie Zusammenfassung steht in
[docs/requirements/g1-pruefvorlage.md](../requirements/g1-pruefvorlage.md);
die Herleitung mit Diskussion und Beispielen in
[docs/requirements/signal-specification.md](../requirements/signal-specification.md).

Der deterministische Signalkern (`backend/src/ai_trading_analyst/domain/screening`)
ist gegen diese Festlegungen implementiert und über
[PR #3](https://github.com/thommson92/TradingViewAnalyzer/pull/3) nach `dev`
gemergt (Sprint 1A, Tag `sprint-1a-baseline`).

## Entscheidung

**Gate G1 gilt als fachlich freigegeben.**

- `config/default.yaml` enthält den zuvor auskommentierten Abschnitt
  `indicators` jetzt mit den bestätigten Werten:

  | Parameter | Wert |
  |---|---|
  | `rsi_length` | 14 |
  | `rsi_method` | `wilder` |
  | `rsi_ma_length` | 14 |
  | `rsi_ma_type` | `sma` |
  | `fast_ema_length` | 5 |
  | `slow_ema_length` | 20 |
  | `warmup_candles` | 250 |

- `AppConfig.require_indicators()` liefert damit für die ausgelieferte
  Konfiguration die Parameter, statt mit `GateNotClearedError` abzubrechen.
  Die Methode selbst bleibt bestehen: Eine Konfiguration, die den Abschnitt
  `indicators` dennoch nicht enthält (etwa eine unvollständige eigene
  Config-Datei), soll weiterhin mit einem eindeutigen Fehler abbrechen statt
  mit fehlenden Parametern zu rechnen.
- Die Signalformeln selbst sind nicht Teil dieses ADRs -- sie sind bereits
  als Code in `domain/screening` vorhanden und ausführlich in
  `g1-pruefvorlage.md` dokumentiert. Dieses ADR hält nur die
  Freigabeentscheidung und den Ort der maßgeblichen fachlichen Dokumente
  fest.

## Begründung

ADR 0007 sah genau diesen Schritt als Konsequenz einer Freigabe vor: „Nach
der Freigabe wird der Abschnitt in `default.yaml` aktiviert und dieses ADR
durch eines ersetzt, das die festgelegten Parameter dokumentiert." Ein neues
ADR statt einer rückwirkenden Änderung des alten, weil ADRs nicht im
Nachhinein umgeschrieben werden (siehe `docs/adr/README.md`).

## Konsequenzen

- Der Screener kann ab sofort fachlich vollständig weiterentwickelt werden
  (Sprint 1B ff.) -- die vormals blockierten Signalformeln sind bereits
  implementiert.
- Weiterhin offen und nicht Teil dieser Freigabe: Validierung der lokal
  berechneten Indikatoren gegen echte TradingView-Werte (Warm-up-Länge,
  Toleranz), da RSI und EMA pfadabhängig sind. Diese Validierung ist Teil des
  TradingView-Spikes (Gate G2) beziehungsweise der Indikator-Engine
  (ursprünglicher Plan, Sprint 2) und wird dort gesondert nachgewiesen.
- `docs/10 - System Architecture.md` referenziert an einer Stelle noch den
  alten Konfigurationsnamen `lookback_closed_candles` (jetzt
  `signal_lookback_previous_candles`, siehe `g1-pruefvorlage.md`
  Abschnitt 3.2). Doc 10 wird nicht rückwirkend redigiert (ADR 0001); die
  maßgebliche, aktuelle Bezeichnung steht in `g1-pruefvorlage.md` und im Code.
