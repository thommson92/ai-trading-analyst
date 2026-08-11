from __future__ import annotations

from typing import Any, Protocol

from ..config import IbkrSpikeConfig
from .base import StepStatus

STEP_ID = "connectivity"
TITLE = "Verbindungsaufbau zu TWS/IB Gateway"


class IbkrClient(Protocol):
    def connect(self, host: str, port: int, client_id: int, timeout_seconds: float) -> None: ...

    def is_connected(self) -> bool: ...

    def managed_accounts(self) -> list[str]: ...

    def server_version(self) -> int: ...

    def connection_stats(self) -> dict[str, Any]: ...

    def disconnect(self) -> None: ...


def default_client_factory() -> IbkrClient:
    from ..ibkr_client import IbAsyncClient

    return IbAsyncClient()


def run(
    config: IbkrSpikeConfig,
    client_factory: Any = default_client_factory,
) -> dict[str, Any]:
    client = client_factory()
    try:
        client.connect(config.host, config.port, config.client_id, config.timeout_seconds)
    except Exception as exc:
        # Verbindungsfehler jeder Art sind hier ein FAILED-Ergebnis, kein Absturz.
        return {
            "_status": StepStatus.FAILED.value,
            "host": config.host,
            "port": config.port,
            "error": f"{type(exc).__name__}: {exc}",
        }

    try:
        if not client.is_connected():
            return {
                "_status": StepStatus.FAILED.value,
                "host": config.host,
                "port": config.port,
                "error": (
                    "connect() ist ohne Fehler zurueckgekehrt, "
                    "is_connected() meldet aber False"
                ),
            }

        return {
            "_status": StepStatus.OK.value,
            "host": config.host,
            "port": config.port,
            "client_id": config.client_id,
            "managed_accounts": client.managed_accounts(),
            "server_version": client.server_version(),
            "connection_stats": client.connection_stats(),
        }
    finally:
        client.disconnect()
