# ADR 0011: GitHub-Actions-Workflow-Dispatch ist unzuverlaessig (Plattformseitig)

- Status: Angenommen (mit offenem Punkt)
- Datum: 2026-08-07

## Kontext

Seit Sprint 0 fiel wiederholt auf, dass fuer neue Pushes bzw. Pull Requests
kein neuer CI-Lauf sichtbar wurde. Bislang wurde das als generelle Aussage
("CI dispatcht nicht") behandelt. Vor dem Merge von PR #5 (Sprint 1B) wurde
das konkret untersucht, wie vom Nutzer gefordert: `on:`-Trigger, Branch-
Filter, Actions-Einstellungen des Repositories, Workflow-Berechtigungen und
ob GitHub den Workflow ueberhaupt erkennt.

### Gepruefte Konfiguration -- unauffaellig

- `on: push: branches: [main, dev]` und `on: pull_request: branches: [main,
  dev]` (`.github/workflows/ci.yml`) -- korrekt auf die tatsaechlich
  verwendeten Zielbranches begrenzt. `branches:` bei `pull_request` filtert
  auf den **Base**-Branch, nicht den Head-Branch; alle betroffenen PRs haben
  `dev` als Base und erfuellen den Filter.
- `gh api .../actions/workflows`: Der Workflow ist `"state": "active"` --
  GitHub erkennt die Datei.
- `gh api .../actions/permissions`: `"enabled": true, "allowed_actions":
  "all"` -- Actions sind fuer das Repository nicht deaktiviert.
- `gh api .../actions/permissions/workflow`:
  `"default_workflow_permissions": "read"` -- unproblematisch, der Workflow
  selbst deklariert bereits explizit `permissions: contents: read` und
  benoetigt keine weiteren Rechte (kein Push, kein PR-Kommentar).
- Repository ist kein Fork, nicht archiviert, nicht deaktiviert
  (`fork/archived/disabled: false`). Alle PRs sind `isCrossRepository:
  false` -- kein Fork-PR-Sonderfall mit ausstehender Workflow-Genehmigung.

**Fazit zur Konfiguration: Es liegt keine erkennbare Fehlkonfiguration im
Repository vor**, die das Ausbleiben von Runs erklaeren wuerde.

### Beobachtetes tatsaechliches Verhalten -- das eigentliche Problem

`gh api repos/thommson92/TradingViewAnalyzer/actions/runs` liefert ueber die
gesamte bisherige Repository-Historie **`total_count: 3`** -- fuer inzwischen
fuenf Pull Requests:

| PR | Branch | Erstellt | Gemergt | CI-Runs |
|---|---|---|---|---|
| #1 | sprint-0a-projektgrundlage | -- | -- | 2 (1× `success`, 1× seit Erstellung dauerhaft `queued`, nie gestartet) |
| #2 | gate-g1-signal-specification | 19:50:34 | 20:21:18 | **0** |
| #3 | sprint-1a-signalkern | 20:18:04 | 20:22:14 | **0** |
| #4 | gate-g1-freigabe-dokumentation | 20:34:41 | 20:39:01 | 1 (`created_at` 21:04:43 -- **25 Minuten nach dem Merge**, ein Teiljob haengt 15 Minuten und wird als `cancelled` beendet) |
| #5 | sprint-1b-walking-skeleton | 21:32:13 | -- | **0** (auch Stunden spaeter noch immer kein Run) |

Der stecken gebliebene zweite Run von PR #1 zeigt `status: "queued"` mit
`run_started_at` mehrere Stunden nach `created_at` und ohne dass je ein
Runner zugewiesen wurde (0 abgerechnete Millisekunden).

Diese Belege zeigen zwei getrennte Symptome, keine Fehlkonfiguration:

1. **Vollstaendig ausbleibende Runs** fuer PR #2, #3 und #5 -- kein
   Workflow-Run-Objekt wird jemals erzeugt, auch nicht mit Verzoegerung.
2. **Massiv verzoegerte oder haengenbleibende Runs**, wenn doch einer erzeugt
   wird (PR #1, PR #4) -- teils erst nach Minuten bis Stunden, teils nie
   einem Runner zugewiesen.

Die oeffentliche GitHub-Statusseite (`githubstatus.com/api/v2/summary.json`)
meldet fuer den Komponenten "Actions" zum Pruefzeitpunkt `"operational"` und
keine offenen Incidents. Das widerspricht den Beobachtungen nicht zwingend:
Die oeffentliche Statusseite bildet nur groessere, breitenwirksame Ausfaelle
ab, keine kontokonkreten oder auf einzelne Runner-Pools begrenzten
Kapazitaetsengpaesse -- und genau ein solcher, plattformseitig begrenzter
Engpass bei der Zuteilung gehosteter Runner fuer private Repositories im
kostenlosen Plan ist die naheliegendste Erklaerung fuer das beobachtete
Muster (Runs werden vom Backend teils gar nicht materialisiert, teils massiv
verzoegert in die Warteschlange gestellt).

## Entscheidung

1. **Keine Aenderung an `ci.yml`.** Trigger, Branch-Filter und Berechtigungen
   sind bereits korrekt; eine Aenderung wuerde ein Problem "loesen", das
   nachweislich nicht in der Konfiguration liegt.
2. Die Interimsregel aus [ADR 0009](0009-required-checks-nicht-konfigurierbar.md)
   ("kein Merge ohne vorher gepruefte gruene CI") wird um eine explizite
   Ausweichregel ergaenzt: **Bleibt ein CI-Lauf innerhalb von 30 Minuten nach
   PR-Erstellung ganz aus, ersetzt eine dokumentierte lokale Verifikation
   (`pytest`, `ruff check .`, `mypy --strict`, Frontend
   `lint`/`typecheck`/`build`, Secret-Check) die fehlende CI fuer diesen
   Merge.** Diese Ersetzung wird im PR bzw. an dieser Stelle transparent
   vermerkt, nicht stillschweigend vorausgesetzt.
3. Erscheint spaeter doch noch ein verspaeteter Run fuer einen bereits so
   gemergten PR, wird dessen Ergebnis nachtraeglich geprueft. Ein rotes
   Ergebnis fuehrt zu einem sofortigen Fix-Commit, kein Zurueckrudern des
   Merges.

## Begruendung

Ein Wechsel der Trigger-Syntax oder der Berechtigungen auf Verdacht waere
Kosmetik ohne belastbare Grundlage -- die Untersuchung zeigt, dass die
Konfiguration bereits denselben, korrekt funktionierenden Trigger benutzt,
der bei PR #1 und #4 nachweislich (wenn auch verzoegert) ausgeloest hat. Das
Muster spricht fuer eine Kapazitaets- oder Zustellungsschwaeche auf
GitHub-Seite, die im Free-Plan fuer private Repositories bekanntermassen
weniger priorisiert behandelt wird als bezahlte Plaene. Eine ehrliche
Dokumentation dieses Zustands ist wertvoller als ein wiederholtes,
ergebnisloses Nachjustieren der Workflow-Datei.

## Konsequenzen

- Ein Merge kann weiterhin ohne vorher gesehenes gruenes CI-Ergebnis
  stattfinden, wenn die in Punkt 2 beschriebene Ausweichregel dokumentiert
  angewendet wird. Das Risiko bleibt fuer ein Ein-Personen-Projekt vertretbar,
  ist aber real und wird nicht kleingeredet.
- Zwei Wege koennten das Problem entscheidend entschaerfen, sind aber
  Nutzerentscheidungen mit Tragweite (siehe bereits ADR 0009): GitHub Pro
  bzw. ein kostenpflichtiger Plan mit garantierter Runner-Kapazitaet, oder
  selbst gehostete Runner (self-hosted) auf eigener Infrastruktur.
- Dieses ADR ersetzt keine fruehere Entscheidung, sondern ergaenzt ADR 0009
  um die konkret erhobenen Belege und eine daraus abgeleitete Ausweichregel.
