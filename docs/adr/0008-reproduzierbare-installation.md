# ADR 0008: Reproduzierbare Installation über Lock-Dateien

- Status: Angenommen
- Datum: 2026-08-06

## Kontext

Vor dem Merge von Sprint 0 Teil A wurde geprüft, ob die Abhängigkeitsinstallation
reproduzierbar ist. Ergebnis:

- **Frontend:** `package-lock.json` war bereits committet, die CI nutzte bereits
  `npm ci`. Das ist reproduzierbar — `npm ci` installiert exakt die dort
  festgeschriebenen Versionen und bricht ab, wenn `package.json` und Lock-Datei
  auseinanderlaufen.
- **Backend:** Die CI installierte über `pip install -e ".[dev]"`, also direkt
  aus den Versionsbereichen in `pyproject.toml` (z. B. `pydantic>=2.7,<3`).
  Ohne Lock-Datei kann derselbe Befehl an zwei Tagen unterschiedliche
  transitive Versionen auflösen — ein Problem, das sich typischerweise erst
  bemerkbar macht, wenn ein CI-Lauf grün war und ein späterer ohne
  Codeänderung rot wird.

[ADR 0004](0004-python-toolchain.md) hatte diesen Punkt offen gelassen: „venv
statt uv/Poetry" beantwortet nur die Frage nach dem Installationswerkzeug,
nicht nach der Versionsfixierung.

## Entscheidung

**Zwei Lock-Dateien, erzeugt mit `pip-compile` (aus `pip-tools`), mit
`--generate-hashes`:**

- `backend/requirements.lock.txt` — Laufzeitabhängigkeiten.
- `backend/requirements-dev.lock.txt` — Laufzeit- plus Testabhängigkeiten
  (`--extra=dev`).

Beide sind eingecheckt. Installation ausschließlich darüber:

```bash
pip install --require-hashes -r requirements-dev.lock.txt
pip install --no-deps -e .
```

`--require-hashes` verweigert die Installation, wenn ein Paket nicht mit dem
festgeschriebenen Hash übereinstimmt — Version *und* Artefakt sind damit
festgelegt, nicht nur die Versionsnummer. `--no-deps` beim lokalen Paket
verhindert, dass `pip` beim `-e .`-Schritt erneut eine Abhängigkeitsauflösung
anstößt, die die Lock-Datei umgehen könnte.

`pip-tools` selbst ist keine Laufzeit- oder Testabhängigkeit, sondern nur zum
Regenerieren der Lock-Dateien nötig — als eigenes Extra `lock` in
`pyproject.toml` geführt, nicht in `dev`.

## Begründung: warum nicht direkt `pip-compile` in der CI

`pip-compile` 7.6.0 (aktuell) ist mit aktuellem `pip` (26.x) nicht kompatibel —
es importiert eine interne pip-Funktion (`stdlib_pkgs`), die entfernt wurde,
und bricht mit `ImportError` ab. Das wurde beim Erzeugen der Lock-Dateien für
dieses ADR unmittelbar reproduziert.

Die Entscheidung berücksichtigt das: **`pip-compile` läuft nur lokal bei der
Wartung der Lock-Dateien** (mit einem dafür temporär auf `pip==24.3.1`
herabgestuften `pip` in der virtuellen Umgebung — dokumentiert im README).
**Die CI installiert nur noch aus den bereits erzeugten Lock-Dateien**, ohne
`pip-compile` aufzurufen. Dieser Schritt braucht keine Versionsauflösung,
sondern installiert exakt festgeschriebene Pakete — das funktioniert mit jeder
aktuellen `pip`-Version unabhängig von der pip-tools-Kompatibilität.

Damit ist die CI robuster als das Werkzeug, mit dem die Lock-Dateien entstehen.

## Verifikation

Eine Installation aus den Lock-Dateien wurde in einer frisch angelegten
virtuellen Umgebung (ohne jeden vorherigen Zustand) durchgeführt:

```bash
python3.12 -m venv /tmp/clean-venv-test
/tmp/clean-venv-test/bin/pip install --require-hashes -r requirements-dev.lock.txt
/tmp/clean-venv-test/bin/pip install --no-deps -e .
```

Anschließend liefen `pytest` (66 Tests), `ruff check .` und
`mypy --strict src tests` unverändert grün.

## Konsequenzen

- Jede Änderung an `pyproject.toml`-Abhängigkeiten erfordert eine Regenerierung
  beider Lock-Dateien — sonst installiert die CI weiterhin die alten Versionen.
- Sicherheitsupdates transitiver Abhängigkeiten kommen nicht automatisch an;
  die Lock-Dateien müssen bei Bedarf bewusst neu erzeugt werden
  (`pip-compile --upgrade`).
- Die CI installiert schneller und deterministischer, da keine
  Abhängigkeitsauflösung mehr zur Laufzeit stattfindet.
- `npm ci` (Frontend) folgt demselben Prinzip und war bereits korrekt
  konfiguriert — hier gab es nichts zu ändern.
