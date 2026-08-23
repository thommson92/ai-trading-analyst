# Audits

Historische Bestandsaufnahmen des Repositories.

Ein Audit hält fest, **wie das Projekt zu einem Zeitpunkt vorgefunden wurde** —
Implementierungsstand, Abweichungen zwischen Code und Dokumentation, Testlage,
Risiken. Es ist eine Momentaufnahme und wird nach seiner Erstellung **nicht
nachgeführt**.

## Abgrenzung

Ein Audit ist **keine Entscheidung und keine Anforderung.** Es trifft keine
Festlegung, ändert keinen ADR-Status und ersetzt kein Dokument. Maßgeblich
bleiben ausschließlich:

| Frage | Maßgebliche Quelle |
|---|---|
| Was ist entschieden? | `docs/adr/` |
| Was ist gefordert? | `docs/` (bei Widersprüchen `docs/10 - System Architecture.md`, siehe ADR 0001) |
| Was ist fachlich freigegeben? | `docs/requirements/` |
| Was tut das System tatsächlich? | der Quellcode und die Tests |

Enthält ein Audit einen Entscheidungsvorschlag, wird daraus eine Entscheidung
erst, wenn ein ADR sie festhält. Weicht ein Audit von einer der oben genannten
Quellen ab, gilt die Quelle — nicht das Audit.

## Namenskonvention

`JJJJ-MM-TT-<kurzbeschreibung>.md`, benannt nach dem Datum der Durchführung.
Jedes Audit nennt in seinem Metadatenblock den untersuchten Branch, den
vollständigen Commit-SHA, den Zustand des Working Tree, das verwendete Modell
sowie seine bekannten Einschränkungen.

Ein Audit wird **nicht rückwirkend geändert** — dieselbe Regel wie bei ADRs
(`docs/adr/README.md`). Ist eine Feststellung überholt, entsteht ein neues
Audit; die alte Momentaufnahme bleibt als Beleg erhalten, wie der Stand damals
war.

## Nachverfolgung

Weil ein Audit eingefroren bleibt, steht in ihm nie, was von seinen Maßnahmen
inzwischen erledigt ist. Dafür bekommt jedes Audit ein **lebendes**
Begleitdokument:

`JJJJ-MM-TT-nachverfolgung.md`

Es übernimmt die Kennungen des zugehörigen Audits (M…, E…, R…) und führt
**ausschließlich Status und Belegverweis, niemals Inhalte** — sonst entstünde
neben ADRs, Docs und Quellcode eine vierte Quelle, die still veraltet. Der
Beleg ist immer ein Zeiger: ADR-Nummer, Pull Request, Commit, Datei.

Je Audit eine eigene Nachverfolgung, nicht eine gemeinsame über alle hinweg:
Die Kennungen sind auditspezifisch, ein neues Audit nummeriert neu. Ist ein
Audit durch ein neueres abgelöst, wird seine Nachverfolgung nicht mehr
fortgeschrieben — auch sie ist dann Beleg.

## Übersicht

| Datum | Audit | Commit | Gegenstand |
|---|---|---|---|
| 2026-08-23 | [Repository-Audit](2026-08-23-repository-audit.md) | `f61f316` (`dev`) | Vollständiger Ist-Soll-Abgleich über Code, Tests, alle 26 ADRs, Requirements und Dokumentation nach Abschluss des Technical Agent (PR #35) |

Erledigungsstand: [Nachverfolgung zum Audit vom 2026-08-23](2026-08-23-nachverfolgung.md).
