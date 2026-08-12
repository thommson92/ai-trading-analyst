from __future__ import annotations

from tvcdp.cdp_client import CdpSession
from tvcdp.steps import step_layout
from tvcdp.steps.base import StepStatus, run_step

from .conftest import ScriptedCdpServer


class TestStepLayout:
    async def test_keine_sonde_konfiguriert_gilt_als_inconclusive(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        _, session = scripted_session

        result = await run_step(
            step_layout.STEP_ID, step_layout.TITLE, lambda: step_layout.run(session, None)
        )

        assert result.status is StepStatus.INCONCLUSIVE

    async def test_erkennung_ohne_erwartungswert_ist_unverifiziert_aber_passed(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        server, session = scripted_session
        server.when("probe", "Mein Long-Swing-Layout")

        result = await run_step(
            step_layout.STEP_ID, step_layout.TITLE, lambda: step_layout.run(session, "probe")
        )

        assert result.status is StepStatus.PASSED
        assert result.details["verified"] is False

    async def test_erkanntes_layout_stimmt_mit_erwartung_ueberein(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        server, session = scripted_session
        server.when("probe", "Mein Long-Swing-Layout")

        result = await run_step(
            step_layout.STEP_ID,
            step_layout.TITLE,
            lambda: step_layout.run(session, "probe", "Mein Long-Swing-Layout"),
        )

        assert result.status is StepStatus.PASSED
        assert result.details["verified"] is True

    async def test_erkanntes_layout_weicht_von_erwartung_ab_gilt_als_failed(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        server, session = scripted_session
        server.when("probe", "Irgendein anderer Chart")

        result = await run_step(
            step_layout.STEP_ID,
            step_layout.TITLE,
            lambda: step_layout.run(session, "probe", "Mein Long-Swing-Layout"),
        )

        assert result.status is StepStatus.FAILED
        assert result.details["verified"] is False

    async def test_leerer_string_gilt_als_inconclusive(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        server, session = scripted_session
        server.when("probe", "")

        result = await run_step(
            step_layout.STEP_ID, step_layout.TITLE, lambda: step_layout.run(session, "probe")
        )

        assert result.status is StepStatus.INCONCLUSIVE
