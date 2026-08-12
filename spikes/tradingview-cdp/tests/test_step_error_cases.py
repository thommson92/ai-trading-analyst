from __future__ import annotations

import socket

from tvcdp.cdp_client import CdpSession
from tvcdp.config import CdpConfig
from tvcdp.steps import step_error_cases
from tvcdp.steps.base import StepStatus, run_step

from .conftest import ScriptedCdpServer


def _unused_port_config() -> CdpConfig:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return CdpConfig(port=port, connect_timeout_seconds=1.0)


class TestStepErrorCases:
    async def test_ohne_session_wird_cdp_unreachable_dennoch_erkannt(self) -> None:
        result = await run_step(
            step_error_cases.STEP_ID,
            step_error_cases.TITLE,
            lambda: step_error_cases.run(None, _unused_port_config()),
        )

        assert result.status is StepStatus.PASSED
        assert result.details["automated_checks"]["cdp_nicht_erreichbar"]["detected"] is True

    async def test_mit_session_wird_javascript_fehler_erkannt(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        _, session = scripted_session

        result = await run_step(
            step_error_cases.STEP_ID,
            step_error_cases.TITLE,
            lambda: step_error_cases.run(session, _unused_port_config()),
        )

        assert result.status is StepStatus.PASSED
        assert (
            result.details["automated_checks"]["javascript_fehler_wird_erkannt"]["detected"]
            is True
        )

    async def test_manuelle_faelle_werden_als_solche_ausgewiesen(self) -> None:
        result = await run_step(
            step_error_cases.STEP_ID,
            step_error_cases.TITLE,
            lambda: step_error_cases.run(None, _unused_port_config()),
        )

        assert len(result.details["requires_manual_windows_procedure"]) == 7
