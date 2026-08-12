# Prüfliste: Darf RESC verwendet werden?

Zu klären ist eine einzige Frage: Deckt die vorhandene Vertragslage die
geplante Verarbeitung der über `reqFundamentalData(reportType='RESC')`
bezogenen Reuters-Daten?

**Status: offen.** Bis zur Klärung wird RESC **nicht** als produktive
Datenquelle eingeplant oder implementiert. Kein Blocker für den
`IbkrMarketDataProvider`, den TWS-End-to-End-Test oder die übrigen
Sprint-2-Arbeiten — diese betreffen ausschließlich Marktdaten, deren
Bewertung in [ADR 0014](../adr/0014-ibkr-produktivintegration-freigegeben.md)
bereits getroffen ist.

Diese Liste ist keine Rechtsberatung. Sie sagt, wo nachzusehen ist und
welche Formulierungen worauf hindeuten. Die Bewertung trifft der
Projektinhaber.

## Warum überhaupt

Die Marktdatenfrage ist entschieden. ADR 0014 stützt sich auf diese Klausel:

> „Subscriber may access the Data through the API in order to perform
> analytics, enter orders, and perform other transactions or functions
> **exclusively in connection with Subscriber's brokerage account(s)** with
> IBKR"

**RESC ist aber keine Marktdatenquelle.** Es sind redaktionelle
Research-Inhalte von Reuters/Refinitiv, die über ein eigenes Abonnement
bereitgestellt werden. Ob die oben zitierte Klausel für sie gilt oder ob
gesonderte Bedingungen greifen, ist offen — und genau diese Unterscheidung
ist der Kern der Prüfung.

Die Frage wird ernst genommen, weil dieselbe Frage die
TradingView-Anbindung gekippt hat: technisch machbar, vertraglich nicht
zulässig ([ADR 0012](../adr/0012-gate-g3-strang-a-no-go-non-display-nutzung.md)).
Ein zweites Mal auf einer Quelle aufzubauen, die vertraglich nicht trägt,
wäre vermeidbarer Aufwand.

## Wo nachzusehen ist

| # | Dokument | Wo |
|---|---|---|
| D1 | Zugestimmte Abo-Bedingungen für den Research-Dienst | Client Portal → Settings → **Research Subscriptions**; dort die beim Abschluss akzeptierte Vereinbarung öffnen |
| D2 | Market Data Subscriber Agreement (das aus ADR 0014) | Client Portal → Settings → Market Data Subscriptions |
| D3 | Reuters-/Refinitiv-Endnutzerbedingungen | verlinkt aus D1; oft ein eigenes PDF eines Drittanbieters, nicht von IBKR |
| D4 | IBKR Client Agreement, Abschnitt zu Marktdaten und Research | Client Portal → Settings → Agreements and Disclosures |
| D5 | TWS-API-Lizenzbedingungen | bei der API-Installation zugestimmt |

**Wenn D1 oder D3 nicht auffindbar sind, ist das selbst ein Ergebnis** — es
bedeutet, dass die Nutzung auf einer Vermutung beruht. Dann bei IBKR
schriftlich nachfragen und die Antwort hier festhalten.

## Die fünf Nutzungsarten

Für jede Zeile ist zu prüfen, ob die Vertragslage sie trägt. Die mittlere
Spalte beschreibt, was dieses Projekt tatsächlich vorhat — nicht mehr.

| # | Nutzungsart | Was wir konkret tun wollen | Wonach suchen |
|---|---|---|---|
| N1 | **Persönliche Anzeige** | Kursziel und Empfehlungsverteilung im eigenen Dashboard sehen, nur für den Projektinhaber | `display`, `personal use`, `internal use`, `Non-Professional` |
| N2 | **Automatisierte Non-Visual-Verarbeitung** | Werte maschinell abrufen und auswerten, ohne dass sie ein Mensch ansieht | `non-display`, `automated`, `machine readable`, `black box`, `algorithmic`, `trading system` |
| N3 | **Lokale Speicherung** | Antworten in der eigenen Datenbank ablegen, mit Abrufzeitpunkt, dauerhaft (Doc 10: Analysen sind unveränderlich und nachvollziehbar) | `store`, `retain`, `cache`, `database`, `warehousing`, `copy` |
| N4 | **Ableitung eigener Signale** | Aus Kursziel und Empfehlungen einen eigenen Score errechnen, der ins Gesamtergebnis eingeht | `derived data`, `derived works`, `create indices`, `benchmark`, `modify`, `combine` |
| N5 | **Veröffentlichung oder Weitergabe** | **Nichts.** Keine Weitergabe an Dritte, keine Veröffentlichung, kein externer Zugriff auf das Dashboard | `redistribute`, `third party`, `publish`, `disseminate`, `make available` |

N5 steht bewusst mit „nichts" da: Solange das Dashboard nur der
Projektinhaber erreicht, ist das die unkritischste Zeile. Sie wird
kritisch, sobald F12 (externer Zugriff auf das Dashboard) kommt — dann ist
diese Prüfung zu wiederholen.

## Wie die Antwort zu lesen ist

| Befund | Bedeutung |
|---|---|
| Ausdrückliche Erlaubnis für den jeweiligen Zweck | **GO** für diese Nutzungsart |
| Erlaubnis „in connection with Subscriber's brokerage account(s)" **und** RESC fällt nachweislich unter dieselbe Vereinbarung | **GO**, mit Beleg, welche Vereinbarung das ist |
| Ausdrückliches Verbot von Non-Display-Nutzung, Speicherung oder abgeleiteten Daten | **NO_GO** für diese Nutzungsart — wie bei TradingView |
| Erlaubnis nur für „display" oder „personal viewing", ohne Aussage zur maschinellen Nutzung | **NO_GO für N2 und N4.** Schweigen ist keine Erlaubnis. Dieselbe Auslegung wie bei TradingView, sonst wäre die dortige Entscheidung inkonsequent |
| Gesonderte Gebühren für Non-Display-Nutzung genannt | Nutzung ist möglich, aber **kostenpflichtig** — Betrag notieren, das gehört in die Anbieterentscheidung |
| Nichts Auffindbares | **offen**, kein GO. Bei IBKR nachfragen |

## Ergebnis festhalten

Die Antworten gehören in ein ADR zur F9-Datenquelle — **noch nicht
anzulegen**. Es entsteht erst, wenn diese Prüfung *und* die fachliche
RESC-Inhaltsprüfung abgeschlossen sind; beide Ergebnisse fließen dann
gemeinsam mit der Bewertung externer Anbieter in eine Entscheidung ein.

Bereits erledigt ist die **strukturelle** Inhaltsprüfung: Welche Felder
RESC enthält, steht belegt in
[`spikes/resc-schema/RESULT.md`](../../spikes/resc-schema/RESULT.md).
Offen bleibt die fachliche Seite — ob die Werte über die Watchlist hinweg
belastbar und vollständig genug sind (bei `WMT` fehlten die Empfehlungen
ganz).

Fällt die Lizenzprüfung negativ aus, werden Analystenratings und Kursziele
wie die Earnings-Termine als **externe** Datenquelle behandelt. Die
Anbieterevaluation berücksichtigt das als Möglichkeit.
