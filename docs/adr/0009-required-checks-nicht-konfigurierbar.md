# ADR 0009: Required Status Checks derzeit nicht konfigurierbar

- Status: Angenommen (mit offenem Punkt)
- Datum: 2026-08-06

## Kontext

Vor dem Merge von Sprint 0 Teil A sollten die drei grünen CI-Jobs
(`Backend (lint, typecheck, test)`, `Frontend (lint, typecheck, build)`,
`Keine Geheimnisse im Repository`) als erforderliche Checks für die
geschützten Branches `main` und `dev` konfiguriert werden — damit ein PR ohne
grüne CI gar nicht mergbar ist, statt sich auf manuelle Disziplin zu
verlassen.

Sowohl die klassische Branch-Protection-API als auch die neuere
Rulesets-API antworten für dieses Repository mit:

```
403 Upgrade to GitHub Pro or make this repository public to enable this feature.
```

Das Repository ist privat (bewusste Entscheidung — persönliche Handelsstrategie
und Analyseergebnisse), und der Account läuft auf dem kostenlosen Plan. Beide
Funktionen sind auf privaten Repositories im Free-Plan nicht verfügbar.

## Entscheidung

**Keine automatisierte Merge-Sperre in Sprint 0.** Stattdessen:

1. Dieses ADR hält die Einschränkung fest, statt sie stillschweigend als
   erledigt zu behandeln.
2. Die exakten Job-Namen sind hier dokumentiert, damit die Konfiguration ohne
   erneute Recherche nachgeholt werden kann, sobald eine der beiden
   Voraussetzungen erfüllt ist:

   ```bash
   gh api repos/thommson92/TradingViewAnalyzer/branches/main/protection \
     -X PUT -f required_status_checks[strict]=true \
     -f 'required_status_checks[contexts][]=Backend (lint, typecheck, test)' \
     -f 'required_status_checks[contexts][]=Frontend (lint, typecheck, build)' \
     -f 'required_status_checks[contexts][]=Keine Geheimnisse im Repository' \
     -f enforce_admins=true \
     -f required_pull_request_reviews=null \
     -f restrictions=null
   ```

   Derselbe Befehl für `dev` (Branch-Segment anpassen).

3. **Interimsregel, solange die technische Sperre fehlt:** Kein Merge nach
   `main` oder `dev`, ohne die CI-Läufe des PRs geprüft zu haben
   (`gh pr checks <nummer>`). Diese Regel ist bereits Teil der bestehenden
   Arbeitsweise (ADR 0002) und wird hier nur um den expliziten Hinweis
   ergänzt, dass sie aktuell die einzige Absicherung ist.

## Begründung

Eine unwahre Erfolgsmeldung („Required Checks sind konfiguriert") wäre
schlimmer als die ehrliche Feststellung einer Plan-Einschränkung. Das
Repository öffentlich zu machen, um die Funktion freizuschalten, ist eine
Entscheidung mit Tragweite — sie exponiert Code und potenziell Rückschlüsse
auf die Handelsstrategie — und wird hier bewusst nicht eigenmächtig getroffen.

## Konsequenzen

- Ein Merge ohne grüne CI ist technisch weiterhin möglich. Solange dieses
  Projekt ein Ein-Personen-Projekt bleibt, ist das Risiko gering, aber real.
- Zwei Wege, den offenen Punkt zu schließen: GitHub Pro (persönliches
  Abonnement, das Repository bleibt privat) oder das Repository öffentlich
  stellen. Beides ist eine Nutzerentscheidung.
- Sobald entschieden, wird dieses ADR durch eines ersetzt, das die tatsächlich
  konfigurierte Regel dokumentiert.
