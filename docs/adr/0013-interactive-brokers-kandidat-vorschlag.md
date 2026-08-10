# ADR 0013: Interactive Brokers als nächster Kandidat für Marktdaten -- Spike vorgeschlagen

- Status: Vorgeschlagen
- Datum: 2026-08-10

## Kontext

Gate G3 ist mit NO_GO entschieden (siehe [ADR 0012](0012-gate-g3-strang-a-no-go-non-display-nutzung.md)):
TradingView scheidet als Datenquelle aus, sowohl für den ursprünglich
geplanten CDP-Zugriff als auch für den im Spikebericht
(`spikes/tradingview-cdp/REPORT.md`, Abschnitt "Fallback-Vergleich")
skizzierten Fallback über Alerts/Webhooks bzw. Watchlist-Export -- Letzterer
ist zusätzlich praktisch nicht verfügbar, da das dafür nötige
TradingView-Abonnement nicht besteht (Nutzerangabe, 2026-08-10).

Der Nutzer verfügt über ein bestehendes Marktdaten-Abonnement bei
Interactive Brokers (IBKR) und schlägt IBKR als alternative Datenquelle vor,
mit der Option, auf dem Windows-Server dauerhaft eine angemeldete
IBKR-Konsole (TWS) laufen zu lassen, oder alternativ einen anderen
technischen Weg (z. B. API/IB Gateway) zu nutzen.

IBKR unterscheidet sich von TradingView in zwei für die bisherigen Blocker
relevanten Punkten:

1. **Offizielle, dokumentierte API.** TWS API / IB Gateway sind von IBKR
   selbst für programmatischen Zugriff durch eigene Kunden bereitgestellt --
   kein Auslesen interner, undokumentierter Objekte wie beim
   TradingView-CDP-Ansatz.
2. **Für unbeaufsichtigten Betrieb ausgelegt.** IB Gateway ist als
   headless-fähige Alternative zur vollen TWS-Desktop-Oberfläche gedacht,
   und es existiert ein verbreitetes Drittanbieter-Tool ("IBC" --
   Interactive Brokers Controller) zur Automatisierung des Anmeldevorgangs
   nach einem Neustart. Das adressiert unmittelbar das bei TradingView
   ungelöste Risiko R2 (Session-0-Isolation, Autologon).

Damit ist die Ausgangslage für einen neuen Anlauf strukturell günstiger als
bei TradingView, aber nicht automatisch frei von Lizenzfragen: Markt­daten-
Vereinbarungen von Börsen kennen häufig eine Unterscheidung zwischen
"Display"- und "Non-Display Usage" mit eigener Abo-Kategorie bzw. Gebühr.
Bei IBKR ist das nach bisherigem Kenntnisstand ein **Tarif-/Lizenzthema**,
kein pauschales Verbot wie bei TradingView -- muss aber vor nennenswertem
Implementierungsaufwand geklärt werden, statt es wie im TradingView-Fall bis
nach dem technischen Spike offenzulassen.

## Entscheidung

Der Vorschlag wird als **nächster zu untersuchender Kandidat** aufgenommen.
Dieses ADR ist noch keine Freigabe für einen Spike-Start und keine Freigabe
für Produktivcode -- beides bleibt gesperrt, bis die folgenden Schritte
durchlaufen sind:

1. **Kurze Vorprüfung vor Spike-Start** (kein vollständiger
   Strang-A-artiger Prozess nötig, da andere Ausgangslage, aber keine
   Auslassung): Welche Marktdaten-Abonnements sind auf dem IBKR-Konto aktiv,
   welche Nutzungskategorie (privat/nicht-kommerziell, Display vs.
   Non-Display) deckt sie ab, und deckt sie den geplanten Verwendungszweck
   (automatisiertes Auslesen für den eigenen Screener, keine Weitergabe an
   Dritte) ab. Ergebnis kurz dokumentieren, bevor Spike-Code entsteht.
2. **Explizite Freigabe des Nutzers für den Spike-Start** -- analog zum
   bisherigen Gate-G2-Muster (Sprint-0-Auftrag: "Start des
   TradingView-Spikes bedarf gesonderter Freigabe"). Dieselbe Regel gilt
   sinngemäß für jeden neuen Datenanbieter-Spike.
3. **Spike isoliert unter `spikes/ibkr-marketdata/` (Arbeitstitel)**, analog
   zum bisherigen `spikes/tradingview-cdp/`-Muster: kein Import in/aus
   `backend/src` oder `frontend`, kein Produktivcode. Zu klären u. a.:
   - TWS Desktop vs. IB Gateway als Zugriffspunkt; IBC-Automatisierung für
     unbeaufsichtigten Neustart.
   - Verfügbare Bar-Größen/Auflösungen für die geplante
     195-Minuten-Aggregation (voraussichtlich Aggregation aus kleineren
     nativen Bar-Größen, wie ursprünglich ohnehin für R3/Backfill geplant).
   - Historische Datenabdeckung (5 Jahre, Watchlist-Umfang) und
     Rate-Limits der API.
   - Ob IBKR auch Earnings-/Fundamentaldaten/Optionsketten mit Greeks
     liefert (relevant für F9) oder ob dafür weiterhin separate Anbieter
     nötig sind.
4. **Eigenes Gate/ADR für die produktive Integration** nach Abschluss des
   Spikes, mit denselben zwei getrennten Dimensionen wie bei TradingView
   (technische Stabilität / vertragliche Zulässigkeit) -- nicht vermischt.

## Begründung

Die Lehre aus Gate G2/G3 ist nicht "keine Spikes mehr", sondern
"vertragliche Prüfung nicht erst nach dem vollständigen technischen Spike
nachholen". Bei TradingView entstand ein vollständiger, aufwendiger
technischer Spike, dessen Ergebnis anschließend an einer vertraglichen
Ausschlussklausel scheiterte. Bei IBKR ist die Ausgangslage günstiger
(offizielle API, bestehendes bezahltes Abonnement, für Automatisierung
ausgelegte Infrastruktur), aber genau deshalb soll die kurze Vorprüfung aus
Schritt 1 diesmal *vor* dem Spike stehen, nicht danach.

## Konsequenzen

- Kein Implementierungs- oder Spike-Code entsteht durch dieses ADR selbst.
- Nächster konkreter Schritt liegt beim Nutzer: Ergebnis der kurzen
  Vorprüfung (Schritt 1) und die ausdrückliche Freigabe für den Spike-Start
  (Schritt 2).
- `docs/03 - Roadmap.md` (Sprint 2) und `docs/adr/README.md` sind
  entsprechend als "in Prüfung" statt "TradingView Integration" markiert.
- Gate G3 (TradingView, NO_GO) bleibt von diesem ADR unberührt und wird
  durch einen möglichen IBKR-Spike nicht wieder geöffnet.
