"""Schritt E.15/E.16: Koennen RSI 14, RSI-MA SMA 14, EMA5 und EMA20
strukturiert und maschinenlesbar ausgelesen werden?

Jeder der vier Werte hat eine eigene, unabhaengig konfigurierbare Sonde --
es ist plausibel, dass manche Werte z. B. ueber interne JS-Objekte
erreichbar sind und andere nur ueber den DOM (Frage E.16/E.17). Der Schritt
haelt deshalb je Indikator fest, ob und wie er gewonnen wurde, statt nur
ein einzelnes Gesamtergebnis zu melden.
"""

from __future__ import annotations

from typing import Any, NamedTuple

from ..cdp_client import CdpSession
from .base import StepStatus

STEP_ID = "indicators"
TITLE = "RSI/RSI-MA/EMA5/EMA20 auslesbar"


class _IndicatorProbe(NamedTuple):
    name: str
    expression: str | None


async def _read_one(session: CdpSession, probe: _IndicatorProbe) -> dict[str, Any]:
    if probe.expression is None:
        return {"status": "not_configured"}

    value = await session.evaluate(probe.expression)
    if not isinstance(value, int | float):
        return {"status": "invalid", "raw_type": type(value).__name__}
    return {"status": "ok", "value": float(value)}


async def run(
    session: CdpSession,
    rsi_js: str | None,
    rsi_ma_js: str | None,
    ema5_js: str | None,
    ema20_js: str | None,
) -> dict[str, Any]:
    probes = (
        _IndicatorProbe("rsi", rsi_js),
        _IndicatorProbe("rsi_ma", rsi_ma_js),
        _IndicatorProbe("ema5", ema5_js),
        _IndicatorProbe("ema20", ema20_js),
    )

    if all(probe.expression is None for probe in probes):
        return {
            "_status": StepStatus.INCONCLUSIVE.value,
            "reason": "Keine einzige Indikator-Sonde konfiguriert.",
        }

    results = {probe.name: await _read_one(session, probe) for probe in probes}
    all_ok = all(r["status"] == "ok" for r in results.values())

    return {
        "_status": (StepStatus.PASSED if all_ok else StepStatus.INCONCLUSIVE).value,
        "indicators": results,
    }
