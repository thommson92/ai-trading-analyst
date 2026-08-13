"""Schritt C.9/C.10: Ist das persoenliche Chartlayout eindeutig erkennbar,
und laesst sich verifizieren, dass wirklich dieses Layout aktiv ist (nicht
nur irgendein Chart)?

Ohne ``expected_layout`` liefert der Schritt nur eine unverifizierte
Erkennung (``verified: false``) -- reine Erkennung beantwortet C.9 aber
nicht C.10. Erst der Abgleich gegen einen erwarteten Namen/eine erwartete
Kennung beantwortet beide Fragen zusammen.
"""

from __future__ import annotations

from typing import Any

from ..cdp_client import CdpSession
from .base import StepStatus

STEP_ID = "layout_detection"
TITLE = "Chartlayout eindeutig erkannt und verifiziert"


async def run(
    session: CdpSession, probe_js: str | None, expected_layout: str | None = None
) -> dict[str, Any]:
    if probe_js is None:
        return {
            "_status": StepStatus.INCONCLUSIVE.value,
            "reason": "Keine Sonde konfiguriert (TVCDP_PROBE_LAYOUT_NAME_JS).",
        }

    detected = await session.evaluate(probe_js)

    if not isinstance(detected, str) or not detected:
        return {
            "_status": StepStatus.INCONCLUSIVE.value,
            "reason": "Sonde lieferte keinen nicht-leeren String als Layoutbezeichner.",
            "raw_type": type(detected).__name__,
        }

    if expected_layout is None:
        return {
            "detected_layout": detected,
            "verified": False,
            "note": "Kein erwartetes Layout angegeben -- nur Erkennung, keine Verifikation.",
        }

    if detected == expected_layout:
        return {"detected_layout": detected, "expected_layout": expected_layout, "verified": True}

    return {
        "_status": StepStatus.FAILED.value,
        "detected_layout": detected,
        "expected_layout": expected_layout,
        "verified": False,
    }
