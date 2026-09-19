# ADR 0066: Signalereignisse tragen den Kerzenzeitpunkt, Läufe ihre Verarbeitungsfehler

- Status: Angenommen
- Datum: 2026-09-19

## Kontext

Der Kandidatenbericht nennt je Signal nur `candle_index`. Das ist ein Index
in der Kerzenserie, und der Tiefen-Backfill fügt ältere Bars vorn an — ein
gespeicherter Index zeigt danach auf eine andere Kerze (ADR 0061, Befund 1).
Für den Leser ist er außerdem ohne Aussage: „Kerze 2726" sagt nicht, wann
das Signal war. Rückmeldung des Inhabers vom 2026-09-19.

Zweitens: Ein Lauf heißt `PARTIALLY_COMPLETED`, sobald eine Aktie an einem
Fehler hängen blieb (`run_analysis.py`). Die Laufansicht zeigte nur die
Zahl (`module_errors`), nicht die Aktien und Gründe — der Status wirkte
unbegründet, obwohl der Grund gespeichert ist (`StockProcessingError`).

## Entscheidung

1. **`SignalEvent.candle_at`** — der Zeitstempel der Kerze neben dem Index,
   gesetzt beim Feuern aus der Serie (`candidate.py`), gespeichert in
   `signal_events.candle_at` (Migration `d4f6a1c7e9b2`, NULL zulässig) und
   über `_rein` im Bericht. Der Index bleibt: Er ist die Identität des
   Ereignisses in Episoden und Torbedingungen (ADR 0057).
2. **Keine Rückwirkung.** Alte Ereignisse haben `NULL`; der Bericht zeigt
   dann wie bisher den Index. Eine Nachrechnung mit heutigen Bars wäre
   nicht der damalige Stand.
3. **Keine Verfahrensänderung.** `SIGNAL_RULE_VERSION` und
   `REPORT_SCHEMA_VERSION` bleiben; der Golden Master friert weiterhin
   Typ und Index ein.
4. **Die Laufübersicht nennt jede hängengebliebene Aktie** mit Meldung und
   Zeitpunkt (`processing_errors` in `RunOverview`, API und Export).
   `module_errors` bleibt als Zahl.

## Konsequenzen

- Migration auf dem Server vor dem nächsten Lauf; Signale mit Datum ab dem
  ersten Lauf danach.
- Die Berichtsseite zeigt „Datum (Kerze n)", die Laufseite die Fehlerliste
  unter den Warnungen mit dem Hinweis, dass sie der Grund für „teilweise
  abgeschlossen" ist.
