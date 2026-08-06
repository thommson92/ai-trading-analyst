# ADR 0003: Monorepo mit vier Schichten und erzwungenen Grenzen

- Status: Angenommen
- Datum: 2026-08-06

## Kontext

Doc 10 §9 fordert vier Schichten mit einer harten Regel: Der Domain Layer darf
nicht von FastAPI, SQLAlchemy, TradingView oder einem konkreten KI-Anbieter
abhängen. Diese Regel trägt das gesamte Vorhaben — sie ist der Grund, warum
ein gescheiterter TradingView-Spike nur einen Adapter kostet und nicht die
Anwendung.

Eine Architekturregel, die nur in einem Dokument steht, wird im Alltag
verletzt. Meist nicht absichtlich, sondern weil ein Import bequem ist und
niemand beim Review darauf achtet.

## Entscheidung

**Monorepo** mit `backend/`, `frontend/`, `config/`, `docker/`, `docs/`.

**Vier Schichten** unter `backend/src/ai_trading_analyst/`:

| Schicht | Darf importieren |
|---|---|
| `domain` | nichts aus den anderen Schichten |
| `application` | `domain` |
| `infrastructure` | `domain` |
| `presentation` | `domain`, `application` |

Querschnittspakete (`config`, `observability`) darf jede Schicht nutzen.

**Die Regel wird automatisiert durchgesetzt.**
`backend/tests/architecture/test_layer_boundaries.py` prüft den Import-Graph
statisch über den AST und schlägt fehl bei

- jedem Import über eine unerlaubte Schichtgrenze,
- jedem Import von `fastapi`, `starlette`, `sqlalchemy`, `alembic`, `psycopg`,
  `httpx`, `requests`, `anthropic`, `openai`, `redis` oder `yaml` im Domain
  Layer.

## Begründung

**Monorepo statt getrennter Repositories:** Ein Ein-Personen-Projekt, in dem
Backend und Frontend gemeinsam versioniert und deployt werden. Getrennte
Repositories brächten Versionsabgleich ohne Gegenwert.

**Statische AST-Prüfung statt Laufzeitprüfung:** Ein verbotener Import in
einem selten erreichten Zweig würde einer Laufzeitprüfung entgehen. Der AST
sieht ihn immer.

**Eigener Test statt `import-linter`:** Die Prüfung sind rund 60 Zeilen und
braucht keine zusätzliche Abhängigkeit. Sie enthält zwei Selbsttests, die
sicherstellen, dass die Erkennung überhaupt anschlägt — ein leerer Import-Graph
oder eine umbenannte Schicht würde den Wächter sonst still wirkungslos machen.

**`yaml` steht mit auf der Verbotsliste:** Der Domain Layer soll seine Regeln
aus übergebenen Objekten beziehen, nicht selbst Dateien lesen.

## Konsequenzen

- Ein Verstoß bricht die CI, nicht erst das Review.
- Neue Infrastrukturbibliotheken müssen der Verbotsliste hinzugefügt werden;
  die Liste ist bewusst explizit statt heuristisch.
- Die Schichtpakete existieren ab Sprint 0 leer. Das ist beabsichtigt: Die
  Struktur soll stehen, bevor der erste fachliche Code entsteht.
