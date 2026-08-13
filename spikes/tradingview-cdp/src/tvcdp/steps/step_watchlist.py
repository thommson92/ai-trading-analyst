"""Schritt B: Koennen vorhandene Watchlists strukturiert ausgelesen werden?

Erwartete Form des konfigurierten Sondenergebnisses (JSON-serialisierbar,
von der Sonde selbst im Seitenkontext zusammengestellt):

    [{"name": "Meine Watchlist", "symbols": [{"symbol": "AAPL", "exchange": "NASDAQ"}, ...]}, ...]

Der Schritt vertraut dieser Form nicht blind -- eine Sonde, die etwas
anderes liefert, ist ein diagnostisch wertvolles INCONCLUSIVE, kein blinder
Absturz.
"""

from __future__ import annotations

import time
from typing import Any

from ..cdp_client import CdpSession
from .base import StepStatus

STEP_ID = "watchlist"
TITLE = "Watchlists strukturiert auslesbar"


def _validate_watchlists(raw: Any) -> list[dict[str, Any]] | None:
    if not isinstance(raw, list):
        return None
    validated: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict) or "name" not in entry or "symbols" not in entry:
            return None
        symbols = entry["symbols"]
        if not isinstance(symbols, list):
            return None
        for symbol_entry in symbols:
            if (
                not isinstance(symbol_entry, dict)
                or "symbol" not in symbol_entry
                or "exchange" not in symbol_entry
            ):
                return None
        validated.append(entry)
    return validated


async def run(session: CdpSession, probe_js: str | None) -> dict[str, Any]:
    if probe_js is None:
        return {
            "_status": StepStatus.INCONCLUSIVE.value,
            "reason": "Keine Sonde konfiguriert (TVCDP_PROBE_WATCHLIST_JS).",
        }

    started = time.monotonic()
    raw = await session.evaluate(probe_js)
    elapsed_seconds = time.monotonic() - started

    watchlists = _validate_watchlists(raw)
    if watchlists is None:
        return {
            "_status": StepStatus.INCONCLUSIVE.value,
            "reason": (
                "Sonde lieferte ein Ergebnis, aber nicht in der erwarteten Form "
                "(Liste von {name, symbols:[{symbol, exchange}]})."
            ),
            "raw_type": type(raw).__name__,
            "elapsed_seconds": round(elapsed_seconds, 3),
        }

    return {
        "watchlist_count": len(watchlists),
        "watchlist_names": [w["name"] for w in watchlists],
        "total_symbol_count": sum(len(w["symbols"]) for w in watchlists),
        "elapsed_seconds": round(elapsed_seconds, 3),
    }
