# ADR 0002: Branching-Modell main/dev mit Feature-Branches

- Status: Angenommen
- Datum: 2026-08-06

## Kontext

Das Repository hatte zu Projektbeginn keinen einzigen Commit und keinen
`dev`-Branch. Der Standardbranch hieß `master`.

## Entscheidung

- `main` ist der Standardbranch (umbenannt von `master`).
- `dev` ist der Integrationsbranch.
- Jedes Feature erhält einen eigenen Branch nach dem Schema
  `feature/<kurzbeschreibung>`, abgezweigt von `dev`.
- Abschluss eines Features immer über einen Pull Request nach `dev`, erstellt
  mit `gh pr create`.
- Es wird nie direkt auf `main` oder `dev` gearbeitet.
- Ausschließlich `git`- und `gh`-CLI; keine Git-GUI.
- Force-Push nur nach ausdrücklicher Zustimmung.

## Begründung

Entspricht der etablierten Arbeitsweise des Entwicklers. Der zusätzliche
`dev`-Branch kostet bei einem Ein-Personen-Projekt wenig und hält `main` auf
einem Stand, der jederzeit deploybar ist — bei einem System, das
unbeaufsichtigt auf einem Server läuft, ist das mehr wert als die eingesparte
Merge-Operation.

## Konsequenzen

- Vor jedem PR läuft die Test-Suite lokal und eine unabhängige Code-Review.
- Der Feature-Branch wird regelmäßig zu `origin` gepusht (Backup-Charakter).
- `main` erhält nur Änderungen über `dev`.
