# ADR 0031: Merge-Schutz auf `main` und `dev` — die Sperre steht

- Status: Angenommen
- Datum: 2026-08-24
- Löst ab: [ADR 0009](0009-required-checks-nicht-konfigurierbar.md)

## Kontext

[ADR 0009](0009-required-checks-nicht-konfigurierbar.md) hat am 2026-08-06
festgehalten, dass Required Status Checks für dieses Repository nicht
konfigurierbar sind: Branch-Protection- und Rulesets-API antworteten mit

```
403 Upgrade to GitHub Pro or make this repository public to enable this feature.
```

Das ADR hat den offenen Punkt ausdrücklich nicht eigenmächtig geschlossen —
öffentlich zu stellen „exponiert Code und potenziell Rückschlüsse auf die
Handelsstrategie" — und die Entscheidung dem Projektinhaber überlassen. Sie
wurde als **E10** in der Nachverfolgung des Repository-Audits vom 2026-08-23
geführt, das Fehlen der Sperre als Risiko **R7**.

Der Projektinhaber hat das Repository am 2026-08-24 auf **öffentlich**
gestellt. Damit ist die Voraussetzung erfüllt, die ADR 0009 als zweiten der
zwei Wege genannt hatte, und der offene Punkt ist fällig.

## Entscheidung

**Beide Branches sind geschützt, grüne CI ist erzwungen — mit einem
Notausgang für den Repository-Inhaber.**

Gesetzt über die klassische Branch-Protection-API, gleichlautend für `main`
und `dev`:

| Einstellung | Wert | Wirkung |
|---|---|---|
| `required_status_checks.contexts` | die fünf CI-Jobs (unten) | Ohne grüne CI kein Merge |
| `required_pull_request_reviews.required_approving_review_count` | **0** | Ein PR ist Pflicht, eine Freigabe nicht |
| `enforce_admins` | **false** | Der Inhaber kann im Notfall durchgreifen |
| `allow_force_pushes` | false | Historie bleibt nachvollziehbar |
| `allow_deletions` | false | Kein versehentliches Löschen von `dev` |
| `required_conversation_resolution` | true | Ein Review-Befund verschwindet nicht durch Wegscrollen |
| `required_status_checks.strict` | **false** | siehe L1 |

Die erforderlichen Checks, mit den Namen, unter denen GitHub sie meldet:

```
Backend (lint, typecheck, test, Python 3.12)
Backend (lint, typecheck, test, Python 3.13)
Backend unter Windows (Installation, Tests ohne Datenbank)
Frontend (lint, typecheck, build)
Keine Geheimnisse im Repository
```

Das sind fünf, nicht die drei aus ADR 0009: Die Backend-Matrix ist seit M13
auf zwei Python-Versionen gewachsen (3.12 Entwicklung, 3.13 Server), und der
Windows-Job ist dazugekommen.

### Drei Abweichungen vom vorbereiteten Kommando aus ADR 0009

ADR 0009 hatte den Aufruf vorbereitet, mit dem der Punkt zu schließen wäre.
Drei seiner Parameter sind bewusst anders gesetzt worden — das gehört
benannt, sonst sieht es aus wie ein Versehen:

**`enforce_admins`: `true` vorbereitet, `false` gesetzt.** Bei einem
Ein-Personen-Projekt ist der Inhaber die einzige Person, die einen
klemmenden Zustand auflösen kann. Ein Flake in einem Windows-Job oder ein
Ausfall bei GitHub würde ihn sonst aus seinem eigenen Repository aussperren,
ohne dass jemand anders eingreifen könnte. Der Schutz richtet sich hier nicht
gegen Böswilligkeit, sondern gegen Unachtsamkeit — und dagegen wirkt er auch
ohne Zwang gegen den Inhaber.

**`required_pull_request_reviews`: `null` vorbereitet, mit 0 Freigaben
gesetzt.** Das ist die *strengere* Variante: `null` hätte den Pull Request
nicht zur Pflicht gemacht. Ein direkter Push wäre damit nicht frei gewesen —
die Required Status Checks gelten auch für ihn —, aber er wäre möglich
geblieben, sobald die Checks auf dem gepushten Commit grün sind. Mit dem
gesetzten Block ist der Pull Request selbst Pflicht, was die Arbeitsweise
ohnehin verlangt und bisher nur Disziplin war.

**`required_status_checks.strict`: `true` vorbereitet, `false` gesetzt.**
Die dritte Abweichung, und die einzige, die den Schutz *schwächt* statt ihn
zu verschieben. Begründung und Preis stehen unten in L1.

**Die Zahl muss 0 sein.** GitHub lässt niemanden den eigenen Pull Request
freigeben. Jede andere Zahl machte den Merge-Knopf für den einzigen
Entwickler unerreichbar — er käme dann nur noch über den Notausgang an
seinem eigenen Schutz vorbei, also über genau den Weg, den die Regel
verhindern soll.

## Einschränkungen

| # | Einschränkung |
|---|---|
| **L1** | **`strict` steht auf `false` — abweichend von ADR 0009, das `true` vorbereitet hatte: Ein PR kann grün sein und nach dem Merge trotzdem brechen.** Die Checks laufen gegen den Stand des PR-Zweigs, nicht gegen `dev` plus PR. Bewegt sich `dev` währenddessen, bleibt ein semantischer Konflikt unentdeckt. `strict: true` schlösse das, verlangte dafür aber, jeden offenen PR nach jedem Merge nachzuziehen und die CI erneut laufen zu lassen. Bei sequentiell bearbeiteten, kurzlebigen Zweigen ist der Nutzen gering und der Aufwand ständig — die Abwägung kippt, sobald mehrere PRs gleichzeitig offen stehen. Umschaltbar mit einem Parameter. |
| **L2** | **Der Notausgang ist einer.** `enforce_admins: false` heißt, dass ein unachtsamer Direkt-Push nach `dev` möglich bleibt, wenn er bewusst am PR vorbei erfolgt. Die Sperre erzwingt den Weg, sie verhindert nicht, dass jemand mit den Rechten dazu ihn verlässt. |
| **L3** | **Die Check-Namen sind Zeichenketten und keine Referenz.** Wird ein Job in `ci.yml` umbenannt, wartet die Sperre auf einen Check, den es nicht mehr gibt — und blockiert jeden Merge, statt ihn durchzulassen. Die Fehlerrichtung ist damit die ungefährliche, aber wer einen Job umbenennt, muss die Liste hier nachziehen. |
| **L4** | **Öffentlich ist eine Einbahnstraße.** Der Schutz wurde erst durch das Öffentlichmachen möglich. Ein Zurückstellen auf privat nähme ihn wieder weg — und der bis dahin veröffentlichte Stand bliebe in Forks und Caches ohnehin bestehen. Die Voraussetzung dieses ADR ist damit praktisch dauerhaft. |

## Konsequenzen

- **R7 ist geschlossen, E10 entschieden.** Die Interimsregel aus ADR 0009
  („kein Merge ohne `gh pr checks`") ist nicht mehr die einzige Absicherung.
  Sie bleibt trotzdem sinnvoll, weil sie den Fehler früher zeigt als der
  blockierte Merge-Knopf.
- Der Arbeitsablauf ändert sich nicht: Feature-Zweig von `dev`, PR zurück
  nach `dev`. Was bisher Vereinbarung war, ist jetzt erzwungen.
- Ein neuer CI-Job wird **nicht** automatisch zur Merge-Bedingung. Wer einen
  hinzufügt und ihn erzwingen will, trägt ihn in beide Branch-Schutzregeln
  ein.
- Der Job `Keine Geheimnisse im Repository` bleibt, obwohl GitHubs Secret
  Scanning mit Push Protection inzwischen aktiv ist. Die beiden prüfen
  Verschiedenes: GitHub sucht nach Mustern bekannter Anbieter-Schlüssel, der
  Job danach, ob `.env` eingecheckt wurde und ob in `config/default.yaml` ein
  geheimnisverdächtiger Schlüssel auftaucht — genau die Regel aus Doc 10,
  Paragraph 20, die kein Anbietermuster kennt.

## Alternativen, die nicht gewählt wurden

**GitHub Pro und das Repository privat lassen.** Der zweite in ADR 0009
genannte Weg. Er kostet dauerhaft Geld für eine Funktion, die im
öffentlichen Repository kostenlos ist, und hätte den Nebeneffekt gehabt, den
das Öffentlichmachen mitbringt — Secret Scanning und Push Protection —
gerade nicht mitgeliefert.

**Rulesets statt klassischer Branch Protection.** Funktional gleichwertig für
das hier Benötigte und in der Bedienung moderner, aber mit einer
Bypass-Modellierung über Rollen, die auf einem persönlichen Repository ohne
Organisation umständlicher ist als das eine `enforce_admins: false`. Ein
Wechsel wäre jederzeit möglich und wäre kein neues ADR wert.
