from __future__ import annotations

from typing import Any, Protocol

from ..config import IbkrSpikeConfig
from ..timeframe import Bar, aggregate_to_195_minutes
from .base import StepStatus

STEP_ID = "historical_bars"
TITLE = "Historische Bars und 195-Minuten-Aggregation"

# Nur native Bar-Groessen, die 195 Minuten ohne Rest teilen, sind fuer die
# geplante Aggregation geeignet (siehe timeframe.aggregate_to_195_minutes).
SUPPORTED_BAR_SIZES = {
    "1 min": 1,
    "3 mins": 3,
    "5 mins": 5,
    "13 mins": 13,
    "15 mins": 15,
    "39 mins": 39,
    "65 mins": 65,
}


class HistoricalDataClient(Protocol):
    def connect(self, host: str, port: int, client_id: int, timeout_seconds: float) -> None: ...

    def is_connected(self) -> bool: ...

    def qualify_stock(self, symbol: str) -> Any: ...

    def historical_bars(
        self, contract: Any, duration_str: str, bar_size: str, use_rth: bool
    ) -> list[dict[str, Any]]: ...

    def disconnect(self) -> None: ...


def default_client_factory() -> HistoricalDataClient:
    from ..ibkr_client import IbAsyncClient

    return IbAsyncClient()


def _candle_to_dict(candle: Any) -> dict[str, Any]:
    return {
        "session_date": candle.session_date.isoformat(),
        "bucket_index": candle.bucket_index,
        "start": candle.start.isoformat(),
        "end": candle.end.isoformat(),
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
        "bar_count": candle.bar_count,
        "is_complete": candle.is_complete,
    }


def run(
    config: IbkrSpikeConfig,
    symbol: str,
    duration_str: str,
    bar_size: str,
    use_rth: bool = True,
    client_factory: Any = default_client_factory,
) -> dict[str, Any]:
    native_bar_minutes = SUPPORTED_BAR_SIZES.get(bar_size)
    if native_bar_minutes is None:
        return {
            "_status": StepStatus.FAILED.value,
            "symbol": symbol,
            "error": (
                f"bar_size {bar_size!r} ist nicht in der unterstuetzten Liste "
                f"({sorted(SUPPORTED_BAR_SIZES)}) -- 195 Minuten muessen ohne "
                "Rest teilbar sein."
            ),
        }

    client = client_factory()
    try:
        client.connect(config.host, config.port, config.client_id, config.timeout_seconds)
    except Exception as exc:
        return {
            "_status": StepStatus.FAILED.value,
            "symbol": symbol,
            "error": f"{type(exc).__name__}: {exc}",
        }

    try:
        if not client.is_connected():
            return {
                "_status": StepStatus.FAILED.value,
                "symbol": symbol,
                "error": "Verbindung nicht hergestellt (is_connected() == False)",
            }
        return _fetch_and_aggregate(
            client, symbol, duration_str, bar_size, use_rth, native_bar_minutes
        )
    finally:
        client.disconnect()


def _fetch_and_aggregate(
    client: HistoricalDataClient,
    symbol: str,
    duration_str: str,
    bar_size: str,
    use_rth: bool,
    native_bar_minutes: int,
) -> dict[str, Any]:
    try:
        contract = client.qualify_stock(symbol)
    except Exception as exc:
        return {
            "_status": StepStatus.FAILED.value,
            "symbol": symbol,
            "error": f"Kontrakt-Aufloesung fehlgeschlagen: {type(exc).__name__}: {exc}",
        }

    try:
        raw_bars = client.historical_bars(contract, duration_str, bar_size, use_rth)
    except Exception as exc:
        return {
            "_status": StepStatus.FAILED.value,
            "symbol": symbol,
            "error": f"Historische Daten nicht abrufbar: {type(exc).__name__}: {exc}",
        }

    if not raw_bars:
        return {
            "_status": StepStatus.INCONCLUSIVE.value,
            "symbol": symbol,
            "reason": "Keine Bars zurueckgegeben",
        }

    bars = [
        Bar(
            timestamp=raw["timestamp"],
            open=raw["open"],
            high=raw["high"],
            low=raw["low"],
            close=raw["close"],
            volume=raw["volume"],
        )
        for raw in raw_bars
    ]

    result = aggregate_to_195_minutes(bars, native_bar_minutes=native_bar_minutes)
    complete = [c for c in result.candles if c.is_complete]

    return {
        "_status": StepStatus.OK.value,
        "symbol": symbol,
        "duration_str": duration_str,
        "bar_size": bar_size,
        "use_rth": use_rth,
        "raw_bar_count": len(bars),
        "bars_outside_session_count": len(result.bars_outside_session),
        "aggregated_candle_count": len(result.candles),
        "complete_candle_count": len(complete),
        "incomplete_candle_count": len(result.candles) - len(complete),
        "candles": [_candle_to_dict(c) for c in result.candles],
    }
