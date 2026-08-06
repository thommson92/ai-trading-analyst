"""Correlation ID und Laufkontext fuer strukturierte Logs (Doc 10, Paragraph 12).

Jeder Logeintrag soll sich einem Analyse-Lauf und -- wo sinnvoll -- einer
einzelnen Aktie zuordnen lassen. Der Kontext wird ueber ``contextvars``
gefuehrt, damit er auch ueber ``await``-Grenzen hinweg erhalten bleibt und
nicht durch jede Funktionssignatur gereicht werden muss.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LogContext:
    """Die Pflichtfelder aus Doc 10, Paragraph 12, soweit sie kontextabhaengig sind."""

    correlation_id: str | None = None
    analysis_run_id: str | None = None
    stock_symbol: str | None = None
    module: str | None = None

    def as_log_fields(self) -> dict[str, str]:
        """Nur gesetzte Felder -- leere Werte blaehen die Logzeile unnoetig auf."""
        fields = {
            "correlation_id": self.correlation_id,
            "analysis_run_id": self.analysis_run_id,
            "stock_symbol": self.stock_symbol,
            "module": self.module,
        }
        return {key: value for key, value in fields.items() if value is not None}


_EMPTY = LogContext()
_context: ContextVar[LogContext] = ContextVar("ata_log_context", default=_EMPTY)


def current_context() -> LogContext:
    """Der aktuell gueltige Logkontext."""
    return _context.get()


def new_correlation_id() -> str:
    """Eine neue, gut lesbare Correlation ID."""
    return uuid.uuid4().hex[:16]


@contextmanager
def log_context(
    *,
    correlation_id: str | None = None,
    analysis_run_id: str | None = None,
    stock_symbol: str | None = None,
    module: str | None = None,
) -> Iterator[LogContext]:
    """Erweitert den Logkontext fuer die Dauer des Blocks.

    Nur uebergebene Felder werden gesetzt; alles andere bleibt aus dem
    umgebenden Kontext erhalten. Verschachtelte Bloecke sind dadurch additiv:
    Der Orchestrator setzt die Lauf-ID, ein Modul ergaenzt Symbol und Modulname.

    Ohne ``correlation_id`` und ohne bereits gesetzten Wert wird automatisch
    eine erzeugt -- so gibt es keine Logzeile ohne Zuordnung.
    """
    parent = _context.get()
    effective_correlation_id = correlation_id or parent.correlation_id or new_correlation_id()
    child = LogContext(
        correlation_id=effective_correlation_id,
        analysis_run_id=analysis_run_id or parent.analysis_run_id,
        stock_symbol=stock_symbol or parent.stock_symbol,
        module=module or parent.module,
    )
    token: Token[LogContext] = _context.set(child)
    try:
        yield child
    finally:
        _context.reset(token)
