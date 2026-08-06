"""Tests des strukturierten Loggings und des Correlation-Kontexts."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

import pytest

from ai_trading_analyst.config import LoggingConfig
from ai_trading_analyst.observability import (
    JsonLogFormatter,
    configure_logging,
    current_context,
    get_logger,
    log_context,
    new_correlation_id,
)


def make_record(
    *,
    name: str = "ata.test",
    level: int = logging.INFO,
    message: str = "Lauf gestartet",
    pathname: str = "/x/y.py",
    lineno: int = 42,
) -> logging.LogRecord:
    return logging.LogRecord(
        name=name,
        level=level,
        pathname=pathname,
        lineno=lineno,
        msg=message,
        args=(),
        exc_info=None,
    )


def format_as_json(record: logging.LogRecord) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(JsonLogFormatter().format(record))
    return payload


class TestJsonFormatter:
    def test_emits_the_mandatory_fields(self) -> None:
        payload = format_as_json(make_record())

        assert payload["level"] == "INFO"
        assert payload["logger"] == "ata.test"
        assert payload["message"] == "Lauf gestartet"
        assert payload["source"] == "/x/y.py:42"
        assert str(payload["timestamp"]).endswith("+00:00")

    def test_extra_fields_become_own_json_keys(self) -> None:
        record = make_record(message="fertig")
        record.event = "run_completed"

        payload = format_as_json(record)

        assert payload["event"] == "run_completed"

    def test_extra_field_cannot_overwrite_a_structural_field(self) -> None:
        """Ein 'extra' mit reserviertem Namen wird umbenannt statt zu ueberschreiben."""
        record = make_record()
        record.level = "gefaelscht"

        payload = format_as_json(record)

        assert payload["level"] == "INFO"
        assert payload["extra_level"] == "gefaelscht"

    def test_exception_is_included(self) -> None:
        record = make_record(level=logging.ERROR, message="fehlgeschlagen")
        try:
            raise ValueError("kaputt")
        except ValueError:
            record.exc_info = sys.exc_info()

        payload = format_as_json(record)

        assert "ValueError: kaputt" in str(payload["exception"])

    def test_output_is_a_single_line(self) -> None:
        """Mehrzeilige Meldungen duerfen die zeilenweise Auswertung nicht zerstoeren."""
        record = make_record(message="Zeile eins\nZeile zwei")

        assert "\n" not in JsonLogFormatter().format(record)

    def test_non_serialisable_values_do_not_break_the_line(self) -> None:
        record = make_record()
        record.payload = object()

        assert format_as_json(record)["payload"]


class TestLogContext:
    def test_context_fields_land_in_the_payload(self) -> None:
        with log_context(correlation_id="abc123", analysis_run_id="run-1", stock_symbol="AAPL"):
            payload = format_as_json(make_record(name="ata.screener"))

        assert payload["correlation_id"] == "abc123"
        assert payload["analysis_run_id"] == "run-1"
        assert payload["stock_symbol"] == "AAPL"

    def test_module_defaults_to_the_logger_name(self) -> None:
        assert format_as_json(make_record(name="ata.screener"))["module"] == "ata.screener"

    def test_correlation_id_is_generated_when_absent(self) -> None:
        with log_context() as context:
            assert context.correlation_id is not None
            assert len(context.correlation_id) == 16

    def test_nested_context_is_additive(self) -> None:
        with log_context(correlation_id="abc123", analysis_run_id="run-1"):
            with log_context(stock_symbol="MSFT", module="screener") as inner:
                assert inner.correlation_id == "abc123"
                assert inner.analysis_run_id == "run-1"
                assert inner.stock_symbol == "MSFT"
                assert inner.module == "screener"

    def test_context_is_restored_after_the_block(self) -> None:
        assert current_context().correlation_id is None
        with log_context(correlation_id="abc123"):
            assert current_context().correlation_id == "abc123"
        assert current_context().correlation_id is None

    def test_context_is_restored_even_after_an_exception(self) -> None:
        with pytest.raises(RuntimeError):
            with log_context(correlation_id="abc123"):
                raise RuntimeError("Abbruch")

        assert current_context().correlation_id is None

    def test_unset_fields_are_omitted(self) -> None:
        with log_context(correlation_id="abc123") as context:
            assert context.as_log_fields() == {"correlation_id": "abc123"}

    def test_correlation_ids_are_unique(self) -> None:
        assert len({new_correlation_id() for _ in range(1000)}) == 1000


class TestConfigureLogging:
    def test_repeated_configuration_does_not_duplicate_handlers(self) -> None:
        configure_logging(LoggingConfig(format="json"))
        configure_logging(LoggingConfig(format="json"))

        assert len(logging.getLogger().handlers) == 1

    def test_json_output_is_parseable_end_to_end(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging(LoggingConfig(level="INFO", format="json"))
        with log_context(correlation_id="abc123", stock_symbol="NVDA"):
            get_logger("ata.test").info("Kandidat gefunden", extra={"event": "candidate_found"})

        payload = json.loads(capsys.readouterr().out.strip())

        assert payload["message"] == "Kandidat gefunden"
        assert payload["correlation_id"] == "abc123"
        assert payload["stock_symbol"] == "NVDA"
        assert payload["event"] == "candidate_found"

    def test_console_format_is_human_readable(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging(LoggingConfig(level="INFO", format="console"))
        with log_context(correlation_id="abc123", stock_symbol="NVDA"):
            get_logger("ata.test").info("Kandidat gefunden")

        output = capsys.readouterr().out

        assert "abc123" in output
        assert "NVDA" in output
        assert "Kandidat gefunden" in output

    def test_level_is_respected(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(LoggingConfig(level="WARNING", format="json"))
        logger = get_logger("ata.test")

        logger.info("wird unterdrueckt")
        logger.warning("wird ausgegeben")

        output = capsys.readouterr().out
        assert "wird unterdrueckt" not in output
        assert "wird ausgegeben" in output
