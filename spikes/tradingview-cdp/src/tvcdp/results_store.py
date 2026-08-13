"""Persistiert Rohergebnisse jedes Testlaufs als Dateien (Nutzervorgabe:
"Rohresultate in Dateien speichern koennen").

Jeder Lauf bekommt ein eigenes, zeitgestempeltes Verzeichnis unter
``results/``, damit mehrere Laeufe (z. B. mehrere Versuche auf dem
Windows-Server) nebeneinander erhalten bleiben statt sich gegenseitig zu
ueberschreiben.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from .redaction import redact
from .steps.base import StepResult


def new_run_directory(results_dir: Path) -> Path:
    """Erzeugt ein neues, garantiert eindeutiges Lauf-Verzeichnis.

    Sekundenaufloesung allein reicht nicht: zwei rasch aufeinanderfolgende
    Einzelschritt-Aufrufe (z. B. in einem Shell-Skript ohne Pause) landen
    sonst in derselben Sekunde und ``mkdir(exist_ok=False)`` bricht mit
    ``FileExistsError`` ab -- beobachtet beim Smoke-Test gegen eine echte
    CDP-Instanz. Mikrosekundenaufloesung macht eine Kollision praktisch
    ausgeschlossen; ein Fallback-Zaehler faengt den verbleibenden,
    theoretischen Rest ab, statt den Testlauf abzubrechen.
    """
    base_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    for suffix in ("", *(f"-{n}" for n in range(1, 1000))):
        run_dir = results_dir / f"{base_id}{suffix}"
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            return run_dir
        except FileExistsError:
            continue
    raise RuntimeError("Konnte kein eindeutiges Lauf-Verzeichnis erzeugen.")


def _result_to_json_dict(result: StepResult) -> dict[str, object]:
    raw = asdict(result)
    raw["started_at"] = result.started_at.isoformat()
    raw["finished_at"] = result.finished_at.isoformat()
    raw["duration_seconds"] = result.duration_seconds
    return cast(dict[str, object], redact(raw))


def write_step_result(run_dir: Path, result: StepResult) -> Path:
    path = run_dir / f"{result.step_id}.json"
    path.write_text(
        json.dumps(_result_to_json_dict(result), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return path


def write_summary(run_dir: Path, results: list[StepResult]) -> Path:
    path = run_dir / "summary.json"
    payload = {
        "run_id": run_dir.name,
        "step_count": len(results),
        "steps": [_result_to_json_dict(result) for result in results],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
