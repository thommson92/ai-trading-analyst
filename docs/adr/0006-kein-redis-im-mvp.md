# ADR 0006: Kein Redis im MVP — Koordination über PostgreSQL

- Status: Angenommen
- Datum: 2026-08-06

## Kontext

Doc 13 führt Redis als festen Docker-Compose-Service. Doc 10 §3 widerspricht:
Redis nur bei nachgewiesenem Bedarf, „eine verteilte Queue-Infrastruktur darf
nicht ohne konkreten technischen Nutzen eingeführt werden".

Die tatsächliche Last: ein Lauf pro Handelstag, ein paar hundert Aktien im
Screening, zwei bis drei Kandidaten in der Tiefenanalyse.

Ohne Message Broker muss aber explizit festgelegt sein, wie Scheduler, Backend
und Worker Aufgaben austauschen und sperren — eine unklare Worker-Architektur
ist schlimmer als eine zusätzliche Abhängigkeit.

## Entscheidung

**Kein Redis im MVP.** Die Koordination läuft über PostgreSQL, in zwei Stufen:

**Stufe 1 (Walking Skeleton, Sprint 1):** Ein einzelner Backend-Prozess
übernimmt Scheduler und Verarbeitung. Kein Worker-Container, keine
Nebenläufigkeit.

**Stufe 2 (ab Sprint 2, mit eigenem Worker-Prozess):**

- Persistente Tabelle `analysis_job`, an den `AnalysisRun` gebunden, mit
  Status, Versuchszähler, `locked_by`, `locked_at`, `heartbeat_at`.
- **`SELECT … FOR UPDATE SKIP LOCKED`** regelt die atomare Übernahme
  **einzelner Jobs** — und nur das.
- **PostgreSQL Advisory Lock** verhindert, dass **zwei reguläre Tagesläufe für
  denselben Handelstag** parallel starten — und nur das. Der Lock wird auf den
  Handelstag-Schlüssel genommen, nicht auf einzelne Jobs, zusätzlich
  abgesichert durch eine Unique Constraint auf dem Laufschlüssel.
- Heartbeat auf laufenden Jobs; ohne frischen Heartbeat gilt ein Job nach
  konfigurierbarem Timeout als verwaist.
- Recovery beim Start: verwaiste Jobs werden erkannt, protokolliert und
  kontrolliert wieder aufgenommen oder als `FAILED` abgeschlossen — nie still
  übersprungen.
- Migrationen laufen in einem dedizierten Schritt, nicht parallel aus Backend
  und Worker.

Die beiden Sperrmechanismen haben getrennte, nicht überlappende
Zuständigkeiten. Das ist ausdrücklich Teil der Entscheidung: Ein Advisory Lock,
der auch einzelne Jobs schützt, würde die Verantwortlichkeiten vermischen und
bei Erweiterungen schwer nachvollziehbar.

## Begründung

Redis brächte hier einen zusätzlichen Dienst, ein zusätzliches Backup-Ziel und
einen zusätzlichen Ausfallpunkt — für eine Last, die eine
PostgreSQL-Job-Tabelle problemlos trägt. `SKIP LOCKED` ist seit PostgreSQL 9.5
verfügbar und für genau diesen Zweck gedacht.

Der Recovery-Pfad deckt zugleich die Anforderung aus Doc 10 §14 ab, dass ein
unterbrochener Lauf nach einem Serverneustart als unterbrochen erkannt und
kontrolliert behandelt wird.

## Konsequenzen

- Docker Compose enthält im MVP `frontend`, `backend`, `worker`, `postgres`
  und `reverse-proxy` — kein `redis`.
- Doc 13 wird beim Deployment-Sprint entsprechend korrigiert.
- Redis wird eingeführt, sobald ein konkreter Engpass nachgewiesen ist; dann
  über ein neues ADR, das dieses ablöst.
- Die Job-Verarbeitung ist an PostgreSQL gebunden. Bei einem Datenbankwechsel
  müsste dieser Mechanismus ersetzt werden — bei einem persönlichen System mit
  festgelegtem Stack ein hinnehmbarer Preis.


---

### Nachtrag 2026-08-23 (Maßnahme M12 aus dem Repository-Audit)

Die Entscheidung selbst — kein Redis im MVP, Koordination über PostgreSQL —
gilt unverändert. Zwei ihrer Annahmen sind es nicht mehr:

- **„Stufe 2 (ab Sprint 2, mit eigenem Worker-Prozess)" ist nicht eingetreten
  und wird es nicht.** An ihre Stelle ist der Trading-Day-Dispatcher getreten:
  ein idempotenter Einzelstart, ausgelöst von der Windows-Aufgabenplanung,
  statt eines dauerhaft laufenden Worker-Prozesses
  ([ADR 0019](0019-trading-day-dispatcher.md)). Die Begründung gegen Redis
  trägt dadurch eher besser als schlechter — es gibt keine Queue mehr,
  gegen die eine Warteschlange nötig wäre.
- **Der `worker`-Service aus der Konsequenzliste existiert nicht**, ebenso
  wenig das übrige Docker-Compose-Zielbild. Betrieben wird nativ auf Windows
  (Doc 14). Ob das die beschlossene Architektur wird, ist offen (E6 aus dem
  Audit).

Der Entscheidungstext bleibt unverändert; dieser Nachtrag hält nur fest,
was aus ihm überholt ist.
