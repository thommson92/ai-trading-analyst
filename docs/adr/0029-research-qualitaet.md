# ADR 0029: Research-Qualität — Quellenrang, Abdeckung, Zitatgrenze, Quellenalter

- Status: Angenommen
- Datum: 2026-08-23

## Kontext

[ADR 0023](0023-research-agent-zitierarchitektur.md) hält vier Mängel des
Research Agent ausdrücklich als offene Folgepunkte fest, statt sie zu
übergehen. Das [Repository-Audit vom 2026-08-23](../audits/2026-08-23-repository-audit.md)
hat sie als Entscheidungsvorlage E5 gebündelt und an eine Bedingung geknüpft:
„HOCH, sobald `--research-provider anthropic` täglich läuft."

**Diese Bedingung ist eingetreten.** Der Research Agent läuft im täglichen
Scharfbetrieb. Damit sind die Mängel keine Vorsorge mehr — sie wirken bei
jedem Lauf und kosten jeden Abend Geld und Belegqualität.

Beim Nachlesen im Adapter und im Anthropic-SDK sind zwei Punkte schärfer
geworden, als sie im Audit stehen:

- **Der Systemprompt nannte die abrufbaren Domains nicht.** Er sagte „auf
  wenige vertrauenswürdige Domains beschränkt", ohne sie aufzuzählen. Das
  Modell musste raten. Jeder Fehlgriff ist eine weitere Iteration der
  serverseitigen Werkzeugschleife und verrechnet den **gesamten**
  angesammelten Kontext erneut — genau das ist die in ADR 0023 gemessene
  Kostenstreuung (ein Lauf mit knappem Kontingent: 0,315 USD, überwiegend für
  abgelehnte Versuche).
- **Suchtreffer wurden gar nicht ausgewertet.** `_scan_tool_result` stieg bei
  einer Liste sofort aus — und ein Suchergebnis ist immer eine Liste. Dort
  steckt `page_age`, das einzige Alterssignal, das die API überhaupt liefert.

## Entscheidung

### 1. Der Quellenrang steht neben der Lizenzklasse, nicht an ihrer Stelle

`SourceLicenseClass` beantwortet, was mit einem Inhalt rechtlich geschehen
darf. `SourceRank` beantwortet, wie belastbar er ist. Das sind zwei Fragen,
und ein Feld für beide hätte eine davon verdrängt — eine Agenturmeldung kann
urheberrechtlich heikel und trotzdem gut belegt sein.

Sechs Stufen, von der belastbarsten zur schwächsten: `REGULATORY`, `COMPANY`,
`FINANCIAL_MEDIA`, `GENERAL_MEDIA`, `AGGREGATOR`, `UNRANKED`. Die Reihenfolge
steht als ausdrückliche Konstante `RANGFOLGE`, nicht als
Deklarationsreihenfolge des Enums: Eine später eingefügte Stufe würde die
Sortierung sonst still verschieben.

`UNRANKED` ist **keine** Aussage über die Güte, sondern nur darüber, dass wir
die Quelle nicht kennen.

Wie die Lizenzklasse wird der Rang **deterministisch aus der URL** bestimmt und
nie vom Sprachmodell erfragt (CLAUDE.md: Klassifikationen nicht aus
LLM-Freitext übernehmen). Ein Dokument, das von sich behauptet, amtlich zu
sein, ändert daran nichts — dafür gibt es eine Testsonde.

### 2. Der Systemprompt nennt die abrufbaren Domains

Die konfigurierte `fetch_allowed_domains` wird in den Systemprompt eingesetzt,
zusammen mit dem Hinweis, dass ein abgelehnter Abruf trotzdem kostet. Die
Liste ist die eigene Konfiguration, kein Fremdinhalt — sie darf deshalb in die
Instruktion, anders als Recherchetext.

Prompt-Version auf **`research-v2`**. Ein geänderter Prompt ist eine
Verfahrensänderung und muss am Ergebnis sichtbar sein.

### 3. Zitate werden nach Rang sortiert und gedeckelt

Nach der vorhandenen Deduplizierung wird **stabil** nach `RANGFOLGE` sortiert
und auf `research.max_citations` (Standard 15) gekappt. Wie viele Zitate dabei
weggefallen sind, steht am Bericht.

Das ersetzt einen Teil von **ADR 0023, Entscheidung 6**: Die Reihenfolge der
ersten Nennung bleibt erhalten — aber innerhalb eines Rangs, nicht über alle
Zitate hinweg. Die stabile Sortierung ist dafür die tragende Eigenschaft, kein
Implementierungsdetail.

Gedeckelt statt vollständig gespeichert, weil ein Bericht mit rund 40
ungewichteten Belegen niemanden in die Lage versetzt zu erkennen, worauf er
steht. Die Zahl der verworfenen Zitate steht daneben, damit die Auslassung
nicht still bleibt.

### 4. Die Abdeckung ist deterministisch und steht neben dem Status

`ResearchStatus` sagt, dass ein Lauf technisch durchgelaufen ist.
`ResearchCoverage` (`BROAD` · `LIMITED` · `THIN`) sagt, worauf er steht. Beides
in ein Feld zu pressen hätte einen der beiden Befunde verschwinden lassen.

Berechnet aus dem, was **messbar geschehen ist** — nie aus einer Selbstauskunft
des Modells. Ein Modell, das eine dünne Quellenlage nicht erkennt, meldet auch
eine gute Abdeckung. Der in ADR 0023 dokumentierte Fehllauf (eine Suche, null
erfolgreiche Abrufe, acht abgelehnte Werkzeugaufrufe, `COMPLETED` mit
Confidence 0,55) ist damit `THIN`.

Die Zahlen, aus denen die Stufe entsteht, werden **mitgespeichert**
(`ResearchEvidence`): verschiedene Quellen vor der Deckelung, erfolgreiche
Abrufe, abgelehnte Werkzeugaufrufe, verworfene Zitate. Eine Einstufung ohne
die Zahlen dahinter wäre ein weiteres undurchsichtiges Etikett, und ob eine
Schwelle richtig gewählt war, lässt sich später nur an den Rohwerten prüfen —
dasselbe Muster wie beim Backtest, der rohe und deduplizierte Stichprobengröße
beide ausweist.

Der beste erreichte Rang wird **nicht** gespeichert: Er ist aus den Zitaten
ablesbar, weil die Deckelung die schwächsten zuerst entfernt.

Die Schwellen stehen als benannte Konstanten im Code, nicht in der
Konfiguration. Sie sind Teil des Verfahrens, und ein Verfahren wird
versioniert, nicht eingestellt.

### 5. Das Quellenalter wird roh gespeichert und nie umgerechnet

`Citation.source_age` nimmt auf, was der Anbieter meldet — unverändert.

**Es heißt ausdrücklich nicht `published_at`**, weil es keines ist:
`page_age` ist relativ („3 days ago"), steht nur im Suchtrefferblock und
fehlt bei `web_fetch` vollständig. Daraus ein Datum zu rechnen wäre ein
abgeleiteter Wert an einer Stelle, die Genauigkeit verspricht — CLAUDE.md
verbietet genau das. Der Wert wird gespeichert, nie geparst, und fließt in
keine Berechnung ein.

## Begründung

Die Trennung von Rang und Lizenz (1) ist die einzige der vier Entscheidungen,
die etwas kostet, das man sich hätte sparen können: ein zweites Feld und eine
Migration. Sie ist es wert, weil der Rang ohnehin gebraucht wird, um Zitate zu
sortieren (3) — und ihn aus der Lizenzklasse abzuleiten hätte bedeutet, die
Lizenzfrage nach Qualitätsgesichtspunkten zu beantworten.

(2) ist der billigste Eingriff mit der größten erwarteten Wirkung: Er ändert
keine Datenstruktur und beseitigt vermutlich den größten Einzelposten der
Kostenstreuung.

(4) folgt dem Muster des Technical Agent (ADR 0026): deterministisch rechnen,
die KI nur einordnen lassen. Eine vom Modell gemeldete Abdeckung wäre
bequemer, aber nicht nachprüfbar.

(5) ist die ehrlichste verfügbare Antwort auf einen Punkt, den ADR 0023
bewusst offengelassen hat. Sie erfüllt die Quellenbindung nicht, aber sie
liefert statt gar nichts das, was der Anbieter tatsächlich sagt.

## Konsequenzen

- **Was aus ADR 0023 ersetzt wird:** Entscheidung 4 bleibt gültig, ist aber
  nicht länger die einzige Quelleneinordnung. Entscheidung 6 gilt weiter,
  jetzt innerhalb eines Rangs. Alles übrige bleibt unberührt; ADR 0023 selbst
  wird nicht geändert.
- **Der offene Folgepunkt `published_at` ist beantwortet, nicht erfüllt.** Die
  Quellenbindungs-Regel aus CLAUDE.md („URL, Veröffentlichungs- und
  Abrufzeitpunkt") bleibt für LLM-recherchierte Zitate teilweise offen. Neu
  ist, dass der gemeldete Rohwert vorliegt statt gar nichts, und dass klar
  benannt ist, warum mehr nicht geht.
- **Alte Berichte behaupten keine Abdeckung.** Alle neuen Spalten sind
  nullable, es gibt keine Rückrechnung. Ein vor dieser Migration geschriebener
  Bericht liefert `coverage=None`, `evidence=None` und `UNRANKED` — nicht
  Nullen, die eine Messung vortäuschen würden.
- **Die Kostenwirkung ist erwartet, nicht belegt.** Sie entsteht aus
  ausbleibenden Fehlversuchen gegen die echte API und lässt sich lokal nicht
  messen. Ein Vergleichslauf auf dem Server nach dem Merge beantwortet das;
  bis dahin ist die Verbesserung eine begründete Erwartung.
- **`fetch_allowed_domains` wurde bewusst nicht erweitert.** Eine Domain, die
  Anthropics Crawler aussperrt, lässt die *gesamte* Anfrage mit einem 400
  scheitern (ADR 0023) — jede neue Domain gehört einzeln durch einen echten
  Lauf, nicht in dieselbe Änderung.
- Die Domainlisten für Rang und Lizenzklasse sind von Hand gepflegt und
  veralten still — dasselbe bekannte Problem wie bei den Preislisten
  (Risiko R8 des Audits). `UNRANKED` ist der unschädliche Ausgang: Es
  behauptet nichts.
