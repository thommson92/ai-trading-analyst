# ADR 0053: Die Web-API ist lesend — kein Analyselauf über HTTP

- Status: Angenommen
- Datum: 2026-09-01

## Kontext

Sprint 6 baut die API aus, damit das Dashboard gespeicherte Läufe und
Berichte anzeigen kann. Vorhanden sind heute drei Endpunkte für Läufe und
zwei Sonden. Einer davon ist `POST /api/v1/analysis-runs`: Er startet einen
vollständigen Analyselauf mit den Anbietern **aus der Konfiguration**.

Das war folgenlos, solange die API nur zum Entwickeln lief. Mit
[ADR 0052](0052-dashboard-als-statischer-export.md) läuft sie dauerhaft auf
dem Server — und dort steht `config/default.yaml` bewusst auf `fixture`.
Scharf geschaltet wird ausschließlich über Argumente in der Aufgabenplanung,
damit ein `git pull` keinen lokalen Diff vorfindet
([ADR 0036](0036-nativer-windows-betrieb.md), Punkt 4). Ein Aufruf des
Endpunkts auf dem Server erzeugte deshalb einen **Lauf aus erfundenen Werten
in der Produktivdatenbank** — gespeichert wie jeder andere, mit Scores,
Empfehlung und Bericht.

Dazu kommt die Zugriffsseite: Doc 10 §6.14 verlangt für manuelle Läufe eine
eigene Berechtigung. Eine Authentifizierung gibt es nach
[ADR 0049](0049-dashboard-mvp-nur-lan.md) bewusst nicht.

## Entscheidung

1. **Die Web-API ist lesend.** `POST /api/v1/analysis-runs` entfällt
   ersatzlos. Läufe entstehen über die Aufgabenplanung und `cli dispatch`,
   Einzelproben über die übrigen CLI-Befehle.
2. **Der API-Bootstrap verdrahtet keine Anbieter mehr.** Ohne den
   Analyse-Use-Case braucht die Anwendung nur die UnitOfWork-Fabrik und die
   Datenbankprobe: kein Anbieterbau, keine belegte TWS-Client-ID, kein
   Shutdown-Haken für die Kursquelle.
3. **Die Detailsicht bekommt das gespeicherte Dokument unverändert.** Es
   wird durchgereicht, nicht neu erzeugt und nicht übersetzt — auch nicht in
   englische Schlüssel. Es führt alle achtzehn Punkte mit `verfuegbar` und
   `vorbehalte`; genau das zeigt die Oberfläche an.
4. **Listen sind paginiert** (`limit`/`offset`, gedeckelt, neueste zuerst),
   wie Doc 10 §6.14 es verlangt.
5. **Das MVP baut drei der zehn Ansichten** aus Doc 10 §6.15 —
   Tagesübersicht, Berichtsdetail, Historie je Aktie. Die übrigen bleiben
   Zielbild.

## Begründung

**Ein Knopf, der erfundene Läufe speichert, ist schlimmer als kein Knopf.**
Der Fixture-Lauf sieht im Bericht aus wie ein echter; wer ihn eine Woche
später in der Historie findet, hat keine Handhabe, ihn zu erkennen. Das ist
derselbe Fehler, den [ADR 0051](0051-research-im-dauerbetrieb-abgeschaltet.md)
beim Research-Anbieter vermieden hat — nur diesmal für einen ganzen Lauf.

**Der Weg zum „richtigen" Knopf wäre teurer, als er aussieht.** Damit der
Endpunkt scharfe Anbieter benutzt, müssten sie in die Serverkonfiguration
wandern. Genau das vermeidet ADR 0036 Punkt 4 mit Absicht: Die Trennung
zwischen ausgelieferter Konfiguration und scharfem Lauf ist der Grund, warum
auf dem Server kein lokaler Diff liegt. Ein Auslöseknopf ohne
Authentifizierung wäre zudem für jeden im Netz erreichbar und könnte, weil
ein Lauf die TWS belegt, den Tageslauf stören.

**Die Nutzlast unverändert durchzureichen, ist keine Bequemlichkeit.** Der
Bericht ist die verbindliche, unveränderlich gespeicherte Fassung
([ADR 0039](0039-report-generator.md)); ihn beim Lesen aus heutigem Code neu
zu erzeugen hieße, einen abgeschlossenen Bericht nachträglich durch neue
Regeln zu schicken. Der Repository-Port sagt das bereits so; die API hält
sich daran.

**Ohne Schreibpfad ist die fehlende Authentifizierung vertretbar.** Der
Schaden eines unbefugten Zugriffs aus dem eigenen Netz beschränkt sich auf
Lesen — das war die stille Annahme hinter ADR 0049, und sie gilt nur, solange
die API nichts anstoßen kann.

## Konsequenzen

- `docs/11 - API-Design.md` wird neu geschrieben; der dort geführte
  `POST /api/run-analysis` („Nur Administrator") entfällt mit.
- **Doc 10 §6.14 führt `POST /analysis-runs` und `…/retry` weiter.** Sie
  bleiben Zielbild; dieses ADR entscheidet für das MVP dagegen
  ([ADR 0001](0001-dokumentenhierarchie.md): Entschieden wird in ADRs).
- Der Wunsch nach einem Auslöseknopf kommt wahrscheinlich wieder — dann
  gehört er zur Neubewertung von ADR 0049, zusammen mit Authentifizierung
  und Exposition, nicht davor.
- `ATA_SESSION_SECRET` bleibt reserviert und weiterhin ohne Wirkung.
- Der bisherige API-Test für den Startpfad entfällt; dafür kommen Tests für
  Paginierungsgrenzen, unbekannte IDs und unbekannte Symbole.
