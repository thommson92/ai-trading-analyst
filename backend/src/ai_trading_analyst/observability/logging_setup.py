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
import logging.handlers
import sys
from pathlib import Path
from typing import Any

from ai_trading_analyst.config.settings import LoggingConfig
from ai_trading_analyst.observability.correlation import current_context
from ai_trading_analyst.observability.secret_redaction import redact_registered

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
#
# ``duration_ms`` und ``error_code`` standen hier, obwohl der Formatter
# **keines von beiden** setzt. Die Folge war, dass ein
# ``extra={"duration_ms": ...}`` als ``extra_duration_ms`` herauskam -- genau
# entgegen der Zusage im Modulkopf. Die Liste beschreibt, was der Formatter
# belegt; wer sie erweitert, belegt es auch.
_RESERVED_OUTPUT_FIELDS = frozenset(
    {
        "timestamp",
        "level",
        "logger",
        "message",
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

        # Die **fertige** Zeile schwaerzen, nicht die einzelnen Felder: So
        # sind Traceback, Zusatzfelder und fremde Meldungen -- etwa die
        # Anfragezeile von ``httpx`` -- mit abgedeckt.
        return redact_registered(json.dumps(payload, ensure_ascii=False, default=str))


class ConsoleLogFormatter(logging.Formatter):
    """Kompakte, menschenlesbare Ausgabe fuer die lokale Entwicklung."""

    def format(self, record: logging.LogRecord) -> str:
        context = current_context()
        prefix_parts = [part for part in (context.correlation_id, context.stock_symbol) if part]
        prefix = f"[{' '.join(prefix_parts)}] " if prefix_parts else ""
        timestamp = dt.datetime.fromtimestamp(record.created, tz=dt.UTC).strftime("%H:%M:%S")
        line = f"{timestamp} {record.levelname:<8} {prefix}{record.name}: {record.getMessage()}"
        if record.exc_info is not None:
            # Der Traceback laeuft ueber ``__cause__`` mit. Genau dort steht
            # die ungeschwaerzte URL der ausloesenden ``httpx``-Ausnahme.
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return redact_registered(line)


def configure_logging(config: LoggingConfig | None = None) -> None:
    """Richtet das Root-Logging ein.

    Idempotent: Ein erneuter Aufruf ersetzt die bestehenden Handler, statt
    weitere hinzuzufuegen -- sonst erschiene jede Zeile doppelt.

    Ist ``logging.file`` gesetzt, kommt **zusaetzlich** zur Ausgabe auf
    ``stdout`` eine rotierende Datei dazu. Der Tageslauf laeuft unter der
    Windows-Aufgabenplanung, und deren ``stdout`` ist fluechtig: Ohne Datei
    ist nach einem Lauf nicht mehr nachvollziehbar, wo seine Zeit geblieben
    ist. Die Datei traegt **immer JSON**, unabhaengig von ``format`` -- sie
    wird ausgewertet, nicht gelesen.
    """
    settings = config if config is not None else LoggingConfig()

    formatter: logging.Formatter = (
        JsonLogFormatter() if settings.format == "json" else ConsoleLogFormatter()
    )
    handlers: list[logging.Handler] = []

    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setFormatter(formatter)
    handlers.append(stream_handler)

    if settings.file:
        handlers.append(_datei_handler(settings.file, settings))

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
        existing.close()
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(settings.level)


def _datei_handler(ziel: str, settings: LoggingConfig) -> logging.Handler:
    """Die rotierende Datei -- immer JSON, und immer geschwaerzt.

    Die Schwaerzung haengt nicht am Handler, sondern am Formatter:
    ``JsonLogFormatter.format`` ruft ``redact_registered`` auf der fertigen
    Zeile. Ein zweiter Ausgang ist damit keine zweite Stelle, an der ein
    Geheimnis entwischen koennte (ADR 0044) -- genau deshalb bekommt die
    Datei denselben Formatter und keinen eigenen.
    """
    pfad = Path(ziel)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        pfad,
        maxBytes=settings.max_bytes,
        backupCount=settings.backups,
        encoding="utf-8",
    )
    handler.setFormatter(JsonLogFormatter())
    return handler


def get_logger(name: str) -> logging.Logger:
    """Logger fuer ein Modul. Duenne Huelle, damit Aufrufer kein ``logging`` importieren."""
    return logging.getLogger(name)
