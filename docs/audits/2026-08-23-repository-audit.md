# Repository-Audit — 2026-08-23 (historische Bestandsaufnahme)

> **Dieses Dokument ist eine Momentaufnahme, keine Festlegung.**
>
> Es beschreibt, wie das Repository am 2026-08-23 vorgefunden wurde. Es
> **ersetzt kein ADR, keine Requirements-Datei und keine Roadmap** und trifft
> keine Entscheidungen. Wo dieser Bericht und die maßgeblichen Quellen —
> Quellcode, `docs/adr/`, `docs/requirements/`, `config/default.yaml` —
> auseinandergehen, gelten **immer die maßgeblichen Quellen**. Der Bericht
> altert ab dem Tag seiner Erstellung; er wird nicht nachgeführt.
>
> Insbesondere sind die hier aufgeführten Entscheidungsvorschläge (E1–E13)
> **Vorlagen zur Entscheidung, keine getroffenen Entscheidungen.** Eine
> getroffene Entscheidung entsteht ausschließlich als ADR in `docs/adr/`.

## Metadaten des Audit-Laufs

| Feld | Wert |
|---|---|
| **Status** | `Point-in-time snapshot` |
| **Audit-Datum** | 2026-08-23 |
| **Untersuchter Branch** | `dev` |
| **Commit-SHA (vollständig)** | `f61f316dad9c71c26661741994d9166325707aeb` |
| **Commit-Betreff** | `Merge pull request #35 from thommson92/feature/technical-agent` |
| **Zustand des Working Tree** | **Sauber.** Zu Beginn des Audits mit `git status` verifiziert („nothing to commit, working tree clean"); unmittelbar vor Anlage dieses Berichts erneut geprüft und weiterhin sauber. Es lag damit keine unversionierte Nutzerarbeit vor, die das Bild hätte verfälschen können. |
| **Verwendetes Modell** | Audit-Durchführung und Berichtserstellung: `claude-fable-5` (Claude Fable 5) über Claude Code. Die reine Archivierung dieses Berichts erfolgte in derselben Sitzung nach einem Modellwechsel mit `claude-opus-5`; am Berichtsinhalt wurde dabei nichts geändert. |
| **Arbeitsmodus** | Ausschließlich auditierend und read-only. Keine Änderung an Quellcode, Dokumentation oder ADRs; kein Commit; keine externen API-Aufrufe; keine Telegram-Nachricht; keine Broker- oder Börsenaktion. |

## Audit-Umfang

Sieben Phasen, vollständig durchlaufen:

1. **Repository-Inventar** — Struktur, Abhängigkeiten, Einstiegspunkte, Module, Datenfluss, externe Schnittstellen, Konfigurations- und Secret-Handling, Teststruktur, CI.
2. **Requirements-/Implementierungsabgleich** — Traceability über Doc 02, die Architekturfragen F1–F13 aus Doc 10 §19 und die User Stories aus Doc 04.
3. **ADR-Audit** — alle 26 ADRs einzeln, mit deklariertem gegen tatsächlich erkennbaren Status.
4. **Dokumentationsaudit** — alle Markdown-Dateien: 14 Fachdokumente, 26 ADRs + ADR-README, 7 Requirements-Dateien, Projekt-`CLAUDE.md`, Projekt-README, Spike-Berichte.
5. **Test- und Qualitätsaudit** — Inventar plus lokale Ausführung aller Prüfungen ohne externe Seiteneffekte.
6. **Offene Entscheidungen** — nur Punkte, die eine menschliche Produkt-, Architektur-, Risiko- oder Priorisierungsentscheidung erfordern.
7. **Konsolidierter Maßnahmenplan** — priorisiert P0–P4.

**Vollständig gelesene Quellen:** sämtlicher Produktivcode unter
`backend/src/ai_trading_analyst/`, die Testsuiten, `config/default.yaml`,
`.env.example`, `.github/workflows/ci.yml`, `backend/pyproject.toml`, alle
Alembic-Migrationen, alle unter Punkt 4 genannten Markdown-Dateien.

## Bekannte Einschränkungen dieses Audits

| Bereich | Einschränkung |
|---|---|
| Betriebszustand des Windows-Servers | **Nicht verifizierbar.** Abnahmestand der Stufen F/G/H aus Doc 14, der Eintrag in der Windows-Aufgabenplanung und die tatsächliche Belegung der `.env` liegen außerhalb des Repositories und wurden nicht eingesehen. |
| Externe Anbieter (IBKR/TWS, Finnhub, Anthropic, Telegram) | **Nicht geprüft.** Bewusst kein einziger Aufruf (Auditvorgabe: keine kostenpflichtigen oder produktiven externen APIs). Die Spike-Ergebnisse unter `spikes/` wurden als eingefrorene Nachweisartefakte übernommen und **nicht** reproduziert. |
| GitHub-seitige Zustände | **Nicht verifizierbar aus dem Repository.** Ob die in ADR 0011 beschriebene CI-Dispatch-Schwäche fortbesteht, ließe sich nur an der Actions-Historie ablesen, nicht am ausgecheckten Stand. |
| Wirtschaftlichkeit der Strategie | **Ausdrücklich keine Aussage.** Es liegen keine belastbaren Fünf-Jahres-Daten im Bestand; eine Bewertung der Strategie als profitabel oder zuverlässig wäre unbelegt und unterbleibt. |
| Integrationstests | Ausgeführt gegen einen bereits laufenden lokalen PostgreSQL-Container (`ata-postgres-test`, Port 55432) auf dem Entwicklungsrechner — nicht gegen eine Produktionsdatenbank. |

## Konventionen im Berichtstext

- **Dateiverweise** stehen als Codespan im Fließtext. Pfade beginnen entweder
  im Repository-Wurzelverzeichnis (`backend/src/…`, `docs/adr/…`,
  `config/default.yaml`) oder — innerhalb von Abschnitt 4 und der ADR-Matrix,
  wo die Basis im Text ausdrücklich genannt ist — relativ zu
  `backend/src/ai_trading_analyst/`. Der Bericht enthält bewusst **keine**
  editor-, sitzungs- oder werkzeugspezifischen URLs; er ist damit unabhängig
  von der Umgebung lesbar, in der er entstanden ist.
- **Belegstufen** werden durchgehend unterschieden: im Code implementiert,
  durch Tests belegt, dokumentiert, per ADR beschlossen, lediglich geplant.
  Nicht Verifizierbares ist als solches gekennzeichnet.
- **Symbole in Statustabellen:** ✅ vollständig · ◐ teilweise · ✖ nicht
  vorhanden.

---

*Ab hier folgt der Bericht im Wortlaut des Audit-Laufs vom 2026-08-23,
unverändert übernommen. Die nachstehende Überschrift und die Abschnitts-
nummerierung 1–12 gehören zum ursprünglichen Bericht.*

---

# Ist-Soll-Audit — AI Trading Analyst

**Stand:** 2026-08-23, Branch `dev`, Commit `f61f316` (Merge PR #35), Working Tree sauber.
**Modus:** rein auditierend, read-only. Keine Quellcode- oder Doku-Änderung, keine Commits, keine externen Aufrufe.

---

## 1. Executive Summary

Der Befund ist besser, als die Aufgabenstellung vermuten ließ. Die **deterministische Kette läuft durchgehend und ist testbelegt**: Watchlist-Import → resumierbarer Backfill (15-Minuten-Bars) → 195-Minuten-Kerzenbildung → Indikatoren (G1-freigegeben, am realen TradingView-Layout bestätigt) → Screener mit 2-aus-3-Regel → Earnings-Filter → deterministische Chartauswertung (technical-v3) → KI-Einordnung (Technical Agent, prompt v3, an echten Kursen verifiziert) → Research Agent — orchestriert vom Trading-Day-Dispatcher. 915 Tests (775 Unit/Architektur + 98 Integration + 42 Sonden) grün, `mypy --strict` und `ruff` sauber, Frontend-Build grün.

**Zwei Annahmen aus dem Auditauftrag stimmen nicht mit dem Ist überein:**

1. **Es gibt keine Fundamentalanalyse.** Entschieden ist nur die Quelle (SEC EDGAR XBRL, deterministisch — ADR 0022); kein Code, keine Tests. Roadmap: Sprint 4, „noch nicht begonnen".
2. **Telegram versendet keine Analyse-Zusammenfassungen.** Der Kanal ist ausschließlich ein Ausfall-Alarm des Dispatchers (ADR 0024, dort ausdrücklich: keine Kurse, keine Kandidaten, keine Ergebnisse). Die Ergebnis-Benachrichtigung aus Doc 02 §2.12 ist Sprint 6 und unimplementiert.

**Weitere Kernbefunde:**

- **Backtesting ist implementiert und getestet, hängt aber nicht im Tageslauf** — nur manuell über `cli backtest`. Doc 10 §7 zeichnet es je Kandidat im täglichen Ablauf. Für das Scoring (Sprint 5, „historische Signalqualität" = 25 % des Swing-Scores) wird die Integration gebraucht.
- **Der Bestand trägt 1 Jahr Historie (`history_duration: 1 Y`), das Backtesting unterstellt 5 (`history_years: 5`).** Doc 14 benennt das als eigene, offene Entscheidung; der in ADR 0014 (E3) vorgesehene 5-Jahres-Batch-Backfill wurde nie gebaut.
- **Nicht implementiert** (planmäßig, Sprint 5/6): Optionsanalyse, Scoring (Konfig-Versionen existieren ungenutzt), Report Generator, Dashboard (Next.js-Platzhalter), Authentifizierung (`ATA_SESSION_SECRET` ungenutzt), Ergebnis-Push.
- **Die ADR-Hygiene ist ungewöhnlich gut** (26 ADRs, klare Status, Ablösungen markiert). Konkrete Doku-Veraltungen sind punktuell: das Projekt-`CLAUDE.md` (Gate-Tabelle liest sich, als seien G1–G3 noch offen; „KI-Integration braucht zuerst ein ADR" — beide ADRs existieren längst), Doc 14 Stufe B (veralteter Alembic-Head `01b2e8681b7a`, tatsächlich `f2b8d6104a37`; F10 als „noch nicht entschieden" geführt), README/Roadmap (Technical-Agent-Verifikation vom 2026-08-23 noch nicht nachgezogen).
- **Keine akuten Sicherheits- oder Datenintegritätsrisiken gefunden** (P0 leer): `.env` sauber ignoriert, CI-Secret-Checks, `SecretStr`, Schichtgrenzen automatisiert erzwungen, Kennzahlentrennung (Trefferquote vs. dauerhaftes Halten) eingehalten, keine erfundenen Werte-Pfade.

---

## 2. Vertrauensniveau und Grenzen des Audits

| Aussagenklasse | Vertrauen | Begründung |
|---|---|---|
| Code, Tests, Konfiguration, Migrationen | **hoch** | vollständig gelesen bzw. lokal ausgeführt (Testläufe s. Abschnitt 8) |
| Dokumentations-/ADR-Abgleich | **hoch** | alle 14 Docs, 26 ADRs + README, 7 Requirements-Dateien gelesen |
| Betriebszustand des Windows-Servers | **nicht verifizierbar** | Abnahme Stufe F/G/H, Aufgabenplanungs-Eintrag, `.env`-Belegung liegen außerhalb des Repos. Laut Sitzungsgedächtnis wartet Stufe F auf einen Handelstag — aus dem Repo nicht belegbar |
| Externe Anbieter (TWS, Finnhub, Anthropic, Telegram) | **nicht geprüft** | bewusst nicht aufgerufen (Auditvorgabe); Spike-Ergebnisse als eingefrorene Artefakte übernommen, nicht reproduziert |
| Profitabilität der Strategie | **keine Aussage** | keine belastbaren 5-Jahres-Daten im Bestand; wird ausdrücklich nicht bewertet |

Nicht ausgeführt (Netz/Credentials/Kosten): `cli screen/backfill/dispatch` gegen die TWS, `cli research`/`technical --interpret` gegen Anthropic, Telegram-Einzelprobe, Spike-Sonden gegen Anbieter. Sichere Ausführungswege stehen in Doc 14 (Stufen D–H).

---

## 3. Repository- und Architekturübersicht

**Stack:** Backend Python 3.12/3.13 (FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, ib_async, httpx, anthropic-SDK), ~12.700 Zeilen `src`; Frontend Next.js 15 + TypeScript strict (Platzhalter); PostgreSQL 16; Lock-Dateien mit Hashes (`uv pip compile --universal`, ADR 0008/0015).

**Vier Schichten** unter `backend/src/ai_trading_analyst/` — `domain` (ohne jede Infrastruktur), `application`, `infrastructure`, `presentation`; Composition Root `bootstrap.py`. Erzwungen durch `tests/architecture/test_layer_boundaries.py` (AST-basiert, Verbotsliste inkl. `ib_async`, `anthropic`, `httpx`, `yaml`).

**Einstiegspunkte:**

| Einstieg | Zweck |
|---|---|
| `cli watchlist` | Watchlist-Dateien einlesen, ohne TWS |
| `cli backfill` | Lücke seit letztem Lauf holen, idempotent über `(symbol, start)` |
| `cli screen` | Screening auf Bestand (`stored`) oder live; verweigert `fixture` (RC 2) |
| `cli backtest` | historische Signalprüfung, manuell |
| `cli technical [--interpret] [--show-prompt]` | Chartauswertung + optionale KI-Einordnung |
| `cli research` | Einzelprobe Research Agent |
| `cli dispatch` | täglicher Lauf (Aufgabenplanung, alle 15 min); Rückgabewerte 0/1/2/130 |
| `uvicorn ai_trading_analyst.main:app` | REST-API `/api/v1` (5 Endpunkte) |

**Datenfluss des Tageslaufs (Ist):** Aufgabenplanung → `dispatch` (Advisory-Lock + `dispatcher_runs`, Kalender live aus IBKR-`tradingHours`, Überfälligkeitsmeldung ggf. via Telegram) → Backfill → Vollständigkeitsprüfung der Zielkerze → `RunAnalysisUseCase`: Phase 1 sequentiell (Screening; für Kandidaten: Chartauswertung **vor** und unabhängig vom Earnings-Filter), Phase 2 nebenläufig (Pool = 4; Research nur bei `EARNINGS_CLEAR`, Technical Agent für jeden Kandidaten), Phase 3 Persistenz in Originalreihenfolge. Fehlerisolation je Aktie; Lauf gilt erst ab `minimum_completion_ratio` 0,9 als erledigt. **Backtesting und Scoring kommen im Tageslauf nicht vor.**

**Persistenz (Head `f2b8d6104a37`, 9 Migrationen):** `intraday_bars`, `stocks`, `analysis_runs`, `screening_results` (inkl. `earnings_*`, `technical_*`, `technical_ai_*`, `research_*`-Spaltensätze, strikt getrennt), `signal_events`, `technical_zones`, `research_citations`, `analysis_run_errors`, `backtest_results`, `dispatcher_runs`.

**Konfiguration/Secrets:** `config/default.yaml` streng validiert (`extra="forbid"`, Querbezugsprüfungen, SHA-256-Fingerprint); Geheimnisse nur über `ATA_*`/`.env` (gitignored, CI-geprüft). Ungenutzt definiert: `ATA_SESSION_SECRET` (erst Dashboard), `ATA_MARKET_DATA_API_KEY` (IBKR braucht keinen Schlüssel).

**CI:** 4 Jobs — Backend-Matrix 3.12/3.13 mit Postgres-Service, Windows-Job (Installation + Unit/Architektur + Watchlist-Smoke), Frontend, Secret-Checks. Required Checks nicht erzwingbar (Free-Plan, ADR 0009); `dev` ohne Branch-Protection.

---

## 4. Implementierungsstand je Baustein

Legende: ✅ vollständig · ◐ teilweise · ✖ nicht vorhanden. „Tests" = durch Tests belegt.

| Baustein | Code | Tests | Doku/ADR | Anmerkung |
|---|---|---|---|---|
| Watchlist-Import (TradingView-Exportformat) | ✅ | ✅ | README | liest lokale `watchlists/*.txt` (192 Symbole), kein TradingView-Zugriff |
| Backfill (resumierbar, idempotent) | ✅ | ✅ | README, ADR 0014 E3 | 1-Jahres-Fenster; 5-Jahres-Batch **nie gebaut** |
| 195-min-Kerzenbildung (nur geschlossene Kerzen) | ✅ | ✅ | Doc 10 §6.1 | inkl. verkürzte Handelstage |
| Indikatoren RSI/RSI-MA/EMA5/EMA20 | ✅ | ✅ | ADR 0010, g1-pruefvorlage | 2026-08-12 gegen reales TradingView-Layout bestätigt |
| Screener (3 Signale, 2-aus-3, 6-Kerzen-Fenster) | ✅ | ✅ | ADR 0010 | `UNKNOWN_DATA_INCOMPLETE` statt stillem Negativ |
| Earnings-Filter | ✅ | ✅ | ADR 0017/0020 | 3-wertiges Statusmodell (bewusste Abweichung von Doc 10 §6.5); Wochentagsnäherung statt echtem Kalender (Ablösung offen, L3) |
| Backtesting (Replay, Cooldown, Kennzahlen) | ✅ | ✅ | ADR 0001-Ausnahme, Doc 07 | **nur manuell**; Kennzahlen-Teilmenge von Doc 10 §6.6 (ohne Stddev, beste/schlechteste Rendite, MAE/MFE, Anteil positiver Schlüsse); Trefferquote und Halten-über-Einstieg getrennt ✅ |
| Trading-Day-Dispatcher | ✅ | ✅ | ADR 0019 | idempotent, Kalender aus TWS, Nachholfrist, Vollständigkeitsschwelle |
| Benachrichtigung (Ausfall-Alarm) | ✅ | ✅ | ADR 0024 | Telegram + `dry_run`; `pushover` im Schema, ungebaut. **Kein Ergebnis-Push** |
| Deterministische Chartauswertung (Zonen, Trend, ATR, CRV) | ✅ | ✅ | ADR 0025 | technical-v3; Parameter an jedem Ergebnis; `min_touches`-Schwäche dokumentiert |
| Technical Agent (KI-Einordnung) | ✅ | ✅ | ADR 0026 | prompt v3, Pflichtfelder im Schema, `temperature=0` (Stabilität unverifiziert), an echten Kursen verifiziert 2026-08-23 |
| Research Agent | ✅ | ✅ | ADR 0021–0023 | Zwei-Phasen-Architektur, Zitate, Kostenbremsen; bekannte Qualitätslücken (Quellenhierarchie, `published_at`, Primärquellen, Abdeckung) |
| Fundamental Agent | ✖ | ✖ | ADR 0022 (nur Quelle) | nicht begonnen |
| Optionsanalyse | ✖ | ✖ | Doc 08/10 §6.10 | Sprint 5; braucht IBKR-Optionsdaten-Abo |
| Scoring | ✖ | ✖ | Doc 09/10 §6.11 | Sprint 5; `scoring`-Konfig ungenutzt; Komponentenzahl (5 vs. 6) offen |
| Report Generator | ✖ | ✖ | Doc 10 §6.12 | Sprint 4/6; Berichtsschema-Version existiert nirgends |
| REST-API | ◐ | ✅ | Doc 10 §6.14 | 3 Analysis-Run-Endpunkte + health/readiness; keine Auth, keine Pagination, kein Rest der Endpunktliste |
| Dashboard | ✖ | — | Doc 10 §6.15 | Next.js-Platzhalterseite |
| Observability | ◐ | ✅ | Doc 10 §12 | JSON-Logs mit Correlation-ID ✅; Metriken/Provider-Status in Readiness ✖; Token/Kosten nur im Log |
| Backup/Restore | ✖ | — | Doc 10 §15 | reine Doku-Anforderung, nichts umgesetzt |

---

## 5. Requirements-Traceability-Matrix

### 5.1 Produktanforderungen (Doc 02)

| Req | Kurzbeschreibung | Status | Code | Tests | Abweichung / nächste Aktion |
|---|---|---|---|---|---|
| 2.1 | Tägliche automatische Analyse 12:45 ET | **IMPLEMENTIERT** | `application/dispatch_daily_run.py`, `cli dispatch` | Unit + Integration | Betriebsabnahme Stufe F laut Gedächtnis noch offen (nicht verifizierbar) |
| 2.2 | TradingView als Datenquelle | **ÜBERHOLT** | — | — | NO_GO ADR 0012; Ersatz IBKR (ADR 0014). Doc 02 nachziehen oder Vermerk |
| 2.3 | Screener, 3 Signale, 2-aus-3 | **IMPLEMENTIERT** | `domain/screening/` | 100+ Unit-Tests | keine |
| 2.4 | Earnings-Ausschluss 10–20 Kerzen | **IMPLEMENTIERT** | `domain/earnings/`, `infrastructure/finnhub/` | Unit + Integration | Statusmodell reduziert (ADR 0020); Feiertagsnäherung; historische Termine fehlen (L9) |
| 2.5 | Backtesting 5 Jahre, Kennzahlen | **TEILWEISE** | `domain/backtesting/`, `cli backtest` | Unit + Integration | nicht im Tageslauf; Bestand 1 J statt 5 J; Kennzahlen-Teilmenge |
| 2.6 | KI-Research | **TEILWEISE** | `infrastructure/anthropic/provider.py` | Unit (34 KB Testdatei) | funktionsfähig mit dokumentierten Qualitätslücken (ADR 0023 Folgepunkte) |
| 2.7 | Technische Analyse | **IMPLEMENTIERT** | `domain/technical/`, Technical Agent | Unit + Integration | „Chartformationen" (auch US-007) bewusst nicht geliefert (ADR 0026) |
| 2.8 | Optionsanalyse | **NICHT IMPLEMENTIERT** | — | — | Sprint 5; Zonen-Eingabe steht bereit (ADR 0025) |
| 2.9 | Zwei Scores | **NICHT IMPLEMENTIERT** | nur `ScoringConfig`-Versionen | — | Sprint 5; Komponentenfrage Doc 09 vs. Doc 10 offen |
| 2.10 | Dauerhafte Speicherung | **IMPLEMENTIERT** (für Existierendes) | `infrastructure/persistence/` | 98 Integrationstests | „spätere Performanceentwicklung" wird nicht nachgeführt |
| 2.11 | Dashboard | **NICHT IMPLEMENTIERT** | Platzhalter | Build grün | Sprint 6 |
| 2.12 | Ergebnis-Benachrichtigung | **NICHT IMPLEMENTIERT** | nur Ausfall-Alarm | Unit | Sprint 6; kollidiert mit ADR-0024-Prinzip „keine Analyse­inhalte über Telegram" → Entscheidung E7 |

### 5.2 Architekturfragen aus Doc 10 §19 (F1–F13)

| F | Frage | Status |
|---|---|---|
| F1/F2 | TradingView-Anbindung / Watchlisten+Indikatoren auslesbar | entschieden: **NO_GO** (ADR 0012); Watchlist über Export-Dateien |
| F3–F5 | RSI-/EMA-Definitionen | entschieden + implementiert (ADR 0010, g1-pruefvorlage) |
| F6 | Quelle historischer 195-min-Kerzen (5 J) | entschieden: IBKR (ADR 0014) — **5-J-Abdeckung im Bestand offen** |
| F7 | Earnings-Termine | entschieden: Finnhub (ADR 0017) |
| F8 | Optionsketten + Greeks | entschieden: IBKR nach Abo-Aktivierung (ADR 0013/0014) — Abo-Entscheidung offen |
| F9 | Ratings/Kursziele | Ratings: Finnhub; **Kursziele zurückgestellt** (kostenpflichtig) |
| F10 | Benachrichtigungskanal | entschieden + umgesetzt: Telegram (ADR 0024) |
| F11 | KI-Anbieter/Modelle | entschieden + umgesetzt: Anthropic, Modellprofile (ADR 0021) |
| F12 | Externer Dashboard-Zugriff | **OFFEN** (einzige offene F-Frage; berührt Finnhub L8) |
| F13 | Redis | entschieden: nein (ADR 0006) |

### 5.3 User Stories (Doc 04)

US-001 ✅ (Dispatcher) · US-002 ◐ überholt (Export-Dateien statt TradingView-Sync) · US-003/004 ✅ · US-005 ◐ (Backtest manuell, 1 J) · US-006 ◐ (Research ja, Fundamentaldaten nein) · US-007 ◐ (ohne Chartformationen) · US-008 ✖ · US-009 ✖ · US-010 ◐ (Speicherung ja, spätere Kursentwicklung nein).

---

## 6. ADR-Matrix

Deklarierter Status ist überall korrekt gepflegt; abweichende Beobachtungen in der letzten Spalte.

| ADR | Titel (kurz) | Deklariert | Erkennbar | Evidenz | Empfohlene Aktion |
|---|---|---|---|---|---|
| 0001 | Doc 10 maßgeblich | Angenommen | umgesetzt, aktiv genutzt | Ausnahmen (Backtest-Einstieg, Modulentkopplung) im Code | BEIBEHALTEN |
| 0002 | Branching | Angenommen | gelebt | PR-Historie #1–#35 | BEIBEHALTEN |
| 0003 | Monorepo, 4 Schichten | Angenommen | umgesetzt + erzwungen | `test_layer_boundaries.py` inkl. Selbsttests | BEIBEHALTEN |
| 0004 | Python-Toolchain | Angenommen | umgesetzt | pyproject, mypy strict grün | BEIBEHALTEN; Randnotiz: Serverversion 3.12 (Doc 14) vs. 3.13 (ci.yml-Kommentar) klären |
| 0005 | Config/Secrets | Angenommen | umgesetzt | `extra=forbid`, `SecretStr`, CI-Check | BEIBEHALTEN |
| 0006 | Kein Redis | Angenommen | Kern gilt; **Stufe 2 (analysis_job, SKIP LOCKED, Heartbeat) nie gebaut** — faktisch durch `dispatcher_runs`+Advisory-Lock (ADR 0019) ersetzt | `infrastructure/persistence/dispatcher_runs.py` | AKTUALISIEREN: kurzer Nachtrag/Neu-ADR, dass 0019 die Koordination konkretisiert |
| 0007 | G1-Parameter leer | Abgelöst (0010) | korrekt | `require_indicators()` besteht weiter | BEIBEHALTEN |
| 0008 | Lock-Dateien | Angenommen (Erzeuger ersetzt) | umgesetzt | CI installiert `--require-hashes` | BEIBEHALTEN |
| 0009 | Required Checks nicht möglich | Angenommen (offen) | unverändert offen | `dev` ohne Protection | MANUELLE ENTSCHEIDUNG (E10); vorbereitetes `gh`-Kommando trägt noch den alten Repo-Namen `TradingViewAnalyzer` |
| 0010 | G1 freigegeben | Angenommen | umgesetzt + real bestätigt | `config indicators`, g1-pruefvorlage Kopf | BEIBEHALTEN |
| 0011 | CI-Dispatch unzuverlässig | Angenommen (offen) | vermutlich überholt (CI läuft heute inkl. Windows-Job) — **nicht verifiziert** | Erfolgsbelege lägen in GitHub, nicht im Repo | STATUS PRÜFEN: wenn CI seit Wochen zuverlässig dispatcht, Nachtrag „entschärft" |
| 0012 | TradingView NO_GO | Angenommen | eingehalten | kein TV-Provider im Produktivcode; Export-Parser liest nur lokale Dateien | BEIBEHALTEN |
| 0013 | IBKR-Kandidat/Spike | Angenommen (abgeschlossen) | historisch korrekt | Spike eingefroren | BEIBEHALTEN |
| 0014 | IBKR produktiv | Angenommen | umgesetzt; E1–E5 nachweisbar | `infrastructure/ibkr/`, Pacing, Fehlerverhalten | BEIBEHALTEN; **Folgearbeit offen: 5-J-Backfill-Batch (E3)** |
| 0015 | Universelle Locks | Angenommen | umgesetzt | Marker-Zeilen in Lock-Dateien | BEIBEHALTEN |
| 0016 | RESC NO_GO | Angenommen | eingehalten | kein RESC im Produktivcode | BEIBEHALTEN |
| 0017 | Finnhub | Angenommen | umgesetzt inkl. L4-Plausibilitätsschutz | `finnhub/provider.py` | BEIBEHALTEN; L9 (historische Termine) → Entscheidung E3 |
| 0018 | Kein Autologon | Angenommen | eingehalten | TWS-Ausfall = normaler Zustand im Code | BEIBEHALTEN |
| 0019 | Dispatcher | Angenommen | umgesetzt + getestet | `dispatch_daily_run.py`, Fenster-Tests | BEIBEHALTEN |
| 0020 | Earnings-Status + Näherung | Angenommen | umgesetzt | `domain/earnings/` | **NEUES ADR VORMERKEN**: L3 (Ablösung der Wochentagsnäherung durch Dispatcher-Kalender) ist seit dem Dispatcher-Merge fällig → E4 |
| 0021 | Anthropic + Modellprofile | Angenommen | umgesetzt | `LlmConfig`, Modell an jedem Ergebnis | BEIBEHALTEN; `fallback_model` nirgends konfiguriert (bewusst?) → E12 |
| 0022 | Research-Quellen | Angenommen (GO_WITH_LIMITATIONS) | umgesetzt (Research); Fundamental-Teil ungebaut | Deployment-Gate dokumentiert, technisch nicht erzwungen | BEIBEHALTEN |
| 0023 | Zitierarchitektur | Angenommen | umgesetzt inkl. aller Nachträge | `provider.py`, `research_citations` | BEIBEHALTEN; offene Folgepunkte → E5 |
| 0024 | Telegram | Angenommen | umgesetzt | `notifications.py`, Fehlerisolation | BEIBEHALTEN |
| 0025 | Chartauswertung/Zonen | Angenommen | umgesetzt (v3) | `domain/technical/` | BEIBEHALTEN; `min_touches`-Nachzug → E9 |
| 0026 | Technical Agent | Angenommen | umgesetzt + verifiziert | Schema-Pflichtfelder, `temperature=0` | BEIBEHALTEN; temperature-Stabilität unverifiziert (E12) |

**Implementierte Architekturentscheidung ohne ADR:** das reale Deployment. Doc 10 §14 und Doc 13 fordern Docker Compose (frontend/backend/worker/postgres/reverse-proxy); tatsächlich läuft das Backend nativ auf dem Windows-Server über die Aufgabenplanung (Doc 14). Das ist gelebte Praxis ohne Beschlussdokument → **NEUES ADR ERFORDERLICH** (E6).

---

## 7. Dokumentationsstatus

| Datei | Klassifikation | Befund / Änderungsvorschlag (nichts davon in diesem Audit geändert) |
|---|---|---|
| `README.md` | TEILWEISE VERALTET | Hochwertig und weitgehend aktuell. Zeile „Technical Agent — Prompt noch nicht am realen Chart erprobt" ist durch ADR 0026 (v3 verifiziert 2026-08-23) überholt → „Noch offen"-Tabelle nachziehen |
| `CLAUDE.md` (Projekt) | **TEILWEISE VERALTET — mit Wirkung** | Gate-Tabelle liest sich, als seien G1–G3 offen (G1 freigegeben ADR 0010, G2 erledigt, G3 endgültig NO_GO); „produktive Datenprovider und KI-Integration brauchen zuerst ein ADR" — ADR 0014/0021 existieren. Da diese Datei jede Arbeits-Session steuert, ist das die wichtigste einzelne Doku-Korrektur → Abschnitt auf Ist-Stand bringen, Gates als historisch kennzeichnen |
| `docs/01 - Vision.md` | TEILWEISE VERALTET | TradingView als Watchlist-/Datenquelle; Vision sonst gültig → Kopfvermerk „Datenquelle inzwischen IBKR (ADR 0012/0014)" |
| `docs/02 - Product Requirements.md` | TEILWEISE VERALTET | §2.2 TradingView überholt; §2.4-Statusmodell überholt (ADR 0020). Vorschlag: Kopfvermerk statt Umbau (Doc 10 ist ohnehin maßgeblich) |
| `docs/03 - Roadmap.md` | TEILWEISE VERALTET | gepflegt; nur „Lauf gegen echte Kurse steht aus" (Technical Agent) überholt |
| `docs/04 - User Stories.md` | TEILWEISE VERALTET | US-002 (TradingView-Sync) überholt; US-007 „Chartmuster" ohne Umsetzungsgrundlage (ADR 0026) → Entscheidung E13 |
| `docs/05 - Data Model.md` | VERALTET | weit hinter dem realen Schema (10 Tabellen, Spaltensätze, Versionierung). Bekannt seit ADR 0001. Vorschlag: entweder generierten Schema-Anhang pflegen oder Kopfvermerk „historische Skizze, maßgeblich ist `orm.py`/Migrationen" |
| `docs/06 - AI-Agents.md` | TEILWEISE VERALTET | führt Backtesting/Scoring als „Agenten" — beides ist (bzw. wird) deterministisch; Research/Technical umgesetzt, Fundamental/Report nicht → Kopfvermerk |
| `docs/07 - Backtesting.md` | TEILWEISE VERALTET / WIDERSPRÜCHLICH | Einstieg „Close der Signalkerze" ist durch die freigegebene Regel (Erkennungskerze) überstimmt (ADR 0001); Cooldown F5 fehlt. ADR 0001 sieht die Korrektur „sobald Backtesting implementiert" vor — das ist es inzwischen → nachziehen |
| `docs/08 - Options Analysis.md` | AKTUELL (Skizze) | unverändert gültige Vorplanung für Sprint 5 |
| `docs/09 - Scoring.md` | WIDERSPRÜCHLICH | 5 gewichtete Komponenten vs. Doc 10 §6.11 mit 6; bekannter, bewusst offener Punkt → vor Sprint 5 entscheiden (E-Teil von E1/Sprint-5-Planung) |
| `docs/10 - System Architecture.md` | AKTUELL (Zielbild) | maßgeblich per ADR 0001. Bekannte, dokumentierte Überstimmungen: §4/§7 Analyse-Reihenfolge, `lookback_closed_candles`, §6.5-Statusmodell, RunStatus-Teilmenge, §14 Deployment (Ist weicht ab → E6) |
| `docs/11 - API-Design.md` | VERALTET | Pfade ohne `/v1`, Endpunkte existieren nicht; per ADR 0001 bewusst bis zum API-Sprint zurückgestellt |
| `docs/12 - CLAUDE.md` | REDUNDANT (ok) | historisches Original der Projekt-CLAUDE.md; als Quelle referenziert, keine Aktion nötig |
| `docs/13 - Deployment.md` | VERALTET / WIDERSPRÜCHLICH | Redis als Pflicht-Service (widerspricht ADR 0006), Docker Compose (widerspricht gelebtem Betrieb Doc 14) → nach Deployment-ADR (E6) neu schreiben |
| `docs/14 - Inbetriebnahme und Betrieb.md` | TEILWEISE VERALTET | ① Stufe B erwartet Alembic-Head `01b2e8681b7a` — aktuell ist `f2b8d6104a37` (drei Migrationen neuer); das Abbruchkriterium schlägt bei der nächsten Server-Aktualisierung fälschlich an. ② Stufe-B-Tabelle: „ATA_NOTIFICATION_TOKEN — Kanal F10 noch nicht entschieden" widerspricht Stufe H im selben Dokument. ③ „Python 3.12" vs. ci.yml („Zielserver 3.13") |
| `docs/adr/README.md` | AKTUELL | Übersicht und „Offene Entscheidungen" sauber gepflegt |
| ADRs 0001–0026 | AKTUELL | siehe Matrix; punktuelle Nachträge empfohlen (0006, 0009-Repo-Name, 0011-Status, 0020-L3) |
| `docs/requirements/*` (7 Dateien) | AKTUELL | vorbildlich: alle mit klarem Erledigt-/Freigabe-Status. Einziger Rest: `signal-specification.md`-Kopf sagt „liegt zur finalen Durchsicht vor" — die Durchsicht ist seit ADR 0010 erfolgt → Kopfzeile aktualisieren |
| `spikes/*/README, REPORT, RESULT, WINDOWS_VALIDATION` | AKTUELL | eingefrorene Nachweisartefakte, als solche gekennzeichnet |

---

## 8. Testergebnisse und fehlende Tests

### 8.1 Ausgeführte Befehle (alle lokal, ohne externe Seiteneffekte)

| Befehl | Ergebnis | Vorbestehende Fehler |
|---|---|---|
| `backend/.venv/bin/python -m pytest tests/unit tests/architecture` | **775 passed** (7,8 s) | keine |
| `TEST_DATABASE_URL=postgresql+psycopg://ata:ata@localhost:55432/ata_test … -m pytest tests/integration` (gegen bereits laufenden Container `ata-postgres-test`) | **98 passed** (29 s), 1 Deprecation-Warnung (`starlette.testclient`/httpx — vorbestehend, harmlos) | keine |
| `…/python -m ruff check .` | All checks passed | keine |
| `…/python -m mypy src tests` (strict) | Success, 153 Dateien | keine |
| `…/python -m pytest ../spikes/resc-schema/tests ../spikes/earnings-anbieter/tests` | **42 passed** | keine |
| `frontend: npm run lint && npm run typecheck && npm run build` | alle grün | keine |
| `alembic heads` | `f2b8d6104a37 (head)`, Kette linear, keine Dubletten | — |

### 8.2 Testmatrix

| Bereich | Vorhanden | Ausgeführt | Ergebnis | Lücke / Risiko | Empfohlener nächster Test |
|---|---|---|---|---|---|
| Unit: Signale, Kandidatenregel, Indikatoren, Aggregation | ✅ umfangreich | ✅ | grün | — | — |
| Unit: Backtesting (Replay, Cooldown, Kennzahlen) | ✅ | ✅ | grün | Golden-Master fehlt (s. u.) | — |
| Unit: Earnings, Technical (Zonen/Snapshot/CRV), Research-Werte, Scheduling | ✅ | ✅ | grün | — | — |
| Architektur (Schichtgrenzen, Screening-Domain) | ✅ mit Selbsttests | ✅ | grün | — | — |
| Integration: Repositories, Migrationen, API, Full-Run (Fixture-E2E), Dispatcher | ✅ | ✅ (echtes Postgres 16) | grün | — | — |
| Adapter-Tests IBKR/Finnhub/Anthropic/Telegram (gemockte Transporte) | ✅ | ✅ | grün | **Contract-Tests gegen eingefrorene Original-Antworten** fehlen als eigene Kategorie (Doc 10 §16); die Unit-Tests bauen Antworten nach | je Anbieter eine echte, anonymisierte Antwort einfrieren und dagegen testen |
| Golden-Master (Doc 10 §16) | ✖ | — | — | **größte Testlücke**: eine Verfahrensänderung an Screener/Backtest fiele nur auf, wenn ein Unit-Test zufällig den Fall trifft | Referenzausschnitt echter Bars (z. B. AAPL 2026) einfrieren, erwartete Signale/Kennzahlen festschreiben — lokal ohne Netz lauffähig |
| Look-ahead-Bias | ◐ indirekt (Replay-Entscheidungspunkte, Warm-up-Tests) | ✅ | grün | kein expliziter Anti-Look-ahead-Test | Testfall: künftige Kerze manipulieren → Ergebnis darf sich nicht ändern |
| Fehler-/Timeout-/Rate-Limit-Szenarien | ◐ (Timeouts konfiguriert + getestet, IBKR-Pacing getestet; kein Einzel-Retry — Wiederholung liegt beim 15-min-Dispatcher) | ✅ | grün | Retry-Regel aus g1-pruefvorlage §1.5 („Retry gemäß vorgesehener Regel") existiert nur auf Dispatcher-Ebene — nicht verifiziert, ob das die Absicht abschließend erfüllt | klären + ggf. dokumentieren, dass Dispatcher-Wiederholung die Retry-Regel *ist* |
| Fehlende/veraltete Marktdaten | ✅ (`UNKNOWN_DATA_INCOMPLETE`, `StaleDataError`, Vollständigkeitsschwelle) | ✅ | grün | — | — |
| Prompt-Injection (Research) | ✖ | — | — | ADR 0022 E3 verschiebt die Abwehr in die Implementierung; ein Test dafür existiert nicht. Technical Agent hat konstruktiv keine Angriffsfläche | Testfall: Instruktions-Payload in gemockten Suchergebnissen darf Bericht/Statuswerte nicht steuern |
| Security/Secrets/Logging | ✅ (CI-Checks, `SecretStr`-Test, Logging-Tests, Token-Redaktion im Telegram-Fehlerpfad) | ✅ | grün | — | — |
| Lint/Typprüfung | ✅ | ✅ | grün | — | — |

### 8.3 Kategorisierung

1. **Automatisch lokal:** alles unter 8.1 außer Integration — läuft ohne jede Vorbereitung.
2. **Mit Sandbox:** Integrationstests (Docker-Postgres, README-Anleitung; Container lief hier bereits).
3. **Mit Credentials/extern (nicht im Audit ausgeführt):** `cli screen/backfill/dispatch --provider ibkr` (TWS), `cli dispatch --earnings-provider finnhub`, `cli research --provider anthropic --max-searches 1 --max-fetches 1` (~0,3 USD), `cli technical --interpret --agent-provider anthropic` (~0,005 USD/Titel), Telegram-Einzelprobe (Doc 14 Stufe H). Sichere Reihenfolge: Doc 14, Stufen D–H.
4. **Vor Produktivbetrieb zwingend:** Stufe F über einen vollen Handelstag (laut Gedächtnis offen), Finnhub-Schritt G1, Research-Einzelprobe G2, Telegram-Probe H — plus Golden-Master-Tests, bevor am Verfahren weitergeschraubt wird.

---

## 9. Offene Entscheidungen

Nur Punkte, die wirklich eine Entscheidung des Projektverantwortlichen brauchen. Sortiert nach Priorität.

**E1 — Kommt das Backtesting in den Tageslauf? (HOCH)**
Warum jetzt: Doc 10 §7 sieht es je Kandidat vor; das Scoring (Sprint 5) braucht „historische Signalqualität" je Kandidat. Betroffen: `run_analysis.py`, `cli dispatch`, `backtest_results`.
Optionen: (a) je Kandidat im Tageslauf — Doc-10-treu, verlängert den Lauf um Sekunden, braucht E2 zuerst; (b) separater nächtlicher Batch über die Watchlist — entkoppelt, Ergebnisse liegen morgens bereit, kostet einen zweiten Aufgabenplanungs-Eintrag; (c) erst mit Sprint 5 integrieren — kein Aufwand jetzt, Scoring-Design entscheidet.
Empfehlung: **(c)**, festgehalten als Sprint-5-Voraussetzung — heute liest niemand die Backtest-Ergebnisse automatisiert. Vertagung kostet nichts, bis Sprint 5 beginnt; dann blockiert es.

**E2 — Historientiefe: 5-Jahres-Backfill nachholen oder Anspruch senken? (HOCH)**
Warum jetzt: `backtesting.history_years: 5` vs. Bestand aus `history_duration: 1 Y`. Jede Backtest-Zahl basiert real auf ~1 Jahr; `history_start/end` stehen zwar am Ergebnis, aber Doc 02/07 versprechen 5 Jahre. Der in ADR 0014 E3 vorgesehene Chunking-Batch wurde nie gebaut. IBKR liefert 15-min-Bars laut Spike ~2 Jahre zurück — **ob 5 Jahre in 15-min-Auflösung überhaupt erreichbar sind, ist unbelegt**.
Optionen: (a) Batch bauen und maximal verfügbare Tiefe holen (ehrlich ausweisen, was ankam); (b) `history_years` auf die reale Tiefe senken und Doku anpassen; (c) 195-min-Kerzen aus gröberen Bars für ältere Zeiträume zulassen (Verfahrensänderung, neue Versionsnummer).
Empfehlung: **(a) mit Messung zuerst** — ein einmaliger Probelauf über 2–3 Symbole zeigt die echte Tiefe, dann (a) oder (b). Vertagung: Kennzahlen bleiben stillschweigend 1-Jahres-basiert; Konfidenz-Label stimmen, Erwartung nicht.

**E3 — Historische Earnings-Termine (SEC EDGAR 8-K) fürs Backtesting? (MITTEL)**
Warum: L9 aus ADR 0017 — der Backtest zählt Ereignisse, die der Live-Filter ausgeschlossen hätte; die Kennzahlen messen eine leicht andere Strategie als die gehandelte. Optionen: (a) EDGAR-Adapter (kostenlos, lizenzfrei, vorgemerkt); (b) bewusst so lassen und die Abweichung am Ergebnis kennzeichnen. Empfehlung: **(b) jetzt, (a) vor Sprint 5**, gemeinsam mit E1. Vertagung: verzerrte Backtest-Basis für das Scoring.

**E4 — Wochentagsnäherung durch den echten Kalender ablösen? (MITTEL)**
ADR 0020 L3 hat die Ablösung fest zugesagt, „sobald der Dispatcher gemergt ist" — das ist er seit Wochen. Optionen: (a) Earnings-Kerzenzählung auf den IBKR-Kalender umstellen (neues ADR, koppelt den Filter an die TWS); (b) Näherung behalten und L3 in einem neuen ADR ausdrücklich entkräften (die Abweichung wirkt konservativ). Empfehlung: **(b)** — die Kopplung an die TWS widerspräche der Modul-Entkopplung; aber es braucht das ADR, sonst bleibt eine gebrochene Zusage stehen.

**E5 — Research-Qualitätspaket vor dem Dauerbetrieb? (HOCH, sobald `--research-provider anthropic` täglich läuft)**
Vier belegte Mängel aus ADR 0023: Lizenzklasse fast immer `UNKNOWN`; Primärquellen werden nie abgerufen (Prompt verlangt sie, `fetch_allowed_domains` verhindert sie — jeder Lauf bezahlt Fehlversuche, Kostenstreuung 0,32–0,58 USD); ~40 ungewichtete Zitate; `COMPLETED` sagt nichts über Abdeckung; `published_at` fehlt. Optionen: (a) Paket schnüren (Quellenhierarchie + Allowlist-Neuschnitt + Zitatobergrenze + Abdeckungsfeld samt Migration); (b) Dauerbetrieb mit bekannten Mängeln starten und nur Kosten beobachten. Empfehlung: **(a) vor dem täglichen Scharfschalten** — die Kosten- und Belegqualität ist sonst jeden Abend zufällig. Vertagung: funktioniert, aber teurer und schwächer belegt als nötig.

**E6 — Deployment-Zielbild festschreiben (MITTEL)**
Ist: nativer Windows-Betrieb + Aufgabenplanung (Doc 14). Soll laut Doc 10 §14/Doc 13: Docker Compose mit fünf Services. Optionen: (a) Ist per ADR als MVP-Deployment beschließen, Doc 13 neu schreiben, Docker erst mit Dashboard-Sprint neu bewerten; (b) Docker-Migration einplanen. Empfehlung: **(a)** — der native Betrieb ist begründet (TWS braucht die angemeldete Desktop-Session) und funktioniert. Vertagung: Doku widerspricht dauerhaft dem Betrieb.

**E7 — Inhalt der Ergebnis-Benachrichtigung (MITTEL, spätestens Sprint 6)**
ADR 0024 hält Analyseinhalte bewusst aus Telegram heraus; Doc 02 §2.12 will Symbol, Score, Zusammenfassung, Link aufs Telefon. Beides zusammen geht nicht ohne Entscheidung: (a) Inhalte doch über Telegram (Prinzip aufgeben); (b) nur neutraler Ping + Link ins (dann existierende, abgesicherte) Dashboard; (c) anderer Kanal für Inhalte. Empfehlung: **(b)** — konsistent mit ADR 0024 und Finnhub L8. Vertagung: unkritisch bis Sprint 6.

**E8 — F12: externer Dashboard-Zugriff und Auth (NIEDRIG jetzt, BLOCKIEREND für Sprint 6)**
Einzige offene F-Frage aus Doc 10 §19. Berührt Finnhub L8 (keine Weitergabe abgeleiteter Daten) und das Deployment-Gate aus ADR 0022. Braucht ein eigenes ADR, bevor irgendetwas von außen erreichbar wird.

**E9 — `min_touches` → Wendepunkt-Filter (NIEDRIG–MITTEL)**
ADR 0025 benennt die erste Nachziehkandidatin (Filter misst Antreffen statt Umkehr; Rauschen in Kursnähe verdrängt tragende Zonen). Bedingung laut ADR: erst nach einem weiteren Lauf an echten Kursen. Empfehlung: nach den nächsten 2–3 Realläufen entscheiden; Verfahrensversion würde auf v4 steigen.

**E10 — Required Checks: GitHub Pro, public oder Status quo? (NIEDRIG)**
Seit ADR 0009 offen. Empfehlung: Status quo, solange Ein-Personen-Betrieb; bei Pro-Abo das vorbereitete Kommando mit **aktualisiertem Repo-Namen** (`ai-trading-analyst`) ausführen.

**E11 — Kursziele nachrüsten? (NIEDRIG bis Sprint 5)**
Finnhub-Endpunkt kostenpflichtig (ADR 0017). Erst entscheiden, wenn das Scoring-Design sagt, ob Kursziele einfließen.

**E12 — Kleinigkeiten mit Entscheidungscharakter (NIEDRIG, je XS)**
① `fallback_model` je Modellprofil setzen oder bewusst leer lassen (ADR 0021 sieht Fallback vor; heute `None` — zudem greift der Fallback laut ADR 0026 auch bei 400ern). ② `temperature=0`-Stabilität mit zwei identischen Läufen verifizieren (ADR 0026, offener Punkt). ③ Serverseitige Python-Version (3.12 laut Doc 14, 3.13 laut ci.yml) einmal festellen und Doku vereinheitlichen.

**E13 — US-007 „relevante Chartmuster": bauen oder streichen? (NIEDRIG)**
ADR 0026 stellt fest: ohne deterministische Mustererkennung wäre jede KI-Formation eine Erfindung. Optionen: (a) Anforderung aus Doc 04 streichen; (b) deterministische Erkennung als spätere Ausbaustufe vormerken. Empfehlung: **(a)** mit Vermerk.

---

## 10. Risiken und technische Schulden

| # | Risiko / Schuld | Schwere | Beleg |
|---|---|---|---|
| R1 | Backtest-Kennzahlen suggerieren 5 Jahre, Basis ist ~1 Jahr | **hoch (fachlich)** | `config` `history_years: 5` vs. `history_duration: 1 Y`; Doc 14 „Reichweite des Bestands" |
| R2 | Kein Golden-Master — Verfahrensdrift bei Screener/Backtest unentdeckbar | **mittel–hoch** | Doc 10 §16 gefordert, nirgends umgesetzt |
| R3 | Projekt-CLAUDE.md leitet Arbeits-Sessions mit veralteten Gates fehl | mittel | Gate-Tabelle vs. ADR 0010/0012/0014/0021 |
| R4 | Doc 14 Stufe B bricht bei nächster Aktualisierung fälschlich ab (falscher Head) | mittel (Betrieb) | `alembic heads` = `f2b8d6104a37` |
| R5 | Research-Dauerbetrieb: Kostenstreuung + schwache Belegqualität | mittel (Kosten) | ADR 0023 Folgepunkte, gemessene Läufe 0,32–0,62 USD |
| R6 | Backtest ohne historischen Earnings-Filter misst andere Strategie als gehandelt | mittel | ADR 0017 L9 |
| R7 | Kein Merge-Schutz; CI-Grün nicht erzwungen | niedrig–mittel | ADR 0009/0011; `dev` ungeschützt |
| R8 | Manuell gepflegte Preislisten (`research.pricing`, `technical_agent.pricing`) veralten still | niedrig | Kommentare in `default.yaml` |
| R9 | Ein Thread-Pool für Research + Technical Agent (hängende Recherche blockiert Einordnungen) | niedrig | ADR 0026, benannter Ausweg |
| R10 | `pushover` im Schema ungebaut; ungenutzte Secrets-Felder | kosmetisch | `settings.py`, `.env.example` |

Positiv festzuhalten: Idempotenz (Backfill, Dispatcher), Fehlerisolation je Aktie, Unveränderlichkeit + Versionierung an jedem Ergebnis (Signalregel-, Verfahrens-, Prompt-, Modellversion, Parameter als JSONB), strikte Trennung deterministisch/KI bis in die Spaltensätze — die zentrale Regel des Projekts ist strukturell verankert, nicht nur behauptet.

---

## 11. Priorisierter Maßnahmenplan

**P0 — keine.** Keine akuten Sicherheits-, Datenintegritäts- oder Produktionsrisiken gefunden.

| # | Maßnahme | Prio | Größe | Entscheidung nötig? | Definition of Done | Abhängig von |
|---|---|---|---|---|---|---|
| M1 | Doc 14 Stufe B korrigieren: Head-Prüfung auf „aktueller Head der Migrationskette" (oder `f2b8d6104a37`), F10-Zeile auf ADR 0024 umstellen | **P1** | XS | nein | Stufe B widerspricht keinem realen Zustand mehr | — |
| M2 | Projekt-CLAUDE.md: Gate-Abschnitt auf Ist bringen (G1 freigegeben, G2/G3 historisch, ADR 0014/0021 existieren) | **P1** | XS | nein | neue Session liest keinen falschen Sperrzustand mehr | — |
| M3 | E2 entscheiden; danach Tiefenmessung + ggf. 5-J-Backfill-Batch (chunked, ADR 0014 E3) | **P1** | M | **ja (E2)** | reale Historientiefe gemessen, Bestand entspricht beschlossenem Anspruch, Doku angepasst | TWS |
| M4 | E1 entscheiden (Backtest-Integration), Ergebnis in Roadmap/Sprint-5-Zuschnitt festhalten | **P1** | S (Entscheid) | **ja (E1)** | beschlossener Integrationsweg dokumentiert | E2 sinnvoll zuerst |
| M5 | Golden-Master-Tests für Screener + Backtest auf eingefrorenem Realdaten-Ausschnitt | **P2** | M | nein | Verfahrensänderung bricht einen Test, lokal ohne Netz lauffähig | Bestand vorhanden |
| M6 | Prompt-Injection-Test für den Research-Adapter (gemockte bösartige Suchtreffer) | **P2** | S | nein | Instruktions-Payload beeinflusst weder Status noch Feldwerte | — |
| M7 | E4 umsetzen: neues ADR zur Wochentagsnäherung (Ablösung oder begründeter Verbleib) | **P2** | S | **ja (E4)** | L3 aus ADR 0020 ist nicht länger eine offene Zusage | — |
| M8 | E5-Paket Research-Qualität (Quellenhierarchie, Allowlist-Neuschnitt, Zitatobergrenze, Abdeckungsfeld + Migration, `published_at`-Entscheid) | **P2** | M–L | **ja (E5)** | Dauerbetrieb mit stabilen Kosten und klassifizierten Belegen | vor täglichem `--research-provider anthropic` |
| M9 | README „Noch offen"-Tabelle + Roadmap (Technical-Agent-Verifikation) nachziehen | **P3** | XS | nein | keine überholten Statusaussagen mehr | — |
| M10 | Kopfvermerke Doc 01/02/04/05/06/07; `signal-specification.md`-Kopf auf „freigegeben" | **P3** | S | nein | jeder Doc-Kopf sagt, was maßgeblich ist | — |
| M11 | Deployment-ADR (E6) + Doc 13 neu | **P3** | S | **ja (E6)** | Ist-Betrieb ist beschlossene Architektur | — |
| M12 | ADR-Nachträge: 0006 (Stufe 2 durch 0019 ersetzt), 0009 (Repo-Name im Kommando), 0011 (Status prüfen) | **P3** | XS | teils (E10) | ADR-Übersicht ohne stille Widersprüche | — |
| M13 | Python-Versionsfrage Server (E12 ③) klären, Doc 14/README/ci.yml konsistent | **P3** | XS | nein | eine Version, überall gleich benannt | Serverzugriff |
| M14 | Sammelposten P4: `fallback_model`-Entscheid, `temperature=0`-Verifikationsdoppel­lauf, getrennte Agent-Pools, `pushover` entfernen oder bauen, ungenutzte Secret-Felder kommentieren/entfernen | **P4** | XS–S | teils (E12) | jeweils erledigt oder bewusst verworfen | — |

---

## 12. Empfohlene nächste drei Schritte

1. **Die zwei XS-Korrekturen sofort (M1 + M2):** Doc 14 Stufe B und der Gate-Abschnitt der Projekt-CLAUDE.md. Beide kosten Minuten und beseitigen die einzigen Doku-Fehler, die aktiv fehlleiten — einer davon bei der nächsten Server-Aktualisierung, der andere in jeder Arbeits-Session.
2. **E2 entscheiden und die reale IBKR-Historientiefe messen (M3):** ein Probelauf über zwei, drei Symbole zeigt, ob 5 Jahre in 15-Minuten-Auflösung überhaupt erreichbar sind. Erst danach lohnt jede weitere Backtest-Arbeit — und E1/E3 hängen daran.
3. **Golden-Master-Tests aufsetzen (M5), sobald der Bestand steht:** das Projekt ändert seine Verfahren bewusst und versioniert (technical-v1→v3, prompt v1→v3) — genau dafür fehlt das Sicherheitsnetz auf der Screener-/Backtest-Seite, bevor `min_touches` (E9) und Sprint 5 weitere Verfahrensänderungen bringen.

---

*Audit durchgeführt am 2026-08-23. Alle Feststellungen beziehen sich auf Commit `f61f316`. Ausgeführte Prüfbefehle und Ergebnisse: Abschnitt 8.1. Nichts wurde verändert, committet oder versendet.*
