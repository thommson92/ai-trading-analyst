from __future__ import annotations

from tvcdp.cdp_client import CdpSession
from tvcdp.steps import step_session_check
from tvcdp.steps.base import StepStatus, run_step

from .conftest import ScriptedCdpServer


class TestStepSessionCheck:
    async def test_keine_sonde_konfiguriert_gilt_als_inconclusive(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        _, session = scripted_session

        result = await run_step(
            step_session_check.STEP_ID,
            step_session_check.TITLE,
            lambda: step_session_check.run(session, None),
        )

        assert result.status is StepStatus.INCONCLUSIVE

    async def test_sonde_liefert_true_gilt_als_passed(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        server, session = scripted_session
        server.when("document.querySelector('.user-menu') !== null", True)

        result = await run_step(
            step_session_check.STEP_ID,
            step_session_check.TITLE,
            lambda: step_session_check.run(
                session, "document.querySelector('.user-menu') !== null"
            ),
        )

        assert result.status is StepStatus.PASSED
        assert result.details == {"authenticated": True}

    async def test_sonde_liefert_false_gilt_als_failed_nicht_als_fehler(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        server, session = scripted_session
        server.when("loggedInCheck", False)

        result = await run_step(
            step_session_check.STEP_ID,
            step_session_check.TITLE,
            lambda: step_session_check.run(session, "loggedInCheck"),
        )

        assert result.status is StepStatus.FAILED
        assert result.details == {"authenticated": False}

    async def test_nicht_boolescher_rueckgabewert_gilt_als_inconclusive(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        server, session = scripted_session
        server.when("ambiguousCheck", "vielleicht")

        result = await run_step(
            step_session_check.STEP_ID,
            step_session_check.TITLE,
            lambda: step_session_check.run(session, "ambiguousCheck"),
        )

        assert result.status is StepStatus.INCONCLUSIVE
        assert result.details["probe_returned_type"] == "str"

    async def test_kein_cookie_oder_token_erscheint_jemals_im_ergebnis(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        """Auch wenn eine schlecht gewaehlte Sonde selbst ein Cookie
        zurueckgeben wuerde, prueft dieser Test die Absicht des Schritts:
        das Ergebnis-Dict enthaelt ausschliesslich den Schluessel
        'authenticated' mit einem Wahrheitswert -- keinen Rohinhalt."""
        server, session = scripted_session
        server.when("probe", True)

        result = await run_step(
            step_session_check.STEP_ID,
            step_session_check.TITLE,
            lambda: step_session_check.run(session, "probe"),
        )

        assert set(result.details.keys()) <= {"authenticated"}
