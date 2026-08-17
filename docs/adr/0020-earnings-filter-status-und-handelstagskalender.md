# ADR 0020: Earnings-Filter -- reduziertes Statusmodell und Wochentagsnäherung für die Kerzenzählung

- Status: Angenommen
- Datum: 2026-08-16

## Kontext

Doc 10, Paragraph 6.5, legt für den Earnings-Filter zwei Dinge fest, die bei
der Umsetzung mit dem in [ADR 0017](0017-finnhub-fuer-earnings-und-ratings.md)
entschiedenen Anbieter nicht unverändert übernehmbar sind:

1. **Ein fünfwertiger Status** (`CONFIRMED_CLEAR`, `CONFIRMED_EXCLUDED`,
   `ESTIMATED_CLEAR`, `ESTIMATED_EXCLUDED`, `UNKNOWN`), der zwischen
   bestätigten und geschätzten Terminen unterscheidet. ADR 0017,
   Einschränkung L1, hält aber bereits fest: Finnhub liefert in der
   kostenlosen Stufe **kein Feld** für diese Unterscheidung, und die
   Tageszeitangabe (`bmo`/`amc`) taugt ausdrücklich nicht als Ersatz -- sie
   ist ein Merkmal der Abdeckung, nicht der Bestätigung.
2. Die Berechnung der **verbleibenden 195-Minuten-Kerzen bis zum Termin**
   setzt einen vorwärtsgerichteten Handelstagskalender voraus (Wochenenden,
   US-Feiertage, verkürzte Handelstage). Der einzige im Projekt vorhandene
   Weg zu einem verlässlichen Kalender läuft über die IBKR-Anbindung des
   Trading-Day-Dispatchers (ADR 0019, Branch `feature/trading-day-dispatcher`)
   -- der bezieht seinen Kalender live von der TWS und pflegt bewusst
   **keine** eigene Feiertagsliste im Code. Dieser Branch ist zum Zeitpunkt
   dieser Entscheidung noch nicht nach `dev` gemergt.

Der Earnings-Filter wird unabhängig vom Dispatcher entwickelt (Sprint 3 ist
davon nicht gegated). Eine Kopplung an den ungemergten Dispatcher-Branch
würde diese Unabhängigkeit aufheben und die Fertigstellung an einen fremden
Merge-Zeitpunkt binden.

## Entscheidung

1. **Reduziertes Statusmodell.** `EarningsFilterStatus` erhält nur drei
   Werte: `EARNINGS_CLEAR`, `EARNINGS_EXCLUDED`, `UNKNOWN`. Die
   bestätigt/geschätzt-Unterscheidung aus Doc 10 entfällt ersatzlos, bis ein
   Anbieter sie tatsächlich liefert.
2. **Eigenständige Wochentagsnäherung.** Die Kerzenzählung bis zum
   nächsten Earnings-Termin geht von einer regulären Handelswoche
   Montag bis Freitag mit je zwei 195-Minuten-Kerzen aus. US-Börsenfeiertage
   und verkürzte Handelstage bleiben unberücksichtigt. Die Berechnung ist
   vollständig eigenständig in `domain/earnings/` implementiert und
   importiert nichts aus dem Dispatcher-Branch oder von IBKR.

## Begründung

Zu (1): Eine synthetische Unterscheidung zu erfinden -- etwa aus der
Tageszeitangabe oder dem Vorlauf bis zum Termin -- hat ADR 0017 bereits
ausdrücklich verworfen ("die Tageszeit taugt nicht als Ersatz"). Ein
fünfwertiger Status, dessen zwei `CONFIRMED_*`-Werte mit dem aktuellen
Anbieter nie erreichbar sind, wäre irreführender toter Code. Das dreiwertige
Modell bildet exakt das ab, was die Datenlage hergibt.

Zu (2): Die Alternative -- eine eigene Feiertagsliste pflegen oder auf
IBKR zugreifen -- wurde verworfen. Eine eigene Liste dupliziert Wissen, das
der Dispatcher ohnehin bald zentral vorhält, und veraltet stillschweigend.
Ein direkter IBKR-Zugriff koppelt den Earnings-Filter an einen Anbieter, mit
dem er inhaltlich nichts zu tun hat, und verdoppelt Kalenderlogik parallel
zum Dispatcher. Die Wochentagsnäherung ist der einzige Weg, der beide
Kopplungen vermeidet und sofort umsetzbar ist.

## Konsequenzen

Vom Projektinhaber akzeptierte Einschränkungen, nicht als offene Punkte:

| # | Einschränkung | Folge für die Implementierung |
|---|---|---|
| L1 | **Kein bestätigt/geschätzt-Unterschied im Status.** Deckt sich mit ADR 0017 L1 auf Datenebene | Jeder Termin zählt gleich für die Ausschlussentscheidung, unabhängig davon, ob Finnhub ihn intern als geschätzt führt |
| L2 | **Die Kerzenzählung ignoriert die ~9 US-Börsenfeiertage pro Jahr.** Um einen übersehenen Feiertag herum kann die gezählte Kerzenzahl von der tatsächlichen abweichen | Die Abweichung wirkt konservativ: Ein nicht erkannter Feiertag lässt die Kerzenzählung tendenziell zu hoch (nicht zu niedrig) ausfallen, da ein Tag ohne Handel fälschlich als zwei Kerzen mitgezählt wird -- das begünstigt eher einen zusätzlichen Ausschluss als ein übersehenes Risiko. Nicht bewiesen, nur als Richtung dokumentiert |
| L3 | **Kein Abgleich mit dem echten Handelskalender.** Der Trading-Day-Dispatcher (ADR 0019) wird nach seinem Merge nach `dev` über einen echten, IBKR-gestützten Kalender verfügen | Nachzuholen, sobald `feature/trading-day-dispatcher` gemergt ist -- die Wochentagsnäherung wird dann durch den echten Kalender abgelöst. Dieses ADR wird dafür nicht rückwirkend geändert, sondern durch ein neues abgelöst |

Ändert sich die Datenlage bei Finnhub (Statusfeld wird verfügbar) oder wird
der Dispatcher-Kalender verfügbar, ist das ein neues ADR.
