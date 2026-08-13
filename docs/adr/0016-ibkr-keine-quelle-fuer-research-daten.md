# ADR 0016: Interactive Brokers ist keine Quelle für Research-Daten

- Status: Angenommen
- Datum: 2026-08-13

## Kontext

Über `reqFundamentalData(reportType='RESC')` liefert die IBKR-TWS-API einen
umfangreichen Datensatz mit Analystenschätzungen. Die
[Inhaltsprüfung](../../spikes/resc-schema/RESULT.md) vom 2026-08-12 hat
belegt, dass darin Kursziele (`TARGETPRICE` mit High/Low/Mean/Median) und
Empfehlungen (`BUY`…`SELL` mit der Zahl der Analysten je Stufe) stehen —
nicht aber künftige Berichtstermine.

Offen blieb, ob die Vertragslage die geplante Verarbeitung deckt. Die
Inhalte stammen ausweislich mehrerer Indizien von Reuters/Refinitiv
(Wurzelelement `REarnEstCons`, Sektorschema `set="R"`, `RIC` als
Wertpapierkennung) und werden über ein eigenes Research-Abonnement
bereitgestellt. Die in [ADR 0014](0014-ibkr-produktivintegration-freigegeben.md)
zitierte Klausel („exclusively in connection with Subscriber's brokerage
account(s)") stammt aus dem **Marktdaten**-Abonnement und deckt
Research-Inhalte nicht erkennbar mit ab.

Für die Klärung lagen vor: eine
[Prüfliste](../requirements/resc-lizenzpruefung.md) mit Erhebungsbogen und
Prüftabelle sowie ein fertiger
[Entwurf für eine schriftliche Anfrage an IBKR](../requirements/resc-ibkr-anfrage.md).
Die Prüftabelle stand zum Entscheidungszeitpunkt auf fünfmal `UNKLAR`.

## Entscheidung

**Interactive Brokers wird nicht als Quelle für Analystenschätzungen,
Analystenratings, Kursziele, Earnings-Berichte und Earnings-Termine
verwendet.** Das Ergebnis lautet `NO_GO mangels belastbarer Grundlage` nach
der in der Prüfliste festgelegten Entscheidungsregel.

Der Projektinhaber hat die Anfrage an IBKR bewusst nicht abgesendet, sondern
entschieden, den Weg nicht weiter zu verfolgen: Die Vertragslage ist zu
ungewiss.

**ADR 0014 bleibt unberührt.** IBKR ist und bleibt die produktive Quelle für
**Marktdaten** — Kurse, historische Bars, Optionsketten. Diese Entscheidung
betrifft ausschließlich Research-Inhalte.

## Begründung

Die Prüfliste hält fest: *„Ein angenommenes Restrisiko genügt bei RESC
nicht."* Genau dieser Maßstab wird hier angewandt. Anders als bei den
Marktdaten, wo der Projektinhaber eine eigene Einschätzung auf Basis einer
konkret zitierbaren Klausel getroffen hat, gibt es für Research-Inhalte
keine auffindbare Grundlage — weder eine Erlaubnis noch ein Verbot.

Fehlende Regelung wird nicht zugunsten der Nutzung ausgelegt. Andernfalls
wäre [ADR 0012](0012-gate-g3-strang-a-no-go-non-display-nutzung.md)
inkonsequent, wo TradingView aus genau demselben Grund abgelehnt wurde.

Der Weg über eine schriftliche Bestätigung durch IBKR wäre gangbar gewesen,
kostet aber Zeit mit ungewissem Ausgang, und selbst eine positive Antwort
hätte die Frage offengelassen, ob sie die Rechte des eigentlichen
Datenlieferanten abdeckt (Frage Q4 des Entwurfs). Eine externe Quelle mit
klarer, selbst prüfbarer Lizenz ist die belastbarere Grundlage.

## Konsequenzen

- **RESC wird nicht implementiert.** Kein produktiver Zugriff, keine
  Konfiguration, keine Scheduler-Anbindung. Der aktuelle Stand erfüllt das
  bereits — RESC kommt im Produktivcode nicht vor.
- **Analystenratings und Kursziele werden extern zugekauft**, zusammen mit
  den Earnings-Terminen. Sie waren bis hierher der einzige Grund, RESC
  überhaupt zu erwägen.
- **Der Earnings-Workstream bleibt bestehen** und wird um Ratings und
  Kursziele erweitert. Bewertung in
  [`docs/requirements/earnings-anbieter-evaluation.md`](../requirements/earnings-anbieter-evaluation.md).
- **Einschränkung E1 aus ADR 0014 bleibt gültig** und ist jetzt endgültig:
  Earnings-Termine kommen nicht von IBKR.
- Der Filter F9 bleibt bis zur Anbieterentscheidung **ohne Datengrundlage**.
  Kein Ersatzwert, keine geschätzten Termine — ein Ergebnis ohne
  Earnings-Prüfung wird als solches gekennzeichnet.
- **Die Sonde `spikes/resc-schema/` bleibt als eingefrorenes Artefakt**
  erhalten, wie die beiden anderen Spikes. Sie belegt, was RESC enthält —
  falls die Frage je neu aufgeworfen wird, muss der Inhalt nicht erneut
  erhoben werden. Prüfliste und Anfrageentwurf bleiben aus demselben Grund
  bestehen; beide tragen einen Vermerk auf dieses ADR.
- Ändert sich die Vertragslage, oder liegt eine schriftliche Bestätigung von
  IBKR vor, ist das ein **neues ADR** — dieses wird nicht rückwirkend
  geändert.
