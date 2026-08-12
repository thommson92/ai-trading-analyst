"""Schritt A.3: Laesst sich eine bestehende authentifizierte Sitzung nutzen,
ohne Zugangsdaten selbst auszulesen oder zu speichern?

Bewusste Sicherheitsentscheidung: Dieser Schritt liest niemals Cookies,
LocalStorage oder sonstige Session-Artefakte. Er wertet ausschliesslich ein
vom Aufrufer konfiguriertes JavaScript-Praedikat aus, das selbst im
Seitenkontext entscheidet, ob eine UI erscheint, die nur eingeloggten
Nutzern angezeigt wird (z. B. ein Benutzermenue) -- das Ergebnis ist ein
Wahrheitswert, nie ein Zugangsdaten-Inhalt.
"""

from __future__ import annotations

from typing import Any

from ..cdp_client import CdpSession
from .base import StepStatus

STEP_ID = "session_check"
TITLE = "Bestehende authentifizierte Sitzung nutzbar"


async def run(session: CdpSession, probe_js: str | None) -> dict[str, Any]:
    if probe_js is None:
        return {
            "_status": StepStatus.INCONCLUSIVE.value,
            "reason": (
                "Keine Sonde konfiguriert (TVCDP_PROBE_SESSION_AUTHENTICATED_JS). "
                "Muss manuell ermittelt werden, z. B. ueber ein Element, das nur "
                "im eingeloggten Zustand sichtbar ist."
            ),
        }

    value = await session.evaluate(probe_js)

    if not isinstance(value, bool):
        return {
            "_status": StepStatus.INCONCLUSIVE.value,
            "reason": "Sonde lieferte keinen eindeutigen Wahrheitswert.",
            "probe_returned_type": type(value).__name__,
        }

    if value:
        return {"authenticated": True}
    return {"_status": StepStatus.FAILED.value, "authenticated": False}
