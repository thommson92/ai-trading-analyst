from datetime import datetime, timedelta
from typing import Any

from ibkrspike.config import IbkrSpikeConfig
from ibkrspike.steps import step_historical_coverage
from ibkrspike.steps.base import StepStatus
from ibkrspike.timeframe import EXCHANGE_TZ


class FakeCoverageClient:
    def __init__(
        self,
        *,
        bars_by_duration: dict[str, list[dict[str, Any]]] | None = None,
        errors_by_duration: dict[str, Exception] | None = None,
        connect_error: Exception | None = None,
        qualify_error: Exception | None = None,
    ) -> None:
        self._bars_by_duration = bars_by_duration or {}
        self._errors_by_duration = errors_by_duration or {}
        self._connect_error = connect_error
        self._qualify_error = qualify_error
        self._connected = False
        self.disconnected = False
        self.requested_durations: list[str] = []

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
        self.requested_durations.append(duration_str)
        if duration_str in self._errors_by_duration:
            raise self._errors_by_duration[duration_str]
        return self._bars_by_duration.get(duration_str, [])

    def disconnect(self) -> None:
        self.disconnected = True
        self._connected = False


def _bars(count: int) -> list[dict[str, Any]]:
    start = datetime(2026, 8, 6, 9, 30, tzinfo=EXCHANGE_TZ)
    return [
        {
            "timestamp": start + timedelta(minutes=15 * i),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 10.0,
        }
        for i in range(count)
    ]


def _config() -> IbkrSpikeConfig:
    return IbkrSpikeConfig(
        host="127.0.0.1", port=7496, client_id=17, timeout_seconds=10.0, account_id=None
    )


def test_erfolgreiche_dauern_liefern_bar_anzahl_und_zeitspanne() -> None:
    fake = FakeCoverageClient(bars_by_duration={"1 M": _bars(10), "1 Y": _bars(50)})
    sleeps: list[float] = []

    result = step_historical_coverage.run(
        _config(),
        "AAPL",
        "15 mins",
        durations=["1 M", "1 Y"],
        client_factory=lambda: fake,
        sleep_fn=sleeps.append,
    )

    assert result["_status"] == StepStatus.OK.value
    results_by_duration = {r["duration_str"]: r for r in result["results"]}
    assert results_by_duration["1 M"]["status"] == StepStatus.OK.value
    assert results_by_duration["1 M"]["raw_bar_count"] == 10
    assert results_by_duration["1 Y"]["raw_bar_count"] == 50
    # Zwischen zwei Anfragen wird genau einmal pausiert, nicht vor der ersten.
    assert sleeps == [step_historical_coverage.DEFAULT_PACING_DELAY_SECONDS]
    assert fake.disconnected is True


def test_ueberschrittenes_duration_limit_wird_pro_dauer_gemeldet_ohne_abbruch() -> None:
    fake = FakeCoverageClient(
        bars_by_duration={"1 M": _bars(10)},
        errors_by_duration={"5 Y": RuntimeError("historical data query returned no data (162)")},
    )

    result = step_historical_coverage.run(
        _config(),
        "AAPL",
        "15 mins",
        durations=["1 M", "5 Y"],
        client_factory=lambda: fake,
        sleep_fn=lambda _seconds: None,
    )

    assert result["_status"] == StepStatus.OK.value
    results_by_duration = {r["duration_str"]: r for r in result["results"]}
    assert results_by_duration["1 M"]["status"] == StepStatus.OK.value
    assert results_by_duration["5 Y"]["status"] == StepStatus.FAILED.value
    assert "162" in results_by_duration["5 Y"]["error"]
    # Beide Dauern wurden trotz Fehlschlag der ersten tatsaechlich angefragt.
    assert fake.requested_durations == ["1 M", "5 Y"]


def test_leere_bar_liste_fuer_eine_dauer_ist_inconclusive_nicht_ok() -> None:
    fake = FakeCoverageClient(bars_by_duration={"1 M": []})

    result = step_historical_coverage.run(
        _config(),
        "AAPL",
        "15 mins",
        durations=["1 M"],
        client_factory=lambda: fake,
        sleep_fn=lambda _seconds: None,
    )

    assert result["results"][0]["status"] == StepStatus.INCONCLUSIVE.value


def test_verbindungsfehler_liefert_failed_ohne_weitere_anfragen() -> None:
    fake = FakeCoverageClient(connect_error=ConnectionRefusedError("nope"))

    result = step_historical_coverage.run(
        _config(),
        "AAPL",
        "15 mins",
        durations=["1 M", "1 Y"],
        client_factory=lambda: fake,
        sleep_fn=lambda _seconds: None,
    )

    assert result["_status"] == StepStatus.FAILED.value
    assert fake.requested_durations == []
