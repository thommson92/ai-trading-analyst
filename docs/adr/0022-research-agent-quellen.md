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
Rechtegrundlage, sondern eine konkret benennbare, noch zu klärende Frage
(siehe Einschränkung E1).

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

- **E1 -- Lizenzfrage bei Weiterverarbeitung ungeklärt.** Anthropics
  Dokumentation verlangt Rücksprache mit der eigenen Rechtsabteilung, sobald
  Suchergebnisse nicht unverändert mit Zitat angezeigt, sondern
  umformuliert/kombiniert werden -- genau das tut der Research Agent
  (strukturierter Bericht statt Rohtreffer). **Vor dem ersten produktiven
  Research-Agent-Lauf** sind Anthropics Commercial Terms of Service
  (<https://www.anthropic.com/legal/commercial-terms>) und die Usage Policy
  (<https://www.anthropic.com/aup>) konkret auf diesen Anwendungsfall zu
  prüfen -- ein persönliches, nicht öffentlich zugängliches Dashboard mit
  dauerhafter, aber nicht weitergegebener Speicherung ist voraussichtlich
  unkritisch, aber das ist eine Einschätzung, keine Feststellung. Diese
  Prüfung blockiert nicht die Konfigurationsgrundlage oder die
  Domain-/Ports-Implementierung, wohl aber den ersten echten Lauf gegen
  produktive Daten.
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

### Nächste Schritte

- Die in [ADR 0021](0021-ki-anbindung-anthropic-api.md) beschriebene
  Konfigurationsgrundlage (`feature/llm-konfiguration`, bereits gemergt)
  bleibt unverändert -- dieses ADR ergänzt sie um die Quellenwahl, ändert
  aber nichts an `LlmConfig`.
- Der Research Agent selbst (Port, Adapter, Prompt-Aufbau,
  strukturiertes Ausgabeschema, Injection-Abwehr) ist ein eigener
  Implementierungsschritt.
