# Nachverfolgung zum Audit vom 2026-09-20

Lebendes Begleitdokument zum [Repository-Audit 3](2026-09-20-repository-audit-3.md).

Es führt **ausschließlich Status und Belegverweis, niemals Inhalte** — der
Befund selbst steht im Audit und wird dort nicht geändert. Der Beleg ist
immer ein Zeiger: ADR-Nummer, Pull Request, Commit, Datei.

**Stand:** 2026-09-20, Anlage. Noch nichts bearbeitet.

---

## Befunde

| # | Kurzform | Severity | Status | Beleg / was noch fehlt |
|---|---|---|---|---|
| AUDIT-003-001 | Aktiensplit zerreißt die Kursreihe unbemerkt | **Critical** | offen | Sprungprüfung im Backfill, `cli refetch-bars`, ADR zur Schwelle |
| AUDIT-003-002 | Keine automatisierte Datensicherung im Betrieb | **Critical** | offen | Task eintragen (23:45), erster Lauf, Zählprobe — schließt zugleich A2-M4 |
| AUDIT-003-003 | `EARNINGS_EXCLUDED` schließt nichts aus | High | offen | Entscheidung Variante A/B/C, ADR, Kennzeichnung in Meldung und Bericht |
| AUDIT-003-004 | Empfehlungsstufe ignoriert die Datenabdeckung | High | offen | Deckel `cap_low_coverage`, Abdeckung in die Meldung, ADR (löst ADR 0046 in diesem Punkt ab) |
| AUDIT-003-005 | Liquiditätswarnungen erreichen die Meldung nicht | High | offen | Stufe in die Put-Zeile; drei Zusagen richtigstellen; ggf. ADR zu `POOR` |
| AUDIT-003-006 | Sicherung nur lokal — kein Disaster Recovery | High | offen | ADR zu Ziel, Verschlüsselung und Aufbewahrung; danach Umsetzung |
| AUDIT-003-007 | Ergebnismeldung ohne Wiederholversuch und ohne Spur | Medium | offen | Vermerk am Laufdatensatz + Nachholen; Wiederholversuch im Adapter |
| AUDIT-003-008 | Kein Retry bei 429/5xx; Wiederholsperre friert das Ergebnis ein | Medium | offen | Backoff in Finnhub- und EDGAR-Adaptern; ggf. Nachtrag zu ADR 0054 |
| AUDIT-003-009 | Scoring-Schwellen und -Version können auseinanderlaufen | Medium | offen | Prüfsummentest; optional zweiter Golden Master über die Score-Kette |
| AUDIT-003-010 | Optionsnotierungen ohne Zeitstempel und Marktdatenmodus | Medium | offen | Migration `quoted_at`, `market_data_type`; Nachtrag zu ADR 0058 |
| AUDIT-003-011 | Backtest bildet die Wiederholsperre nicht ab, ohne Kennzeichen | Medium | offen | Berichtsvermerk nach dem Muster `earnings_exclusion_applied` |
| AUDIT-003-012 | Prämie = Mid, ohne Gebühren | Medium | offen | Benennung in Bericht und Meldungslegende; ggf. Nachtrag zu ADR 0048 |
| AUDIT-003-013 | Kein Protokoll im Betrieb (`logging.file` aus) | Medium | offen | `--log-file var/logs/tageslauf.log` in die Task-Argumente |
| AUDIT-003-014 | Stille Ausfallarten; kein Wächter | Medium | offen | Zeitlimit 3 h, Aufgabenverlauf an, `send_when_no_candidates`, Wächter-Task |
| AUDIT-003-015 | Warm-up verkürzt das Backtestfenster um ~6 Monate | Low | offen | `_truncate_to_recent_history` erweitern; Neuaufzeichnung + Versionssprung |
| AUDIT-003-016 | `/docs`, `/redoc`, `/openapi.json` offen | Low | offen | vor Einrichtung von Doc 14, Stufe J schließen |
| AUDIT-003-017 | Tote Modellprofile `llm.fundamental`, `llm.report` | Low | offen | streichen, Nachtrag zu ADR 0021 (Muster ADR 0024/`pushover`) |
| AUDIT-003-018 | Doc 13 behauptet „Sicherungsverfahren nicht beschlossen" | Low | offen | Verweis auf Doc 14, Muster Doc 10 §15 |
| AUDIT-003-019 | `cli.py` mit 5.055 Zeilen | Low | offen | kein Auditnebenprodukt — eigenes Vorhaben, falls angegangen |
| AUDIT-003-020 | Survivorship Bias der Watchliste | Informational | offen | ein Satz an der Gesamtzeile des Optionsbacktests |
| AUDIT-003-021 | ADR 0068/0069 gemergt, nicht ausgerollt | Informational | offen | Aktualisierung nach Doc 14; ADR-0068-Status klären |

---

## Übernommene Punkte aus früheren Audits

Fortgeschrieben werden hier nur die, die dieses Audit als weiterhin offen
oder nur teilweise erledigt bestätigt hat. Die vollständige Reconciliation
steht in Abschnitt 6 des Audits.

| ID | Herkunft | Kurzform | Status | Verweis |
|---|---|---|---|---|
| A2-M4 | Audit 2 | Backup/Restore minimal | **teilweise**, unverändert seit 2026-09-01 | geht in AUDIT-003-002 auf |
| A2-M11 | Audit 2 | Dashboard-Sprint | **teilweise** — Stufe J steht aus | berührt AUDIT-003-016 |
| A2-F006 | Audit 2 | Gemessene Schwellen ohne Turnus | **teilweise** — Turnus da, Versionskopplung fehlt | geht in AUDIT-003-009 auf |
| R1 | Audit 1 | Historientiefe | **teilweise** — effektiv ~4,5 statt 5 Jahre | geht in AUDIT-003-015 auf |
| R6 | Audit 1 | Backtest misst andere Strategie | **eingegrenzt**, Muster unvollständig | geht in AUDIT-003-011 auf |
| R8 | Audit 1 | Preislisten veralten still | **offen**, Fläche erweitert | geht in AUDIT-003-009 auf |

Geschlossen und hier nicht weiter geführt: R2, R3, R4, R5, R7, R9, R10,
A2-M1, A2-M2, A2-M3, A2-M5, A2-M6, A2-M7, A2-M8, A2-M9, A2-M10, A2-F001
bis A2-F005, A2-F008.

---

## Entscheidungen

Punkte, die vor der Umsetzung eine Festlegung des Projektinhabers brauchen.

| # | Gegenstand | Status | Bemerkung |
|---|---|---|---|
| E-A3-1 | Schwelle der Sprungprüfung auf Bars | **offen** | ADR 0028 hat den Fall ausdrücklich an ein eigenes ADR verwiesen |
| E-A3-2 | Wirkung von `EARNINGS_EXCLUDED` (kennzeichnen / ausschließen / §6.5 ablösen) | **offen** | Empfehlung des Audits: Variante A (kennzeichnen) |
| E-A3-3 | Deckel bei niedriger Datenabdeckung | **offen** | ändert ADR 0046, hebt `recommendation.version` |
| E-A3-4 | Schließt `POOR`-Liquidität einen Put-Vorschlag aus? | **offen** | unabhängig davon gehört die Stufe in die Meldung |
| E-A3-5 | Ziel, Verschlüsselung und Aufbewahrung der Sicherung außer Haus | **offen** | die letzte offene Mindestanforderung aus Doc 10 §15 |
| E-A3-6 | Gebührensatz in der Optionsrendite ausweisen? | **offen** | nur sinnvoll, wenn gemessen statt geraten |
| E-A3-7 | Wiederholsperre bei degradierter Analyse aussetzen? | **offen** | Nachtrag zu ADR 0054; Kosten gegen Vollständigkeit |

---

## Ergänzungen gegenüber dem Audit

Punkte, die nach dem 2026-09-20 entstanden sind oder außerhalb des
Repositorys liegen.

| Datum | Ergänzung |
|---|---|
| — | noch keine |
