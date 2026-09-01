# Eingefrorene Finnhub-Antworten

**Echt, nicht erzeugt.** Beide am **2026-09-01** vom Windows-Server gegen den
produktiven Finnhub-Dienst abgerufen, Symbol `AAPL`, unverändert gespeichert —
kein Wert, kein Feld, keine Reihenfolge angetastet.

| Datei | Endpunkt |
|---|---|
| `calendar-earnings-AAPL.json` | `/calendar/earnings?symbol=AAPL&from=…&to=…` (90-Tage-Fenster) |
| `recommendation-AAPL.json` | `/stock/recommendation?symbol=AAPL` |

## Wozu

Alle übrigen Adaptertests schreiben ihre Antwort selbst hin. Sie prüfen damit
das Verfahren, aber **nicht das Format des Anbieters**: Benennt Finnhub ein
Feld um, bleiben sie grün, und der Tageslauf liefert `INSUFFICIENT_DATA`.
Diese beiden Dateien sind die einzige Stelle, an der eine solche Änderung
auffällt (Audit-2-Maßnahme A2-M7, Befund A2-F008).

Es geht **nur** um das Format. Dass ein Termin auf den 28.10.2026 fällt oder
dass 54 Analysten AAPL bewerten, ist keine Aussage, die das Projekt trifft.

## Was darin bemerkenswert ist

- Der Kalendereintrag ist ein **zukünftiger** Termin: `epsActual` und
  `revenueActual` sind `null`, die Schätzwerte gesetzt. Genau der Fall, den
  der Earnings-Filter im Laufzeitfenster prüft.
- Die Empfehlungen tragen **vier Monatsstände**, absteigend, und alle fünf
  Votenklassen sind unterschiedlich besetzt — eine Vertauschung von `buy` und
  `hold` fällt daran auf.
- `strongSell` ist überall `0`. Das ist eine **gemeldete** Null, keine
  fehlende. Der Unterschied ist der Grund, warum der Adapter fehlende Felder
  nicht stillschweigend auf 0 setzt.

## Keine Weitergabe von Daten, nur von Format

[ADR 0017](../../../../../../docs/adr/0017-finnhub-fuer-earnings-und-ratings.md)
L8 untersagt die Weitergabe von Finnhub-Daten an Dritte, und dieses
Repository ist öffentlich. Deshalb sind hier **zwei Antworten zu einem
einzigen, überall bekannten Symbol** eingefroren und nicht ein Messlauf über
die Watchliste — Mess-CSV bleiben aus demselben Grund per `.gitignore`
draußen. Ein einzelner Kalendereintrag und ein Votenstand zu AAPL sind ein
Formatbeleg, kein Datenbestand.

## Neu aufzeichnen

Wenn ein Contract-Test bricht, weil Finnhub das Format geändert hat: Die
Kommandos stehen in Doc 14, Zwischenschritt „Contract-Antworten einfrieren".
Sie laufen auf dem Server, weil dort der Schlüssel liegt.

**Ändert sich dabei die Struktur, ist das eine Aussage** — der Diff gehört
angesehen und der Adapter nachgezogen, bevor die neue Datei eingecheckt wird.
Die *Werte* ändern sich bei jedem Abruf: Der Termin rückt, die Votenstände
wandern. Das allein ist kein Befund.
