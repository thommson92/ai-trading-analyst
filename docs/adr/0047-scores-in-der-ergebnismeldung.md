# ADR 0047: Die Ergebnismeldung nennt beide Scores und die Empfehlungsstufe

- Status: Angenommen
- Datum: 2026-08-31

## Kontext

[ADR 0040](0040-inhalt-der-ergebnismeldung.md) hat die Grenze der
Telegram-Meldung bei Symbolen und Signaltypen gezogen — **keine Zahlen** —
und die Frage ausdrücklich offen gelassen:

> **Zu entscheiden, sobald es Scores gibt:** ob eine Punktzahl in die Meldung
> gehört. Dieses ADR sagt Nein zu Zahlen; ein Score ist eine.

Es gibt sie jetzt. Doc 10 §6.13 verlangt für die Benachrichtigung
ausdrücklich Anzahl der Kandidaten, Symbol, **beide Scores**, die wichtigsten
Signalgründe, die wichtigste Risikowarnung und einen Link zum Bericht. Nach
[ADR 0001](0001-dokumentenhierarchie.md) ist Doc 10 bei Widersprüchen
maßgeblich.

## Entscheidung

**Die Meldung nennt je Kandidat beide Scores und die Empfehlungsstufe.**

Eine Zeile trägt: Symbol, Signaltypen, Empfehlungsstufe, beide Scores,
Fehlsignalrisiko als Stufe und den Hinweis auf einen unbekannten
Berichtstermin.

```
NVDA  EMA5_EMA20_CROSS + RSI_CROSS  -- STRONG_CANDIDATE  [S 8.6 | I 5.5]
```

**Sortiert nach Swing-Score, absteigend.** Die Kürzung des Kanals greift am
Ende des Textes; alphabetisch sortiert verlöre man ausgerechnet die
Kandidaten, wegen derer die Meldung geschrieben wird. Bei Gleichstand
entscheidet das Symbol — ohne zweiten Schlüssel hinge die Reihenfolge an der
Aktienliste, und zwei Läufe derselben Lage ergäben verschiedene Meldungen.

**Ein fehlender Score steht als Strich, nicht als Null.** Null hieße geprüft
und schlecht (Doc 09) — in einer Meldung, die auf ein Smartphone geht, ist
der Unterschied besonders teuer.

Weiterhin **nicht** enthalten:

- Kurse, Kennzahlen, Renditen — nichts, woraus sich eine Bewertung
  einzelner Rohdaten ablesen ließe,
- Freitext aus der Recherche oder der KI-Einordnung,
- ein Link (es gibt kein Dashboard).

Die Grenze verschiebt sich damit von „keine Zahlen" zu **„keine Rohdaten und
keine Formulierung"**. Ein Score ist eine aggregierte, versionierte,
deterministisch gerechnete Größe — näher an einem Signaltyp als an einem
Kurs.

## Finnhub, Einschränkung L8

[ADR 0017](0017-finnhub-fuer-earnings-und-ratings.md) hält als L8 fest:

> Weitergabe an Dritte ist untersagt, einschließlich abgeleiteter Ergebnisse.

Die Frage wird mit diesem ADR schärfer, denn die News-Komponente des
Swing-Scores steht seit [ADR 0046](0046-empfehlungsstufe-aus-beiden-scores.md)
auf Finnhub-Analystenvoten. Ein Swing-Score in der Meldung trägt damit ein
abgeleitetes Finnhub-Ergebnis nach außen. ADR 0040 erwähnte L8 mit keinem
Wort, obwohl der Earnings-Hinweis schon damals hinausging.

**Entscheidung: Der Versand an den eigenen Chat des Kontoinhabers ist keine
Weitergabe an Dritte.** Begründung:

- Der **Empfänger ist der Bezieher selbst**. Es entsteht kein zweiter Nutzer
  der Daten.
- Aus einer aggregierten Punktzahl ist **kein einzelnes Finnhub-Datum
  rekonstruierbar**. Der Swing-Score ist ein gewichtetes Mittel aus fünf
  Komponenten; die Votenverteilung geht mit 10 % und über eine Fünftelstufe
  ein.
- Der **Earnings-Hinweis geht seit ADR 0040 bereits so hinaus**. Die
  Entscheidung ändert die Art des Versands nicht, sondern nur seinen Umfang.

**Das Restrisiko wird ausgewiesen, nicht weggelassen:** Die Nachricht liegt
nach dem Versand auf Telegrams Servern. Das ist eine Übertragung an einen
Dienstleister, keine Veröffentlichung — aber es ist nicht nichts, und wer die
Entscheidung später prüft, soll es hier finden und nicht rekonstruieren
müssen.

**F12 bleibt der scharfe Fall.** Ein extern erreichbares Dashboard zeigte
Finnhub-abgeleitete Ergebnisse einem unbestimmten Personenkreis; das ist
etwas anderes und von dieser Entscheidung unberührt.

## Kürzung

Der Adapter kürzt bei 4096 Zeichen und kennzeichnet die Kürzung (ADR 0040).
Mit den längeren Zeilen verschiebt sich die Grenze — **gemessen, nicht
geschätzt**:

| Zeile | Kandidaten, die passen |
|---|---|
| voll (drei Signale, Fehlsignalrisiko, Earnings-Hinweis) | 24 |
| kurz (zwei Signale, keine Hinweise) | 51 |

ADR 0040 hatte ohne Scores rund 65 genannt. Beide Enden sind als Test
festgehalten; wandern sie, gehört die Zahl hier nachgezogen.

Gemessen wird an dem, **was tatsächlich versendet wird** — also an
`Betreff + Leerzeile + Text`, denn der Adapter kürzt die zusammengesetzte
Zeichenkette. Ein erster Anlauf maß nur den Text und war damit um eine Zeile
zu optimistisch; der Betreff wächst außerdem mit der Kandidatenzahl. Der Test
schickt deshalb durch den Notifier und misst, was beim Transport ankommt.

Die Kürzung selbst war seit ADR 0040 zugesichert und **bis heute ungeprüft**
— das ist mit diesem ADR nachgeholt.

## Konsequenzen

**Positiv**

- Doc 10 §6.13 ist bis auf den Link erfüllt. Der fehlt mangels Dashboard und
  nicht mangels Entscheidung.
- Die Meldung beantwortet zum ersten Mal die Frage, die sich der Empfänger
  stellt: nicht „gab es Kandidaten", sondern „lohnt sich einer davon".
- Die Sortierung macht die Kürzung erträglich: Was wegfällt, ist das
  Schwächste.

**Negativ und offen**

- **Analyseinhalte verlassen das eigene Netz in größerem Umfang.** Wer den
  Nachrichtenverlauf mitliest, sieht nicht mehr nur, welche Titel das System
  interessant fand, sondern auch, wie gut es sie fand.
- **Bei mehr als 24 Kandidaten steht der Rest nur im Bericht.** Eine
  fachliche Obergrenze wird weiterhin nicht eingeführt, bevor gemessen ist,
  wie viele es an einem gewöhnlichen Tag sind — der erste produktive
  Tageslauf steht noch aus.
- **Die Empfehlungsstufe ist eine Empfehlung.** Sie geht damit weiter als
  alles, was ADR 0024 ursprünglich zulassen wollte. Sie ist ein Enum aus
  einer deterministischen Ableitung, kein formulierter Satz — aber sie ist
  eine Aussage über eine Aktie, und das gehört gesagt.
