"""Schritt G.20/G.21: Koennen mehrere Aktien automatisiert nacheinander
verarbeitet werden, und wie sieht die Performance dabei aus?

Simuliert einen realen Watchlist-Durchlauf, *ohne* die produktive
Screener-Logik aufzurufen (Nutzervorgabe) -- gemessen wird ausschliesslich,
ob und wie schnell sich Symbole automatisiert durchschalten und auslesen
lassen.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from typing import Any

from ..cdp_client import CdpProtocolError, CdpSession
from .base import StepStatus

STEP_ID = "multi_symbol_run"
TITLE = "Mehrsymbol-Durchlauf und Performance"

_POLL_INTERVAL_SECONDS = 0.5


async def _wait_for_settled_values(
    session: CdpSession,
    read_values_js: str,
    previous_values: Any,
    timeout_seconds: float,
) -> tuple[bool, Any, str | None]:
    """Pollt ``read_values_js``, bis ein vom vorherigen Symbol verschiedener
    Wert ohne Fehler zurueckkommt, oder das Timeout erreicht ist.

    ``getSymbol()`` als Bereitschaftssignal wurde auf dem Windows-Zielserver
    empirisch widerlegt: es aktualisiert sich synchron mit dem Wechsel-Aufruf,
    unabhaengig davon, ob die Study-Daten (RSI, EMA, ...) schon nachgezogen
    sind -- ein Poll darauf war also immer sofort "erfolgreich", ohne etwas
    zu pruefen. Ein ``CdpProtocolError`` waehrend des Uebergangs (Studies
    voruebergehend nicht definiert, waehrend TradingView sie fuer das neue
    Symbol neu aufbaut) gilt als "noch nicht bereit", nicht als Fehlschlag."""
    deadline = time.monotonic() + timeout_seconds
    last_error: str | None = None
    while True:
        try:
            values = await session.evaluate(read_values_js)
            if values != previous_values:
                return True, values, None
            last_error = "Wert ist unveraendert gegenueber dem vorherigen Symbol"
        except CdpProtocolError as exc:
            last_error = str(exc)
        if time.monotonic() >= deadline:
            return False, None, last_error
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)


async def run(
    session: CdpSession,
    symbols: list[str],
    change_symbol_js_template: str | None,
    read_values_js: str | None,
    switch_timeout_seconds: float = 0.0,
) -> dict[str, Any]:
    """Liest Werte erst, wenn sie sich (fehlerfrei) vom vorherigen Symbol
    unterscheiden -- statt sich auf einen festen Sleep oder auf ``getSymbol()``
    als Bereitschaftssignal zu verlassen (beide empirisch auf dem
    Windows-Zielserver als unzureichend widerlegt, siehe REPORT.md
    Abschnitt 10). Ohne ``switch_timeout_seconds > 0`` wird nur einmal
    gelesen, ungeprueft (``symbol_switch_verified: None``)."""
    if not symbols:
        return {
            "_status": StepStatus.INCONCLUSIVE.value,
            "reason": "Keine Symbole zum Testen angegeben (SpikeConfig.watchlist_probe_names).",
        }
    if change_symbol_js_template is None:
        return {
            "_status": StepStatus.INCONCLUSIVE.value,
            "reason": "Keine Sonde konfiguriert (TVCDP_PROBE_CHANGE_SYMBOL_JS_TEMPLATE).",
        }

    # Ausgangswert VOR dem ersten Symbolwechsel lesen. Ohne das wuerde das
    # allererste Symbol ungeprueft akzeptiert (nichts zum Vergleichen
    # vorhanden) -- auf dem Windows-Zielserver empirisch bestaetigt: die
    # CDP-Session eines neuen Prozesses zeigte noch den Altbestand des
    # zuletzt in einem frueheren Lauf gesetzten Symbols, und das erste neue
    # Symbol wurde faelschlich damit "bestaetigt", weil der Vergleich gegen
    # None lief statt gegen den tatsaechlich sichtbaren Altwert.
    previous_values: Any = None
    if switch_timeout_seconds > 0 and read_values_js is not None:
        try:
            previous_values = await session.evaluate(read_values_js)
        except Exception:
            previous_values = None

    per_symbol: list[dict[str, Any]] = []
    for symbol in symbols:
        started = time.monotonic()
        entry: dict[str, Any] = {"symbol": symbol}
        try:
            await session.evaluate(change_symbol_js_template.format(symbol=symbol))
            if read_values_js is not None:
                if switch_timeout_seconds > 0:
                    settled, values, error = await _wait_for_settled_values(
                        session, read_values_js, previous_values, switch_timeout_seconds
                    )
                    entry["symbol_switch_verified"] = settled
                    if not settled:
                        entry["succeeded"] = False
                        entry["error"] = (
                            f"Werte fuer '{symbol}' nach {switch_timeout_seconds}s nicht "
                            f"bestaetigt (letzter Zustand: {error}) -- nicht gelesen, um "
                            "keinen veralteten Wert zu melden."
                        )
                        entry["elapsed_seconds"] = round(time.monotonic() - started, 3)
                        per_symbol.append(entry)
                        continue
                    entry["values"] = values
                    previous_values = values
                else:
                    entry["symbol_switch_verified"] = None
                    entry["values"] = await session.evaluate(read_values_js)
                    previous_values = entry["values"]
            entry["succeeded"] = True
        except Exception as exc:
            entry["succeeded"] = False
            entry["error"] = f"{type(exc).__name__}: {exc}"
        entry["elapsed_seconds"] = round(time.monotonic() - started, 3)
        per_symbol.append(entry)

    durations = [entry["elapsed_seconds"] for entry in per_symbol]
    successes = [entry for entry in per_symbol if entry["succeeded"]]
    error_count = len(per_symbol) - len(successes)

    performance = {
        "symbol_count": len(symbols),
        "average_seconds": round(statistics.mean(durations), 3),
        "median_seconds": round(statistics.median(durations), 3),
        "slowest_seconds": round(max(durations), 3),
        "error_count": error_count,
        "error_rate": round(error_count / len(symbols), 3),
    }

    status = StepStatus.PASSED if error_count == 0 else StepStatus.INCONCLUSIVE
    return {"_status": status.value, "performance": performance, "per_symbol": per_symbol}
