# ADR 0012: Gate G3 Strang A -- NO_GO wegen Non-Display-Nutzungsverbots der TradingView-Nutzungsbedingungen

- Status: Angenommen
- Datum: 2026-08-10

## Kontext

Gate G2 (`spikes/tradingview-cdp/REPORT.md`, Branch `spike/tradingview-cdp`) hat
mit `GO_WITH_LIMITATIONS` bestätigt, dass ein CDP-Adapter gegen die lokal
installierte, mit dem eigenen Account angemeldete TradingView-Desktop-App
technisch zuverlässig Kurs- und Indikatorwerte auslesen kann. Der Bericht hat
ausdrücklich offengelassen, ob dieser Zugriffsweg mit den TradingView-
Nutzungsbedingungen vereinbar ist (REPORT.md, Abschnitt 18: "Ein bestandener
technischer Test belegt keine vertragliche oder rechtliche Zulässigkeit").
Diese Prüfung ist Gegenstand von Strang A der Gate-G3-Entscheidungsvorlage
(`docs/requirements/g3-entscheidungsvorlage.md`, Abschnitt 2).

Die folgenden drei Punkte -- geprüfter Vertragsinhalt, technische Subsumtion
und Entscheidung -- werden bewusst getrennt dargestellt, damit nicht aus einer
technischen Tatsache stillschweigend eine rechtliche Bewertung wird.

### Geprüfte Quelle

- Dokument: TradingView Terms of Use, Abschnitt 3 "Ownership of information;
  license to use TradingView; redistribution of data; non-display usage"
- Quelle: [tradingview.com/policies/](https://www.tradingview.com/policies/)
- Prüfdatum (Abrufzeitpunkt): 2026-08-10
- Auf der Seite selbst ist zum Abrufzeitpunkt kein gesondertes
  Versions-/Änderungsdatum des Abschnitts ausgewiesen; maßgeblich für dieses
  ADR ist ausdrücklich der zum Prüfdatum abgerufene Stand. Bei einer
  wesentlichen Änderung der Bedingungen ist dieses ADR neu zu bewerten (vgl.
  Prüfschritt A7 der Entscheidungsvorlage).

### Vertragsinhalt (wörtliche Kernzitate)

> "\[content is] licensed for exclusive display-only use"

> "any form of automated trading, automated order generation, price
> referencing, order verification, algorithmic decision-making, algorithmic
> trading, smart order routing"

> "using data in operations control or risk management programs, or any
> machine-driven processes that do not involve the direct, human-readable
> display [of such data]"

> "creating products or services based on TradingView content, any
> processing of TradingView's content"

### Technische Subsumtion (getrennt vom Vertragsinhalt)

Der in Gate G2 validierte und für eine Produktivintegration vorgesehene
Zugriffsweg (siehe `spikes/tradingview-cdp/src/tvcdp/steps/step_indicators.py`
und `step_multi_symbol.py`) liest Kurs- und Indikatorwerte über
`Runtime.evaluate` programmatisch aus internen JavaScript-Objekten der
TradingView-Desktop-App aus -- nicht durch menschliches Ablesen des
Bildschirms. Die ausgelesenen Werte sind laut Projektarchitektur
(`docs/10 - System Architecture.md`, `docs/05 - Data Model.md`) zur
strukturierten Speicherung und als Eingabe für vollautomatische,
deterministische Weiterverarbeitung bestimmt -- namentlich die
Screener-Signalregeln, das Backtesting und die Scoring-Engine -- bevor an
irgendeiner Stelle eine direkte, menschenlesbare Anzeige der ausgelesenen
Rohwerte selbst stattfindet.

Das entspricht der im Zitat beschriebenen Kategorie "machine-driven processes
that do not involve the direct, human-readable display" sowie "processing of
TradingView's content". Die Klausel unterscheidet nach Verwendungsart
(Anzeige vs. maschinelle Verarbeitung), nicht nach Zugriffsweg. Dass der
Zugriff lokal über CDP und mit der eigenen, bereits angemeldeten Sitzung
erfolgt (REPORT.md, Abschnitt 3b) und kein direkter Server-Endpunkt
angesprochen wird, ändert an dieser Einordnung nichts -- keiner der
zitierten Klauselteile macht eine Ausnahme für lokale, kontoeigene oder
Debug-Schnittstellen-basierte Zugriffswege.

## Entscheidung

**Strang A der Gate-G3-Entscheidungsvorlage wird mit NO_GO abgeschlossen.**

Der geplante CDP-Adapter liest TradingView-Kurs- und Indikatorwerte
automatisiert aus, speichert bzw. verarbeitet sie maschinell und verwendet
sie außerhalb einer ausschließlich direkten, menschenlesbaren Anzeige. Die
zitierten Bedingungen untersagen ausdrücklich Non-Display-Nutzung,
Verarbeitung von TradingView-Inhalten und machinengetriebene Prozesse ohne
direkte Anzeige. Der lokale, konto-eigene, CDP-basierte Zugriffsweg begründet
keine erkennbare Ausnahme von diesem Verbot.

Es liegt damit der NO_GO-Fall aus Abschnitt 2.4 der Entscheidungsvorlage vor:
ein ausdrückliches, den geprüften Weg erkennbar einschließendes Verbot wurde
gefunden. Eine Risikoakzeptanz nach Variante (b) scheidet aus, weil eine
ausdrückliche, einschlägige Regelung vorliegt -- keine unklare oder
auslegungsbedürftige Vertragslage, die eine bewusst getragene
Auslegungsunsicherheit rechtfertigen würde.

**Strang B (R2-Betriebsmodell/Autologon) wird nicht weiterverfolgt.** Da
Strang A Gate G3 bereits eigenständig blockiert, werden keine
Autologon-Konfiguration und keine weiteren R2-Tests durchgeführt. Strang B
gilt als zurückgestellt, nicht als geprüft oder erledigt.

**Gate G3 insgesamt: NO_GO.** Damit keine Freigabe für Sprint 1C und keine
produktive `TradingViewMarketDataProvider`-Implementierung.

## Begründung

Anders als bei einer unklaren oder lückenhaften Vertragslage (Variante (b)
in Abschnitt 2.4 der Entscheidungsvorlage) liegt hier eine Klausel vor, die
den konkreten Verwendungszweck des Projekts -- automatisiertes Auslesen zur
Weiterverarbeitung in Screener, Backtesting und Scoring, ohne vorgelagerte
direkte menschliche Anzeige der Rohwerte -- ausdrücklich und spezifisch
benennt. Eine Risikoakzeptanz wäre hier keine vertretbare Einschätzung einer
Grauzone, sondern eine bewusste Inkaufnahme eines erkannten Verstoßes gegen
eine eindeutige Regelung. Das entspricht nicht den in Abschnitt 2.4
formulierten Kriterien für ein verantwortbares GO.

## Konsequenzen

- Gate G3 bleibt geschlossen (NO_GO). Kein Sprint 1C, keine produktive
  TradingView-Integration, keine Autologon-Einrichtung.
- L1 (Watchlist nicht über interne API lesbar) und L2 (Study-Indizes müssen
  dynamisch aufgelöst werden) bleiben als dokumentierte technische
  Erkenntnisse aus Gate G2 bestehen, werden aber **nicht** als
  Produktionsbedingungen freigegeben, da keine Produktivintegration
  genehmigt wird.
- Der in `spikes/tradingview-cdp/REPORT.md` skizzierte Fallback-Vergleich
  (TradingView-Alerts/Webhooks, Watchlist-Export) ist als nächster
  Untersuchungsschritt für die Marktdatenbeschaffung zu behandeln --
  **ausdrücklich ohne Vorwegnahme**, ob diese Wege derselben oder einer
  abweichenden vertraglichen Bewertung unterliegen. Auch dort werden
  TradingView-Inhalte gelesen; eine eigene Prüfung gegen dieselbe Klausel
  ist vor einer etwaigen Umsetzung erforderlich und nicht Gegenstand dieses
  ADR.
- Eine Neubewertung dieser Entscheidung erfolgt ausschließlich bei
  ausdrücklicher schriftlicher Erlaubnis bzw. einer separaten
  Lizenzvereinbarung mit TradingView (und ggf. den zugrundeliegenden
  Datenanbietern/Börsen) oder bei einem grundlegend anderen, zulässigen
  Datenzugriffsweg, der nicht unter das Non-Display-Verbot fällt.
- Kein Merge in eine Codebasis, keine Codeänderung, keine
  TradingView-Automatisierung als Folge dieses ADR -- es handelt sich
  ausschließlich um eine Dokumentations- und Entscheidungsfestlegung.
