import pytest

from ibkrspike.config import ConfigError, IbkrSpikeConfig


def test_fehlender_port_wirft_konfigurationsfehler() -> None:
    with pytest.raises(ConfigError, match="IBKRSPIKE_PORT"):
        IbkrSpikeConfig.from_env(env={})


def test_liest_vollstaendige_konfiguration_aus_env() -> None:
    config = IbkrSpikeConfig.from_env(
        env={
            "IBKRSPIKE_HOST": "10.0.0.5",
            "IBKRSPIKE_PORT": "7497",
            "IBKRSPIKE_CLIENT_ID": "42",
            "IBKRSPIKE_TIMEOUT_SECONDS": "5.5",
            "IBKRSPIKE_ACCOUNT_ID": "U1234567",
        }
    )

    assert config == IbkrSpikeConfig(
        host="10.0.0.5",
        port=7497,
        client_id=42,
        timeout_seconds=5.5,
        account_id="U1234567",
    )


def test_host_client_id_und_timeout_haben_sinnvolle_defaults() -> None:
    config = IbkrSpikeConfig.from_env(env={"IBKRSPIKE_PORT": "7497"})

    assert config.host == "127.0.0.1"
    assert config.client_id == 17
    assert config.timeout_seconds == 10.0
    assert config.account_id is None


def test_ungueltiger_port_wirft_konfigurationsfehler() -> None:
    with pytest.raises(ConfigError, match="IBKRSPIKE_PORT"):
        IbkrSpikeConfig.from_env(env={"IBKRSPIKE_PORT": "nicht-numerisch"})
