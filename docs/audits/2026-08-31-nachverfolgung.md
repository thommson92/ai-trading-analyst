# Nachverfolgung — Repository-Audit 2 vom 2026-08-31

> **Dieses Dokument lebt.** Es wird fortgeschrieben, sooft sich ein Stand
> ändert — im Gegensatz zum [Audit selbst](2026-08-31-repository-audit-2.md),
> das als eingefrorene Momentaufnahme unverändert bleibt.

**Stand:** 2026-09-01 (nach PR #61 und dem Sprint-6-Zweig
`feature/sprint-6-zuschnitt`: Lese-API, Dashboard, ADR 0052/0053,
A2-M10, Abhängigkeitsprüfung)

## Wozu dieses Dokument

Das Audit hält fest, wie das Repository am 2026-08-31 vorgefunden wurde
(Branch `feature/optionsanalyse`, Commit `1f65472`). Es darf nicht
nachgeführt werden (`README.md` dieses Verzeichnisses) — hier steht, was von
seinen Befunden, Maßnahmen und Entscheidungen inzwischen erledigt ist.

## Was hier **nicht** steht

Dieses Dokument führt **ausschließlich Status und Belegverweis, niemals
Inhalte.** Maßgeblich bleiben unverändert:

| Frage | Maßgebliche Quelle |
|---|---|
| Was ist entschieden? | `docs/adr/` |
| Was ist gefordert? | `docs/` (bei Widersprüchen Doc 10, siehe ADR 0001) |
| Was ist fachlich freigegeben? | `docs/requirements/` |
| Was tut das System tatsächlich? | der Quellcode und die Tests |

## Statuswerte

| Wert | Bedeutung |
|---|---|
| **behoben** | Nur Befunde: Ursache beseitigt und belegt. |
| **erledigt** | Nur Maßnahmen: Die Definition of Done aus dem Audit ist erfüllt und belegt. |
| **teilweise** | Begonnen, aber nicht vollständig. Der Rest steht ausdrücklich dabei. |
| **offen** | Unangetastet. |
| **verworfen** | Bewusst nicht umgesetzt, mit Begründung. |
| **entschieden** | Nur Entscheidungen: als ADR festgehalten — reine Betriebsfestlegungen im maßgeblichen Betriebsdokument (Doc 14, Muster E12 ③ der Audit-1-Nachverfolgung). |

---

## Befunde (A2-F001–A2-F008)

| # | Befund (Kurzform, maßgeblich ist das Audit) | Status | Beleg / was noch fehlt |
|---|---|---|---|
| A2-F001 | Optionsanalyse ohne Review, Merge und Serverprobe | **teilweise** | Review eingearbeitet (`be2b24a`, `04db9ec`), Merge PR #60 (2026-09-01). Offen: der begleitete Verbundlauf `dispatch → options` am Server (= A2-M2) |
| A2-F002 | README/Roadmap führen Sprint 5 als „noch nicht gebaut" | **behoben** | `README.md`, `docs/03 - Roadmap.md` — siehe unten |
| A2-F003 | Doc 08 ohne Kopfvermerk, von ADR 0048 überholt | **behoben** | Kopfvermerk in `docs/08 - Options Analysis.md` |
| A2-F004 | Veralteter Tiefen-Backfill-Kommentar in der Konfiguration | **behoben** | `config/default.yaml`, Kommentar an `history_duration` |
| A2-F005 | Ungenutzte Secret-Felder mit veralteten Kommentaren | **behoben** | `.env.example`: `ATA_LLM_API_KEY` auf ADR 0021 und realen Gebrauch, `ATA_MARKET_DATA_API_KEY` als ungenutzt gekennzeichnet |
| A2-F006 | Gemessene Schwellen ohne Pflegeturnus | **behoben** | Entscheidung E-A2-1; Doc 14, Abschnitt „Pflege" (quartalsweise, nächster Termin 2026-12-01) |
| A2-F007 | Widersprüchliche Aussagen zum Betriebszustand | **behoben** | Doc 14, Abschnitt „Betriebszustand": vor dem 2026-09-01 kein automatischer Tageslauf; seither aktiv mit benannter Anbieterliste |
| A2-F008 | Contract-Tests nur für EDGAR eingefroren | **offen** | A2-M7, parallel zu Sprint 6 |

### A2-F001 — was der Abschluss noch braucht

Der Verbundlauf ist für den **2026-09-01 ab 18:50 CEST** (12:50 ET) auf dem
Windows-Server angesetzt: Einzelprobe `cli options --provider ibkr`, dann
ein manueller `dispatch` mit dem vollen Argumentstring aus Doc 14 Stufe H,
danach die erstmalige Aktivschaltung der Aufgabenplanung (E-A2-2). Erfolgt
das, sind A2-F001 und A2-M2 erledigt; das Ergebnis gehört hier eingetragen.

### A2-F002 — die Abweichung vom Audit-Vorschlag

Das Audit empfahl den Doku-Nachzug **im Options-PR** (A2-M1). Tatsächlich
kam er einen PR später, im Zweig dieser Nachverfolgung — PR #60 enthielt
weder `README.md` noch die Roadmap. Am Ergebnis ändert das nichts; der
Prozessbefund (Doku-Nachzug ist nicht an den Merge gekoppelt) bleibt als
Beobachtung stehen.

---

## Maßnahmen (A2-M1–A2-M11)

| # | Maßnahme (Kurzform) | Status | Beleg / was noch fehlt |
|---|---|---|---|
| A2-M1 | Optionsanalyse: Review, PR, Merge, Doku-Nachzug | **erledigt** | PR #60 (Review `be2b24a`); Doku-Nachzug mit Abweichung, siehe A2-F002 |
| A2-M2 | Serverprobe Optionspfad + begleiteter Tageslauf | **offen** | angesetzt 2026-09-01 ab 18:50 CEST, siehe A2-F001 |
| A2-M3 | Golden-Master-Realdatenfall ziehen | **offen** | läuft am Server; wegen des Merge-Schutzes über einen kleinen Branch samt PR (Doc 14, Zwischenschritt Golden Master) |
| A2-M4 | Backup/Restore minimal | **teilweise** | Doc 14, Abschnitt „Sicherung" steht (Skript, Task 22:00, `pgpass.conf`, Restore-Probe). Offen: Einrichtung und erste Zählprobe am Server |
| A2-M5 | Betriebszustand klarstellen (E-A2-2) | **erledigt** | Doc 14, Abschnitt „Betriebszustand" |
| A2-M6 | Pflegeturnus festlegen (E-A2-1) | **erledigt** | Doc 14, Abschnitt „Pflege" — deckt zugleich Risiko R8 des Audits vom 2026-08-23 |
| A2-M7 | Contract-Antworten einfrieren (Finnhub ×2, IBKR-Optionskette) | **offen** | parallel zu Sprint 6 |
| A2-M8 | Doku-Kleinigkeiten (Doc 08, Konfiguration, .env.example) | **erledigt** | siehe A2-F003/F004/F005 |
| A2-M9 | E13 entscheiden | **erledigt** | [ADR 0050](../adr/0050-us-007-chartmuster-gestrichen.md); Vermerke in Doc 04 |
| A2-M10 | M14-Rest: `pushover`, Finnhub-Token in den Header | **erledigt** | `pushover` aus dem Schema gestrichen (Risiko R10 geschlossen, [ADR 0024](../adr/0024-benachrichtigungskanal-telegram.md) Nachtrag); Header-Umstellung gebaut und **am 2026-09-01 gegen den echten Finnhub-Dienst bestätigt** — die Zugriffszeile trägt keinen Schlüssel mehr ([ADR 0044](../adr/0044-geheimnisse-an-der-log-senke-schwaerzen.md) Nachtrag). Damit ist auch der Prozessbefund „Symptom statt Ursache" aus Audit 1 geschlossen |
| A2-M11 | Dashboard-Sprint vorbereiten | **teilweise** | E8 entschieden ([ADR 0049](../adr/0049-dashboard-mvp-nur-lan.md)); Zuschnitt, Lese-API und die drei Ansichten sind gebaut ([ADR 0052](../adr/0052-dashboard-als-statischer-export.md), [ADR 0053](../adr/0053-lese-api-kein-lauf-ueber-http.md), Doc 11). Offen: die Einrichtung am Server (Doc 14, Stufe J) |

Außerhalb der Audit-Maßnahmen, aber aus dem Audit motiviert: der neue
Provider-Wert **`none`** für Research und Technical Agent
(`backend/src/ai_trading_analyst/infrastructure/disabled.py`; Zweig
`feature/audit-2-und-none-provider`) — siehe Ergänzungen.

---

## Entscheidungen

| # | Gegenstand | Status | Beleg / Bemerkung |
|---|---|---|---|
| E8 | F12: externer Dashboard-Zugriff und Auth | **entschieden** | [ADR 0049](../adr/0049-dashboard-mvp-nur-lan.md): MVP nur eigenes Netz, keine Exposition, keine eigene Auth; Neubewertung nach stabilem Betrieb. Sprint 6 entsperrt |
| E9 | `min_touches` → Wendepunkt-Filter | **offen** | Bedingung „weitere Läufe an echten Kursen" (ADR 0025) ist seit der Aktivschaltung datierbar erfüllbar — siehe unten |
| E13 | US-007 „relevante Chartmuster" | **entschieden** | [ADR 0050](../adr/0050-us-007-chartmuster-gestrichen.md): gestrichen mit Vermerk |
| E-A2-1 | Pflegeturnus für gemessene Schwellen und Preislisten | **entschieden** | quartalsweise, nächster Termin 2026-12-01; Doc 14, Abschnitt „Pflege" |
| E-A2-2 | Betriebszustand / Aktivschaltung | **entschieden** | ab 2026-09-01 aktiv, alle Anbieter scharf außer Research (bewusst `none`, [ADR 0051](../adr/0051-research-im-dauerbetrieb-abgeschaltet.md)); Doc 14, Abschnitt „Betriebszustand" |

### E9 — das konkrete Vorgehen

Nach ein bis zwei Wochen aktiven Betriebs (fünf bis zehn Realläufe) die
Zonen von zwei, drei echten Kandidaten sichten
(`cli technical --provider ibkr --symbols ...`). Der designierte Schritt
steht seit ADR 0025 fest: Filter auf `pivot_count` (mindestens zwei
Wendepunkte) statt der Berührungszählung — Umkehr statt Antreffen. Fällt
die Entscheidung dafür, folgt ein ADR, das Verfahren steigt auf
`technical-v4`, und der Golden Master wird neu aufgezeichnet.

---

## Ergänzungen gegenüber dem Audit

Punkte, die das Audit so nicht wissen konnte, weil sie außerhalb des
Repositories liegen oder erst danach entstanden sind.

| Datum | Ergänzung |
|---|---|
| 2026-09-01 | **PR #60 ist gemergt** (11:12 UTC), inklusive unabhängiger Review (`be2b24a`) und zusätzlicher Anwendungsfall-Tests (`04db9ec`). Die A2-F001-Lage des Audits ist damit zur Hälfte überholt; offen bleibt der Verbundlauf. |
| 2026-09-01 | **Es gibt jetzt einen Provider-Wert `none`** für Research und Technical Agent ([ADR 0051](../adr/0051-research-im-dauerbetrieb-abgeschaltet.md)). Zum Auditzeitpunkt existierte er nicht; die Alternative `fixture` wäre im Scharfbetrieb fachlich falsch gewesen — der Fixture-Interpreter füllte 30 % des Swing-Scores mit identischen Konstanten und jede Meldungszeile mit „Fehlsignalrisiko medium", ohne Kennzeichnung. |
| 2026-09-01 | **Es gibt jetzt eine automatische Abhängigkeitsprüfung** (`.github/workflows/audit.yml`, wöchentlich, nicht blockierend). Abschnitt 13 des Audits führte sie als einzige unbearbeitete Sicherheitslücke — „nicht eingerichtet, unverändert seit Audit 1". Sie war keine Audit-Maßnahme; der erste Lauf hat gleich zwei Funde. **Beide sind beschieden:** `pytest` ist auf 9.1.1 gehoben (Suite unverändert grün), `sharp` bleibt bewusst stehen — transitiv und optional über Next.js 15, die Bildoptimierung führt ein statischer Export nicht aus; Neubewertung im Turnus, Vermerk in Doc 14 „Pflege". |
| 2026-09-01 | **Die Aufgabenplanung wird erstmals dauerhaft aktiv geschaltet** (Beschluss E-A2-2): alle Anbieter scharf, Research bewusst `none`, Technical Agent `anthropic`, Meldung `telegram`. Das Audit führte den Betriebszustand als nicht verifizierbar und widersprüchlich dokumentiert (A2-F007); ab jetzt gilt der Doc-14-Abschnitt „Betriebszustand". |
