# Audit #3 — Ganzheitliche Systemprüfung: Fachliche Korrektheit, stille Fehler und Produktionsbetrieb

## 1. Metadaten und untersuchter Repository-Stand

| Feld | Wert |
|---|---|
| Datum der Durchführung | 2026-09-20 |
| Untersuchter Branch | `dev` |
| Commit | `3540adc` (Merge PR #92, `feature/tageslauf-tempo`) |
| Working Tree | sauber |
| Modell | Claude Opus 5 (1M Kontext) |
| Vorgänger | [Audit 1](2026-08-23-repository-audit.md) (`f61f316`), [Audit 2](2026-08-31-repository-audit-2.md) (`1f65472`) |
| Nachverfolgung | [2026-09-20-nachverfolgung.md](2026-09-20-nachverfolgung.md) |

### Ausgeführte Prüfungen

| Prüfung | Ergebnis |
|---|---|
| `pytest tests/unit tests/golden tests/architecture` | **2.282 Tests grün**, 3 übersprungen |
| `pytest tests/integration` (PostgreSQL 16 im Container) | **203 Tests grün** |
| `ruff check .` | All checks passed |
| `mypy --strict src tests` | Success: no issues found in 281 source files |
| `npm run lint` / `npm run typecheck` (Frontend) | sauber |
| `npm test` (Frontend, vitest) | **142 Tests grün** in 25 Dateien |

**2.485 Backend-Tests und 142 Frontend-Tests laufen grün.** Kein Befund dieses
Audits beruht auf einem roten Test — sie beruhen auf Lücken zwischen dem,
was geprüft wird, und dem, was gelten soll.

### Einschränkungen dieses Audits

> **Nicht verifizierbar anhand des Repository-Zustands:**

1. **Der Zustand des Windows-Servers.** Welche Aufgaben in der
   Aufgabenplanung tatsächlich eingetragen sind, ob Sicherungen existieren,
   welcher Argumentstring geschaltet ist, ob `D:\` ein eigenes Laufwerk ist.
   Grundlage ist hier ausschließlich die Angabe des Projektinhabers
   (**genau eine** geplante Aufgabe) und Doc 14.
2. **Der Inhalt der Produktivdatenbank.** Zeilenzahlen, tatsächliche
   Historientiefe je Symbol, ob seit dem Tiefen-Backfill ein Split
   stattgefunden hat.
3. **Laufende Kennzahlen.** Trefferquoten, Drawdowns und Verteilungen der
   Backtests liegen ausschließlich auf dem Server. Abschnitt 12 bewertet
   deshalb das **Verfahren**, nicht seine Ergebnisse.
4. **Das Verhalten externer Anbieter.** IBKR, Finnhub, EDGAR, Anthropic,
   Telegram und Cloudflare sind nur über eingefrorene Antworten
   (Contract-Tests) und über die dokumentierten Messungen geprüft.
5. **Das laufende Dashboard.** Bewertet ist der Quelltext und der
   Exportpfad, nicht eine laufende Instanz.

---

## 2. Executive Summary

Dieses System ist **überdurchschnittlich sorgfältig gebaut**. Die Regel
„fehlende Werte bleiben fehlend" ist nicht behauptet, sondern durchgesetzt:
Indikatoren liefern `None` statt `0.0`, Signalfunktionen werfen
`DataIncompleteError` statt `False`, Scores rechnen um statt zu nullen, und
an drei getrennten Stellen im Code steht ausformuliert, warum ein
Ersatzwert schlimmer wäre als eine Lücke. Der Advisory Lock des Dispatchers
überlebt einen harten Prozessabbruch. Die Geheimnisschwärzung sitzt an der
Log-Senke statt an einzelnen Fehlermeldungen. Die Kerzenaggregation
unterscheidet drei Arten unvollständiger Fenster, statt sie stillschweigend
wegzulassen. Das ist kein übliches Niveau.

**Die Befunde dieses Audits liegen deshalb fast ausnahmslos nicht im Code,
sondern an den Nahtstellen** — zwischen einer Regel und ihrer Wirkung,
zwischen einer gerechneten Kennzeichnung und dem Kanal, der sie nicht
transportiert, zwischen einem im ADR benannten Risiko und dem fehlenden
Mechanismus, der es bemerken würde.

### Die fünf wichtigsten Befunde

1. **Ein Aktiensplit zerreißt die Kursreihe unbemerkt** (AUDIT-003-001,
   Critical). Der Backfill holt nur, was fehlt, und ändert vorhandene Bars
   nie (`ON CONFLICT DO NOTHING`). IBKR liefert `TRADES` **zum
   Abrufzeitpunkt** split-bereinigt. Nach einem Split stehen damit zwei
   Preisniveaus in derselben Reihe. ADR 0028 benennt genau diesen Fall — und
   überlässt ihn der manuellen Entdeckung. Es gibt **keine** Prüfung, die ihn
   fände. Bei rund 190 Großunternehmen ist das kein hypothetischer Fall.
2. **Es läuft keine Datensicherung** (AUDIT-003-002, Critical). Die
   Skripte liegen versioniert im Repository, Doc 14 beschreibt den Eintrag,
   Maßnahme A2-M4 steht seit dem 2026-09-01 auf „teilweise — offen bleibt
   die Ausführung am Server". Betroffen sind unter anderem die
   `option_quotes`, von denen ADR 0058 ausdrücklich sagt, dass es sie **nie
   wieder geben wird**.
3. **Der Earnings-Filter schließt nichts aus** (AUDIT-003-003, High).
   `EARNINGS_EXCLUDED` wird gerechnet, gespeichert und gezählt — und wirkt
   danach auf nichts: nicht auf den Screening-Status, nicht auf die
   Empfehlungsstufe, nicht auf die Telegram-Meldung. Doc 10 §6.5 sagt „Ein
   Kandidat wird ausgeschlossen". Kein ADR löst diesen Satz ab. Die
   Meldung kennzeichnet einen **unbekannten** Termin, einen **bekannt
   nahen** nicht.
4. **Die Empfehlungsstufe ignoriert die Datenabdeckung** (AUDIT-003-004,
   High). Ein Swing-Score aus 60 % Abdeckung kann `STRONG_CANDIDATE`
   ergeben. Der Fall ist nicht konstruiert: Fällt der Technical Agent aus,
   entfallen zwei Komponenten (30 %) **und** zugleich die einzige
   wirksame Deckelung (`FalseSignalRisk.HIGH`) — beide hängen am selben
   Objekt.
5. **Liquiditätswarnungen erreichen die Meldung nicht** (AUDIT-003-005,
   High). Ein Put-Vorschlag mit Stufe `POOR` steht in Telegram
   zeichengleich neben einem mit `GOOD`. Die Zusage „steht nie an erster
   Stelle" steht dreimal im Repository und gilt nur, solange es einen
   besseren Vorschlag gibt.

### Gesamtbewertung

| Dimension | Bewertung |
|---|---|
| Fachliche Korrektheit der Rechnung | **sehr gut** — Indikatoren, Signale, Kerzenbildung, Episoden und Scores sind korrekt, dokumentiert und getestet |
| Umgang mit fehlenden Daten | **sehr gut** — durchgängig, kein einziger stiller Ersatzwert gefunden |
| Umgang mit **falschen** Daten | **schwach** — es gibt fast keine Plausibilitätsschranke auf Kursdaten (AUDIT-003-001) |
| Reproduzierbarkeit | **gut mit einer Lücke** — Versionen stehen an jedem Ergebnis, aber die Konfiguration wird von Hand versioniert (AUDIT-003-009) |
| Kontrollierte Degradation | **gut** — Fehlerisolation je Aktie und je Modul ist durchgängig |
| Stille Fehlentscheidungen | **drei gefunden** (001, 003, 004) |
| Architektonische Konsistenz | **sehr gut** — Schichtgrenzen per Test erzwungen, ADR-Disziplin vorbildlich |
| Beobachtbarkeit im Betrieb | **unzureichend** — kein Protokoll eingeschaltet, kein Wächter (AUDIT-003-013/014) |
| Sicherheit | **gut** — keine Geheimnisse in der Historie, Schwärzung an der Senke, CSP durchdacht |
| Betriebsreife | **lückenhaft** — ein einziger Scheduled Task deckt den Betrieb nicht ab (Abschnitt 22) |
| Wartbarkeit | **gut**, mit einem Ausreißer (`cli.py`, 5.055 Zeilen) |

---

## 3. Audit Scope

Geprüft wurden:

- **alle 69 ADRs** in `docs/adr/` samt `README.md`,
- **alle 10 Dateien** unter `docs/requirements/`,
- **Doc 01–14**, mit Schwerpunkt auf Doc 05, 07, 08, 09, 10, 13, 14,
- **beide bisherigen Audits** samt ihrer Nachverfolgungen,
- **37.244 Zeilen** Backend-Quelltext, Schwerpunkt Domain- und
  Application-Schicht,
- **40.318 Zeilen** Testcode in 99 Dateien,
- `config/default.yaml` (831 Zeilen) vollständig,
- Frontend (`src/lib`, `src/components`, `public/_headers`),
- `scripts/` (Sicherung, Zählprobe, Laufzeiten, PostgreSQL-Werkzeuge),
- `.github/workflows/`, `.gitignore`, `.env.example`, Git-Historie
  auf Geheimnisse.

Nicht Gegenstand: UI-Ästhetik, Formulierungsfragen, reine Stilkritik.

---

## 4. Repository / Documentation Review

### 4.1 Dokumentationslage

Die Dokumentation ist **die Stärke dieses Projekts und zugleich seine
Hauptquelle für Widersprüche** — weil sie so viel behauptet, lässt sich so
viel prüfen. Von 69 ADRs ist keiner inhaltlich falsch; drei tragen
Formulierungen, die vom Code überholt sind (AUDIT-003-018, -021).

Bemerkenswert: **ADR 0030 widerlegt ausdrücklich eine Aussage von Audit 1.**
Die Wochentagsnäherung wurde dort als „konservativ" bezeichnet;
`domain/earnings/calendar.py` stellt im Modul-Docstring richtig, dass die
Fehlerrichtung **riskant** ist — ein mitgezählter Feiertag lässt den Termin
weiter weg erscheinen und schließt seltener aus. Das ist gelebte
Audit-Kultur: Ein Befund wurde nicht übernommen, sondern nachgerechnet und
korrigiert.

### 4.2 Requirement- und ADR-Traceability

| Requirement / ADR | Erwartetes Verhalten | Tatsächliche Implementierung | Status | Abweichung / Risiko |
|---|---|---|---|---|
| Doc 10 §6.2 Orchestrator | Reihenfolge steuern, keine Fachrechnung | `RunAnalysisUseCase`, drei Phasen + 1b | **erfüllt** | — |
| Doc 10 §6.3 Screener | Nur abgeschlossene Kerzen, Warm-up 250 | `aggregate_intraday_bars`, `evaluate_candidate` | **erfüllt** | — |
| Doc 10 §6.5 Earnings-Filter | **Kandidat wird ausgeschlossen** | Status wird gerechnet und gespeichert; schließt nur die Recherche aus | **nicht erfüllt** | **AUDIT-003-003** |
| Doc 10 §6.6 Look-ahead-Verbot | Keine Zukunftsdaten im Backtest | Replay über `evaluate_candidate`, nur `t` und `t−5…t` | **erfüllt** | — |
| Doc 10 §6.8 Zonen | Nachvollziehbar, deterministisch | `domain/technical/zones.py`, drei Schritte | **erfüllt** | — |
| Doc 10 §6.9 Fundamentaldaten | Keine Kennzahl aus zwei Zeiträumen | `domain/fundamentals/metrics.py`, Stichtagsbindung erzwungen | **erfüllt** | Vergleichsgruppe fehlt (bewusst, ADR 0032) |
| Doc 10 §6.10 Optionen | Unzureichende Liquidität nicht verschweigen | Warnungen am Vorschlag, **nicht** in der Meldung | **teilweise erfüllt** | **AUDIT-003-005** |
| Doc 10 §6.11 Scores | Keine Scheingenauigkeit, Begründung deckungsgleich | `aggregate()`, eine Nachkommastelle, Faktoren gerechnet | **erfüllt** | — |
| Doc 10 §6.12 Bericht | Mindestinhalt, Lücken gekennzeichnet | `domain/report/builder.py` | **erfüllt** | — |
| Doc 10 §12 Nachvollziehbarkeit | Jede Empfehlung belegt ihre Herleitung | `RecommendationResult.reasons`, gerechnet | **erfüllt** | Abdeckung fehlt als Faktor (**AUDIT-003-004**) |
| Doc 10 §14 Deployment | Nativer Windows-Betrieb, ein Auslöser | ADR 0036, Doc 14 | **erfüllt** | — |
| Doc 10 §15 Backup | 5 Mindestanforderungen | Skripte vorhanden, **nicht eingerichtet** | **nicht erfüllt** | **AUDIT-003-002/-006** |
| Doc 10 §16 Testarchitektur | Unit, Integration, Contract, Golden, E2E | alle fünf vorhanden | **erfüllt** | Golden deckt Scoring/Optionen nicht (**AUDIT-003-009**) |
| Doc 05 Unveränderlichkeit | Abgeschlossene Analysen nie überschreiben | append-only, `ON CONFLICT DO NOTHING` | **erfüllt** | genau dieser Mechanismus verhindert die Split-Heilung (**AUDIT-003-001**) |
| Doc 07 / ADR 0057 Episoden | Geteilte Grundlage statt Cooldown | `group_into_episodes` | **erfüllt** | — |
| ADR 0019 Dispatcher | Idempotent, ein Lauf je Handelstag | `dispatcher_runs` + Advisory Lock | **erfüllt** | — |
| ADR 0021 KI-Anbindung | Code hängt an keinem Modell | `llm.*`-Profile, Version am Ergebnis | **erfüllt** | `llm.fundamental`/`llm.report` tot (**AUDIT-003-017**) |
| ADR 0026 Technical Agent | Nur Einordnung, keine eigene Ableitung | Werkzeugschema `strict`, `temperature=0` | **erfüllt** | — |
| ADR 0028 Historientiefe | 5 Jahre im Bestand | Tiefen-Backfill gelaufen | **nicht verifizierbar** (Server) | Splitrisiko benannt, **kein Mechanismus** |
| ADR 0032 Fundamentalanalyse | Deterministisch, kein LLM | EDGAR direkt, `compute_fundamental_snapshot` | **erfüllt** | — |
| ADR 0042 Kein hist. Earnings-Filter | Abweichung am Ergebnis gekennzeichnet | `earnings_exclusion_applied` + Bericht | **erfüllt** | Gegenstück für die Wiederholsperre fehlt (**AUDIT-003-011**) |
| ADR 0044 Schwärzung an der Senke | Jede Zeile geschwärzt | `redact_registered` im Formatter | **erfüllt** | — |
| ADR 0048 Optionsanalyse | Prämie = Mid, Liquidität warnt | umgesetzt | **erfüllt** | Zusage „nie an erster Stelle" trägt nicht (**AUDIT-003-005**) |
| ADR 0053 Lese-API | Kein Lauf über HTTP | `build_app` baut keinen Anbieter | **erfüllt** | `/docs` offen (**AUDIT-003-016**) |
| ADR 0054 Wiederholsperre | 7 Tage je vollanalysiertem Symbol | `_ohne_kuerzlich_analysierte` | **erfüllt** | verstärkt 429-Folgen (**AUDIT-003-008**) |
| ADR 0058 Optionsrückblick | Rohnotierungen speichern | `option_quotes` | **teilweise erfüllt** | ohne Zeitstempel/Modus (**AUDIT-003-010**) |
| ADR 0060 Dashboard extern | Zero-Knowledge, ausgehend | `publishing/`, CSP, Access | **erfüllt** | — |
| ADR 0068 Exportzeit | Abgeschlossene Läufe nicht neu rechnen | gebaut, in `dev` | **nicht ausgerollt** | **AUDIT-003-023** |

### 4.3 Nicht dokumentierte Architekturentscheidungen

Gesucht, **keine wesentliche gefunden**. Jede im Code angetroffene
Festlegung ließ sich auf einen ADR, eine Requirements-Datei oder einen
ausformulierten Modul-Docstring zurückführen. Zwei Grenzfälle:

- `MAX_CROSSING_SIGNAL_AGE_CANDLES = 1` und `RSI_OVERSOLD_LEVEL = 30.0`
  stehen im Code statt in der Konfiguration — mit ausdrücklicher Begründung
  (Regelsemantik hängt an `SIGNAL_RULE_VERSION`). Das ist eine Entscheidung
  und sie ist dokumentiert, wenn auch nur am Ort.
- `_SYMBOLE_VOR_DEM_DATENGATE = 5` ist eine Abwägung ohne ADR, aber mit
  ausformulierter Begründung im Docstring. Vertretbar.

---

## 5. Findings

Zwanzig Befunde. Zwei Critical, vier High, acht Medium, vier Low, zwei
Informational.

### Critical

#### AUDIT-003-001

**Severity:** Critical
**Kategorie:** Data Integrity / Silent Failure
**Komponente:** Marktdatenbeschaffung, Kerzenbestand
**Dateien:** `backend/src/ai_trading_analyst/application/backfill_history.py`,
`backend/src/ai_trading_analyst/infrastructure/persistence/repositories.py:1502`,
`backend/src/ai_trading_analyst/infrastructure/ibkr/bar_source.py:664`

**Problem**

Führt ein Titel der Watchliste einen Aktiensplit durch, entsteht in seiner
gespeicherten Kursreihe ein Sprung, der wie eine reale Kursbewegung aussieht
und keiner ist. Es gibt keinen Mechanismus, der ihn erkennt, meldet oder
heilt.

**Technische Ursache**

Drei für sich richtige Entscheidungen greifen ungünstig ineinander:

1. IBKR liefert `whatToShow="TRADES"` **zum Abrufzeitpunkt split-bereinigt**
   (`bar_source.py:664`). Dieselbe historische Kerze hat vor und nach einem
   Split verschiedene Werte.
2. Der Backfill holt **nur, was fehlt** — er fragt den Bestand nach dem
   jüngsten Bar und fordert ab dort an (`backfill_history.py`, Modul-Docstring).
3. Die Ablage ist idempotent über `(symbol, start)` und lässt vorhandene
   Bars **unverändert**: `.on_conflict_do_nothing(index_elements=["symbol",
   "start"])` (`repositories.py:1502`).

Die Historie bleibt damit auf dem Preisniveau **vor** dem Split, die ab dem
Splittag nachgeführten Bars stehen auf dem Niveau **danach**. Bei einem
4:1-Split liegt zwischen der letzten alten und der ersten neuen Kerze ein
Sprung von −75 %.

ADR 0028 beschreibt exakt diesen Fall und schließt: *„Sollte ein Split einen
bereits geholten Zeitraum betreffen, sind die Bars der Aktie zu löschen und
neu zu holen — ein Fall für ein eigenes ADR, sobald er eintritt."* Die
Entdeckung bleibt damit dem Menschen überlassen. Eine Suche über den
gesamten Quelltext nach Plausibilitäts-, Sprung- oder Ausreißerprüfungen auf
Bars ergibt **keinen Treffer**; Plausibilitätsschranken existieren
ausschließlich für Finnhub-Antworten (`finnhub/recommendations.py`).

**Auswirkung**

Betroffen ist **jede** Rechnung, die auf der Kerzenreihe steht:

| Betroffen | Wirkung |
|---|---|
| EMA5/EMA20 | Der EMA5 folgt dem neuen Niveau schneller als der EMA20 → nach einem Split zwangsläufig ein Abwärtskreuz, danach eines nach oben. **Ein künstliches Signal C.** |
| RSI(14) | Ein einzelner −75-%-Schritt drückt den RSI für ~14 Kerzen in den Bereich unter 30 → **künstliches Signal D**. |
| Signal B | Der Schlusskurs kreuzt den EMA20 zwangsläufig von oben, später von unten → **künstliches Signal B**. |
| Kandidatenregel | Die Kombination aus B, C und D ist genau die Qualifikationsschwelle. **Ein Split erzeugt einen Kandidaten.** |
| Backtest | Jede Episode, deren Horizont über den Splittag reicht, misst eine Rendite von −75 % oder +300 %. Die Trefferquote der betroffenen Kombination wird unbrauchbar — und geht mit 25 % Gewicht in den Swing-Score. |
| Zonen | Unterstützungszonen aus der Vor-Split-Historie liegen um den Splitfaktor daneben; der `distance_to_support_pct` jedes Put-Vorschlags ist falsch. |
| Fundamentalbewertung | KGV und Marktkapitalisierung stehen auf dem Schlusskurs der letzten Kerze — der ist korrekt. **Nicht betroffen.** |
| Optionsanalyse | Das Strike-Band steht ebenfalls auf dem aktuellen Kurs. **Nicht betroffen.** |

Die Kerzenaggregation kann den Fall nicht fangen: Sie prüft
Vollständigkeit und Raster, nicht Größenordnung. Der Golden Master kann ihn
nicht fangen: Er rechnet über eingefrorene Bars, in denen kein Split
vorkommt. `_require_expected_candle` kann ihn nicht fangen: Es prüft das
**Alter** der jüngsten Kerze, nicht ihren Wert.

**Beispiel**

NVDA vollzog 2024 einen 10:1-Split. Angenommen, ein Titel der Watchliste
täte dasselbe am 2026-10-05:

- Bestand bis 2026-10-02: Kurse um 1.200 USD (Tiefen-Backfill vom 2026-08-24).
- Backfill am 2026-10-05: IBKR liefert ab dem jüngsten gespeicherten Bar,
  alle neuen Bars um 120 USD.
- `_require_expected_candle` ist zufrieden — die jüngste Kerze ist die
  erwartete.
- `evaluate_candidate` sieht im Sechs-Kerzen-Fenster einen Absturz um 90 %,
  einen RSI unter 10 und anschließend, sobald sich der EMA5 auf das neue
  Niveau gesetzt hat, ein EMA5/EMA20-Aufwärtskreuz.
- Der Titel wird **Kandidat**, durchläuft die volle Analyse, bekommt einen
  Put-Vorschlag auf Basis des korrekten neuen Kurses, aber mit einem
  `distance_to_support_pct`, der sich auf Zonen um 1.100 USD bezieht.
- Die Telegram-Meldung nennt ihn mit Score und Put-Zeile.
- Die Wiederholsperre (ADR 0054) friert diesen Zustand für **sieben Tage** ein.
- Der Backtest dieses Titels bleibt **dauerhaft** unbrauchbar, bis jemand
  seine Bars löscht und neu holt.

**Warum das relevant ist**

Die Watchliste umfasst rund 190 Großunternehmen. In diesem Segment sind
Splits regelmäßig — allein 2024 splitteten NVDA, WMT, CMG, BRO und SMCI.
Zwei bis fünf Fälle pro Jahr in einer Liste dieser Größe sind eine
realistische Erwartung, nicht ein Randfall. Es ist zudem der **einzige** im
System gefundene Fall, in dem falsche Eingangsdaten zu einem plausibel
aussehenden Kandidaten führen, ohne dass irgendetwas warnt — also genau das
Fehlerbild, dem dieses Audit die höchste Priorität geben soll.

**Empfehlung**

Drei Stufen, aufsteigend nach Aufwand; die erste allein schließt den
stillen Teil des Befundes:

1. **Sprungprüfung im Backfill** (S, ~4 h). Beim Ablegen neuer Bars den
   ersten neuen gegen den letzten gespeicherten prüfen. Überschreitet das
   Verhältnis eine Schwelle (etwa Faktor 1,5 oder 0,67 über eine
   Kerzengrenze hinweg), gilt die Aktie als **verdächtig**: Sie wird
   protokolliert, gemeldet und für den Lauf als `StaleDataError`-artiger
   Einzelfehler behandelt — der Lauf läuft weiter, dieser Titel fällt
   heraus. Ein Faktor, der einem üblichen Splitverhältnis entspricht
   (2, 3, 4, 5, 10, 20 oder deren Kehrwerte), wird zusätzlich als
   **mutmaßlicher Split** benannt. Das ist keine Korrektur, nur eine
   ehrliche Weigerung — und genau die fehlt heute.
2. **Heilung als Kommando** (S, ~3 h). `cli refetch-bars --symbols X`
   löscht die Bars eines Titels und holt sie vollständig neu. Der
   Handgriff aus ADR 0028 existiert heute nur als Satz, nicht als Werkzeug.
3. **Regelmäßige Bestandsprüfung** (M, ~4 h). Ein monatliches, rein
   lesendes Kommando, das jede Kerzenreihe auf Sprünge absucht — es fängt
   auch die Fälle, die zwischen zwei Läufen entstanden sind.

Ein ADR gehört dazu: Die Sprungschwelle ist eine fachliche Festlegung, und
ADR 0028 hat den Fall ausdrücklich an ein eigenes ADR verwiesen.

**Status früherer Audits**

- Audit #1: nicht vorhanden (der Tiefen-Backfill existierte noch nicht)
- Audit #2: nicht vorhanden; ADR 0028 benennt das Risiko, beide Audits
  greifen es nicht auf

**Aufwand:** Medium (Stufe 1 allein: Small)

---

#### AUDIT-003-002

**Severity:** Critical
**Kategorie:** Data Loss / Betrieb
**Komponente:** Windows-Aufgabenplanung, Datensicherung
**Dateien:** `scripts/sicherung.ps1`, `scripts/sicherung-probe.ps1`,
`docs/14 - Inbetriebnahme und Betrieb.md` (Abschnitt „Sicherung"),
`docs/audits/2026-08-31-nachverfolgung.md:91`

**Problem**

Auf dem Windows-Server läuft nach Angabe des Projektinhabers **genau eine**
geplante Aufgabe: der Tageslauf. Es existiert damit keine automatische
Sicherung der Produktivdatenbank. Alles, was das System seit dem
2026-09-01 erarbeitet hat, hängt an einer einzelnen Festplatte.

**Technische Ursache**

Kein Programmfehler — ein nicht ausgeführter Einrichtungsschritt. Die
Nachverfolgung zu Audit 2 führt ihn seit dem 2026-09-01 als **A2-M4,
Status „teilweise"**: *„Offen bleibt allein die Ausführung am Server:
erster Lauf, Aufgabe eintragen, einmal die Zählprobe durchspielen."*

Bemerkenswert ist, wie vollständig das Gegenteil vorbereitet ist:
`sicherung.ps1` prüft den Dump mit `pg_restore --list` auf Lesbarkeit statt
nur auf Existenz, räumt alte Stände **erst nach** erfolgreicher Sicherung
weg, nimmt das Passwort aus `pgpass.conf` statt aus den Task-Argumenten und
meldet einen Fehlschlag bewusst mit Rückgabewert 2 statt 1. Doc 14 nennt
Trigger, Programm, Argumente und Abnahmekriterium. Es fehlt ausschließlich
der Eintrag.

**Auswirkung**

| Datenbestand | Nach Plattenausfall |
|---|---|
| `option_quotes` | **endgültig verloren.** ADR 0058, Festlegung 1: *„rund 400 echte Notierungen je Handelstag, die es nie wieder geben wird"* — historische Optionsnotierungen sind nicht rückwirkend abrufbar |
| `analysis_runs`, `screening_results`, `stock_reports`, `signal_events`, `technical_zones` | **endgültig verloren** — unveränderliche Momentaufnahmen mit Versionsstempel |
| `fundamental_metrics`, `research_citations` | verloren; aus EDGAR neu beschaffbar, aber nicht als Momentaufnahme |
| `intraday_bars` (5 Jahre, ~6,3 Mio. Zeilen) | neu beschaffbar — über einen **elfstündigen Wochenendlauf** (ADR 0028) |
| `dispatcher_runs` | verloren |
| `.env` | verloren, sofern nicht im Passwortmanager |

Die Kalibrierungsgrundlage aus ADR 0058 (Festlegungen 2 und 3 — gemessener
Volatilitätsaufschlag und Skew-Steigung statt gesetzter Werte) wächst
täglich und ist der einzige Weg, die Modellzahlen des Optionsbacktests
durch gemessene zu ersetzen. Sie ist zugleich der Bestand, der sich am
wenigsten ersetzen lässt.

**Beispiel**

Ein Ransomware-Befall oder ein Plattendefekt am 2026-11-01 kostet zwei
Monate produktiven Betrieb: rund 40 Analyseläufe, alle Berichte, alle
Scores — und etwa 16.000 Optionsnotierungen aus 40 Handelstagen, die sich
durch nichts rekonstruieren lassen. Der Quelltext überlebt auf GitHub, die
Kurshistorie ließe sich über ein Wochenende zurückholen. Der Rest nicht.

**Warum das relevant ist**

Doc 10 §15 nennt „automatisiertes tägliches Datenbank-Backup" als erste von
fünf Mindestanforderungen und setzt als Ziel „maximal ein Handelstag
Datenverlust". Der heutige Zustand erfüllt weder das eine noch das andere.
Es ist der einzige Befund dieses Audits, bei dem ein **einzelnes Ereignis**
den gesamten bisherigen Ertrag des Systems vernichtet.

**Empfehlung**

Den in Doc 14 beschriebenen Task eintragen — mit einer Korrektur:

| Feld | Wert |
|---|---|
| Name | `AI Trading Analyst — Sicherung` |
| Trigger | täglich **23:45** (Doc 14 nennt 22:00 — siehe unten) |
| Programm | `powershell.exe` |
| Argumente | `-NoProfile -File C:\...\scripts\sicherung.ps1 -Ziel D:\backups\ata` |
| Einstellungen | „Unabhängig von der Benutzeranmeldung ausführen", Zeitlimit 1 h |

**Die Uhrzeit aus Doc 14 passt nicht mehr.** Sie war richtig, als ein Lauf
53 Minuten dauerte; seit dem Dashboard-Export dauert er **103 Minuten**
(Doc 14, Abschnitt „Betriebszustand"). Ein um 21:30 gestarteter Lauf rechnet
bis 23:13. Ein `pg_dump` um 22:00 bliebe zwar konsistent — PostgreSQL
arbeitet auf einem MVCC-Schnappschuss, ein zerrissener Zustand entsteht
nicht —, enthielte den Tag aber möglicherweise nicht. 23:45 darf zurück auf
23:00, sobald ADR 0068 auf dem Server ist.

Danach die Zählprobe einmal durchspielen und A2-M4 schließen.

**Status früherer Audits**

- Audit #1: nicht vorhanden
- Audit #2: **vorhanden als A2-M4, Status „teilweise", seit dem 2026-09-01
  unverändert offen**

**Aufwand:** Small (~30 min, keine Implementierung — die Skripte existieren)

---

### High

#### AUDIT-003-003

**Severity:** High
**Kategorie:** Fachliche Korrektheit / False Confidence
**Komponente:** Earnings-Filter, Empfehlung, Benachrichtigung
**Dateien:** `backend/src/ai_trading_analyst/application/run_analysis.py:604`,
`backend/src/ai_trading_analyst/domain/scoring/recommendation.py:137`,
`backend/src/ai_trading_analyst/domain/report/notification.py:143`,
`backend/src/ai_trading_analyst/domain/report/builder.py:137`

**Problem**

Der Status `EARNINGS_EXCLUDED` wird korrekt berechnet, gespeichert und in
der Laufansicht gezählt — und schließt danach nichts aus. Ein Titel, dessen
Quartalszahlen in wenigen Tagen anstehen, erscheint als empfohlener
Kandidat in der Telegram-Meldung, **ohne jeden Hinweis auf den Termin**.

**Technische Ursache**

Eine Suche nach `EARNINGS_EXCLUDED` über den gesamten Quelltext liefert vier
Treffer: die Enum-Definition, zwei Docstrings und **eine** Verwendung — das
Hochzählen für die Laufübersicht (`read_run_overview.py:102`). Der Status
wirkt an keiner Entscheidungsstelle:

- `_prepare_stock` setzt `needs_research = earnings.status ==
  EARNINGS_CLEAR`. **Nur die Recherche ist gesperrt** — und die steht
  produktiv auf `none` (ADR 0051). In der geschalteten Konfiguration hat der
  Filter damit **keinerlei Wirkung** auf die Ausgabe.
- Der Screening-Status bleibt `CANDIDATE`.
- `_run_agents_concurrently` ruft die KI-Einordnung ausdrücklich auch bei
  nahem Termin auf (Kommentar Zeile 686–689).
- `_gedeckelt` in `recommendation.py` kennt zwei Deckelungen:
  `FalseSignalRisk.HIGH` und `EarningsFilterStatus.UNKNOWN`.
  `EARNINGS_EXCLUDED` ist **nicht darunter**.
- `_kandidatenblock` in `notification.py` hängt den Zusatz
  „— Earnings-Termin unbekannt" an, wenn der Status `UNKNOWN` ist. Für
  `EARNINGS_EXCLUDED` **keine Zeile**.
- `_pruefe_earnings` in `builder.py` erzeugt einen Datenrisiko-Vermerk —
  ebenfalls nur für `UNKNOWN`.

Damit gilt: **Ein unbekannter Termin wird an drei Stellen gekennzeichnet,
ein bekannt naher an keiner.**

**Auswirkung**

Doc 10 §6.5 ist eindeutig: *„Der Earnings Filter verhindert eine vertiefte
Analyse, wenn Quartalszahlen innerhalb des definierten Ausschlussfensters
bevorstehen"* und *„Ein Kandidat wird ausgeschlossen, wenn der nächste
Earnings-Termin innerhalb des konfigurierten Fensters von 10 bis 20
zukünftigen 195-Minuten-Kerzen liegt."* Doc 10 Zeile 535 präzisiert: *„Die
Research Pipeline wird nur für Kandidaten gestartet, die Screener und
Earnings-Filter bestanden haben."* — dieser eine Satz **ist** umgesetzt,
der allgemeine Ausschluss nicht.

Kein ADR löst §6.5 ab. ADR 0020 und ADR 0030 betreffen den Status und den
Kalender, nicht die Wirkung. ADR 0048 nutzt den Termin für die Wahl des
Verfallstermins — das ist eine zusätzliche Verwendung, kein Ersatz.

Ein Teil des Risikos ist konstruktiv abgefangen: Weil
`min_days_to_expiration` bei 21 Kalendertagen liegt und das
Ausschlussfenster 20 Kerzen (≈ 10 Handelstage ≈ 14 Kalendertage) umfasst,
findet `select_expiration` für einen ausgeschlossenen Titel in aller Regel
**keinen** zulässigen Verfall — es entsteht kein Put-Vorschlag. Der
Aktienkandidat selbst bleibt aber bestehen.

**Beispiel**

Ein Titel meldet am Dienstag Quartalszahlen. Am Vorabend qualifiziert er
sich mit vier von fünf Signalen.

- Der Earnings-Filter rechnet 4 Handelstage × 2 Kerzen = 8 Kerzen bis zum
  Termin, das ist ≤ 20 → `EARNINGS_EXCLUDED`.
- Die volle Analyse läuft: Chartauswertung, Backtest, EDGAR,
  Analystenvoten, KI-Einordnung, Optionskette.
- Der Swing-Score liegt bei 8,4 → `STRONG_CANDIDATE`. Der Investment-Score
  korrigiert nicht, das Fehlsignalrisiko ist `medium` → keine Deckelung.
- Telegram meldet:
  `SYMBOL -- STRONG_CANDIDATE -- 4/5 Signale -- Risiko medium` /
  `S 8.4 | I 6.1` / `Put-Verkauf: keine Optionsdaten`.
- Der Berichtstermin wird nirgends erwähnt. „Keine Optionsdaten" liest sich
  wie ein Abrufproblem, nicht wie das Ergebnis einer Risikoregel.

**Warum das relevant ist**

Das Earnings-Risiko ist für eine Put-Verkaufsstrategie **das** zentrale
Einzelereignisrisiko — deshalb steht es in Doc 10 als eigener Filter und
deshalb hält ADR 0048 den Verfall davor. Dass die Kennzeichnung ausgerechnet
im Kanal fehlt, der das eigene Netz verlässt, und dass ein *unbekannter*
Termin strenger behandelt wird als ein *bekannt naher*, ist eine Umkehrung
der Risikologik.

**Empfehlung**

Der Entscheid, **was** `EARNINGS_EXCLUDED` bewirken soll, gehört dem
Projektinhaber und in ein ADR. Drei Varianten:

| Variante | Wirkung | Bemerkung |
|---|---|---|
| **A — Kennzeichnen** | Deckel `cap_earnings_excluded` (Vorschlag: `WATCH`), Zusatz in der Meldung, Vermerk im Bericht | kleinster Eingriff, passt zum Muster von `cap_earnings_unknown`; **empfohlen** |
| **B — Ausschließen** | Status auf `NOT_CANDIDATE` mit Grund, keine Meldungszeile | wörtlich Doc 10 §6.5; verwirft die bereits bezahlte Analyse |
| **C — §6.5 ablösen** | ADR hält fest, dass der Filter nur die Recherche gattert | macht den Ist-Zustand zur Entscheidung; dann fehlt die Kennzeichnung trotzdem |

Variante A ist die kleinste Änderung mit der größten Wirkung: Sie hält die
Entkopplung der Analysemodule (CLAUDE.md) unangetastet, nutzt einen
vorhandenen Mechanismus und macht den Befund dort sichtbar, wo er
gebraucht wird. In jedem Fall gehört der Termin in den Meldungsblock —
symmetrisch zu `UNKNOWN`.

**Status früherer Audits**

- Audit #1: nicht vorhanden
- Audit #2: nicht vorhanden. Abschnitt 6.2 prüfte die Beschaffung des
  Termins und die Statuslogik, nicht die Wirkung des Status

**Aufwand:** Small (Variante A: Deckel + Meldungszeile + Bericht, ~4 h) zzgl. ADR

---

#### AUDIT-003-004

**Severity:** High
**Kategorie:** False Confidence / Scoring
**Komponente:** Empfehlungsableitung
**Dateien:** `backend/src/ai_trading_analyst/domain/scoring/recommendation.py:137`,
`backend/src/ai_trading_analyst/domain/scoring/aggregate.py:56`,
`config/default.yaml:611`

**Problem**

Die Empfehlungsstufe wird allein aus den Score-**Werten** abgeleitet. Ob
ein Score auf sechs von sechs oder auf drei von sechs Komponenten steht,
verändert die Stufe nicht. `STRONG_CANDIDATE` aus 60 % Datenabdeckung ist
möglich und von `STRONG_CANDIDATE` aus 100 % nicht zu unterscheiden.

**Technische Ursache**

`aggregate()` kennt die Abdeckung genau und bildet sie sauber ab: unterhalb
von `minimum_coverage` (0,6) entsteht `INSUFFICIENT_DATA`, zwischen 0,6 und
`normal_confidence_coverage` (0,8) trägt das Ergebnis
`ScoreConfidence.LOW_COVERAGE`. Die Umgewichtung skaliert die verbliebenen
Gewichte auf 100 %.

`derive_recommendation` liest `ScoreResult.value` und `ScoreResult.status` —
`confidence` und `coverage` **nicht**. Die Deckelungsliste in `_gedeckelt`
enthält zwei Einträge: `FalseSignalRisk.HIGH` und
`EarningsFilterStatus.UNKNOWN`.

Erschwerend: Die Deckelung `FalseSignalRisk.HIGH` und die Komponenten
`CHART_SETUP` (0,15) und `CHANCE_RISK` (0,15) stammen **alle drei aus
demselben Objekt** — dem `TechnicalAssessment` des Technical Agent. Fällt
der Anthropic-Aufruf aus, fällt gleichzeitig ein Drittel der
Score-Grundlage **und** die einzige Deckelung weg, die ein überhöhtes
Ergebnis noch senken würde. Die beiden Schutzmechanismen sind nicht
unabhängig.

Der Docstring von `_gedeckelt` begründet ausdrücklich, warum die
Stichproben-Konfidenz des Backtests **nicht** deckelt („bestrafte dieselbe
Tatsache zweimal"). Für die Datenabdeckung ist dieselbe Frage nirgends
beantwortet — sie wurde offenbar nicht gestellt.

**Auswirkung**

Rechenweg mit den geschalteten Gewichten (ADR 0041):

```
Ausfall des Technical Agent  → CHART_SETUP (0,15) + CHANCE_RISK (0,15) entfallen
Analystenvoten fehlen/zu alt → NEWS_AND_EVENTS (0,10) entfällt
                               verbleibendes Gewicht = 0,60 = minimum_coverage ✓

verbleibend, umgewichtet:  TECHNICAL_SIGNALS   0,25 → 0,4167
                           SIGNAL_STATISTICS   0,25 → 0,4167
                           OPTIONS_ATTRACT.    0,10 → 0,1667

Teilwerte 10 / 8 / 8  →  10·0,4167 + 8·0,4167 + 8·0,1667 = 8,8
8,8 ≥ recommendation.strong_candidate (8,0)  →  STRONG_CANDIDATE
false_signal_risk = None (kein Assessment)   →  keine Deckelung
```

Ein `STRONG_CANDIDATE` mit 8,8 Punkten, der ausschließlich aussagt: „fünf
von fünf Signalen haben gefeuert, die historische Trefferquote dieser
Kombination ist gut, und die Optionsprämie ist hoch". Über die Chartlage,
das Chance-Risiko-Verhältnis, das Fehlsignalrisiko und die Stimmungslage
weiß das System nichts — und sagt es nicht.

Die Information ist vorhanden: `ScoreResult.coverage` steht am Ergebnis und
im Bericht. Sie erreicht nur weder die Stufe noch die Meldung.

**Beispiel**

Anthropic hat eine Störung, Finnhub antwortet mit 429. Der Tageslauf
liefert vier Kandidaten, zwei davon als `STRONG_CANDIDATE`, jeweils ohne
Risikoangabe in der Meldung (die Zeile `Risiko …` entfällt, weil kein
Assessment vorliegt). Die Meldung sieht aus wie an jedem anderen Tag, nur
etwas knapper. Die Wiederholsperre friert beide Titel für sieben Tage ein.

**Warum das relevant ist**

Genau dieser Fall steht im Auditauftrag unter „False Confidence": *„ein
hoher Score trotz fehlender Daten"*. Das System hat die Kennzeichnung
gebaut (`LOW_COVERAGE`), führt sie mit — und lässt sie an der einzigen
Stelle fallen, an der aus einer Zahl eine Handlungsempfehlung wird.

**Empfehlung**

Zwei Änderungen, beide klein:

1. **Deckel `cap_low_coverage`** (Vorschlag: `CANDIDATE`) in
   `recommendation.py`, ausgelöst durch
   `swing.confidence is ScoreConfidence.LOW_COVERAGE`. Er reiht sich in den
   vorhandenen Mechanismus ein, erscheint in `reasons` und `applied_caps`
   und ist damit im Bericht belegt.
2. **Abdeckung in den Meldungsblock**, wenn sie unter
   `normal_confidence_coverage` liegt — etwa `S 8.8 | I -- | Abdeckung 60 %`.
   Eine Zahl, kein Freitext; ADR 0055 bleibt gewahrt.

Die Abgrenzung zur Backtest-Konfidenz trägt: Dort ist die Komponente
**einzeln** dünn und entfällt bereits; hier fehlt ein **Drittel des
Gesamtbildes** und nichts weist darauf hin. Das ist nicht dieselbe Tatsache
zweimal, sondern eine zweite.

Ein ADR gehört dazu — es ändert die Ableitung der Empfehlungsstufe
(ADR 0046) und hebt `recommendation.version`.

**Status früherer Audits**

- Audit #1: nicht vorhanden (Scoring existierte noch nicht)
- Audit #2: nicht vorhanden. Abschnitt 6.5 prüfte Gewichte und
  Umgewichtung, nicht die Folge für die Stufe

**Aufwand:** Small (~4 h) zzgl. ADR

---

#### AUDIT-003-005

**Severity:** High
**Kategorie:** False Confidence / Optionsanalyse
**Komponente:** Put-Auswahl, Benachrichtigung, Swing-Score
**Dateien:** `backend/src/ai_trading_analyst/domain/options/strategies.py:185`,
`backend/src/ai_trading_analyst/domain/report/notification.py:170`,
`backend/src/ai_trading_analyst/domain/scoring/swing.py:175`,
`config/default.yaml:577`

**Problem**

Ein Put-Vorschlag mit der Liquiditätsstufe `POOR` kann an erster Stelle
stehen, den Score-Teilwert `OPTIONS_ATTRACTIVENESS` bestimmen und
unverändert in die Telegram-Meldung wandern — **ohne dass die Meldung die
Warnungen nennt**. An drei Stellen des Repositorys steht die gegenteilige
Zusage.

**Technische Ursache**

Die Sortierung in `build_options_analysis`:

```python
strategien.sort(key=lambda s: (s.liquidity is LiquidityGrade.POOR,
                               -s.annualized_return, -s.strike))
```

`POOR` wandert nach hinten — **relativ**. Sind alle Vorschläge `POOR`, steht
ein `POOR` an Position 0. Die Liquidität ist ein Sortierkriterium, kein
Ausschlusskriterium; `_bewerte` verwirft nur bei fehlendem Delta, fehlendem
Mittelwert, Prämie ≤ 0, gekreuztem Markt oder abgelaufenem Kontrakt.

Daraus folgen drei Aussagen im Repository, die nicht allgemein gelten:

| Ort | Aussage | Gilt |
|---|---|---|
| `config/default.yaml:577` | „Ein Vorschlag mit zwei oder mehr Warnungen gilt als POOR und **steht nie an erster Stelle**" | nur bei vorhandener Alternative |
| `swing.py:175` (`_optionsattraktivitaet`) | „ein illiquider Vorschlag steht **ohnehin nie** an erster Stelle" | dieselbe Einschränkung |
| ADR 0048, Abschnitt 6 | „Doc 10 §6.10 verlangt genau das — unzureichende Liquidität wird nicht verschwiegen" | im Bericht ja, **in der Meldung nein** |

`_put_angabe` in `notification.py` rendert Strike, Verfall und Prämie.
`liquidity` und `liquidity_warnings` stehen am `PutStrategy`-Objekt und
werden **nicht** ausgegeben. Die Tilde vor der Prämie kennzeichnet die
Mid-Annahme — die Liquidität kennzeichnet nichts.

**Auswirkung**

Die Prämie ist per ADR 0048 der Mittelwert aus Geld- und Briefkurs, mit der
ausdrücklichen Begründung: *„Bei liquiden Optionen füllt ein Limit meist
nahe am Mid."* Bei einem Kontrakt mit einer Geld-Brief-Spanne von 40 %
gilt diese Begründung nicht mehr — der Verkäufer füllt näher am Geldkurs.
Die gemeldete annualisierte Rendite überschätzt das Erreichbare dann
erheblich, und derselbe Wert speist über `OPTIONS_ATTRACTIVENESS` mit 10 %
Gewicht den Swing-Score.

Betroffen sind gerade die Titel, bei denen es zählt: Große, liquide Werte
haben enge Spannen und gute Ketten; ein Vorschlag wird typischerweise dann
`POOR`, wenn die Kette dünn ist — und dann ist auch der Mid am wenigsten
belastbar.

**Beispiel**

Ein Titel mit ausschließlich Monatsverfällen und dünner Optionskette.
Alle drei Vorschläge tragen zwei Warnungen (Spanne 22 %, Open Interest 40).
Der erste hat eine annualisierte Rendite von 41 % — aus einem Mid, der
zwischen Geld 0,90 und Brief 1,40 liegt.

- Score-Teilwert: 41 % liegt über der gemessenen Fünftelgrenze von 32,44 %
  → **10 von 10** für die Optionsattraktivität.
- Telegram: `Put-Verkauf: Strike 182,50 $, Verfall 17.10.2026, Praemie ~115 $`.
- Tatsächlich erzielbar wären eher 90 $ — rund 32 % annualisiert statt 41 %,
  und das nur, wenn überhaupt jemand auf der anderen Seite steht.
- Nichts in der Meldung deutet darauf hin.

Der vollständige Bericht enthält die Warnungen. Er wird aber nicht
automatisch gelesen — die Meldung ist der Kanal, auf dem gehandelt wird.

**Warum das relevant ist**

Der Auditauftrag fragt ausdrücklich: *„Prüfe besonders kritisch, ob die
Bezeichnung ‚geeignet für Put-Verkauf' möglicherweise eine höhere Sicherheit
suggeriert, als die tatsächlichen Kriterien rechtfertigen."* Hier ist der
Fall: Die Kriterien sind gebaut, ausgewertet und gespeichert — und
verschwinden auf dem letzten Meter.

**Empfehlung**

Drei Punkte, absteigend nach Nutzen:

1. **Liquiditätsstufe in die Meldung.** Ein Wort je Put-Zeile, etwa
   `Put-Verkauf: Strike 182,50 $, Verfall 17.10.2026, Praemie ~115 $
   (Liquiditaet POOR)`. Bei `GOOD` kann sie entfallen. Kein Freitext,
   ADR 0055 bleibt gewahrt.
2. **Die drei Zusagen richtigstellen.** Der Satz „steht nie an erster
   Stelle" gehört zu „steht hinter jedem besseren Vorschlag". Eine Zusage,
   die nur meistens gilt, ist gefährlicher als keine.
3. **Entscheiden, ob `POOR` ausschließt** — Projektinhaber, ADR. Dafür
   spricht, dass ein nicht handelbarer Vorschlag kein Vorschlag ist;
   dagegen, dass ein sichtbarer Befund mehr wert ist als eine Lücke. Eine
   Zwischenlösung: `POOR` bleibt im Bericht, trägt aber keinen
   Score-Teilwert (`OPTIONS_ATTRACTIVENESS` entfällt mit benanntem Grund)
   und erscheint in der Meldung mit Warnung.

**Status früherer Audits**

- Audit #1: nicht vorhanden (Optionsanalyse existierte noch nicht)
- Audit #2: nicht vorhanden; A2-F001 betraf den fehlenden Merge, nicht die
  Auswahlregel

**Aufwand:** Small (Punkte 1 und 2: ~3 h); Punkt 3 zzgl. ADR

---

#### AUDIT-003-006

**Severity:** High
**Kategorie:** Disaster Recovery
**Komponente:** Sicherungsstrategie
**Dateien:** `docs/10 - System Architecture.md:1519` (§15),
`docs/14 - Inbetriebnahme und Betrieb.md` (Abschnitt „Sicherung")

**Problem**

Auch nach Umsetzung von AUDIT-003-002 läge die Sicherung auf demselben
Rechner, unter demselben Benutzerkonto wie die Produktivdatenbank. Gegen
den Ausfall oder die Kompromittierung des Servers schützt sie nicht.

**Technische Ursache**

Bewusste Einschränkung, nicht Versehen. Doc 14 hält sie fest: *„Die Ablage
liegt nicht außerhalb des primären Datenvolumes, wie Doc 10 §15 es als
Zielbild nennt. Sie schützt gegen Softwarefehler, Fehlbedienung und eine
kaputte Migration — nicht gegen den Ausfall der Platte selbst. Neu zu
bewerten nach stabilem Betrieb."*

Doc 10 §15 nennt „Sicherung außerhalb des primären Datenvolumes" als eine
von fünf Mindestanforderungen; sie ist die einzige, die offen ist.

Das Zielverzeichnis der Doc-14-Beispiele ist `D:\backups\ata`. Ob `D:` eine
eigene physische Platte ist, **ist aus dem Repository nicht feststellbar**;
Doc 14 spricht im Fließtext von „demselben Laufwerk". Selbst eine eigene
Platte teilte Rechner, Betriebssystem und Benutzerkonto — und damit den
Ransomware-Pfad.

**Auswirkung**

Der Beschluss vom 2026-09-01 erfolgte, als der produktive Betrieb gerade
begann und wenig zu verlieren war. Seither sind rund vierzehn Handelstage
mit Optionsnotierungen hinzugekommen (ADR 0058: ~400 je Tag), und die
Bedingung „nach stabilem Betrieb neu bewerten" ist erfüllt. Der Wert des
Bestands ist seit dem Beschluss deutlich gestiegen, die Schutzwirkung nicht.

**Beispiel**

Verschlüsselungstrojaner über eine beliebige Anwendung auf dem Server.
Er verschlüsselt, was das Benutzerkonto beschreiben darf — die
PostgreSQL-Datenverzeichnisse **und** `D:\backups\ata`. Der Zustand danach
ist derselbe wie ganz ohne Sicherung.

**Warum das relevant ist**

Der Auditauftrag verlangt ausdrücklich, ein Backup auf derselben
Festplatte bzw. demselben Server nicht als Disaster-Recovery-Strategie zu
werten. Das Projekt sieht das genauso — es hat den Punkt nur noch nicht
umgesetzt.

**Empfehlung**

Eine tägliche, **verschlüsselte** Kopie des jüngsten geprüften Dumps an
einen Ort außerhalb des Servers. Die Entscheidung über Ziel und Verfahren
gehört dem Projektinhaber und in ein ADR; drei Punkte sind dabei zu
beantworten:

| Frage | Bemerkung |
|---|---|
| Ziel | Netzlaufwerk/NAS, Cloudspeicher oder Wechselmedium. Ein Ziel, auf das der Server nur **schreiben**, nicht löschen darf, entwertet den Ransomware-Pfad — das ist der eigentliche Hebel, nicht die Entfernung |
| Verschlüsselung | Sobald der Dump den Server verlässt, ist sie Pflicht. Der Schlüssel gehört in den Passwortmanager, nicht neben die Kopie |
| Aufbewahrung | Extern länger als die 14 Tage lokal — ein spät bemerkter Fehler ist der Hauptfall, gegen den Versionierung hilft |

Als eigener Task, **nach** der Sicherung (Kette: Dump → Prüfung → Kopie →
Aufräumen). Wichtig ist die Reihenfolge: kopiert wird nur, was
`pg_restore --list` bereits als lesbar bestätigt hat.

**Status früherer Audits**

- Audit #1: nicht vorhanden
- Audit #2: als bewusste Einschränkung dokumentiert (Ergänzung zu A2-M4),
  nicht als Befund geführt

**Aufwand:** Medium (ADR + ~4 h)

---

### Medium

#### AUDIT-003-007

**Severity:** Medium
**Kategorie:** Resilienz / Observability
**Komponente:** Ergebnismeldung
**Datei:** `backend/src/ai_trading_analyst/application/run_analysis.py:445`

**Problem**

Scheitert die Zustellung der Ergebnismeldung, geht sie für diesen Tag
verloren. Es gibt keinen Wiederholversuch, keinen persistierten Vermerk und
— bei ausgeschalteter Protokolldatei — keine Spur.

**Technische Ursache**

```python
except NotifierError as error:
    _logger.error("Ergebnismeldung ging nicht raus: %s", error)
```

Die Isolation selbst ist richtig und durch ADR 0024 gedeckt: Der Kanal ist
eine Systemgrenze und darf den bereits abgeschlossenen Lauf nicht
nachträglich scheitern lassen. Danach wird der Lauf mit
`mark_succeeded` festgeschrieben; jeder weitere Start des Tages endet mit
„Bereits erledigt". Die Meldung ist damit endgültig weg.

**Der Kontrast fällt auf:** Für die Überfälligkeitsmeldung ist derselbe Fall
sorgfältig gelöst — `_notify` in `dispatch_daily_run.py` setzt bei
gescheiterter Zustellung **keinen** Vermerk, die Meldung gilt als offen und
wird beim nächsten Start erneut versucht. Der Docstring begründet das
ausdrücklich: *„Die Alternative erzeugte genau den stillen Ausfall, gegen den
dieser Kanal gebaut ist, eine Ebene höher."* Für die Ergebnismeldung gilt
dasselbe Argument — dort ist es nicht angewandt.

Verschärfend: `logging.file` steht ausgeliefert auf `null`
(AUDIT-003-013), und unter der Aufgabenplanung ist `stdout` flüchtig. Die
`_logger.error`-Zeile landet damit **nirgends**.

**Auswirkung**

Ein Telegram-Ausfall, ein 429 oder eine kurze Netzstörung im falschen
Moment: Der Lauf war erfolgreich, die Kandidaten stehen in der Datenbank,
das Dashboard bekommt sie — und der Nutzer erfährt nichts. Von außen ist
dieser Tag nicht von einem Tag ohne Kandidaten zu unterscheiden, denn
`notifications.send_when_no_candidates` steht auf `false`.

**Beispiel**

Telegram antwortet um 19:12 mit `429 Too Many Requests` (der Bot wurde
kurz zuvor anderweitig genutzt). Vier Kandidaten, zwei davon
`STRONG_CANDIDATE`, bleiben unerwähnt. Am Folgetag sind sie durch die
Wiederholsperre für sieben Tage stumm gestellt.

**Empfehlung**

Zwei Stufen:

1. **Vermerk statt Vergessen** (S, ~3 h). Eine gescheiterte Ergebnismeldung
   am Laufdatensatz vermerken (etwa `analysis_runs.notification_sent_at`
   bleibt leer) und beim nächsten Dispatcher-Start nachholen, sofern der
   Lauf desselben Handelstages gemeint ist — nach dem Muster, das
   `unresolved()`/`alert_sent` für die Überfälligkeitsmeldung bereits
   umsetzt. Das Zeitfenster gibt es: Der Auslöser startet bis 21:30 weiter.
2. **Ein Wiederholversuch im Adapter** (XS, ~1 h). Bei 429 und 5xx einmal
   nach wenigen Sekunden erneut senden. Deckt den häufigsten Fall, ohne
   Zustandshaltung.

Unabhängig davon: `logging.file` einschalten (AUDIT-003-013) — sonst bleibt
auch der Befund selbst unsichtbar.

**Status früherer Audits**

- Audit #1: nicht vorhanden
- Audit #2: nicht vorhanden; Abschnitt 6.6 prüfte Inhalt und Kürzung der
  Meldung, nicht den Fehlerfall der Zustellung

**Aufwand:** Small

---

#### AUDIT-003-008

**Severity:** Medium
**Kategorie:** Resilienz / Datenqualität
**Komponente:** Finnhub- und EDGAR-Adapter im Zusammenspiel mit der Wiederholsperre
**Dateien:** `backend/src/ai_trading_analyst/infrastructure/finnhub/provider.py:99`,
`backend/src/ai_trading_analyst/infrastructure/finnhub/recommendations.py:125`,
`backend/src/ai_trading_analyst/infrastructure/throttle.py`,
`backend/src/ai_trading_analyst/application/run_analysis.py:306`

**Problem**

Es gibt an keiner Stelle einen Wiederholversuch für vorübergehende
HTTP-Fehler. Ein einzelner `429` oder `503` kostet die betroffene Kennzahl
für den ganzen Lauf — und die Wiederholsperre friert dieses degradierte
Ergebnis anschließend für sieben Tage ein.

**Technische Ursache**

Beide Finnhub-Adapter rufen `response.raise_for_status()` und übersetzen
jede `HTTPError` in einen Provider-Fehler. Eine Suche nach `retry`,
`backoff` oder `tenacity` über den Quelltext liefert **keinen Treffer**.
Vorhanden ist ausschließlich die vorbeugende Drossel (`throttle.Drossel`),
eingeführt, nachdem ein Messlauf *„vier von 192 Symbolen an `429 Too Many
Requests` verlor"* (Modul-Docstring, ADR 0046).

Die Degradation selbst ist sauber: Earnings → `UNKNOWN` mit Grund
`provider_error`; Analystenvoten → Komponente entfällt mit benanntem Grund.
Kein erfundener Wert, keine stille Lücke.

**Die Verschärfung entsteht erst im Zusammenspiel** mit ADR 0054: Ein Titel,
der als `CANDIDATE` durchlief, wird für sieben Kalendertage von jeder
weiteren Analyse ausgeschlossen. Das gilt auch, wenn sein Ergebnis wegen
eines transienten Fehlers unvollständig war. Punkt 4 von ADR 0054 („Ein
unterdrücktes Wiederauftreten verlängert die Sperre nicht") hilft hier
nicht — der Anker ist die degradierte Analyse selbst.

**Auswirkung**

| Ausgefallen | Sofortige Folge | Folge über sieben Tage |
|---|---|---|
| Earnings (Finnhub) | `UNKNOWN`, Deckel auf `CANDIDATE` | Titel bleibt sieben Tage mit gedeckelter Stufe stehen |
| Analystenvoten (Finnhub) | `NEWS_AND_EVENTS` entfällt, Abdeckung 90 % | dito, mit dauerhaft niedrigerer Abdeckung |
| beide zugleich | Abdeckung 80 %, Deckel `CANDIDATE` | sieben Tage |
| EDGAR | Investment-Score `INSUFFICIENT_DATA`, keine Korrektur | sieben Tage ohne Investment-Sicht |

Die Fehlerrichtung ist konservativ — das System wird vorsichtiger, nicht
kühner. Der Verlust ist nicht Falschheit, sondern **Information**: Ein
ganzer Analysezyklus steht auf Daten, die nur wegen eines
Sekundenereignisses fehlen.

**Beispiel**

Finnhub antwortet beim 140. von 192 Symbolen mit `429`. Zwei Kandidaten
dieses Laufs haben keinen Earnings-Termin. Beide werden auf `CANDIDATE`
gedeckelt, obwohl einer von ihnen ein `STRONG_CANDIDATE` gewesen wäre. Beide
sind für sieben Tage gesperrt. Ein zweiter Aufruf 200 ms später hätte
geantwortet.

**Empfehlung**

1. **Wiederholversuch mit Backoff** (S, ~4 h) in beiden Finnhub-Adaptern und
   im EDGAR-Adapter: bei `429`, `500`, `502`, `503`, `504` zweimal erneut
   versuchen, mit wachsendem Abstand und Beachtung eines `Retry-After`.
   Nicht bei `4xx` außer `429` — ein `401` oder `404` wiederholt sich nicht
   weg, und ein stiller Dauerversuch verdeckte einen echten
   Konfigurationsfehler.
2. **Erwägen: keine Sperre für degradierte Analysen** (S, Entscheidung).
   Ein Titel, dessen Analyse mit `provider_error` unvollständig blieb,
   könnte von der Wiederholsperre ausgenommen werden. Das erfordert einen
   Nachtrag zu ADR 0054 und ist eine fachliche Frage — Kosten gegen
   Vollständigkeit.

**Status früherer Audits**

- Audit #1: nicht vorhanden
- Audit #2: die Drossel ist als Konsequenz aus ADR 0046 dokumentiert; die
  Wechselwirkung mit ADR 0054 entstand erst danach

**Aufwand:** Small

---

#### AUDIT-003-009

**Severity:** Medium
**Kategorie:** Reproduzierbarkeit
**Komponente:** Konfiguration, Scoring, Golden Master
**Dateien:** `config/default.yaml:601`, `backend/tests/golden/pipeline.py:16`

**Problem**

Die gemessenen Schwellen und Gewichte des Scorings stehen in
`config/default.yaml`; die zugehörige Version (`swing_version`,
`long_term_version`, `recommendation.version`) steht daneben und wird von
Hand gepflegt. **Kein Test und kein Mechanismus erzwingt, dass sie
zusammenpassen.** Eine geänderte Schwelle ohne Versionssprung macht zwei
Ergebnisse unvergleichbar, die dieselbe Version tragen.

**Technische Ursache**

Der Golden Master schließt die Konfiguration ausdrücklich aus — und das aus
gutem Grund (`pipeline.py`, Modul-Docstring): *„Die Parameter stammen
absichtlich nicht aus `config/default.yaml` … Eine Konfigurationsänderung
soll den Golden Master **nicht** brechen — sonst schlüge er bei jeder
Parameterprobe an und verlöre seinen Wert."*

Die Kette, die er einfriert, endet zudem beim Backtest:

```
native Bars → aggregate_intraday_bars → compute_indicator_values
            → evaluate_candidate → compute_backtest
```

**Scoring, Empfehlungsableitung und Optionsauswahl sind nicht Teil des
Golden Master.** Eine Änderung an `scoring.thresholds`,
`analyst_buy_share.boundaries`, `options_annualized_return.boundaries`,
`swing_weights` oder `recommendation` verändert damit jedes künftige
Ergebnis, ohne dass ein Test anschlägt.

Zugleich ist der Pflegeturnus (Doc 14, „Pflege", quartalsweise, nächster
Termin 2026-12-01) ausdrücklich darauf angelegt, **genau diese Zahlen zu
ändern** — nach dem Muster „messen, dann festlegen" (ADR 0045, ADR 0048).
Die ADRs sagen jeweils „die Modellversion steigt"; erzwungen wird es
nirgends.

**Auswirkung**

An jedem Ergebnis stehen vorbildlich viele Versionen: `signal_rule_version`,
`technical_analysis_version`, `technical_ai_model`,
`technical_ai_prompt_version`, `fundamentals_analysis_version`,
`analyst_analysis_version`, `swing_version`, `long_term_version`,
`options_analysis_version`, `report_schema_version`, `app_version`. Die
Versionskultur ist hervorragend — sie hat nur eine Lücke an der Stelle, an
der Zahlen turnusmäßig ersetzt werden sollen.

Folge: Ein Vergleich zweier Läufe über einen Quartalswechsel hinweg kann
stillschweigend Äpfel mit Birnen vergleichen. Die Dashboard-Ansichten, die
historische Läufe nebeneinanderstellen, zeigen die Differenz dann als
Marktveränderung.

**Beispiel**

Am Pflegetermin werden die `analyst_buy_share`-Grenzen aus einem neuen
Messlauf nachgezogen, `swing_version` bleibt bei `1.3`. Ein Titel mit 62 %
Kauf-Anteil bekommt vorher 6, nachher 8 Punkte. Im Dashboard steht der
Swing-Score desselben Titels in zwei Läufen bei 7,1 und 7,6 — beide unter
Version `1.3`, und nichts sagt, dass dazwischen die Skala verschoben wurde.

**Empfehlung**

Ein Test, der die scoring-relevanten Konfigurationswerte gegen eine
gespeicherte Prüfsumme je Version hält (S, ~3 h): Ändert sich ein Wert,
ohne dass die zugehörige Versionsnummer steigt, wird der Test rot und nennt
den Grund. Technisch derselbe Gedanke wie der Golden Master, nur auf die
Konfiguration statt auf die Rechnung angewandt — und ohne dessen Nachteil,
weil er bei einer Parameterprobe nur verlangt, die Version mitzuziehen.

Ergänzend erwägen: einen **zweiten** Golden-Master-Fall, der die
Score-Kette über eingefrorene Eingaben rechnet (M, ~6 h). Er würde auch
Verfahrensänderungen in `aggregate()`, `derive_recommendation` und
`build_options_analysis` fangen — heute die größte ungesicherte Fläche.

**Status früherer Audits**

- Audit #1: verwandt als **R8** („Preislisten veralten still")
- Audit #2: **A2-F006** („Gemessene Schwellen ohne Pflegeturnus") — der
  Turnus ist seither eingerichtet (A2-M6, Doc 14 „Pflege"), die
  **Versionskopplung** nicht

**Aufwand:** Small (Prüfsummentest); Medium (zweiter Golden Master)

---

#### AUDIT-003-010

**Severity:** Medium
**Kategorie:** Datenqualität / Stale Data
**Komponente:** Optionsnotierungen, Kalibrierungsgrundlage
**Dateien:** `backend/src/ai_trading_analyst/infrastructure/persistence/orm.py:505`,
`backend/src/ai_trading_analyst/infrastructure/ibkr/bar_source.py:317`,
`config/default.yaml:522`

**Problem**

Die gespeicherten Optionsnotierungen tragen weder einen eigenen Zeitstempel
noch den verwendeten Marktdatenmodus. Eine im „frozen"-Modus gelieferte
Notierung vom Vortag ist in der Datenbank von einer lebenden nicht zu
unterscheiden.

**Technische Ursache**

`OptionQuoteOrm` führt: `screening_result_id`, `position`, `expiration`,
`strike`, `bid`, `ask`, `delta`, `implied_volatility`, `open_interest`,
`volume`. Der Zeitbezug entsteht ausschließlich über
`screening_results.evaluated_at` — den Zeitpunkt der **Analyse**, nicht den
der Notierung.

`options.market_data_type` steht auf `2` („frozen"), mit ausdrücklicher
Begründung in der Konfiguration: *„‚frozen' verhält sich bei offener Börse
wie live und liefert bei geschlossener den letzten festgestellten Stand
statt nichts. Das kostet im Regelfall nichts und macht eine Einzelprobe am
Abend brauchbar."* Für den Tageslauf ist das unkritisch — er läuft zwischen
12:50 und 14:50 ET, also bei offenem Optionsmarkt.

`_als_quote` übernimmt `bid`, `ask` und die `modelGreeks`, ohne ein
Zeitfeld des Tickers mitzuführen.

**Auswirkung**

Der Tageslauf selbst ist durch sein Zeitfenster geschützt. Betroffen ist die
**Kalibrierungsgrundlage** aus ADR 0058, Festlegung 1 — und die ist der
Zweck dieser Tabelle. Festlegungen 2 und 3 sehen vor, aus diesen Zeilen den
Volatilitätsaufschlag und die Skew-Steigung **am eigenen Universum zu
messen** und damit die heute gesetzten Modellwerte zu ersetzen. ADR 0058
formuliert das Prinzip ausdrücklich: *„Der Anspruch wird gemessen, bevor er
erhoben wird."*

Eine Messreihe, in der einzelne Zeilen aus eingefrorenen Ständen stammen
und nicht als solche erkennbar sind, trägt diesen Anspruch nicht. Quellen
solcher Zeilen:

- manuelle Einzelproben am Abend (`cli options --provider ibkr --symbols X`)
  — Doc 14 nennt sie als regulären Handgriff, und sie schreiben in dieselbe
  Tabelle,
- ein Ausfall der Marktdatenberechtigung mitten im Lauf,
- ein künftiger Lauf mit verschobenem Zeitfenster.

**Beispiel**

Eine Einzelprobe um 20:30 Uhr deutscher Zeit (14:30 ET wäre noch offen —
20:30 ET ist es nicht) liefert den Schlussstand. Zwölf Zeilen landen mit
`evaluated_at = 20:30` in `option_quotes`. Sechs Monate später vergleicht
`options-calibrate` für jede gespeicherte Notierung die modellierte mit der
gestellten Prämie. Diese zwölf Zeilen verschieben das Ergebnis, ohne dass
sich ihre Herkunft feststellen lässt.

**Empfehlung**

Zwei Spalten an `option_quotes`, beide klein und beide vor der ersten
Kalibrierung nötig:

1. `market_data_type` (`int`) — welcher Modus galt beim Abruf.
2. `quoted_at` (`timestamptz | None`) — der Zeitstempel des Tickers, sofern
   `ib_async` ihn führt (`ticker.time`). Fehlt er, bleibt er leer; das ist
   ehrlicher als der Analysezeitpunkt an seiner Stelle.

Ergänzend erwägen: Für die **Kalibrierung** nur Zeilen zulassen, deren
Abruf nachweislich im offenen Markt lag. Die Entscheidung gehört als
Nachtrag zu ADR 0058.

**Status früherer Audits**

- Audit #1 und #2: nicht vorhanden (ADR 0058 datiert vom 2026-09-04)

**Aufwand:** Small (Migration + zwei Felder, ~3 h)

---

#### AUDIT-003-011

**Severity:** Medium
**Kategorie:** Backtest-Validität / False Confidence
**Komponente:** Signal-Backtest
**Dateien:** `backend/src/ai_trading_analyst/domain/backtesting/replay.py:60`,
`backend/src/ai_trading_analyst/domain/report/builder.py:152`

**Problem**

Der Backtest bildet die Wiederholsperre (ADR 0054) nicht ab und misst damit
eine andere Strategie als die gehandelte. Anders als bei der
Earnings-Abweichung steht diese Abweichung **an keinem Ergebnis** und in
keinem Bericht.

**Technische Ursache**

`find_historical_decisions` prüft jede erste Tageskerze mit
`evaluate_candidate`; `group_into_episodes` bündelt Entscheidungspunkte,
die mindestens eine identische Feuerung teilen. Das ist die in ADR 0057
beschlossene Zählung und für sich richtig.

Der Live-Lauf entfernt zusätzlich jedes Symbol, das in den letzten sieben
Kalendertagen als `CANDIDATE` durchlief — **unabhängig davon, ob ein neues
Signal vorliegt**. ADR 0057, Abschnitt 6 hält die Unterschiedlichkeit
ausdrücklich fest: *„Sie ist ein anderes Mittel für einen anderen Zweck …
Die Episodenlogik dorthin zu übertragen wäre eine Lockerung."* Das ist
schlüssig — es folgt daraus aber, dass die beiden Zählungen **nicht
dasselbe** ergeben.

Für die strukturgleiche Earnings-Abweichung gibt es die Behandlung bereits:
`BacktestResult.earnings_exclusion_applied` steht am Ergebnis, und
`_pruefe_earnings`/`_pruefe_signalstatistik` schreiben einen Vermerk in den
Bericht (ADR 0038, Entscheidung 3). Für die Wiederholsperre existiert kein
Gegenstück.

**Auswirkung**

Die Trefferquote der Signalstatistik geht mit **25 % Gewicht** in den
Swing-Score — der zweitgrößte Einzelposten. Sie misst eine Ereignismenge,
die im Live-Betrieb so nicht gehandelt würde.

Die Richtung ist bestimmbar: Episoden werden über die geteilte Grundlage
gebündelt, typischerweise über wenige Kerzen. Ein starres Fenster von
sieben Kalendertagen ist in aller Regel **breiter**. Der Backtest zählt
damit tendenziell **mehr** Einstiege als der Live-Betrieb je erzeugt — und
zwar gerade die dicht aufeinanderfolgenden, die aus derselben Bewegung
stammen. Die gemessene Trefferquote ist damit nicht offensichtlich zu hoch
oder zu niedrig, aber sie beantwortet eine andere Frage als „wie liefen die
Einstiege, die ich tatsächlich bekommen hätte".

**Beispiel**

Ein Titel triggert am 3., am 6. und am 9. September, wobei der dritte
Trigger auf frischen Ereignissen steht und deshalb eine eigene Episode
bildet. Der Backtest zählt zwei Einstiege. Der Live-Betrieb hätte nach dem
3. September sieben Tage gesperrt — der 6. entfällt ohnehin (gleiche
Episode), der 9. entfällt durch die Sperre. Gehandelt worden wäre **ein**
Einstieg.

**Empfehlung**

Kein Umbau der Zählung — ADR 0057 hat gute Gründe. Stattdessen dieselbe
Behandlung wie bei der Earnings-Abweichung:

1. Ein Vermerk am `BacktestResult` (oder, sparsamer, ein fester Zusatz in
   `_pruefe_signalstatistik`): *„Der Replay bildet die Wiederholsperre des
   Tageslaufs nicht ab (ADR 0054); die Kennzahlen messen eine leicht andere
   Strategie als die gehandelte."*
2. Erwägen, die Kennzahl **zusätzlich** unter Anwendung eines
   Sieben-Tage-Fensters zu rechnen und beide auszuweisen — dieselbe
   Doppelzählung, die ADR 0057 mit roher und gezählter Stichprobengröße
   bereits vorlebt. Das beantwortet die Frage, ohne eine der beiden
   Zählungen aufzugeben.

Punkt 1 kostet eine Stunde und schließt den False-Confidence-Anteil.

**Status früherer Audits**

- Audit #1: **R6** betraf dieselbe Klasse (Backtest misst andere Strategie),
  bezogen auf Earnings — dort behandelt und gekennzeichnet
- Audit #2: R6 als „eingegrenzt bestätigt" geführt; die Wiederholsperre
  entstand am 2026-09-01, also nach dem Auditstichtag

**Aufwand:** Extra Small (Punkt 1); Medium (Punkt 2)

---

#### AUDIT-003-012

**Severity:** Medium
**Kategorie:** Fachliche Plausibilität / Optionen
**Komponente:** Renditeberechnung
**Datei:** `backend/src/ai_trading_analyst/domain/options/strategies.py:300`

**Problem**

Die ausgewiesene annualisierte Prämienrendite enthält keine
Transaktionskosten und steht auf dem Mittelwert. Sie beschreibt damit eine
Obergrenze, nicht eine Erwartung — und wird als einzige Zahl in Score,
Bericht und Meldung geführt.

**Technische Ursache**

```python
einfache_rendite = praemie / quote.strike
annualized_return = einfache_rendite * TAGE_JE_JAHR / restlaufzeit
```

Eine Suche nach `Gebuehr`, `Kommission`, `commission` oder `Provision` über
den gesamten Quelltext und über ADR 0048 sowie Doc 08 liefert **keinen
Treffer**. Der Optionsbacktest (ADR 0058) kennt demgegenüber einen
`execution_haircut` von 2 % je Seite und Transaktion — die **historische**
Betrachtung ist an dieser Stelle also strenger als die Live-Empfehlung.

Die übrigen Größen sind korrekt und gut begründet: Kapitalbindung =
`strike × 100` (richtig für einen Cash Secured Put), Annualisierung linear
statt aufgezinst (ADR 0048: eine Aufzinsung unterstellte beliebige
Wiederholbarkeit), Kalendertage statt Handelstage (Kapital ist über ein
Wochenende ebenso gebunden).

**Auswirkung**

Größenordnung: Bei IBKR kostet ein Optionskontrakt rund 0,65 USD. Auf eine
Prämie von 100 USD je Kontrakt sind das 0,65 % der Prämie — und, weil die
Rendite annualisiert wird, bei 35 Tagen Laufzeit rund **0,7 Prozentpunkte**
annualisierter Rendite. Bei kleinen Prämien wächst der Anteil deutlich: auf
40 USD Prämie sind es 1,6 % der Prämie.

Das ist für sich genommen klein. Es addiert sich aber auf die
Mid-Annahme aus AUDIT-003-005, und beide zeigen in dieselbe Richtung: Die
gemeldete Zahl ist die bestmögliche, nicht die erwartete. Da die Zahl
zugleich über `OPTIONS_ATTRACTIVENESS` in den Score eingeht und die
Fünftelgrenzen aus derselben Rechnung gemessen wurden (ADR 0048), ist die
**relative** Einordnung zwischen Titeln davon unberührt — die absolute
Aussage „41 % annualisiert" ist es nicht.

**Beispiel**

Ein Vorschlag mit Strike 100, Prämie 1,00 USD, 35 Tage Laufzeit:
ausgewiesen 10,4 % annualisiert. Nach Gebühren (0,65 USD je Kontrakt, ein
Verkauf) bleiben 9,7 %. Wird der Kontrakt zurückgekauft, fällt die Gebühr
erneut an.

**Empfehlung**

Nicht die Rendite umrechnen — das verlangt Annahmen über den Broker und
wäre ein gesetzter Wert an einer Stelle, die heute rein gemessen ist.
Stattdessen:

1. **Benennen.** Der Bericht und die Legende der Meldung sollten sagen, dass
   die Rendite vor Gebühren und auf Mid-Basis steht. Die Meldung trägt die
   Tilde bereits; ein Halbsatz in der Legende („Praemie je Kontrakt (Mid),
   vor Gebuehren") kostet nichts.
2. **Erwägen** (Projektinhaber, ADR-Nachtrag zu 0048): einen konfigurierten
   Gebührensatz je Kontrakt, der **zusätzlich** zur Bruttorendite eine
   Nettorendite ausweist. Nur dann sinnvoll, wenn der Wert gemessen und
   nicht geraten ist — sonst widerspricht er dem Prinzip dieses Projekts.

**Status früherer Audits**

- Audit #1 und #2: nicht vorhanden

**Aufwand:** Extra Small (Punkt 1)

---

#### AUDIT-003-013

**Severity:** Medium
**Kategorie:** Observability
**Komponente:** Protokollierung im Produktionsbetrieb
**Dateien:** `config/default.yaml:730`,
`docs/14 - Inbetriebnahme und Betrieb.md` (Abschnitt „Betriebszustand")

**Problem**

Im produktiven Betrieb entsteht **kein Protokoll**. `logging.file` steht auf
`null`, der Tageslauf schreibt nach `stdout`, und `stdout` ist unter der
Windows-Aufgabenplanung flüchtig. Nach einem fehlgeschlagenen oder
auffälligen Lauf ist nicht mehr feststellbar, was geschehen ist.

**Technische Ursache**

Kein Fehler — ein nicht gesetzter Schalter. Die Rotationsdatei ist
vollständig gebaut (`RotatingFileHandler`, 20 MB × 5, immer JSON), der
Schalter `--log-file` existiert an `cli dispatch`, der Pfad wird gegen die
Projektwurzel aufgelöst (damit eine Aufgabe ohne „Starten in" die Datei
trotzdem findet), ein nicht beschreibbarer Pfad endet sofort mit
Rückgabewert 2 statt mit einem Traceback alle 15 Minuten, und die
Schwärzung greift an der Senke. Doc 14 beschreibt alles davon.

Doc 14 hält den Zustand selbst fest: *„Die Protokolldatei ist gebaut, aber
noch nicht eingeschaltet … damit gehen die Protokolle des Tageslaufs
weiterhin nur nach `stdout` — unter der Aufgabenplanung also ins Leere."*

**Auswirkung**

Nicht beantwortbar, solange der Schalter fehlt:

| Frage aus dem Auditauftrag (§25) | heute |
|---|---|
| Welche APIs waren erfolgreich, welche nicht? | nein |
| Welche Aktien hatten Datenfehler? | teilweise (`analysis_run_errors`) |
| Warum wurde eine Aktie ausgeschlossen? | teilweise (`screening_results.reason`) |
| Gab es Warnungen? | **nein** |
| Wie viele Retries gab es? | nein |
| Welche Schritte wurden übersprungen? | nur die Wiederholsperre, und nur als Logzeile — also nirgends |
| Wo blieb die Zeit? | grob ja (`scripts/laufzeiten.py`), fein nein |

Die Logzeilen aus AUDIT-003-007 („Ergebnismeldung ging nicht raus") und
AUDIT-003-008 (Provider-Warnungen) gehen genau hier verloren. Mehrere
Befunde dieses Audits wären im Betrieb unsichtbar — nicht weil sie nicht
protokolliert werden, sondern weil das Protokoll nirgends landet.

**Empfehlung**

`--log-file var/logs/tageslauf.log` in die Argumentliste der geplanten
Aufgabe aufnehmen. Fünf Minuten Aufwand, keine Implementierung, kein
Deployment. **Der beste Ertrag je Aufwand im ganzen Audit.**

In die Argumente und nicht in `config/default.yaml` — ADR 0031: Eine
Änderung an der versionierten Datei hinterließe auf dem Server einen
dauerhaften lokalen Diff, den jedes `git pull` vorfindet.

**Status früherer Audits**

- Audit #1: nicht vorhanden (die Datei existierte noch nicht)
- Audit #2: nicht vorhanden; sie entstand mit ADR 0069 (PR #92, 2026-09-20)

**Aufwand:** Extra Small

---

#### AUDIT-003-014

**Severity:** Medium
**Kategorie:** Observability / Betrieb
**Komponente:** Überwachung des Tageslaufs
**Dateien:** `backend/src/ai_trading_analyst/cli.py:3772`,
`backend/src/ai_trading_analyst/application/dispatch_daily_run.py:92`,
`config/default.yaml:458`

**Problem**

Drei Arten von Ausfall bleiben unbemerkt. Der Kanal, der stille Ausfälle
sichtbar machen soll, hat selbst blinde Flecken.

**Technische Ursache**

Der Meldeweg für ausgefallene Läufe ist gut gebaut: `_report_overdue` prüft
bei **jedem** Start alle unerledigten Läufe, nicht nur den heutigen, und
eine gescheiterte Zustellung setzt keinen Vermerk. Er hat drei Grenzen:

1. **Rückgabewert 2 vor der Dispatcher-Logik.** `command_dispatch` kehrt bei
   Konfigurationsfehlern (fehlendes Geheimnis, unbeschreibbarer Protokollpfad,
   unbekannter Konfigurationsschlüssel, leere Watchlist) zurück, **bevor**
   `DispatchDailyRunUseCase.execute()` je läuft. `_report_overdue` wird nie
   erreicht. Es geht keine Meldung hinaus — alle 15 Minuten, den ganzen Abend.
2. **Kein Start.** Server aus, Aufgabe deaktiviert oder gelöscht. Doc 14
   nennt das Deaktivieren als regulären Handgriff für Einzelproben
   (Stufe G, Schritt 1: *„Erst die Aufgabenplanung anhalten"*). Wer sie
   danach nicht wieder aktiviert, bemerkt es nicht.
3. **Hängender Lauf.** Ein Lauf, der nicht abstürzt, sondern steht, hält den
   Advisory Lock. Alle weiteren Starts enden mit `IN_PROGRESS` — und weil
   `_report_overdue` **innerhalb** der Sperre läuft, geht auch die
   Überfälligkeitsmeldung nie hinaus.

Hinzu kommt: `notifications.send_when_no_candidates` steht auf `false`. Seit
der Wiederholsperre sind kandidatenlose Tage der Normalfall. **„Keine
Nachricht" heißt damit sowohl „alles gut, nichts gefunden" als auch „nichts
gelaufen".**

**Auswirkung**

Die im Auditauftrag geforderte Unterscheidung ist nur teilweise möglich:

```
Task gestartet          → ja  (Aufgabenplanung, Verlauf muss aktiviert sein)
Python-Prozess gestartet→ ja  („Letztes Ausführungsergebnis")
Pipeline ausgeführt     → nur per Datenbankabfrage
Pipeline erfolgreich    → nur per Datenbankabfrage; Telegram erst nach Fristablauf
Ergebnis korrekt        → nein (und das ist in Ordnung)
```

Keine dieser Feststellungen kommt von selbst. Ohne aktive Nachschau können
mehrere Tage ohne Analyse vergehen, ohne dass etwas auffällt.

**Beispiel**

Nach einem Serverneustart am Sonntag wird die TWS nicht angemeldet (ADR 0018,
akzeptierte Einschränkung). Am Montag scheitert jeder Start mit Rückgabewert 1
— hier greift die Meldung korrekt. Wird stattdessen am Freitag ein Geheimnis
rotiert und die `.env` nicht nachgezogen, endet jeder Start mit **2**, und
es meldet sich nichts.

**Empfehlung**

Ein **Wächter** als eigener, kleiner Scheduled Task, täglich um 23:15 —
bewusst außerhalb des überwachten Prozesses, denn ein Wächter im
überwachten Prozess schweigt genau dann, wenn dieser hängt:

- rein lesend, Muster `scripts/laufzeiten.py` (nimmt die Zugangsdaten aus
  `ATA_DATABASE_URL`, braucht kein `psql` im Suchpfad),
- Frage: War heute ein Handelstag, und gibt es dazu eine Zeile in
  `dispatcher_runs` mit `status = 'succeeded'`? Zusatzfrage: Liegt im
  Sicherungsordner ein Dump von heute?
- bei Befund: Telegram-Meldung und Rückgabewert 2.

Das schließt die Fälle 1 und 3 sowie die Zweideutigkeit des kandidatenlosen
Tages. Fall 2 im Extrem („Server aus") kann kein Mechanismus auf dem Server
schließen — dafür bräuchte es etwas außerhalb, und das wäre eine neue
externe Abhängigkeit mit eigenem ADR.

Kleiner Zwischenschritt, sofort wirksam:
`notifications.send_when_no_candidates` auf `true`. Dann ist eine
ausbleibende Abendnachricht ein Signal und kein Rauschen.

**Status früherer Audits**

- Audit #1: nicht vorhanden (kein produktiver Betrieb)
- Audit #2: nicht vorhanden; der Betrieb begann am 2026-09-01

**Aufwand:** Small (Wächter ~4 h); Extra Small (Meldungsschalter)

---

### Low

#### AUDIT-003-015

**Severity:** Low
**Kategorie:** Backtest / Stichprobengröße
**Komponente:** Historischer Replay
**Datei:** `backend/src/ai_trading_analyst/domain/backtesting/metrics.py:38`

**Problem**

Der Backtest verliert am Anfang seines Betrachtungsfensters rund ein halbes
Jahr Historie, weil der Warm-up von 250 Kerzen ein zweites Mal greift —
obwohl die Indikatorwerte dort bereits gültig sind.

**Technische Ursache**

`_truncate_to_recent_history` schneidet die Kerzenreihe auf
`history_years` (5) zurück. **Die Indikatoren sind zu diesem Zeitpunkt
bereits über die vollständige gespeicherte Reihe gerechnet** — der Provider
liefert sie fertig, `compute_backtest` kürzt nur. Die Werte am Anfang des
gekürzten Fensters tragen also die volle Vorgeschichte und sind gültig.

`evaluate_candidate` prüft anschließend `t < params.warmup_candles` gegen
den Index in der **gekürzten** Reihe und stuft die ersten 250 Kerzen als
`UNKNOWN_DATA_INCOMPLETE` ein. 250 Kerzen sind 125 Handelstage, also rund
sechs Monate.

**Auswirkung**

Aus nominell fünf Jahren werden effektiv rund viereinhalb. Die Zahl der
gezählten Episoden je Kombination sinkt entsprechend um etwa 10 %. Bei
Kombinationen nahe der Konfidenzschwelle (`minimum_sample_size: 10`,
`normal_confidence_sample_size: 30`) kann das den Unterschied zwischen
`NORMAL` und `LOW_SAMPLE` ausmachen — und damit über die Deckelung des
Teilwerts auf 6,0 entscheiden.

Die Richtung ist **konservativ**: Es wird nichts falsch gerechnet, es wird
weniger gerechnet. Deshalb Low und nicht höher.

**Beispiel**

Eine Kombination mit 32 Episoden über fünf volle Jahre läge auf `NORMAL`.
Fallen drei davon in das verworfene erste Halbjahr, bleiben 29 → `LOW_SAMPLE`,
und ein Teilwert von 7,8 wird auf 6,0 gedeckelt. Der Swing-Score sinkt um
0,45 Punkte — genug, um eine Stufengrenze zu verschieben.

**Empfehlung**

Prüfen, ob der Warm-up im Replay überhaupt greifen muss: Er schützt davor,
auf noch nicht eingeschwungenen Indikatorwerten zu entscheiden — genau dieser
Schutz ist durch die Berechnung über die volle Reihe bereits gegeben. Eine
saubere Lösung schneidet erst bei `cutoff` **minus Warm-up** und beginnt die
Entscheidungspunkte bei `cutoff`. Das verlangt eine kleine Erweiterung von
`_truncate_to_recent_history` und **eine Neuaufzeichnung des Golden Master**
— die Änderung verändert Kennzahlen, also steigt `SIGNAL_RULE_VERSION`.

Weil die heutige Fassung konservativ irrt, ist das kein dringlicher Punkt.
Er gehört aber benannt, weil „5 Jahre" heute an zwei Stellen etwas anderes
bedeutet als im Konfigurationskommentar.

**Status früherer Audits**

- Audit #1: **R1** betraf dieselbe Klasse („Kennzahlen suggerieren 5 Jahre,
  Basis ist ~1 Jahr") und wurde behoben. Die verbleibende Differenz ist die
  kleinere Schwester desselben Musters
- Audit #2: R1 als „behoben und verifiziert" geführt

**Aufwand:** Small (zzgl. Neuaufzeichnung und Versionssprung)

---

#### AUDIT-003-016

**Severity:** Low
**Kategorie:** Security
**Komponente:** Lese-API
**Datei:** `backend/src/ai_trading_analyst/presentation/api/app.py:24`

**Problem**

`FastAPI(...)` wird ohne `docs_url=None` / `redoc_url=None` /
`openapi_url=None` gebaut. Sobald der Dienst aus Doc 14, Stufe J läuft, sind
`/docs`, `/redoc` und `/openapi.json` im gesamten LAN ohne Anmeldung
erreichbar und beschreiben jeden Endpunkt samt Schema.

**Technische Ursache**

FastAPI-Standardverhalten. Es gibt keine Authentifizierung — das ist durch
[ADR 0049](../adr/0049-dashboard-mvp-nur-lan.md) ausdrücklich so
entschieden („MVP nur eigenes Netz, keine Exposition, keine eigene
Authentifizierung"), und die API ist strikt lesend (ADR 0053: `build_app`
baut **keinen** Anbieter, der einzige Marktdatenzugang steht fest auf
`stored`).

**Auswirkung**

Heute: **keine.** Doc 14 hält fest, dass der Dienst auf dem Server noch
nicht eingerichtet ist. Der externe Weg (ADR 0060) führt nicht über diese
API, sondern über einen verschlüsselten statischen Datenbaum bei
Cloudflare hinter Access — dort ist nichts davon erreichbar.

Künftig: Wer im eigenen Netz steht, bekommt über `/openapi.json` eine
vollständige Landkarte inklusive Feldnamen und kann jede Analyse, jeden
Bericht und jede Optionsmessung abrufen. Das ist von ADR 0049 gedeckt,
aber die Schemaauskunft ist eine zusätzliche Fläche, die nichts kostet zu
schließen.

**Empfehlung**

Vor der Einrichtung von Stufe J: `docs_url` und `redoc_url` auf `None`,
`openapi_url` auf `None` oder hinter einen Konfigurationsschalter. Ein
Entwicklungsschalter (`api.expose_docs`, ausgeliefert `false`) hielte die
lokale Erkundbarkeit, ohne sie auf dem Server zu öffnen.

**Status früherer Audits**

- Audit #1: nicht vorhanden
- Audit #2: Abschnitt 13 prüfte Sicherheit und Betriebsreife, ohne diesen
  Punkt

**Aufwand:** Extra Small

---

#### AUDIT-003-017

**Severity:** Low
**Kategorie:** Tote Konfiguration / Irreführung
**Komponente:** Modellprofile
**Datei:** `config/default.yaml:236`,
`backend/src/ai_trading_analyst/config/settings.py:600`

**Problem**

`llm.fundamental` und `llm.report` sind definiert, konfiguriert und
kommentiert — und werden **nirgends gelesen**. Ein Leser der Konfiguration
muss schließen, dass an Fundamentalanalyse und Berichtserzeugung ein
Sprachmodell beteiligt ist. Beides ist ausdrücklich nicht der Fall.

**Technische Ursache**

`bootstrap.py` greift ausschließlich auf `config.llm.research` (Zeilen
566–567) und `config.llm.technical` (Zeilen 601–602) zu. Die beiden übrigen
Profile haben keinen Leser.

Historisch nachvollziehbar: ADR 0021 legte Modellprofile je Analyseaufgabe
fest, bevor ADR 0032 („Fundamentalanalyse deterministisch") und ADR 0039
(„Report Generator erzeugt keine neuen Fakten") entschieden, dass diese
beiden Aufgaben **ohne** Modell laufen. Die Profile sind stehen geblieben.

**Auswirkung**

Kein Laufzeiteffekt. Die Irreführung ist der Punkt: Die zentrale Regel des
Projekts lautet „Technische Signale werden niemals durch KI verändert", und
`config/default.yaml` ist die Datei, in der ein Außenstehender nachsieht,
wo überall KI im Spiel ist. Zwei Einträge behaupten dort etwas, das drei
ADRs ausschließen.

Zusätzlich fallen beide unter den quartalsweisen Pflegepunkt
„Modell-Identifier gegen den aktuellen Katalog prüfen" (Doc 14) — Pflege für
etwas, das niemand benutzt.

**Empfehlung**

Streichen, mit Vermerk im ADR-Nachtrag zu 0021 (Muster ADR 0024/`pushover`,
A2-M10 — dort wurde genauso verfahren). Alternativ, falls sie für eine
geplante Aufgabe reserviert bleiben sollen: einen Kommentar, der sagt, dass
sie heute keinen Leser haben und warum.

**Status früherer Audits**

- Audit #1: **M14** („ungenutzte Secret-Felder kommentieren/entfernen")
  betraf dasselbe Muster an anderer Stelle; als erledigt geführt
- Audit #2: **A2-F005** („Ungenutzte Secret-Felder mit veralteten
  Kommentaren") — dasselbe Muster, die Modellprofile waren nicht erfasst

**Aufwand:** Extra Small

---

#### AUDIT-003-018

**Severity:** Low
**Kategorie:** Dokumentationswiderspruch
**Komponente:** Doc 13
**Datei:** `docs/13 - Deployment.md` (Abschnitt „Backup")

**Problem**

Doc 13 schließt mit: *„**Ein Sicherungsverfahren ist noch nicht
beschlossen.** Zu sichern sind Datenbank, Berichte und Konfiguration; wie und
wohin, ist offen."* Das stimmt seit dem 2026-09-01 nicht mehr — Doc 14
beschreibt Verfahren, Skripte, Aufbewahrungsfrist, Prüfung und
Abnahmekriterium, und Doc 10 §15 trägt bereits einen Umsetzungsvermerk.

**Technische Ursache**

Nachzug unterblieben. Dasselbe Muster, das Audit 1 als **R3** und Audit 2
als **A2-F002/A2-F007** geführt haben: Die Dokumentation wird an einer
Stelle nachgeführt und an einer zweiten nicht.

**Auswirkung**

Verwirrend an der ungünstigsten Stelle. Wer nach einem Serverausfall die
Wiederherstellung vorbereitet, liest zuerst Doc 13 („was wird ausgeliefert")
— und erfährt dort, dass es kein Sicherungsverfahren gibt. Das ist
zufälligerweise der heutige Ist-Zustand (AUDIT-003-002), aber aus dem
falschen Grund: nicht weil nichts beschlossen wäre, sondern weil das
Beschlossene nicht eingerichtet ist.

**Empfehlung**

Den Abschnitt durch einen Verweis auf Doc 14 ersetzen, mit der bewussten
Einschränkung (Ablage auf demselben Volume) als Einzeiler. Doc 10 §15 zeigt,
wie es aussieht: ein Umsetzungsvermerk, der das Zielbild stehen lässt.

**Status früherer Audits**

- Audit #1: **R3**/**M9** (Dokumentation führt überholte Statusaussagen)
- Audit #2: **A2-F002**/**A2-F007** (dasselbe Muster); A2-F002 hält
  ausdrücklich fest, dass der Doku-Nachzug nicht an den Merge gekoppelt ist

**Aufwand:** Extra Small

---

#### AUDIT-003-019

**Severity:** Low
**Kategorie:** Technische Schuld
**Komponente:** CLI
**Datei:** `backend/src/ai_trading_analyst/cli.py` (5.055 Zeilen)

**Problem**

`cli.py` ist mit 5.055 Zeilen mehr als doppelt so groß wie die nächstgrößte
Datei und enthält 21 Kommandos, deren Ausgabeformatierung, deren
Argumentdefinition und erhebliche Teile der Verdrahtung. `build_parser`
allein umfasst rund 900 Zeilen.

**Technische Ursache**

Gewachsen, nicht entworfen. Die Struktur ist dabei durchgängig konsistent:
je Kommando eine `command_*`-Funktion, davor die `_print_*`-Helfer, am Ende
ein Parser-Block. Die Domain- und Application-Schichten sind sauber
getrennt — es ist ausschließlich die Presentation-Schicht, die sich
aufgestaut hat.

**Auswirkung**

Keine fachliche. Drei praktische:

1. `tests/unit/test_cli.py` ist mit 4.173 Zeilen entsprechend groß; ein
   gezielter Testlauf für ein Kommando ist nicht möglich.
2. Wiederkehrende Muster liegen mehrfach vor — Provider-Übersteuerung,
   `_open_database`, Watchlist-Filterung nach `--symbols`, CSV-Ausgabe
   treten in jeweils vier bis sechs Kommandos in leichten Abwandlungen auf.
   Genau dort entstehen Abweichungen, die niemand sucht.
3. Die Datei ist die häufigste Konfliktfläche bei paralleler Arbeit.

**Empfehlung**

**Kein Refactoring im Rahmen dieses Audits** (§32). Wenn die Datei ohnehin
angefasst wird, bietet sich ein schrittweiser Zuschnitt an: ein Paket
`presentation/cli/` mit einem Modul je Themenbereich (Bestand, Screening,
Backtest, Optionen, Fundamentals, Betrieb) und einer gemeinsamen
Hilfsschicht für die wiederkehrenden Muster. Das ist ein eigenes Vorhaben
mit eigenem PR, nicht ein Nebenprodukt.

**Status früherer Audits**

- Audit #1: nicht vorhanden (die Datei war kleiner)
- Audit #2: nicht vorhanden

**Aufwand:** Large (falls überhaupt angegangen)

---

### Informational

#### AUDIT-003-020

**Severity:** Informational
**Kategorie:** Backtest / Survivorship Bias
**Komponente:** Watchliste als Grundgesamtheit

**Problem**

Der Backtest läuft über die **heutige** Watchliste. Titel, die in den
vergangenen fünf Jahren aus dem Index gefallen, übernommen, dekotiert oder
umbenannt wurden, sind nicht darin. Das ist ein klassischer Survivorship
Bias, und er ist im Repository **nirgends dokumentiert**.

**Warum das trotzdem nur Informational ist**

Der Backtest beantwortet hier nicht die Frage „wie hätte die Strategie über
ein Anlageuniversum abgeschnitten", sondern „wie liefen Signale **dieses
Titels** in der Vergangenheit" — die Kennzahlen werden je Aktie und je
Signalkombination gerechnet, gespeichert und in den Score dieses Titels
eingespeist (`_signalstatistik`: *„Maßgeblich ist die Statistik genau der
Signalkombination, die heute ausgelöst hat"*). Für diese Frage ist die
Auswahlverzerrung über die Titelmenge ohne Bedeutung.

Sie bekäme Bedeutung, sobald jemand die Kennzahlen **über Titel hinweg**
aggregiert — etwa im Optionsbacktest, der genau das tut: eine Zeile über
alle Aktien (ADR 0058, Festlegung 9). Die dortige Gesamtzeile steht damit
auf einer überlebenden Auswahl.

**Empfehlung**

Ein Satz an der richtigen Stelle. Die Gesamtzeile des Optionsbacktests
gehört mit dem Hinweis versehen, dass ihre Grundgesamtheit die heutige
Watchliste ist. Der Signal-Backtest je Titel braucht nichts.

Eine Korrektur wäre unverhältnismäßig: Sie verlangte eine historische
Indexzusammensetzung und Kursdaten dekotierter Titel — eine neue
Datenquelle für eine Frage, die das System nicht stellt.

**Status früherer Audits:** in beiden nicht behandelt.

**Aufwand:** Extra Small

---

#### AUDIT-003-021

**Severity:** Informational
**Kategorie:** Betrieb / Ausstehendes Deployment
**Komponente:** Dashboard-Export

**Problem**

ADR 0068 („Der Export rechnet abgeschlossene Läufe nicht jeden Tag neu")
und ADR 0069 („Backfill und Analyse verzahnt") sind über PR #92 nach `dev`
gemergt, aber **nicht auf dem Server**. Doc 14 führt den Tageslauf
weiterhin mit 103 Minuten, davon 42,7 für den Export — ein Anteil, der
laut ADR 0068 mit jedem Handelstag wächst, unabhängig davon, wieviel sich
geändert hat.

**Auswirkung**

Zwei Folgen, beide betrieblich:

1. Das Startfenster (17:30 bis 21:30) wird enger. Ein um 21:30 gestarteter
   Lauf rechnet bis 23:13; wächst der Export weiter, rückt er in die
   Nachholfrist hinein.
2. Die in Doc 14 genannte Sicherungszeit von 22:00 passt nicht mehr
   (siehe AUDIT-003-002).

Außerdem steht ADR 0068 formal noch auf **„Vorgeschlagen"**, obwohl er
gemergt ist. Das gehört vor dem Ausrollen geklärt — die ADR-Konvention
unterscheidet die beiden Zustände nicht ohne Grund.

**Empfehlung**

Aktualisierung nach Doc 14, Abschnitt „Aktualisierung" (inklusive `npm ci`
— ohne frisch aufgelösten `node_modules`-Baum sendet der Tageslauf nichts),
danach eine Messung mit `scripts/laufzeiten.py` über einige Tage. Erst
danach die Sicherungszeit festlegen.

**Status früherer Audits:** nicht anwendbar (beide ADRs vom 2026-09-20).

**Aufwand:** Small (Deployment + Abnahme)

---

## 6. Previous Audit Findings

### 6.1 Audit #1 (2026-08-23) — Risiken R1–R10

Audit 2 hatte alle zehn verifiziert. Dieses Audit prüft nach, ob der Stand
gehalten hat.

| ID | Risiko | Stand nach Audit 2 | **Stand 2026-09-20** | Beleg |
|---|---|---|---|---|
| R1 | Kennzahlen suggerieren 5 J, Basis ~1 J | behoben | **behoben, mit kleinem Rest** | `backtesting.history_years: 5`, Tiefen-Backfill gelaufen; effektiv ~4,5 J wegen doppeltem Warm-up → **AUDIT-003-015** |
| R2 | Kein Golden Master | behoben | **behoben, Reichweite begrenzt** | Golden-Tests laufen im normalen `pytest`; Scoring/Optionen nicht abgedeckt → **AUDIT-003-009** |
| R3 | CLAUDE.md leitet Sessions fehl | behoben | **behoben** | Gate-Tabelle aktuell; Muster wiederholt sich anderswo → AUDIT-003-018 |
| R4 | Doc 14 bricht am falschen Head | behoben | **behoben** | „aktueller Head" trägt weiterhin; 28 Migrationen ohne Anpassung überstanden |
| R5 | Research: Kostenstreuung, Belegqualität | eingegrenzt | **gegenstandslos im Betrieb** | Research steht produktiv auf `none` (ADR 0051); der Pfad existiert und ist getestet |
| R6 | Backtest ohne hist. Earnings-Filter | eingegrenzt | **eingegrenzt, Muster unvollständig** | `earnings_exclusion_applied` + Berichtsvermerk vorbildlich; für die Wiederholsperre fehlt das Gegenstück → **AUDIT-003-011** |
| R7 | Kein Merge-Schutz | behoben | **behoben** | ADR 0031; nicht erneut extern geprüft |
| R8 | Preislisten veralten still | offen | **weiterhin offen, verschärft** | `research.pricing`/`technical_agent.pricing` von Hand; dieselbe Lücke betrifft die Score-Schwellen → **AUDIT-003-009**. Die Modell-IDs (`claude-sonnet-5`, `claude-haiku-4-5-20251001`) sind aktuell |
| R9 | Ein Thread-Pool für beide Agenten | behoben | **behoben** | `AgentConcurrency(2, 4)`, zwei Pools im `ExitStack` |
| R10 | `pushover` ungebaut im Schema | offen | **behoben** | aus dem Schema gestrichen (A2-M10); dasselbe Muster besteht bei `llm.fundamental`/`llm.report` → **AUDIT-003-017** |

**Kein Rückfall.** Von zehn Risiken sind acht geschlossen, R8 bleibt offen
und hat sich auf eine zweite Fläche ausgedehnt, R6 ist als Muster
unvollständig geblieben.

### 6.2 Audit #1 — Maßnahmen M1–M14

Alle vierzehn waren in der Nachverfolgung zu Audit 1 als erledigt oder
bewusst verworfen geführt; Audit 2 hat das verifiziert. Stichprobenprüfung
in diesem Audit an drei Stellen:

| ID | Maßnahme | Stichprobe | Ergebnis |
|---|---|---|---|
| M5 | Golden Master auf Realdaten | `tests/golden/data/` | **bestätigt** — zwei erzeugte und zwei reale Fälle (A2-M3), 15 Tests grün |
| M6 | Prompt-Injection-Test Research | `tests/unit/infrastructure/anthropic/` | **bestätigt** — Research-Kontext ohne Werkzeugrechte, Scores nie aus Freitext |
| M14 | `temperature=0` verifizieren | `technical_interpreter.py:579` | **bestätigt** — `temperature=0.0`, Werkzeugschema mit `strict: True` und Pflichtfeldern |

### 6.3 Audit #2 (2026-08-31) — Maßnahmen A2-M1–A2-M11

| ID | Maßnahme | Stand Audit 2 | **Stand 2026-09-20** |
|---|---|---|---|
| A2-M1 | Optionsanalyse: Review, PR, Merge | erledigt | **erledigt** (PR #60) |
| A2-M2 | Serverprobe Optionspfad + Tageslauf | erledigt | **erledigt** (Lauf `7c88d78c`) |
| A2-M3 | Golden-Master-Realdatenfall | erledigt | **erledigt** (`aapl`, `msft` ab 2025-01-02) |
| A2-M4 | Backup/Restore minimal | **teilweise** | **unverändert teilweise** → **AUDIT-003-002**. Seit 19 Tagen offen |
| A2-M5 | Betriebszustand klarstellen | erledigt | **erledigt und gepflegt** — Doc 14 führt Export und Laufzeiten nach |
| A2-M6 | Pflegeturnus festlegen | erledigt | **erledigt**, erster Termin 2026-12-01 steht aus |
| A2-M7 | Contract-Antworten einfrieren | erledigt | **erledigt** — Finnhub ×2, IBKR-Kette, je ein Contract-Test |
| A2-M8 | Doku-Kleinigkeiten | erledigt | **erledigt**; neues Beispiel derselben Klasse → AUDIT-003-018 |
| A2-M9 | E13 entscheiden | erledigt | **erledigt** (ADR 0050) |
| A2-M10 | `pushover`, Finnhub-Header | erledigt | **erledigt und verifiziert** — `auth.py` setzt `X-Finnhub-Token`, Schwärzung greift zusätzlich |
| A2-M11 | Dashboard-Sprint vorbereiten | teilweise | **weitgehend erledigt** — Redesign, externer Export und Cloudflare sind gebaut und geschaltet; **Stufe J (LAN-Dienst) steht weiter aus** |

### 6.4 Audit #2 — Befunde A2-F001–A2-F008

| ID | Befund | **Stand 2026-09-20** | Beleg |
|---|---|---|---|
| A2-F001 | Optionsanalyse ohne Review/Merge/Serverprobe | **behoben** | PR #60 gemergt, Serverprobe belegt |
| A2-F002 | README/Roadmap führen Sprint 5 als „nicht gebaut" | **behoben** | README auf Stand 2026-09-18 |
| A2-F003 | Doc 08 ohne Kopfvermerk, von ADR 0048 überholt | **behoben** | Kopfvermerk vorhanden |
| A2-F004 | Veralteter Konfigurationskommentar 5-J-Backfill | **behoben** | |
| A2-F005 | Ungenutzte Secret-Felder | **behoben**; Muster besteht fort | → **AUDIT-003-017** (Modellprofile) |
| A2-F006 | Gemessene Schwellen ohne Pflegeturnus | **teilweise behoben** | Turnus da (Doc 14 „Pflege"), Versionskopplung nicht → **AUDIT-003-009** |
| A2-F007 | Widersprüchliche Aussagen zum Betriebszustand | **behoben**; ein Rest | Doc 14 „Betriebszustand" ist maßgeblich; Doc 13 hinkt nach → **AUDIT-003-018** |
| A2-F008 | Contract-Tests nur für EDGAR | **behoben** | A2-M7; die IBKR-Kette friert die Struktur nach `_als_quote` ein, nicht das Drahtformat — als Folgeschritt benannt |

---

## 7. New Findings

Achtzehn der zwanzig Befunde sind neu: AUDIT-003-001 bis -008, -010 bis
-014, -016, -017 sowie -019 bis -021.

Sie verteilen sich auf drei Ursachen:

| Ursache | Befunde |
|---|---|
| **Der produktive Betrieb ist neu.** Beide Vorgängeraudits untersuchten ein System vor dem Scharfschalten; Betriebsbefunde konnten dort nicht entstehen | 002, 006, 013, 014, 021 |
| **Neue Bausteine seit dem 2026-08-31**: Scoring-Empfehlung, Wiederholsperre, Optionsrückblick, Dashboard-Export, Verzahnung | 004, 008, 010, 011, 021 |
| **Anderer Prüfwinkel.** Dieses Audit fragt nach der *Wirkung* einer Regel, nicht nach ihrem Vorhandensein | 001, 003, 005, 007, 012, 017 |

Der dritte Punkt erklärt die schwersten Befunde. Audit 2 prüfte für den
Earnings-Filter, ob der Status korrekt entsteht — das tut er. Dieses Audit
fragt, was der Status bewirkt, und findet: nichts (AUDIT-003-003).
Entsprechend bei den Liquiditätswarnungen (005) und der Datenabdeckung
(004): Alles ist berechnet, gespeichert und getestet; es fehlt jeweils die
letzte Stufe, an der die Information eine Entscheidung verändert.

## 8. Resolved Findings

Seit Audit 2 geschlossen: **A2-F001, A2-F002, A2-F003, A2-F004, A2-F005,
A2-F008** sowie **A2-M1, A2-M2, A2-M3, A2-M7, A2-M9, A2-M10** und aus
Audit 1 **R10**.

Bemerkenswert ist A2-M10: Die Umstellung des Finnhub-Schlüssels vom
Query-Parameter in den Header wurde nicht nur gebaut, sondern **gegen den
echten Dienst bestätigt**, und die Schwärzung an der Log-Senke bleibt
zusätzlich bestehen — mit der ausdrücklichen Begründung, dass sie für den
nächsten Parameter gilt, den jemand ergänzt, ohne den Absatz gelesen zu
haben. Das ist die Behebung einer Ursache statt eines Symptoms, und Audit 1
hatte genau dieses Muster als Prozessbefund angemahnt.

## 9. Partially Resolved Findings

| ID | Was steht, was fehlt |
|---|---|
| **A2-M4** (Backup) | Skripte, Dokumentation, Abnahmekriterium stehen. Es fehlt der Eintrag in der Aufgabenplanung → AUDIT-003-002 |
| **A2-M11** (Dashboard) | Redesign, Export und externer Weg stehen. Es fehlt Stufe J → AUDIT-003-016 wird damit relevant |
| **A2-F006** (Schwellen) | Der Turnus steht. Die Kopplung an die Version fehlt → AUDIT-003-009 |
| **R1** (Historientiefe) | Fünf Jahre sind geholt. Effektiv nutzbar sind ~4,5 → AUDIT-003-015 |
| **R6** (Backtest-Abweichung) | Earnings gekennzeichnet. Wiederholsperre nicht → AUDIT-003-011 |
| **R8** (Preislisten) | Modell-IDs aktuell. Kein Mechanismus, der Alterung bemerkt → AUDIT-003-009 |

## 10. Regression Findings

**Keine.** Kein in Audit 1 oder 2 behobener Befund ist wieder aufgetreten,
und keine Maßnahme hat einen neuen Fehler eingeführt.

Zwei Punkte, die wie Regressionen aussehen könnten, sind keine:

- Die **Wiederholsperre** (ADR 0054) verschärft die Folgen eines
  Provider-Ausfalls (AUDIT-003-008). Das ist keine Regression, sondern eine
  neue Wechselwirkung zwischen zwei für sich richtigen Mechanismen — und
  ADR 0054 hat die Kostenabwägung bewusst getroffen.
- Der **Dashboard-Export** hat die Laufzeit von 53 auf 103 Minuten gehoben
  (AUDIT-003-021). Das wurde am ersten produktiven Tag gemessen, in Doc 14
  festgehalten und mit ADR 0068 behoben, bevor dieses Audit begann. Der
  Vorgang ist ein Beleg **für** die Beobachtungsdisziplin, nicht gegen sie.

---

## 11. Architecture Assessment

**Die Architektur ist konsistent mit ADRs und Requirements.** Das ist keine
Höflichkeitsformel, sondern das Ergebnis von zwei Prüfungen, die es hätten
widerlegen können.

**Erstens: Die Schichtgrenze ist erzwungen, nicht vereinbart.**
`tests/architecture/test_layer_boundaries.py` bricht die CI bei einem
Import aus dem Domain Layer auf FastAPI, SQLAlchemy, Anbieter-SDKs oder
KI-Bibliotheken. Stichproben bestätigen die Wirkung: `domain/options/
strategies.py` enthält keine Uhr, kein Netz und keine Konfiguration; der
IBKR-Adapter ruft die Domänenfunktionen, statt die Auswahl selbst zu
treffen; `domain/fundamentals/metrics.py` bekommt bereits aufgelöste Werte.

**Zweitens: Die drei gerichteten Kopplungen halten.** CLAUDE.md nennt genau
drei — Optionen↔Zonen, Fundamentals↔Kurs, Optionen↔Earnings — und für jede
drei Bedingungen (optional, nicht blockierend, keine eigene Ableitung). Alle
drei sind im Code nachweisbar eingehalten:

- `build_options_analysis(zones=(), next_earnings_date=None)` — beide
  Vorgaben leer zulässig, die zonenabhängigen Felder werden `None`.
- `_evaluate_fundamentals(stock, series.candles[decision_index].close)` —
  der Kurs wird hineingereicht, nicht beschafft.
- `select_expiration(next_earnings_date=...)` — ein fehlender Termin hält
  nichts auf, ein vorhandener wirkt. Genau die in CLAUDE.md verlangte
  Asymmetrie.

Eine vierte, nicht deklarierte Kopplung wurde gesucht und **nicht gefunden**.

### Verantwortlichkeiten

| Schicht | Zuständig für | Auffälligkeit |
|---|---|---|
| Domain | Signale, Kerzen, Backtest, Scores, Optionsauswahl, Berichtsinhalt | sauber, keine Infrastruktur |
| Application | Orchestrierung, Fehlerisolation, Nebenläufigkeit, Dispatcher | `run_analysis.py` mit 1.166 Zeilen an der Obergrenze des Angenehmen |
| Infrastructure | Anbieter, Persistenz, Publishing, Protokollierung | durchgängig ohne Fachregel |
| Presentation | CLI, API, Export | **`cli.py` aufgestaut** → AUDIT-003-019 |

### Überholte Architekturentscheidungen

Gesucht, **keine gefunden**. Drei ADRs tragen Formulierungen, die vom
späteren Stand überholt wurden — alle drei sagen das selbst:

- ADR 0020 (L2, „konservative" Fehlerrichtung) — von ADR 0030 widerlegt und
  abgelöst; ADR 0020 bleibt bewusst unverändert stehen.
- ADR 0049 („keine Exposition") — von ADR 0060 präzisiert; die
  ADR-Übersicht hält die Ablösung ausdrücklich fest.
- ADR 0068 steht auf „Vorgeschlagen", obwohl gemergt → AUDIT-003-021.

Die Konvention „ein Audit wird nicht rückwirkend geändert; ist eine
Feststellung überholt, entsteht ein neues Audit" gilt hier offenbar auch für
ADRs und wird gelebt.

---

## 12. Data Quality Assessment

### 12.1 Quellen und Zuständigkeiten

| Datum | Quelle | Bezug | Validierung |
|---|---|---|---|
| 15-Minuten-Bars | IBKR TWS (`TRADES`, `useRTH=True`, `formatDate=2`) | Backfill in den Bestand | Raster-, Dubletten- und Zeitzonenprüfung in `aggregate_intraday_bars`; **keine Größenordnungsprüfung** → AUDIT-003-001 |
| 195-Minuten-Kerzen | eigene Aggregation | alle Analysen | Vollständigkeit erzwungen, drei Unvollständigkeitsgründe unterschieden |
| Handelskalender | IBKR `liquidHours` | Dispatcher | bei Ausfall Wochentagsnäherung, protokolliert |
| Earnings-Termine | Finnhub | Filter, Optionsverfall | Termin vor `as_of` → `ValueError` → `UNKNOWN` mit Grund `invalid_data` |
| Analystenvoten | Finnhub | Score-Komponente | Plausibilitätsschranke (`_SUSPICIOUS_ENTRY_COUNT`), Altersschranke 62 Tage |
| Fundamentaldaten | SEC EDGAR (XBRL) | Investment-Score | Stichtagsbindung erzwungen, `MAX_RUECKSTAND_TAGE` 180, `MAX_BEWERTUNGSALTER_TAGE` 455 |
| Optionsketten | IBKR (`market_data_type: 2`) | Put-Vorschläge | Delta-Band, Mittelwert, Prämie > 0, gekreuzter Markt; **kein Zeitstempel** → AUDIT-003-010 |
| KI-Einordnung | Anthropic | zwei Score-Komponenten | Werkzeugschema `strict`, Pflichtfelder, `temperature=0`, Abbruch bei `max_tokens` |

### 12.2 Der Umgang mit fehlenden Werten

**Durchgängig vorbildlich.** Eine gezielte Suche nach dem typischen
Fehlerbild — `or 0`, `or 0.0`, `.get(x, 0)`, stille Defaults, fortgeschriebene
Vorwerte — ergab **keinen einzigen Treffer** in einem fachlich relevanten
Pfad. Stattdessen:

- `relative_strength_index` liefert bei 0/0 `None`, nicht 50 oder 100, mit
  ausformulierter Begründung.
- `simple_moving_average` liefert `None`, sobald ein Fenster eine Lücke
  enthält — keine Interpolation, kein Überspringen.
- `_recursive_average` beginnt nach einer Lücke **neu**, statt über sie
  hinwegzuschreiben.
- Signalfunktionen werfen `DataIncompleteError`, statt `False`
  zurückzugeben: *„eine Datenlücke ist kein negatives Signal"*.
- `analyst_buy_share` unterscheidet vier Arten von „kein Wert" und benennt
  sie einzeln im Bericht.
- Der Score gewichtet um, statt zu nullen — *„sie mit 0 zu bewerten hieße zu
  behaupten, sie sei geprüft und schlecht"*.

Die einzige Stelle, an der ein fehlender Wert in eine Rechnung eingeht, ist
`aggregate()`: `sum(k.effective_weight * (k.value or 0.0) …)`. Sie ist
ungefährlich, weil das effektive Gewicht nicht verfügbarer Komponenten
zuvor auf `0.0` gesetzt wird — das `or 0.0` ist Typsicherheit, keine
Ersetzung.

### 12.3 Der Umgang mit **falschen** Werten

Hier liegt die Asymmetrie dieses Systems. Gegen *fehlende* Daten ist es
hervorragend gerüstet; gegen *falsche* fast gar nicht.

| Quelle | Plausibilitätsprüfung |
|---|---|
| Finnhub-Empfehlungen | **ja** — `_SUSPICIOUS_ENTRY_COUNT`, erkennt Antworten mit unplausibel vielen Einträgen |
| Finnhub-Earnings | **ja** — Termin vor `as_of` wird abgewiesen |
| EDGAR | **ja** — Stichtagsbindung, Rückstands- und Bewertungsalter |
| Optionsnotierungen | **ja** — gekreuzter Markt, Prämie ≤ 0, fehlendes Delta |
| **Kursdaten (Bars)** | **nein** — Raster und Vollständigkeit, aber kein Wertebereich, kein Sprung, kein Ausreißer |

Der letzte Punkt ist AUDIT-003-001 und zugleich die Antwort auf die Frage
des Auditauftrags nach Corporate Actions: **Splits werden nicht behandelt**,
Dividenden fließen nicht ein (`TRADES` ist nicht dividendenbereinigt — für
eine Signalstrategie auf Schlusskursen ist das richtig, und der
Optionsbacktest hält die Auslassung in ADR 0058 fest), Delistings und
Tickerwechsel treten nicht auf, weil die Watchliste manuell gepflegt wird
und ein unbekanntes Symbol bei IBKR schlicht als Fehler dieser einen Aktie
endet.

### 12.4 Zeit und Zeitzonen

Gezielt nach DST- und Zeitzonenfehlern gesucht. **Keiner gefunden.**

- `ruff` erzwingt die `DTZ`-Regeln; naive Zeitstempel sind untersagt und
  werden in `aggregate_intraday_bars` zusätzlich zur Laufzeit abgewiesen.
- Der Dispatcher rechnet den Börsentag in `America/New_York` aus, nicht in
  UTC — mit ausformulierter Begründung für den Fall der zweiten Tageskerze.
- Der Betreff der Telegram-Meldung nimmt den Handelstag aus der Börsenzeit,
  *„ein Lauf nach 20:00 New Yorker Zeit läge in UTC bereits am Folgetag"*.
- `observability/timing.py` misst mit `time.monotonic`, ausdrücklich gegen
  Zeitumstellung und NTP-Sprünge.
- Die Kerzenbildung rechnet ab der lokalen Sitzungseröffnung; 09:30 New York
  existiert an jedem DST-Übergangstag.
- Die einzige feste deutsche Uhrzeit steht im Trigger der Aufgabenplanung —
  bewusst und dokumentiert, mit einem Fenster, das den zwei- bis
  dreiwöchigen Versatz zwischen US- und EU-Umstellung abdeckt.

---

## 13. Backtest Assessment

### 13.1 Die Leitfrage

> **Ist der Backtest tatsächlich eine Simulation dessen, was das heutige
> System zum jeweiligen historischen Zeitpunkt hätte wissen können?**

**Weitgehend ja — mit drei benannten Abweichungen, von denen zwei
dokumentiert sind und eine nicht.**

| Prüfpunkt | Ergebnis | Beleg |
|---|---|---|
| **Look-ahead Bias** | **nein** | `evaluate_candidate` liest ausschließlich `t` und `t−1` bis `t−5`. Die Indikatoren sind rekursiv aus der Vergangenheit gerechnet (EMA, Wilder). `compute_episode_outcome` nimmt den Einstieg aus `t` und den Pfad aus `t+1 … t+horizon` — die Zukunft geht in die **Bewertung**, nie in die **Entscheidung** |
| **Zonen-Look-ahead** | **nein** | Ein Swing-Punkt braucht `pivot_reach` Kerzen auf **beiden** Seiten; die jüngsten können keinen bilden. Der Docstring nennt den Grund: *„Ein Verfahren, das den letzten Balken schon als Hochpunkt führt, meldet auf jedem neuen Hoch eine neue Widerstandszone"* |
| **Data Leakage** | **nein** | Keine Kennzahl aus der Zukunft, keine anbieterseitige Rückwirkung — mit einer Ausnahme: AUDIT-003-001, wo IBKRs Rückwirkung über Splits **in die Vergangenheit** hineinreicht |
| **Falsche Candle-Grenzen** | **nein** | Entscheidungspunkt ist ausschließlich die erste Tageskerze (`is_decision_point`), identisch zum Live-Betrieb. Die Funktion ist öffentlich, *„damit der Validierungschart dieselbe Definition benutzt"* |
| **Entry/Exit-Definition** | **eindeutig** | Einstieg = Schluss der Kerze des **ersten Triggers der Episode** (CLAUDE.md, ADR 0057). Kein Exit — gemessen wird der Kurspfad über feste Horizonte |
| **Overlapping Trades** | **behandelt** | Episodenbildung über geteilte Feuerungen (ADR 0057). Der Nachbarvergleich genügt für die transitive Hülle, und der Docstring beweist es |
| **Stichprobengröße** | **ausgewiesen** | roh **und** gezählt, je Horizont; unter 10 Ereignissen keine Kennzahl, 10–29 gedeckelter Teilwert |
| **Survivorship Bias** | **vorhanden, unschädlich** | je Titel gerechnet → AUDIT-003-020 |
| **Selection Bias** | **vorhanden, benannt** | Die Watchliste ist manuell gewählt. Für eine Aussage je Titel ohne Belang |
| **Splits / Corporate Actions** | **nicht behandelt** | **AUDIT-003-001** |
| **Dividenden** | **nicht enthalten** | `TRADES` ist nicht dividendenbereinigt. Für eine Signalstrategie auf Schlusskursen richtig; in ADR 0058 für die Optionsseite ausdrücklich als Auslassung geführt |
| **Fehlende Handelstage** | **teilweise erkennbar** | Innerhalb eines Tages mit Daten bleibt kein Fenster unbemerkt; ein **vollständig** fehlender Tag ist ohne Börsenkalender nicht feststellbar — im Docstring benannt |
| **Slippage / Transaktionskosten** | **nicht enthalten** | Bewusst: Der Signal-Backtest misst den **Kurspfad**, nicht einen Handel. Der Optionsbacktest kennt demgegenüber einen `execution_haircut` |
| **Earnings-Abweichung** | **gekennzeichnet** | `earnings_exclusion_applied` + Berichtsvermerk (ADR 0038/0042) |
| **Wiederholsperre-Abweichung** | **nicht gekennzeichnet** | **AUDIT-003-011** |

### 13.2 Kennzahlen

Der Auditauftrag verlangt, soweit aus der Implementierung möglich, auch
Zahlen zu prüfen.

> **Nicht verifizierbar anhand des Repository-Zustands.** Trefferquoten,
> Mittelwerte, Mediane, Drawdowns und Ereigniszahlen entstehen aus dem
> Serverbestand und liegen nicht im Repository. Der Golden Master enthält
> Kennzahlen über **erzeugte** und zwei **eingefrorene reale** Bar-Reihen;
> sie belegen die Rechnung, nicht die Marktlage.

Geprüft wurde stattdessen, ob die Kennzahlen **definiert und richtig
gerechnet** sind:

| Kennzahl | Definition | Bewertung |
|---|---|---|
| Anzahl Ereignisse | roh und nach Episoden gezählt, je Horizont getrennt | korrekt; ein Ereignis nahe dem Reihenende zählt für lange Horizonte nicht mit, und das ist ausgewiesen |
| Trefferquote | Anteil der Episoden mit `return_pct > 0` | korrekt; strikt größer null |
| Mittelwert / Median | `statistics.fmean` / `statistics.median` über dieselben Ergebnisse | korrekt |
| Max Loss | **Minimum** aller Zwischenrenditen über den Pfad, nicht nur am Ende | korrekt und strenger als eine Endbetrachtung |
| Drawdown | maximaler Rückgang vom laufenden Hoch | korrekt |
| „Hält über Einstieg" | `all(close > entry)` über den gesamten Pfad | **getrennt** von der Trefferquote geführt — CLAUDE.md verlangt genau das, und es wird eingehalten |

**Die wichtigste Eigenschaft ist eine Negative:** Trefferquote und
dauerhaftes Halten werden nirgends zu einer gemeinsamen „Erfolgsquote"
verrechnet — weder in der Datenhaltung noch im Score noch im Berichtstext.
Das wurde gezielt gesucht und nicht gefunden.

ADR 0061 („eine Rechnung") ist sauber umgesetzt: `compute_episode_outcome`
liefert das Ergebnis genau einmal; die Kennzahlen mitteln über **dieselben**
Objekte, die die Episodentabelle einzeln zeigt. Zwei Fassungen, die
auseinanderlaufen könnten, gibt es nicht.

### 13.3 Der Optionsbacktest (ADR 0058)

Eigenständig zu bewerten, weil er andere Regeln hat: **Jede Prämie ist eine
Modellzahl**, und das ADR sagt das an jeder Stelle mit. Bemerkenswert:

- Die Volatilität kommt aus Kerzen **vor** der Entscheidungskerze
  (Look-ahead-Verbot), mit konfiguriertem Aufschlag.
- Das Ergebnis wird als **Band** über mehrere Aufschläge gelesen, nie als
  eine Zahl — *„Kippt eine Aussage innerhalb des Bandes, ist sie nicht
  belastbar"*.
- Jeder Lauf legt eine eigene `measurement_id` an, angehängt, nie
  überschrieben: *„zwei Läufe mit verschiedenem Volatilitätsaufschlag sind
  zwei Befunde und nicht ein korrigierter"*.
- Ein `execution_haircut` macht sichtbar, dass jede Managementregel eine
  zusätzliche Transaktion kostet.

Das ist methodisch sauberer als die meisten veröffentlichten
Optionsbacktests. Die Einschränkung liegt woanders: Der Weg von der
Modellzahl zur gemessenen Zahl führt über `option_quotes` — und deren
Datenqualität ist nicht vollständig gesichert (AUDIT-003-010).

---

## 14. Options Assessment

### 14.1 Die Auswahlkette

```
option_chain          → Verfallstermine                 (1 Anfrage)
select_expiration     → einer, nächst an 35 Tagen, vor dem Earnings-Termin
option_strikes        → gelistete Strikes zu DIESEM Termin (1 Anfrage)
select_strikes        → Moneyness-Band 0,80–0,99, absteigend, max. 12
option_quotes         → Notierung je Strike             (bis 12 Anfragen)
build_options_analysis→ Delta-Band, Mittelwert, Bewertung, Sortierung
                      → höchstens 3 Vorschläge
```

Die Reihenfolge ist begründet und durch einen gemessenen Befund erzwungen:
`reqSecDefOptParams` liefert die **Vereinigung** aller Strikes über alle
Termine; ohne den zweiten Abruf gingen *„am 2026-08-31 bei AAPL sechs von
zwölf Anfragen an Kontrakte, die es zu diesem Termin nicht gibt"*.

### 14.2 Prüfpunkte des Auditauftrags

| Frage | Antwort |
|---|---|
| Quelle | IBKR, `market_data_type: 2` („frozen") |
| Bid / Ask / Mid | alle drei am Vorschlag; **Mid ist die Prämie** (ADR 0048) |
| Last Price | **nicht verwendet** — richtig, ein letzter Kurs kann Stunden alt sein |
| Open Interest | erhoben, fehlt oft (`reqTickers` fordert es nicht an); fehlend erzeugt **keine** Warnung |
| Volume | erhoben, Schwelle 10 |
| Implied Volatility | erhoben, gespeichert, nicht bewertet |
| Delta | **Pflichtfeld** — ohne Delta kein Vorschlag; Band 0,10–0,40 |
| Gamma / Theta / Vega | **nicht erhoben** — für die Auswahlregel nicht gebraucht; ihre Abwesenheit wird nirgends als Vollständigkeit behauptet |
| Expiration / DTE | Kalendertage, Fenster 21–60, Ziel 35, bei Gleichstand der frühere Termin |
| Assignment Risk | über `abs(delta)`, **ausdrücklich als Näherung gekennzeichnet** |
| Liquidität | dreistufig aus Spanne, OI und Volumen — **warnt, schließt nicht aus** → AUDIT-003-005 |
| Spreads | relative Spanne gegen `max_relative_spread` (0,10) |
| Ungewöhnliche Quotes | gekreuzter Markt und Prämie ≤ 0 werden verworfen, mit gezähltem Grund |
| Prämienrechnung | Mittelwert; **ohne Gebühren** → AUDIT-003-012 |
| Kapitalbindung | `strike × 100` — korrekt für einen Cash Secured Put |
| Annualisierung | linear, auf Kalendertagen — begründet und korrekt |
| Earnings | wirkt bei der **Wahl des Verfalls**; `earnings_within_term` am Vorschlag |
| Dividenden | nicht berücksichtigt; für Put-Verkäufe der kleinere Hebel, in ADR 0058 benannt |
| Early Assignment / American Style | **nicht modelliert**; auch nicht behauptet |
| Theoretisch vs. handelbar | die Tilde in der Meldung kennzeichnet die Mid-Annahme; die Liquiditätsstufe erreicht die Meldung nicht → AUDIT-003-005 |

### 14.3 Suggeriert „geeignet für Put-Verkauf" zu viel?

**Teilweise ja** — und zwar an genau zwei Stellen, beide in AUDIT-003-005
und -012 beschrieben: die fehlende Liquiditätsangabe in der Meldung und die
Bruttorendite auf Mid-Basis.

**Die Gegenrechnung gehört dazu**, denn sie ist ungewöhnlich sorgfältig:

- Der Begriff „geeignet" fällt nirgends. Das Datenmodell heißt
  `PutStrategy`, die Meldung schreibt „Put-Verkauf: Strike …".
- Die Andienungswahrscheinlichkeit ist als Näherung gekennzeichnet.
- Der Berichtstermin schließt Verfälle danach aus — eine echte, wirksame
  Risikoregel.
- Ein Vorschlag entsteht **nie** aus einem geschätzten Delta.
- Ein gekreuzter Markt wird verworfen, mit der Begründung, sein Mittelwert
  sei *„ein Kurs, zu dem nie gehandelt wurde — ein erfundener Wert"*.
- Die Put-Zeile erscheint **nur** bei `STRONG_CANDIDATE` und `CANDIDATE`,
  weil sie bei `WATCH` *„eine Handlungsaufforderung wäre, die die Stufe
  gerade nicht ausspricht"*.

Das ist die Haltung, die der Auditauftrag verlangt. Die beiden Lücken sind
Ausnahmen davon, keine Regel.

---

## 15. Security Assessment

| Prüfbereich | Ergebnis |
|---|---|
| Geheimnisse in der Git-Historie | **keine.** `git log --all --name-only` zeigt `.env` in keiner Fassung; `.gitignore` schließt `.env`, `.env.*`, `*.pem`, `*.key`, `secrets/` aus |
| Geheimnisse im Code | **keine.** Ausschließlich `ATA_`-Umgebungsvariablen (ADR 0005) |
| Geheimnisse in Logs | **geschwärzt an der Senke** (ADR 0044). Der Formatter lässt jede fertige Zeile durch `redact_registered` — Meldung, Traceback **und** Ausnahmekette. Die Motivation ist ein gemessener Befund: Der Finnhub-Schlüssel stand ~200-mal je Lauf in httpx' eigenen INFO-Zeilen |
| Geheimnisse in Task-Argumenten | vermieden; `pgpass.conf` statt Kommandozeile, mit ausformulierter Begründung |
| PowerShell-Verlauf | beachtet — Doc 14 nutzt `Read-Host` für das Cloudflare-Token, *„Windows PowerShell 5.1 schreibt jede eingegebene Befehlszeile in eine Verlaufsdatei"* |
| Externe Inhalte als Daten | Research-Kontext ohne Werkzeugrechte; Scores nie aus Freitext; M6 (Prompt-Injection-Test) erledigt |
| Prompt Injection | Werkzeugschema mit `strict: True` und Pflichtfeldern — *„dass eine Bitte befolgt wird, ist keine Zusicherung"* |
| CSP | **ausführlich durchdacht.** `default-src 'none'`, `script-src-attr 'none'`, `worker-src 'none'` (ausdrücklich, weil es über `child-src` auf `script-src` zurückfiele), `frame-ancestors 'none'`, `base-uri 'none'`, `form-action 'none'` |
| `unsafe-inline` | begründet (Next legt sieben Inline-Skripte je Seite ab) und **durch zwei bewachte Senken abgesichert**: kein `dangerouslySetInnerHTML`, kein `innerHTML`, konstante URL-Präfixe. `sicherheitsheader.test.ts` bricht, wenn eine davon geöffnet wird |
| XSS | React maskiert jeden Berichtstext, auch den vom Sprachmodell erzeugten |
| Injection (SQL) | SQLAlchemy mit gebundenen Parametern durchgängig; keine Zeichenkettenverkettung gefunden |
| Transportsicherheit | HSTS, `nosniff`, `no-referrer`, COOP/CORP — **im Repository versioniert**, nicht in der Anbieterkonsole |
| Zugriffsschutz außen | Cloudflare Access auf genau eine Person; Vorschau-Adressen abgeschaltet und bei **jedem** Upload erneut erzwungen, mit Kanarienvogel-Meldung nach Telegram |
| Zero-Knowledge-Export | PBKDF2 mit 600.000 Runden, jede Datei opak benannt, kein Symbol im Klartext, `Cache-Control: no-store` für `/data/*`, Prüfsummenkontrolle im Browser. Sechs Frontend-Tests belegen den Vertrag mit der Python-Hälfte |
| Notausschalter | dokumentierte Notfallkarte für sechs Lagen (Token verloren, Passphrase verraten, Verdacht auf Datenabfluss …) |
| CORS | keine Middleware — statischer Export gleicher Herkunft, richtig |
| Rate Limiting (eigene API) | keines. Ohne Exposition unkritisch (ADR 0049) |
| Debug-Endpunkte | keine; `/docs` und `/openapi.json` offen → **AUDIT-003-016** |
| Abhängigkeiten | `.github/workflows/audit.yml` wöchentlich, nicht blockierend; ein bewusst offener `postcss`-Punkt mit ausformulierter Begründung (Bauzeit, eigenes CSS) |

### Angriffsfläche Browser → Cloudflare → Worker → Datenquelle

Der Weg nach außen ist **einseitig**: Der Server bekommt keinen eingehenden
Port. Er schreibt einen verschlüsselten Datenbaum und lädt ihn ausgehend
hoch (ADR 0060). Der Worker liefert Chiffrat aus; entschlüsselt wird
ausschließlich im Browser mit einer Passphrase, die der Anbieter nie sieht.
Zwischen Cloudflare und der Datenquelle besteht **keine Verbindung** — es
gibt nichts, was ein kompromittierter Worker nach innen erreichen könnte.

Die verbleibende Fläche ist ehrlich benannt: Wer beim Anbieter schreiben
darf, ersetzt die `_headers` mit demselben Upload — *„Dagegen steht die
Zugriffsregel, die außerhalb des Deployments liegt, nicht die CSP."*

**Ein latentes Risiko steht angeschrieben:** Sobald Quellen-URLs aus
Berichten klickbar werden — *„der naheliegende nächste Schritt bei
Quellenbindung"* —, fällt eine der beiden Bedingungen, unter denen
`unsafe-inline` vertretbar ist. Der Test bricht dann. Das ist ein Hinweis
an die Zukunft, kein heutiger Befund.

---

## 16. Dashboard Assessment

| Prüfpunkt | Ergebnis |
|---|---|
| Datenkorrektheit | Der Export liest dieselben Use Cases wie die API; Schwellen und Kandidatenregel kommen **aus derselben Konfiguration wie der Lauf** — *„Eine Oberfläche, die anders einstuft als der Lauf, der die Zahlen erzeugt hat, wäre schlimmer als gar keine"* |
| Konsistenz mit dem Backend | keine zweite Rechnung gefunden; `laufAdresse` und die Meldungsseite halten dieselbe URL-Form in einem Test fest |
| Integrität | jede Datei trägt eine Prüfsumme; ein verändertes Byte, ein fremder Pfad oder eine falsche Passphrase brechen — je ein Test |
| Stale Data | Der Baum ist unveränderlich, ein neuer Stand ist ein neuer Baum. Ein **expliziter** Erzeugungszeitpunkt fehlt; das Datum des jüngsten Laufs dient als Anzeiger |
| Fehlerzustände | `DatenbaumFehler` mit sprechenden Meldungen je Fall (fehlende Datei, falsche Passphrase, fremder Pfad, beschädigte Datei) |
| Race Conditions | Exportsperre als Dateilock mit einer Stunde Verfall; *„eine Sperre, die niemand mehr aufhebt, wäre schlimmer als keine"* |
| Caching | `/data/* → Cache-Control: no-store`, begründet: auf geteilten Geräten bliebe sonst Chiffrat liegen |
| Timezones | Zeitpunkte kommen als ISO-Zeitstempel aus dem Backend |
| Darstellung von Scores | Die Datenlage kommt mit; ob **Abdeckung und Konfidenz** sichtbar sind, ist am laufenden Dashboard zu prüfen → relevant für AUDIT-003-004 |
| Darstellung der Optionen | Die Liquiditätswarnungen stehen im Berichtsdokument; ob sie in der Listenansicht erscheinen, ist nicht verifiziert |
| Mobile | nicht verifizierbar ohne laufende Instanz |
| Performance | Der Export baute bis ADR 0068 jeden Lauf neu; die Anzeige selbst lädt je Stand und Pfad einmal |

### Vermittelt das Dashboard ungedeckte Aussagen?

**Nicht verifizierbar ohne laufende Instanz.** Aus dem Quelltext lässt sich
sagen: Der Export überträgt die vorhandenen Lücken-, Status- und
Begründungsfelder, erfindet nichts und rechnet nichts neu. Die beiden
False-Confidence-Befunde dieses Audits (004 und 005) betreffen Werte, die
**vor** dem Export entstehen — was der Score nicht kennzeichnet, kann das
Dashboard nicht kennzeichnen.

> **Empfehlung für die Abnahme von Stufe J bzw. des externen Dashboards:**
> gezielt prüfen, ob die Score-Abdeckung, die Konfidenzstufe und die
> Liquiditätsstufe in den Listenansichten sichtbar sind — nicht nur im
> aufgeklappten Berichtsdokument.

---

## 17. Reliability & Resilience

Die im Auditauftrag genannten Szenarien, durchgespielt am Code:

| Szenario | Verhalten | Bewertung |
|---|---|---|
| API nicht erreichbar | Provider-Fehler → Modul degradiert mit benanntem Grund; Aktie bleibt im Lauf | **gut** |
| HTTP 500 | wie oben, **ohne Wiederholversuch** | **schwach** → AUDIT-003-008 |
| HTTP 429 | wie oben; vorbeugend gedrosselt, **kein Retry** | **schwach** → AUDIT-003-008 |
| Leere Antwort | eigener Zweig je Adapter („keine Abdeckung" ≠ „kein Abruf") | **gut** |
| Syntaktisch korrekt, inhaltlich falsch | für Finnhub, EDGAR und Optionen geprüft; **für Bars nicht** | **Lücke** → AUDIT-003-001 |
| Einzelne Aktie fehlt | `_PreparedError`, Zeile in `analysis_run_errors`, Lauf läuft weiter | **sehr gut** |
| KI-API nicht verfügbar | `UNAVAILABLE` mit Grund, Fallback auf die andere Modellstufe bei technischem Versagen; Komponenten entfallen | **gut**, aber siehe AUDIT-003-004 |
| Telegram nicht verfügbar | Lauf läuft weiter; Überfälligkeitsmeldung wird wiederholt, **Ergebnismeldung nicht** | **teils** → AUDIT-003-007 |
| Optionsdaten fehlen | `INSUFFICIENT_DATA` mit gezähltem Grund; Komponente entfällt | **sehr gut** |
| Dashboard/Cloudflare nicht erreichbar | drei getrennte Ausgänge mit drei verschiedenen Meldungen; Lauf bleibt erfolgreich | **sehr gut** |
| Netzunterbrechung im Backfill | Einzelausfälle toleriert; fällt **alles** aus → `MarketDataProviderError`, kein Analyse-Lauf | **sehr gut** |
| Serverneustart während des Laufs | Advisory Lock fällt mit der Verbindung; Lauf gilt als nicht erledigt, nächster Start wiederholt | **sehr gut** |
| Prozessabsturz | wie oben; *„Eine hängende Sperre nach einem Absturz gibt es nicht"* | **sehr gut** |
| Timeout | je Anbieter konfiguriert; `wrangler` mit 900 s; **TWS-Aufrufe nicht durchgängig** → hängender Lauf möglich | **teils** → AUDIT-003-014 |
| Partieller Lauf | `minimum_completion_ratio` 0,9; darunter gilt der Lauf als gescheitert und wird wiederholt | **sehr gut** |
| Doppelter Lauf | eindeutiger Schlüssel `(session_date, candle_close)`; zweiter Aufruf endet mit „Bereits erledigt" | **sehr gut** |
| Zwei Läufe gleichzeitig | `pg_try_advisory_lock`, nicht blockierend, auf eigener Verbindung | **sehr gut** |
| Datenbankfehler | `_open_database` gibt Rückgabewert 2; Unit of Work rollt zurück | **gut** |
| Beschädigte Cache-Dateien | kein Dateicache vorhanden | entfällt |

### Idempotenz und Wiederholbarkeit

| Frage | Antwort |
|---|---|
| Entstehen Duplikate? | **nein** — Bars über `(symbol, start)`, Läufe über `(session_date, candle_close)` |
| Werden historische Ergebnisse überschrieben? | **nein** — append-only, Unveränderlichkeit ist Architekturprinzip |
| Doppelte Telegram-Nachrichten? | **nein** — ein zweiter Start rechnet nicht und meldet nicht |
| Unnötige API-Kosten? | **nein** — ein erledigter Lauf fasst die TWS *„gar nicht mehr an"* |
| Können Scores unterschiedlich ausfallen? | ja, bei einem **echten** zweiten Lauf (andere Marktdaten); nicht bei einer Wiederholung desselben Laufs |
| Können KI-Ergebnisse abweichen? | `temperature=0` und `strict`-Schema begrenzen die Streuung; Determinismus ist damit nicht zugesichert. Modell und Promptversion stehen am Ergebnis |
| Kann ein gescheiterter Lauf fortgesetzt werden? | **ja** — der Backfill ist idempotent und abbrechbar, der Versuchszähler steigt, `is_done` bleibt falsch |

**Die Idempotenz ist der am besten durchdachte Teil des Systems.** Sie ist
an drei Stellen unabhängig voneinander abgesichert (Schlüssel, Lock,
Datengate), und jede der drei hat einen Docstring, der erklärt, welchen Fall
sie fängt und welchen nicht.

---

## 18. Test Coverage

### 18.1 Lage

2.485 Backend-Tests in 99 Dateien, 142 Frontend-Tests in 25 Dateien, alles
grün. Alle fünf von Doc 10 §16 geforderten Arten sind vorhanden:

| Art | Ort | Bewertung |
|---|---|---|
| Unit | `tests/unit/` | sehr gut; die Domain-Tests prüfen Grenzwerte und Gleichheitsfälle einzeln |
| Integration | `tests/integration/` (203) | gegen echtes PostgreSQL, inklusive Migrationen |
| Contract | eingefrorene Antworten für EDGAR, Finnhub ×2, IBKR-Kette | mit Gegenprobe belegt (A2-M7: ein umbenanntes Feld bricht genau die vier neuen Tests) |
| Golden Master | `tests/golden/` | 15 Tests, ohne Netz und Datenbank; erzeugte **und** reale Bars |
| End-to-End | `tests/integration/test_full_run.py` | vorhanden |
| Architektur | `tests/architecture/` | Schichtgrenzen erzwungen |

Besonders hervorzuheben ist die Qualität einzelner Testzusagen:
`sicherheitsheader.test.ts` bricht mit einer **Begründung**, wenn jemand
eine der beiden Senken öffnet, unter denen `unsafe-inline` vertretbar ist.
Ein Test, der erklärt, warum er bricht, ist selten.

### 18.2 Die wichtigsten fehlenden Tests

Nach Nutzen geordnet:

| # | Fehlender Test | Deckt Befund | Aufwand |
|---|---|---|---|
| 1 | **Sprung in der Bar-Reihe** (Split-Szenario): zwei Preisniveaus in einer Reihe müssen zu einem Fehler oder einer Warnung führen | AUDIT-003-001 | S |
| 2 | **Empfehlung bei niedriger Abdeckung**: `LOW_COVERAGE` + fehlendes Assessment darf kein `STRONG_CANDIDATE` ergeben | AUDIT-003-004 | XS |
| 3 | **`EARNINGS_EXCLUDED` wirkt**: ein Kandidat mit nahem Termin darf nicht ungekennzeichnet in die Meldung gelangen | AUDIT-003-003 | XS |
| 4 | **Alle Vorschläge `POOR`**: der erste ist dann `POOR`, und die Meldung muss das zeigen | AUDIT-003-005 | XS |
| 5 | **Konfigurationsprüfsumme je Scoring-Version** | AUDIT-003-009 | S |
| 6 | **Gescheiterte Ergebnismeldung** wird vermerkt und nachgeholt | AUDIT-003-007 | S |
| 7 | **Retry bei 429/5xx** in den Adaptern | AUDIT-003-008 | S |
| 8 | **Golden Master über die Score-Kette** (Scoring, Empfehlung, Optionsauswahl über eingefrorene Eingaben) | AUDIT-003-009 | M |
| 9 | **DST-Übergangstag** in der Kerzenaggregation — geprüft wurde der Code, ein expliziter Testfall für den März-/November-Sonntag wurde nicht gefunden | — | S |
| 10 | **Hängender Lauf**: Verhalten bei gehaltener Sperre über das Startfenster hinaus | AUDIT-003-014 | S |

Die Punkte 2 bis 4 kosten jeweils unter einer Stunde und sichern drei der
fünf wichtigsten Befunde ab.

### 18.3 Erkennen die Tests fachlich relevante Fehler?

**Überwiegend ja**, und es gibt einen Beleg dafür: Die Gegenprobe zu A2-M7
(ein umbenanntes Feld in der eingefrorenen Finnhub-Antwort bricht genau die
vier neuen Tests und keinen bestehenden) ist der Nachweis, dass die
Contract-Tests tatsächlich binden.

Die Lücke liegt dort, wo die Befunde liegen: Die Tests prüfen durchgängig,
**dass etwas berechnet wird**, und nur selten, **dass es wirkt**. Kein Test
fragt heute „darf dieser Kandidat so gemeldet werden". Die Punkte 2 bis 4
oben schließen genau diese Art Lücke.

---

## 19. Observability

Die Fragen des Auditauftrags (§25), beantwortet für den heutigen Zustand:

| Frage | Heute beantwortbar? | Woraus |
|---|---|---|
| Hat der Lauf stattgefunden? | **ja**, per Abfrage | `dispatcher_runs.status` |
| Wann begann er? | **ja** | `dispatcher_runs.last_attempt_at` |
| Wann endete er? | **ja** | `dispatcher_runs.finished_at` |
| Wie viele Aktien? | **ja** | `analysis_runs.number_of_stocks` (nach Wiederholsperre) |
| Wie viele Kandidaten? | **ja** | `analysis_runs.candidates_found` |
| Welche APIs waren erfolgreich? | **nein** | nur im Protokoll — und das existiert nicht |
| Welche sind fehlgeschlagen? | **teilweise** | der *Effekt* steht am Ergebnis (`reason: provider_error`), nicht der Vorgang |
| Welche Aktien hatten Datenfehler? | **ja** | `analysis_run_errors` |
| Welche Scores wurden berechnet? | **ja** | `screening_results`, mit Version |
| Welche Optionen gefunden? | **ja** | `option_quotes`, bewertete Vorschläge am Ergebnis |
| Welche Schritte übersprungen? | **teilweise** | Wiederholsperre nur als Logzeile → unsichtbar; die Sperre ist aber **rekonstruierbar** (ADR 0054, Punkt 6) |
| Warum wurde eine Aktie ausgeschlossen? | **ja** | `screening_results.reason`, inklusive `gate:`-Gründen |
| Gab es Warnungen? | **nein** | nur im Protokoll |
| Wie viele Retries? | **teilweise** | `dispatcher_runs.attempts` je Lauf; innerhalb eines Laufs gibt es keine |

**Die Datenbank ist ein hervorragendes Protokoll — für Ergebnisse.** Sie
kennt keine Vorgänge. Genau dafür ist die Protokolldatei gebaut, und genau
sie ist ausgeschaltet (AUDIT-003-013). Mit einer Zeile in den
Task-Argumenten verschieben sich fünf der obigen „nein" und „teilweise" auf
„ja":

Jede gemessene Zeile trägt `event`, `duration_ms` und `ausgang`. Gemessen
werden die drei Laufphasen, `meldung` und `dashboard_export` getrennt, je
Aktie die `kerzenserie`, je Kandidat `backtest`, `fundamentaldaten`,
`analystenvoten`, `earnings_termin` und `optionsanalyse`, dazu `backfill`
und `backfill_symbol` — letzteres mit `verschlafene_sekunden` neben
`duration_ms`, was das Warten an der eigenen Drossel vom Warten an der
Leitung trennt. Das ist genau die Zerlegung, nach der der Auditauftrag
fragt.

`scripts/laufzeiten.py` liefert die **grobe** Zerlegung rückwirkend für
jeden Tag seit dem 2026-09-01, ohne dass irgendetwas eingeschaltet sein
müsste — die drei Zeitstempel stehen ohnehin in der Datenbank. Das ist eine
kluge Konstruktion.

---

## 20. Performance & Cost

### 20.1 Laufzeit

| Abschnitt | Gemessen | Anmerkung |
|---|---|---|
| Backfill + Datengate | **35,2 min**, konstant | davon rund 34 min reines `time.sleep` — IBKRs Ratengrenze, nicht beschleunigbar |
| Analyse (Phasen 1–3) | ~7 s je Aktie | |
| Meldung + Export | **42,7 min** am 2026-09-18, **wachsend** | ADR 0068 gebaut, nicht ausgerollt → AUDIT-003-021 |
| **Gesamt** | **~103 min** (vorher 53) | Startfenster 17:30–21:30 |

ADR 0069 (Verzahnung) ist die richtige Antwort auf den ersten Posten: Der
Backfill wird nicht schneller — *„er darf es nicht, IBKR begrenzt die
Rate"* —, beschleunigt wird, was währenddessen stillstand. Das ist eine
Optimierung, die die fachliche Korrektheit nicht antastet: Die Analyse
wartet je Aktie, bis deren Bars abgelegt sind (`Bereitschaft`), und das
Datengate greift früher statt später.

### 20.2 Anfragen je Aktie

| Vorgang | Anfragen | Bemerkung |
|---|---|---|
| Backfill | 1 je Symbol, Abstand 11 s | ~192 je Lauf |
| Optionskette (nur Kandidaten) | 1 + 1 + bis zu 12 | bis zu 14 je Kandidat |
| Absicherungs-Strike | +1, nur wo es etwas abzusichern gibt | bewusst gezielt statt das Band zu verbreitern |
| Finnhub | 2 je Kandidat (Earnings, Voten) | 60/min-Grenze, gedrosselt |
| EDGAR | mehrere je Kandidat | gedrosselt |
| Anthropic | 1 je Kandidat (Technical Agent) | Research steht auf `none` |

**Redundante Anfragen wurden gesucht und nicht gefunden.** Im Gegenteil: Der
zweite Strike-Abruf existiert genau deshalb, weil ohne ihn *„sechs von zwölf
Anfragen an Kontrakte gingen, die es zu diesem Termin nicht gibt"*.

Eine kleine Unwucht: Für Kandidaten mit `EARNINGS_EXCLUDED` wird die
Optionskette abgerufen, obwohl `select_expiration` danach in aller Regel
keinen zulässigen Verfall findet. Das kostet **eine** Anfrage je solchem
Kandidaten — vernachlässigbar, aber vermeidbar, sobald AUDIT-003-003
entschieden ist.

### 20.3 Kosten

| Posten | Kosten | Grundlage |
|---|---|---|
| Technical Agent | **0,0056 USD je Kandidat** | gemessen 2026-09-01 (Haiku 4.5, ~3.500 Eingabe-/420 Ausgabe-Token) |
| Research Agent | ~0,52–0,58 USD je Kandidat | **abgeschaltet** (ADR 0051) |
| Finnhub, EDGAR, IBKR-Optionen | 0 USD | Abos bzw. kostenfrei |

Bei 36 Kandidaten rund **20 Cent je Tageslauf**. Die Wiederholsperre
(ADR 0054) senkt das weiter — sie war ausdrücklich auch eine
Kostenentscheidung.

Die Kostenschätzung wird je Anfrage protokolliert, aber **nicht
persistiert** (`provider.py`: *„ein persistierter Kostenwert braucht eine
eigene Entscheidung"*). Mit ausgeschaltetem Protokoll (AUDIT-003-013) ist
sie damit heute nirgends nachlesbar. Kein eigener Befund — eine weitere
Folge desselben fehlenden Schalters.

### 20.4 Optimierungsmöglichkeiten

| Maßnahme | Ertrag | Risiko für die Korrektheit |
|---|---|---|
| ADR 0068 ausrollen | −40 min je Lauf, wachsend | keines — ändert nur, was neu gerechnet wird |
| Optionskette für `EARNINGS_EXCLUDED` auslassen | wenige Anfragen | keines, sobald 003 entschieden ist |
| Backfill beschleunigen | **keiner** | gemessen: 34 von 35 min sind Drossel |
| Mehr Nebenläufigkeit bei den Agenten | gering | Pools sind bereits getrennt (ADR 0037) |

---

## 21. Technical Debt

Getrennt nach den drei vom Auditauftrag verlangten Kategorien.

### Echte Risiken

| Punkt | Befund |
|---|---|
| Keine Plausibilitätsschranke auf Kursdaten | AUDIT-003-001 |
| Versionierung der Konfiguration per Handschlag | AUDIT-003-009 |
| Golden Master endet vor Scoring und Optionen | AUDIT-003-009 |
| Kein Retry auf transiente HTTP-Fehler | AUDIT-003-008 |

### Normale technische Kompromisse

| Punkt | Bewertung |
|---|---|
| `cli.py` mit 5.055 Zeilen | AUDIT-003-019 — Presentation-Schicht, keine fachliche Wirkung |
| `run_analysis.py` mit 1.166 Zeilen | an der Obergrenze, aber klar gegliedert und durchgängig kommentiert |
| `repositories.py` mit 2.195 Zeilen | Ein Repository je Aggregat in einer Datei; vertretbar |
| Wochentagsnäherung im Earnings-Kalender | **gemessen** begründet (ADR 0030): `liquidHours` reicht vier Tage voraus, gebraucht werden elf. Kein Kompromiss aus Bequemlichkeit |
| Keine Vergleichsgruppe in der Fundamentalanalyse | bewusst offen (ADR 0032), als Lücke ausgewiesen statt geschätzt |
| Manuelle Migrationen | bewusst (Doc 13) — richtig für diesen Betrieb |

### Kosmetisch

| Punkt | Bewertung |
|---|---|
| Tote Modellprofile | AUDIT-003-017 — Low, weil irreführend, nicht weil unsauber |
| Doc 13 Backup-Abschnitt | AUDIT-003-018 |
| Deutsche und englische Bezeichner gemischt | durchgängiges Muster (Domäne deutsch, Ports englisch); **keine Kritik** — es ist konsistent und begründet |

### Was ausdrücklich **keine** Schuld ist

Drei Dinge, die in einem Standard-Review als Mangel erschienen und hier
keiner sind:

1. **Die außergewöhnlich langen Docstrings.** Sie tragen die Begründung der
   fachlichen Entscheidung am Ort ihrer Wirkung. Mehrere Befunde dieses
   Audits ließen sich **nur** deshalb präzise formulieren, weil der Code
   sagt, was er zusichern will — und man die Zusage dann prüfen kann.
2. **Magic Numbers im Code statt in der Konfiguration**
   (`RSI_OVERSOLD_LEVEL`, `MAX_CROSSING_SIGNAL_AGE_CANDLES`). Begründet:
   *„Wäre er verstellbar, könnten zwei Läufe dieselbe Regelversion tragen
   und dennoch Verschiedenes gerechnet haben."* Das ist der Mechanismus, der
   bei den Scoring-Schwellen fehlt (AUDIT-003-009).
3. **Die Zahl der ADRs (69).** Sie ist die Ursache dafür, dass dieses Audit
   überhaupt Abweichungen benennen kann.

---

## 22. Production Operations & Scheduling

### 22.1 Current Windows Scheduled Tasks

Nach Angabe des Projektinhabers **genau eine** geplante Aufgabe:

```text
C:\Users\Administrator\Documents\TradingViewAnalyzer\backend\.venv\Scripts\python.exe
  -m ai_trading_analyst.cli dispatch
     --provider ibkr --earnings-provider finnhub --fundamentals-provider edgar
     --ratings-provider finnhub --options-provider ibkr
     --technical-agent-provider anthropic --research-provider none
     --notification-channel telegram --telegram-chat-id <id>
     --dashboard-export cloudflare
```

Der Argumentstring deckt sich mit Doc 14, Abschnitt „Betriebszustand" —
alle sechs Analyseanbieter sind gesetzt, Research bewusst auf `none`
(ADR 0051). **Er enthält kein Geheimnis**, richtig so. Auffällig ist nur,
was fehlt: `--log-file` (AUDIT-003-013).

> **Zu prüfen auf dem Server**, weil das Repository es nicht weiß:
> ```powershell
> Get-ScheduledTask | Where-Object { $_.TaskName -like "*Trading*" -or $_.TaskName -like "*ATA*" } |
>   Get-ScheduledTaskInfo | Format-Table TaskName, LastRunTime, LastTaskResult, NextRunTime
> ```

### 22.2 Required Operational Tasks

| Aufgabe | Vorhanden? | Im Code vorgesehen? | Notwendig? | Frequenz | Abhängigkeiten | Risiko bei Nichtausführung |
|---|---|---|---|---|---|---|
| Täglicher Produktionslauf | **ja** | ja (ADR 0019) | **zwingend** | Mo–Fr 17:30, alle 15 min für 4 h | TWS, PostgreSQL, fünf externe Dienste | kein Screening |
| Datenbanksicherung | **nein** | ja (`scripts/sicherung.ps1`) | **zwingend** | täglich 23:45 | PostgreSQL, `pgpass.conf` | **Totalverlust** → AUDIT-003-002 |
| Kopie außer Haus | **nein** | nein | **zwingend** | täglich 00:15 | Sicherung | Serververlust trotz Sicherung → AUDIT-003-006 |
| Wächter / Laufkontrolle | **nein** | nein | **betrieblich sinnvoll** | täglich 23:15 | PostgreSQL, Telegram | stille Ausfälle → AUDIT-003-014 |
| Restore-Zählprobe | **nein** | ja (`sicherung-probe.ps1`) | **betrieblich sinnvoll** | quartalsweise, von Hand | Sicherung | ungeprüfte Sicherung |
| Integritätsprüfung Bestand | **nein** | nein | **betrieblich sinnvoll** | monatlich | PostgreSQL | Split- und Lückenbefunde bleiben liegen → AUDIT-003-001 |
| Signal-Backtest | nein | ja, als Werkzeug | **nicht erforderlich** | — | — | keines — läuft je Kandidat im Tageslauf (ADR 0038) |
| Optionsbacktest | nein | ja (ADR 0058) | **optional** | bei Bedarf / quartalsweise | Kerzenbestand | keines für den Betrieb |
| Retention / Datenbereinigung | nein | **bewusst nicht** | **nicht erforderlich** | — | — | keines; Archivgrenze ist vertagt (ADR 0060/0061/0067) |
| Cache-Bereinigung | nein | — | **nicht erforderlich** | — | — | es gibt keinen Dateicache |
| Log-Rotation | entfällt | ja (`RotatingFileHandler`) | **nicht als Task** | — | — | keines — aber das Protokoll ist aus |
| Alembic-Migration | nein | ja, **von Hand** (Doc 13) | **nicht als Task** | bei Aktualisierung | — | keines; automatisch wäre hier ein Risiko |
| Watchlist-Pflege | nein | Dateien im Repository | **nicht als Task** | bei Bedarf über PR | — | Watchliste veraltet, fällt auf |
| Anbieterpflege (Preise, Modelle, Token) | **ja, als Prozess** | Doc 14 „Pflege" | **betrieblich sinnvoll** | quartalsweise (2026-12-01) | — | veraltete Preislisten (R8) |
| Abhängigkeitsprüfung | **ja** (GitHub Action) | `audit.yml`, wöchentlich | erledigt | wöchentlich | GitHub | — |
| Dashboard-Dienst (Stufe J) | **nein** | ja (Doc 14) | **optional** | Systemstart | — | keine LAN-Anzeige; extern gedeckt |
| TWS-Start nach Neustart | Handarbeit | ADR 0018, bewusst manuell | **zwingend manuell** | nach Neustart | — | **alle Läufe fallen aus** |

### 22.3 Backup Assessment

Das geplante Verfahren ist **inhaltlich gut und nicht eingerichtet**.
Bewertet wird hier die Qualität dessen, was eingerichtet würde:

| Merkmal | Stand | Bewertung |
|---|---|---|
| Frequenz | täglich | angemessen (Ziel: max. ein Handelstag Verlust) |
| Ziel | `D:\backups\ata`, derselbe Rechner | **unzureichend** → AUDIT-003-006 |
| Retention | 14 Tage rollierend | gut begründet |
| Versionierung | ein Dump je Tag, Datumsstempel | ausreichend |
| Verschlüsselung | keine | lokal vertretbar, extern Pflicht |
| Zugriffsschutz | NTFS des Benutzerkontos | Ransomware erreicht beides |
| Integritätsprüfung | Größe **und** `pg_restore --list` | **vorbildlich** |
| Aufräumreihenfolge | erst sichern und prüfen, dann löschen | **vorbildlich** |
| Rückgabewert | 2 bei Fehlschlag | richtig — die Spalte „Letztes Ausführungsergebnis" ist das einzige Signal ohne Zutun |
| Wiederherstellbarkeit | Wegwerfdatenbank, Produktivname fest ausgeschlossen | **vorbildlich** |
| Restore-Test | vorgesehen, **nie durchgeführt** | A2-M4 offen |

### Datenklassifikation

| Daten | Speicherort | Aus Quelle wiederherstellbar? | Backup nötig? | Retention |
|---|---|---|---|---|
| `option_quotes` | PostgreSQL | **nein — endgültig** (ADR 0058) | **ja, höchste Priorität** | unbegrenzt |
| `analysis_runs`, `screening_results`, `stock_reports`, `signal_events`, `technical_zones` | PostgreSQL | **nein** (unveränderliche Momentaufnahmen) | **ja** | unbegrenzt |
| `backtest_results`, `backtest_episodes` | PostgreSQL | aus Bars neu rechenbar, nur mit derselben Regelfassung | ja | unbegrenzt |
| `fundamental_metrics`, `research_citations` | PostgreSQL | teilweise (EDGAR ja, Momentaufnahme nein) | **ja** | unbegrenzt |
| `intraday_bars`, jüngstes Jahr | PostgreSQL | ja, ~35 min | ja | unbegrenzt |
| `intraday_bars`, Tiefenhistorie | PostgreSQL | ja, **elfstündiger Wochenendlauf** | **ja** | unbegrenzt |
| `dispatcher_runs` | PostgreSQL | nein | ja | unbegrenzt |
| `.env` (`ATA_*`) | Projektwurzel, **nicht in Git** | teils; **`ATA_DASHBOARD_EXPORT_PASSPHRASE` nicht** | **ja, getrennt** (Passwortmanager) | bis zur Rotation |
| `pgpass.conf` | `%APPDATA%` | ja (Passwort neu setzen) | nein, aber dokumentieren | — |
| Quellcode, Konfiguration, Watchlisten, Skripte | Git / GitHub | **ja, vollständig** | nein | — |
| `var/dashboard` | Dateisystem | ja (`publish --full`) | nein | — |
| `.venv`, `node_modules`, `frontend/out` | Dateisystem | ja (Lock-Dateien) | nein | — |
| `var/logs/tageslauf.log` | Dateisystem | nein | derzeit gegenstandslos | 5 × 20 MB |
| Dumps selbst | `D:\backups\ata` | — | **ja, außer Haus** | 14 d lokal, länger extern |

### 22.4 Backtest Scheduling Assessment

**Empfehlung: kein Scheduled Task, weder für den Signal- noch für den
Optionsbacktest.** Begründet aus der Architektur, nicht aus einer
allgemeinen Regel:

| Frage | Befund |
|---|---|
| Separater Mechanismus? | zwei: `cli backtest` und `cli options-backtest` |
| Muss er regelmäßig laufen? | **nein** — der Signal-Backtest läuft **je Kandidat im Tageslauf** (ADR 0038) und füllt Berichtspunkt 5 |
| Analysewerkzeug oder Produktionsschritt? | `cli backtest` rechnet dasselbe über die ganze Watchliste, mit leerer `analysis_run_id`. Täglich ausgeführt bliebe das Ergebnis über Wochen nahezu gleich — die Historie wächst um eine Kerze je Tag |
| Vorher nötige Daten | gefüllter `intraday_bars`-Bestand, dieselbe Quelle wie der Produktionslauf |
| Kosten / API-Kontingent | **keine** — beide rechnen auf `source: stored`, ohne TWS, ohne Finnhub, ohne Anthropic |
| Laufzeit | nicht dokumentiert; die erste Vollmessung lief über 192 Aktien und 15.878 Episoden — Minuten bis Zehnminuten, CPU- und DB-gebunden |
| Race Conditions? | **keine.** Beide schreiben ausschließlich anfügend, der Optionsbacktest je Lauf unter eigener `measurement_id` |
| Parallel zum Produktionslauf? | technisch ja, **betrieblich nein** — der Tageslauf dauert 103 min und läuft im Fenster der Nachholfrist |
| Grund für täglich/wöchentlich/monatlich? | **keiner.** ADR 0058 legt das Ergebnis ausdrücklich als Band über mehrere Aufschläge an; die zentrale Eingangsgröße ist gesetzt, nicht gemessen |

Der richtige Anlass sind drei Ereignisse: eine Regeländerung, eine neue
Kalibrierung aus `options-calibrate`, der quartalsweise Pflegetermin. Von
Hand, außerhalb des Dispatch-Fensters.

### 22.5 Maintenance Tasks

Der quartalsweise Pflegeturnus (Doc 14, nächster Termin **2026-12-01**)
deckt: gemessene Schwellen, LLM-Preislisten, Modell-Identifier, gemeldete
Schwachstellen, Restore-Zählprobe. Zu ergänzen wären:

- **Cloudflare-Token-Ablauf** — meldet sich zwar von selbst („der Tag danach
  kommt die Meldung"), gehört aber auf die Liste.
- **Laufzeitmessung** mit `scripts/laufzeiten.py` — die Streuung über
  mehrere Wochen ist aussagekräftiger als ein Einzelwert.
- **Versionskopplung der Schwellen** prüfen, solange AUDIT-003-009 offen ist.

### 22.6 Job Dependencies

```text
  ┌──────────────────────────────────────────────────────────────┐
  │  Mo–Fr 17:30, alle 15 min (4 h)   — Tageslauf (dispatch)     │
  │  Advisory Lock: höchstens einer, egal wie oft gestartet      │
  │                                                              │
  │   Backfill ──┬── Datengate (nach 5 Symbolen)                 │
  │              └──► Analyse Phase 1 / 1b / 2 / 3               │
  │                          │                                   │
  │              ┌───────────┴───────────┐                       │
  │              ▼                       ▼                       │
  │        Telegram-Meldung      Dashboard-Export                │
  │        (isoliert)            (isoliert, eigene Sperre)       │
  └──────────────────────────────────────────────────────────────┘
                              ╎ keine Abhängigkeit
  ┌───────────────────────────▼──────────────────────────────────┐
  │  täglich 23:45 — Sicherungskette                             │
  │   pg_dump ──► Lesbarkeitsprüfung ──► Kopie außer Haus         │
  │                                  └──► alte Stände entfernen   │
  └──────────────────────────────────────────────────────────────┘

  täglich 23:15   Wächter: lief heute ein Lauf? griff die Sicherung?
  monatlich       Integritätsprüfung des Bar-Bestands
  quartalsweise   Zählprobe, Pflege, Backtests (von Hand)
```

**Abhängig sein dürfen** nur Schritte, bei denen der zweite ohne das
Ergebnis des ersten falsch wäre: Analyse nach Bars, Meldung nach Ergebnis,
Kopie nach geprüftem Dump, Löschen nach erfolgreicher Sicherung.

**Unabhängig bleiben müssen** — und das ist die wichtigere Hälfte: Die
**Sicherung** hängt nicht am Lauf (sonst sichert ein schlechter Tag gar
nicht). Der **Wächter** hängt nicht am Lauf (sonst schweigt er genau dann,
wenn er reden soll).

Ein Pfeil „Backup → Daily Run" wäre hier **falsch**: Er machte die Analyse
vom Gelingen der Sicherung abhängig, und ein voller Sicherungsordner ließe
dann das Screening ausfallen.

### 22.7 Failure & Recovery

**Was passiert bei einem Absturz während der Ausführung?** Sauber gelöst.
Der Advisory Lock hängt an der Datenbankverbindung: *„Bricht der Prozess
hart ab, schließt die Verbindung, und PostgreSQL gibt die Sperre von selbst
frei. Eine hängende Sperre nach einem Absturz gibt es nicht."* Der
Laufeintrag bleibt auf `running`/`failed`, `is_done` bleibt falsch, der
nächste Start in 15 Minuten zählt den Versuch hoch und rechnet neu. Kein
Dateilock, kein PID-File, nichts aufzuräumen.

**Was passiert, wenn der nächste Start den vorigen noch laufend antrifft?**
Zwei Ebenen, die nicht zu verwechseln sind: Der eindeutige Schlüssel
`(session_date, candle_close)` sorgt dafür, dass ein *erledigter* Lauf
erledigt bleibt; der Advisory Lock verhindert *gleichzeitige* Arbeit. Der
zweite Start endet mit `IN_PROGRESS` und Rückgabewert **0**.

**Die Lücke:** Ein **hängender** (nicht abstürzender) Lauf ist unsichtbar.
Er hält die Sperre, alle weiteren Starts enden mit `IN_PROGRESS`, und weil
`_report_overdue` **innerhalb** der Sperre läuft, geht auch die
Überfälligkeitsmeldung nie hinaus (AUDIT-003-014).

**Empfohlene Strategie:**

| Mechanismus | Empfehlung |
|---|---|
| Locking | vorhanden und richtig — nichts zu ändern |
| Single Instance | „Keine neue Instanz starten" in der Aufgabenplanung **zusätzlich** zum Advisory Lock |
| Retry | vorhanden (15-Minuten-Takt, Nachholfrist); **kein** „Neustart bei Fehler" in der Aufgabenplanung — er stünde quer zum eigenen Mechanismus |
| Timeout | **„Task beenden nach 3 Stunden"** setzen. Der Kill ist unbedenklich: Verbindung schließt, Sperre fällt, Lauf gilt als nicht erledigt |
| Recovery | vorhanden; Backfill idempotent und fortsetzbar |

### 22.8 Windows-Aufgabenplanung — Einstellungen

| Einstellung | Tageslauf | Sicherungskette | Begründung |
|---|---|---|---|
| Ausführen, ob angemeldet oder nicht | **nein** (nur bei Anmeldung) | **ja** | Die TWS braucht die angemeldete Sitzung (ADR 0018); Doc 14 hält für die Sicherung ausdrücklich das Gegenteil fest |
| Mit höchsten Rechten | **nein** | **nein** | nichts schreibt in geschützte Pfade |
| Starten in | `…\backend` empfohlen | Projektwurzel | **nicht kritisch:** `config/default.yaml`, `.env` und `--log-file` werden gegen die **Projektwurzel** aufgelöst, der `wrangler`-Unterprozess bekommt sein `cwd` explizit |
| Umgebungsvariablen | aus `.env` der Projektwurzel | `pgpass.conf` | **nie in die Task-Argumente** |
| Virtuelle Umgebung | direkter Aufruf von `.venv\Scripts\python.exe` | `powershell.exe -NoProfile -File …` | richtig; kein `activate` nötig |
| Mehrfachinstanzen | „Keine neue Instanz starten" | dito | zusätzlich zum Advisory Lock |
| Zeitlimit | **3 Stunden setzen** | 1 Stunde | schließt den hängenden Lauf |
| Neustart bei Fehler | **nein** | optional 1× nach 30 min | der Lauf hat seinen eigenen, besseren Mechanismus |
| Energie / Netz | „Nur bei Netzbetrieb" **deaktivieren** | dito | Server läuft durch |
| Verlauf | **einschalten** | einschalten | standardmäßig deaktiviert; ohne ihn kein Nachweis vergangener Starts |
| Protokollierung | **`--log-file` ergänzen** | `sicherung.log` entsteht selbst | AUDIT-003-013 |
| Benutzerkonto | dasselbe wie die TWS | Konto mit `pgpass.conf` | `pgpass.conf` liegt in `%APPDATA%` und ist **benutzergebunden** |

### 22.9 Monitoring des Scheduled Tasks

```text
Task gestartet          → ja  (Aufgabenplanung, Verlauf muss aktiv sein)
  ≠ Python gestartet    → ja  („Letztes Ausführungsergebnis")
  ≠ Pipeline ausgeführt → nur per Datenbankabfrage
  ≠ Pipeline erfolgreich→ nur per Abfrage; Telegram erst nach Fristablauf
  ≠ Ergebnis korrekt    → nein, und das ist in Ordnung
```

Drei stille Ausfallarten und ihre Gegenmittel stehen in AUDIT-003-014.
Sofort wirksam und je fünf Minuten: `--log-file` ergänzen, Zeitlimit
setzen, `send_when_no_candidates` auf `true`.

### 22.10 Backup vor oder nach dem Lauf?

| Reihenfolge | Geschützt | Worst Case |
|---|---|---|
| **vor** dem Lauf (17:00) | Stand des Vortages | der heutige Lauf samt ~400 Optionsnotierungen wird bis zu 24 h später gesichert |
| **nach** dem Lauf (23:45) | **der heutige Analysestand einschließlich `option_quotes`** | ein Lauf, der die Datenbank beschädigte, ginge mit — bei dieser Architektur praktisch ausgeschlossen: Läufe schreiben **anfügend**, Migrationen laufen von Hand |
| beides | maximale Abdeckung | doppelter Platzbedarf |

**Empfehlung: nach dem Lauf, täglich 23:45.** Der entscheidende Grund ist
die Unveränderlichkeit — der Tageslauf **kann** den Vortagesstand nicht
beschädigen, also schützt eine Vorher-Sicherung davor nichts. Umgekehrt
entsteht der einzige unersetzliche Neubestand des Tages **im** Lauf.

### 22.11 Disaster Recovery

**Könnte ein neuer Windows-Server das System vollständig herstellen?**
Heute: **nein** — die Anleitung ist ausgezeichnet, es gibt nur nichts
zurückzuspielen.

| Baustein | Vorhanden? | rebuildable / restore-only | Quelle |
|---|---|---|---|
| Quellcode | ✅ | rebuildable | GitHub |
| Python-Version, Abhängigkeiten | ✅ | rebuildable | Lock-Dateien, hash-verifiziert (ADR 0008) |
| `.venv` | ✅ | rebuildable | Doc 13 / Doc 14 Stufe A |
| Fachliche Konfiguration | ✅ | rebuildable | `config/default.yaml` |
| Watchlisten | ✅ | rebuildable | `watchlists/*.txt` im Repository |
| Datenbankschema | ✅ | rebuildable | Alembic |
| **Datenbankinhalt** | ❌ | **restore-only** | **existiert nicht** |
| Struktur der Geheimnisse | ✅ | rebuildable | `.env.example`, Doc 14 Stufe B |
| **Werte der Geheimnisse** | ⚠️ | **restore-only** | Passwortmanager — für Passphrase und Notfallkarte vorgeschrieben; für `ATA_LLM_API_KEY`, `ATA_FINNHUB_API_KEY`, `ATA_NOTIFICATION_TOKEN`, `ATA_DASHBOARD_PUBLISH_TOKEN` **zu prüfen** |
| Scheduler-Konfiguration | ✅ | rebuildable | Doc 14 Stufen F/H, Felder vollständig tabelliert |
| Cloudflare | ✅ | rebuildable | Doc 14 Stufe L, Schritte 1–8 inkl. Notfallkarte |
| Telegram | ✅ | rebuildable | Doc 14 Stufe H (der Bot lebt bei Telegram) |
| TWS / IBKR | ✅ | manuell | ADR 0018 |
| Deployment-Anleitung | ✅ | — | Doc 13 + Doc 14 (2.316 Zeilen) |
| **Restore-Anleitung** | ❌ | — | **fehlt** — es gibt eine *Prüf*-Anleitung (`sicherung-probe.ps1`), aber keine „so spielst du den Produktivbestand zurück" |

#### Disaster-Recovery-Checkliste

```text
 1. Windows-Server, Benutzerkonto, angemeldete Sitzung          [Doc 14 Stufe A]
 2. Python + PostgreSQL, bin in PATH oder -PgBin nutzen         [Doc 14 Stufe A/B]
 3. git clone; .venv; pip --require-hashes; pip -e .            [Doc 13]
 4. .env aus dem Passwortmanager wiederherstellen               ← restore-only
 5. Rolle 'ata' + leere Datenbank anlegen                       [Doc 14 Stufe B]
 6. pg_restore des jüngsten Dumps                               ← ANLEITUNG FEHLT
 7. alembic current == alembic heads prüfen                     [Doc 14 Stufe B]
 8. TWS installieren, anmelden, API-Port freigeben              [Doc 14 Stufe D]
 9. Trockenlauf, dann Einzelprobe screen/options                [Doc 14 Stufe C/D]
10. pgpass.conf anlegen; Sicherung einmal von Hand              [Doc 14 „Sicherung"]
11. npm ci im Frontend (dort liegt wrangler!)                   [Doc 14 „Aktualisierung"]
12. publish --full (Oberfläche + Daten nach Cloudflare)         [Doc 14 Stufe L]
13. Aufgaben eintragen: Tageslauf, Sicherung, Wächter           [Doc 14 Stufe F/H]
14. Erster begleiteter Tageslauf, 12:50–14:50 ET                [Doc 14 Stufe F]
```

Schritte 1–3, 5, 7–9 und 11–14 sind **rebuildable** und vollständig
beschrieben. Schritte **4 und 6 sind restore-only** — und genau dort hat das
System heute nichts.

### 22.12 Recommended Task Architecture

**Empfehlung: getrennte Tasks (Variante B) — mit einer bewussten Ausnahme.**

Die Begründung kommt aus dieser Architektur, nicht aus einer allgemeinen
Best Practice: `dispatch` **ist bereits ein Orchestrator** — er ordnet
Backfill, Datengate, Analyse, Meldung und Export, und diese fünf hängen
tatsächlich voneinander ab. Die Sicherung hängt von keinem davon ab. Sie in
denselben Prozess zu ziehen fügte eine Kopplung hinzu, die es nicht gibt —
und zwar beim Vorgang, der **gerade dann** laufen muss, wenn der Tageslauf
gescheitert ist.

| Kriterium | Eine zentrale Aufgabe | **Getrennte Aufgaben** |
|---|---|---|
| Fehlereinkapselung | ein Rückgabewert für fünf Vorgänge | **je Task ein eigener, bereits entworfener Vertrag** (0/1/2/130 bzw. 0/2) |
| Zeitfenster | **unvereinbar**: `dispatch` hat ein hartes fachliches Fenster und startet alle 15 min; die Sicherung hat keines und soll genau einmal laufen | je Trigger passend |
| Recovery | der Wiederholmechanismus zöge die Sicherung mit — 16 Dumps am Abend | jeder nach eigener Logik |
| Monitoring | eine Zeile für fünf Vorgänge | **eine Zeile je Vorgang** |
| Datenkonsistenz | ein Dump mitten in Phase 3 — die Entscheidung verschwände im Orchestrator | die Uhrzeit entscheidet, sichtbar im Trigger |
| Sicherheit | ein Prozess bräuchte TWS-Zugang, LLM-Schlüssel, Cloudflare-Token **und** Dump-Rechte | getrennte Rechte je Task |
| Wartbarkeit | neuer Orchestrator-Code mit eigenen Tests | **kein neuer Code** |

**Gemeinsam orchestriert** gehört die Sicherungskette: Dump → Prüfung →
Kopie außer Haus → Aufräumen. Das ist eine Kette mit echten Abhängigkeiten,
und ihre ersten beiden Glieder sowie das Aufräumen stehen bereits in dieser
Reihenfolge in `sicherung.ps1`.

#### Recommended Windows Task Schedule

| Task | Frequency | Approx. Duration | Dependencies | Purpose | Failure Handling |
|---|---|---:|---|---|---|
| **Tageslauf** *(besteht)* | Mo–Fr 17:30, alle 15 min, 4 h | 103 min; ~60 nach ADR 0068 | TWS, PostgreSQL, 5 Dienste | Screening, Analyse, Bericht, Meldung, Export | Advisory Lock; 15-min-Wiederholung; Telegram nach Frist; **Zeitlimit 3 h ergänzen** |
| **Sicherung** *(neu, zwingend)* | täglich 23:45 | 1–5 min | PostgreSQL, `pgpass.conf` | Dump, Lesbarkeitsprüfung, Aufräumen | Rückgabewert 2 sichtbar; `sicherung.log`; Wächter meldet |
| **Kopie außer Haus** *(neu, zwingend)* | täglich 00:15 | wenige min | Sicherung, externes Ziel | einzige Stufe gegen Serververlust | Rückgabewert; Wächter |
| **Wächter** *(neu, sinnvoll)* | täglich 23:15 | Sekunden | PostgreSQL, Telegram | „lief heute ein Lauf, griff die Sicherung?" | selbst der Melder; Rückgabewert 2 |
| **Integritätsprüfung** *(neu, sinnvoll)* | monatlich, So 03:00 | Minuten | PostgreSQL | Sprünge und Lücken im Bar-Bestand | Bericht, keine Automatik |
| **Restore-Zählprobe** *(von Hand)* | quartalsweise | 5–20 min | Sicherung | beweist, dass der Dump Daten enthält | menschlicher Zahlenvergleich |
| **Backtests, Kalibrierung** *(von Hand)* | bei Bedarf | Minuten | Kerzenbestand | Messung, nicht Betrieb | — |
| **Pflegetermin** *(von Hand)* | quartalsweise, 2026-12-01 | — | — | Schwellen, Preise, Modelle, Advisories | Doc 14 „Pflege" |
| **Dashboard-Dienst** *(optional)* | Systemstart | dauerhaft | — | LAN-Anzeige | fällt er aus, fehlt nur die Anzeige |

> **Hinweis zur Zählprobe:** `sicherung-probe.ps1` ist zum **Mitlesen**
> gebaut — sie stellt Zahlen nebeneinander und hat keinen
> Rückgabewertvertrag für „die Zahlen passen". Automatisieren ließe sie sich
> erst mit einer eingebauten Zählprüfung. Bis dahin bleibt sie Handarbeit.

### 22.13 Ist der aktuelle Zustand vollständig?

**Nein.** Der `dispatch`-Task deckt den fachlichen Kern vollständig ab —
Screening, Analyse, Backtest je Kandidat, Bericht, Meldung, Export,
Wiederholung, Sperre und Ausfallmeldung sind sauber gebaut und laufen. Es
fehlen **Sicherung, Kopie außer Haus, Überwachung und Protokollierung**.

| Einstufung | Prozess | Frequenz | Eigener Task? |
|---|---|---|---|
| **zwingend erforderlich** | Datenbanksicherung | täglich 23:45 | **ja** — muss gerade dann laufen, wenn der Lauf scheitert |
| **zwingend erforderlich** | Kopie außer Haus | täglich 00:15 | **ja** (oder als vierter Schritt der Sicherungskette) |
| **betrieblich sinnvoll** | Wächter | täglich 23:15 | **ja** — ein Wächter im überwachten Prozess schweigt, wenn dieser hängt |
| **betrieblich sinnvoll** | Protokolldatei einschalten | — | **nein** — eine Argumentänderung am bestehenden Task |
| **betrieblich sinnvoll** | Zeitlimit 3 h | — | **nein** — eine Einstellung am bestehenden Task |
| **betrieblich sinnvoll** | Restore-Zählprobe | quartalsweise | nein, Handarbeit |
| **betrieblich sinnvoll** | Integritätsprüfung Bestand | monatlich | ja |
| **optional** | Optionsbacktest, Dashboard-Dienst, `send_when_no_candidates` | — | teils |
| **nicht erforderlich** | Retention, Cache-Bereinigung, Signal-Backtest, automatische Migrationen, Log-Rotation als Task | — | nein |

---

## 23. Datenfluss und Single Source of Truth

### 23.1 Der tatsächliche Fluss

```text
  watchlists/*.txt  ──────────────────────────────┐
         │                                        │
         ▼                                        │
  IBKR TWS ──► Backfill ──► intraday_bars ◄───────┘  (Bestand, unveränderlich)
                  ╎              │
                  ╎ (verzahnt,   ▼
                  ╎  ADR 0069)  aggregate_intraday_bars  → 195-Min-Kerzen
                  ╎              │                        + incomplete-Befunde
                  ▼              ▼
             Datengate      compute_indicator_values  (RSI, RSI-MA, EMA5, EMA20)
             (5 Symbole)         │
                                 ▼
                        evaluate_candidate   ← EINZIGE Kandidatenentscheidung
                                 │             (Live UND Backtest)
                    ┌────────────┴────────────┐
              NOT_CANDIDATE              CANDIDATE
                                              │
     ┌────────────┬────────────┬──────────────┼────────────┬─────────────┐
     ▼            ▼            ▼              ▼            ▼             ▼
  technical    backtest    fundamentals   analysts     earnings    [Phase 1b]
  snapshot     (Episoden)  (EDGAR)        (Finnhub)    (Finnhub)    options
  + zones          │           ▲              │            │        (IBKR)
     │             │           │              │            │          ▲ ▲
     │             │      Schlusskurs ────────┘            └──────────┘ │
     │             │      der letzten                    (Verfallswahl)  │
     │             │      abgeschl. Kerze                                │
     └─────────────┼───────────────── Zonen (optional) ──────────────────┘
                   │
                   ▼           [Phase 2, nebenläufig]
            Technical Agent (Anthropic)   Research Agent (= none)
                   │
                   ▼           [Phase 3]
            compute_swing_score  ◄── Signale, Statistik, Chart, Chance/Risiko,
            compute_long_term_score      Analystenvoten, Optionsrendite
                   │
                   ▼
            derive_recommendation  ── Grundstufe → Korrektur → Deckelung
                   │
                   ▼
            screening_results + stock_reports  (unveränderlich, versioniert)
                   │
     ┌─────────────┴──────────────┐
     ▼                            ▼
  render_notification        Dashboard-Export (verschlüsselt)
     │                            │
     ▼                            ▼
  Telegram                   Cloudflare Worker ──► Browser (entschlüsselt lokal)
```

**Abweichungen vom Diagramm des Auftrags:** News und KI-Analyse sind
produktiv abgeschaltet (ADR 0051); die „News- und Ereignislage" im Score
steht auf den gezählten Analystenvoten (ADR 0046). Die Optionsanalyse läuft
nicht parallel zu den übrigen Modulen, sondern **hinter** dem Backfill in
einer eigenen Phase 1b — sie ist der einzige Teil der Aktienschleife, der
die TWS anfasst, und teilt sich deren Verbindung (ADR 0069).

### 23.2 Single Source of Truth

| Größe | Einzige Quelle | Geprüft |
|---|---|---|
| Kandidatenentscheidung | `evaluate_candidate` | **ja** — Live und Backtest rufen dieselbe Funktion; ein Architekturtest bewacht die Domänengrenze |
| Entscheidungspunkt | `is_decision_point` | **ja** — öffentlich gemacht, *„damit der Validierungschart dieselbe Definition benutzt"* |
| Episodenergebnis | `compute_episode_outcome` | **ja** — Aggregat und Einzelwert aus derselben Rechnung (ADR 0061) |
| Kauf-Anteil der Analysten | `analyst_buy_share` | **ja** — Messlauf und Score rufen dieselbe Funktion, *„zwei Formeln hätten Schwellen ergeben, die zu den gemessenen Werten nicht passen"* |
| Liquiditätsstufe | `liquiditaetsstufe_von` | **ja** — öffentlich, weil der Absicherungs-Strike sie ebenso braucht |
| Aktienkurs | Schluss der letzten abgeschlossenen Kerze | **ja** — Screening, Chartauswertung, Fundamentalbewertung und Optionen nutzen denselben Wert |
| Sperrstatus | `latest_candidate_analyses` | **ja** — Lauf und Laufansicht rechnen dasselbe Fenster (ADR 0062) |
| Schwellen und Regelparameter | `config/default.yaml` | **ja**, aber ohne Versionskopplung → AUDIT-003-009 |

**Das ist bemerkenswert sauber.** An sechs Stellen, an denen zwei Fassungen
derselben Rechnung hätten entstehen können, wurde jeweils die eine Funktion
öffentlich gemacht statt die zweite geschrieben — mit ausformulierter
Begründung. Redundante Datenflüsse oder widersprüchliche Definitionen
derselben Kennzahl wurden **nicht gefunden**.

### 23.3 Fehlende Persistenz

| Größe | Persistiert? | Folge |
|---|---|---|
| Vorgänge (Anfragen, Warnungen, Retries) | **nein** | AUDIT-003-013 |
| Kostenschätzung je Lauf | **nein** | nur im Protokoll; bewusst offen gelassen |
| Zeitstempel der Optionsnotierung | **nein** | AUDIT-003-010 |
| Aktive Konfiguration je Lauf | **nur als Versionsnummern** | AUDIT-003-009 |
| Zustellstatus der Ergebnismeldung | **nein** | AUDIT-003-007 |
| Alles Übrige (Bars, Ergebnisse, Berichte, Notierungen, Episoden, Versionen) | **ja** | — |

### 23.4 Reproduzierbarkeit eines historischen Laufs

| Frage des Auditauftrags | Heute |
|---|---|
| Welche Kursdaten? | **ja** — `intraday_bars`, unveränderlich |
| Welche Fundamentaldaten? | **ja** — `fundamental_metrics` samt Vorgangsnummer der Einreichung |
| Welche News? | entfällt (Research aus); bei Nutzung: `research_citations` mit URL, Veröffentlichungs- und Abrufzeitpunkt |
| Welche Analystendaten? | **ja** — Voten und Monatsstand am Ergebnis |
| Welche Optionsdaten? | **ja** — `option_quotes`, alle abgerufenen; **ohne Zeitstempel** (010) |
| Welche Modellversion / welcher Prompt? | **ja** — `technical_ai_model`, `technical_ai_prompt_version` |
| Welche Konfiguration? | **teilweise** — elf Versionsfelder, aber keine Werte (009) |
| Welche Scores? | **ja** — Wert, Komponenten, Gewichte, Abdeckung, Begründungen |

**Sieben von acht.** Die Lücke ist die Konfiguration, und sie ist die
Ursache von AUDIT-003-009.

---

## 24. Fachliche Plausibilitätsprüfung

> Für jede Pipeline-Stufe: **Kann der Code technisch korrekt funktionieren
> und trotzdem fachlich ein falsches Ergebnis produzieren?**

| Stufe | Möglich? | Wodurch |
|---|---|---|
| Watchliste → Bars | **ja** | Split ohne Erkennung → **AUDIT-003-001** |
| Bars → Kerzen | nein | Vollständigkeit erzwungen, Lücken benannt, Raster geprüft |
| Kerzen → Indikatoren | nein | keine Ersatzwerte, Lücken brechen die Glättung |
| Indikatoren → Signale | nein | strikte Vergleiche, `DataIncompleteError` statt `False` |
| Signale → Kandidat | **mittelbar ja** | nur über falsche Eingangsdaten (001) |
| Kandidat → Backtest | **ja** | zwei Abweichungen von der gehandelten Strategie; eine gekennzeichnet (Earnings), eine nicht → **AUDIT-003-011** |
| Kandidat → Fundamentals | nein | Stichtagsbindung, Altersschranken, keine Mischung |
| Kandidat → Analystenvoten | nein | Altersschranke 62 Tage, vier Arten von „kein Wert" |
| Kandidat → Earnings | **ja** | der Status wirkt nicht → **AUDIT-003-003** |
| Kandidat → Optionen | **ja** | Mid + illiquide Kette + fehlende Warnung → **AUDIT-003-005/-012** |
| Alles → Score | **ja** | Abdeckung geht nicht in die Stufe → **AUDIT-003-004** |
| Score → Empfehlung | **ja** | dieselbe Ursache |
| Empfehlung → Telegram | **ja** | drei Kennzeichnungen erreichen den Kanal nicht (003, 004, 005) |
| Ergebnis → Dashboard | nein | überträgt, was da ist; erfindet nichts |

### Priorisierung nach der Vorgabe des Auftrags

| Rang | Kategorie | Befunde |
|---|---|---|
| 1 | falsche Signale | **001** |
| 2 | falsche Backtest-Ergebnisse | **001**, 011, 015 |
| 3 | falsche Scores | **004**, mittelbar 001 und 008 |
| 4 | falsche Optionsselektion | **005**, 012 |
| 5 | veraltete/falsche Marktdaten | **001**, 010 |
| 6 | stille Datenfehler | **001**, 007, 008, 013 |
| 7 | Security | 016 (gering) |
| 8 | Datenverlust | **002**, 006 |
| 9 | fehlende Reproduzierbarkeit | 009, 010 |

**AUDIT-003-001 steht in fünf von neun Kategorien.** Das ist der Grund für
seine Einstufung.

### False Confidence — gesammelt

Der Auftrag verlangt eine ausdrückliche Kennzeichnung solcher Fälle:

| Fall | Vorhanden? | Befund |
|---|---|---|
| Hoher Score trotz fehlender Daten | **ja** | 004 |
| Backtest mit zu geringer Stichprobe | **nein** — unter 10 Ereignissen entsteht keine Kennzahl, 10–29 deckeln den Teilwert auf 6,0 | — |
| Präzise Optionsrendite bei illiquidem Markt | **ja** | 005, 012 |
| KI-Newsanalyse ohne belastbare Quellen | **nein** — Research ist abgeschaltet; bei Nutzung Zitierarchitektur mit Quellenbindung (ADR 0023) | — |
| Veraltete Analystenratings | **nein** — Altersschranke 62 Tage, mit ausformulierter Begründung | — |
| Alte Kursdaten | **nein** — `_require_expected_candle` wirft `StaleDataError` je Aktie | — |
| Fehlende Earnings-Daten | **nein** — `UNKNOWN` deckelt auf `CANDIDATE` und steht in der Meldung | — |
| **Bekannt nahe Earnings-Daten** | **ja** | **003** |
| Nicht reproduzierbare Ergebnisse | **teilweise** | 009 |
| Falsche Kursdaten nach Split | **ja** | **001** |

Sechs von zehn typischen Fällen sind **bereits sauber behandelt** — mehrere
davon mit einer Sorgfalt, die über das Übliche hinausgeht. Die vier offenen
sind die Befunde dieses Audits.

---

## 25. Recommended Actions

### Sofort, ohne Implementierung (zusammen unter einer Stunde)

| # | Maßnahme | Befund | Aufwand |
|---|---|---|---|
| 1 | `--log-file var/logs/tageslauf.log` in die Task-Argumente | 013 | 5 min |
| 2 | Zeitlimit „3 Stunden" am Tageslauf-Task | 014 | 5 min |
| 3 | Aufgabenverlauf in der Aufgabenplanung einschalten | 014 | 2 min |
| 4 | **Sicherungs-Task eintragen** (23:45), einmal von Hand laufen lassen | **002** | 30 min |
| 5 | Zählprobe einmal durchspielen, A2-M4 schließen | 002 | 20 min |

### Kurzfristig (Entwicklung, je unter einem Tag)

| # | Maßnahme | Befund | Aufwand |
|---|---|---|---|
| 6 | **Sprungprüfung im Backfill** + `cli refetch-bars` | **001** | 1 Tag |
| 7 | Deckel `cap_low_coverage`, Abdeckung in die Meldung | **004** | 4 h + ADR |
| 8 | Liquiditätsstufe in die Put-Zeile; die drei Zusagen richtigstellen | **005** | 3 h |
| 9 | `EARNINGS_EXCLUDED` kennzeichnen (Variante A) | **003** | 4 h + ADR |
| 10 | Retry mit Backoff auf 429/5xx | 008 | 4 h |
| 11 | Ergebnismeldung: Vermerk + Nachholen | 007 | 3 h |
| 12 | `option_quotes`: `quoted_at` und `market_data_type` | 010 | 3 h |
| 13 | Prüfsummentest Konfiguration ↔ Scoring-Version | 009 | 3 h |
| 14 | Berichtsvermerk zur Wiederholsperre im Backtest | 011 | 1 h |

### Mittelfristig

| # | Maßnahme | Befund | Aufwand |
|---|---|---|---|
| 15 | **ADR und Umsetzung: Kopie außer Haus** | **006** | ADR + 4 h |
| 16 | Wächter-Task | 014 | 4 h |
| 17 | ADR 0068/0069 ausrollen, Laufzeit neu messen | 021 | Deployment |
| 18 | Zweiter Golden Master über die Score-Kette | 009 | 6 h |
| 19 | Monatliche Integritätsprüfung des Bestands | 001 | 4 h |
| 20 | `/docs` schließen vor Stufe J | 016 | 15 min |
| 21 | Tote Modellprofile streichen; Doc 13 nachziehen | 017, 018 | 1 h |
| 22 | Warm-up im Replay prüfen (mit Neuaufzeichnung) | 015 | S + Version |

---

## 26. Prioritized Remediation Plan

### Stufe 0 — noch in dieser Woche

> **Der Zustand „kein Backup" ist der einzige, bei dem Warten einen
> unwiederbringlichen Verlust riskiert.** Alles andere kann warten, das
> nicht.

1. Maßnahmen 1–5 (unter einer Stunde, keine Entwicklung, kein Deployment).

Danach ist das System gesichert, protokolliert und gegen den hängenden Lauf
abgesichert — mit fünf Handgriffen am Server.

### Stufe 1 — die stillen Fehler (1–2 Wochen)

2. **Maßnahme 6** (Sprungprüfung) — schließt den einzigen Weg, auf dem
   falsche Kursdaten zu einem plausiblen Kandidaten werden. **Höchste
   fachliche Priorität.** Mit ADR, weil die Schwelle eine Festlegung ist.
3. **Maßnahmen 7–9** (Abdeckung, Liquidität, Earnings) — drei Änderungen,
   die dieselbe Klasse schließen: berechnete Kennzeichnungen, die ihre
   Wirkung nicht entfalten. Zusammen unter zwei Tagen, zwei ADRs.
4. Die zugehörigen Tests (Abschnitt 18.2, Punkte 1–4).

### Stufe 2 — Robustheit und Nachweisbarkeit (2–4 Wochen)

5. Maßnahmen 10–14 (Retry, Meldungsvermerk, Notierungszeitstempel,
   Prüfsummentest, Berichtsvermerk).
6. **Maßnahme 15** (Kopie außer Haus) — ADR zuerst; die Entscheidung über
   Ziel und Verschlüsselung gehört dem Projektinhaber.
7. Maßnahme 16 (Wächter), Maßnahme 17 (Deployment ADR 0068/0069).

### Stufe 3 — Substanz (wenn Zeit ist)

8. Maßnahmen 18–22.

### Was bewusst **nicht** empfohlen wird

| Nicht empfohlen | Grund |
|---|---|
| Refactoring von `cli.py` | eigenes Vorhaben, kein Auditnebenprodukt (§32) |
| Retention / Archivgrenze | bewusst vertagt; Unveränderlichkeit ist Architekturprinzip |
| Regelmäßiger Backtest als Task | läuft je Kandidat im Tageslauf |
| Split-Bereinigung automatisieren | Erkennen ja, Korrigieren nein — eine automatische Korrektur historischer Kurse widerspräche der Unveränderlichkeit |
| Container | ADR 0036, zweimal neu bewertet, zweimal bestätigt |
| Authentifizierung für die LAN-API | ADR 0049; der externe Weg läuft über Cloudflare Access |

---

## 27. Conclusion

**Die Architektur ist konsistent mit ADRs und Requirements.** Die
Schichtgrenzen werden durch Tests erzwungen, die drei deklarierten
Kopplungen halten, eine vierte wurde gesucht und nicht gefunden, und keine
Architekturentscheidung ist überholt, ohne dass ein ablösender ADR das
festhielte.

**Die fachliche Rechnung ist korrekt.** Indikatoren, Signalregeln,
Kerzenbildung, Episodenbildung, Kennzahlen und Scores wurden einzeln gegen
ihre Spezifikation geprüft. Kein Rechenfehler, kein Off-by-one, kein
Look-ahead, kein Zeitzonenfehler. Der Umgang mit fehlenden Daten ist
durchgängig und ohne einen einzigen stillen Ersatzwert.

**Die Schwäche liegt woanders, und sie ist strukturell.** Dieses System ist
darauf ausgelegt, **fehlende** Daten zu erkennen — und darin ist es sehr
gut. Gegen **falsche** Daten hat es fast keine Schranke; das ist
AUDIT-003-001. Und es berechnet Kennzeichnungen sorgfältig, die auf dem
letzten Meter nicht ankommen: die Datenabdeckung nicht in der
Empfehlungsstufe, die Liquiditätsstufe nicht in der Meldung, der nahe
Berichtstermin nirgends. Das sind drei Instanzen desselben Musters, und
alle drei sind mit wenigen Stunden zu schließen.

**Der Betrieb ist der am wenigsten entwickelte Teil.** Ein einzelner
Scheduled Task trägt ein System, dessen wertvollster Bestand nicht
rekonstruierbar ist. Die Sicherungsskripte sind besser gebaut als die
meisten produktiven Backup-Skripte — sie sind nur nicht eingetragen. Das
ist der einzige Befund dieses Audits, bei dem ein einzelnes Ereignis alles
kostet, und zugleich der mit dem kleinsten Aufwand.

Was dieses Projekt von vergleichbaren unterscheidet, ist nicht die
Fehlerfreiheit, sondern die **Nachprüfbarkeit**: Weil jede Entscheidung
begründet an ihrem Wirkungsort steht, lässt sich prüfen, ob sie hält. Vier
der fünf wichtigsten Befunde dieses Audits konnten nur deshalb so präzise
formuliert werden, weil der Code selbst aussprach, was er zusichern wollte.
Ein Repository, das seine eigenen Zusagen aufschreibt, macht sich
angreifbar — und genau das ist der Grund, warum es besser wird.

---

*Dieses Audit ist eine Momentaufnahme des Commits `3540adc` vom 2026-09-20
und wird nicht nachgeführt. Der Erledigungsstand steht in der
[Nachverfolgung](2026-09-20-nachverfolgung.md).*
