# `optionskette-AAPL.json`

**Echt, nicht erzeugt.** Mitschnitt der Antworten, die die TWS am
**2026-09-01 um 17:02 UTC** (13:02 New Yorker Zeit, offener Markt) auf die
drei Abrufe der Optionskette für `AAPL` gab. Aufgezeichnet mit

```powershell
cli options --symbol AAPL --provider ibkr --market-data-provider ibkr `
    --record tests\unit\infrastructure\ibkr\data\optionskette-AAPL.json
```

Der Mitschnitt hängt zwischen Adapter und Schnittstelle
(`infrastructure/ibkr/chain_recorder.py`) und ist passiv: Ein Lauf mit
`--record` und einer ohne liefern dieselbe Analyse.

## Warum ein Mitschnitt und kein `curl`

Von den Anbietern, deren Antwortformat die Auswertung trägt, ist dieser der
einzige, der nicht über HTTP erreichbar ist. Finnhub und EDGAR lassen sich
mit einem `curl` einfrieren; die TWS spricht ein eigenes Protokoll über einen
lokalen Socket, und ohne laufende TWS gibt es keine Antwort zum Aufheben.

## Roh, nicht gerechnet

Aufgezeichnet ist, was der Anbieter **gab** — Verfallstermine, gelistete
Strikes, Notierungen. **Nicht** die bewerteten Vorschläge: Ein Mitschnitt der
fertigen Analyse würde die Rechnung mit einfrieren, und eine Formatänderung
des Anbieters wäre danach von einer Verfahrensänderung nicht mehr zu
unterscheiden. Der Test in `../test_eingefrorene_kette.py` rechnet aus diesen
Rohdaten neu.

Aus demselben Grund stehen **angefragte und gelieferte Strikes getrennt**:
Dass die TWS zu einem angefragten Kontrakt nichts zurückgibt, ist selbst ein
Befund ([ADR 0048](../../../../../../docs/adr/0048-optionsanalyse-im-tageslauf.md)).
An diesem Tag lieferte sie zu allen zwölf etwas.

## Was diese Aufzeichnung zeigt, was eine gebaute nicht zeigt

- **23 Verfallstermine**, Wochen- und Monatsverfälle gemischt. Mehrere liegen
  im Laufzeitfenster von 21 bis 60 Tagen; gewählt wird der der bevorzugten
  Laufzeit nächste — der 02.10. mit 32 Tagen, **nicht** der frühere 25.09. mit
  25. An einer selbst gebauten Terminliste geht dieser Unterschied unter.
- **61 gelistete Strikes** zu diesem Termin, von 110 bis 415. Angefragt werden
  die zwölf im Moneyness-Band. Die 49 nicht gestellten Anfragen je Titel sind
  der Unterschied zwischen einem Tageslauf und einem Nachmittag.
- **Kein einziges Open Interest.** Im `frozen`-Marktdatenmodus (`2`) gibt die
  TWS es zu keinem der zwölf Kontrakte heraus, bei durchweg dreistelligem
  Volumen. Eine 0 an dieser Stelle hieße „niemand hält diesen Kontrakt" — eine
  Aussage über den Markt, die niemand gemacht hat. Das Feld bleibt leer, und
  die Liquiditätsbewertung stützt sich auf Spanne und Volumen.
- **Delta negativ**, wie der Anbieter es für einen Put liefert. Gefiltert und
  ausgewiesen wird der Betrag.

## Neu aufzeichnen

Bei laufender TWS und offenem Markt, mit demselben Kommando. Die *Werte*
ändern sich dabei zwangsläufig — andere Kurse, andere Termine, andere
Prämien; die Zahlen im Test müssen dann mitwandern. **Ändert sich die
Struktur, ist das eine Aussage**: Dann hat IBKR etwas an der Schnittstelle
geändert, und der Adapter gehört nachgezogen, bevor die neue Datei
eingecheckt wird.

Die Datei enthält Kurse und Kontraktdaten eines öffentlich gehandelten
Papiers — nichts Kontobezogenes, keine Zugangsdaten, keine Order.
