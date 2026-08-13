from __future__ import annotations

import json
import logging

from tvcdp.logging_setup import configure_logging, log_step_result


class TestConfigureLogging:
    def test_log_zeile_ist_gueltiges_json_mit_erwarteten_feldern(self) -> None:
        import io

        logger = configure_logging()
        buffer = io.StringIO()
        handler = logger.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        handler.stream = buffer

        log_step_result(logger, "cdp_reachability", "PASSED", target_count=1)

        line = buffer.getvalue().strip()
        parsed = json.loads(line)

        assert parsed["step_id"] == "cdp_reachability"
        assert parsed["status"] == "PASSED"
        assert parsed["target_count"] == 1
        assert parsed["level"] == "INFO"
        assert "timestamp" in parsed

    def test_sensible_felder_werden_auch_im_log_redigiert(self) -> None:
        import io

        logger = configure_logging()
        buffer = io.StringIO()
        handler = logger.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        handler.stream = buffer

        log_step_result(logger, "session_check", "PASSED", cookie="sessionid=abc123")

        parsed = json.loads(buffer.getvalue().strip())
        assert parsed["cookie"] == "***REDACTED***"

    def test_wiederholtes_konfigurieren_haeuft_keine_handler_an(self) -> None:
        configure_logging()
        configure_logging()
        logger = configure_logging()

        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)
