"""Schritt B.5/A.3-Vorstufe: Welches der CDP-Ziele ist tatsaechlich
TradingView Desktop?

Ein Debug-Port kann mehrere Ziele melden (mehrere Fenster, Hintergrund-
Renderer-Prozesse). Dieser Schritt filtert nach einem konfigurierbaren
Titel-/URL-Muster, statt anzunehmen, dass immer genau ein Ziel existiert.
"""

from __future__ import annotations

from typing import Any

from ..cdp_client import CdpTarget
from .base import StepStatus

STEP_ID = "target_discovery"
TITLE = "TradingView-Ziel unter den CDP-Zielen identifiziert"


async def run(targets: list[CdpTarget], title_pattern: str) -> dict[str, Any]:
    if not targets:
        return {
            "_status": StepStatus.FAILED.value,
            "reason": "Keine CDP-Ziele vorhanden -- CDP-Erreichbarkeit ist bereits gescheitert.",
        }

    pattern = title_pattern.lower()
    matches = [t for t in targets if pattern in t.title.lower() or pattern in t.url.lower()]

    if not matches:
        return {
            "_status": StepStatus.INCONCLUSIVE.value,
            "reason": (
                f"Kein Ziel passt zum Muster '{title_pattern}'. Verfuegbare Zieltitel "
                f"unten pruefen und ggf. TVCDP_TARGET_TITLE_PATTERN anpassen."
            ),
            "available_titles": [t.title for t in targets],
        }

    return {
        "matched_target_id": matches[0].id,
        "matched_title": matches[0].title,
        "match_count": len(matches),
        "all_match_ids": [t.id for t in matches],
    }
