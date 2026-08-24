# Nachverfolgung — Repository-Audit vom 2026-08-23

> **Dieses Dokument lebt.** Es wird fortgeschrieben, sooft sich ein Stand
> ändert — im Gegensatz zum [Audit selbst](2026-08-23-repository-audit.md),
> das als eingefrorene Momentaufnahme unverändert bleibt.

**Stand:** 2026-08-24 (nach PR #38 und PR #39 sowie dem Serverlauf vom
2026-08-24)

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
| M3 | E2 entscheiden, Tiefe messen, ggf. Backfill-Batch | **erledigt** | ADR 0027, ADR 0028; PR #37 (`9ce7391`, `2b8021d`); Serverlauf über die volle Watchlist am 2026-08-24 — siehe unten |
| M4 | E1 entscheiden, Ergebnis in den Sprint-5-Zuschnitt | **offen** | durch ADR 0028 entblockt, aber unentschieden |
| M5 | Golden-Master für Screener und Backtest | **erledigt**, mit Abweichung | PR #37, `813c539`, `backend/tests/golden/`. Abweichung siehe unten |
| M6 | Prompt-Injection-Test für den Research-Adapter | **erledigt** | `backend/tests/unit/.../test_provider.py::TestPromptInjection`, fünf gegengeprobte Sonden. Dabei eine echte Lücke gefunden und geschlossen, siehe unten |
| M7 | E4 umsetzen: ADR zur Wochentagsnäherung | **offen** | — |
| M8 | E5-Paket Research-Qualität | **erledigt** | [ADR 0029](../adr/0029-research-qualitaet.md) samt Nachträgen; Vergleichslauf 2026-08-24 gemessen — siehe unten |
| M9 | README- und Roadmap-Status nachziehen | **erledigt** | `README.md`, `docs/03 - Roadmap.md` |
| M10 | Kopfvermerke Doc 01/02/04/05/06/07, `signal-specification.md` | **erledigt** | Kopfvermerk je Dokument; G1-Status auf „freigegeben" (ADR 0010) |
| M11 | Deployment-ADR (E6) und Doc 13 neu | **offen** | braucht E6 |
| M12 | ADR-Nachträge zu 0006, 0009, 0011 | **erledigt** | je ein `### Nachtrag`-Abschnitt; Entscheidungstexte unberührt |
| M13 | Python-Version des Servers klären, Doku vereinheitlichen | **erledigt** | Server läuft auf 3.13 (Auskunft 2026-08-23); Doc 14 und README benennen den Unterschied zum Entwicklungsrechner |
| M14 | Sammelposten P4 | **offen** | teils E12 |

### M3 — womit die Definition of Done erfüllt ist

Entschieden (ADR 0027), gemessen (ADR 0028), Werkzeug gebaut (`cli
history-depth`, `cli deepen-history`). Die Definition of Done des Audits
lautete „**Bestand** entspricht beschlossenem Anspruch" und hing damit an
einem Lauf außerhalb des Repositories.

Der Tiefen-Backfill über die volle Watchlist ist am **2026-08-24** auf dem
Windows-Server durchgelaufen (Auskunft des Projektverantwortlichen; aus dem
Repository nicht belegbar). Maßgeblich für „durch" war die Zeile
**„Fehlgeschlagen"** im Bericht des Laufs, nicht „Unter dem Zielzeitraum" —
Aktien mit kürzerer Börsenhistorie erreichen den Zielzeitraum nie und stehen
dort dauerhaft (Doc 14, Zwischenschritt Tiefen-Backfill).

Damit ist auch R1 geschlossen: Der Backtest erreicht für
`PRICE_EMA20_BREAKOUT+RSI_CROSS` auf allen fünf geprüften Aktien die Stufe
`NORMAL` (n = 44–60) statt `LOW_SAMPLE`.

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

Seit dem Tiefen-Backfill vom 2026-08-24 ist die Abweichung **nicht mehr durch
fehlende Daten begründet** — der Bestand reicht fünf Jahre zurück. Sie besteht
fort, weil niemand den Ausschnitt gezogen hat, nicht weil es ihn nicht gäbe.

### M6 — was der Test gefunden hat

Die Sonden waren als reine Absicherung geplant und haben eine tatsächliche
Lücke aufgedeckt: Die Strukturierungsphase bekam den Recherchetext zwischen
`<recherchetext>`-Tags, ohne dass der Text gegen seine eigene Abgrenzung
gesichert war. Ein Suchtreffer oder abgerufenes Dokument, das das
schließende Tag enthält, hätte die Datenregion vorzeitig beendet — alles
danach wäre in Instruktionsposition gelandet.

Geschlossen in `_build_structure_prompt` / `_neutralize_delimiters`
(`infrastructure/anthropic/provider.py`): Die Tags werden im Text unkenntlich
gemacht und der Vorgang protokolliert. Der Bericht wird nicht verworfen — ein
legitimer Recherchetext enthält sie nicht, und ein Lauf ist zu teuer, um ihn
an einem Zeichenspiel scheitern zu lassen.

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
| E4 | Wochentagsnäherung ablösen? | **offen** | ADR 0020 L3 ist eine offene Zusage. Zur Fehlerrichtung siehe unten |
| E5 | Research-Qualitätspaket | **entschieden** | [ADR 0029](../adr/0029-research-qualitaet.md) — ersetzt Teile von ADR 0023 |
| E6 | Deployment-Zielbild festschreiben | **offen** | — |
| E7 | Inhalt der Ergebnis-Benachrichtigung | **offen** | ADR 0024 gegen Doc 02 §2.12 |
| E8 | F12: externer Dashboard-Zugriff und Auth | **offen** | blockierend für Sprint 6 |
| E9 | `min_touches` → Wendepunkt-Filter | **offen** | ADR 0025; Bedingung: weitere Läufe an echten Kursen |
| E10 | Required Checks: Pro, public oder Status quo | **offen** | ADR 0009 |
| E11 | Kursziele nachrüsten | **offen** | ADR 0017; erst mit dem Scoring-Design |
| E12 | Drei Kleinigkeiten mit Entscheidungscharakter | **teilweise** | ③ beantwortet: Server auf 3.13 (→ M13). ① `fallback_model` und ② der `temperature=0`-Doppellauf sind offen |
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

### E5 — was beim Umsetzen dazukam

Zwei Befunde, die in der Entscheidungsvorlage des Audits nicht stehen, weil
sie erst beim Lesen von Adapter und SDK sichtbar wurden:

- **Der Systemprompt nannte die abrufbaren Domains nicht.** Er sagte nur „auf
  wenige vertrauenswürdige Domains beschränkt". Das Modell musste raten, und
  jeder Fehlgriff verrechnete den gesamten Kontext erneut. Dies wurde beim
  Planen als „wahrscheinlich größte Einzelursache der Kostenstreuung"
  eingeschätzt — **der Vergleichslauf hat das widerlegt**, siehe unten.
- **Suchtreffer wurden gar nicht ausgewertet.** `_scan_tool_result` stieg bei
  einer Liste sofort aus. Dadurch war `page_age` unerreichbar — das einzige
  Alterssignal, das die API liefert, und die Grundlage für den Umgang mit
  `published_at`.

### E5 — was der Vergleichslauf ergeben hat

Gemessen am 2026-08-24 auf dem Windows-Server, dasselbe Symbol (AAPL) vor und
nach der Umstellung:

| | `dev` (vorher) | `research-v2` (nachher) |
|---|---|---|
| Kosten | 0,524 USD | 0,584 USD |
| Eingabe-Token, ungecacht | 113.685 | 120.933 |
| Abgelehnte Werkzeugaufrufe | 1 | 0 |
| Erfolgreiche Abrufe | — | 0 |
| Zitate gespeichert / Quellen | 38 / 19 | 25 (von 29) / 14 |
| Quellenrang, Quellenalter, Abdeckung | fehlten | belegt, `LIMITED` |

**Die Qualitätswirkung ist eingetreten, die Kostenwirkung nicht.** Rang, Alter,
Deckelung und Abdeckung greifen am echten Lauf. Die Domainnennung hat den einen
abgelehnten Abruf beseitigt, den es gab (rund 0,3 % der Kosten); der längere
Prompt kostete mehr, als er sparte. E5 war eine Qualitätsmaßnahme.

Der Kostenanteil liegt zu 62 % bei der Eingabe (120.933 Token), zu 29 % bei der
Ausgabe (11.386) und zu 9 % bei der Websuche (5 Anfragen). Festgehalten in
ADR 0029, Nachträge.

### E4 — die Fehlerrichtung der Näherung

Das Audit empfiehlt für E4 den Verbleib bei der Wochentagsnäherung mit der
Begründung, die Abweichung „wirkt konservativ". **Die Richtung stimmt nicht.**

`count_future_trading_candles` (`domain/earnings/calendar.py`) zählt Feiertage
als Handelstage, also **zu hoch**. `evaluate_earnings_filter` schließt aus,
wenn `candles_until_earnings <= configured_exclusion_candles`. Ein zu hoher
Wert lässt den Termin weiter weg erscheinen — der Filter schließt damit
**seltener** aus als er sollte, nicht öfter. Der Fehler zeigt in die riskante
Richtung.

Das ändert nicht, welche Option richtig ist, wohl aber ihre Begründung. Ein
ADR zu E4 darf sich nicht auf die Konservativitäts-Annahme des Audits stützen.

---

## Risiken (R1–R10)

| # | Risiko / Schuld | Status | Beleg / Bemerkung |
|---|---|---|---|
| R1 | Kennzahlen suggerieren 5 Jahre, Basis ist ~1 Jahr | **geschlossen** | [ADR 0028](../adr/0028-historientiefe-gemessen.md); Tiefen-Backfill über die volle Watchlist am 2026-08-24 durchgelaufen (M3). Backtest erreicht `NORMAL` statt `LOW_SAMPLE` |
| R2 | Kein Golden Master, Verfahrensdrift unentdeckbar | **geschlossen** | PR #37, `813c539` |
| R3 | Projekt-`CLAUDE.md` mit veralteten Gates | **geschlossen** | PR #37, `eabcaca` |
| R4 | Doc 14 Stufe B bricht am falschen Head ab | **geschlossen** | PR #37, `eabcaca` |
| R5 | Research: Kostenstreuung und schwache Belegqualität | **eingegrenzt** | Belegqualität behoben und am echten Lauf bestätigt (ADR 0029). Die Kostenwirkung ist **gemessen und ausgeblieben** — siehe unten |
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
| 2026-08-23 | Der Server läuft auf **Python 3.13**, nicht 3.12 (Auskunft des Projektverantwortlichen). Damit ist E12 ③ beantwortet und M13 erledigt. |
| 2026-08-23 | Die in ADR 0011 beschriebene CI-Dispatch-Schwäche besteht nicht mehr: 171 Läufe statt der damaligen 3, beide Trigger feuern. Das Audit führte GitHub-seitige Zustände als aus dem Repository nicht verifizierbar. Der fehlende Merge-Schutz (R7) bleibt davon unberührt. |
| 2026-08-24 | Der Tiefen-Backfill über die volle Watchlist ist auf dem Windows-Server durchgelaufen. Damit ist M3 erledigt und R1 geschlossen. |
| 2026-08-24 | **Es gibt kein automatisches Prompt-Caching.** Der Lauf meldet 120.933 ungecachte gegen 0 gelesene und 0 geschriebene Cache-Token. Der Docstring von `_UsageTotals.input_tokens` behauptete das Gegenteil und trug damit die Begründung der Budgetbremse; korrigiert. |
| 2026-08-24 | Ein Research-Lauf besteht aus **zwei** Anfragen — Recherche und Strukturierung —, nicht aus mehreren Recherche-Runden. `pause_turn` trat nicht auf. Die Token entstehen in der serverseitigen Werkzeugschleife *innerhalb einer* Anfrage. |
| 2026-08-24 | Zwischen den beiden Anfragen lagen **921 Sekunden**. `max_retries` war beim Anthropic-Client nicht gesetzt (SDK-Standard: 2) und `timeout` lag als Skalar auf dem Lesetimeout — 300 + 300 + ~320 s passt auf die Sekunde. Eine abgelaufene Anfrage erzeugt keine Logzeile, wird aber berechnet. Hypothese, die die Protokollierung je Anfrage beantwortet. |
| 2026-08-24 | `fetch_allowed_domains` deckt keine Domain ab, die in den realen Suchtreffern vorkam — der Lauf machte **null Abrufe**, ohne einen einzigen Fehlversuch. Ausgerechnet `apple.com/newsroom`, die beste Quelle des Laufs, ist nicht abrufbar. |
