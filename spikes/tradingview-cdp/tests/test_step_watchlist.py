from __future__ import annotations

from tvcdp.cdp_client import CdpSession
from tvcdp.steps import step_watchlist
from tvcdp.steps.base import StepStatus, run_step

from .conftest import ScriptedCdpServer


class TestStepWatchlist:
    async def test_keine_sonde_konfiguriert_gilt_als_inconclusive(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        _, session = scripted_session

        result = await run_step(
            step_watchlist.STEP_ID,
            step_watchlist.TITLE,
            lambda: step_watchlist.run(session, None),
        )

        assert result.status is StepStatus.INCONCLUSIVE

    async def test_wohlgeformte_watchlist_gilt_als_passed(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        server, session = scripted_session
        server.when(
            "probe",
            [
                {
                    "name": "Swing-Kandidaten",
                    "symbols": [
                        {"symbol": "AAPL", "exchange": "NASDAQ"},
                        {"symbol": "MSFT", "exchange": "NASDAQ"},
                    ],
                }
            ],
        )

        result = await run_step(
            step_watchlist.STEP_ID,
            step_watchlist.TITLE,
            lambda: step_watchlist.run(session, "probe"),
        )

        assert result.status is StepStatus.PASSED
        assert result.details["watchlist_count"] == 1
        assert result.details["total_symbol_count"] == 2
        assert result.details["watchlist_names"] == ["Swing-Kandidaten"]
        assert "elapsed_seconds" in result.details

    async def test_mehrere_watchlists_werden_unterschieden(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        server, session = scripted_session
        server.when(
            "probe",
            [
                {"name": "A", "symbols": [{"symbol": "AAPL", "exchange": "NASDAQ"}]},
                {"name": "B", "symbols": [{"symbol": "TSLA", "exchange": "NASDAQ"}]},
            ],
        )

        result = await run_step(
            step_watchlist.STEP_ID,
            step_watchlist.TITLE,
            lambda: step_watchlist.run(session, "probe"),
        )

        assert result.details["watchlist_names"] == ["A", "B"]

    async def test_falsch_geformtes_ergebnis_gilt_als_inconclusive_nicht_failed(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        server, session = scripted_session
        server.when("probe", {"unerwartet": True})

        result = await run_step(
            step_watchlist.STEP_ID,
            step_watchlist.TITLE,
            lambda: step_watchlist.run(session, "probe"),
        )

        assert result.status is StepStatus.INCONCLUSIVE
        assert result.details["raw_type"] == "dict"

    async def test_symbol_eintrag_ohne_exchange_gilt_als_inconclusive(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        server, session = scripted_session
        server.when(
            "probe", [{"name": "A", "symbols": [{"symbol": "AAPL"}]}]  # exchange fehlt
        )

        result = await run_step(
            step_watchlist.STEP_ID,
            step_watchlist.TITLE,
            lambda: step_watchlist.run(session, "probe"),
        )

        assert result.status is StepStatus.INCONCLUSIVE
