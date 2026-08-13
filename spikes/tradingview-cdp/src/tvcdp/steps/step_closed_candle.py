"""Schritt D.13/D.14: Laesst sich eindeutig feststellen, welche Kerze zuletzt
vollstaendig geschlossen wurde -- und wird eine noch laufende Kerze
korrekt als *nicht* geschlossen erkannt?

Das ist der schaerfste Einzelpunkt im gesamten Spike (Projektplan R9): die
Produktivanwendung darf niemals auf einer laufenden Kerze screenen. Ein
falsch-positives ``is_closed`` waere kein Randfall, sondern ein stiller
Fachfehler mit plausibel aussehenden, aber falschen Signalen. Deshalb
prueft dieser Schritt zwei unabhaengige Bedingungen, nicht nur eine:

1. Die Sonde selbst meldet ``is_closed: true``.
2. Der gemeldete Timestamp liegt plausibel in der Vergangenheit (eine
   "geschlossene" Kerze mit einem Timestamp in der Zukunft waere ein
   Widerspruch in sich und wird als Fehldiagnose behandelt, nicht als
   bestanden durchgewunken).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..cdp_client import CdpSession
from .base import StepStatus

STEP_ID = "closed_candle_detection"
TITLE = "Zuletzt geschlossene Kerze eindeutig identifiziert"


def _parse_timestamp(raw: Any) -> datetime | None:
    if isinstance(raw, int | float):
        # Sekunden vs. Millisekunden anhand der Groessenordnung unterscheiden.
        seconds = raw / 1000 if raw > 10**12 else raw
        try:
            return datetime.fromtimestamp(seconds, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return None


async def run(
    session: CdpSession, probe_js: str | None, now: datetime | None = None
) -> dict[str, Any]:
    if probe_js is None:
        return {
            "_status": StepStatus.INCONCLUSIVE.value,
            "reason": "Keine Sonde konfiguriert (TVCDP_PROBE_LAST_CLOSED_CANDLE_JS).",
        }

    raw = await session.evaluate(probe_js)
    # 'now' wird bewusst *nach* dem CDP-Roundtrip erfasst: ein frisch im
    # Seitenkontext erzeugter Timestamp (z. B. `new Date().toISOString()`)
    # entsteht zeitlich vor der Antwort, aber nach einem vorher erfassten
    # 'now' koennte die Netzwerk-/Auswertungslatenz ihn faelschlich als
    # 'in der Zukunft' erscheinen lassen -- beobachtet beim Live-Test gegen
    # eine echte CDP-Instanz.
    reference_now = now if now is not None else datetime.now(UTC)

    if not isinstance(raw, dict) or "is_closed" not in raw or "closed_timestamp" not in raw:
        return {
            "_status": StepStatus.INCONCLUSIVE.value,
            "reason": (
                "Sonde lieferte kein Objekt mit den Feldern 'is_closed' und "
                "'closed_timestamp'."
            ),
            "raw_type": type(raw).__name__,
        }

    if raw["is_closed"] is not True:
        return {
            "_status": StepStatus.FAILED.value,
            "reason": "Sonde meldet die aktuelle Kerze nicht als geschlossen.",
            "is_closed": raw["is_closed"],
        }

    parsed_timestamp = _parse_timestamp(raw["closed_timestamp"])
    if parsed_timestamp is None:
        return {
            "_status": StepStatus.INCONCLUSIVE.value,
            "reason": "closed_timestamp konnte nicht geparst werden.",
            "raw_closed_timestamp": raw["closed_timestamp"],
        }

    if parsed_timestamp > reference_now:
        return {
            "_status": StepStatus.FAILED.value,
            "reason": (
                "Gemeldeter Timestamp liegt in der Zukunft -- Widerspruch zu "
                "'geschlossen'. Sonde vermutlich fehlerhaft."
            ),
            "closed_timestamp": parsed_timestamp.isoformat(),
        }

    return {
        "is_closed": True,
        "closed_timestamp": parsed_timestamp.isoformat(),
        "age_seconds": (reference_now - parsed_timestamp).total_seconds(),
    }
