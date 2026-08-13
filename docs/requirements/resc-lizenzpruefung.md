# Prüfung: Darf RESC verwendet werden?

Zu klären ist eine einzige Frage: Deckt die Vertragslage die geplante
Verarbeitung der über `reqFundamentalData(reportType='RESC')` bezogenen
Daten?

**Status: offen.** Bis zu einer belastbaren Freigabe wird RESC **nicht** als
produktive Datenquelle eingeplant oder implementiert. Kein Blocker für den
`IbkrMarketDataProvider`, den TWS-End-to-End-Test oder die übrigen
Sprint-2-Arbeiten — diese nutzen ausschließlich Marktdaten, deren Bewertung
in [ADR 0014](../adr/0014-ibkr-produktivintegration-freigegeben.md) getroffen
ist.

Dieses Dokument ist keine Rechtsberatung. Es trennt, was **belegt** ist, von
dem, was **noch zu erheben** ist, und trifft ausdrücklich keine Auslegung
dort, wo die Grundlage fehlt.

## Warum überhaupt

ADR 0014 stützt sich auf diese Klausel:

> „Subscriber may access the Data through the API in order to perform
> analytics, enter orders, and perform other transactions or functions
> **exclusively in connection with Subscriber's brokerage account(s)** with
> IBKR"

Sie stammt aus dem **Marktdaten**-Abonnement. RESC ist keine Marktdatenquelle,
sondern redaktioneller Research-Inhalt, der über ein eigenes Abonnement
bereitgestellt wird und von einem Dritten stammt. Ob diese Klausel für RESC
gilt oder ob gesonderte Bedingungen greifen, ist genau die offene Frage.

Sie wird ernst genommen, weil dieselbe Frage die TradingView-Anbindung
gekippt hat: technisch machbar, vertraglich nicht zulässig
([ADR 0012](../adr/0012-gate-g3-strang-a-no-go-non-display-nutzung.md)).

---

## 1. Der konkrete Vertragsgegenstand

### 1.1 Belegt (aus dem eigenen Abruf vom 2026-08-12)

| Angabe | Wert | Beleg |
|---|---|---|
| Zugriffsweg | IBKR TWS API über `ib_async` 1.0.3, Aufruf `IB.reqFundamentalData(contract, 'RESC')` | [`spikes/resc-schema/probe_resc.py`](../../spikes/resc-schema/probe_resc.py) |
| Reporttyp | `RESC` | ebenda |
| Kontrakt | `Stock(symbol, 'SMART', 'USD')`, qualifiziert über `qualifyContracts` | ebenda |
| Antwortformat | XML, Wurzelelement `REarnEstCons`, ca. 325 KB je Symbol | [`RESULT.md`](../../spikes/resc-schema/RESULT.md) |
| Verbindung | eigene TWS des Projektinhabers, `127.0.0.1:7496`, eigenes Konto | Betriebsdoku ADR 0014 |

**Hinweise auf den Rechteinhaber — Indizien, keine Feststellung:**

- Wurzelelement `REarnEstCons` = *Reuters Earnings Estimates Consensus*.
- `Sector@set="R"` — Sektorklassifikation im Reuters-Schema.
- `SecId@type="RIC"` — *Reuters Instrument Code*.
- `ib_async` dokumentiert `RESC` als „Analyst Estimates".

Das deutet stark auf Reuters/Refinitiv (heute LSEG) als Urheber der Inhalte
hin. **Wer der Rechteinhaber vertraglich ist und über welches Abonnement die
Daten bereitgestellt werden, ist damit nicht festgestellt** — das steht in
den Dokumenten unter 1.2.

### 1.2 Noch zu erheben — nur im Client Portal einsehbar

Diese Angaben liegen ausschließlich im Konto des Projektinhabers. Sie werden
hier **nicht geraten**: Ein erfundener Dokumenttitel wäre schlimmer als eine
Lücke, weil er wie ein Beleg aussieht.

| # | Angabe | Wo nachzusehen | Erhoben am | Wert |
|---|---|---|---|---|
| V1 | IBKR-Rechtsträger (z. B. IBKR LLC, IB Ireland Ltd., IB Central Europe) | Client Portal → Settings → Account Settings → *Account Type/Configuration*; steht auch im Kopf jedes Kontoauszugs | | |
| V2 | Exakter Name des Research-/Estimates-Abonnements | Client Portal → Settings → **Research Subscriptions** (getrennt von *Market Data Subscriptions*) | | |
| V3 | Genannter Datenlieferant / Rechteinhaber | ebenda, in der Beschreibung des Abonnements | | |
| V4 | Beim Abschluss akzeptierte Bedingungen — **Titel, Version, Datum, Fundstelle** | Client Portal → Settings → *Agreements and Disclosures*; dort die zu V2 gehörende Vereinbarung | | |
| V5 | Endnutzerbedingungen des Datenlieferanten (eigenes Dokument, oft PDF eines Dritten) | verlinkt aus V4 | | |
| V6 | TWS-API-Lizenzbedingungen | bei der API-Installation zugestimmt; auch auf der IBKR-Website | | |

**Wenn V5 nicht auffindbar ist, ist das selbst ein Ergebnis.** Es bedeutet,
dass die Nutzung auf einer Vermutung beruht — und löst Schritt 3 aus.

Beim Lesen dieser Dokumente helfen diese Suchbegriffe:

| Thema | Wonach suchen |
|---|---|
| Anzeige | `display`, `personal use`, `internal use`, `Non-Professional` |
| Maschinelle Nutzung | `non-display`, `automated`, `machine readable`, `algorithmic`, `trading system`, `black box` |
| Speicherung | `store`, `retain`, `cache`, `database`, `warehousing`, `copy` |
| Abgeleitete Daten | `derived data`, `derived works`, `create indices`, `benchmark`, `modify`, `combine` |
| Weitergabe | `redistribute`, `third party`, `publish`, `disseminate`, `make available` |

---

## 2. Prüftabelle

Auszufüllen mit den **gefundenen Nachweisen**, nicht mit Einschätzungen. Der
Stand unten ist der heutige.

| Nutzungsart | Ergebnis | Dokument/Fundstelle | Wörtliche Klausel | Begründung |
|---|---|---|---|---|
| Abruf über die TWS API | **UNKLAR** | — | — | Grundlage (V2–V6) noch nicht erhoben. Die in ADR 0014 zitierte API-Klausel stammt aus dem Marktdaten-Abo; ob sie Research-Inhalte einschließt, ist nicht belegt. |
| Automatisierte Non-Visual-Auswertung | **UNKLAR** | — | — | dito. Genau der Punkt, an dem TradingView gescheitert ist. |
| Lokale dauerhafte Speicherung | **UNKLAR** | — | — | dito. Doc 10 verlangt unveränderliche, nachvollziehbare Analysen — Speicherung ist keine Option, sondern Voraussetzung. |
| Ableitung eigener Scores und Signale | **UNKLAR** | — | — | dito. |
| Anzeige im ausschließlich persönlichen Dashboard | **UNKLAR** | — | — | dito. Voraussichtlich der unkritischste Punkt, aber unbelegt. |
| Keine Weitergabe an Dritte | **bestätigt (Stand 2026-08-12)** | eigener Code | — | Keine Weitergabe, keine Veröffentlichung, kein externer Zugriff. Das Dashboard ist nicht von außen erreichbar; F12 (externer Zugriff) ist nicht umgesetzt. **Kommt F12, ist diese Zeile neu zu bewerten.** |

Zu unterscheiden ist beim Ausfüllen zwischen **ausdrücklicher Erlaubnis**,
**ausdrücklichem Verbot** und **fehlender oder mehrdeutiger Regelung**. Der
dritte Fall bleibt `UNKLAR` und wird nicht zugunsten der Nutzung ausgelegt —
sonst wäre die TradingView-Entscheidung inkonsequent.

---

## 3. Anfrage an IBKR

Ausgelöst, sobald ein erforderlicher Punkt `UNKLAR` bleibt oder V5 nicht
auffindbar ist. **Nach heutigem Stand ist der Fall eingetreten**, weil die
Grundlage noch nicht erhoben ist.

Der fertige Entwurf steht in
[`resc-ibkr-anfrage.md`](resc-ibkr-anfrage.md). Er ist vom Projektinhaber
aus dem eigenen Konto abzusenden (Client Portal → Help → Secure Message
Center), möglichst an die für **API- und Market-Data-/Research-Lizenzierung**
zuständige Stelle.

Eine allgemeine technische Supportantwort ohne Bezug auf die
Vertragsbedingungen gilt **nicht** als Freigabe.

---

## 4. Entscheidungsregel

| Ergebnis | Bedingung |
|---|---|
| **GO** | Alle erforderlichen Nutzungsarten sind ausdrücklich durch die Bedingungen oder durch eine schriftliche, auf den konkreten Anwendungsfall bezogene Bestätigung abgedeckt. |
| **GO_WITH_LIMITATIONS** | Nutzung erlaubt, aber nur unter konkreten Einschränkungen, die technisch und betrieblich umsetzbar sind. Die Einschränkungen werden wie E1–E5 in ADR 0014 einzeln aufgeführt. |
| **NO_GO** | Eine erforderliche Nutzung ist verboten. |
| **NO_GO mangels belastbarer Grundlage** | Bedingungen fehlen, bleiben widersprüchlich, oder IBKR kann die erforderlichen Rechte nicht bestätigen. |

**Ein angenommenes Restrisiko genügt bei RESC nicht.** Ohne belastbare
Freigabe wird RESC nicht produktiv verwendet. Das unterscheidet diese
Entscheidung von der Marktdatenbewertung in ADR 0014, wo der Projektinhaber
bewusst eine eigene Einschätzung getroffen hat.

---

## 5. Fachliches Gate — erst nach Lizenz-GO

Erst bei `GO` oder `GO_WITH_LIMITATIONS` läuft die Inhaltsprüfung
kontrolliert über alle 192 Watchlist-Symbole. **Vorher kein Lauf gegen die
gesperrte Quelle.** Zu liefern sind dann mindestens:

- Abdeckungsquote je benötigtem Feld,
- Aktualität und Alter der Daten,
- Anteil leerer oder unvollständiger `Recommendations`-Blöcke — bei zwei
  geprüften Symbolen fehlte er schon bei einem (`WMT`),
- Konsistenz der Werte,
- API-Fehler und Verhalten an den Anfragegrenzen,
- reproduzierbare Roh- und Zusammenfassungsergebnisse **ohne Kontodaten**.

## Wann das ADR entsteht

Das ADR zur F9-Datenquelle wird erst geschrieben, wenn vorliegen:

1. Lizenzentscheidung zu RESC,
2. fachliche RESC-Abdeckung, sofern lizenzrechtlich erlaubt,
3. Anbieter-Matrix für Earnings und gegebenenfalls Ratings/Kursziele,
4. Kosten und Anfragegrenzen für 192 Symbole bei täglicher Nutzung.

Fällt die Lizenzprüfung negativ aus, werden Analystenratings und Kursziele
wie die Earnings-Termine als **externe** Datenquelle behandelt; die
Anbieterevaluation berücksichtigt das von vornherein als Möglichkeit.
