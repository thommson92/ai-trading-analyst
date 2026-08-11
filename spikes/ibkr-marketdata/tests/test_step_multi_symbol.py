from datetime import datetime, timedelta
from typing import Any

from ibkrspike.config import IbkrSpikeConfig
from ibkrspike.steps import step_multi_symbol
from ibkrspike.steps.base import StepStatus
from ibkrspike.timeframe import EXCHANGE_TZ


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


class FakeMultiSymbolClient:
    def __init__(
        self,
        *,
        bars_by_symbol: dict[str, list[dict[str, Any]]] | None = None,
        errors_by_symbol: dict[str, Exception] | None = None,
        connect_error: Exception | None = None,
    ) -> None:
        self._bars_by_symbol = bars_by_symbol or {}
        self._errors_by_symbol = errors_by_symbol or {}
        self._connect_error = connect_error
        self._connected = False
        self.disconnected = False
        self.requested_symbols: list[str] = []

    def connect(self, host: str, port: int, client_id: int, timeout_seconds: float) -> None:
        if self._connect_error is not None:
            raise self._connect_error
        self._connected = True

    def is_connected(self) -> bool:
        return self._connected

    def qualify_stock(self, symbol: str) -> Any:
        self.requested_symbols.append(symbol)
        if symbol in self._errors_by_symbol and "qualify" in str(self._errors_by_symbol[symbol]):
            raise self._errors_by_symbol[symbol]
        return object()

    def historical_bars(
        self, contract: Any, duration_str: str, bar_size: str, use_rth: bool
    ) -> list[dict[str, Any]]:
        symbol = self.requested_symbols[-1]
        if symbol in self._errors_by_symbol:
            raise self._errors_by_symbol[symbol]
        return self._bars_by_symbol.get(symbol, [])

    def disconnect(self) -> None:
        self.disconnected = True
        self._connected = False


def _config() -> IbkrSpikeConfig:
    return IbkrSpikeConfig(
        host="127.0.0.1", port=7496, client_id=17, timeout_seconds=10.0, account_id=None
    )


def _time_fn() -> Any:
    values = iter(float(i) for i in range(1000))

    def _next() -> float:
        return next(values)

    return _next


def test_alle_symbole_erfolgreich_liefert_aggregierte_zaehlung() -> None:
    fake = FakeMultiSymbolClient(bars_by_symbol={"AAPL": _bars(13), "MSFT": _bars(13)})

    result = step_multi_symbol.run(
        _config(),
        ["AAPL", "MSFT"],
        "1 D",
        "15 mins",
        client_factory=lambda: fake,
        time_fn=_time_fn(),
    )

    assert result["_status"] == StepStatus.OK.value
    assert result["symbol_count"] == 2
    assert result["success_count"] == 2
    assert result["failed_count"] == 0
    results_by_symbol = {r["symbol"]: r for r in result["results"]}
    assert results_by_symbol["AAPL"]["status"] == StepStatus.OK.value
    assert results_by_symbol["AAPL"]["complete_candle_count"] == 1
    assert fake.disconnected is True


def test_ein_fehlschlagendes_symbol_bricht_den_lauf_nicht_ab() -> None:
    fake = FakeMultiSymbolClient(
        bars_by_symbol={"AAPL": _bars(13)},
        errors_by_symbol={"BADSYM": RuntimeError("no security definition found")},
    )

    result = step_multi_symbol.run(
        _config(),
        ["AAPL", "BADSYM"],
        "1 D",
        "15 mins",
        client_factory=lambda: fake,
        time_fn=_time_fn(),
    )

    assert result["_status"] == StepStatus.OK.value
    assert result["success_count"] == 1
    assert result["failed_count"] == 1
    results_by_symbol = {r["symbol"]: r for r in result["results"]}
    assert results_by_symbol["BADSYM"]["status"] == StepStatus.FAILED.value
    # Beide Symbole wurden trotz Fehlschlag des ersten tatsaechlich angefragt.
    assert fake.requested_symbols == ["AAPL", "BADSYM"]


def test_leere_bar_liste_fuer_ein_symbol_ist_inconclusive() -> None:
    fake = FakeMultiSymbolClient(bars_by_symbol={"AAPL": []})

    result = step_multi_symbol.run(
        _config(), ["AAPL"], "1 D", "15 mins", client_factory=lambda: fake, time_fn=_time_fn()
    )

    assert result["results"][0]["status"] == StepStatus.INCONCLUSIVE.value
    assert result["inconclusive_count"] == 1


def test_unbekannte_bar_groesse_wird_ohne_verbindungsversuch_abgelehnt() -> None:
    fake = FakeMultiSymbolClient()

    result = step_multi_symbol.run(
        _config(), ["AAPL"], "1 D", "30 mins", client_factory=lambda: fake, time_fn=_time_fn()
    )

    assert result["_status"] == StepStatus.FAILED.value
    assert fake._connected is False


def test_verbindungsfehler_liefert_failed() -> None:
    fake = FakeMultiSymbolClient(connect_error=ConnectionRefusedError("nope"))

    result = step_multi_symbol.run(
        _config(), ["AAPL"], "1 D", "15 mins", client_factory=lambda: fake, time_fn=_time_fn()
    )

    assert result["_status"] == StepStatus.FAILED.value
