# Architecture Decision Records

Jede Architekturentscheidung wird hier als eigenes Dokument festgehalten
(Doc 10, Paragraph 19).

## Format

Dateiname: `NNNN-kurzbeschreibung.md`, fortlaufend nummeriert.

Aufbau:

```markdown
# ADR NNNN: Titel

- Status: Vorgeschlagen | Angenommen | Abgeloest durch ADR-NNNN
- Datum: YYYY-MM-DD

## Kontext
Welches Problem steht an, welche Rahmenbedingungen gelten.

## Entscheidung
Was wird getan.

## Begruendung
Warum diese Option und nicht die Alternativen.

## Konsequenzen
Was folgt daraus, auch das Unangenehme.
```

Ein ADR wird nicht rueckwirkend geaendert. Aendert sich die Entscheidung,
entsteht ein neues ADR, das das alte ausdruecklich abloest.

## Uebersicht

| ADR | Titel | Status |
|---|---|---|
| [0001](0001-dokumentenhierarchie.md) | Doc 10 ist bei Widersprüchen maßgeblich | Angenommen |
| [0002](0002-branching-modell.md) | Branching-Modell main/dev mit Feature-Branches | Angenommen |
| [0003](0003-monorepo-und-schichtung.md) | Monorepo mit vier Schichten und erzwungenen Grenzen | Angenommen |
| [0004](0004-python-toolchain.md) | Python-Toolchain: pyproject, venv, ruff, mypy strict | Angenommen |
| [0005](0005-konfiguration-und-secrets.md) | Konfiguration in YAML, Geheimnisse aus der Umgebung | Angenommen |
| [0006](0006-kein-redis-im-mvp.md) | Kein Redis im MVP, Koordination über PostgreSQL | Angenommen |
| [0007](0007-gate-g1-indikatorparameter.md) | Indikator-Parameter bleiben bis zur Freigabe leer | Abgelöst durch ADR 0010 |
| [0008](0008-reproduzierbare-installation.md) | Reproduzierbare Installation über Lock-Dateien | Angenommen |
| [0009](0009-required-checks-nicht-konfigurierbar.md) | Required Status Checks derzeit nicht konfigurierbar (Plan-Limit) | Angenommen (offener Punkt) |
| [0010](0010-gate-g1-freigegeben.md) | Gate G1 fachlich freigegeben -- Indikator- und Signalparameter | Angenommen |

## Offene Entscheidungen

Diese Punkte sind bewusst noch nicht entschieden und erhalten je ein eigenes
ADR, sobald die nötigen Informationen vorliegen:

- Anbindung an TradingView (nach dem Spike, Gate G2/G3)
- Anbieter für historische Intraday-Kurse (F9)
- Anbieter für Earnings-Termine (F9)
- Anbieter für Optionsketten mit Greeks (F9)
- Anbieter für Analystenratings und Kursziele (F9)
- Benachrichtigungskanal (F10)
- KI-Anbieter und Modellprofile (F11)
- Externer Zugriff auf das Dashboard (F12)
