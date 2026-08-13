"""Schritt A.1/A.2: Ist der CDP-Debug-Port ueberhaupt erreichbar?

Das ist die Grundvoraussetzung fuer jeden weiteren Schritt. Ein Fehlschlag
hier beantwortet A.1 direkt mit "nein, so nicht" und macht alle folgenden
Schritte automatisch NOT_APPLICABLE (siehe cli.py-Orchestrierung).
"""

from __future__ import annotations

from typing import Any

from ..cdp_client import CdpTarget, list_targets
from ..config import CdpConfig
from .base import StepStatus

STEP_ID = "cdp_reachability"
TITLE = "CDP-Debug-Port erreichbar"


async def run(config: CdpConfig) -> dict[str, Any]:
    targets = list_targets(config)

    if not targets:
        return {
            "_status": StepStatus.FAILED.value,
            "reason": (
                f"CDP-Endpunkt {config.http_base_url} war erreichbar, meldet aber "
                f"keine Debug-Ziele. Laeuft die Zielanwendung wirklich?"
            ),
        }

    return {
        "endpoint": config.http_base_url,
        "target_count": len(targets),
        "targets": [_target_summary(t) for t in targets],
    }


def _target_summary(target: CdpTarget) -> dict[str, str]:
    return {"id": target.id, "title": target.title, "type": target.type, "url": target.url}
