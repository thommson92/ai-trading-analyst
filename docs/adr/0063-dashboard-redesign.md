# ADR 0063: Dashboard-Redesign — sechs Seiten, Seitenleiste, Design-Tokens, gleichwertig auf dem Smartphone

- Status: Vorgeschlagen
- Datum: 2026-09-18

## Kontext

Das Dashboard aus Sprint 6 hat vier Ansichten und einen Leser
([ADR 0049](0049-dashboard-mvp-nur-lan.md)). Seit
[ADR 0060](0060-dashboard-ausserhalb-des-servers.md) läuft es außerhalb des
Servers, und der Inhaber liest es auf dem Smartphone. Zwei Befunde vom
2026-09-18:

1. **Die Berichtsseite ist ein Baum.** `Berichtsdokument.tsx` rendert die
   achtzehn Abschnitte des gespeicherten Dokuments rekursiv als
   Schlüssel-Wert-Liste. Das war gewollt — ein neues Feld sollte nie still
   verschwinden —, ergibt aber bei einem Kandidaten mit zwölf
   Signalkombinationen und drei Horizonten eine Seite von 16.000 Pixeln Höhe,
   die ein Drittel der Breite nutzt, rohe Feldnamen und UUIDs zeigt.
2. **Es fehlt, was der Betrieb inzwischen braucht:** eine Liste aller Läufe
   mit Datumswahl, eine Liste aller Aktien, eine Kandidatenkarte, die sagt,
   worauf es ankommt, ein interaktiver Chart, eine Navigation zwischen den
   Bereichen, ein Layout für das Smartphone.

Die Entscheidungen dazu hat der Inhaber am 2026-09-18 in fünf Fragerunden
getroffen. Dieses ADR hält die Gestaltungsentscheidungen fest. Die
Datenseite (Einzelepisoden des Signal-Backtests; Kurzlisten und der
Status der Wiederholsperre), die Chartbibliothek sowie Build und Meldung
werden in eigenen ADRs festgehalten, jeweils bevor ihre Phase beginnt.

## Entscheidung

1. **Sechs Seiten.** Übersicht (`/`, der letzte Lauf), Tagesläufe
   (`/laeufe/?id=`), Aktien (`/aktien/`), Einzelaktie
   (`/aktie/?symbol=&lauf=&messung=&episode=`), Kandidatenbericht
   (`/bericht/?id=&tab=`), Backtest-Explorer
   (`/backtests/?ansicht=&symbol=&messung=`). Adressiert wird weiterhin über
   Query-Parameter, nicht über dynamische Segmente — der statische Export
   verlangt das ([ADR 0052](0052-dashboard-als-statischer-export.md)).
2. **Seitenleiste links,** unter 64rem eingeklappt und über einen Menüknopf
   als Overlay zu öffnen. Ein DOM für alle Breiten.
3. **Dunkel ist der Standard, hell die Wahl des Lesers.** Die Wahl liegt als
   `data-thema` am Wurzelelement und wird im `localStorage` gemerkt. Die
   Systemeinstellung spielt keine Rolle mehr. Ein Inline-Skript gegen den
   kurzen dunklen Moment vor der gemerkten Wahl gibt es **nicht**: Es
   verstieße gegen die Zusage, auf der die Richtlinie in `public/_headers`
   steht (`sicherheitsheader.test.ts`).
4. **Design-Tokens statt Bibliothek.** Drei Ebenen in `styles/tokens.css`
   — Primitive, Semantik, Komponenten. Bauteile greifen nur auf Semantik und
   Komponenten zu. Keine UI-Bibliothek, kein Tailwind: Die CSP bleibt, die
   Abhängigkeiten bleiben, und das Audit hat mit `postcss` schon eine rote
   Zeile.
5. **Das Smartphone ist gleichwertig.** Tabellen werden unter 40rem per CSS
   zu Karten (`td[data-label]`), nicht zu einem zweiten Layout im DOM.
   Charts sind mit Touch zoom- und schwenkbar.
6. **Prominenz in der Kandidatenkarte:** zuerst die Nähe zum Berichtstermin
   und der beste Put-Vorschlag, in zweiter Reihe Empfehlung, beide Scores
   und die Signalbuchstaben. Der Inhaber hat das so gewichtet; die Meldung
   ([ADR 0055](0055-put-vorschlag-und-signalzahl-in-der-ergebnismeldung.md))
   sagt dasselbe.
7. **Der Bericht bekommt je Abschnitt eine eigene Darstellung** — Kopf mit
   Kurs, Earnings, Put, Empfehlung, Scores, Signalen; sieben Reiter. Der
   generische Baum bleibt als Rückfall: Jedes Feld, das eine Darstellung
   nicht ausdrücklich verarbeitet, erscheint unter „Weitere Felder", jeder
   unbekannte Abschnitt als Baum. Die Zusage „nichts verschwindet still"
   bleibt damit — sie wird nur getestet statt erzwungen.
8. **Quellen-URLs werden klickbar,** aber nur über eine Hilfsfunktion, die
   ausschließlich `https://` durchlässt; alles andere bleibt Text. Der
   Sicherheitstest wird um genau diese eine Form erweitert, nicht gelockert.
   `Referrer-Policy: no-referrer` bleibt.

## Konsequenzen

- Die vier bestehenden Seiten werden schrittweise abgelöst; je Phase ein
  Feature-Branch und ein PR nach `dev`, nach Abnahme durch den Inhaber.
- Das Frontend bleibt ohne Geschäftslogik: Es stellt dar, filtert, sortiert
  und zählt exportierte Werte. Es bewertet nichts und rechnet keinen Score.
- Wer hell gewählt hat, sieht beim Laden kurz dunkel. Bekannt, akzeptiert.
- Die Namen der ersten Token-Fassung (`--grund`, `--schrift`, `--ema20` …)
  bleiben gültig, damit die Backtest-Bauteile ohne Umbau weiterlaufen.
