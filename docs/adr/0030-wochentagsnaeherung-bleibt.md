# ADR 0030: Wochentagsnäherung im Earnings-Filter bleibt — der TWS-Kalender reicht nicht

- Status: Angenommen
- Datum: 2026-08-24

## Kontext

[ADR 0020](0020-earnings-filter-status-und-handelstagskalender.md) hat den
Earnings-Filter auf eine **Wochentagsnäherung** gestellt: Montag bis Freitag
gelten als Handelstage, US-Börsenfeiertage und verkürzte Handelstage bleiben
unberücksichtigt (Einschränkung L2). Einschränkung **L3** hat die Ablösung fest
zugesagt:

> Nachzuholen, sobald `feature/trading-day-dispatcher` gemergt ist — die
> Wochentagsnäherung wird dann durch den echten Kalender abgelöst.

Der Dispatcher ist seit Wochen gemergt und verfügt über einen IBKR-gestützten
Kalender (`infrastructure/ibkr/calendar.py`). Die Zusage ist also fällig. Das
Repository-Audit vom 2026-08-23 hat sie als offenen Punkt E4 geführt.

## Zwei Dinge, die vor der Entscheidung geklärt werden mussten

### Die Empfehlung des Audits stützt sich auf eine falsche Prämisse — die aus ADR 0020 selbst stammt

Das Audit empfiehlt den Verbleib bei der Näherung mit der Begründung, „die
Abweichung wirkt konservativ". **Die Richtung stimmt nicht.**

Der Satz ist nicht im Audit entstanden. Er steht wörtlich in ADR 0020, L2:

> Die Abweichung wirkt konservativ: Ein nicht erkannter Feiertag lässt die
> Kerzenzählung tendenziell zu hoch (nicht zu niedrig) ausfallen […] — das
> begünstigt eher einen zusätzlichen Ausschluss als ein übersehenes Risiko.

Das Audit hat ihn übernommen. Wer künftig ADR 0020 liest — und der Code
verweist an mehreren Stellen dorthin —, findet die Korrektur nur über dieses
ADR. ADR 0020 wird dafür nicht rückwirkend geändert; es wird abgelöst.

`count_future_trading_candles` zählt Feiertage als Handelstage, liefert also
einen **zu hohen** Wert. `evaluate_earnings_filter` schließt aus bei
`candles_until_earnings <= configured_exclusion_candles`. Ein zu hoher Wert
lässt den Termin weiter weg erscheinen — der Filter schließt damit **seltener**
aus, als er sollte, nicht öfter.

Konkret: Bei berechneten 22 Kerzen und tatsächlich 20 lautet das Ergebnis
`EARNINGS_CLEAR`, obwohl `EARNINGS_EXCLUDED` richtig wäre. Wir handeln in die
Quartalszahlen hinein, statt draußen zu bleiben. Der Fehler zeigt in die
**riskante** Richtung.

Diese Feststellung ändert nichts daran, welcher Weg gangbar ist — aber sie
verbietet, den Verbleib mit einer angeblichen Vorsicht zu rechtfertigen.

### Wie weit der echte Kalender reicht, war unbelegt

`IbkrTradingCalendar` hält in seinem eigenen Quelltext fest, dass IBKR „nur ein
Fenster um den heutigen Tag" liefert. Wie groß dieses Fenster ist, stand
nirgends — und genau daran hängt die Entscheidung. Muster wie bei E2
([ADR 0027](0027-historientiefe-messen-vor-anspruch.md)): erst messen, dann
entscheiden.

## Das Messergebnis

Gemessen am 2026-08-24 auf dem Windows-Server gegen die produktive TWS mit
`cli calendar-reach --provider ibkr`, Referenzkontrakt NVDA (erstes Symbol der
Watchlist).

| | |
|---|---|
| Abgedeckter Zeitraum | 2026-08-24 bis 2026-08-28 |
| Tage insgesamt | **5** |
| Künftige Handelstage | **4** |
| Künftige Ruhetage im Fenster | keine |
| Gebraucht | **11** |

Die 11 ergeben sich aus `configured_exclusion_candles: 20` bei 2 Kerzen je Tag
(390 Minuten Sitzung / 195 Minuten). Nicht 10: Der Filter schließt aus bis
*einschließlich* 20 Kerzen, „nicht ausgeschlossen" beginnt erst einen
Handelstag danach.

**Der Kalender reicht auf gut ein Drittel des Ausschlussfensters.**

## Entscheidung

**Die Wochentagsnäherung bleibt. Die Zusage L3 aus ADR 0020 wird hiermit
entkräftet.** ADR 0020 selbst bleibt unverändert; es wird durch dieses ADR
abgelöst, nicht rückwirkend geändert — so hat es L3 selbst vorgesehen.

Die Begründung ist ausdrücklich **nicht** die des Audits. Sie lautet: Der echte
Kalender existiert für diesen Zweck nicht. IBKR beantwortet die Frage „ist der
Tag in fünf Handelstagen ein Handelstag?" schlicht nicht, und ein `session_on`
außerhalb des Fensters liefert korrekterweise einen Fehler statt einer
Vermutung. Es gibt nichts, womit sich die Näherung ersetzen ließe.

Damit fallen auch die beiden Wege, die im Vorfeld erwogen wurden:

- **(a) Filter auf den IBKR-Kalender umstellen** — nicht möglich, mangels
  Reichweite. Zusätzlich hätte es die Modulentkopplung belastet.
- **(c) Nichthandelstage als Parameter in die Domain hineinreichen** —
  technisch sauber (`TradingCalendar` ist bereits ein Domain-Port, die Domain
  bliebe rein), scheitert aber an derselben Reichweite. Der Weg bleibt
  beschrieben, falls sich die Datenlage ändert.

## Einschränkungen

| # | Einschränkung |
|---|---|
| **L1** | **Der Filter schließt bei Feiertagen im Fenster seltener aus, als er sollte.** Die Fehlerrichtung ist riskant, nicht vorsichtig. Betroffen ist der Grenzfall: ein Termin, der rechnerisch knapp außerhalb des Fensters liegt und tatsächlich knapp darin. Wie oft das eintritt, ist **nicht gemessen** — dafür fehlt genau der Kalender, dessen Fehlen dieses ADR feststellt. |
| **L2** | **Die Messung lief über ein Symbol.** Die Handelszeiten gelten für die Börse, nicht für das Papier, und das Ergebnis ist mit 4 von 11 nicht knapp — eine Gegenprobe hätte die Entscheidung nicht bewegt. Sollte sie je knapp werden, gehört sie über mehrere Kontrakte wiederholt. |
| **L3** | **Eine zweite Lücke bleibt unberührt.** `candles_until_earnings` wird auch für nicht ausgeschlossene Titel gespeichert, und Termine werden bis 30 Kalendertage voraus geholt (`lookahead_calendar_days`). Selbst ein Kalender, der die Ausschlussentscheidung trüge, deckte diese Zahl nicht ab. `cli calendar-reach` kennt diesen Fall und weist darauf hin — bei der hier gemessenen Reichweite kommt es dazu gar nicht erst, weil der Kalender schon für die Ausschlussentscheidung nicht reicht. |
| **L4** | **Die Datenlage kann sich ändern.** IBKRs Fenster ist eine Eigenschaft des Anbieters, keine Naturkonstante. `cli calendar-reach` bleibt im Code und macht die Messung ohne Aufwand wiederholbar. Ein größeres Fenster wäre ein neues ADR, kein Nachtrag zu diesem. |

## Konsequenzen

- `domain/earnings/calendar.py` bleibt unverändert und behält seine Reinheit —
  kein Kalenderzugriff, keine Abhängigkeit von IBKR oder vom Dispatcher.
- Der Kopfkommentar dort nennt künftig die **Fehlerrichtung**, nicht nur die
  Tatsache der Näherung. Wer ihn liest, soll nicht dieselbe falsche Annahme
  treffen wie das Audit.
- `cli calendar-reach` bleibt als Diagnosekommando bestehen; Doc 14 führt es
  als optionalen Zwischenschritt.
- E4 und M7 der Audit-Nachverfolgung sind damit geschlossen.

## Alternativen, die nicht gewählt wurden

**Einen eigenen Feiertagskalender pflegen.** Er wäre sofort vollständig und
löste L1. Er ist aber genau die Sorte Liste, vor der `infrastructure/ibkr/
calendar.py` in seinem Kopf warnt: Sie muss jährlich stimmen, ein Fehler darin
fällt niemandem auf, und das Risiko R8 der Audit-Nachverfolgung führt
handgepflegte Listen bereits als eigenen Posten. Ein solcher Kalender käme nur
über eine Bibliothek in Frage — das wäre eine neue Abhängigkeit für einen
Grenzfall unbekannter Häufigkeit und braucht ein eigenes ADR, keine Fußnote in
diesem.

**Das Ausschlussfenster verkleinern, bis der Kalender reicht.** Vier Handelstage
statt zehn wären abgedeckt. Das ändert aber die fachliche Regel, um ein
technisches Hindernis zu umgehen — die falsche Reihenfolge.
