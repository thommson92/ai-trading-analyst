# ADR 0004: Python-Toolchain — pyproject, venv, ruff, mypy strict

- Status: Angenommen
- Datum: 2026-08-06

## Kontext

Der Entwicklungsplan nannte „uv oder Poetry" als Paketmanager. Auf dem
Entwicklungsrechner ist `uv` nicht installiert; verfügbar sind Python 3.12 und
3.14.

## Entscheidung

- **Python 3.12** als Zielversion, eingegrenzt auf `>=3.12,<3.14`.
- **`pyproject.toml` (PEP 621) mit `venv` und `pip`** — kein zusätzlicher
  Paketmanager.
- **ruff** für Linting und Importsortierung.
- **mypy im `strict`-Modus**, zusätzlich `warn_unreachable` und
  `disallow_any_unimported`.
- **pytest** mit `--strict-markers`.

## Begründung

**Python 3.12 statt 3.14:** Das Ökosystem um SQLAlchemy, psycopg und die
Datenanbieter-SDKs hinkt neuen Python-Versionen regelmäßig hinterher. Bei einem
System, das unbeaufsichtigt laufen soll, ist eine ausgereifte Laufzeit mehr wert
als aktuelle Sprachfeatures. Die Obergrenze `<3.14` ist bewusst gesetzt, damit
ein Versionssprung eine Entscheidung bleibt und nicht nebenbei passiert.

**venv/pip statt uv:** Vermeidet eine Systeminstallation und funktioniert überall
unverändert. `uv` liest dasselbe `pyproject.toml` und kann jederzeit als reiner
Beschleuniger daraufgesetzt werden — die Entscheidung ist nicht bindend.

**mypy strict von Beginn an:** Nachträglich Typen in eine gewachsene Codebasis
einzuziehen ist deutlich teurer, als sie von Anfang an zu verlangen. Doc 12
fordert Python-Type-Hints ohnehin verbindlich.

**Regelauswahl bei ruff:** Neben den üblichen Regeln ist `DTZ`
(flake8-datetimez) aktiviert. Das Projekt rechnet durchgehend mit
Börsenzeitzonen; ein naiver Zeitstempel ist hier keine Stilfrage, sondern ein
Fehler, der zu einem Lauf am falschen Tag führen kann.

## Konsequenzen

- Einrichtung: `python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"`.
- Die CI nutzt dieselben Befehle wie die lokale Entwicklung.
- Versionen sind mit Ober- und Untergrenze angegeben, damit ein Major-Sprung
  einer Abhängigkeit nicht unbemerkt in einen Lauf gerät.
