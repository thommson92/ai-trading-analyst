from __future__ import annotations

from tvcdp.cdp_client import CdpSession
from tvcdp.steps import step_indicators
from tvcdp.steps.base import StepStatus, run_step

from .conftest import ScriptedCdpServer


class TestStepIndicators:
    async def test_keine_einzige_sonde_konfiguriert_gilt_als_inconclusive(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        _, session = scripted_session

        result = await run_step(
            step_indicators.STEP_ID,
            step_indicators.TITLE,
            lambda: step_indicators.run(session, None, None, None, None),
        )

        assert result.status is StepStatus.INCONCLUSIVE

    async def test_alle_vier_indikatoren_erfolgreich_gilt_als_passed(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        server, session = scripted_session
        server.when("rsi", 61.4)
        server.when("rsi_ma", 55.2)
        server.when("ema5", 101.3)
        server.when("ema20", 98.7)

        result = await run_step(
            step_indicators.STEP_ID,
            step_indicators.TITLE,
            lambda: step_indicators.run(session, "rsi", "rsi_ma", "ema5", "ema20"),
        )

        assert result.status is StepStatus.PASSED
        assert result.details["indicators"]["rsi"] == {"status": "ok", "value": 61.4}
        assert result.details["indicators"]["ema20"] == {"status": "ok", "value": 98.7}

    async def test_teilweise_konfiguriert_gilt_als_inconclusive_mit_details_je_indikator(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        server, session = scripted_session
        server.when("rsi", 61.4)

        result = await run_step(
            step_indicators.STEP_ID,
            step_indicators.TITLE,
            lambda: step_indicators.run(session, "rsi", None, None, None),
        )

        assert result.status is StepStatus.INCONCLUSIVE
        assert result.details["indicators"]["rsi"]["status"] == "ok"
        assert result.details["indicators"]["rsi_ma"]["status"] == "not_configured"

    async def test_nicht_numerischer_indikatorwert_gilt_als_invalid(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        server, session = scripted_session
        server.when("rsi", "N/A")

        result = await run_step(
            step_indicators.STEP_ID,
            step_indicators.TITLE,
            lambda: step_indicators.run(session, "rsi", None, None, None),
        )

        assert result.details["indicators"]["rsi"] == {"status": "invalid", "raw_type": "str"}
