from __future__ import annotations

from tvcdp.cdp_client import CdpTarget
from tvcdp.steps import step_target_discovery
from tvcdp.steps.base import StepStatus, run_step

_TV_TARGET = CdpTarget(
    id="1", title="TradingView", url="app://tv/", type="page", websocket_debugger_url="ws://x"
)
_OTHER_TARGET = CdpTarget(
    id="2", title="DevTools", url="devtools://x", type="page", websocket_debugger_url="ws://y"
)


class TestStepTargetDiscovery:
    async def test_passendes_ziel_wird_gefunden(self) -> None:
        result = await run_step(
            step_target_discovery.STEP_ID,
            step_target_discovery.TITLE,
            lambda: step_target_discovery.run([_TV_TARGET, _OTHER_TARGET], "TradingView"),
        )

        assert result.status is StepStatus.PASSED
        assert result.details["matched_target_id"] == "1"

    async def test_kein_passendes_ziel_gilt_als_inconclusive_nicht_failed(self) -> None:
        result = await run_step(
            step_target_discovery.STEP_ID,
            step_target_discovery.TITLE,
            lambda: step_target_discovery.run([_OTHER_TARGET], "TradingView"),
        )

        assert result.status is StepStatus.INCONCLUSIVE
        assert result.details["available_titles"] == ["DevTools"]

    async def test_leere_zielliste_gilt_als_failed(self) -> None:
        result = await run_step(
            step_target_discovery.STEP_ID,
            step_target_discovery.TITLE,
            lambda: step_target_discovery.run([], "TradingView"),
        )

        assert result.status is StepStatus.FAILED

    async def test_musterabgleich_ist_case_insensitive(self) -> None:
        result = await run_step(
            step_target_discovery.STEP_ID,
            step_target_discovery.TITLE,
            lambda: step_target_discovery.run([_TV_TARGET], "tradingview"),
        )

        assert result.status is StepStatus.PASSED
