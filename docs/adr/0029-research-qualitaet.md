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

**Die Regel steht in der Domain**, nicht im Anthropic-Adapter
(`domain/research/sources.py`) — dasselbe Muster wie `_classify_confidence`
beim Backtest. Läge sie im Adapter, hätten zwei Anbieter zwei Antworten auf
dieselbe Frage, und in derselben Spalte `research_coverage` stünden Werte, die
nach verschiedenen Verfahren entstanden sind. Der Fixture-Anbieter ruft
dieselbe Funktion auf, statt seine Einstufung hinzuschreiben.

### 2. Der Systemprompt nennt die abrufbaren Domains

Die konfigurierte `fetch_allowed_domains` wird in den Systemprompt eingesetzt,
zusammen mit dem Hinweis, dass ein abgelehnter Abruf trotzdem kostet. Die
Liste ist die eigene Konfiguration, kein Fremdinhalt — sie darf deshalb in die
Instruktion, anders als Recherchetext.

Prompt-Version auf **`research-v2`**. Ein geänderter Prompt ist eine
Verfahrensänderung und muss am Ergebnis sichtbar sein.

### 3. Zitate werden nach Rang sortiert und gedeckelt

Nach der vorhandenen Deduplizierung wird nach `RANGFOLGE` sortiert und auf
`research.max_citations` (Standard 25, siehe Nachtrag) gekappt. Wie viele Zitate dabei
weggefallen sind, steht am Bericht.

**Gekappt wird reihum je Quelle, nicht der Reihe nach.** Ein Deckel, der
schlicht die ersten fünfzehn der rangsortierten Liste nimmt, wirkt auf
*Zitate* und verliert dabei *Quellen*: Zwanzig Fundstellen aus einem einzigen
Filing hätten alle Plätze belegt und jede unabhängige Bestätigung verdrängt.
Der Bericht sagte dann etwas über eine Nachricht, deren einzige unabhängige
Quelle nicht mehr gespeichert ist — gegen die Quellenbindung. Deshalb bekommt
zuerst jede Quelle einen Beleg, in Rangfolge, dann einen zweiten, und so fort.
Quellen gehen erst verloren, wenn es mehr davon gibt als Plätze.

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

Die Zahlen werden **mitgespeichert** (`ResearchEvidence`): verschiedene
Quellen, erfolgreiche Abrufe, abgelehnte Werkzeugaufrufe, verworfene Zitate.
`distinct_sources` zählt die **gespeicherten** Belege, damit sich die Zahl an
den Zitaten derselben Zeile nachrechnen lässt statt eine Breite zu behaupten,
die dort nicht mehr steht.

Zwei der vier Zahlen gehen in die Einstufung ein, zwei nicht:
`rejected_tool_calls` und `dropped_citations` sagen etwas über verbrannte
Kosten und über Auslassungen, nicht über die Belegdichte. Was die Ablehnungen
an Belegen gekostet haben, steht bereits in den beiden Zahlen, die eingehen.
Sie werden gespeichert, weil sie die **Diagnose** tragen, nicht die Stufe.
Ein erfolgreicher Abruf zählt außerdem nur, wenn das Dokument einen Titel
trägt — sonst lässt sich kein Zitat darauf zurückführen, und ein bezahlter,
aber unbelegbarer Abruf hätte die `BROAD`-Schwelle geöffnet. Eine Einstufung ohne
die Zahlen dahinter wäre ein weiteres undurchsichtiges Etikett, und ob eine
Schwelle richtig gewählt war, lässt sich später nur an den Rohwerten prüfen —
dasselbe Muster wie beim Backtest, der rohe und deduplizierte Stichprobengröße
beide ausweist.

Der beste erreichte Rang wird **nicht** gespeichert: Er ist aus den Zitaten
ablesbar, weil die Deckelung die schwächsten zuerst entfernt.

Die Schwellen stehen als benannte Konstanten im Code, nicht in der
Konfiguration. Sie sind Teil des Verfahrens, und ein Verfahren wird
versioniert, nicht eingestellt: `RESEARCH_ANALYSIS_VERSION` steht an jedem
Ergebnis, getrennt von der Prompt-Version, weil beide sich unabhängig ändern
(Muster `TECHNICAL_ANALYSIS_VERSION`). Ohne dieses Feld ließe sich ein
gespeicherter `coverage`-Wert nicht der Regel zuordnen, unter der er
entstanden ist.

`max_citations` bleibt dagegen Konfiguration: Wie viele Belege eine
Installation aufhebt, ist eine Betriebsentscheidung und ändert die Einstufung
nicht — die Deckelung wirkt erst weit oberhalb der Abdeckungsschwellen.

### 5. Das Quellenalter wird roh gespeichert und nie umgerechnet

`Citation.source_age` nimmt auf, was der Anbieter meldet — unverändert.

**Es heißt ausdrücklich nicht `published_at`**, weil es keines ist:
`page_age` ist relativ („3 days ago"), steht nur im Suchtrefferblock und
fehlt bei `web_fetch` vollständig. Daraus ein Datum zu rechnen wäre ein
abgeleiteter Wert an einer Stelle, die Genauigkeit verspricht — CLAUDE.md
verbietet genau das. Der Wert wird gespeichert, nie geparst, und fließt in
keine Berechnung ein.

### Nachtrag: am ersten echten Lauf nachgeschärft (2026-08-24)

Ein Lauf gegen die Anthropic-API (AAPL, `research-v1`, 38 Zitate aus 19
Quellen, 0,524 USD) hat drei Dinge gezeigt, die die erdachten Testfälle nicht
zeigen konnten.

**`www.apple.com/newsroom/…` fiel auf `UNRANKED` durch.** Für einen
CEO-Wechsel die verlässlichste denkbare Quelle — und die Einstufung sah sie
nicht, weil sie nur IR-*Unterdomains* erkannte (`investor.apple.com`). Die
Hauptdomain eines Unternehmens lässt sich weder auflisten noch am Host
erkennen; ihr Newsroom-Pfad dagegen schon. `_UNTERNEHMENSPFADE` prüft
`/newsroom`, `/press-release`, `/press-releases`, `/investor-relations` —
**nach** den Medienlisten, damit ein `/press-releases`-Bereich einer
Nachrichtenseite sie nicht zur Unternehmensmeldung macht.

**Damit war `BROAD` faktisch unerreichbar.** Ohne `REGULATORY` oder `COMPANY`
ist `hat_substanz` falsch, und ein Nachrichtenbericht ohne SEC-Filing hat
weder das eine noch das andere. Eine Stufe, die nie vergeben wird, ist keine
Stufe. Der Newsroom-Pfad behebt das; ein Test hält es an genau diesem
Quellensatz fest.

**Die Obergrenze von 15 war zu knapp.** Bei 19 verschiedenen Quellen hätte die
Deckelung vier davon ganz verloren — obwohl sie gerade die Vielfalt schützen
soll. Ab 20 überleben alle; der Standard steht jetzt auf **25**, das lässt Luft
und halbiert die Zeilenzahl trotzdem.

**Was der Lauf außerdem geradegerückt hat:** Dieses ADR nannte den nicht
benannten Domain-Katalog im Prompt als vermutlich größten Kostenposten. Der
Lauf zeigt **einen einzigen** `url_not_allowed` — die Ersparnis daraus ist
Kleingeld. Der eigentliche Posten steht daneben: **113.685 Eingabe-Token,
davon 0 aus dem Cache.** Über zwei Runden wird der Kontext der ersten
vollständig neu verrechnet. Prompt-Caching ist damit der wirksamere Hebel und
gehört in eine eigene Entscheidung; es ist **nicht** Teil dieses ADR.

Und ein Befund über die Recherche selbst, nicht über ihre Einstufung: **31 der
38 Zitate bleiben `UNRANKED`** — 24/7 Wall St., ts2.tech, clearank, tickernerd,
lawfold und ähnliche. Das ist kein Mangel der Rangzuordnung, sondern ihr
eigentlicher Zweck: Sie macht sichtbar, worauf sich die Recherche tatsächlich
stützt. Ob daraus eine Konsequenz folgt — engere Suchführung, ein Mindestrang
für zitierfähige Quellen — ist eine eigene Entscheidung und hier bewusst nicht
getroffen.

### Nachtrag: der Vergleichslauf, und was er widerlegt (2026-08-24)

Der Nachher-Lauf auf dem Server (AAPL, `research-v2`) gegen den Vorher-Lauf
desselben Tages:

| | vorher | nachher |
|---|---|---|
| Kosten | 0,524 USD | **0,584 USD** |
| Eingabe-Token, ungecacht | 113.685 | 120.933 |
| Abgelehnte Werkzeugaufrufe | 1 | 0 |
| Erfolgreiche Abrufe | — | **0** |
| Rang, Alter, Deckelung, Abdeckung | fehlten | greifen |

**Die Qualitätswirkung ist eingetreten, die Kostenwirkung nicht.** Entscheidung
(2) — der Prompt nennt die abrufbaren Domains — hat den einen abgelehnten
Abruf beseitigt, den es gab. Der längere Prompt kostete mehr, als er sparte.
Der oben stehende Satz, (2) sei „der billigste Eingriff mit der größten
erwarteten Wirkung", ist damit **widerlegt**. Er bleibt stehen; ein ADR wird
nicht rückwirkend geändert.

**`BROAD` verlangt keinen erfolgreichen Abruf mehr.** Entscheidung (4) wird an
dieser einen Stelle korrigiert: `successful_fetches > 0` entfällt aus der
Schwelle, `RESEARCH_ANALYSIS_VERSION` steigt auf `research-analysis-v2`.

Der Grund ist gemessen, nicht theoretisch. `fetch_allowed_domains` enthält
`sec.gov`, drei Pressedienste und `nasdaq.com` — **keine davon kam in den
Suchtreffern vor.** Das Modell hat sich korrekt verhalten: gesucht, nichts
Abrufbares gefunden, nicht abgerufen, nichts verschwendet. Der erste Nachtrag
hat `BROAD` über den Newsroom-Pfad erreichbar gemacht; diese zweite Hürde stand
noch dahinter. Ausgerechnet `apple.com/newsroom`, die beste Quelle des Laufs,
ist nicht abrufbar.

Der Preis ist ausdrücklich zu benennen: `BROAD` unterscheidet nicht mehr
zwischen einem gelesenen Filing und gut belegten Suchschnipseln, und der
Abstand zu `LIMITED` schrumpft auf „zwei Quellen gegen drei plus Substanz".
`successful_fetches` wird weiter erhoben, gespeichert und ausgewiesen — die
Bedingung ist damit rückholbar, sobald die Allowlist die tatsächlich
gefundenen Primärquellen erreicht. Der andere Weg — die Allowlist erweitern —
wurde erwogen und zurückgestellt: Eine Domain, die Anthropics Crawler
aussperrt, lässt die gesamte Anfrage mit einem 400 scheitern, das braucht je
Kandidatin einen echten Lauf.

**Zwei Aussagen des ersten Nachtrags waren falsch.** Er schrieb, über zwei
Runden werde der Kontext der ersten vollständig neu verrechnet. Ein
Research-Lauf besteht aber aus **zwei Anfragen unterschiedlicher Art** —
Recherche und Strukturierung —, nicht aus zwei Recherche-Runden; `pause_turn`
trat nicht auf. Die Token entstehen in der serverseitigen Werkzeugschleife
*innerhalb einer* Anfrage. Und es greift **kein** automatisches Prompt-Caching:
0 gelesene, 0 geschriebene Cache-Token. Ob ein Cache-Breakpoint innerhalb der
Werkzeugschleife überhaupt wirkt, ist offen und wird gemessen, bevor darüber
entschieden wird.

### Nachtrag: die offene Cache-Frage ist beantwortet (2026-08-24)

Der Nachtrag darüber lässt zwei Fragen offen und kündigt eine Messung an.
Beide sind inzwischen beantwortet — **nicht hier, sondern in
[ADR 0023](0023-research-agent-zitierarchitektur.md), Nachtrag „Prompt-Caching
wird nicht gebaut"**, weil dort die Kostensteuerung des Research-Adapters
festgelegt ist.

Kurzfassung, damit niemand diesem Dokument bis zu einem „offen" folgt: Ein
Cache-Breakpoint erfasst weniger als ein Prozent der Eingabe-Token. Die
Instrumentierung je Anfrage zeigt 109.324 Token in der Recherche gegen 7.061
in der Strukturierung; die 94 % entstehen in der serverseitigen
Werkzeugschleife *innerhalb einer* Anfrage, wo es keinen wiederholten Präfix
zwischen Anfragen gibt. Damit ist auch die Aussage dieses ADR, Prompt-Caching
sei „der wirksamere Hebel", widerlegt. Sie bleibt stehen, wie sie war; die
Korrektur steht hier und in ADR 0023.

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

### 6. Die Rangreihenfolge überlebt die Datenbank

`research_citations` bekommt eine `position`-Spalte und die Relationship ein
`order_by` (Muster `technical_zones`). Ohne beides wäre die Sortierung nach dem
ersten Neuladen verloren — eine Relationship ohne `order_by` überlässt die
Reihenfolge der Datenbank, und eine Reihenfolge, die nur im Arbeitsspeicher
gilt, ist keine.

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
