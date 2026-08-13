"""Strukturiertes Logging fuer den Spike -- einzeilige JSON-Ausgabe auf
stdout, damit ein Testlauf auf dem Windows-Server sich 1:1 in eine Datei
umleiten und spaeter maschinell auswerten laesst (Nutzervorgabe:
"aussagekraeftige strukturierte Logs erzeugen").

Bewusst keine Abhaengigkeit vom Backend-Logging (``observability/``) --
dieser Spike bleibt vollstaendig eigenstaendig.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from .redaction import redact

_LOGGER_NAME = "tvcdp"


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(redact(payload), ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    logger.handlers.clear()
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)


def log_step_result(logger: logging.Logger, step_id: str, status: str, **fields: Any) -> None:
    logger.info(
        f"Schritt '{step_id}' abgeschlossen: {status}",
        extra={"extra_fields": {"step_id": step_id, "status": status, **fields}},
    )
