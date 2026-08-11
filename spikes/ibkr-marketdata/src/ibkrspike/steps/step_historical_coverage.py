from __future__ import annotations

import time
from typing import Any

from ..config import IbkrSpikeConfig
from .base import StepStatus
from .step_historical_bars import HistoricalDataClient, default_client_factory

STEP_ID = "historical_coverage"
TITLE = "Historische Abdeckung und Pacing-Verhalten"

DEFAULT_DURATIONS = ["1 M", "3 M", "6 M", "1 Y", "2 Y", "5 Y"]
DEFAULT_PACING_DELAY_SECONDS = 2.0


def run(
    config: IbkrSpikeConfig,
    symbol: str,
    bar_size: str,
    durations: list[str] | None = None,
    pacing_delay_seconds: float = DEFAULT_PACING_DELAY_SECONDS,
    client_factory: Any = default_client_factory,
    sleep_fn: Any = time.sleep,
) -> dict[str, Any]:
    """Fragt dieselbe Bar-Groesse mit steigender Historientiefe ab.

    Jede Anfrage ist ein eigener, gegen IBKR ausgefuehrter Versuch -- die
    tatsaechlichen Pacing-/Duration-Limits werden empirisch ermittelt statt
    aus der Dokumentation uebernommen, da sie sich zwischen Kontotypen und
    IBKR-Versionen unterscheiden koennen. Zwischen den Anfragen liegt eine
    konfigurierbare Pause, um Pacing-Verstoesse (siehe IBKR-Dokumentation:
    max. 60 historische Anfragen je 10 Minuten) zu vermeiden.
    """
    durations = durations if durations is not None else DEFAULT_DURATIONS

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

        try:
            contract = client.qualify_stock(symbol)
        except Exception as exc:
            return {
                "_status": StepStatus.FAILED.value,
                "symbol": symbol,
                "error": f"Kontrakt-Aufloesung fehlgeschlagen: {type(exc).__name__}: {exc}",
            }

        per_duration: list[dict[str, Any]] = []
        for index, duration_str in enumerate(durations):
            if index > 0:
                sleep_fn(pacing_delay_seconds)
            per_duration.append(_probe_duration(client, contract, duration_str, bar_size))

        return {
            "_status": StepStatus.OK.value,
            "symbol": symbol,
            "bar_size": bar_size,
            "durations_tested": durations,
            "results": per_duration,
        }
    finally:
        client.disconnect()


def _probe_duration(
    client: HistoricalDataClient,
    contract: Any,
    duration_str: str,
    bar_size: str,
) -> dict[str, Any]:
    try:
        raw_bars = client.historical_bars(contract, duration_str, bar_size, use_rth=True)
    except Exception as exc:
        return {
            "duration_str": duration_str,
            "status": StepStatus.FAILED.value,
            "error": f"{type(exc).__name__}: {exc}",
        }

    if not raw_bars:
        return {
            "duration_str": duration_str,
            "status": StepStatus.INCONCLUSIVE.value,
            "reason": "Keine Bars zurueckgegeben",
        }

    timestamps = [bar["timestamp"] for bar in raw_bars]
    return {
        "duration_str": duration_str,
        "status": StepStatus.OK.value,
        "raw_bar_count": len(raw_bars),
        "earliest_timestamp": min(timestamps).isoformat(),
        "latest_timestamp": max(timestamps).isoformat(),
    }
