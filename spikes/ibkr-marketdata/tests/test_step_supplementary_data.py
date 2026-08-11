from typing import Any

from ibkrspike.config import IbkrSpikeConfig
from ibkrspike.steps import step_supplementary_data
from ibkrspike.steps.base import StepStatus


class _Contract:
    # Spiegelt die Attributnamen des echten ib_async.Contract (secType/conId).
    secType = "STK"  # noqa: N815
    conId = 265598  # noqa: N815


class FakeSupplementaryClient:
    def __init__(
        self,
        *,
        connect_error: Exception | None = None,
        qualify_error: Exception | None = None,
        fundamental_by_report: dict[str, str] | None = None,
        fundamental_errors: dict[str, Exception] | None = None,
        option_chains: list[dict[str, Any]] | None = None,
        option_chain_error: Exception | None = None,
        option_snapshot: dict[str, Any] | None = None,
        option_snapshot_error: Exception | None = None,
    ) -> None:
        self._connect_error = connect_error
        self._qualify_error = qualify_error
        self._fundamental_by_report = fundamental_by_report or {}
        self._fundamental_errors = fundamental_errors or {}
        self._option_chains = option_chains if option_chains is not None else []
        self._option_chain_error = option_chain_error
        self._option_snapshot = option_snapshot or {"greeks_available": False}
        self._option_snapshot_error = option_snapshot_error
        self._connected = False
        self.disconnected = False

    def connect(self, host: str, port: int, client_id: int, timeout_seconds: float) -> None:
        if self._connect_error is not None:
            raise self._connect_error
        self._connected = True

    def is_connected(self) -> bool:
        return self._connected

    def qualify_stock(self, symbol: str) -> Any:
        if self._qualify_error is not None:
            raise self._qualify_error
        return _Contract()

    def fundamental_data(self, contract: Any, report_type: str) -> str:
        if report_type in self._fundamental_errors:
            raise self._fundamental_errors[report_type]
        return self._fundamental_by_report.get(report_type, "")

    def option_chain_params(
        self,
        underlying_symbol: str,
        underlying_sec_type: str,
        underlying_con_id: int,
        fut_fop_exchange: str = "",
    ) -> list[dict[str, Any]]:
        if self._option_chain_error is not None:
            raise self._option_chain_error
        return self._option_chains

    def option_snapshot(
        self, symbol: str, expiration: str, strike: float, right: str, exchange: str = "SMART"
    ) -> dict[str, Any]:
        if self._option_snapshot_error is not None:
            raise self._option_snapshot_error
        return self._option_snapshot

    def disconnect(self) -> None:
        self.disconnected = True
        self._connected = False


def _config() -> IbkrSpikeConfig:
    return IbkrSpikeConfig(
        host="127.0.0.1", port=7496, client_id=17, timeout_seconds=10.0, account_id=None
    )


def test_earnings_kalender_und_analystenschaetzungen_verfuegbar() -> None:
    fake = FakeSupplementaryClient(
        fundamental_by_report={
            "CalendarReport": "<CalendarReport>...</CalendarReport>",
            "RESC": "<RESC>...</RESC>",
        }
    )

    result = step_supplementary_data.run(_config(), "AAPL", client_factory=lambda: fake)

    assert result["_status"] == StepStatus.OK.value
    assert result["earnings_calendar"]["status"] == StepStatus.OK.value
    assert result["earnings_calendar"]["xml_length"] > 0
    assert result["analyst_estimates"]["status"] == StepStatus.OK.value
    assert fake.disconnected is True


def test_fehlende_berechtigung_liefert_inconclusive_pro_report_ohne_abbruch() -> None:
    fake = FakeSupplementaryClient(fundamental_by_report={"CalendarReport": ""})

    result = step_supplementary_data.run(_config(), "AAPL", client_factory=lambda: fake)

    assert result["_status"] == StepStatus.OK.value
    assert result["earnings_calendar"]["status"] == StepStatus.INCONCLUSIVE.value
    # RESC wurde trotzdem angefragt, obwohl CalendarReport leer war.
    assert result["analyst_estimates"]["status"] == StepStatus.INCONCLUSIVE.value


def test_whitespace_only_antwort_gilt_als_inconclusive_nicht_ok() -> None:
    """Live-Fund (2026-08-11): IBKR antwortet auf CalendarReport fuer manche
    Kontrakte technisch fehlerfrei, aber mit einer inhaltslosen
    Whitespace-Antwort (xml_length=2) statt einer Exception oder einem
    echten leeren String -- das darf nicht als 'ok' durchgehen."""
    fake = FakeSupplementaryClient(fundamental_by_report={"CalendarReport": "\r\n"})

    result = step_supplementary_data.run(_config(), "AAPL", client_factory=lambda: fake)

    assert result["earnings_calendar"]["status"] == StepStatus.INCONCLUSIVE.value


def test_fundamentaldaten_fehler_blockiert_nicht_die_optionskette() -> None:
    fake = FakeSupplementaryClient(
        fundamental_errors={"CalendarReport": RuntimeError("no fundamental data (430)")},
        option_chains=[
            {
                "exchange": "SMART",
                "trading_class": "AAPL",
                "multiplier": "100",
                "expirations": ["20260918", "20261016"],
                "strikes": [190.0, 195.0, 200.0],
            }
        ],
        option_snapshot={
            "greeks_available": True,
            "implied_vol": 0.25,
            "delta": 0.5,
            "gamma": 0.02,
            "vega": 0.1,
            "theta": -0.05,
        },
    )

    result = step_supplementary_data.run(_config(), "AAPL", client_factory=lambda: fake)

    assert result["_status"] == StepStatus.OK.value
    assert result["earnings_calendar"]["status"] == StepStatus.FAILED.value
    assert "430" in result["earnings_calendar"]["error"]
    assert result["option_chain"]["status"] == StepStatus.OK.value
    assert result["option_chain"]["strike_count"] == 3
    assert result["option_chain"]["greeks_probe"]["status"] == StepStatus.OK.value
    assert result["option_chain"]["greeks_probe"]["delta"] == 0.5


def test_optionskette_ohne_greeks_meldet_inconclusive_nicht_ok() -> None:
    fake = FakeSupplementaryClient(
        option_chains=[
            {
                "exchange": "SMART",
                "trading_class": "AAPL",
                "multiplier": "100",
                "expirations": ["20990101"],
                "strikes": [100.0],
            }
        ],
        option_snapshot={"greeks_available": False},
    )

    result = step_supplementary_data.run(_config(), "AAPL", client_factory=lambda: fake)

    assert result["option_chain"]["greeks_probe"]["status"] == StepStatus.INCONCLUSIVE.value


def test_leere_optionskette_liefert_inconclusive() -> None:
    fake = FakeSupplementaryClient(option_chains=[])

    result = step_supplementary_data.run(_config(), "AAPL", client_factory=lambda: fake)

    assert result["option_chain"]["status"] == StepStatus.INCONCLUSIVE.value


def test_verbindungsfehler_liefert_failed_ohne_weitere_anfragen() -> None:
    fake = FakeSupplementaryClient(connect_error=ConnectionRefusedError("nope"))

    result = step_supplementary_data.run(_config(), "AAPL", client_factory=lambda: fake)

    assert result["_status"] == StepStatus.FAILED.value
