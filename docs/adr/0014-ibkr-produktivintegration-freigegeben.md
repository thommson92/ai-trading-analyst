# ADR 0014: Interactive Brokers als produktive Marktdaten-Grundlage freigegeben (Schritt 4 aus ADR 0013)

- Status: Angenommen (Accepted)
- Datum: 2026-08-11

## Kontext

[ADR 0013](0013-interactive-brokers-kandidat-vorschlag.md) hat vier Schritte
festgelegt, bevor IBKR produktiv angebunden werden darf. Schritt 1
(lizenzrechtliche Vorprüfung), Schritt 2 (Freigabe des Spike-Starts) und
Schritt 3 (technischer Spike unter `spikes/ibkr-marketdata/`) sind
abgeschlossen; der Spike endete mit der Empfehlung `GO_WITH_LIMITATIONS` auf
technischer Ebene (`spikes/ibkr-marketdata/REPORT.md`, Abschnitt 12).

Schritt 4 -- ein eigenes Gate für die produktive Integration, mit getrennter
technischer und vertraglicher Bewertung -- war bis zu diesem ADR gesperrt.
Dieses ADR dokumentiert die dazu vom Projektinhaber am 2026-08-11 erteilte
Freigabe.

Damit endet zugleich der Zustand, dass das Projekt seit dem Gate-G3-NO_GO
([ADR 0012](0012-gate-g3-strang-a-no-go-non-display-nutzung.md)) ohne
produktive Marktdatenquelle war. Der bisher einzige `MarketDataProvider` ist
der `FixtureMarketDataProvider` aus Sprint 1B.

## Entscheidung

**Interactive Brokers (TWS API) wird als produktive Marktdaten-Grundlage des
AI Trading Analyst freigegeben.** Die beiden Dimensionen werden -- wie bei
Gate G3 -- getrennt festgehalten und nicht miteinander verrechnet.

### Dimension 1 -- technisch: GO_WITH_LIMITATIONS

Grundlage ist der abgeschlossene Spike (alle acht Fragen live gegen die TWS
des Projektinhabers beantwortet). Der Projektinhaber übernimmt die im Spike
dokumentierten Einschränkungen ausdrücklich als **Betriebs- und
Implementierungsanforderungen**, nicht als offene Punkte:

| # | Akzeptierte Einschränkung | Folge für die Implementierung bzw. den Betrieb |
|---|---|---|
| E1 | Earnings-Termine sind über IBKR nicht verfügbar (`reqFundamentalData`/`CalendarReport` liefert keine nutzbaren Daten) | Eigener Anbieter, eigenes ADR. Bis dahin bleibt der Earnings-Filter (F9, Sprint 3) ohne Datengrundlage -- kein Ersatzwert, keine geschätzten Termine. Kein Blocker für die IBKR-Anbindung. |
| E2 | Nach Server- oder TWS-Neustart ist ein manueller Start bzw. Login nötig; kein Windows-Autologon, kein IB Gateway/IBC | Die Anwendung muss eine nicht erreichbare TWS als **normalen Betriebszustand** behandeln: klarer Fehler, keine erfundenen Daten, kein stiller Fallback. Die Nichtverfügbarkeit zwischen Sonntagsneustart und manuellem Montagsstart ist bewusst akzeptiert. |
| E3 | Historischer Backfill benötigt Chunking und kontrolliertes Pacing; eine einzelne Großanfrage über 5 Jahre scheitert am Client-Timeout | Backfill ausschließlich als resumierbarer, in Zeitfenster zerlegter Batch-Job mit Pacing zwischen den Anfragen -- nie als eine Großanfrage. |
| E4 | Fundamentaldaten-Verfügbarkeit ist pro Report-Typ zu prüfen (`RESC` funktioniert, `CalendarReport` nicht) | Keine pauschale Annahme "IBKR liefert Fundamentaldaten". Jeder genutzte Report-Typ wird einzeln verifiziert; eine inhaltsleere Antwort gilt als Fehlschlag, nicht als Erfolg. |
| E5 | Die weiteren im Spike dokumentierten technischen Befunde (Event-Loop-Verhalten ab Python 3.14, ungefiltertes Konto-Logging der Fremdbibliothek, Client-ID-Kollisionen, Strike-Auswahl anhand des tatsächlichen Kurses) | Werden als Implementierungsanforderungen übernommen; die Belege stehen in REPORT.md, Abschnitte 3, 8 und 10. |

Zusätzlich gilt unverändert die Betriebsvorgabe aus ADR 0013: **"Read-Only
API" darf in der TWS nicht aktiviert werden**, solange dieselbe Instanz von
der Trade Automation Toolbox (TAT) für echte Orderübermittlung genutzt wird.
Die Lesebeschränkung des Analyzers ist im eigenen Code zu verankern (keine
ordererzeugenden API-Aufrufe), nicht über diesen TWS-weiten Schalter. Der
Analyzer nutzt eine eigene, konfigurierbare Client-ID (Spike: 17), die sich
von der von TAT genutzten (99) unterscheiden muss.

### Dimension 2 -- vertraglich: GO

Der Projektinhaber hat die vertragliche Zulässigkeit ausdrücklich mit **GO**
entschieden. Grundlage ist die bereits in ADR 0013 geprüfte und zitierte
Klausel des "Market Data API Supplement to the GFIS Subscriber Agreement",
die den geplanten Verwendungszweck wörtlich erlaubt:

> "Subscriber may access the Data through the API in order to perform
> analytics, enter orders, and perform other transactions or functions
> exclusively in connection with Subscriber's brokerage account(s) with
> IBKR"

Der Projektinhaber hält dazu fest, dass IBKR die persönliche Nutzung der
abonnierten Marktdaten auch in einer eigenen Non-Visual-Anwendung bzw. einem
Trading-Bot erlaubt. Diese Bewertung ist eine Entscheidung des
Projektinhabers, keine Rechtsberatung durch das Projekt oder durch Claude
Code.

### Dokumentierte Annahmen und Restrisiken

Die folgenden Punkte sind mit dieser Freigabe **nicht als geklärt erklärt**,
sondern als bewusst getragene Annahmen bzw. Restrisiken festgehalten. Sie
blockieren die Integration nicht:

| # | Annahme / Restrisiko | Wirkung, falls sie sich als falsch erweist |
|---|---|---|
| A1 | Die konkrete IBKR-Rechtsträgerschaft des Kontos (z. B. US-LLC vs. europäische Tochtergesellschaft) ändert nichts an der zitierten Klausel | Anwendbare Vertragsfassung könnte abweichen -- dann ist dieses ADR neu zu bewerten. |
| A2 | Für die konkret abonnierten Börsen-Feeds bestehen keine zusätzlichen, börsenspezifischen Einschränkungen | Einzelne Feeds könnten enger reguliert sein als das allgemeine Supplement. |
| A3 | Die Nutzung bleibt dauerhaft rein persönlich (kein Dritter erhält Zugriff, keine Weitergabe von Daten oder abgeleiteten Produkten, keine Weitergabe der Software) | Die Erlaubnisklausel greift nicht mehr; die Verbotstatbestände des Supplements wären einschlägig. |
| A4 | GFIS macht von seinem jederzeitigen, begründungsfreien Widerrufsrecht bezüglich des API-Zugriffs keinen Gebrauch | Operationelles Risiko: Datenquelle fällt weg. Die Provider-Abstraktion (`MarketDataProvider` als Protokoll) hält den Austausch offen. |
| A5 | Die technische Machbarkeit gilt weiterhin bei größerem Watchlist-Umfang als den im Spike getesteten 10 Symbolen | Pacing-/Zeilenlimits könnten früher greifen als angenommen -- im ersten produktiven Lauf zu beobachten. |

Nach der Systematik aus ADR 0013 stützt sich die Freigabe damit auf Variante
(a) des Entscheidungsrasters ("dokumentierte tragfähige Grundlage"), nicht
auf eine Risikoakzeptanz bei unklarer Rechtslage.

## Begründung

Der Spike hat alle acht Fragen live gegen die reale Umgebung beantwortet, in
der die Anwendung später laufen soll -- einschließlich der Koexistenz mit der
bereits produktiv laufenden Anwendung TAT. Die verbliebenen Einschränkungen
sind sämtlich **bekannt, benannt und mit einer konkreten Konsequenz
versehen**; keine davon betrifft den Kernpfad (Watchlist-Kurse,
195-Minuten-Kerzen, historische Tiefe, Erkennung abgeschlossener Kerzen).

Die Alternative -- weiter zu warten, bis auch E1 (Earnings) und E2
(unbeaufsichtigter Betrieb) gelöst sind -- würde den Kernnutzen des Projekts
ohne Not blockieren: Der Earnings-Filter ist ein Sprint-3-Thema und der
manuelle Montagsstart ist bereits gelebte Praxis für eine andere Anwendung
desselben Nutzers auf demselben Server.

Die Trennung der beiden Dimensionen wird beibehalten, weil genau ihre
Vermischung im TradingView-Fall zu dem teuren Umweg geführt hat: dort war das
technische Ergebnis positiv und die vertragliche Prüfung fiel danach negativ
aus (ADR 0012).

## Konsequenzen

- **Schritt 4 aus ADR 0013 ist abgeschlossen.** Ein
  `IbkrMarketDataProvider` unter `backend/src/ai_trading_analyst/infrastructure/`
  darf implementiert werden. Sprint 2 ist nicht mehr gegated.
- Die Implementierung ist eine **Neuimplementierung**, kein Übernehmen des
  Spike-Codes. Der Spike bleibt als eingefrorenes Nachweisartefakt unter
  `spikes/ibkr-marketdata/` erhalten (siehe dortiges README, Abschnitt
  "Status: eingefroren").
- `MarketDataProvider` bleibt ein Protokoll im Domain Layer; IBKR ist ein
  austauschbarer Infrastructure-Adapter. Der Domain Layer bekommt keine
  Kenntnis von `ib_async`, TWS, Client-IDs oder Ports -- die
  Schichtgrenzen-Tests werden um `ib_async` erweitert.
- Verbindungsparameter (Host, Port, Client-ID) sind Konfiguration, keine
  Geheimnisse und keine Konstanten im Code. Konto-Kennungen werden vor
  Logging und Persistenz maskiert.
- E1 macht einen **eigenen Workstream** nötig: Auswahl eines
  Earnings-Anbieters mit eigenem ADR. Er ist erforderlich, aber kein Blocker
  für die IBKR-Anbindung.
- Der Inhalt der `RESC`-Antwort (Analystenschätzungen, 325 KB XML) ist
  weiterhin ungeprüft und bleibt in der ADR-Übersicht als offene Entscheidung
  geführt, bis er inhaltlich bestätigt ist.
- Windows-Autologon bleibt eine eigenständige, weiterhin **nicht getroffene**
  Entscheidung -- unverändert gegenüber Gate G3/Strang B.
- Gate G3 (TradingView, NO_GO) wird durch dieses ADR nicht berührt und nicht
  wieder geöffnet.
- Ändern sich die zitierten IBKR-Bedingungen wesentlich, oder erweist sich
  eine der Annahmen A1--A3 als falsch, ist dieses ADR neu zu bewerten (ein
  neues ADR, keine rückwirkende Änderung dieses Dokuments).
