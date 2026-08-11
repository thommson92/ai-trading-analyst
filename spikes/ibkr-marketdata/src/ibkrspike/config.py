from __future__ import annotations

import os
from dataclasses import dataclass

_ENV_PREFIX = "IBKRSPIKE_"


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class IbkrSpikeConfig:
    host: str
    port: int
    client_id: int
    timeout_seconds: float
    account_id: str | None

    @staticmethod
    def from_env(env: dict[str, str] | None = None) -> IbkrSpikeConfig:
        source = env if env is not None else os.environ

        port_raw = source.get(f"{_ENV_PREFIX}PORT")
        if not port_raw:
            raise ConfigError(
                f"{_ENV_PREFIX}PORT ist nicht gesetzt. TWS-Standardports: "
                "7496 (Live) / 7497 (Paper). IB-Gateway-Standardports: "
                "4001 (Live) / 4002 (Paper). Kein Default, da Live/Paper "
                "bewusst nicht stillschweigend angenommen werden soll."
            )
        try:
            port = int(port_raw)
        except ValueError as exc:
            raise ConfigError(
                f"{_ENV_PREFIX}PORT muss eine Ganzzahl sein, war: {port_raw!r}"
            ) from exc

        client_id_raw = source.get(f"{_ENV_PREFIX}CLIENT_ID", "17")
        try:
            client_id = int(client_id_raw)
        except ValueError as exc:
            raise ConfigError(
                f"{_ENV_PREFIX}CLIENT_ID muss eine Ganzzahl sein, war: {client_id_raw!r}"
            ) from exc

        timeout_raw = source.get(f"{_ENV_PREFIX}TIMEOUT_SECONDS", "10")
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise ConfigError(
                f"{_ENV_PREFIX}TIMEOUT_SECONDS muss eine Zahl sein, war: {timeout_raw!r}"
            ) from exc

        return IbkrSpikeConfig(
            host=source.get(f"{_ENV_PREFIX}HOST", "127.0.0.1"),
            port=port,
            client_id=client_id,
            timeout_seconds=timeout_seconds,
            account_id=source.get(f"{_ENV_PREFIX}ACCOUNT_ID") or None,
        )
