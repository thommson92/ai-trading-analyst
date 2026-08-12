from __future__ import annotations

from datetime import UTC, datetime

from tvcdp.cdp_client import CdpSession
from tvcdp.steps import step_closed_candle
from tvcdp.steps.base import StepStatus, run_step

from .conftest import ScriptedCdpServer

_NOW = datetime(2026, 8, 7, 12, 45, tzinfo=UTC)


class TestStepClosedCandle:
    async def test_keine_sonde_konfiguriert_gilt_als_inconclusive(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        _, session = scripted_session

        result = await run_step(
            step_closed_candle.STEP_ID,
            step_closed_candle.TITLE,
            lambda: step_closed_candle.run(session, None),
        )

        assert result.status is StepStatus.INCONCLUSIVE

    async def test_geschlossene_kerze_mit_plausiblem_timestamp_gilt_als_passed(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        server, session = scripted_session
        server.when(
            "probe", {"is_closed": True, "closed_timestamp": "2026-08-07T12:45:00+00:00"}
        )

        result = await run_step(
            step_closed_candle.STEP_ID,
            step_closed_candle.TITLE,
            lambda: step_closed_candle.run(session, "probe", now=_NOW),
        )

        assert result.status is StepStatus.PASSED
        assert result.details["age_seconds"] == 0

    async def test_laufende_kerze_wird_korrekt_als_nicht_geschlossen_erkannt(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        """Der kritischste Fall im gesamten Spike (R9): eine laufende Kerze
        darf niemals als 'geschlossen' durchgehen."""
        server, session = scripted_session
        server.when(
            "probe", {"is_closed": False, "closed_timestamp": "2026-08-07T09:30:00+00:00"}
        )

        result = await run_step(
            step_closed_candle.STEP_ID,
            step_closed_candle.TITLE,
            lambda: step_closed_candle.run(session, "probe", now=_NOW),
        )

        assert result.status is StepStatus.FAILED

    async def test_timestamp_in_der_zukunft_gilt_trotz_is_closed_true_als_failed(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        server, session = scripted_session
        server.when(
            "probe", {"is_closed": True, "closed_timestamp": "2026-08-07T99:99:99+00:00"}
        )
        # ungueltiges Format -> INCONCLUSIVE statt Absturz
        result = await run_step(
            step_closed_candle.STEP_ID,
            step_closed_candle.TITLE,
            lambda: step_closed_candle.run(session, "probe", now=_NOW),
        )
        assert result.status is StepStatus.INCONCLUSIVE

        server.when(
            "probe2", {"is_closed": True, "closed_timestamp": "2026-08-07T13:00:00+00:00"}
        )
        result2 = await run_step(
            step_closed_candle.STEP_ID,
            step_closed_candle.TITLE,
            lambda: step_closed_candle.run(session, "probe2", now=_NOW),
        )
        assert result2.status is StepStatus.FAILED

    async def test_unix_timestamp_in_millisekunden_wird_erkannt(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        epoch_ms = int(_NOW.timestamp() * 1000)
        server, session = scripted_session
        server.when("probe", {"is_closed": True, "closed_timestamp": epoch_ms})

        result = await run_step(
            step_closed_candle.STEP_ID,
            step_closed_candle.TITLE,
            lambda: step_closed_candle.run(session, "probe", now=_NOW),
        )

        assert result.status is StepStatus.PASSED

    async def test_fehlendes_feld_gilt_als_inconclusive(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        server, session = scripted_session
        server.when("probe", {"is_closed": True})

        result = await run_step(
            step_closed_candle.STEP_ID,
            step_closed_candle.TITLE,
            lambda: step_closed_candle.run(session, "probe", now=_NOW),
        )

        assert result.status is StepStatus.INCONCLUSIVE
