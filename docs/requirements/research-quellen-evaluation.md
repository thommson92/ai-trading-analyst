# Externe Quellen für den Research Agent

Stand 2026-08-16. **Erledigt** — die Entscheidung steht in
[ADR 0022](../adr/0022-research-agent-quellen.md). Dieses Dokument bleibt als
Beleg erhalten: Es beantwortet die in
[ADR 0021](../adr/0021-ki-anbindung-anthropic-api.md) offen gelassene Frage,
woher der Research Agent seine externen Inhalte bezieht (Doc 06:
Nachrichten, Unternehmensmeldungen, Analystenberichte, SEC Informationen).
Wie bei
[docs/requirements/earnings-anbieter-evaluation.md](earnings-anbieter-evaluation.md)
und
[docs/requirements/resc-lizenzpruefung.md](resc-lizenzpruefung.md) trennt
dieses Dokument **belegt** (aus offizieller Erstanbieter-Dokumentation, mit
Fundstelle) von **Annahme** (Erfahrungswert, bei Implementierung
gegenzuprüfen).

## Der entscheidende Punkt: schon ein Anbieter gewählt

ADR 0021 hat den KI-Anbieter bereits auf Anthropic festgelegt. Bevor eine
gesonderte Such-/News-API mit eigenem Vertrag und eigener Rechnung evaluiert
wird, lohnt die Prüfung, ob Anthropics **eigene, serverseitige Werkzeuge**
(Web Search, Web Fetch) ausreichen -- dieselbe Rechnung, kein zusätzlicher
Anbieter, passt zur "ein Anbieter"-Entscheidung aus ADR 0021.

## 1. Anthropic Web Search Tool

### 1.1 Belegt (aus der offiziellen Dokumentation, abgerufen 2026-08-16)

Quelle: [platform.claude.com/docs -- Web search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool)

| Angabe | Wert |
|---|---|
| Zugriffsweg | Serverseitiges Tool in der regulären Messages API (`type: web_search_20250305` oder neuer) -- kein separater Vertrag, keine separate Rechnung |
| Preis | **10 USD je 1.000 Suchen**, zusätzlich normale Tokenkosten für die zurückgegebenen Suchergebnisse als Input-Tokens |
| Ergebnisformat | Je Treffer `url`, `title`, `page_age`, `encrypted_content` (für Mehrrunden-Gespräche zurückzugeben) |
| Zitate | Immer aktiv, je Zitat `url`, `title`, `cited_text` (bis 150 Zeichen), `encrypted_index` -- deckt CLAUDE.mds "Quellenbindung" strukturell ab |
| Domain-Filter | `allowed_domains` **oder** `blocked_domains` (nicht beides), z. B. auf vertrauenswürdige Finanznachrichtenseiten einschränkbar |
| Kostenkontrolle | `max_uses` begrenzt Suchen je Anfrage hart |
| Fehlgeschlagene Suche | Wird nicht berechnet (laut Dokumentation) |
| Rechtlicher Hinweis | *"When displaying API outputs directly to end users, citations must be included... If you are making modifications... by reprocessing or combining them with your own material, display citations as appropriate based on consultation with your legal team."* -- **nicht abschließend geklärt, siehe Abschnitt 4** |

### 1.2 Anthropic Web Fetch Tool

Quelle: [platform.claude.com/docs -- Web fetch tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-fetch-tool)

| Angabe | Wert |
|---|---|
| Zweck | Vollständigen Inhalt einer **bekannten** URL abrufen (auch PDF) -- ergänzt Web Search: erst suchen, dann gezielt eine gefundene Quelle vollständig lesen |
| Preis | **Keine Zusatzkosten** -- nur normale Tokenkosten für den abgerufenen Inhalt |
| Sicherheitsgrenze | Claude kann **keine** URL selbst erfinden -- nur URLs abrufen, die bereits im Kontext stehen (Nutzereingabe, vorheriges Such-/Fetch-Ergebnis). Verhindert das Modell als Werkzeug fürs Nachschlagen beliebiger, potenziell schädlicher Adressen |
| Datenexfiltrationswarnung | Anthropic warnt ausdrücklich: Web Fetch in Umgebungen mit nicht vertrauenswürdiger Eingabe **und** sensiblen Daten im selben Kontext ist riskant -- Empfehlung: `allowed_domains` einschränken, `max_uses` begrenzen |
| Einschränkung | Kein JavaScript-Rendering -- rein clientseitig aufgebaute Seiten liefern keinen Inhalt |
| Zitate | Optional (`citations.enabled`), anders als bei Web Search nicht standardmäßig an |

**Zusammenspiel:** Web Search zum Auffinden, Web Fetch zum vollständigen
Lesen einer konkreten Quelle (z. B. eine über die Suche gefundene
Unternehmensmeldung oder einen SEC-Filing-Link) -- genau das in der
Dokumentation beschriebene "Combined search and fetch"-Muster.

### 1.3 Grobe Kostenabschätzung (Annahme, keine Messung)

Bei geschätzt 3-10 Suchen je Kandidat (Doc 06: Nachrichten, Analysten,
Marktumfeld) und einer erwarteten, niedrigen ein- bis zweistelligen Zahl
qualifizierter Kandidaten pro Tag (Beobachtung aus dem Earnings-Filter-Betrieb,
[earnings-anbieter-evaluation.md](earnings-anbieter-evaluation.md)):
Suchgebühr allein liegt bei rund 0,03-0,10 USD je Kandidat -- bei 20
Kandidaten/Tag und 20 Handelstagen/Monat also grob 12-40 USD **allein an
Suchgebühr**, exklusive Token- und Fetch-Kosten. Das ist ohne Feinsteuerung
(`max_uses`, Modellwahl) am oberen Rand des in ADR 0021 gesetzten
20-30-EUR-Korridors -- **muss vor der Implementierung mit echten Zahlen
nachgemessen werden**, nicht nur geschätzt.

## 2. SEC EDGAR

### 2.1 Belegt

Quelle: [SEC.gov -- Accessing EDGAR Data / EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces),
Suchergebnisse vom 2026-08-16.

| Angabe | Wert |
|---|---|
| Zugang | Vollständig kostenlos, kein API-Schlüssel, keine Registrierung |
| Pflicht | `User-Agent`-Header mit Selbstauskunft (Name/Kontakt) -- sonst Sperre |
| Rate Limit | 10 Anfragen/Sekunde über alle EDGAR-APIs, bei Überschreitung temporäre IP-Sperre (fair-access, kein Vertrag) |
| Volltextsuche | `efts.sec.gov` -- Suche über Einreichungstexte, praktisch für Nachrichten-/Ereignissuche zu einem Symbol |
| Strukturierte Kennzahlen | `data.sec.gov/api/xbrl/companyfacts/CIK{10-stellig}.json` liefert **jeden** je gemeldeten XBRL-Wert eines Unternehmens (Umsatz, Bilanzsumme, Aktien im Umlauf etc.) als strukturiertes JSON |

### 2.2 Wichtiger fachlicher Punkt: nicht alles über den Research Agent laufen lassen

Doc 06 nennt "Fundamentaldaten" (Wachstum, Bewertung, Profitabilität,
Verschuldung) als eigenen Aufgabenbereich (Fundamental Agent). Die
`companyfacts`-API liefert diese Werte bereits **strukturiert und
maschinenlesbar** -- ein direkter, deterministischer Abruf (kein
Sprachmodell im Pfad) passt besser zu CLAUDE.mds zentraler Regel
*"Technische Signale werden niemals durch KI verändert"* und der
Backtesting-Erfahrung, dass Zahlen dort am verlässlichsten sind, wo sie nicht
erst aus Fließtext herausgelesen werden müssen. **Vorschlag für die
spätere Umsetzung** (nicht Teil dieser Untersuchung): Der Fundamental Agent
liest `companyfacts` direkt und deterministisch; das Sprachmodell
interpretiert die bereits berechneten Kennzahlen, erfindet sie nicht. Web
Search/Fetch bleiben dem Research Agent für qualitative, nicht strukturierte
Inhalte (Nachrichten, Analystenkommentare, Unternehmensmeldungen)
vorbehalten -- exakt die in CLAUDE.md geforderte Trennung von
deterministischer Berechnung und KI-Interpretation, jetzt auch auf der
Datenbeschaffungsseite statt nur bei der Auswertung.

## 3. Deckt das Doc 06 vollständig ab?

| Doc-06-Bereich | Abgedeckt durch |
|---|---|
| Aktuelle News, Unternehmensmeldungen | Web Search + Web Fetch |
| Analystenberichte (Kursziele, Empfehlungen) | Web Search + Web Fetch -- **keine strukturierte, verlässliche Gratis-API dafür bekannt**; Finnhub deckt das kostenpflichtig ab ([earnings-anbieter-evaluation.md](earnings-anbieter-evaluation.md) P7), aber nur für Earnings/Ratings, nicht als allgemeine Recherche |
| SEC-Informationen | SEC EDGAR Volltextsuche + `companyfacts` (siehe 2.2) |
| Marktumfeld (Branche, Konkurrenz, Makro) | Web Search |

Keine Lücke, die einen dritten Anbieter zwingend erfordert -- Analystenratings
bleiben ein offener Punkt, aber der ist bereits in ADR 0017 als eigenständige,
kostenpflichtige Frage vorgemerkt (F9, zurückgestellt) und nicht spezifisch
für den Research Agent.

## 4. Offene Punkte -- nicht Teil dieser Untersuchung

1. **Lizenzfrage bei Weiterverarbeitung.** Die Dokumentation verlangt
   ausdrücklich Rücksprache mit "legal team", sobald Suchergebnisse nicht
   unverändert mit Zitat angezeigt, sondern umformuliert/kombiniert werden --
   genau das tut der Research Agent (strukturierter Bericht statt
   Rohtreffer). Nach der RESC-Erfahrung wird hier **keine Annahme
   getroffen**: Vor der Implementierung sind Anthropics
   [Nutzungsbedingungen](https://www.anthropic.com/legal/commercial-terms)
   und die [Usage Policy](https://www.anthropic.com/aup)
   konkret auf diesen Anwendungsfall zu prüfen -- ein persönliches,
   nicht-öffentliches Dashboard mit dauerhafter, aber nicht weitergegebener
   Speicherung ist ein anderer Fall als eine öffentlich zugängliche
   Anwendung, aber das ist eine Einschätzung, keine Feststellung.
2. **Prompt-Injection-Abwehr** (Doc 10 §13, CLAUDE.md "Sicherheit"): Wie
   Suchergebnisse als reine Daten markiert werden, ohne dass Inhalte
   fremder Webseiten als Instruktion wirken können, ist Design der
   eigentlichen Research-Agent-Implementierung, nicht dieser
   Quellenauswahl.
3. **Reale Kostenmessung** statt der groben Schätzung in Abschnitt 1.3.

## Empfehlung

**GO_WITH_LIMITATIONS:** Anthropic Web Search + Web Fetch für Nachrichten,
Meldungen, Marktumfeld; SEC EDGAR `companyfacts` deterministisch (nicht über
den Research Agent) für Fundamentaldaten. Einschränkung: Punkt 4.1
(Lizenzfrage bei Weiterverarbeitung) ist vor der Implementierung zu klären,
nicht erst danach -- das war genau der Fehler, der bei TradingView
(non-display) und bei RESC vermieden wurde.
