"""Strukturiertes, maschinenlesbares Logging (Doc 10, Paragraph 12).

Pflichtfelder jeder Logzeile: Zeitstempel, Level, Modul und Ereignis. Die
kontextabhaengigen Felder Correlation ID, Analysis Run ID und Stock Symbol
kommen aus ``correlation.py`` und werden automatisch ergaenzt.

Zusaetzliche Felder werden ueber ``extra={"event": ..., "duration_ms": ...}``
uebergeben und landen als eigene JSON-Schluessel -- nicht im Fliesstext, damit
sie auswertbar bleiben.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from typing import Any

from ai_trading_analyst.config.settings import LoggingConfig
from ai_trading_analyst.observability.correlation import current_context

# Attribute, die jeder LogRecord von Haus aus mitbringt. Alles, was darueber
# hinausgeht, stammt aus einem `extra=` und gehoert in die Ausgabe.
_STANDARD_RECORD_ATTRIBUTES = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)

# Feldnamen, die der Formatter selbst belegt. Ein `extra` mit diesem Namen
# wuerde die Zuordnung eines Logeintrags zerstoeren und wird deshalb umbenannt.
_RESERVED_OUTPUT_FIELDS = frozenset(
    {
        "timestamp",
        "level",
        "logger",
        "message",
        "error_code",
        "duration_ms",
        "correlation_id",
        "analysis_run_id",
        "stock_symbol",
        "module",
        "exception",
        "source",
    }
)


class JsonLogFormatter(logging.Formatter):
    """Gibt jeden Logeintrag als einzeilige JSON-Struktur aus."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": dt.datetime.fromtimestamp(record.created, tz=dt.UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Der Kontext ueberschreibt nichts, was bereits gesetzt ist: Das
        # Logger-Modul ist praeziser als ein grob gesetztes Kontextmodul.
        for key, value in current_context().as_log_fields().items():
            payload.setdefault(key, value)
        payload.setdefault("module", record.name)

        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_ATTRIBUTES:
                continue
            output_key = f"extra_{key}" if key in _RESERVED_OUTPUT_FIELDS else key
            payload[output_key] = value

        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info is not None:
            payload["stack"] = self.formatStack(record.stack_info)

        payload["source"] = f"{record.pathname}:{record.lineno}"

        return json.dumps(payload, ensure_ascii=False, default=str)


class ConsoleLogFormatter(logging.Formatter):
    """Kompakte, menschenlesbare Ausgabe fuer die lokale Entwicklung."""

    def format(self, record: logging.LogRecord) -> str:
        context = current_context()
        prefix_parts = [part for part in (context.correlation_id, context.stock_symbol) if part]
        prefix = f"[{' '.join(prefix_parts)}] " if prefix_parts else ""
        timestamp = dt.datetime.fromtimestamp(record.created, tz=dt.UTC).strftime("%H:%M:%S")
        line = f"{timestamp} {record.levelname:<8} {prefix}{record.name}: {record.getMessage()}"
        if record.exc_info is not None:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return line


def configure_logging(config: LoggingConfig | None = None) -> None:
    """Richtet das Root-Logging ein.

    Idempotent: Ein erneuter Aufruf ersetzt den bestehenden Handler, statt
    einen zweiten hinzuzufuegen -- sonst erschiene jede Zeile doppelt.
    """
    settings = config if config is not None else LoggingConfig()

    formatter: logging.Formatter = (
        JsonLogFormatter() if settings.format == "json" else ConsoleLogFormatter()
    )
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
        existing.close()
    root.addHandler(handler)
    root.setLevel(settings.level)


def get_logger(name: str) -> logging.Logger:
    """Logger fuer ein Modul. Duenne Huelle, damit Aufrufer kein ``logging`` importieren."""
    return logging.getLogger(name)
