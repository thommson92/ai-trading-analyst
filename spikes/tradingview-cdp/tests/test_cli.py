from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tvcdp.cli import _combined_indicator_read_js, _emit
from tvcdp.probe_config import ProbeConfig
from tvcdp.results_store import new_run_directory
from tvcdp.steps.base import StepResult, StepStatus


class TestEmitRedaction:
    """Regression: _emit() darf auf der Konsole nichts ausgeben, was in der
    persistierten Ergebnisdatei redigiert wuerde -- beide Ausgabewege muessen
    durch dieselbe Redaction laufen (Review-Fund)."""

    def test_sensible_details_werden_auch_auf_stdout_redigiert(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run_dir = new_run_directory(tmp_path)
        now = datetime.now(UTC)
        result = StepResult(
            step_id="session_check",
            title="Beispiel",
            status=StepStatus.PASSED,
            started_at=now,
            finished_at=now,
            details={"cookie": "sessionid=geheim123"},
        )

        _emit(run_dir, result)

        stdout = capsys.readouterr().out
        assert "geheim123" not in stdout
        assert "***REDACTED***" in stdout

    def test_sensibler_fehlertext_wird_auch_auf_stdout_redigiert(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run_dir = new_run_directory(tmp_path)
        now = datetime.now(UTC)
        result = StepResult(
            step_id="error_case_detection",
            title="Beispiel",
            status=StepStatus.FAILED,
            started_at=now,
            finished_at=now,
            error="CDP-Fehler: Bearer eyJabcdefgh.eyJabcdefgh.signaturewert",
        )

        _emit(run_dir, result)

        stdout = capsys.readouterr().out
        assert "eyJabcdefgh" not in stdout


class TestCombinedIndicatorReadJs:
    def test_liefert_none_wenn_eine_sonde_fehlt(self) -> None:
        probes = ProbeConfig(
            session_authenticated_js=None,
            watchlist_js=None,
            layout_name_js=None,
            timeframe_minutes_js=None,
            last_closed_candle_js=None,
            indicator_rsi_js="rsi()",
            indicator_rsi_ma_js="rsiMa()",
            indicator_ema5_js="ema5()",
            indicator_ema20_js=None,
            change_symbol_js_template=None,
        )

        assert _combined_indicator_read_js(probes) is None

    def test_kombiniert_alle_vier_sonden_wenn_vollstaendig_konfiguriert(self) -> None:
        probes = ProbeConfig(
            session_authenticated_js=None,
            watchlist_js=None,
            layout_name_js=None,
            timeframe_minutes_js=None,
            last_closed_candle_js=None,
            indicator_rsi_js="rsi()",
            indicator_rsi_ma_js="rsiMa()",
            indicator_ema5_js="ema5()",
            indicator_ema20_js="ema20()",
            change_symbol_js_template=None,
        )

        combined = _combined_indicator_read_js(probes)

        assert combined is not None
        assert "rsi()" in combined
        assert "rsiMa()" in combined
        assert "ema5()" in combined
        assert "ema20()" in combined
