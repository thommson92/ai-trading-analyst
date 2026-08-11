from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


# ib_async.IB synchronisiert beim Verbinden automatisch Account-Positionen
# und Portfoliowerte und protokolliert sie ungefragt auf INFO-Level ueber
# den Logger "ib_async.wrapper" (live gegen ein echtes Konto reproduziert,
# siehe REPORT.md, "Sicherheitsfund"). Diese Zeilen enthalten unmaskierte
# Account-Kennungen, konkrete Positionen und Geldbetraege -- unsere eigene
# Redaction-Schicht (redaction.py) greift nur bei selbst gebauten
# Ergebnisdaten, nicht bei Log-Zeilen fremder Bibliotheken. Deshalb wird
# dieser Logger hier gezielt auf WARNING angehoben, nicht nur global gefiltert.
_SENSITIVE_THIRD_PARTY_LOGGERS = ("ib_async.wrapper",)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    for logger_name in _SENSITIVE_THIRD_PARTY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
