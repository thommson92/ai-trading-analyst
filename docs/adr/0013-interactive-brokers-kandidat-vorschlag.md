# ADR 0013: Interactive Brokers als nächster Kandidat für Marktdaten -- Spike vorgeschlagen

- Status: Angenommen -- Vorprüfung mit GO abgeschlossen, Spike-Start freigegeben (2026-08-11)
- Datum: 2026-08-10 (Vorschlag), 2026-08-11 (Freigabe)

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

## Vorprüfung — Zwischenstand (2026-08-10)

Schritt 1 (kurze Vorprüfung vor Spike-Start) ist teilweise durchgeführt. Wie
bei ADR 0012 werden geprüfter Vertragsinhalt, technische Subsumtion und
Einschätzung getrennt dargestellt; die abschließende Entscheidung trifft
weiterhin der Projektinhaber (siehe "Verantwortlichkeiten"-Abschnitt,
analog Abschnitt 2.3 der Gate-G3-Entscheidungsvorlage).

### Geprüfte Quelle

- Dokument: "Market Data API Supplement to the GFIS Subscriber Agreement"
  -- die zusätzliche, speziell für API-Zugriff geltende Vereinbarung, die
  die allgemeine GFIS Subscriber Agreement (Formular 3089) ergänzt.
- Herkunft: vom Nutzer am 2026-08-10 direkt aus dem eigenen IBKR-Konto
  (Marktdaten-Abonnement-Bereich) im Volltext bereitgestellt -- kein
  öffentlich zugängliches Dokument, daher nicht extern verlinkbar.
- Diese Vereinbarung ist bereits akzeptiert (elektronische Signatur laut
  Dokument rechtlich einer handschriftlichen Unterschrift gleichgestellt).

### Vertragsinhalt (wörtliche Kernzitate)

> "The Data that Subscriber accesses through the API is provided to
> Subscriber for trading-related purposes only [...] Subscriber may access
> the Data through the API in order to perform analytics, enter orders, and
> perform other transactions or functions exclusively in connection with
> Subscriber's brokerage account(s) with IBKR and not for any other
> purpose."

Verbotene Nutzungen (Auszug, wörtlich):

> "Publish, disseminate, or redistribute the Data to any third party."

> "Assign, transfer, grant access or use, disclose or otherwise provide, in
> any form whatsoever, the Data accessed through the API to any third
> party, or display it electronically."

> "Create data products based upon or derived from the Data, or use the
> Data to create any index or use the Data to create any other derived
> works that will be disseminated, published, or otherwise provided to
> others."

> "Use Subscriber's access to the Data through the API to develop software
> applications that Subscriber wishes to: (a) sell to third-party users for
> a fee or provide for free, or (b) give to third-party users to generate
> an indirect financial benefit."

Ergänzend (kein Verbot, aber operativ relevant): "The API is a mode of
delivery for Data [...] and is not intended to be used as a substitute for
a data feed. [...] there are fixed limits on the number of simultaneous
data lines and other pacing limitations", sowie ein jederzeitiges,
begründungsfreies Widerrufsrecht von GFIS bezüglich des API-Zugriffs.

### Technische Subsumtion (getrennt vom Vertragsinhalt)

Der für dieses Projekt geplante Verwendungszweck -- automatisiertes
Auslesen von Kursdaten über die offizielle API, lokale Berechnung von
Indikatoren, deterministischer Screener, Backtesting und KI-gestützte
Analyse, ausschließlich zur Unterstützung eigener Handelsentscheidungen des
Kontoinhabers, ohne Weitergabe an Dritte, ohne kommerziellen
Vertrieb -- entspricht wörtlich der ausdrücklich erlaubten Kategorie
"perform analytics [...] exclusively in connection with Subscriber's
brokerage account(s)". Keine der aufgeführten Verbotstatbestände (Weitergabe
an Dritte, elektronische Anzeige für Dritte, Erstellung extern verbreiteter
abgeleiteter Produkte/Indizes, Verkauf oder unentgeltliche Weitergabe der
Software an Dritte) trifft auf den geplanten rein persönlichen Gebrauch zu,
solange das System ausschließlich vom Kontoinhaber selbst und für dessen
eigenes Konto genutzt wird.

Operativ relevant, aber keine rechtliche Hürde: Die pauschalen Hinweise auf
Zeilen-/Pacing-Limits sind für die spätere technische Auslegung
(historischer Backfill, Anzahl gleichzeitiger Marktdatenzeilen) zu
berücksichtigen, ebenso das jederzeitige, begründungsfreie
Widerrufsrecht von GFIS (operationelles Restrisiko, kein Nutzungsverbot).

### Vorläufige Einschätzung (keine Rechtsberatung, keine Entscheidung)

Anders als beim TradingView-Befund in ADR 0012 enthält dieser Vertragstext
eine Klausel, die den geplanten Verwendungszweck **ausdrücklich und
wörtlich als erlaubt benennt** ("perform analytics [...] exclusively in
connection with Subscriber's brokerage account(s)"), statt ihn zu
verbieten. Das entspricht eher Variante (a) ("dokumentierte tragfähige
Grundlage") aus dem für Strang A entwickelten Entscheidungsraster als
Variante (b) (Risikoakzeptanz bei Unklarheit) -- die Bedingungen sind hier
nicht unklar, sondern decken den Fall konkret ab.

Offene Punkte, die vor einer abschließenden Bewertung noch zu klären wären:
- Welche IBKR-Rechtsträgerschaft (z. B. US-LLC vs. europäische
  Tochtergesellschaft) das eigene Konto tatsächlich führt, da dies die
  anwendbare Vertragsfassung bestimmen kann.
- Ob für einzelne, konkret abonnierte Börsen-Feeds zusätzliche,
  börsenspezifische Zusatzvereinbarungen mit eigenen Einschränkungen
  bestehen (im Marktdaten-Bereich des Kontos einsehbar).

**Die abschließende Bewertung (GO/NO_GO für diesen Vorprüfungsschritt) ist
weiterhin eine Entscheidung des Projektinhabers**, nicht von Claude Code --
analog zur Verantwortlichkeitsregelung in Abschnitt 2.3 der
Gate-G3-Entscheidungsvorlage.

## Freigabe des Projektinhabers (2026-08-11)

Der Projektinhaber hat die Vorprüfung ausdrücklich mit **GO** entschieden:
"Basierend auf der aktuellen Lizenz-Situation ist IBKR für mich ein GO."
Damit ist Schritt 1 (Vorprüfung) abgeschlossen -- Grundlage ist Variante (a)
("dokumentierte tragfähige Grundlage") aus dem Entscheidungsraster: die
Klausel "perform analytics [...] exclusively in connection with
Subscriber's brokerage account(s)" aus dem Market Data API Supplement
erlaubt den geplanten Verwendungszweck ausdrücklich, statt ihn zu verbieten.

Zusätzlich hat der Projektinhaber ausdrücklich den **Spike-Start
freigegeben** (Schritt 2): "Hiermit bekommst du meine offizielle Freigabe
für den Spike-Start zum Thema Interactive Brokers."

Die unter "Offene Punkte" genannten Restfragen (konkrete IBKR-
Rechtsträgerschaft des Kontos, ggf. börsenspezifische
Zusatzvereinbarungen) sind mit dieser Freigabe nicht als rechtlich
irrelevant erklärt, sondern bewusst vom Projektinhaber im Rahmen seiner
Risikoeinschätzung mitgetragen -- sie bleiben im Blick, blockieren den
Spike-Start aber nicht mehr.

**Damit sind Schritt 1 und Schritt 2 aus dem "Entscheidung"-Abschnitt oben
erfüllt.** Schritt 3 (Spike isoliert unter `spikes/ibkr-marketdata/`) kann
beginnen. Schritt 4 (eigenes Gate/ADR für die produktive Integration nach
Abschluss des Spikes) bleibt unverändert bestehen -- diese Freigabe ist
keine Freigabe für Produktivcode.

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

- Vorprüfung (Schritt 1) und Spike-Start-Freigabe (Schritt 2) sind erteilt
  (2026-08-11). Der Spike unter `spikes/ibkr-marketdata/` (Schritt 3) darf
  beginnen -- isoliert, kein Import in/aus `backend/src` oder `frontend`,
  kein Produktivcode.
- Schritt 4 (eigenes Gate/ADR für die produktive Integration, mit
  getrennter technischer und vertraglicher Bewertung) bleibt gesperrt, bis
  der Spike abgeschlossen ist -- diese Freigabe deckt ausdrücklich keine
  Produktivintegration ab.
- `docs/03 - Roadmap.md` (Sprint 2) und `docs/adr/README.md` sind
  entsprechend als "IBKR-Spike gestartet" statt "in Prüfung" zu
  aktualisieren.
- Gate G3 (TradingView, NO_GO) bleibt von diesem ADR unberührt und wird
  durch den IBKR-Spike nicht wieder geöffnet.
