"""Schritt D.12: Ist der Chart zuverlaessig auf den 195-Minuten-Timeframe
eingestellt bzw. laesst sich der eingestellte Timeframe eindeutig auslesen?
"""

from __future__ import annotations

from typing import Any

from ..cdp_client import CdpSession
from .base import StepStatus

STEP_ID = "timeframe_195"
TITLE = "195-Minuten-Timeframe erkannt"

_EXPECTED_MINUTES = 195


async def run(session: CdpSession, probe_js: str | None) -> dict[str, Any]:
    if probe_js is None:
        return {
            "_status": StepStatus.INCONCLUSIVE.value,
            "reason": "Keine Sonde konfiguriert (TVCDP_PROBE_TIMEFRAME_MINUTES_JS).",
        }

    detected = await session.evaluate(probe_js)

    if not isinstance(detected, int | float):
        return {
            "_status": StepStatus.INCONCLUSIVE.value,
            "reason": "Sonde lieferte keinen numerischen Wert.",
            "raw_type": type(detected).__name__,
        }

    if detected == _EXPECTED_MINUTES:
        return {"detected_minutes": detected}

    return {
        "_status": StepStatus.FAILED.value,
        "detected_minutes": detected,
        "expected_minutes": _EXPECTED_MINUTES,
    }
