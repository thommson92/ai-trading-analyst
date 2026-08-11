from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from ..config import IbkrSpikeConfig
from ..timeframe import Bar, aggregate_to_195_minutes
from .base import StepStatus
from .step_historical_bars import SUPPORTED_BAR_SIZES, HistoricalDataClient, default_client_factory

STEP_ID = "multi_symbol"
TITLE = "Mehrsymbol-Durchlauf -- Laufzeit, Fehlerrate, Stabilitaet"

DEFAULT_SYMBOLS = [
    "AAPL",
    "MSFT",
    "AMZN",
    "GOOGL",
    "META",
    "NVDA",
    "TSLA",
    "JPM",
    "XOM",
    "UNH",
]


def run(
    config: IbkrSpikeConfig,
    symbols: list[str] | None = None,
    duration_str: str = "5 D",
    bar_size: str = "15 mins",
    use_rth: bool = True,
    client_factory: Any = default_client_factory,
    time_fn: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Durchlaeuft mehrere Symbole ueber **eine** TWS-Verbindung (wie ein
    produktiver Watchlist-Lauf es taete) und misst je Symbol Laufzeit und
    Erfolg -- analog zum Referenzvergleich aus Gate G2
    (`spikes/tradingview-cdp`, Mehrsymbol-Schritt). Ein fehlschlagendes
    Symbol bricht den Durchlauf nicht ab, sondern wird einzeln vermerkt.
    """
    symbols = symbols if symbols is not None else DEFAULT_SYMBOLS
    native_bar_minutes = SUPPORTED_BAR_SIZES.get(bar_size)
    if native_bar_minutes is None:
        return {
            "_status": StepStatus.FAILED.value,
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
            "error": f"{type(exc).__name__}: {exc}",
        }

    try:
        if not client.is_connected():
            return {
                "_status": StepStatus.FAILED.value,
                "error": "Verbindung nicht hergestellt (is_connected() == False)",
            }

        run_started = time_fn()
        per_symbol = [
            _run_one_symbol(
                client, symbol, duration_str, bar_size, use_rth, native_bar_minutes, time_fn
            )
            for symbol in symbols
        ]
        total_duration = time_fn() - run_started

        by_status = dict.fromkeys((s.value for s in StepStatus), 0)
        for entry in per_symbol:
            by_status[entry["status"]] += 1

        return {
            "_status": StepStatus.OK.value,
            "symbol_count": len(symbols),
            "duration_str": duration_str,
            "bar_size": bar_size,
            "use_rth": use_rth,
            "total_duration_seconds": total_duration,
            "success_count": by_status[StepStatus.OK.value],
            "failed_count": by_status[StepStatus.FAILED.value],
            "inconclusive_count": by_status[StepStatus.INCONCLUSIVE.value],
            "results": per_symbol,
        }
    finally:
        client.disconnect()


def _run_one_symbol(
    client: HistoricalDataClient,
    symbol: str,
    duration_str: str,
    bar_size: str,
    use_rth: bool,
    native_bar_minutes: int,
    time_fn: Callable[[], float],
) -> dict[str, Any]:
    started = time_fn()

    def elapsed() -> float:
        return time_fn() - started

    try:
        contract = client.qualify_stock(symbol)
    except Exception as exc:
        return {
            "symbol": symbol,
            "status": StepStatus.FAILED.value,
            "duration_seconds": elapsed(),
            "error": f"Kontrakt-Aufloesung fehlgeschlagen: {type(exc).__name__}: {exc}",
        }

    try:
        raw_bars = client.historical_bars(contract, duration_str, bar_size, use_rth)
    except Exception as exc:
        return {
            "symbol": symbol,
            "status": StepStatus.FAILED.value,
            "duration_seconds": elapsed(),
            "error": f"Historische Daten nicht abrufbar: {type(exc).__name__}: {exc}",
        }

    if not raw_bars:
        return {
            "symbol": symbol,
            "status": StepStatus.INCONCLUSIVE.value,
            "duration_seconds": elapsed(),
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
        "symbol": symbol,
        "status": StepStatus.OK.value,
        "duration_seconds": elapsed(),
        "raw_bar_count": len(bars),
        "complete_candle_count": len(complete),
    }
