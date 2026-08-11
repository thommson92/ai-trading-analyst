from datetime import datetime, timedelta
from typing import Any

from ibkrspike.config import IbkrSpikeConfig
from ibkrspike.steps import step_historical_bars
from ibkrspike.steps.base import StepStatus
from ibkrspike.timeframe import EXCHANGE_TZ


def _raw_bars(count: int, minutes: int = 15) -> list[dict[str, Any]]:
    start = datetime(2026, 8, 6, 9, 30, tzinfo=EXCHANGE_TZ)
    return [
        {
            "timestamp": start + timedelta(minutes=minutes * i),
            "open": 100.0 + i,
            "high": 101.0 + i,
            "low": 99.0 + i,
            "close": 100.5 + i,
            "volume": 10.0 + i,
        }
        for i in range(count)
    ]


class FakeHistoricalClient:
    def __init__(
        self,
        *,
        bars: list[dict[str, Any]] | None = None,
        connect_error: Exception | None = None,
        qualify_error: Exception | None = None,
        historical_error: Exception | None = None,
    ) -> None:
        self._bars = bars if bars is not None else _raw_bars(13)
        self._connect_error = connect_error
        self._qualify_error = qualify_error
        self._historical_error = historical_error
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
        return object()

    def historical_bars(
        self, contract: Any, duration_str: str, bar_size: str, use_rth: bool
    ) -> list[dict[str, Any]]:
        if self._historical_error is not None:
            raise self._historical_error
        return self._bars

    def disconnect(self) -> None:
        self.disconnected = True
        self._connected = False


def _config() -> IbkrSpikeConfig:
    return IbkrSpikeConfig(
        host="127.0.0.1", port=7496, client_id=17, timeout_seconds=10.0, account_id=None
    )


def test_dreizehn_15_minuten_bars_ergeben_eine_vollstaendige_kerze() -> None:
    fake = FakeHistoricalClient()

    result = step_historical_bars.run(
        _config(), "AAPL", "1 D", "15 mins", client_factory=lambda: fake
    )

    assert result["_status"] == StepStatus.OK.value
    assert result["raw_bar_count"] == 13
    assert result["aggregated_candle_count"] == 1
    assert result["complete_candle_count"] == 1
    assert result["candles"][0]["is_complete"] is True
    assert fake.disconnected is True


def test_unbekannte_bar_groesse_wird_ohne_verbindungsversuch_abgelehnt() -> None:
    fake = FakeHistoricalClient()

    result = step_historical_bars.run(
        _config(), "AAPL", "1 D", "30 mins", client_factory=lambda: fake
    )

    error = result["error"]
    assert result["_status"] == StepStatus.FAILED.value
    assert "teilbar" in error or "30 mins" in error
    assert fake._connected is False


def test_verbindungsfehler_liefert_failed() -> None:
    fake = FakeHistoricalClient(connect_error=ConnectionRefusedError("nope"))

    result = step_historical_bars.run(
        _config(), "AAPL", "1 D", "15 mins", client_factory=lambda: fake
    )

    assert result["_status"] == StepStatus.FAILED.value
    assert "ConnectionRefusedError" in result["error"]


def test_kontraktaufloesung_fehlgeschlagen_liefert_failed_und_trennt_disconnect() -> None:
    fake = FakeHistoricalClient(qualify_error=ValueError("unbekanntes Symbol"))

    result = step_historical_bars.run(
        _config(), "NICHTEXISTENT", "1 D", "15 mins", client_factory=lambda: fake
    )

    assert result["_status"] == StepStatus.FAILED.value
    assert "Kontrakt" in result["error"]
    assert fake.disconnected is True


def test_leere_bar_liste_liefert_inconclusive_statt_leerer_kerzenliste() -> None:
    fake = FakeHistoricalClient(bars=[])

    result = step_historical_bars.run(
        _config(), "AAPL", "1 D", "15 mins", client_factory=lambda: fake
    )

    assert result["_status"] == StepStatus.INCONCLUSIVE.value
