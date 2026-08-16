# ADR 0022: Research Agent -- Zitierarchitektur

- Status: Angenommen
- Datum: 2026-08-16

## Kontext

ADR 0021 legt Anbieter, Budget und Modellstufung für die KI-Anbindung fest,
lässt aber die konkrete Umsetzung des Research Agent (des ersten der vier
in ADR 0021 geplanten Bausteine) offen. Der Research Agent ist laut Doc 10
Paragraph 6.7 der Pipeline-Einstieg der KI-Analyse und läuft ausschließlich
für Aktien, die Screener **und** Earnings-Filter (`EARNINGS_CLEAR`) bestanden
haben.

Zwei Vorgaben binden diese Entscheidung, ohne sie vorwegzunehmen:

- **CLAUDE.md "Daten und Ergebnisse", Quellenbindung:** Aussagen über
  Nachrichten, Analystenmeinungen, Kursziele oder Fundamentaldaten verweisen
  auf gespeicherte Quellen mit URL, Veröffentlichungs- und
  Abrufzeitpunkt.
- **CLAUDE.md "Die zentrale Regel":** Scores und Klassifikationen werden nie
  direkt aus LLM-Freitext übernommen.

Die Umsetzung nutzt das offizielle `anthropic`-SDK mit den serverseitigen
Werkzeugen `web_search` und `web_fetch` samt deren eingebauter
Zitat-Blöcke (`web_search_result_location`, `char_location`) -- diese Wahl
selbst ist keine gesonderte Architekturentscheidung, sondern folgt aus ADR
0021 ("kontrollierter Workflow mit strukturierten Ausgaben"; kein eigenes
Such-/Fetch-Werkzeug nachgebaut). Offen war, wie aus den von der API
gelieferten Zitat-Rohdaten belastbare, persistierbare Belege werden.

## Entscheidung

1. **Jede wesentliche Aussage im Bericht muss auf ein konkretes Zitat
   zurückführbar sein** -- nicht auf eine einzige Sammelquelle je Bericht.
   Der Systemprompt verlangt das vom Modell ausdrücklich; der Adapter
   sammelt jeden Zitat-Block aus jeder Gesprächsrunde einzeln (`Citation`
   pro Fundstelle, nicht pro Bericht).
2. **Zitate werden in einer eigenen Tabelle (`research_citations`)
   gespeichert, nicht als flache Spalte** -- jedes Zitat trägt mehrere
   Felder (URL, Titel, Abrufzeit, zitierter Ausschnitt, Lizenzklasse,
   Transformation), Muster wie `SignalEventOrm` für die
   `screening_results`-Zeile.
3. **Zugriff über eine Domain-Allowlist, nicht über eine Blockliste**
   (`ResearchConfig.allowed_domains`, an `web_search`/`web_fetch`
   durchgereicht). Eine leere Allowlist bedeutet keine Einschränkung, ist
   aber nicht der ausgelieferte Standard -- eine Blockliste müsste jede
   unerwünschte Domain im Voraus kennen, eine Allowlist ist im
   Finanzkontext (Primärquellen, etablierte Nachrichtenanbieter) die
   sicherere Voreinstellung.
4. **Lizenzklasse deterministisch aus der URL, nie vom Modell erfragt**
   (`SourceLicenseClass`, `_classify_license` in
   `infrastructure/anthropic/provider.py`): `PRIMARY_SOURCE` für bekannte
   regulatorische Domains (aktuell `sec.gov`), sonst `UNKNOWN`. Setzt
   CLAUDE.mds Verbot um, Klassifikationen aus LLM-Freitext zu übernehmen.
5. **Jedes Zitat trägt ein `transformation`-Feld** (z. B.
   `"zusammengefasst"`), das dokumentiert, wie die Quelle im Bericht
   verwendet wurde -- Grundlage für eine spätere Unterscheidung zwischen
   direkt zusammengefassten und über mehrere Quellen aggregierten Aussagen.
6. **Zitate werden dedupliziert**, falls dieselbe Quelle (gleiche URL,
   gleicher zitierter Ausschnitt) mehrfach über mehrere Gesprächsrunden
   auftritt; die Reihenfolge der ersten Nennung bleibt erhalten.

### Bekannte Abweichung von der Quellenbindungs-Regel

`Citation` speichert ausschließlich die **eigene Abrufzeit**
(`retrieved_at`), nicht den vom Anbieter gemeldeten
Veröffentlichungszeitpunkt der Quelle selbst -- eine bewusste Entscheidung
beim Bau des Adapters (siehe Docstring `Citation.retrieved_at`), keine
Auslassung. Weder `web_search_result_location`- noch
`char_location`-Zitatblöcke der Anthropic-API liefern zuverlässig ein
Veröffentlichungsdatum der Quelle mit; ein `web_fetch_result` trägt zwar
teils Metadaten der abgerufenen Seite, aber nicht einheitlich genug für ein
Pflichtfeld ohne stille Lücken.

Das erfüllt CLAUDE.mds Quellenbindungs-Anforderung ("URL, Veröffentlichungs-
und Abrufzeitpunkt") nur teilweise. Dieses ADR nimmt die Lücke bewusst in
Kauf, statt sie stillschweigend zu übergehen, und hält sie hier für eine
gesonderte Entscheidung fest: ein optionales `published_at`-Feld
nachzuziehen (samt Migration), sobald feststeht, welche Zitat-Typen der
API verlässlich ein Datum liefern -- oder die Quellenbindungs-Regel für
LLM-recherchierte Zitate (im Unterschied zu strukturierten Anbietern wie
Finnhub) ausdrücklich einzuschränken.

## Begründung

Die Entscheidungen 1-2 und 6 leiten sich unmittelbar aus Doc 10 Paragraph
10 (Halluzinationsschutz, Rückverfolgbarkeit) und dem bereits etablierten
Muster für optionale Teilergebnisse (`EarningsFilterResult`) ab. 3-5 setzen
CLAUDE.mds Verbot um, dass Scores/Klassifikationen aus LLM-Freitext
übernommen werden -- die Lizenzklasse und die Domain-Beschränkung sind
deterministischer Infrastrukturcode, kein Modell-Output.

Die bekannte Abweichung bei der Veröffentlichungszeit wird hier
dokumentiert statt stillschweigend im Code belassen, weil sie sonst bei
jeder künftigen Lektüre des Codes neu entdeckt werden müsste -- ADRs sind
laut CLAUDE.md der Ort für genau solche, bereits getroffenen,
architekturrelevanten Entscheidungen.

## Konsequenzen

- `docs/adr/README.md`-Übersicht um diesen Eintrag ergänzt.
- Die im Code verstreuten Verweise auf "ADR 0022" (u. a.
  `infrastructure/anthropic/provider.py`, `domain/research/values.py`,
  `config/settings.py`, `infrastructure/persistence/orm.py`) sind damit
  gedeckt.
- Offener Folgepunkt: Entscheidung zu `published_at` nachholen (siehe
  oben), bevor Research-Ergebnisse in einem Bericht gegenüber dem Nutzer
  als vollständig quellengebunden dargestellt werden.
