# Repository-Audit 2 — 2026-08-31 (historische Bestandsaufnahme)

> **Dieses Dokument ist eine Momentaufnahme, keine Festlegung.**
> `Point-in-time snapshot – keine normative Spezifikation.`
>
> Es beschreibt, wie das Repository am 2026-08-31 vorgefunden wurde. Es
> **ersetzt kein ADR, keine Requirements-Datei und keine Roadmap** und trifft
> keine Entscheidungen. Wo dieser Bericht und die maßgeblichen Quellen —
> Quellcode, `docs/adr/`, `docs/requirements/`, `config/default.yaml` —
> auseinandergehen, gelten **immer die maßgeblichen Quellen**. Der Bericht
> altert ab dem Tag seiner Erstellung; er wird nicht nachgeführt
> (`README.md` dieses Verzeichnisses).

## 1. Metadaten und untersuchter Repository-Stand

| Feld | Wert |
|---|---|
| **Status** | `Point-in-time snapshot` |
| **Audit-Datum** | 2026-08-31, Beginn 23:19 CEST |
| **Untersuchter Branch** | `feature/optionsanalyse` — **nicht** `dev`. Der Branch liegt 14 Commits vor `origin/dev` (`5f81568`, Merge PR #59) und enthält die vollständige, noch nicht gemergte Optionsanalyse. Auditiert wurde bewusst dieser Stand: Er ist der jüngste, und der Auftrag untersagt Branch-Wechsel. Wo eine Feststellung nur den Branch betrifft und nicht `dev`, ist das vermerkt. |
| **Commit-SHA (vollständig)** | `1f65472be12c6e7c6d38f5f19845efae8c75be82` |
| **Commit-Betreff** | `fix(cli): dispatch kannte den Optionsanbieter nicht` |
| **Zustand des Working Tree** | **Sauber.** `git status --porcelain` zu Beginn leer; es lag keine unversionierte Nutzerarbeit vor. Der Branch ist nach `origin/feature/optionsanalyse` gepusht und dort auf demselben Stand. |
| **Bezug zu Audit 1** | [Repository-Audit vom 2026-08-23](2026-08-23-repository-audit.md), Commit `f61f316` (`dev`). Seitdem: **130 Commits, 24 gemergte Pull Requests (#36–#59), 22 neue ADRs (0027–0048), 8 neue Alembic-Migrationen** (Head jetzt `f4a71c9e2d38`), Testbestand von 915 auf 1758. |
| **Verwendetes Modell** | `claude-fable-5` (Claude Fable 5) über Claude Code. |
| **Arbeitsmodus** | Ausschließlich auditierend. Geändert wurden nur dieser Bericht und eine Zeile im Audit-Index. Keine Änderung an Quellcode, Dokumentation, ADRs, Requirements, Audit 1 oder dessen Nachverfolgung; kein Commit, kein Push, kein Branch-Wechsel; keine produktiven externen API-Aufrufe, keine Telegram-Nachricht, keine Broker- oder Börsenaktion, keine Änderung an Datenbanken. |

**Repository-Struktur und Stack** (unverändert zu Audit 1, gewachsen im Umfang):
Monorepo mit `backend/` (Python 3.12/3.13, FastAPI, SQLAlchemy 2, Alembic,
Pydantic 2, ib_async, httpx, anthropic-SDK; vier Schichten unter
`backend/src/ai_trading_analyst/`), `frontend/` (Next.js 15, TypeScript
strict — Platzhalter), `config/default.yaml`, `docs/` (14 Fachdokumente, 48
ADRs, 7 Requirements-Dateien, Audits), `spikes/`, `watchlists/` (3
Export-Dateien). PostgreSQL 16; Lock-Dateien mit Hashes (`uv pip compile
--universal`). CI: 5 Jobs (Backend-Matrix 3.12/3.13 mit Postgres-Service,
Windows-Job, Frontend, Secret-Checks). Einstiegspunkte: 16 CLI-Kommandos
(`watchlist`, `backfill`, `deepen-history`, `export-bars`, `history-depth`,
`calendar-reach`, `screen`, `backtest`, `technical`, `fundamental`,
`calibrate-scores`, `options`, `report`, `research`, `ratings`, `dispatch`)
plus `uvicorn ai_trading_analyst.main:app`. Secrets ausschließlich über
`ATA_*`-Umgebungsvariablen (`.env` gitignored, CI-geprüft). Eine
`AGENTS.md` existiert nicht; maßgebliche Arbeitsanweisungen stehen in
`CLAUDE.md` (Projekt) und `docs/12 - CLAUDE.md` (Original).

## 2. Executive Summary

**Das Projekt hat in den acht Tagen seit Audit 1 zwei Sprints Substanz
aufgeholt und dabei die Audit-1-Nachverfolgung im Wesentlichen ehrlich
geführt.** Der Befund im Einzelnen:

1. **Die Kette läuft jetzt von der Watchlist bis zur bewerteten
   Push-Nachricht.** Zu Audit 1 endete der Tageslauf nach Research und
   Technical Agent. Heute hängen im selben Lauf zusätzlich: Backtest je
   Kandidat (ADR 0038), deterministische Fundamentalkennzahlen aus SEC
   EDGAR (ADR 0032–0035), Analystenempfehlungen von Finnhub (ADR 0043),
   Optionsanalyse über die IBKR-Kette (ADR 0048, nur dieser Branch), beide
   Scores samt Empfehlungsstufe (ADR 0041/0045/0046), der
   18-Punkte-Bericht (ADR 0039, `report-v2`) und die Ergebnismeldung mit
   Scores über Telegram (ADR 0040/0047). Alles deterministisch getrennt von
   KI, alles versioniert, alles testbelegt.

2. **Zwei Ausgangshypothesen des Auditauftrags sind überholt:** Die
   Fundamentalanalyse existiert (deterministisch; ihre KI-Einordnung steht
   noch aus), und Telegram ist weiter als „steht aus" — Ausfall-Alarm *und*
   Ergebnismeldung sind implementiert und getestet; nicht verifizierbar ist
   nur, ob der Kanal auf dem Server scharf geschaltet ist. Das Dashboard
   ist dagegen wie vermutet unverändert ein Next.js-Platzhalter.

3. **Audit-1-Reconciliation:** 12 von 14 Maßnahmen `BEHOBEN UND
   VERIFIZIERT`, M5 und M14 `TEILWEISE BEHOBEN` — beide exakt so, wie die
   Nachverfolgung es selbst deklariert. **Keine Maßnahme wurde als erledigt
   markiert, ohne dass die Substanz im Repository nachweisbar ist.** Zwei
   Erledigungen (M3-Serverlauf, M13-Serverversion) stützen sich anteilig
   auf Auskünfte außerhalb des Repositories und sind dort als solche
   gekennzeichnet. Alle 10 als „entschieden" geführten E-Punkte haben ihr
   ADR; E8, E9 und E13 sind offen — korrekt deklariert. Von den Risiken
   sind R1–R4, R7, R9 geschlossen (R7 in diesem Audit erstmals **extern
   verifiziert**: Branch-Protection auf `main` und `dev` mit fünf
   erzwungenen CI-Checks, per GitHub-API geprüft), R5/R6 eingegrenzt,
   R8/R10 offen.

4. **Prüfungen:** 1758 Tests grün (1567 Unit, 138 Integration gegen echtes
   PostgreSQL 16, 38 Architektur, 15 Golden Master), dazu 42
   Spike-Sonden. `ruff` sauber, `mypy --strict` über 224 Dateien ohne
   Befund, Frontend-Lint/-Typecheck/-Build grün, Alembic-Kette linear.

5. **Neue Befunde: keine P0, keine P1.** Der gewichtigste (A2-F001, P2):
   Die Optionsanalyse ist fertig gebaut, aber ungemergt, ohne die
   projektübliche unabhängige Review, und ihr End-to-End-Pfad im
   Server-Tageslauf ist unbelegt — der jüngste Commit behebt genau dort
   einen Verdrahtungsfehler. Daneben wiederholt sich ein Muster aus
   Audit 1 (A2-F002, P3): README und Roadmap führen Sprint 5 als „noch
   nicht gebaut", obwohl Scoring und Empfehlung seit dem 2026-08-31 in
   `dev` gemergt sind. Der Rest sind Dokumentations- und Pflegereste
   (P3/P4).

6. **Größte Erkenntnisgrenze bleibt der Betriebszustand des
   Windows-Servers** — wie bei Audit 1 aus dem Repository nicht
   verifizierbar. Neu ist, dass zwei Repository-Stellen dazu
   Unterschiedliches nahelegen (A2-F007): Die Nachverfolgung nennt seit dem
   2026-08-23 einen „täglichen Scharfbetrieb" des Research Agent, der
   Docstring von `domain/scoring/swing.py` (2026-08-31) sagt „Es gibt
   bislang keinen produktiven Tageslauf". Beides sind Aussagen, keine
   Belege.

## 3. Projektüberblick – aktueller verifizierter Stand

**Was ist das Projekt?** Ein persönliches Analyse-System für
Long-Swing-Trades auf US-Aktien. Es screent täglich nach Börsenschluss der
ersten 195-Minuten-Kerze rund 190 Aktien aus lokal gepflegten Watchlisten
auf drei definierte technische Kaufsignale, reduziert sie auf wenige
Kandidaten und analysiert diese vertieft. Es führt **keine Orders aus** und
trifft keine Handelsentscheidungen; Ergebnis ist eine begründete
Entscheidungsgrundlage.

**Welche Daten verarbeitet es?** Historische 15-Minuten-Kurse von
Interactive Brokers (lokal gespeichert, zu 195-Minuten-Kerzen aggregiert),
Earnings-Termine und Analystenempfehlungen von Finnhub, Fundamentaldaten
aus den XBRL-Einreichungen der SEC (EDGAR), Optionsketten von Interactive
Brokers sowie Web-Recherche über die Anthropic-API.

**Wie läuft eine Analyse ab?** Die Windows-Aufgabenplanung startet alle 15
Minuten einen Dispatcher, der in New Yorker Zeit entscheidet, ob heute ein
Handelstag ist und die Zielkerze (12:45 ET) vollständig vorliegt. Dann:
Bestand auffüllen, screenen (2-aus-3-Signalregel), und je Kandidat —
unabhängig voneinander — Chartauswertung (Zonen, Trend, ATR,
Chance-Risiko), Backtest der heutigen Signalkombination über die eigene
Historie, Fundamentalkennzahlen, Analystenvoten, Earnings-Filter und
Cash-Secured-Put-Vorschläge aus der Optionskette. Zwei KI-Aufrufe kommen
hinzu: eine Web-Recherche (nur wenn kein Earnings-Termin nahe ist) und die
qualitative Einordnung der Chartlage. **Kein Sprachmodell verändert dabei
eine Zahl** — KI-Ausgaben werden gegen feste Schemata validiert und
getrennt gespeichert.

**Wie entstehen Ranking und Scoring?** Deterministisch aus den Teilwerten:
Der Swing-Score gewichtet sechs Komponenten (Signale, historische
Trefferquote, Chart-Setup, Chance-Risiko, Analystenvoten,
Optionsattraktivität), der Investment-Score vier Fundamentalkomponenten.
Die Schwellen sind an der eigenen Watchlist gemessen, nicht gesetzt.
Fehlende Komponenten werden umgewichtet und benannt; unter 60 % Abdeckung
entsteht `INSUFFICIENT_DATA` statt einer Zahl. Aus beiden Scores leitet
sich eine Empfehlungsstufe ab. Je Kandidat entsteht ein unveränderlich
gespeicherter 18-Punkte-Bericht; die Telegram-Meldung nennt Symbole,
Signaltypen, beide Scores und die Stufe — sortiert nach Swing-Score, ohne
Freitext.

**Was ist nachweislich funktionsfähig?** Die gesamte Kette oben, belegt
durch 1758 grüne Tests, strikte Typprüfung und Golden-Master-Tests des
Verfahrens. **Implementiert, aber noch nicht ausreichend validiert:** die
Optionsanalyse (fertig auf einem ungemergten Feature-Branch; der Lauf gegen
die echte TWS im Tageslauf steht aus) und der produktive Dauerbetrieb
selbst — ob die Aufgabenplanung auf dem Server tatsächlich täglich läuft,
ist aus dem Repository nicht belegbar. **Geplant, nicht begonnen:** das
Web-Dashboard (Platzhalterseite), die KI-Formulierungen von
Fundamental- und Gesamtbericht, Authentifizierung, Backup/Restore.

**Wesentliche Einschränkungen:** Ein-Personen-Betrieb auf einem
Windows-Server mit manuell angemeldeter TWS; Kennzahlen-Schwellen und
Preislisten müssen von Hand nachgemessen bzw. gepflegt werden; die
Profitabilität der Strategie ist **nicht** bewertet — dafür fehlen
realisierte Ausgänge.

**Datenfluss (belegt an `application/run_analysis.py` und `cli.py`):**

1. Aufgabenplanung → `cli dispatch` (Handelstag? Kerze da? schon erledigt?)
2. Backfill der 15-Minuten-Bars von der TWS in PostgreSQL
3. Screening aller Watchlist-Titel auf dem Bestand (2-aus-3-Regel)
4. Je Kandidat sequentiell: Chartauswertung → Backtest → Fundamentaldaten (EDGAR) → Analystenvoten (Finnhub) → Earnings-Filter (Finnhub) → Optionsanalyse (TWS; Zonen und Berichtstermin als optionale Eingaben)
5. Nebenläufig in getrennten Pools: Research Agent (nur bei `EARNINGS_CLEAR`) und Technical Agent (Anthropic)
6. Scoring: Swing- und Investment-Score, Empfehlungsstufe
7. Persistenz in Originalreihenfolge: Screening-Ergebnis, Backtest, 18-Punkte-Bericht (eine Transaktion je Aktie)
8. Ergebnismeldung über Telegram (bzw. `dry_run`); Ausfall-Alarm, falls der Lauf ausbleibt
9. Abfrage: `cli report --run <id>`, REST-API (3 Endpunkte); Dashboard noch nicht vorhanden

## 4. Vertrauensniveau und Grenzen

| Aussagenklasse | Vertrauen | Begründung |
|---|---|---|
| Code, Tests, Konfiguration, Migrationen | **hoch** | Kernpfade vollständig gelesen (`run_analysis.py`, `dispatch_daily_run.py`, Scoring-, Options-, Report-, Notification-Module, Adapter-Köpfe); alle Prüfungen lokal ausgeführt (Abschnitt 12) |
| Audit-1-Reconciliation | **hoch** | Jede Maßnahme gegen Code, Tests, ADRs und Doku geprüft; PR-Historie und Branch-Protection zusätzlich über die GitHub-API verifiziert (read-only) |
| ADR-/Doku-Abgleich | **hoch für die 22 neuen ADRs und die geänderten Docs**; die 26 Alt-ADRs wurden gegen Audit 1 fortgeschrieben und stichprobenhaft, nicht erneut vollständig geprüft |
| Betriebszustand des Windows-Servers | **nicht verifizierbar** | Aufgabenplanungs-Eintrag, `.env`-Belegung, Scharfschaltung der Anbieter, Serverbestand (5-Jahres-Tiefe) liegen außerhalb des Repositories. Repository-interne Aussagen dazu widersprechen einander (A2-F007) |
| Externe Anbieter (TWS, Finnhub, EDGAR, Anthropic, Telegram) | **nicht geprüft** | Bewusst kein einziger Aufruf (Auditvorgabe). Messläufe vom 2026-08-24/-31 wurden als dokumentierte Artefakte übernommen, nicht reproduziert |
| Profitabilität der Strategie | **keine Aussage** | Keine realisierten Ausgänge im Bestand; ADR 0046 benennt selbst, dass die Empfehlungsstufen nicht an Ausgängen kalibriert sind |

Nicht ausgeführt (Netz/Credentials/Kosten): `cli
screen/backfill/dispatch/options --provider ibkr` (TWS), `cli
dispatch --earnings-provider finnhub --ratings-provider finnhub`, `cli
fundamental --provider edgar`, `cli research`/`technical
--interpret`/`ratings` gegen Anthropic/Finnhub, Telegram-Einzelprobe.
Sichere Ausführungswege: `docs/14 - Inbetriebnahme und Betrieb.md`
(Stufen und Zwischenschritte).

## 5. Architektur und End-to-End-Datenfluss

**Vier Schichten, unverändert erzwungen.** `domain` (ohne jede
Infrastruktur), `application`, `infrastructure`, `presentation`;
Composition Root `bootstrap.py` (646 Zeilen, verdrahtet inzwischen sieben
Provider-Ports). `tests/architecture/test_layer_boundaries.py` (38 Tests)
bricht bei Verstößen die CI. Die seit Audit 1 neuen Module folgen dem
Muster durchgehend: Domain rechnet (`domain/{fundamentals, analysts,
options, scoring, report}`), Adapter beschaffen (`infrastructure/{edgar,
finnhub/recommendations, ibkr/option_chain}`), und derselbe Domain-Code
bedient Tageslauf **und** Messläufe (`cli calibrate-scores`, `cli options
--watchlist`) — die ausdrückliche Lehre aus ADR 0045/0046, damit
gemessene Schwellen zur Produktionsformel passen.

**Genau drei gerichtete Kopplungen** zwischen Analysemodulen, alle drei
im Code nachvollzogen (`run_analysis.py`, `_prepare_stock` und
`_evaluate_options`): Zonen → Optionsanalyse (optional, nicht
blockierend), Kurs der letzten abgeschlossenen Kerze → Fundamentalbewertung
(optional), Earnings-Termin → Verfallsauswahl der Optionsanalyse
(vorhandener Termin wirkt, fehlender hält nichts auf — `expirations_in_window`
in `domain/options/strategies.py`).

**Fehlerbehandlung:** Fehlerisolation je Aktie; Ausfälle einzelner Anbieter
werden je Modul gefangen und als `UNKNOWN`/`UNAVAILABLE`/`None` mit
benanntem Grund geführt statt als Aktienfehler (durchgängiges Muster,
`_evaluate_*`-Methoden). Timeouts und Ratenbegrenzungen konfiguriert und
begründet: Research 900 s Lesetimeout mit `max_retries: 0` (gemessener
921-Sekunden-Vorfall), Technical Agent 60 s mit 2 Retries, Finnhub-Drossel
0,8 Anfragen/s (gemessen am 429-Verlust von 4/192 Symbolen), EDGAR 8/s,
IBKR-Pacing 11 s. Wiederholung auf Laufebene leistet der
15-Minuten-Dispatcher (idempotent über `dispatcher_runs` + Advisory-Lock;
Überfälligkeits-Alarm mit Zustell-Deduplizierung).

**Persistenz:** 17 lineare Migrationen, Head `f4a71c9e2d38`. Neue Tabellen/
Spaltensätze seit Audit 1: `research_*`-Qualitätsspalten, Backtest im
Tageslauf, `stock_reports` (unveränderliche JSON-Berichte),
Fundamentals-, Analysten-, Score-, Empfehlungs- und Options-Spalten —
deterministische und KI-Felder weiterhin strikt getrennt.

**Observability:** JSON-Logs mit Correlation-ID; seit ADR 0044 läuft jede
Logzeile durch eine Geheimnis-Schwärzung an der Senke
(`observability/secret_redaction.py` — Anlass war der Finnhub-Schlüssel,
der als URL-Parameter in jeder httpx-INFO-Zeile stand). Metriken und
Provider-Status in der Readiness fehlen weiterhin (nur DB-Check);
Token-/Kostenverbrauch steht nur im Log.

**Ausgabekanäle:** Telegram (Ausfall-Alarm + Ergebnismeldung, Kürzung auf
4096 Zeichen mit Kennzeichnung, Token-Redaktion im Fehlerpfad), `cli
report` (lesbar/Dokument), REST-API (`POST/GET /api/v1/analysis-runs`,
`GET .../{id}`, `/system/health`, `/system/readiness` — ohne Auth, ohne
Pagination), Dashboard nicht vorhanden.

**Komponenteneinstufung:**

| Komponente | Einstufung |
|---|---|
| Watchlist-Import, Backfill, Tiefen-Backfill, Kerzenbildung, Indikatoren, Screener | `PRODUKTIV IMPLEMENTIERT` |
| Earnings-Filter (Finnhub + Fixture) | `PRODUKTIV IMPLEMENTIERT` |
| Backtesting (manuell **und** im Tageslauf) | `PRODUKTIV IMPLEMENTIERT` — Kennzahlen-Teilmenge von Doc 10 §6.6 besteht fort (ohne Stddev, beste/schlechteste Rendite, MAE/MFE) |
| Deterministische Chartauswertung + Technical Agent | `PRODUKTIV IMPLEMENTIERT` |
| Research Agent (inkl. Qualitätspaket ADR 0029) | `PRODUKTIV IMPLEMENTIERT` — bekannte, dokumentierte Grenzen (Abrufe erreichen kaum eine Domain der Allowlist) |
| Fundamentalanalyse, deterministische Hälfte (EDGAR) | `PRODUKTIV IMPLEMENTIERT` |
| Fundamentalanalyse, KI-Einordnung | `NICHT VORHANDEN` (geplant, Modellprofil konfiguriert) |
| Analystenempfehlungen (Finnhub) | `PRODUKTIV IMPLEMENTIERT` |
| Scoring Engine + Empfehlungsstufe | `PRODUKTIV IMPLEMENTIERT` (in `dev` seit PR #58/#59) |
| Optionsanalyse (IBKR-Kette, CSP) | `IMPLEMENTIERT, ABER NICHT AUSREICHEND GETESTET` — Code, Konfiguration und Unit-/Integrationstests vollständig und grün, aber nur auf diesem Branch; ungemergt, unabhängige Review offen, End-to-End im Server-Tageslauf unbelegt (A2-F001) |
| Report Generator, deterministische Hälfte (`report-v2`, 18 Punkte) | `PRODUKTIV IMPLEMENTIERT` |
| Report Generator, KI-Formulierung | `NICHT VORHANDEN` (geplant) |
| Benachrichtigung: Ausfall-Alarm + Ergebnismeldung | `PRODUKTIV IMPLEMENTIERT` (Code/Tests); Scharfschaltung am Server `NICHT VERIFIZIERBAR` |
| REST-API | `TEILWEISE IMPLEMENTIERT` (3 Fach-Endpunkte, keine Auth/Pagination — wartet auf E8/Sprint 6) |
| Dashboard | `NUR GERÜST ODER MOCK` (Next.js-Platzhalterseite, Build grün) |
| Observability | `TEILWEISE IMPLEMENTIERT` (Logs + Schwärzung ✓, Metriken ✖) |
| Backup/Restore | `NUR DOKUMENTIERT` (Doc 10 §15; kein Verfahren, kein Doc-14-Abschnitt) |
| Authentifizierung (`ATA_SESSION_SECRET`) | `NICHT VORHANDEN` (Secret-Feld reserviert) |

## 6. Feature-Status (Detail)

### 6.1 Fundamentalanalyse

Deterministisch aus EDGAR-XBRL (`infrastructure/edgar/`, ADR 0032):
Symbolauflösung über `www.sec.gov`, Fakten über `data.sec.gov`,
Kontaktadresse aus `ATA_EDGAR_CONTACT` (seit PR #48 nicht mehr in der
Konfigurationsdatei — das Repository ist öffentlich). 18 Kennzahlen
(`MetricName`) über Profitabilität, Wachstum, Bilanz und Bewertung;
Niveauzahlen und Bewertung auf zwölf Monaten, Wachstum auf
Geschäftsjahren (ADR 0033); Aktualitätsschranke 455 Tage, Umsatz ohne
Vetorecht, drei zugelassene Tag-Abweichler (ADR 0034, `fundamental-v3`).
Regeln im Code nachgelesen: kein Ersatzwert, keine Kennzahl aus zwei
Stichtagen. Einheiten: USD-Rohwerte und Verhältniszahlen mit
`MetricUnit`; Währungsvielfalt ist durch die Beschränkung auf
US-Emittenten (SEC-Einreichungen) begrenzt — Fremdwährungs-Filer sind
nicht gesondert behandelt, bekannte Lücken (Vergleichsgruppe,
Zwei-Stichtags-Kennzahlen) stehen als offene Punkte im ADR-Index. Tests:
63+ Unit-Tests inkl. eines **echten eingefrorenen
EDGAR-Ausschnitts** (`tests/unit/infrastructure/edgar/data/`, mit
Herkunftsvermerk). In den Tageslauf gekoppelt über den Kurs der letzten
abgeschlossenen Kerze (ADR 0035). Einfluss aufs Scoring: alle vier
Investment-Komponenten; gemessene Fünftel-Schwellen (ADR 0045).

### 6.2 Earnings-Termine

Unverändert Finnhub-Kalender (ADR 0017/0020) mit dreiwertigem Status und
Wochentagsnäherung — seit ADR 0030 mit **korrigierter Begründung**: Die
Näherung zählt Feiertage als Handelstage, der Filter schließt dadurch
tendenziell zu **selten** aus (riskante Richtung, nicht konservative). Die
Ablösung durch den TWS-Kalender ist gemessen verworfen (`liquidHours`
reicht 4 Handelstage voraus, gebraucht: 11; `cli calendar-reach`
wiederholt die Messung). Zeitzonen: Vergleich auf Datumsebene in
Börsenzeit; naive Zeitstempel via `ruff`-DTZ verboten. Neu seit Audit 1
wirkt der Termin zusätzlich in die Optionsanalyse (dritte Kopplung, ADR
0048) — strikt `<`, ein unbekannter Termin schließt nichts aus.
Historische Termine fürs Backtesting: bewusst verworfen (ADR 0042,
Look-ahead-Argument); die Abweichung steht als
`earnings_exclusion_applied: False` am Ergebnis und im Bericht.
Grenzfall-Tests vorhanden (Unit-Suite `domain/earnings`).

### 6.3 Technische Analyse

Unverändert `technical-v3` (Zonen aus Swing-Pivots mit Clustering, Trend,
ATR, Extrempunkte, CRV; ADR 0025) plus Technical Agent (prompt v3,
Schema-Pflichtfelder, `temperature=0` — seit dem 2026-08-30 **gemessen**:
zwei identische Läufe, gleiche sechs Einstufungen, abweichende Konfidenz
0,62/0,65; ADR 0026, Nachtrag). Look-ahead-Schutz: nur abgeschlossene
Kerzen, `StaleDataError` bei veralteter Zielkerze, Golden Master friert
das Verfahren ein. `min_touches`-Schwäche (E9) weiterhin offen, Bedingung
(weitere Realläufe) unverändert. Einfluss aufs Scoring: Chart-Setup- und
Chance-Risiko-Komponente aus den validierten Enum-Einstufungen — nie aus
Freitext.

### 6.4 Unternehmensmeldungen und LLM (Research Agent)

Zwei-Phasen-Architektur (Recherche mit serverseitiger
Websuche/Abruf-Schleife, dann Strukturierung), seit ADR 0029 mit
Quellenrang (`classify_source_rank`), deterministischer Abdeckung
(`derive_coverage`), Zitatgrenze 25 (reihum je Quelle gedeckelt),
Quellenalter roh (`page_age`). Prompt-Injection: fünf Sonden
(`TestPromptInjection`) und die dabei geschlossene Delimiter-Lücke
(`_neutralize_delimiters` — ein schließendes Tag im Recherchetext hätte
die Datenregion beendet). Kostenkontrolle: Budgetgrenzen je Symbol,
gemessene Läufe 0,52–0,58 USD; Prompt-Caching gemessen wirkungslos und
verworfen (94 % der Token entstehen innerhalb einer Anfrage).
Preislisten von Hand gepflegt (R8, offen). Bekannte Grenze, dokumentiert:
`fetch_allowed_domains` deckte im Messlauf keine der real gefundenen
Quellen ab — der Lauf machte null Abrufe; `BROAD` verlangt seit v2 keinen
erfolgreichen Abruf mehr. Modell-/Providerwahl ausschließlich
konfiguriert (Modellprofile mit `fallback_model`, das nur bei
technischem Versagen greift — ADR 0037); die Modellversion steht an jedem
Ergebnis. Fixture-Provider hält Tests und CI netzfrei.

### 6.5 Ranking und Scoring

`domain/scoring/`: Swing (6 Komponenten) und Investment (4), Gewichte in
`config/default.yaml` mit erzwungener Summe 1,0
(`_pruefe_gewichtssumme`), Umgewichtung fehlender Komponenten im
Aggregator, `INSUFFICIENT_DATA` unter 60 %, `LOW_COVERAGE`-Konfidenz
unter 80 %. Schwellen **gemessen** an 186–192 Titeln der Watchlist
(ADR 0045/0046/0048; Fünftelgrenzen in der Konfiguration, Messwerkzeuge
`cli ratings/options --watchlist --output` + `cli calibrate-scores`
laufen durch **denselben** Domain-Code). Begrenzende Regeln:
LOW_SAMPLE-Deckel 6,0, INSUFFICIENT_DATA-Stichprobe entfällt.
Empfehlungsstufe: Swing führt, Investment korrigiert ±1 Stufe,
Risiko-Caps (Fehlsignal HIGH → höchstens WATCH, Earnings unbekannt →
höchstens CANDIDATE), Herleitungsschritte am Ergebnis. Determinismus:
reine Funktionen, keine Uhr, Tiebreak in der Meldungssortierung.
Versionen `swing 1.2` / `long_term 1.0` / `recommendation 1.0` an jedem
Ergebnis. Doc 09 neu geschrieben, Widerspruch zu Doc 10 §6.11 aufgelöst
(ADR 0041). Tests: eigene Unit-Suite inkl. zweier nachgetragener
Gegenproben-Lücken (PR #59). **Die Enum→Teilwert-Abbildungen sind
Setzungen** — im Code dokumentiert, mangels produktiver Läufe nicht
kalibrierbar.

### 6.6 Telegram

Implementiert: `TelegramNotifier` (einzelner `sendMessage`-POST,
Timeout 10 s, Kürzung auf 4096 Zeichen **mit Kennzeichnung**,
Statuscode-Unterscheidung 401/429/5xx im Fehlertext **ohne** Token —
httpx' URL-haltiger Fehlertext wandert nicht weiter), `LoggingNotifier`
als ausgelieferter `dry_run`. Konfigurationsfehler (fehlende `chat_id`,
fehlender Token) brechen **vor** dem Lauf ab. Kein Nachrichten-Retry —
bewusst: Der Ergebnis-Versand darf den abgeschlossenen Lauf nicht
scheitern lassen (Fehler wird protokolliert); der Ausfall-**Alarm**
dagegen wird bis zur ersten erfolgreichen Zustellung bei jedem
Dispatcher-Start erneut versucht und dann per Vermerk dedupliziert.
Idempotenz auf Laufebene (ein Lauf je Handelstag) verhindert doppelte
Ergebnismeldungen. Inhalt fachlich fixiert in `domain/report/notification.py`
(ADR 0040/0047): Symbole, Signaltypen, beide Scores, Stufe,
Fehlsignalrisiko, Earnings-unbekannt-Hinweis; kein Freitext, keine
Kurse. Tests mit `httpx.MockTransport` inkl. Fehlerpfaden; keine echte
Nachricht im Audit. **Bis zur sicheren Nutzung fehlt nur Betrieb:**
`--notification-channel telegram --telegram-chat-id <id>` im
Aufgabenplanungs-Eintrag plus `ATA_NOTIFICATION_TOKEN` (Doc 14, Stufe H
und Zeile 718). Aus dem Repository nicht belegbar, ob das geschehen ist.

### 6.7 Dashboard

Unverändert Sprint-0-Platzhalter (`frontend/src/app/page.tsx`: „Das
Dashboard wird im Walking Skeleton (Sprint 1) aufgebaut." — die
Sprint-Angabe dort ist historisch). Kein API-Client, keine Route, keine
Auth. Vorentscheidungen fehlen: F12 (externer Zugriff — einzige offene
F-Frage, als blockierend für Sprint 6 geführt), Berücksichtigung von
Finnhub L8 (entschieden für die Telegram-Meldung in ADR 0047, nicht fürs
Dashboard), Deployment-Neubewertung Container (ADR 0036 vertagt sie
ausdrücklich auf den Dashboard-Sprint). `ATA_SESSION_SECRET` reserviert.
Kein öffentlich erreichbarer Dienst wurde im Audit gestartet.

## 7. Audit-1-Reconciliation

Maßgeblich: [Audit vom 2026-08-23](2026-08-23-repository-audit.md)
(einzige Fassung, keine konkurrierenden Versionen) und seine
[Nachverfolgung](2026-08-23-nachverfolgung.md) (Stand 2026-08-30). Die
Nachverfolgung führt Status und Belege; dieses Audit hat **jeden** Status
unabhängig gegen den heutigen Stand geprüft.

**Gesamtbild in Zahlen:** Maßnahmen: 12× `BEHOBEN UND VERIFIZIERT`, 2×
`TEILWEISE BEHOBEN` (M5, M14), 0× `WEITERHIN OFFEN`, 0× `REGRESSION`.
Entscheidungen: 10 entschieden (je ADR verifiziert), 3 `WEITERHIN OFFEN`
(E8, E9, E13). Risiken: 6 geschlossen (davon R7 extern verifiziert), 2
eingegrenzt (R5, R6), 2 offen (R8, R10). **Kein Status der
Nachverfolgung musste korrigiert werden** — die zwei Teil-Status
deklariert sie selbst, und die außerrepositorischen Anteile (M3, M13,
E5-Bedingung) kennzeichnet sie ausdrücklich als Auskunft.

### 7.1 Maßnahmen M1–M14

| ID | Befund/Maßnahme (Audit 1) | Prio | Gemeldet | **Verifiziert (Audit 2)** | Evidenz | Restrisiko / nächste Aktion |
|---|---|---|---|---|---|---|
| M1 | Doc 14 Stufe B: falscher Alembic-Head, F10-Zeile | P1 | erledigt | **BEHOBEN UND VERIFIZIERT** | Doc 14 prüft auf „aktuellen Head der Migrationskette" (Z. 114) statt einer festen ID — robust gegen die seither 8 neuen Migrationen; F10-Zeile verweist auf ADR 0024 (Z. 83) | keins |
| M2 | Projekt-`CLAUDE.md`: Gate-Tabelle wirkte sperrend | P1 | erledigt | **BEHOBEN UND VERIFIZIERT** | Gate-Abschnitt „Alle drei Gates sind entschieden … historisch, nicht mehr sperrend"; ADR 0014/0017/0021 verlinkt; drei gerichtete Kopplungen aktuell inkl. ADR 0048 | keins |
| M3 | E2 entscheiden, Tiefe messen, Backfill-Batch | P1 | erledigt | **BEHOBEN UND VERIFIZIERT** (Repo-Anteil) | ADR 0027/0028 (≥ 17,4 Jahre gemessen, `history_years: 5` bestätigt); `cli history-depth`/`deepen-history` + Use Cases + Tests; Doc 14 Zwischenschritt | Serverbestand (Lauf 2026-08-24 über die volle Watchlist) **NICHT VERIFIZIERBAR** — in der Nachverfolgung korrekt als Auskunft gekennzeichnet |
| M4 | E1 entscheiden (Backtest-Integration) | P1 | erledigt | **BEHOBEN UND VERIFIZIERT** | ADR 0038; `run_analysis._evaluate_backtest` auf der geladenen Serie; Migration `c4f81a6b2d90`; Persistenz in derselben Transaktion | keins |
| M5 | Golden Master auf eingefrorenem **Realdaten**-Ausschnitt | P2 | erledigt, mit Abweichung | **TEILWEISE BEHOBEN** | `tests/golden/` (15 Tests, grün, ohne Netz): volle deterministische Kette über zwei **erzeugte** Bar-Reihen; Begründung in `generate_bars.py`; `cli export-bars` + Doc 14 Zwischenschritt stehen bereit | Verhalten an echten Kursen (Lücken, Feiertage, Splits) weiterhin uneingefroren. Seit dem Tiefen-Backfill nicht mehr durch Datenmangel begründet → Realdaten-Fall ziehen (A2-M3) |
| M6 | Prompt-Injection-Test Research-Adapter | P2 | erledigt | **BEHOBEN UND VERIFIZIERT** | `TestPromptInjection` (5 Sonden); dabei gefundene Delimiter-Lücke geschlossen (`_neutralize_delimiters`, protokolliert) — Code + Test vorhanden, Suite grün | keins |
| M7 | E4: ADR zur Wochentagsnäherung | P2 | erledigt | **BEHOBEN UND VERIFIZIERT** | ADR 0030 (gestützt auf Kalendermessung, `cli calendar-reach`); riskante Fehlerrichtung im Kopfkommentar von `domain/earnings/calendar.py` — inklusive ausdrücklicher Korrektur der Audit-1-Fehlannahme „wirkt konservativ" | Restrisiko der Näherung bleibt bewusst bestehen und ist jetzt richtig beschriftet |
| M8 | E5-Paket Research-Qualität | P2 | erledigt | **BEHOBEN UND VERIFIZIERT** | ADR 0029; `SourceRank`/`derive_coverage`/`max_citations: 25`/Quellenalter im Code; Migration `a4c7e91f30b2`; zwei dokumentierte Vergleichsläufe (Qualität ✓, Kosten unverändert 0,52–0,58 USD) | Kostenniveau bleibt; einziger Hebel (`max_searches`) bewusst unangetastet |
| M9 | README/Roadmap-Status nachziehen | P3 | erledigt | **BEHOBEN UND VERIFIZIERT** | Die von Audit 1 monierten Stellen (Technical-Agent-Verifikation) sind nachgezogen | Der **heutige** Rückstand von README/Roadmap gegenüber Sprint 5 ist ein neuer Befund (A2-F002), keine Regression von M9 |
| M10 | Kopfvermerke Doc 01/02/04/05/06/07, signal-specification | P3 | erledigt | **BEHOBEN UND VERIFIZIERT** | Alle sechs Docs tragen den „Wozu dieses Dokument"-Kopf; `signal-specification.md`: „Status: Freigegeben (ADR 0010)" | Doc 08 blieb außen vor — damals korrekt (war `AKTUELL`), heute überholt (A2-F003) |
| M11 | Deployment-ADR (E6) + Doc 13 neu | P3 | erledigt | **BEHOBEN UND VERIFIZIERT** | ADR 0036 (nativer Windows-Betrieb, Container zum Dashboard-Sprint neu bewertet); Doc 13 vollständig neu, Redis-Widerspruch beseitigt | keins |
| M12 | ADR-Nachträge 0006/0009/0011 | P3 | erledigt | **BEHOBEN UND VERIFIZIERT** | `### Nachtrag`-Abschnitte in allen dreien; ADR-README-Übersicht führt die Ablösungen (0009→0031, 0020-L2/L3→0030) | keins |
| M13 | Python-Version des Servers klären | P3 | erledigt | **BEHOBEN UND VERIFIZIERT** (Doku-Anteil) | README/Doc 14 benennen konsistent 3.12 (Entwicklung) / 3.13 (Server); CI prüft beide | Serverversion selbst = Auskunft, **NICHT VERIFIZIERBAR** |
| M14 | Sammelposten P4 (`fallback_model`, temperature-Doppellauf, Agent-Pools, `pushover`, ungenutzte Secret-Felder) | P4 | teilweise | **TEILWEISE BEHOBEN** | Erledigt und verifiziert: getrennte Pools (ADR 0037; `AgentConcurrency`, `ExitStack`-Doppelpool in `run_analysis`), `fallback_model` gesetzt + Auslöser verengt (Konfiguration, ADR 0037), temperature gemessen (ADR 0026 Nachtrag). Offen und verifiziert offen: R8 (Preislisten „VON HAND GEPFLEGT", 2 Stellen in `config/default.yaml`), R10 (`pushover` im Schema ungebaut, mit Absicherungstest `test_pushover_ist_weiterhin_nicht_gebaut`); `ATA_MARKET_DATA_API_KEY` weiterhin ungenutzt mit veraltetem Kommentar (A2-F005) | Rest bewusst offen; Deklaration der Nachverfolgung stimmt |

### 7.2 Entscheidungen E1–E13

| ID | Gegenstand | Gemeldet | **Verifiziert** | Evidenz |
|---|---|---|---|---|
| E1 | Backtest in den Tageslauf | entschieden | **BEHOBEN UND VERIFIZIERT** | ADR 0038 + Code (s. M4) |
| E2 | Historientiefe | entschieden | **BEHOBEN UND VERIFIZIERT** | ADR 0027 (Weg a) + 0028 (Messung) |
| E3 | Historische Earnings (EDGAR 8-K) | entschieden (verworfen) | **BEHOBEN UND VERIFIZIERT** | ADR 0042 — Verwerfung mit Look-ahead-Begründung; R6 bleibt eingegrenzt, Kennzeichnung am Ergebnis vorhanden |
| E4 | Wochentagsnäherung | entschieden | **BEHOBEN UND VERIFIZIERT** | ADR 0030 (s. M7) |
| E5 | Research-Qualitätspaket | entschieden | **BEHOBEN UND VERIFIZIERT** | ADR 0029 (s. M8) |
| E6 | Deployment-Zielbild | entschieden | **BEHOBEN UND VERIFIZIERT** | ADR 0036 + Doc 13 (s. M11) |
| E7 | Inhalt der Ergebnis-Benachrichtigung | entschieden | **BEHOBEN UND VERIFIZIERT** | ADR 0040; durch ADR 0047 (Scores hinein) kontrolliert weiterentwickelt, Ablösung sauber vermerkt |
| E8 | F12: externer Dashboard-Zugriff/Auth | offen | **WEITERHIN OFFEN** | Letzte offene F-Frage (ADR-README); blockiert Sprint 6 |
| E9 | `min_touches` → Wendepunkt-Filter | offen | **WEITERHIN OFFEN** | ADR 0025; Bedingung (weitere Realläufe) unverändert |
| E10 | Required Checks | entschieden | **BEHOBEN UND VERIFIZIERT (extern)** | ADR 0031; GitHub-API: Schutz auf `main`+`dev`, 5 erzwungene Checks, PR-Pflicht, Force-Push/Delete gesperrt, `enforce_admins: false` = der beschlossene Notausgang; Repo öffentlich |
| E11 | Kursziele | entschieden (verworfen) | **BEHOBEN UND VERIFIZIERT** | ADR 0043 — dauerhaft zurückgestellt; stattdessen Analystenempfehlungen nachgebaut (Code + Migration + Tests) |
| E12 | Drei Kleinigkeiten | erledigt | **BEHOBEN UND VERIFIZIERT** | ① ADR 0037 + Konfiguration; ② ADR 0026 Nachtrag (gemessen 2026-08-30); ③ s. M13 |
| E13 | US-007 Chartmuster: bauen oder streichen | offen | **WEITERHIN OFFEN** | Keine Entscheidung als ADR; Doc 04 führt US-007 unverändert |

### 7.3 Risiken R1–R10

| ID | Risiko | Gemeldet | **Verifiziert** | Evidenz / Restrisiko |
|---|---|---|---|---|
| R1 | Kennzahlen suggerieren 5 J, Basis ~1 J | geschlossen | **BEHOBEN UND VERIFIZIERT** (Repo-Anteil) | ADR 0028 (Messung ≥ 17,4 J), Werkzeuge, Doc-14-Zwischenschritt; der aufgefüllte **Serverbestand** bleibt `NICHT VERIFIZIERBAR` |
| R2 | Kein Golden Master | geschlossen | **BEHOBEN UND VERIFIZIERT** | 15 Golden-Tests laufen im normalen `pytest` mit; Einschränkung s. M5 (synthetische Bars) |
| R3 | CLAUDE.md leitet Sessions fehl | geschlossen | **BEHOBEN UND VERIFIZIERT** | s. M2 |
| R4 | Doc 14 Stufe B bricht am falschen Head | geschlossen | **BEHOBEN UND VERIFIZIERT** | s. M1 — die Formulierung „aktueller Head" hat die 8 neuen Migrationen bereits schadlos überstanden |
| R5 | Research: Kostenstreuung + Belegqualität | eingegrenzt | **TEILWEISE BEHOBEN** (= eingegrenzt bestätigt) | Qualität behoben (ADR 0029, 2 Messläufe); Kosten stabil, Hebel gemessen nicht vorhanden; Preislisten-Pflege bleibt manuell (R8) |
| R6 | Backtest ohne historischen Earnings-Filter | eingegrenzt | **TEILWEISE BEHOBEN** (= eingegrenzt bestätigt) | `earnings_exclusion_applied` an `BacktestResult` verifiziert; Entscheidung ADR 0042 macht die Eingrenzung dauerhaft und umkehrbar |
| R7 | Kein Merge-Schutz | geschlossen | **BEHOBEN UND VERIFIZIERT (extern)** | s. E10 — in diesem Audit erstmals per GitHub-API belegt, was Audit 1 nur aus dem Repo nicht sehen konnte |
| R8 | Preislisten veralten still | offen | **WEITERHIN OFFEN** | `research.pricing`/`technical_agent.pricing` in `config/default.yaml`, beide „VON HAND GEPFLEGT"; zusätzlich veraltet derselbe Mechanismus jetzt auch die **gemessenen Score-Schwellen** (A2-F006) |
| R9 | Ein Thread-Pool für beide Agenten | geschlossen | **BEHOBEN UND VERIFIZIERT** | ADR 0037; `AgentConcurrency` (2/4), zwei `ThreadPoolExecutor` im `ExitStack`, eigene Konfigurationswerte je Agent |
| R10 | `pushover` ungebaut im Schema | offen | **WEITERHIN OFFEN** | `build_notifier` lehnt ab; als bewusster Zustand getestet |

### 7.4 Prozessfragen aus dem Auditauftrag

- **Erledigt ohne Akzeptanzkriterien?** Nein — jede M-Zeile der
  Nachverfolgung verweist auf ADR/PR/Commit/Datei; die DoD-Lücken (M5,
  M3-Serverlauf) sind dort selbst ausgewiesen.
- **Nur Doku angepasst statt Code?** Nein. Umgekehrt kommt es vor: Code
  gemergt, Doku hinkt (A2-F002).
- **Code ohne Tests geändert?** Nicht festgestellt; die PR-Serie zeigt
  durchgehend Test-Commits, und mehrere „Gegenproben" haben nachweislich
  Lücken gefunden und geschlossen (PR #58/#59).
- **Symptom statt Ursache behoben?** Ein Gegenbeispiel-Muster ist
  positiv dokumentiert (ADR 0044: Schwärzung an der Senke statt an der
  einzelnen Fehlermeldung; zusätzlich an der Entstehung, PR #52). Offen
  bleibt die Wurzel des Finnhub-Falls (Token im Query-Parameter statt
  Header) — im ADR ausdrücklich als besserer, ungetesteter Weg benannt.
- **Korrekturen mit neuen Problemen?** Eine Kette ist belegt und wurde
  intern gefunden: Die Options-Verdrahtung in `dispatch` fehlte zunächst
  (behoben in `1f65472`, dem jüngsten Commit).
- **Audit-Ergebnisse normativ festgehalten?** Ja — durchgehend als ADRs
  (0027–0031, 0036–0038, 0040, 0042, 0043); die Nachverfolgung enthält
  bewusst nur Zeiger.

## 8. Neue Audit-2-Befunde

Keine P0-, keine P1-Befunde. Echte Fehler wurden keine gefunden; alle
Befunde sind Prozess-, Dokumentations- oder Pflegepunkte.

**A2-F001 — Optionsanalyse: fertig gebaut, aber ohne Review, Merge und Serverprobe**
- Kategorie: fehlender Abschluss-Schritt (kein Fehler im Code)
- Evidenz: Branch `feature/optionsanalyse` = `dev` + 14 Commits; kein
  PR offen; in der Commit-Serie fehlt der projektübliche
  „Befunde der unabhängigen Review"-Commit; der jüngste Commit
  (`1f65472`) behebt einen Verdrahtungsfehler genau im End-to-End-Pfad
  (`cli dispatch` kannte `--options-provider` nicht); ADR 0048 nennt den
  Effekt des Berichtstermin-Ausschlusses im Tageslauf als „noch nicht
  gemessen". Der einzige belegte Live-Kontakt ist die Einzelmessung vom
  2026-08-31 (Greeks um 13:02 ET) und der Watchlist-Messlauf über `cli
  options` — nicht der Tageslauf-Pfad `dispatch → options`.
- Komponente: `domain/options/`, `infrastructure/ibkr/option_chain.py`, `cli.py`
- Auswirkung: Der wertvollste neue Baustein ist im Zielzweig nicht
  angekommen; ein unentdeckter Integrationsfehler im Serverlauf bliebe
  bis zum ersten echten Abend unsichtbar. Wahrscheinlichkeit: mittel.
  Schweregrad: **P2**. Vertrauen: hoch. Beziehung zu Audit 1: keine
  (neues Feature).
- Empfehlung: Unabhängige Review, PR nach `dev`, danach Einzelprobe
  `cli options --provider ibkr --symbols <2–3>` und ein begleiteter
  Tageslauf. DoD: PR gemergt, Review-Befunde eingearbeitet, ein
  Tageslauf mit `--options-provider ibkr` hat Optionsdaten persistiert.
  Größe: **S**. Menschliche Entscheidung: Abnahme durch den
  Projektverantwortlichen (gemäß gelebtem „PR erst nach Abnahme").

**A2-F002 — README und Roadmap führen Sprint 5 als „noch nicht gebaut"**
- Kategorie: Dokumentationsabweichung (Wiederholung des Musters R3/M9)
- Evidenz: `README.md` („Sprint 5 ist entschieden, aber noch nicht
  gebaut"; „Noch offen"-Tabelle listet Scoring Engine und Optionsanalyse
  als ausstehend; zuletzt geändert 2026-08-30) und `docs/03 - Roadmap.md`
  (Sprint 5 ohne „umgesetzt"-Vermerke) gegen: PR #58/#59 in `dev`
  gemergt am 2026-08-31, ADR 0045–0047, rechnende Scores in
  `config/default.yaml`.
- Auswirkung: Jede neue Arbeits-Session und jeder Leser startet mit
  falschem Projektstand — exakt die Wirkung, die Audit 1 bei R3 als
  „wichtigste einzelne Doku-Korrektur" einstufte, nur eine Ebene tiefer.
  Schweregrad: **P3**. Vertrauen: hoch. Beziehung: Muster von M9/R3
  (dort behoben; hier neu entstanden, keine Regression derselben Stelle).
- Empfehlung: README-Projektstand + „Noch offen"-Tabelle + Roadmap
  Sprint 5 nachziehen — sinnvollerweise im Options-PR (A2-F001), dann
  stimmt beides in einem Schritt. DoD: keine Statusaussage widerspricht
  `dev`. Größe: **XS–S**.

**A2-F003 — Doc 08 ist das einzige Fachdokument ohne Kopfvermerk und von ADR 0048 überholt**
- Kategorie: Dokumentationsabweichung
- Evidenz: `docs/08 - Options Analysis.md` beginnt ohne den
  M10-Kopfvermerk; Inhalt ist die Vorplanungs-Skizze (Beispiel-Laufzeit
  45 Tage vs. beschlossenes Ziel 35 im Fenster 21–60; „Wahrscheinlichkeit
  der Andienung" ohne den Näherungsvorbehalt aus ADR 0048;
  „Volatilität" als Analyse-Parameter, tatsächlich ist die implizite
  Volatilität nur Anzeigefeld). Audit 1 stufte Doc 08 als `AKTUELL
  (Skizze)` — das war korrekt, ist aber seit ADR 0048 überholt.
- Schweregrad: **P3**. Größe: **XS**. Empfehlung: Kopfvermerk nach dem
  Muster der übrigen Docs („maßgeblich: ADR 0048, Doc 10 §6.10"). DoD:
  Doc 08 sagt, was maßgeblich ist.

**A2-F004 — Veralteter Konfigurationskommentar zum 5-Jahres-Backfill**
- Kategorie: Dokumentationsabweichung
- Evidenz: `config/default.yaml`, Kommentar an
  `market_data.ibkr.history_duration`: „Der 5-Jahres-Backfill laeuft
  spaeter als eigener Batch-Job mit Chunking (ADR 0014, E3)" —
  `cli deepen-history` existiert seit ADR 0028; „später" ist vorbei.
- Schweregrad: **P4**. Größe: **XS**. Empfehlung: Kommentar auf
  `deepen-history`/ADR 0028 umstellen. Beziehung: Folge von M3.

**A2-F005 — Ungenutzte Secret-Felder mit veralteten Kommentaren**
- Kategorie: technische Schuld (Rest aus M14)
- Evidenz: `.env.example`: `ATA_MARKET_DATA_API_KEY` („Auswahl per ADR
  (F9)" — entschieden ist IBKR, das keinen Schlüssel kennt),
  `ATA_LLM_API_KEY`-Kommentar ähnlich datiert („werden per ADR
  festgelegt" — ADR 0021 existiert), `ATA_SESSION_SECRET` reserviert
  fürs Dashboard.
- Schweregrad: **P4**. Größe: **XS**. Empfehlung: im M14-Rest
  mitkommentieren oder entfernen; `ATA_SESSION_SECRET` bleibt (Sprint 6).

**A2-F006 — Gemessene Schwellen ohne Pflegeturnus**
- Kategorie: Produktentscheidung / Betriebsprozess
- Evidenz: Die Fünftelgrenzen in `config/default.yaml` stammen aus
  Messläufen vom 2026-08-31. ADR 0048 sagt selbst: die Options-Schwellen
  sind „kurzlebiger als die übrigen … Die Neumessung gehört zur Pflege,
  und hier häufiger" — aber weder Doc 14 noch ein ADR nennt Auslöser
  oder Turnus; derselbe stille Alterungsmechanismus wie bei R8
  (Preislisten), nur mit fachlicher Wirkung auf den Score.
- Auswirkung: Nach einer Volatilitätsverschiebung bewertet die
  Options-Komponente systematisch zu hoch oder zu niedrig — sichtbar
  erst, wenn jemand nachmisst. Schweregrad: **P3**. Vertrauen: hoch.
- Empfehlung: Entscheidung E-A2-1 (Abschnitt 14): Turnus oder Auslöser
  festlegen; die Werkzeuge (`cli options --watchlist --output`,
  `cli calibrate-scores`) existieren bereits. Größe: **S** (Doku +
  ggf. Doc-14-Abschnitt).

**A2-F007 — Widersprüchliche Repository-Aussagen zum Betriebszustand**
- Kategorie: Dokumentationsinkonsistenz an einer nicht verifizierbaren Stelle
- Evidenz: Nachverfolgung (Ergänzung 2026-08-23): „Der Research Agent
  läuft im täglichen Scharfbetrieb" (Auskunft). Dagegen
  `domain/scoring/swing.py` (2026-08-31, Docstring): „Es gibt bislang
  keinen produktiven Tageslauf, aus dem sich eine Verteilung ergäbe
  (ADR 0045, Abschnitt 4)." Beide Aussagen können sich auf
  Verschiedenes beziehen (manuell angestoßene Läufe vs. automatische
  Aufgabenplanung); aus dem Repository ist das nicht auflösbar.
- Auswirkung: Der nächste Leser (oder das nächste Audit) weiß nicht,
  welche Betriebsannahme gilt; Kalibrier-Entscheidungen (A2-F006, E9)
  hängen genau daran. Schweregrad: **P3**. Vertrauen: hoch (dass der
  Widerspruch besteht), `NICHT VERIFIZIERBAR` (welche Seite stimmt).
- Empfehlung: Eine Klarstellungszeile des Projektverantwortlichen —
  sinnvoll in Doc 14 („Betriebszustand seit …: Aufgabenplanung
  aktiv/inaktiv, scharfe Anbieter: …"). Größe: **XS**. Menschliche
  Entscheidung: nur die Auskunft selbst.

**A2-F008 — Contract-Tests gegen eingefrorene Originalantworten: nur EDGAR**
- Kategorie: Testlücke (Fortschreibung einer Audit-1-Beobachtung, dort ohne Maßnahmen-ID)
- Evidenz: EDGAR hat einen echten eingefrorenen Ausschnitt
  (`tests/unit/infrastructure/edgar/data/companyfacts-ausschnitt.json`
  mit `HERKUNFT.md`). Finnhub (Kalender **und** Recommendations), IBKR
  (Bars, Optionskette) und Anthropic testen weiterhin gegen im Test
  nachgebaute Antworten (`httpx.MockTransport`, konstruiertes JSON).
- Auswirkung: Eine stille Formatänderung eines Anbieters fiele erst im
  Betrieb auf. Schweregrad: **P3** (durch Statusmodelle wie
  `UNAVAILABLE`/`invalid_data` gut abgefedert). Größe: **S–M** je
  Anbieter. Empfehlung: je Anbieter eine echte, anonymisierte Antwort
  einfrieren, beginnend mit den zwei neuen Finnhub-/IBKR-Options-Pfaden.

**Positiv festzuhalten** (gehört zur ehrlichen Bilanz): Die zentrale
Regel — KI verändert keine Signale — ist weiterhin strukturell verankert
und wurde mit jedem neuen Modul konsequent fortgeschrieben (getrennte
Spaltensätze, Enums statt Freitext im Scoring, Berichts-Begründungen
gerechnet statt formuliert). Fehlende Werte bestrafen nirgends. Der
Messlauf-durch-denselben-Code-Grundsatz (ADR 0045/0046/0048) beseitigt
eine ganze Fehlerklasse. Die Review-Schleife hat nachweislich Fehler
gefunden (Gegenproben-Commits), und ADR 0044 dokumentiert einen selbst
gefundenen, realen Secret-Leak samt Zwei-Ebenen-Fix.

## 9. Requirements-Traceability

### 9.1 Produktanforderungen (Doc 02; Kopfvermerk verweist auf Doc 10/ADRs)

| Req | Kurzbeschreibung | Status | Implementierungs-/Testevidenz | Abweichung / Aktion |
|---|---|---|---|---|
| 2.1 | Tägliche automatische Analyse 12:45 ET | **TEILWEISE ERFÜLLT** | `cli dispatch`, Dispatcher-Tests; Scharfbetrieb am Server `NICHT VERIFIZIERBAR` (A2-F007) | Betriebsauskunft einholen |
| 2.2 | TradingView als Datenquelle | **WIDERSPRÜCHLICH** (bewusst überholt) | NO_GO ADR 0012; IBKR ADR 0014; Kopfvermerk vorhanden | keine — Doc-02-Kopf regelt es |
| 2.3 | Screener 3 Signale, 2-aus-3 | **ERFÜLLT UND VERIFIZIERT** | `domain/screening/`, Unit-Suite, Golden Master | — |
| 2.4 | Earnings-Ausschluss 10–20 Kerzen | **ERFÜLLT UND VERIFIZIERT** | `domain/earnings/`, Finnhub-Adapter, Tests | Statusmodell reduziert (ADR 0020), Näherung riskant beschriftet (ADR 0030) |
| 2.5 | Backtesting 5 Jahre, Kennzahlen | **TEILWEISE ERFÜLLT** | Replay+Cooldown+Konfidenz, im Tageslauf (ADR 0038); 5-J-Anspruch gemessen erreichbar (ADR 0028) | Kennzahlen-Teilmenge besteht fort (ohne Stddev/MAE/MFE/beste-schlechteste); Serverbestand n. v. |
| 2.6 | KI-Research | **ERFÜLLT UND VERIFIZIERT** (mit dokumentierten Grenzen) | ADR 0029-Felder im Code, 2 Messläufe | Abruf-Allowlist deckt reale Treffer kaum (bekannt) |
| 2.7 | Technische Analyse | **ERFÜLLT UND VERIFIZIERT** | technical-v3 + Agent, verifiziert an echten Kursen | „Chartformationen" bewusst nicht (E13 offen) |
| 2.8 | Optionsanalyse | **TEILWEISE ERFÜLLT** | Vollständig auf diesem Branch (Code/Tests/ADR 0048) | Merge/Review/Serverprobe offen (A2-F001) — auf `dev`: NICHT ERFÜLLT |
| 2.9 | Zwei Scores | **ERFÜLLT UND VERIFIZIERT** | `domain/scoring/`, gemessene Schwellen, Tests | Statuswechsel seit Audit 1 (dort: nicht implementiert) |
| 2.10 | Dauerhafte Speicherung | **ERFÜLLT UND VERIFIZIERT** (für Existierendes) | 17 Migrationen, Unveränderlichkeit, 138 Integrationstests | „spätere Performanceentwicklung" wird weiterhin nicht nachgeführt |
| 2.11 | Dashboard | **NICHT ERFÜLLT** | Platzhalter | Sprint 6; blockiert von E8 |
| 2.12 | Ergebnis-Benachrichtigung | **ERFÜLLT UND VERIFIZIERT** (Code) | `render_notification` + `TelegramNotifier` + Tests (ADR 0040/0047) | Statuswechsel seit Audit 1; Scharfschaltung n. v. |

### 9.2 Architekturfragen Doc 10 §19

F1–F11, F13: entschieden und (wo bauend) umgesetzt — unverändert bzw.
seit Audit 1 vervollständigt (F8/F9-Optionsteil durch ADR 0048, F9-Kursziele
durch ADR 0043 dauerhaft verworfen, F10-Inhalt durch ADR 0040/0047).
**F12 (externer Dashboard-Zugriff): einzige offene Frage** — deckungsgleich
mit E8.

### 9.3 User Stories (Doc 04)

US-001 ✅ · US-002 ◐ überholt (Export-Dateien) · US-003/004 ✅ ·
US-005 ✅ (seit ADR 0038 im Tageslauf, 5-J-Anspruch entschieden) ·
US-006 ◐→✅ deterministisch (Research + Fundamentalkennzahlen; KI-Einordnung
der Fundamentaldaten offen) · US-007 ◐ (ohne Chartmuster, E13) ·
US-008 ◐ (Optionen: Branch-Stand) · US-009 ✅ (Scores) ·
US-010 ◐ (Speicherung ✅, spätere Kursentwicklung ✖).

## 10. ADR-Abgleich

**ADRs 0001–0026** (von Audit 1 einzeln geprüft): Alle
Statusfortschreibungen seit Audit 1 sind sauber vollzogen und
stichprobenhaft verifiziert — 0009 → abgelöst durch 0031; 0011 →
Nachtrag „Verhalten besteht nicht mehr" (171 CI-Läufe); 0020 → L2/L3
durch 0030 abgelöst; 0006 → Nachtrag zu Stufe 2/0019; 0026 → Nachtrag
temperature-Messung. Keine stillen Widersprüche gefunden; die
Audit-1-Empfehlungen zu diesen Nachträgen (M12) sind vollständig
umgesetzt.

**ADRs 0027–0048** (neu seit Audit 1, alle „Angenommen", alle einzeln geprüft):

| ADR | Gegenstand | Erkennbarer Status | Evidenz (Code/Tests) | Anmerkung |
|---|---|---|---|---|
| 0027 | Historientiefe messen vor Anspruch (E2) | umgesetzt | `cli history-depth`, `measure_history_depth.py` | — |
| 0028 | Historientiefe gemessen, Tiefen-Backfill | umgesetzt | `cli deepen-history`, `deepen_history.py`; Doc 14 | Serverlauf n. v. (s. M3) |
| 0029 | Research-Qualität | umgesetzt | `sources.py` (Rang/Abdeckung), Migration, Tests | ersetzt Teile von 0023 — vermerkt |
| 0030 | Wochentagsnäherung bleibt | umgesetzt | `calendar.py`-Kopf, `cli calendar-reach` | entkräftet 0020-L3 — vermerkt |
| 0031 | Merge-Schutz aktiv | **extern verifiziert** | GitHub-API: 5 Checks, PR-Pflicht | löst 0009 ab — vermerkt |
| 0032–0035 | Fundamentalanalyse (Quelle, TTM, Schranken, Tageslauf) | umgesetzt | `domain/fundamentals/`, `infrastructure/edgar/`, Migration, 63+ Tests, Tageslauf-Verdrahtung | 0033 löst 0032-E3 ab — vermerkt; offene L-Punkte (Vergleichsgruppe, Zwei-Stichtags-Kennzahlen) im ADR-README geführt |
| 0036 | Nativer Windows-Betrieb | umgesetzt (Doku) | Doc 13 neu, Doc 10 §14 nachgezogen | Container-Neubewertung an Sprint 6 gebunden |
| 0037 | Getrennte Pools, enges Ausweichmodell | umgesetzt | `AgentConcurrency`, Doppel-Pool, `fallback_model` je Profil | — |
| 0038 | Backtest im Tageslauf | umgesetzt | `_evaluate_backtest`, Migration, Transaktion | — |
| 0039 | Report Generator | umgesetzt | `domain/report/` (18 `ReportSection`-Punkte, `report-v2`), `cli report`, `stock_reports` | Berichtsschema-Version existiert erstmals |
| 0040 | Inhalt der Ergebnismeldung | umgesetzt | `render_notification` | bewusste Lockerung von 0024 — vermerkt |
| 0041 | Score-Komponenten und Gewichte | umgesetzt | `swing.py`/`long_term.py`, Gewichte + Summenvalidierung | löst Doc-09/Doc-10-Widerspruch — Doc 09 neu |
| 0042 | Kein historischer Earnings-Filter | umgesetzt (Verwerfung) | `earnings_exclusion_applied` | R6 dauerhaft eingegrenzt, umkehrbar |
| 0043 | Analystenempfehlungen statt Kurszielen | umgesetzt | `domain/analysts/`, `finnhub/recommendations.py`, Migration, `cli ratings` | holt eine seit ADR 0017 offene Zusage nach |
| 0044 | Schwärzung an der Log-Senke | umgesetzt | `secret_redaction.py`, Formatter-Anbindung, Tests | Wurzel (Token im Query statt Header) bewusst offen |
| 0045 | Schwellen der Score-Teilwerte | umgesetzt | Konfigurations-Schwellen (gemessen an 191 Titeln), `cli calibrate-scores` | Pflegeturnus offen (A2-F006) |
| 0046 | Empfehlungsstufe | umgesetzt | `recommendation.py`, Caps, Herleitung am Ergebnis | — |
| 0047 | Scores in der Ergebnismeldung | umgesetzt | `notification.py` (Sortierung, Striche statt Nullen) | löst 0040 punktuell ab — vermerkt; entscheidet Finnhub L8 für die Meldung |
| 0048 | Optionsanalyse (CSP) | umgesetzt **auf diesem Branch** | `domain/options/`, `option_chain.py`, Migration `f4a71c9e2d38`, Options-Schwellen | dritte Kopplung in CLAUDE.md nachgezogen; Merge offen (A2-F001) |

**Implementierte Architekturentscheidungen ohne ADR:** keine gefunden —
die Lücke aus Audit 1 (Deployment) ist mit ADR 0036 geschlossen.
**Akzeptierte, aber nicht umgesetzte ADRs:** keine; 0042/0043 sind
bewusste Verwerfungen mit Umsetzung des Alternativwegs.
**Blockierend für Telegram:** nichts (entschieden bis hin zum Inhalt).
**Blockierend für das Dashboard:** F12/E8 (unverändert).

## 11. Dokumentationsstatus

| Datei | Klassifikation | Befund |
|---|---|---|
| `README.md` | **TEILWEISE VERALTET** | Projektstand-/„Noch offen"-Abschnitte hinken Sprint 5 hinterher (A2-F002); Rest hochwertig und aktuell |
| `CLAUDE.md` (Projekt) | **AKTUELL** | Gates historisch, drei Kopplungen inkl. ADR 0048, Golden-Master-Abschnitt — die wichtigste Steuerdatei ist auf Stand |
| Doc 01/02/04/05/06/07 | **AKTUELL** (als beschriftetes Soll) | Kopfvermerke vorhanden (M10); Inhalte teils historisch, aber als solche gekennzeichnet |
| Doc 03 Roadmap | **TEILWEISE VERALTET** | Sprint 5 ohne Umsetzt-Vermerke (A2-F002) |
| Doc 08 Options | **TEILWEISE VERALTET** | Einziges Fachdokument ohne Kopfvermerk; von ADR 0048 in Details überholt (A2-F003) |
| Doc 09 Scoring | **AKTUELL** | Neu geschrieben; Kopf verweist auf ADR 0041 und markiert die alte Fassung als überholt |
| Doc 10 System Architecture | **AKTUELL** (maßgebliches Zielbild) | §6.10/6.11/6.13/§14 nachgezogen; §15 (Backup) weiterhin reines Soll |
| Doc 11 API-Design | **VERALTET** (bewusst) | unverändert bis zum API-/Dashboard-Sprint zurückgestellt (ADR 0001) |
| Doc 12 | **REDUNDANT (ok)** | historisches Original |
| Doc 13 Deployment | **AKTUELL** | neu (M11); Redis-/Container-Widersprüche beseitigt |
| Doc 14 Inbetriebnahme | **AKTUELL** | Head-Prüfung robust, produktiver Dispatch-Befehl inkl. aller sechs Anbieterschalter, Zwischenschritte für alle Messwerkzeuge; kein Backup-Abschnitt (folgt dem offenen Doc-10-§15) |
| `docs/adr/README.md` | **AKTUELL** | 48 Einträge, Ablösungen und offene Punkte sauber |
| `docs/requirements/*` | **AKTUELL** | unverändert bis auf `signal-specification.md` (Kopf „Freigegeben") |
| `docs/audits/*` | **AKTUELL** | Audit 1 eingefroren, Nachverfolgung gepflegt (Stand 2026-08-30) |
| `config/default.yaml` (Kommentare) | **TEILWEISE VERALTET** | ein überholter Kommentar (A2-F004); sonst vorbildlich begründete Werte |
| `.env.example` | **TEILWEISE VERALTET** | zwei überholte Kommentarzeilen (A2-F005) |
| `spikes/*` | **AKTUELL** | eingefrorene Nachweisartefakte |

Interne Links: stichprobenhaft geprüft (ADR-Querverweise,
Audit-Verzeichnis, Doc-14-Verweise) — funktionierend; die in diesem
Bericht neu angelegten relativen Links zeigen auf existierende Dateien.

## 12. Tests und ausgeführte Befehle

Alle Prüfungen liefen lokal auf dem Entwicklungsrechner, ohne externe
Seiteneffekte. Die Integrationstests liefen gegen den bereits laufenden
lokalen Testcontainer `ata-postgres-test` (Port 55432) — eine
Wegwerf-Testdatenbank laut README, keine Produktionsdaten.

| # | Befehl (Kurzform) | Zweck | Ergebnis |
|---|---|---|---|
| 1 | `git rev-parse` / `status --porcelain` / `log` / `branch -vv` | Baseline: Branch, SHA, sauberer Tree, 130 Commits seit `f61f316`, Push-Stand | dokumentiert in Abschnitt 1 |
| 2 | `TEST_DATABASE_URL=… pytest` (komplett, `backend/`) | gesamte Suite inkl. Integration + Golden Master | **grün** (Exit 0), 56 s; einzige Warnung: bekannte Starlette-Deprecation (vorbestehend, harmlos) |
| 3 | `pytest --collect-only -q` je Kategorie | Inventar | **1567 Unit / 138 Integration / 38 Architektur / 15 Golden = 1758** |
| 4 | `ruff check .` | Linting (inkl. DTZ-Regeln) | **All checks passed** |
| 5 | `mypy src tests` (strict) | Typprüfung | **Success, 224 Dateien** (Audit 1: 153) |
| 6 | `pytest ../spikes/resc-schema/tests ../spikes/earnings-anbieter/tests` | eingefrorene Spike-Sonden (offline) | **42 passed** (0,14 s) |
| 7 | `alembic heads` / `history` | Migrationskette | Head `f4a71c9e2d38`, **linear**, 17 Migrationen, keine Dubletten |
| 8 | `npm run lint` / `typecheck` / `build` (`frontend/`) | Frontend-Prüfkette | **alle grün** |
| 9 | `gh api repos/…/branches/{dev,main}/protection` und `…/repos/…` (read-only) | R7/E10-Verifikation | Schutz aktiv: 5 erzwungene Checks, PR-Pflicht, Force-Push/Delete gesperrt, `enforce_admins: false`; Repo `public` |
| 10 | `gh pr list --state merged` (read-only) | PR-Historie #30–#59 | deckungsgleich mit Nachverfolgung und Commit-Historie |
| 11 | `grep -rE '<Secret-Muster>' backend/src config docs frontend/src` + `git ls-files \| grep '^\.env$'` | Secret-Suche (nur Trefferzahl, keine Werte) | **0 Treffer**; `.env` nicht eingecheckt, gitignored |
| 12 | Gezielte Code-/Doku-Lektüre | Verifikation je Maßnahme/Feature | Fundstellen in den Abschnitten 5–11 |

**Nicht ausgeführt** (Begründung: Auditvorgabe — keine produktiven
externen Aufrufe, keine Credentials, keine Kosten): alle Läufe gegen
TWS, Finnhub, EDGAR, Anthropic, Telegram. Sichere Anleitung je Schritt:
Doc 14 (Stufen und Zwischenschritte; die Einzelproben `cli
ratings`/`fundamental` sind kostenfrei, `research` ~0,6 USD je Titel).

**Bewertung der Aussagekraft:** Die Suite ist breit (Verfahren, Adapter
mit gemockten Transporten, Persistenz gegen echtes PostgreSQL,
Architekturgrenzen, Golden Master) und hat in der jüngsten Historie
nachweislich Fehler gefunden. Fachlich zu dünn abgesichert bleiben:
Verhalten der deterministischen Kette an **echten** Kursreihen (M5-Rest),
Anbieter-**Formate** (nur EDGAR eingefroren, A2-F008) und der
End-to-End-Pfad `dispatch → options` gegen die echte TWS (A2-F001).
Nicht vorhandene Tests: Dashboard (kein Testgegenstand vorhanden),
Backup/Restore (kein Verfahren vorhanden).

## 13. Sicherheit und Betriebsreife

**Secrets:** Sauber — ausschließlich `ATA_*`-Umgebungsvariablen,
`SecretStr`, CI-Checks (`.env`-Verbot, Schlüsselwort-Scan), seit ADR 0044
zusätzlich Schwärzung jeder Logzeile an der Senke plus Schwärzung an der
Entstehung (PR #52); EDGAR-Kontaktadresse aus der öffentlichen
Konfiguration entfernt (PR #48); Telegram-Token wandert in keinem
Fehlertext mit. Audit-Scan ohne Treffer. Restpunkt: Finnhub-Token
weiterhin als Query-Parameter (Header-Umstellung als besserer Weg im ADR
benannt, ungetestet).

**AuthN/AuthZ und Netzexposition:** REST-API ohne Authentifizierung —
akzeptabel, solange sie nur lokal läuft; **vor jeder Exposition steht
E8** (so auch ADR 0022-Deployment-Gate). Kein öffentlich erreichbarer
Dienst im Repository konfiguriert. GitHub-seitig: öffentliches
Repository mit aktivem Merge-Schutz und (laut Nachverfolgung) Secret
Scanning + Push Protection.

**Input-Validierung:** Konfiguration `extra="forbid"` mit
Querbezugs- und Summenprüfungen; API über Pydantic-Schemas;
Anbieterantworten laufen in Statusmodelle (`invalid_data` statt
Absturz); Research-Fremdtext als Daten mit Delimiter-Neutralisierung und
Injektionstests; KI-Ausgaben gegen Pflichtfeld-Schemata.

**Dependency-Risiken:** Lock-Dateien mit Hash-Verifikation
(`--require-hashes`), universell erzeugt; `npm ci`. Eine automatisierte
Vulnerability-Prüfung (z. B. `pip-audit`, Dependabot) ist **nicht**
eingerichtet — unverändert seit Audit 1, dort nicht als Maßnahme
geführt.

**LLM-Risiken:** Prompt-Injection getestet (M6); Freitext erreicht
weder Scores noch Statusfelder; Kostenbremsen mehrstufig; Preislisten
manuell (R8). Modell-Identifier laufen gegen einen sich extern
ändernden Katalog — im Kommentar der Konfiguration als Prüfpunkt vor
Produktivläufen benannt.

**Backup/Restore/Recovery:** **Größte Betriebsreife-Lücke, unverändert.**
Doc 10 §15 fordert tägliche Sicherung, Restore-Tests, externe Ablage —
nichts davon existiert, Doc 14 kennt keinen Sicherungsabschnitt. Der
Wiederanlauf nach Ausfall ist dagegen gut gelöst (idempotenter
Dispatcher, resumierbarer Backfill, Nachholfrist, Alarm).

**Scheduler-/Job-Idempotenz:** verifiziert (Advisory-Lock,
`dispatcher_runs`, `is_done`, Alarm-Deduplizierung, idempotenter
Backfill über `(symbol, start)`).

**Monitoring/Alarmierung:** Telegram-Ausfallalarm + Ergebnismeldung;
strukturierte JSON-Logs; keine Metriken, kein Provider-Status in der
Readiness, Kosten nur im Log — unverändert `TEILWEISE`.

**Kosten-/Ratenkontrolle extern:** IBKR-Pacing, Finnhub-Drossel
(gemessen nachjustiert), EDGAR-Drossel, Anthropic-Budgets je Symbol —
durchgehend konfiguriert und getestet (gemockt).

**Umgebungstrennung:** Ausgeliefert ist alles `fixture`/`dry_run`;
scharf geschaltet wird je Lauf über Argumente in der Aufgabenplanung —
saubere Trennung ohne lokale Diffs auf dem Server.

**Was einen Produktivbetrieb heute blockieren würde:** nichts
Technisches im Repository. Die drei realen Lücken sind Backup/Restore
(P2 der Maßnahmenliste), die unbelegte Serverkonfiguration
(A2-F007) und — für die Optionsanalyse — der fehlende Merge samt
Serverprobe (A2-F001).

## 14. Offene Entscheidungen

Nur Punkte, die tatsächlich der Projektverantwortliche entscheiden muss.

**E8 (aus Audit 1) — Externer Dashboard-Zugriff und Authentifizierung (F12).**
Warum jetzt relevant: einzige offene Architekturfrage; blockiert
Sprint 6 vollständig (API-Ausbau, Auth, Exposition, Container-Frage aus
ADR 0036 hängen daran). Optionen: (a) nur LAN/VPN ohne eigene Auth —
minimal, kein Angriffsvektor von außen, Telegram bleibt der
Fernzugang; (b) extern erreichbar mit Auth (Reverse-Proxy + Login) —
voller Nutzen, deutlich mehr Sicherheitsarbeit, berührt Finnhub L8;
(c) Auslieferung an ein Endgerät ohne Server-Exposition (z. B. lokaler
Export). Empfehlung: **(a) als MVP**, (b) erst nach stabilem Betrieb.
Konsequenz der Vertagung: Sprint 6 kann nicht beginnen. Priorität:
**blockierend für Sprint 6, sonst keine Eile.**

**E9 (aus Audit 1) — `min_touches` → Wendepunkt-Filter.** Bedingung
(mehrere Realläufe) ist je nach Betriebszustand (A2-F007) womöglich
längst erfüllt — entscheidbar, sobald die Betriebsauskunft vorliegt.
Priorität: niedrig–mittel; hebt das Verfahren auf v4.

**E13 (aus Audit 1) — US-007 „relevante Chartmuster": bauen oder streichen.**
Unverändert offen; kostet nichts außer einer ADR-Zeile. Empfehlung wie
Audit 1: streichen mit Vermerk. Priorität: niedrig.

**E-A2-1 (neu) — Pflegeturnus für gemessene Schwellen und Preislisten (A2-F006, R8).**
Frage: Wann werden die Fünftelgrenzen (insbesondere
`options_annualized_return`) und die LLM-Preislisten nachgemessen bzw.
geprüft — fester Turnus (z. B. quartalsweise, Options monatlich),
Ereignis-Auslöser (Volatilitätsregime, Modellwechsel), oder bewusst
nie? Warum jetzt: ADR 0048 nennt die Kurzlebigkeit selbst; ohne
Festlegung altert eine gemessene Zahl genauso still wie eine geratene.
Betroffen: `config/default.yaml`, Doc 14. Empfehlung: Doc-14-Abschnitt
„Pflege" mit Turnus je Wertegruppe; Aufwand S. Konsequenz der
Vertagung: schleichende Score-Drift. Priorität: **mittel**.

**E-A2-2 (neu) — Betriebszustand klarstellen (A2-F007).** Frage: Läuft
die Aufgabenplanung täglich, und mit welchen scharfen Anbietern? Warum
jetzt: Mehrere offene Punkte (E9-Bedingung, Kalibrier-Grundlagen,
Priorität von A2-F001) hängen an der Antwort; das Repository enthält
widersprüchliche Aussagen. Betroffen: Doc 14 (eine Statuszeile).
Aufwand: XS (nur Auskunft + Zeile). Priorität: **hoch, da kostenlos und
mehrfach entsperrend**.

## 15. Priorisierter Maßnahmenplan

P0: keine. Reihenfolge innerhalb der Priorität = empfohlene Abarbeitung.
Feature-Abschluss (A2-M1/M2) ist bewusst von Test-/Doku-/Betriebshärtung
(A2-M3 ff.) getrennt.

| ID | Maßnahme | Prio | Größe | Entscheidung nötig? | Betroffen | Definition of Done | Sprint-Empfehlung |
|---|---|---|---|---|---|---|---|
| A2-M1 | Optionsanalyse abschließen: unabhängige Review → Befunde einarbeiten → PR nach `dev` → Merge; README/Roadmap im selben PR nachziehen (A2-F001, A2-F002) | **P1** | S | Abnahme durch Inhaber | Branch, `README.md`, Doc 03 | PR gemergt, CI grün, keine Statusaussage widerspricht `dev` | sofort (Sprint-5-Abschluss) |
| A2-M2 | Serverprobe Optionspfad: Einzelprobe `cli options --provider ibkr`, dann ein begleiteter `dispatch`-Lauf mit `--options-provider ibkr`; Ergebnisse in der Nachverfolgung vermerken | **P1** | S | nein | Serverbetrieb (Doc 14) | Ein Tageslauf hat Optionsdaten + Score-Komponente persistiert | direkt nach A2-M1 |
| A2-M3 | Golden-Master-Realdatenfall ziehen (`cli export-bars`, Doc 14 Zwischenschritt) — schließt den M5-Rest | **P2** | S | nein | `tests/golden/data/` | Mindestens ein echter Ausschnitt läuft als zusätzlicher Fall, ohne Netz | nächster Serverkontakt |
| A2-M4 | Backup/Restore minimal: täglicher `pg_dump` per Aufgabenplanung + dokumentierter Restore-Test (Doc 10 §15 → Doc 14-Abschnitt) | **P2** | M | Ablageort | Server, Doc 14 | Sicherung läuft automatisch; ein Restore ist einmal durchgespielt und beschrieben | vor Dauerbetrieb-Vertrauen |
| A2-M5 | Betriebszustand klarstellen (E-A2-2): eine Statuszeile in Doc 14 | **P2** | XS | **ja (Auskunft)** | Doc 14 | Repository-Aussagen widersprechen sich nicht mehr | sofort möglich |
| A2-M6 | Pflegeturnus festlegen (E-A2-1) und als Doc-14-„Pflege"-Abschnitt dokumentieren (deckt A2-F006 + R8) | **P3** | S | **ja (E-A2-1)** | Doc 14, ggf. ADR-Nachtrag 0045/0048 | Jede gemessene/gepflegte Zahl hat einen benannten Prüfanlass | Sprint 6-Vorlauf |
| A2-M7 | Contract-Antworten einfrieren: je eine echte, anonymisierte Antwort für Finnhub-Kalender, Finnhub-Recommendations, IBKR-Optionskette (A2-F008) | **P3** | M | nein | `tests/unit/infrastructure/…` | Formatänderung eines Anbieters bricht einen Test | Sprint 6 |
| A2-M8 | Doku-Kleinigkeiten: Doc-08-Kopfvermerk (A2-F003), Konfigurationskommentar Tiefen-Backfill (A2-F004), `.env.example`-Kommentare (A2-F005) | **P3** | XS | nein | Doc 08, `config/default.yaml`, `.env.example` | keine überholte Aussage mehr an diesen Stellen | beiläufig |
| A2-M9 | E13 entscheiden (US-007 streichen oder vormerken) — Rest aus Audit 1 | **P4** | XS | **ja (E13)** | Doc 04, ADR | US-007 hat einen beschlossenen Status | beiläufig |
| A2-M10 | M14-Rest weiterführen: R10 (`pushover` entfernen oder bauen), Finnhub-Header-Umstellung als Wurzelfix von ADR 0044 prüfen | **P4** | S | teils | `settings.py`, `finnhub/` | jeweils erledigt oder bewusst verworfen | Gelegenheit |
| A2-M11 | Dashboard-Sprint vorbereiten: E8 entscheiden, dann API-Ausbau (Auth, Pagination, Ergebnis-Endpunkte) und Frontend gegen `stock_reports` | **P2 (für Sprint 6)** | L | **ja (E8)** | `presentation/`, `frontend/` | gemäß dann festzulegendem Sprint-Zuschnitt | Sprint 6 |

## 16. Empfohlene nächste drei Schritte

1. **Optionsanalyse über die Ziellinie bringen (A2-M1 + A2-M2):**
   unabhängige Review, PR mit Doku-Nachzug, Merge, dann die Serverprobe
   des Tageslauf-Pfads. Das Feature ist fertig gebaut und gemessen
   kalibriert — es fehlt nur der Abschluss-Prozess, und jeder Tag
   Verzögerung vergrößert das Risiko, dass Branch und `dev`
   auseinanderlaufen.
2. **Die zwei Nulldiäten sofort (A2-M5, Teil von A2-M8):** eine
   Statuszeile zum Betriebszustand in Doc 14 und die drei
   XS-Doku-Korrekturen. Kostet Minuten, beseitigt die einzigen Stellen,
   an denen das Repository sich selbst widerspricht — dieselbe Logik, mit
   der Audit 1 M1/M2 an den Anfang stellte, und die sich bewährt hat.
3. **Betriebsreife vor Sprint 6 (A2-M4, dann A2-M3):** minimales
   Backup/Restore einrichten und den Golden-Master-Realdatenfall ziehen.
   Beides schützt genau die zwei Werte, die inzwischen entstanden sind —
   den fünf Jahre tiefen Datenbestand und das eingefrorene Verfahren —,
   bevor mit dem Dashboard-Sprint die nächste Baustelle aufgeht.

---

*Audit durchgeführt am 2026-08-31/2026-09-01 (Nachtlauf). Alle
Feststellungen beziehen sich auf Commit `1f65472be12c…` des Branches
`feature/optionsanalyse`. Ausgeführte Prüfbefehle: Abschnitt 12. Außer
diesem Bericht und einer Zeile im Audit-Index wurde nichts verändert;
nichts wurde committet oder versendet.*
