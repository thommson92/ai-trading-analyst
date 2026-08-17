# ADR 0022: Research Agent -- Anthropic Web Search/Web Fetch, SEC EDGAR deterministisch für Fundamentaldaten

- Status: Angenommen (GO_WITH_LIMITATIONS)
- Datum: 2026-08-16

## Kontext

ADR 0021 hat den KI-Anbieter (Anthropic) und die Modellprofil-Mechanik
entschieden, aber ausdrücklich offen gelassen, woher der Research Agent
seine externen Inhalte bezieht (Doc 06: Nachrichten, Unternehmensmeldungen,
Analystenberichte, SEC-Informationen, Marktumfeld). Die Untersuchung dazu
steht in
[docs/requirements/research-quellen-evaluation.md](../requirements/research-quellen-evaluation.md).

Wie bei RESC ([ADR 0016](0016-ibkr-keine-quelle-fuer-research-daten.md)) und
der Earnings-Anbieterwahl ([ADR 0017](0017-finnhub-fuer-earnings-und-ratings.md))
gilt: Belegt wird an der offiziellen Anbieterdokumentation geprüft, nicht an
einer Vergleichstabelle. Anders als bei RESC gibt es hier keine unbelegte
Rechtegrundlage: Anthropics Dokumentation untersagt die Aufbereitung oder
Aggregation von Suchergebnissen nicht, sie verlangt bei modifizierten
API-Ausgaben eine angemessene Quellenanzeige (siehe Einschränkung E1 und den
[Deployment-Gate](#deployment-gate-oeffentliche-oder-kommerzielle-bereitstellung)
unten). Der Projektinhaber hat diese Einschätzung nach Rückfrage bestätigt --
Muster wie bei der IBKR-Marktdatenbewertung in ADR 0014, wo eine bewusste
eigene Einschätzung getroffen wurde, statt auf eine vollständige externe
Klärung zu warten.

## Entscheidung

**Recherchequellen für den Research Agent:**

1. **Anthropic Web Search Tool** (`web_search`, serverseitiges Tool der
   Messages API) für Nachrichten, Unternehmensmeldungen, Analystenkommentare
   und Marktumfeld. Kein zweiter Anbietervertrag -- läuft über dasselbe
   Anthropic-Konto aus ADR 0021.
2. **Anthropic Web Fetch Tool** (`web_fetch`) zum vollständigen Lesen einer
   über die Suche gefundenen, konkreten Quelle (z. B. eine
   Unternehmensmeldung oder ein SEC-Filing-Link) -- kostenlos, nur
   Tokenkosten.
3. **SEC EDGAR** (`data.sec.gov`, `efts.sec.gov`) für SEC-Informationen.

**Fundamentaldaten werden nicht über den Research Agent bezogen.** Der
Fundamental Agent liest `data.sec.gov/api/xbrl/companyfacts/CIK...json`
**direkt und deterministisch**, kein Sprachmodell im Beschaffungspfad. Das
Sprachmodell interpretiert die bereits berechneten Kennzahlen (Wachstum,
Bewertung, Profitabilität, Verschuldung), erfindet oder berechnet sie nicht
selbst -- Umsetzung von CLAUDE.mds zentraler Regel *"Technische Signale
werden niemals durch KI verändert"* auch auf der Datenbeschaffungsseite,
nicht nur bei der Auswertung.

**Domain-Filter und `max_uses`** werden bei der Implementierung des Research
Agent gesetzt, nicht offen gelassen -- konkrete Werte sind Sache der
Implementierung, nicht dieses ADR.

### Lizenzbewusste Quellen- und Zitierarchitektur

Verbindliche Konstruktionsregeln für den Research Agent, nicht optional:

1. Jede wesentliche externe Tatsachenbehauptung bleibt bis zu ihrer
   Originalquelle zurückverfolgbar.
2. Der Bericht enthält absatz-/aussagenahe Verweise mit Quelle, Titel und
   Abrufzeitpunkt -- auch wenn mehrere Quellen zu einer Aussage aggregiert
   wurden. Erfüllt zugleich CLAUDE.mds "Quellenbindung".
3. Keine längeren Textpassagen, Tabellen oder proprietären Kennzahlen
   unverändert übernehmen -- nur eigene Zusammenfassung mit Verweis.
4. Primärquellen bevorzugt (Geschäftsberichte, regulatorische
   Veröffentlichungen, Investor-Relations-Mitteilungen) vor sekundärer
   Berichterstattung. SEC EDGAR erfüllt das für die SEC-Sparte bereits per
   Konstruktion.
5. Anbieter/Webseiten nur gemäß ihren jeweiligen API-, Anzeige-, Speicher-
   und Weiterverbreitungsrechten nutzen. Quellen mit unklarer Rechtslage
   sind technisch abschaltbar bzw. laufen über eine Allowlist
   (`allowed_domains` des Web-Search-/Web-Fetch-Tools) statt einer
   Blockliste als Standard.
6. Intern wird je Aussage gespeichert: Herkunft (URL, Anbieter), Lizenzklasse
   und die angewendeten Transformationsschritte (z. B. "zusammengefasst",
   "übersetzt", "aggregiert aus n Quellen") -- eigenes Datenmodell, kein
   Freitext-Reporting ohne diese Metadaten.

## Begründung

Beide Anthropic-Tools sind Teil der bereits gewählten API, ohne
zusätzlichen Vertrag oder zusätzliche Rechnung -- das war der ausschlaggebende
Vorteil gegenüber der Prüfung eines dritten, separaten News-/Such-API-Anbieters.
Die Zitatpflicht des Web-Search-Tools (URL, Titel, zitierter Text bei jedem
Treffer) deckt CLAUDE.mds Quellenbindungsanforderung strukturell ab, ohne
dass eine eigene Nachweiskette gebaut werden muss. SEC EDGAR ist kostenlos,
gut dokumentiert und liefert Fundamentaldaten bereits strukturiert -- ein
Umweg über ein Sprachmodell würde dort nur Fehlerquellen hinzufügen, ohne
einen Vorteil zu bringen.

## Konsequenzen

### Akzeptierte Einschränkungen

- **E1 -- Lizenzfrage bei Weiterverarbeitung, bewusst eingeschätzt statt
  blockiert.** Anthropics Dokumentation untersagt Aufbereitung/Aggregation
  von Suchergebnissen nicht; sie verlangt bei modifizierten Ausgaben eine
  angemessene Quellenanzeige. Für den privaten Prototyp -- kein öffentlicher
  Zugriff, keine Weitergabe, nur der Projektinhaber selbst als Nutzer --
  ist die oben beschriebene Zitierarchitektur die angemessene Antwort
  darauf, kein zusätzliches Genehmigungsverfahren vor jeder Zusammenfassung.
  Blockiert **nicht** die Implementierung. Die vollständige rechtliche
  Prüfung von Anthropics Commercial Terms of Service
  (<https://www.anthropic.com/legal/commercial-terms>) und Usage Policy
  (<https://www.anthropic.com/aup>) gegen die dann tatsächlich verwendeten
  Quellen und Anbieterbedingungen ist ein
  [Deployment-Gate](#deployment-gate-oeffentliche-oder-kommerzielle-bereitstellung),
  kein Implementierungs-Gate.
- **E2 -- Kostenschätzung ungemessen.** Die grobe Schätzung
  (12-40 USD/Monat allein an Suchgebühr, siehe Untersuchungsdokument
  Abschnitt 1.3) liegt am oberen Rand des in ADR 0021 gesetzten
  20-30-EUR-Korridors. Vor dem produktiven Einsatz mit realen Zahlen
  nachmessen, `max_uses` und Domain-Filter entsprechend eng setzen.
- **E3 -- Prompt-Injection-Abwehr ist Implementierungssache.** Wie
  Suchergebnisse als reine, nicht vertrauenswürdige Daten markiert werden
  (Doc 10 §13), wird beim Bau des Research Agent entschieden, nicht hier.
- **E4 -- Keine strukturierte Quelle für Analystenratings/Kursziele.**
  Bleibt wie in ADR 0017 zurückgestellt; nicht spezifisch für den Research
  Agent.

### Deployment-Gate: öffentliche oder kommerzielle Bereitstellung

**Gesperrt ist:** jede Bereitstellung des Research Agent außerhalb des
privaten Prototyps -- öffentlicher Zugriff, Mehrnutzerbetrieb, kommerzielle
Nutzung oder Weitergabe von Berichten an Dritte.

**Freigabe durch:** eine gezielte rechtliche Prüfung der zu diesem Zeitpunkt
*tatsächlich* verwendeten Quellen und Anbieterbedingungen (nicht nur
Anthropics Bedingungen, auch die der einzelnen über Web Search/Fetch
erreichten Webseiten) -- durchgeführt, bevor eine dieser Bereitstellungsarten
beginnt, nicht danach.

**Bis zur Freigabe:** Betrieb ausschließlich als privater, persönlicher
Prototyp durch den Projektinhaber selbst, im Muster der bereits
umgesetzten Module (kein öffentlich erreichbares Dashboard, siehe Doc 10
§13 "Externer Zugriff", F12 -- ohnehin noch nicht umgesetzt). Eine
technische Durchsetzung dieses Gates (vergleichbar
`AppConfig.require_indicators()` für G1) ist heute nicht gebaut, weil noch
keine Deployment-Unterscheidung zwischen privat und öffentlich existiert --
nachzuholen, sobald F12 ansteht.

### Nächste Schritte

- Die in [ADR 0021](0021-ki-anbindung-anthropic-api.md) beschriebene
  Konfigurationsgrundlage (`feature/llm-konfiguration`, bereits gemergt)
  bleibt unverändert -- dieses ADR ergänzt sie um die Quellenwahl, ändert
  aber nichts an `LlmConfig`.
- Der Research Agent selbst (Port, Adapter, Prompt-Aufbau,
  strukturiertes Ausgabeschema, Injection-Abwehr) ist ein eigener
  Implementierungsschritt.
