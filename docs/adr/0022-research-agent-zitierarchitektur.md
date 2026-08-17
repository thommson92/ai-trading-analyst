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
   regulatorische Domains (`sec.gov`), `NEWS_MEDIA` für die aufgenommenen
   Nachrichtenagenturen und Original-Pressemitteilungsdienste, sonst
   `UNKNOWN`. Setzt CLAUDE.mds Verbot um, Klassifikationen aus LLM-Freitext
   zu übernehmen.
5. **Jedes Zitat trägt ein `transformation`-Feld** (z. B.
   `"zusammengefasst"`), das dokumentiert, wie die Quelle im Bericht
   verwendet wurde -- Grundlage für eine spätere Unterscheidung zwischen
   direkt zusammengefassten und über mehrere Quellen aggregierten Aussagen.
6. **Zitate werden dedupliziert**, falls dieselbe Quelle (gleiche URL,
   gleicher zitierter Ausschnitt) mehrfach über mehrere Gesprächsrunden
   auftritt; die Reihenfolge der ersten Nennung bleibt erhalten.

### Nachtrag: Schemadurchsetzung statt nur Schemabeschreibung

Der erste echte Lauf gegen die API (2026-08-17) hat gezeigt, dass ein
beschriebenes Schema nicht genügt. Das Modell hat die Faktorlisten in seiner
internen XML-Werkzeugsyntax geschrieben (`<parameter name="item">…`), die API
hat den Wert als einfachen String durchgereicht, und der Adapter hat ihn mit
`tuple(...)` in Einzelzeichen zerlegt -- der Bericht hatte einen Listeneintrag
je Buchstabe. Zwei Ergänzungen zu Entscheidung 1:

7. **Das `submit_research_report`-Werkzeug wird mit `strict: true` und
   `additionalProperties: false` deklariert.** Damit erzwingt die API die
   Schemakonformität über grammar-constrained sampling, statt das Schema nur
   zu beschreiben. Ein Array-Feld kann keinen String mehr enthalten.
8. **Der Adapter prüft die Typen der Werkzeugantwort trotzdem selbst**
   (`_require_string_list`, `_require_optional_text` und die Zahlprüfung bei
   `confidence`). Ein falsch typisiertes Feld führt zu einem sichtbaren
   `ResearchProviderError`, nie zu einem stillen Ersatzwert -- der Fehler
   bleibt in der Fehlerisolation je Aktie und blockiert die technische Analyse
   nicht.

Ebenfalls abgesichert: Endet eine Antwort mit `stop_reason == "max_tokens"`,
wird kein Bericht gebaut. Ein dort abgeschnittener Werkzeugaufruf kann eine
halbe Faktorliste enthalten, die vollständig aussähe.

**Nicht gewählt: `output_config.format` / `client.messages.parse()`.** Beides
würde dieselbe Schemagarantie liefern, aber die finale Ausgabe wäre ein
JSON-Textblock. Die Zitat-Blöcke der Websuche hängen an Textblöcken; der
Abschluss über ein Client-Werkzeug ist genau das, was Entscheidung 1 möglich
macht. `strict` liefert die Garantie, ohne die Quellenbindung aufs Spiel zu
setzen.

### Nachtrag: Reichweite der Allowlist

Die ausgelieferte Allowlist enthielt zunächst nur `sec.gov`. Da sie für
`web_search` **und** `web_fetch` gilt, konnte der Agent die im Systemprompt
verlangten Nachrichten und Analystenkommentare gar nicht erreichen -- der
erste echte Bericht stützte sich ausschließlich auf SEC-Einreichungen und hat
das selbst vermerkt. Die Liste wurde deshalb um Original-Pressemitteilungs-
dienste (`prnewswire.com`, `businesswire.com`, `globenewswire.com`,
`nasdaq.com`) ergänzt. Entscheidung 3 bleibt unverändert: kuratierte
Allowlist, keine Blockliste, keine offene Suche.

**Einschränkung durch den Crawler-Zugang.** Nicht jede seriöse Quelle ist
verwendbar. Steht in `allowed_domains` eine Domain, die Anthropics Crawler
aussperrt, scheitert die **gesamte** Anfrage mit einem 400 -- nicht nur der
einzelne Abruf. Reuters und AP tun genau das und sind deshalb nicht in der
Voreinstellung; eine neue Domain gehört vor der Aufnahme einmal durch einen
echten Lauf. Für die eigentlich interessanten Unternehmensmeldungen
(Quartalszahlen, Rückkäufe, Personalien) sind die Pressemitteilungsdienste
ohnehin die Originalquelle und damit die bessere Wahl. Die Klassifikation in
`_NEWS_MEDIA_DOMAINS` führt Reuters und AP weiterhin, weil sie die Quellen-
*art* beschreibt und nicht die Erreichbarkeit.

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
- Offener Folgepunkt: Der technische Status (`ResearchStatus.COMPLETED`) sagt
  bislang nichts über die inhaltliche Abdeckung. Ein Lauf, der wegen des
  Suchbudgets nur einen Teil der Quellenklassen erreicht hat, gilt trotzdem
  als abgeschlossen. Eine getrennte Abdeckungsangabe neben dem Status braucht
  eine eigene Entscheidung samt Migration.
- Token- und Werkzeugnutzung werden je Lauf protokolliert
  (`_UsageTotals`), damit sich das Budget aus ADR 0021 überhaupt überprüfen
  lässt. Bewusst nur im Log: ein persistierter Kostenwert am Ergebnis wäre
  eine eigene Entscheidung.
