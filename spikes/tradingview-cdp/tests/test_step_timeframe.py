from __future__ import annotations

from tvcdp.cdp_client import CdpSession
from tvcdp.steps import step_timeframe
from tvcdp.steps.base import StepStatus, run_step

from .conftest import ScriptedCdpServer


class TestStepTimeframe:
    async def test_keine_sonde_konfiguriert_gilt_als_inconclusive(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        _, session = scripted_session

        result = await run_step(
            step_timeframe.STEP_ID, step_timeframe.TITLE, lambda: step_timeframe.run(session, None)
        )

        assert result.status is StepStatus.INCONCLUSIVE

    async def test_195_minuten_gilt_als_passed(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        server, session = scripted_session
        server.when("probe", 195)

        result = await run_step(
            step_timeframe.STEP_ID,
            step_timeframe.TITLE,
            lambda: step_timeframe.run(session, "probe"),
        )

        assert result.status is StepStatus.PASSED
        assert result.details["detected_minutes"] == 195

    async def test_abweichender_timeframe_gilt_als_failed(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        server, session = scripted_session
        server.when("probe", 60)

        result = await run_step(
            step_timeframe.STEP_ID,
            step_timeframe.TITLE,
            lambda: step_timeframe.run(session, "probe"),
        )

        assert result.status is StepStatus.FAILED
        assert result.details["detected_minutes"] == 60

    async def test_nicht_numerischer_wert_gilt_als_inconclusive(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        server, session = scripted_session
        server.when("probe", "195m")

        result = await run_step(
            step_timeframe.STEP_ID,
            step_timeframe.TITLE,
            lambda: step_timeframe.run(session, "probe"),
        )

        assert result.status is StepStatus.INCONCLUSIVE
