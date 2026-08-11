from ibkrspike.config import IbkrSpikeConfig
from ibkrspike.steps import step_connectivity
from ibkrspike.steps.base import StepStatus


class FakeClient:
    def __init__(
        self,
        *,
        connect_error: Exception | None = None,
        connected_after_connect: bool = True,
    ) -> None:
        self._connect_error = connect_error
        self._connected_after_connect = connected_after_connect
        self._connected = False
        self.disconnected = False
        self.connect_calls: list[tuple[str, int, int, float]] = []

    def connect(self, host: str, port: int, client_id: int, timeout_seconds: float) -> None:
        self.connect_calls.append((host, port, client_id, timeout_seconds))
        if self._connect_error is not None:
            raise self._connect_error
        self._connected = self._connected_after_connect

    def is_connected(self) -> bool:
        return self._connected

    def managed_accounts(self) -> list[str]:
        return ["U1234567"]

    def server_version(self) -> int:
        return 176

    def connection_stats(self) -> dict[str, object]:
        return {"start_time": "2026-08-11T09:00:00+00:00", "duration_seconds": 0.0}

    def disconnect(self) -> None:
        self.disconnected = True
        self._connected = False


def _config() -> IbkrSpikeConfig:
    return IbkrSpikeConfig(
        host="127.0.0.1", port=7497, client_id=17, timeout_seconds=10.0, account_id=None
    )


def test_erfolgreiche_verbindung_liefert_ok_mit_accountinfo() -> None:
    fake = FakeClient()

    result = step_connectivity.run(_config(), client_factory=lambda: fake)

    assert result["_status"] == StepStatus.OK.value
    assert result["managed_accounts"] == ["U1234567"]
    assert result["server_version"] == 176
    assert fake.connect_calls == [("127.0.0.1", 7497, 17, 10.0)]
    assert fake.disconnected is True


def test_verbindungsfehler_liefert_failed_statt_absturz() -> None:
    fake = FakeClient(connect_error=ConnectionRefusedError("Connection refused"))

    result = step_connectivity.run(_config(), client_factory=lambda: fake)

    assert result["_status"] == StepStatus.FAILED.value
    assert "ConnectionRefusedError" in result["error"]


def test_stille_nicht_verbindung_ohne_exception_liefert_failed() -> None:
    fake = FakeClient(connected_after_connect=False)

    result = step_connectivity.run(_config(), client_factory=lambda: fake)

    assert result["_status"] == StepStatus.FAILED.value
    assert "is_connected" in result["error"]
    assert fake.disconnected is True
