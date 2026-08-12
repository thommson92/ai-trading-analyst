from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from tvcdp.results_store import new_run_directory, write_step_result, write_summary
from tvcdp.steps.base import StepResult, StepStatus


def _make_result(step_id: str = "example", **details: object) -> StepResult:
    now = datetime.now(UTC)
    return StepResult(
        step_id=step_id,
        title="Beispiel",
        status=StepStatus.PASSED,
        started_at=now,
        finished_at=now,
        details=details,
    )


class TestNewRunDirectory:
    def test_erzeugt_ein_eindeutiges_verzeichnis(self, tmp_path: Path) -> None:
        run_dir = new_run_directory(tmp_path)

        assert run_dir.is_dir()
        assert run_dir.parent == tmp_path

    def test_kollision_innerhalb_derselben_sekunde_bricht_nicht_ab(
        self, tmp_path: Path, monkeypatch: object
    ) -> None:
        """Regression: zwei rasch aufeinanderfolgende Aufrufe (z. B. mehrere
        Einzelschritte in einem Shell-Skript) duerfen nicht mit
        FileExistsError abbrechen, auch wenn sie in dieselbe Sekunde fallen."""
        import tvcdp.results_store as results_store_module

        fixed_now = datetime(2026, 8, 7, 9, 38, 54, 0, tzinfo=UTC)

        class _FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
                return fixed_now

        monkeypatch.setattr(results_store_module, "datetime", _FrozenDatetime)  # type: ignore[attr-defined]

        first = new_run_directory(tmp_path)
        second = new_run_directory(tmp_path)

        assert first != second
        assert first.is_dir()
        assert second.is_dir()


class TestWriteStepResult:
    def test_schreibt_lesbares_json_mit_erwarteten_feldern(self, tmp_path: Path) -> None:
        run_dir = new_run_directory(tmp_path)
        result = _make_result(target_count=3)

        path = write_step_result(run_dir, result)
        parsed = json.loads(path.read_text(encoding="utf-8"))

        assert parsed["step_id"] == "example"
        assert parsed["status"] == "PASSED"
        assert parsed["details"] == {"target_count": 3}
        assert "duration_seconds" in parsed

    def test_sensible_details_werden_vor_dem_schreiben_redigiert(self, tmp_path: Path) -> None:
        run_dir = new_run_directory(tmp_path)
        result = _make_result(cookie="sessionid=geheim")

        path = write_step_result(run_dir, result)
        parsed = json.loads(path.read_text(encoding="utf-8"))

        assert parsed["details"]["cookie"] == "***REDACTED***"


class TestWriteSummary:
    def test_fasst_alle_schritte_zusammen(self, tmp_path: Path) -> None:
        run_dir = new_run_directory(tmp_path)
        results = [_make_result("a"), _make_result("b")]

        path = write_summary(run_dir, results)
        parsed = json.loads(path.read_text(encoding="utf-8"))

        assert parsed["step_count"] == 2
        assert [s["step_id"] for s in parsed["steps"]] == ["a", "b"]
