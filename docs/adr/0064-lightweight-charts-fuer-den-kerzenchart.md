# ADR 0064: Lightweight Charts für den Kerzenchart der Einzelaktie

- Status: Angenommen
- Datum: 2026-09-19

## Kontext

Die Einzelaktie des Redesigns ([ADR 0063](0063-dashboard-redesign.md)) soll
den Kurs als Kerzen zeigen, mit Zoom und Verschieben per Maus und Touch, die
Episoden-Einstiege des Signal-Backtests ([ADR 0061](0061-einzelepisoden-des-signal-backtests.md))
als anklickbare Marker, und nach Klick das Horizontfenster samt Kurspfad.
Der bisherige Kursverlauf stand in `recharts`: eine Schlusslinie, keine
Kerzen, kein Verschieben, kein Kreuzcursor. Der Export liefert seit jeher
Open, High, Low und Close je 195-Minuten-Kerze; nur die Darstellung hat sie
nicht genutzt.

Die Auslieferung außerhalb des Servers ([ADR 0060](0060-dashboard-ausserhalb-des-servers.md))
setzt Grenzen: `public/_headers` erlaubt Skripte nur von `self`, keine
Webfonts, keine Bilder von außen, keine Worker. Eine Bibliothek muss sich
also bündeln lassen und ohne Netz auskommen.

Der Inhaber hat am 2026-09-18 entschieden: nur Kerzen, Lightweight Charts.

## Entscheidung

1. **`lightweight-charts` (TradingView, Apache-2.0), Version 5**, gebündelt
   über Next. Canvas-basiert, rund 45 KB, mit Kerzen, Linien, Markern,
   Preislinien, mehreren Panes und einer Plugin-API für eigene Zeichnungen.
   `recharts` bleibt für Balken und Verteilungen.
2. **Attribution wie die Lizenz sie verlangt.** Die Bibliothek zeichnet ihr
   Logo mit Link selbst (`layout.attributionLogo: true`); dazu steht unter
   dem Chart der Textvermerk „Chart: TradingView Lightweight Charts™". Kein
   handgeschriebenes externes `href` — der Sicherheitstest bleibt unberührt.
   Der Lizenztext liegt unter `frontend/LIZENZHINWEISE.md`.
3. **Kein Bezug zu ADR 0012.** Dort ging es um TradingView als
   **Datenquelle** und deren Non-Display-Verbot. Hier fließen keine
   TradingView-Daten; die Bibliothek ist quelloffen und zeichnet, was der
   eigene Export liefert.
4. **Aufbau:** Pane 0 mit Kerzen, EMA 5 und EMA 20 (fehlende Warmup-Werte
   als Lücke, nicht als Null); Pane 1 mit RSI und RSI-Durchschnitt und
   Preislinien bei 30, 50, 70. Marker je Episoden-Einstieg (`belowBar`,
   Pfeil, gefärbt nach der Rendite des gewählten Horizonts, grau wenn der
   Horizont nicht erreicht wurde) und ein Kreis an der Entscheidungskerze
   des Laufs, aus dem der Leser kommt (`?lauf=`).
5. **Horizontfenster als eigenes Primitiv** (`ISeriesPrimitive`): Rechtecke
   gibt es in der Bibliothek nicht; die Fläche Einstieg … Einstieg + H wird
   je Zeichnen aus der Zeitachse gerechnet und folgt damit Zoom und
   Verschieben. Dazu eine Linienserie für den Kurspfad nach dem Einstieg.
   Rückfall, falls das Primitiv Ärger macht: nur der Pfad.
6. **Zeit als Epochensekunden.** Episoden werden über `entry_at` mit den
   Kerzen verbunden — als Zahl, nie als Zeichenkette (ADR 0061, Entscheidung
   2). Einstiege ohne passende exportierte Kerze werden gezählt und
   gemeldet, nicht verschluckt.
7. **Farben aus den Tokens.** Die Bibliothek kennt keine CSS-Variablen; die
   Farben werden beim Aufbau und bei jedem Themenwechsel aus
   `getComputedStyle` gelesen.
8. **Tests ohne Canvas.** Die Abbildungen (`lib/chartdaten.ts`) sind reine
   Funktionen und vollständig getestet; der Chart selbst wird mit einer
   Attrappe der Bibliothek geprüft — nur darauf, dass er sie richtig
   anspricht.

## Konsequenzen

- Eine neue Abhängigkeit im Frontend; `npm audit` läuft wöchentlich darüber.
- `Kursverlauf.tsx` und `Backtestansicht.tsx` sind abgelöst; der
  Optionsbacktest steht unverändert in einer eigenen Karte.
- Die Chart-Seite wächst um das Bündel der Bibliothek; Ziel aus dem Plan:
  unter 300 KB JS gzip — nachzumessen in Phase 8.
- Was nicht gebaut wird: Folgetrigger und verworfene Entscheidungspunkte im
  Chart (Entscheidung des Inhabers), Linienchart als Alternative.
