# Nachverfolgung — Repository-Audit vom 2026-08-23

> **Dieses Dokument lebt.** Es wird fortgeschrieben, sooft sich ein Stand
> ändert — im Gegensatz zum [Audit selbst](2026-08-23-repository-audit.md),
> das als eingefrorene Momentaufnahme unverändert bleibt.

**Stand:** 2026-08-23

## Wozu dieses Dokument

Das Audit hält fest, wie das Repository am 2026-08-23 vorgefunden wurde. Es
darf nicht nachgeführt werden (`README.md` dieses Verzeichnisses) — genau das
macht es als Beleg brauchbar. Damit fehlt aber ein Ort, an dem steht, was von
seinen Maßnahmen, Entscheidungsvorlagen und Risiken inzwischen erledigt ist.
Das ist dieser Ort.

## Was hier **nicht** steht

Dieses Dokument führt **ausschließlich Status und Belegverweis, niemals
Inhalte.** Es entscheidet nichts, begründet nichts und fasst nichts zusammen.
Wer wissen will, *was* entschieden wurde, folgt dem Verweis. Maßgeblich
bleiben unverändert:

| Frage | Maßgebliche Quelle |
|---|---|
| Was ist entschieden? | `docs/adr/` |
| Was ist gefordert? | `docs/` (bei Widersprüchen Doc 10, siehe ADR 0001) |
| Was ist fachlich freigegeben? | `docs/requirements/` |
| Was tut das System tatsächlich? | der Quellcode und die Tests |

Widerspricht diese Tabelle einer der genannten Quellen, gilt die Quelle. Ein
Eintrag hier ist ein Zeiger, kein Nachweis.

## Statuswerte

| Wert | Bedeutung |
|---|---|
| **erledigt** | Die Definition of Done aus dem Audit ist erfüllt und belegt. |
| **teilweise** | Begonnen, aber die DoD ist nicht erfüllt. Der Rest steht ausdrücklich dabei. |
| **offen** | Unangetastet. |
| **verworfen** | Bewusst nicht umgesetzt, mit Begründung. |
| **entschieden** | Nur Entscheidungen: als ADR festgehalten. |
| **eingegrenzt** | Nur Risiken: besteht fort, aber Ursache und Weg sind belegt. |
| **geschlossen** | Nur Risiken: besteht nicht mehr. |

---

## Maßnahmen (M1–M14)

| # | Maßnahme (Kurzform, maßgeblich ist das Audit) | Status | Beleg / was noch fehlt |
|---|---|---|---|
| M1 | Doc 14 Stufe B: Head-Prüfung, F10-Zeile auf ADR 0024 | **erledigt** | PR #37, `eabcaca` |
| M2 | Projekt-`CLAUDE.md`: Gate-Abschnitt auf den Ist-Stand | **erledigt** | PR #37, `eabcaca` |
| M3 | E2 entscheiden, Tiefe messen, ggf. Backfill-Batch | **teilweise** | ADR 0027, ADR 0028; PR #37 (`9ce7391`, `2b8021d`). **Offen:** der Lauf über die volle Watchlist auf dem Server — siehe unten |
| M4 | E1 entscheiden, Ergebnis in den Sprint-5-Zuschnitt | **offen** | durch ADR 0028 entblockt, aber unentschieden |
| M5 | Golden-Master für Screener und Backtest | **erledigt**, mit Abweichung | PR #37, `813c539`, `backend/tests/golden/`. Abweichung siehe unten |
| M6 | Prompt-Injection-Test für den Research-Adapter | **offen** | — |
| M7 | E4 umsetzen: ADR zur Wochentagsnäherung | **offen** | — |
| M8 | E5-Paket Research-Qualität | **offen** | Dringlichkeit gestiegen, siehe E5 |
| M9 | README- und Roadmap-Status nachziehen | **offen** | — |
| M10 | Kopfvermerke Doc 01/02/04/05/06/07, `signal-specification.md` | **offen** | — |
| M11 | Deployment-ADR (E6) und Doc 13 neu | **offen** | braucht E6 |
| M12 | ADR-Nachträge zu 0006, 0009, 0011 | **offen** | — |
| M13 | Python-Version des Servers klären, Doku vereinheitlichen | **offen** | braucht Serverzugriff, siehe E12 ③ |
| M14 | Sammelposten P4 | **offen** | teils E12 |

### M3 — was genau fehlt

Entschieden (ADR 0027) und gemessen (ADR 0028) ist beides; `cli history-depth`
und `cli deepen-history` sind gebaut und getestet. Die Definition of Done des
Audits lautet aber „**Bestand** entspricht beschlossenem Anspruch". Bis der
Batch auf dem Windows-Server gelaufen ist, ist sie nicht erfüllt.

Maßgeblich für „durch" ist die Zeile **„Fehlgeschlagen"** im Bericht des
Laufs, nicht die Zeile „Unter dem Zielzeitraum" — Aktien, deren
Börsenhistorie kürzer ist als der Zielzeitraum, erreichen ihn nie und stehen
dort dauerhaft (Doc 14, Zwischenschritt Tiefen-Backfill).

### M5 — die Abweichung

Das Audit forderte den Golden Master „auf eingefrorenem **Realdaten**-
Ausschnitt". Geliefert sind **erzeugte** Bar-Reihen. Das ist bewusst so und
in `backend/tests/golden/generate_bars.py` im Kopf begründet: der reale
Bestand liegt auf dem Server, ein Golden Master soll auf jedem Rechner ohne
Netz laufen. Er friert damit das *Verfahren* ein, belegt aber nichts über das
Verhalten an echten Kursen (Lücken, Feiertage, Splits, Halts).

Der Weg dahin steht offen und kostet keine Codeänderung: `cli export-bars`
schreibt dasselbe Format aus dem Bestand, `available_cases()` nimmt jede
weitere `*.bars.csv` als zusätzlichen Fall auf.

---

## Entscheidungen (E1–E13)

Die E-Punkte des Audits sind **Vorlagen, keine Entscheidungen** — das sagt
das Audit in seinem Kopf selbst. Eine Entscheidung entsteht ausschließlich
als ADR.

| # | Gegenstand | Status | Beleg / Bemerkung |
|---|---|---|---|
| E1 | Backtesting in den Tageslauf? | **offen** | durch ADR 0028 entblockt |
| E2 | Historientiefe: Backfill oder Anspruch senken | **entschieden** | [ADR 0027](../adr/0027-historientiefe-messen-vor-anspruch.md) (Weg a), [ADR 0028](../adr/0028-historientiefe-gemessen.md) (Messergebnis) |
| E3 | Historische Earnings-Termine über SEC EDGAR | **offen** | durch ADR 0028 entblockt |
| E4 | Wochentagsnäherung ablösen? | **offen** | ADR 0020 L3 ist eine offene Zusage |
| E5 | Research-Qualitätspaket | **offen** | **Dringlichkeit gestiegen**, siehe unten |
| E6 | Deployment-Zielbild festschreiben | **offen** | — |
| E7 | Inhalt der Ergebnis-Benachrichtigung | **offen** | ADR 0024 gegen Doc 02 §2.12 |
| E8 | F12: externer Dashboard-Zugriff und Auth | **offen** | blockierend für Sprint 6 |
| E9 | `min_touches` → Wendepunkt-Filter | **offen** | ADR 0025; Bedingung: weitere Läufe an echten Kursen |
| E10 | Required Checks: Pro, public oder Status quo | **offen** | ADR 0009 |
| E11 | Kursziele nachrüsten | **offen** | ADR 0017; erst mit dem Scoring-Design |
| E12 | Drei Kleinigkeiten mit Entscheidungscharakter | **offen** | ③ braucht einen Blick auf den Server |
| E13 | US-007 „relevante Chartmuster": bauen oder streichen | **offen** | ADR 0026 |

### E5 — was sich gegenüber dem Audit geändert hat

Das Audit konnte den Betriebszustand des Servers ausdrücklich **nicht
verifizieren** und hat E5 deshalb an eine Bedingung geknüpft: „HOCH, sobald
`--research-provider anthropic` täglich läuft".

**Diese Bedingung ist eingetreten** — der Research Agent läuft im täglichen
Scharfbetrieb (Auskunft des Projektverantwortlichen, 2026-08-23; aus dem
Repository nicht belegbar). Damit sind die vier in ADR 0023 belegten Mängel
kein Vorsorgethema mehr: sie wirken bei jedem Lauf. E5 ist die
höchstpriorisierte offene Entscheidung.

---

## Risiken (R1–R10)

| # | Risiko / Schuld | Status | Beleg / Bemerkung |
|---|---|---|---|
| R1 | Kennzahlen suggerieren 5 Jahre, Basis ist ~1 Jahr | **eingegrenzt** | [ADR 0028](../adr/0028-historientiefe-gemessen.md): Tiefe belegt, Werkzeug gebaut. Schließt sich erst mit dem Serverlauf (M3) |
| R2 | Kein Golden Master, Verfahrensdrift unentdeckbar | **geschlossen** | PR #37, `813c539` |
| R3 | Projekt-`CLAUDE.md` mit veralteten Gates | **geschlossen** | PR #37, `eabcaca` |
| R4 | Doc 14 Stufe B bricht am falschen Head ab | **geschlossen** | PR #37, `eabcaca` |
| R5 | Research: Kostenstreuung und schwache Belegqualität | **offen — eingetreten** | Dauerbetrieb läuft, siehe E5. Behebung über M8 |
| R6 | Backtest ohne historischen Earnings-Filter | **offen** | ADR 0017 L9; Entscheidung E3 |
| R7 | Kein Merge-Schutz, CI-Grün nicht erzwungen | **offen** | ADR 0009/0011; Entscheidung E10 |
| R8 | Manuell gepflegte Preislisten veralten still | **offen** | M14 |
| R9 | Ein Thread-Pool für Research und Technical Agent | **offen** | M14 |
| R10 | `pushover` im Schema ungebaut | **offen** | M14; als bewusster Zustand getestet (`test_pushover_ist_weiterhin_nicht_gebaut`) |

---

## Ergänzungen gegenüber dem Audit

Punkte, die das Audit so nicht wissen konnte, weil sie außerhalb des
Repositories liegen oder erst danach entstanden sind. Sie ersetzen keine
Feststellung des Audits — sie stehen daneben.

| Datum | Ergänzung |
|---|---|
| 2026-08-23 | Der Research Agent läuft im täglichen Scharfbetrieb. Das Audit führte den Betriebszustand des Servers als nicht verifizierbar. Folge: E5/R5 sind eingetreten, nicht mehr vorsorglich. |
| 2026-08-23 | IBKR zählt `durationStr` bei Intraday-Bars in **Handelstagen**, nicht Kalendertagen — gemessen, nicht dokumentiert (ADR 0028). Das Audit ging bei der Bewertung von E2 von Kalendertagen aus. |
