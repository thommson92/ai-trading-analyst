# `companyfacts-ausschnitt.json`

**Echt, nicht erzeugt.** Ausschnitt aus der Antwort von
`https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json` (Apple Inc.),
abgerufen am **2026-08-25**.

Gefiltert auf das, was die Auswertung tatsächlich liest:

- nur die Tags aus `FIGURE_TAGS` und `EntityCommonStockSharesOutstanding`,
- nur Fakten aus `10-K`, `10-K/A` und `10-Q`,
- bei der Aktienzahl nur der jüngste Stichtag.

Aus 3,8 MB und 503 Tags werden so 566 KB und 15 Tags.

**Die 10-Q gehören seit [ADR 0033](../../../../../../docs/adr/0033-zwoelfmonatswerte-statt-jahresabschluss.md)
dazu.** Ohne sie prüfte der Test nur den Rückfall auf Jahreswerte — also
genau den Weg, den das Verfahren im Regelfall nicht geht. **Inhaltlich verändert
wurde nichts** — kein Wert, kein Datum, keine Vorgangsnummer. Wer den Abruf
wiederholt, bekommt dieselben Zahlen für dieselben Zeiträume, sofern Apple
sie nicht neu ausweist.

Der Unterschied zu den eingefrorenen Bars unter `tests/golden`: Die sind
**erzeugt**, weil der reale Bestand nur auf dem Server liegt. Dieser
Ausschnitt ist gemessen — EDGAR ist öffentlich, es gab keinen Grund, ihn
nachzubauen.

Neu aufzeichnen, falls sich das Antwortformat der SEC ändert:

```bash
curl -H "User-Agent: ai-trading-analyst <kontakt>" \
  https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json
```

Zu erwarten ist dabei, dass sich die **Zwölfmonatswerte ändern**: Sie rücken
mit jedem neuen 10-Q weiter. Die Jahreswerte bleiben, bis Apple neu ausweist
oder ein Geschäftsjahr hinzukommt.

Danach mit demselben Filter kürzen. **Ändern sich dabei Zahlen, ist das eine
Aussage** — entweder hat Apple neu ausgewiesen, oder die Auflösungsregeln
haben sich verschoben. Der Diff gehört angesehen, bevor er eingecheckt wird.
