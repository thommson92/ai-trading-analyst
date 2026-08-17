# ADR 0023: Research Agent -- Zitierarchitektur

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

### Nachtrag: Kostenkontrolle und Reichweite der Allowlist

Ein Lauf am 2026-08-17 verbrauchte **255.996 Eingabe-Token, 6.329
Ausgabe-Token, 5 Websuchen und 2 Webabrufe — rund 0,62 $ — und lieferte
`INSUFFICIENT_DATA`.** Zwei Ursachen, beide betreffen fehlende Parameter, nicht
die Logik.

**Kostenmechanik.** `web_search`/`web_fetch` sind serverseitige Werkzeuge: Ihre
Schleife läuft bis zu zehn Iterationen *innerhalb einer einzigen Anfrage* —
deshalb meldete das Log „1 Runde" bei sieben Werkzeugaufrufen. Abgerufene
Inhalte zählen laut Anthropic-Doku „in search iterations executed during a
single turn", der angesammelte Kontext wird also je Iteration erneut
verrechnet. Ein ungebremst abgerufenes SEC-Filing (~125.000 Token) schlägt
damit vielfach zu Buche.

9. **`max_content_tokens` auf `web_fetch`** (`research.max_fetch_content_tokens`,
   Standard 8.000). Das Produkt `max_fetches × max_fetch_content_tokens` ist
   das eigentliche Kostenbudget — nicht der Wert je Abruf für sich.
10. **`research.max_input_tokens_per_symbol`** (Standard 150.000) bricht den
    Lauf ab, statt eine weitere `pause_turn`-Fortsetzung zu schicken.
    **Reichweite ehrlich benannt:** Die Grenze greift *zwischen* Anfragen. Eine
    bereits abgeschickte Anfrage läuft bis zum Ende durch; innerhalb dieser
    einen Anfrage wirken ausschließlich `max_uses` und `max_content_tokens`.
    Ein Netz gegen mehrrundigen Weglauf, kein Not-Aus.
11. **Werkzeugfehler werden protokolliert.** `web_search_tool_result_error` und
    `web_fetch_tool_result_error` kommen als 200er-Antwort mit Fehlerblock an
    und wurden bisher stillschweigend übergangen. Genau darin stand die
    Diagnose (`max_uses_exceeded`, `url_not_in_prior_context`); ohne sie blieb
    nur die Selbstbeschreibung des Modells.
12. **Kostenschätzung im Log** aus `research.pricing`. Von Hand gepflegte
    Werte, im YAML als solche gekennzeichnet — Token allein beantworten die
    Betreiberfrage „was kostet mich ein Lauf" nicht.

**Revision von Entscheidung 3: Die Allowlist gilt nur noch für den Abruf.** Sie
galt für Suche *und* Abruf. Bei fünf erlaubten Domains liefert die Websuche
kaum Treffer, das Modell verbrennt sein Suchkontingent — und danach ist
`web_fetch` wirkungslos, weil es ausschließlich URLs erreicht, die vorher im
Kontext standen. Genau diesen Ablauf hat das Modell im `reason`-Feld
beschrieben. Künftig: **breit suchen, eng vertiefen.** `web_search` läuft ohne
`allowed_domains`, `web_fetch` bleibt auf `research.fetch_allowed_domains`
beschränkt. Die Quellenbindung bleibt unberührt — Suchtreffer tragen URL und
Titel im Zitatblock, und `_classify_license` stuft alles Unbekannte weiterhin
als `UNKNOWN` ein. Das Prinzip aus Entscheidung 3 (Allowlist statt Blockliste)
gilt unverändert für die Stelle, an der ganze Dokumente in den Kontext
gelangen.

Dass der Lauf `INSUFFICIENT_DATA` statt eines erfundenen Berichts lieferte, ist
die Halluzinationsschutz-Regel aus CLAUDE.md — die hat funktioniert.

### Nachtrag: Zwei Phasen — Zitate und Schemazwang schließen sich aus

Zwei Läufe am 2026-08-17 lieferten inhaltlich brauchbare Berichte mit **null
Zitaten** — und dafür rohem `<cite index="8-3">`-Markup mitten in den
Faktortexten. Damit war die tragende Entscheidung 1 dieses ADR wirkungslos,
und zwar seit dem ersten Commit.

**Der Entwurfsfehler.** Anthropic-Zitate hängen an Textblöcken; ein
`tool_use`-Block hat keine Zitat-Metadaten. Die Dokumentation sagt es
ausdrücklich: *„Citations require interleaving citation blocks with text
output, which is incompatible with the strict JSON schema constraints of
structured outputs."* Dieses ADR verlangte aber beides gleichzeitig —
Quellenbindung (Entscheidung 1) **und** Abschluss über
`submit_research_report`. Damit lieferte das Modell den ganzen Bericht über den
einen Kanal, in dem Zitate technisch nicht existieren können, und schrieb sie
mangels Alternative als Text hinein. `_extract_citations` fand nichts, weil es
nichts zu finden gab.

Der Fehler fiel neun Läufe lang nicht auf, weil keiner davon bis zur
Zitatausgabe kam: Erst schlugen Werkzeugversionen fehl, dann das Schema, dann
der Crawler-Zugang, dann das Budget.

15. **Der Lauf zerfällt in zwei Phasen.** Phase 1 recherchiert **ohne**
    Abschluss-Werkzeug — das Modell muss in Fließtext antworten, und die
    Zitatblöcke entstehen dort automatisch. Phase 2 strukturiert diesen Text in
    einem zweiten Aufruf **ohne** Web-Werkzeuge (`tool_choice` erzwingt den
    Werkzeugaufruf). Was Phase 2 ausgibt, kann nichts enthalten, was nicht
    schon in Phase 1 recherchiert und belegt wurde; der Recherchetext wird ihr
    als abgegrenzte Daten übergeben, nicht als Instruktion.

    Kosten: ein zusätzlicher Aufruf, der aber nur den fertigen Text sieht statt
    der gesamten Werkzeughistorie — rund 0,02 $.

16. **`allowed_callers: ["direct"]` auf beiden Web-Werkzeugen** schaltet die
    dynamische Filterung ab. Sie lässt die Ergebnisse durch Code Execution
    laufen und spart laut Anthropic rund 24 % Eingabe-Token, führt aber zu
    indexbasierten Referenzen statt zu `web_search_result_location`-Blöcken.
    Die Tokenersparnis wird bewusst aufgegeben: Ein billiger Bericht ohne
    Belege ist für dieses System wertlos.

**Rückblickend:** Ein Fremd-Review hatte genau das vorhergesagt („Da
Anthropic-Citations und Structured Outputs nicht ohne Weiteres in derselben
finalen Ausgabe kombinierbar sind, verwende für den strukturierten Report
eigene `source_id`s") und wurde mit der Begründung abgelehnt, `strict` liefere
dieselbe Garantie „ohne die Zitate aufzugeben". Das war falsch — die Zitate
waren zu dem Zeitpunkt bereits verloren.

### Nachtrag: Stichtag im Prompt

Derselbe Lauf beschrieb den November 2025 als aktuelle Lage — bei einem
Laufdatum im August 2026. Das Modell kannte das heutige Datum nicht und hat
neun Monate alte Meldungen als Gegenwart präsentiert. Für ein Handelssystem
ist veraltetes Research, das sich als aktuell ausgibt, schädlicher als gar
keines.

14. **Der Benutzerprompt nennt das heutige Datum** und verlangt, das
    Veröffentlichungsdatum jeder Quelle zu prüfen, den zeitlichen Stand im
    Bericht zu nennen und niemals einen älteren Stand als aktuelle Lage
    auszugeben. Das ersetzt kein `published_at` je Zitat (weiterhin offener
    Folgepunkt), schließt aber die gröbste Lücke.

### Nachtrag: Ein zu knappes Kontingent verteuert den Lauf

Derselbe Lauf mit `--max-searches 1 --max-fetches 1` kostete **0,315 $** —
mehr als das halbe Vollbudget. Nach der einen erlaubten Suche versuchte das
Modell fünf weitere Suchen und drei weitere Abrufe, alle mit
`max_uses_exceeded` bzw. `url_not_allowed` abgelehnt. Jeder Versuch ist eine
weitere Iteration der serverseitigen Schleife und verrechnet den gesamten
Kontext neu.

Konsequenz: `max_uses` ist eine Obergrenze für *sinnvolle* Aufrufe, keine
Sparbremse. Zu knapp gesetzt kostet es mehr. Der Systemprompt weist deshalb
ausdrücklich darauf hin, dass `max_uses_exceeded` und `url_not_allowed` sich
durch Wiederholung nicht ändern, und die CLI-Hilfe warnt davor.

### Nachtrag: Zusammensetzung der Abruf-Allowlist

Die ausgelieferte Liste enthielt zunächst nur `sec.gov` und wurde um
Original-Pressemitteilungsdienste (`prnewswire.com`, `businesswire.com`,
`globenewswire.com`, `nasdaq.com`) ergänzt. Für die eigentlich interessanten
Unternehmensmeldungen (Quartalszahlen, Rückkäufe, Personalien) sind die
ohnehin die Originalquelle und damit die bessere Wahl als eine Agenturmeldung.

**Einschränkung durch den Crawler-Zugang.** Nicht jede seriöse Quelle ist
abrufbar. Steht in `fetch_allowed_domains` eine Domain, die Anthropics Crawler
aussperrt, scheitert die **gesamte** Anfrage mit einem 400 -- nicht nur der
einzelne Abruf. Reuters und AP tun genau das und sind deshalb nicht in der
Voreinstellung; eine neue Domain gehört vor der Aufnahme einmal durch einen
echten Lauf. Die Klassifikation in `_NEWS_MEDIA_DOMAINS` führt Reuters und AP
weiterhin, weil sie die Quellen*art* beschreibt und nicht die Erreichbarkeit:
Als Suchtreffer können sie seit der Öffnung der Suche wieder auftauchen.

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
- Die im Code verstreuten Verweise auf "ADR 0023" (u. a.
  `infrastructure/anthropic/provider.py`, `domain/research/values.py`,
  `config/settings.py`, `infrastructure/persistence/orm.py`) sind damit
  gedeckt.
- Offener Folgepunkt: Entscheidung zu `published_at` nachholen (siehe
  oben), bevor Research-Ergebnisse in einem Bericht gegenüber dem Nutzer
  als vollständig quellengebunden dargestellt werden.
- Offener Folgepunkt, inzwischen belegt: Der technische Status
  (`ResearchStatus.COMPLETED`) sagt nichts über die inhaltliche Abdeckung. Ein
  Lauf mit **einer** Suche, **null** erfolgreichen Abrufen und acht abgelehnten
  Werkzeugaufrufen meldete `COMPLETED` mit Confidence 0,55. Eine getrennte
  Abdeckungsangabe neben dem Status braucht eine eigene Entscheidung samt
  Migration — sie ist damit aber kein theoretischer Punkt mehr, sondern ein
  beobachteter Mangel.
- Token- und Werkzeugnutzung werden je Lauf protokolliert
  (`_UsageTotals`), samt Kostenschätzung, damit sich das Budget aus ADR 0021
  überhaupt überprüfen lässt. Bewusst nur im Log: ein persistierter
  Kostenwert am Ergebnis wäre eine eigene Entscheidung.
- `cli research` kennt `--max-searches`/`--max-fetches`, damit sich die Kette
  für wenige Cent prüfen lässt, statt jeden Testlauf mit dem vollen Budget zu
  bezahlen.
- Die Preise in `research.pricing` sind von Hand gepflegt und können still
  veralten; die Logzeile kennzeichnet den Wert deshalb als Schätzung. Eine
  automatische Preisabfrage gibt es bewusst nicht.
- `research.allowed_domains` heißt jetzt `research.fetch_allowed_domains`.
  Der alte Name versprach eine Geltung, die er nach der Öffnung der Suche
  nicht mehr hat.

### Nachtrag: Befunde der unabhängigen Review

17. **Ein Bericht ohne Belege gilt nicht als abgeschlossen.** Meldet das
    Modell `COMPLETED`, sind aber null Zitate zustande gekommen, wird auf
    `INSUFFICIENT_DATA` mit `reason="no_citations"` herabgestuft. Ohne diese
    Prüfung wäre der Fehllauf vom 2026-08-17 stillschweigend als vollständiger
    Bericht in der Datenbank gelandet — und ein künftiger Bruch der
    Zitat-Extraktion (neue Werkzeugversion, geändertes Blockformat) fiele
    ebenso wenig auf.
18. **Ein mehrdeutiger Dokumenttitel lässt das Zitat entfallen.** Zwei per
    `web_fetch` geholte Dokumente mit gleichem Titel — bei SEC-Filings der
    Normalfall — machen die Zuordnung über den Titel zu Raten. Vorher gewann
    das zuerst gefundene, wodurch Zitate aus dem zweiten Dokument eine falsche
    Quelle bekamen. Eine falsche Quellenangabe ist schlechter als gar keine,
    konsistent zum Umgang mit unauflösbaren Titeln.
19. **`Citation.retrieved_at` ist der vom Abruf gemeldete Zeitpunkt**, nicht
    mehr der Laufbeginn — das Feld verspricht die eigene Abrufzeit, und
    zwischen beiden liegen bei mehreren Runden Minuten. Für Suchtreffer bleibt
    es beim Laufbeginn; einen besseren Wert liefert die API dort nicht.
20. **Das Token-Budget zählt den gesamten Eingabekontext.**
    `usage.input_tokens` ist nur der ungecachte Rest; bei
    `pause_turn`-Fortsetzungen greift automatisches Prompt-Caching, sodass der
    wiederholt verrechnete Kontext größtenteils als `cache_read` erscheint. Die
    Notbremse hätte so an genau dem Fall vorbeilaufen können, gegen den sie
    eingebaut wurde. Die Kostenschätzung rechnet Cache-Lesen und -Schreiben
    jetzt mit ihren eigenen Faktoren (0,1× bzw. 1,25×).
21. **`thinking` wird ausdrücklich gesetzt.** Auf Sonnet 5 läuft ein Aufruf
    ohne dieses Feld mit adaptivem Denken, und `max_tokens` deckelt Denken und
    Antworttext **gemeinsam**. Die Recherchephase bekommt `adaptive` (echte
    Mehrschrittarbeit), die Strukturierungsphase `disabled` (sie formt nur
    vorhandenen Text um) — dort hätte ein langer Werkzeugaufruf sonst
    abgeschnitten werden können, obwohl die teure Recherche schon erfolgreich
    war. `max_output_tokens` ist konfigurierbar und auf 16.000 angehoben.
22. **Ein Zeitlimit am Anthropic-Client** (`request_timeout_seconds`, 300 s).
    Der SDK-Standard sind 600 s Lesezeit mal zwei Wiederholungen — eine
    hängende Anfrage hätte einen der vier nebenläufigen Arbeiter fast eine
    Stunde blockiert.

Ebenfalls behoben, im Application Layer: Ein Research-Anbieter, der entgegen
seinem Vertrag eine rohe Ausnahme statt `ResearchProviderError` wirft, hat die
Aktie als Ganzes in `StockProcessingError` verschoben — samt dem bereits
fertig berechneten, deterministischen Screening-Ergebnis. Das war genau die
Kopplung, die CLAUDE.md ausschließt. `_evaluate_research` fängt das jetzt ab
und liefert `UNAVAILABLE` mit `reason="provider_contract_violation"`.

### Am ersten vollständigen Lauf sichtbar gewordene Folgepunkte

Der erste Lauf mit funktionierender Quellenbindung (2026-08-17, rund 40 Zitate,
0,325 $) hat drei Schwächen belegt, die vorher nur vermutet waren. Alle drei
sind Qualitätsthemen, keine Fehler — sie gehören in eine eigene Entscheidung:

- **Die Lizenzklassifikation sagt nichts mehr aus.** Sämtliche Zitate wurden
  `UNKNOWN`, weil `_NEWS_MEDIA_DOMAINS` nur Agenturen und Wire-Dienste kennt,
  die Suche aber CNBC, Fortune, Yahoo Finance, MacRumors und Engadget
  lieferte. Zugleich stehen dort Aggregatoren und automatisiert erzeugte
  Analyseseiten (`stockinvest.us`, `marketbeat.com`, `finbold.com`)
  gleichberechtigt neben etablierten Medien. Nötig ist eine echte
  Quellenhierarchie mit einer eigenen Klasse für Quellen geringer Beweiskraft,
  die für harte Finanz- oder Rechtsfakten nicht als alleiniger Beleg zählen.
- **Primärquellen kommen nicht vor.** `web_fetch` wurde in keinem Lauf
  benutzt: Die Suche liefert Sekundärberichterstattung, und
  `fetch_allowed_domains` lässt nur `sec.gov` und Wire-Dienste zu — jeder
  Abrufversuch auf einen Suchtreffer liefe auf `url_not_allowed`. Der
  Systemprompt verlangt „Bevorzuge Primärquellen", die Konfiguration macht es
  unmöglich. Entweder gezielt nach SEC-Einreichungen suchen lassen oder die
  Abruf-Allowlist an das ausrichten, was die Suche tatsächlich findet.
- **Die Zitatmenge ist ungesteuert.** Rund 40 Zitate für einen Bericht sind
  eher Rohmaterial als Beleg. Eine Obergrenze und eine Priorisierung nach
  Quellenklasse fehlen.
