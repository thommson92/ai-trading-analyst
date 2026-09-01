# ADR 0055: Die Ergebnismeldung nennt den Put-Vorschlag und zählt Signale statt sie aufzuzählen

- Status: Angenommen
- Datum: 2026-09-01

## Kontext

Der erste scharfe Verbundlauf (2026-09-01, 36 Kandidaten) hat die Meldung
nach [ADR 0040](0040-inhalt-der-ergebnismeldung.md) und
[ADR 0047](0047-scores-in-der-ergebnismeldung.md) zum ersten Mal in echter
Länge auf ein Telefon gestellt. Der Befund des Projektinhabers: schwer
lesbar. Die Signalnamen (`EMA5_EMA20_CROSS + PRICE_EMA20_BREAKOUT +
RSI_CROSS`) dominieren jede Zeile, ohne etwas zu unterscheiden — bei einer
2-aus-3-Regel ist die Information nicht, **welche** Signale feuerten, sondern
**wie viele**. Die Blöcke kleben aneinander, und ausgerechnet die Angabe, die
über einen Handel entscheidet — der Cash-Secured-Put-Vorschlag, den die
Optionsanalyse seit [ADR 0048](0048-optionsanalyse-im-tageslauf.md) für jeden
Kandidaten rechnet — fehlt ganz: Der Formatter liest `outcome.options` nicht.

## Entscheidung

**Je Aktie ein Block aus zwei Zeilen, Blöcke durch eine Leerzeile getrennt;
für STRONG_CANDIDATE und CANDIDATE eine dritte Zeile mit dem besten
Put-Vorschlag.**

```
ULTA -- CANDIDATE -- 3/3 Signale -- Risiko MEDIUM
S 8.1 | I 6.5 -- Earnings-Termin unbekannt
Put-Verkauf: Strike 320 $, Verfall 16.10.2026, Praemie ~230 $

TMUS -- WATCH -- 3/3 Signale -- Risiko HIGH
S 7.6 | I 7.1 -- Earnings-Termin unbekannt
```

Im Einzelnen:

1. **Signalzahl statt Signalnamen** — löst ADR 0040 in genau diesem Punkt
   ab. Gezählt wird gegen die tatsächliche Regelmenge (`len(SignalType)`),
   nicht gegen eine fest verdrahtete Drei.
2. **Der Put-Vorschlag ist eine handelbare Zahl und steht trotzdem drin** —
   löst die Grenze „keine Rohdaten" aus ADR 0047 in genau diesem Punkt ab.
   Begründung: Für einen empfohlenen Kandidaten ist der Vorschlag der
   **Zweck** der Meldung (Doc 08), nicht Beiwerk; wer am Telefon entscheidet,
   ob sich der Blick lohnt, braucht Strike, Verfall und Prämie. Genommen wird
   die **beste** Strategie (`strategies[0]`, absteigend nach annualisierter
   Rendite — die Sortierung ist Zusage des Datentyps); die übrigen bis zu
   drei stehen unverändert im Bericht.
3. **Prämie je Kontrakt, als Mid gekennzeichnet.** `PutStrategy.premium` ist
   der Mid je Aktie; die Meldung zeigt `premium × 100` und markiert den Wert
   mit `~`, weil ein Mid eine Annahme ist und kein handelbarer Kurs
   (ADR 0048). Der Verfall steht als `TT.MM.JJJJ`.
4. **Fehlende Optionsdaten bleiben sichtbar fehlend:** Bei STRONG_CANDIDATE
   und CANDIDATE ohne verwertbare Optionsdaten (`options` fehlt,
   `INSUFFICIENT_DATA`, keine Strategie) steht `Put-Verkauf: keine
   Optionsdaten` — kein Ersatzwert, keine stille Auslassung. WATCH und
   darunter tragen weder Put- noch Hinweiszeile.
5. **Gekürzt wird an der Blockgrenze.** Der Adapter schnitt bisher hart nach
   Zeichen, mitten im Wort; mit Leerzeilen zwischen Blöcken sähe das nach
   einem Defekt aus. Er schneidet jetzt an der letzten Leerzeile vor der
   Grenze; der Kürzungshinweis bleibt wörtlich erhalten, die Obergrenze von
   4096 Zeichen unverändert. Findet sich im Fenster keine Blockgrenze,
   bleibt der harte Schnitt als Rückfall.
6. **Kürzeres Etikett `Risiko`** statt `Fehlsignalrisiko` — die Bedeutung
   trägt die Legende; jedes Zeichen der Zeile kostet Meldungsbudget.

Unverändert bleiben: Sortierung nach Swing-Score (ADR 0047), Strich statt
Null für fehlende Scores, kein Freitext, der Berichtsverweis als Befehl.

## Finnhub L8 und das Restrisiko

Der Put-Vorschlag stammt aus der **IBKR**-Optionskette — Einschränkung L8 aus
[ADR 0017](0017-finnhub-fuer-earnings-und-ratings.md) (keine Weitergabe von
Finnhub-Daten) ist nicht berührt. Es bleibt beim Muster von ADR 0047: Der
Versand an den eigenen Chat des Kontoinhabers ist keine Weitergabe an
Dritte, aber die Nachricht liegt danach auf Telegrams Servern — mit diesem
ADR erstmals einschließlich handelbarer Marktdaten-Ableitungen (Strike,
Prämie). Das Restrisiko wird ausgewiesen, nicht verschwiegen.

## Kürzung — gemessen, nicht geschätzt

Die Tabelle aus ADR 0047 (24 volle / 51 kurze Zeilen) ist mit dem neuen
Format hinfällig. Neu gemessen an dem, was tatsächlich versendet wird
(`Betreff + Leerzeile + Text`, durch den Notifier):

| Block | Kandidaten, die passen |
|---|---|
| voll (drei Zeilen: Stufe, Scores, Earnings-Hinweis, Put-Vorschlag) | — (Messung folgt mit der Umsetzung) |
| kurz (zwei Zeilen: WATCH ohne Hinweise) | — (Messung folgt mit der Umsetzung) |

Beide Enden sind als Test festgehalten; wandern sie, gehört die Zahl hier
nachgezogen.

## Konsequenzen

- Die Meldung des Verbundlaufs vom 2026-09-01 (36 Kandidaten) hätte in
  diesem Format Platz für alle Blöcke bis zur Kürzungsgrenze; zusammen mit
  der Wiederholsperre ([ADR 0054](0054-wiederholsperre-im-tageslauf.md))
  sinkt die Blockzahl an Folgetagen ohnehin deutlich.
- ADR 0040 und ADR 0047 erhalten Nachtragsabschnitte mit Verweis hierher;
  ihre übrigen Festlegungen gelten fort.
- Wer nur die Meldung liest, sieht je Kandidat genau einen Vorschlag. Die
  Abwägung zwischen den bis zu drei Vorschlägen (Delta, Abstand zum Kurs,
  Abstand zur Unterstützung) bleibt Sache des Berichts.
