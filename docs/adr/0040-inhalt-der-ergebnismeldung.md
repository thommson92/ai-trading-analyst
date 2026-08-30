# ADR 0040: Die Ergebnismeldung nennt Symbole und Signalgründe — keine Kurse

- Status: Angenommen
- Datum: 2026-08-30

## Kontext

Telegram meldet heute genau eine Sache: einen **ausgefallenen** Lauf. Der
Klassenkommentar in `notifications.py` begründet das ausdrücklich — die
Meldung verlässt das eigene Netz, deshalb enthält sie „nur Handelstag,
Kerzenzeitpunkt und Ursache — keine Kurse, keine Kandidaten, keine
Analyseergebnisse".

Doc 10 §6.13 verlangt das Gegenteil: Anzahl gefundener Kandidaten, Symbol,
beide Scores, wichtigste Signalgründe, wichtigste Risikowarnung und einen Link
zum Dashboard-Bericht. Doc 02 §2.12 ebenso.

Beides zusammen geht nicht. Das Audit vom 2026-08-23 führt den Widerspruch als
**E7** und empfiehlt „neutraler Ping plus Link ins dann existierende,
abgesicherte Dashboard" — eine Lösung, die voraussetzt, dass es ein Dashboard
gibt. Das gibt es nicht; es gehört zu Sprint 6, und der externe Zugriff darauf
ist als F12 unentschieden.

Damit steht die Frage jetzt an, weil der Report Generator
([ADR 0039](0039-report-generator.md)) die kompakte Zusammenfassung als eine
seiner drei Varianten führt.

## Entscheidung

**Die Meldung nach einem erfolgreichen Lauf nennt Symbole und Signalgründe.**

Enthalten:

- Anzahl der Kandidaten und der Handelstag,
- je Kandidat das Symbol und die Signaltypen, die gefeuert haben,
- je Kandidat, sofern vorhanden, das **Fehlsignalrisiko** der KI-Einordnung
  als Stufe,
- je Kandidat der Hinweis, wenn der Earnings-Termin unbekannt ist.

Ausdrücklich **nicht** enthalten:

- Kurse, Kennzahlen, Kurszielen, Renditen — nichts, woraus sich eine
  Bewertung ablesen ließe,
- Freitext aus der Recherche oder der KI-Einordnung,
- ein Link (es gibt kein Dashboard).

Ohne Kandidaten wird nichts gemeldet, es sei denn
`notifications.send_when_no_candidates` steht auf `true`. Der Schalter
existiert seit Sprint 1 und wurde bislang von keiner Codestelle gelesen; Doc 10
§6.13 verlangt genau ihn.

Ausgelöst wird die Meldung von `RunAnalysisUseCase` und nur dann, wenn ein
Notifier hineingereicht wurde. Der Tageslauf über `cli dispatch` reicht einen
hinein, `cli screen` nicht.

## Begründung

**Warum nicht beim neutralen Ping bleiben?** Weil er nichts nützt. „Der Lauf
ist fertig" beantwortet keine Frage, die sich der Empfänger stellt, und ohne
Dashboard gibt es nichts, worauf er verweisen könnte. Er wäre ein Kanal, der
jeden Abend belegt, dass er funktioniert.

**Warum dann nicht gleich alles?** Weil der ursprüngliche Einwand richtig
bleibt: Die Nachricht verlässt das eigene Netz und liegt danach auf fremden
Servern. Der Unterschied zwischen „AAPL ist heute Kandidat, RSI-Kreuzung" und
einem Kurs samt Bewertung ist kein gradueller. Das erste ist ein Hinweis, sich
den Bericht anzusehen; das zweite ist der Bericht.

Die Trennlinie liegt deshalb dort, wo aus einem Hinweis eine handelbare
Aussage würde: **Symbole und Signaltypen ja, Zahlen nein.**

**Warum Stufen statt Freitext?** Das Fehlsignalrisiko ist ein Enum aus einer
gegen ein Schema validierten Antwort (ADR 0026). Ein Freitext-Risiko aus der
Recherche wäre dagegen Modellausgabe, die ungeprüft das Netz verlässt — und
„das wichtigste" Risiko auszuwählen setzte eine Rangfolge voraus, die es nicht
gibt. Was gemeldet wird, ist gerechnet oder eingestuft, nicht formuliert.

**Beide Scores aus Doc 10 §6.13 fehlen**, weil es sie nicht gibt (Sprint 5).
Wenn sie kommen, ist neu zu entscheiden, ob sie in die Meldung gehören — eine
Punktzahl ist näher an einer Bewertung als ein Signaltyp.

## Konsequenzen

**Positiv**

- Der Kanal wird zum ersten Mal nützlich: Er sagt, ob sich der Blick in den
  Bericht heute lohnt.
- E7 aus dem Audit vom 2026-08-23 ist entschieden.
- `send_when_no_candidates` wird nach Monaten erstmals gelesen.

**Negativ und offen**

- **Das Prinzip aus ADR 0024 wird bewusst gelockert.** Analyseinhalte
  verlassen jetzt das eigene Netz — begrenzt, aber sie tun es. Wer den
  Nachrichtenverlauf mitliest, weiß, welche Titel das System heute
  interessant fand.
- **Doc 10 §6.13 wird nur teilweise erfüllt.** Scores und Link fehlen, das
  eine mangels Modul, das andere mangels Dashboard. Der Punkt ist damit nicht
  abgeschlossen, sondern auf den Stand gebracht, den das System hergibt.
- **Die Meldung wächst mit den Kandidaten.** Bei einem Lauf mit zwanzig
  Kandidaten ist sie lang. Eine Obergrenze wird bewusst nicht eingeführt,
  bevor gemessen ist, wie viele es an einem gewöhnlichen Tag sind.
- **Zu entscheiden, sobald es Scores gibt:** ob eine Punktzahl in die Meldung
  gehört. Dieses ADR sagt Nein zu Zahlen; ein Score ist eine.
