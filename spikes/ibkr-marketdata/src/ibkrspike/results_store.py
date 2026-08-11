from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .redaction import redact_mapping

_DEFAULT_RESULTS_DIR = Path(__file__).resolve().parents[2] / "results"


def save_result(
    step_id: str,
    result: dict[str, Any],
    results_dir: Path = _DEFAULT_RESULTS_DIR,
) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    path = results_dir / f"{timestamp}_{step_id}.json"
    payload = json.dumps(redact_mapping(result), indent=2, ensure_ascii=False)
    path.write_text(payload, encoding="utf-8")
    return path
