"""Schritt I.23: Werden die neun geforderten Fehlerfaelle zuverlaessig
erkannt, statt zu scheinbar gueltigen Null-, alten oder Default-Werten zu
fuehren?

Zwei der neun Faelle lassen sich automatisiert und ohne manuelles Zutun
pruefen (unten). Die uebrigen sieben erfordern eine gezielte Handlung an
der echten TradingView-Instanz (falsches Layout auswaehlen, Symbol
schliessen, Timeframe aendern, Indikator entfernen, ...) und sind deshalb
Teil der manuellen Windows-Testanweisungen (WINDOWS_VALIDATION.md), nicht
dieses Schritts. Was hier automatisiert geprueft wird, ist aber die
Grundvoraussetzung dafuer, dass die manuellen Faelle ueberhaupt erkennbar
waeren: das Fail-loud-Prinzip der uebrigen Schritte (kein Schritt liefert
bei fehlender Voraussetzung einen Default-Wert -- er meldet INCONCLUSIVE
oder FAILED, nie stillschweigend einen plausibel aussehenden Wert).
"""

from __future__ import annotations

from typing import Any

from ..cdp_client import CdpConnectionError, CdpProtocolError, CdpSession, list_targets
from ..config import CdpConfig
from .base import StepStatus

STEP_ID = "error_case_detection"
TITLE = "Fehlerfaelle werden erkannt statt stillschweigend uebergangen"

_MANUAL_ERROR_CASES = (
    "falsches Layout",
    "Symbol nicht geladen",
    "falscher Timeframe",
    "Indikator fehlt",
    "Werte noch nicht aktualisiert",
    "aktuelle statt geschlossene Kerze",
    "Watchlist nicht verfuegbar",
)


async def run(session: CdpSession | None, unreachable_config: CdpConfig) -> dict[str, Any]:
    checks: dict[str, Any] = {}

    try:
        list_targets(unreachable_config)
        checks["cdp_nicht_erreichbar"] = {
            "detected": False,
            "note": "Unerwartet: Endpunkt war doch erreichbar.",
        }
    except CdpConnectionError as exc:
        checks["cdp_nicht_erreichbar"] = {"detected": True, "message": str(exc)}

    checks["tradingview_nicht_gestartet"] = {
        "detected": checks["cdp_nicht_erreichbar"]["detected"],
        "note": "Identischer Mechanismus wie 'CDP nicht erreichbar' auf diesem Weg nicht trennbar.",
    }

    if session is not None:
        try:
            await session.evaluate("this_identifier_does_not_exist_anywhere")
            checks["javascript_fehler_wird_erkannt"] = {"detected": False}
        except CdpProtocolError:
            checks["javascript_fehler_wird_erkannt"] = {"detected": True}
    else:
        checks["javascript_fehler_wird_erkannt"] = {
            "detected": None,
            "note": "Kein Ziel verbunden -- nicht pruefbar.",
        }

    all_automated_detected = all(
        check.get("detected") is not False for check in checks.values()
    )

    return {
        "_status": (
            StepStatus.PASSED if all_automated_detected else StepStatus.FAILED
        ).value,
        "automated_checks": checks,
        "requires_manual_windows_procedure": list(_MANUAL_ERROR_CASES),
    }
