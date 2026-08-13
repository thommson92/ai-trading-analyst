from __future__ import annotations

import pytest

from tvcdp.cdp_client import CdpTarget
from tvcdp.config import CdpConfig
from tvcdp.steps import step_cdp_reachability
from tvcdp.steps.base import StepStatus, run_step

_TARGET = CdpTarget(
    id="1", title="TradingView", url="app://tv/", type="page", websocket_debugger_url="ws://x"
)


class TestStepCdpReachability:
    async def test_mindestens_ein_ziel_gilt_als_passed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "tvcdp.steps.step_cdp_reachability.list_targets", lambda _config: [_TARGET]
        )

        result = await run_step(
            step_cdp_reachability.STEP_ID,
            step_cdp_reachability.TITLE,
            lambda: step_cdp_reachability.run(CdpConfig()),
        )

        assert result.status is StepStatus.PASSED
        assert result.details["target_count"] == 1

    async def test_leere_zielliste_gilt_als_failed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("tvcdp.steps.step_cdp_reachability.list_targets", lambda _config: [])

        result = await run_step(
            step_cdp_reachability.STEP_ID,
            step_cdp_reachability.TITLE,
            lambda: step_cdp_reachability.run(CdpConfig()),
        )

        assert result.status is StepStatus.FAILED

    async def test_connectionerror_wird_von_run_step_zu_failed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tvcdp.cdp_client import CdpConnectionError

        def _raise(_config: CdpConfig) -> list[CdpTarget]:
            raise CdpConnectionError("kein Port offen")

        monkeypatch.setattr("tvcdp.steps.step_cdp_reachability.list_targets", _raise)

        result = await run_step(
            step_cdp_reachability.STEP_ID,
            step_cdp_reachability.TITLE,
            lambda: step_cdp_reachability.run(CdpConfig()),
        )

        assert result.status is StepStatus.FAILED
        assert "kein Port offen" in (result.error or "")
