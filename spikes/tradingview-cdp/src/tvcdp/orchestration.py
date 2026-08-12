"""Verbindungsaufbau, den mehrere Schritte gemeinsam brauchen: CDP-Ziele
auflisten, das TradingView-Ziel darin identifizieren, eine Session oeffnen.

Getrennt von cli.py, damit sowohl `run-all` als auch einzelne
Session-basierte Schritte dieselbe, einmal getestete Verbindungslogik
nutzen statt sie zu duplizieren.
"""

from __future__ import annotations

from dataclasses import dataclass

from .cdp_client import CdpConnectionError, CdpSession, CdpTarget, list_targets
from .config import CdpConfig


@dataclass(frozen=True, slots=True)
class ConnectionOutcome:
    targets: list[CdpTarget]
    matched_target: CdpTarget | None
    connection_error: str | None = None


def discover_target(config: CdpConfig, title_pattern: str) -> ConnectionOutcome:
    try:
        targets = list_targets(config)
    except CdpConnectionError as exc:
        return ConnectionOutcome(targets=[], matched_target=None, connection_error=str(exc))

    pattern = title_pattern.lower()
    matches = [t for t in targets if pattern in t.title.lower() or pattern in t.url.lower()]
    return ConnectionOutcome(targets=targets, matched_target=matches[0] if matches else None)


async def open_session(target: CdpTarget, config: CdpConfig) -> CdpSession:
    return await CdpSession.connect(target, config)
