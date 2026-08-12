"""Minimaler, plattformunabhaengiger CDP-Client.

Bewusst ohne eine der grossen CDP-Bibliotheken: Das Protokoll, das hier
gebraucht wird, ist klein (Zielliste abrufen, ein WebSocket oeffnen,
``Runtime.evaluate`` aufrufen) und eine duenne Eigenimplementierung macht
jeden Schritt fuer den Spike-Bericht nachvollziehbar, statt Verhalten in
einer Fremdbibliothek zu verstecken.

Nichts hier ist TradingView-spezifisch oder Windows-spezifisch -- das
Protokoll ist bei jeder Chromium-basierten Anwendung (Chrome, Electron)
identisch.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from typing import Any

import httpx
import websockets

from .config import CdpConfig


class CdpConnectionError(Exception):
    """Der CDP-Endpunkt ist nicht erreichbar (kein laufender Debug-Port)."""


class CdpProtocolError(Exception):
    """Der CDP-Endpunkt hat geantwortet, aber nicht wie vom Protokoll erwartet."""


@dataclass(frozen=True, slots=True)
class CdpTarget:
    """Ein von CDP gemeldetes Debug-Ziel (ein Fenster/Tab/Renderer-Prozess)."""

    id: str
    title: str
    url: str
    type: str
    websocket_debugger_url: str

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> CdpTarget:
        try:
            return cls(
                id=raw["id"],
                title=raw.get("title", ""),
                url=raw.get("url", ""),
                type=raw.get("type", ""),
                websocket_debugger_url=raw["webSocketDebuggerUrl"],
            )
        except KeyError as exc:
            raise CdpProtocolError(f"Unerwartetes Zielformat, Feld fehlt: {exc}") from exc


def list_targets(config: CdpConfig) -> list[CdpTarget]:
    """Fragt ``/json/list`` ab -- der erste Schritt jeder CDP-Verbindung.

    Erreichbarkeit dieses HTTP-Endpunkts allein beantwortet bereits Frage A.1
    (laesst sich TradingView Desktop mit aktiviertem CDP starten) und A.2
    (ist der Debug-Port erreichbar).
    """
    url = f"{config.http_base_url}/json/list"
    try:
        response = httpx.get(url, timeout=config.connect_timeout_seconds)
        response.raise_for_status()
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        # httpx.ConnectTimeout ist eine TimeoutException, keine Unterklasse von
        # ConnectError -- auf manchen Windows-Umgebungen (z.B. wenn eine
        # Firewall Pakete an geschlossene lokale Ports verwirft statt sie
        # sofort abzulehnen) tritt genau dieser Fall statt eines sofortigen
        # ECONNREFUSED auf. Beides bedeutet fachlich dasselbe: Endpunkt nicht
        # erreichbar innerhalb der konfigurierten Frist.
        raise CdpConnectionError(
            f"CDP-Endpunkt {url} nicht erreichbar. Laeuft die Zielanwendung mit "
            f"aktiviertem Remote-Debugging auf diesem Port?"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise CdpProtocolError(f"CDP-Endpunkt antwortete mit {exc.response.status_code}") from exc

    try:
        raw_targets = response.json()
    except json.JSONDecodeError as exc:
        raise CdpProtocolError("Antwort von /json/list war kein gueltiges JSON") from exc

    return [CdpTarget.from_json(item) for item in raw_targets]


class CdpSession:
    """Eine offene WebSocket-Verbindung zu genau einem CDP-Ziel.

    Verwendung als Kontextmanager:

        async with CdpSession.connect(target, config) as session:
            result = await session.evaluate("1 + 1")
    """

    def __init__(self, websocket: Any, request_timeout_seconds: float) -> None:
        self._websocket = websocket
        self._request_timeout_seconds = request_timeout_seconds
        self._id_counter = itertools.count(1)

    @classmethod
    async def connect(cls, target: CdpTarget, config: CdpConfig) -> CdpSession:
        try:
            websocket = await websockets.connect(
                target.websocket_debugger_url,
                open_timeout=config.connect_timeout_seconds,
            )
        except OSError as exc:
            raise CdpConnectionError(
                f"WebSocket-Verbindung zu Ziel '{target.title}' fehlgeschlagen: {exc}"
            ) from exc
        return cls(websocket, config.request_timeout_seconds)

    async def close(self) -> None:
        await self._websocket.close()

    async def __aenter__(self) -> CdpSession:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()

    async def send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Sendet einen rohen CDP-Befehl und wartet auf die passende Antwort.

        CDP multiplext Ereignisse und Antworten auf derselben Verbindung;
        Nachrichten ohne passende ``id`` (asynchrone Events) werden fuer
        diesen einfachen Anwendungsfall uebersprungen statt verarbeitet.
        """
        import asyncio

        request_id = next(self._id_counter)
        message = {"id": request_id, "method": method, "params": params or {}}
        await self._websocket.send(json.dumps(message))

        async def _await_matching_response() -> dict[str, Any]:
            while True:
                raw = await self._websocket.recv()
                parsed: dict[str, Any] = json.loads(raw)
                if parsed.get("id") == request_id:
                    return parsed
                # sonst: ein asynchrones CDP-Event -- fuer diesen Spike irrelevant

        try:
            response = await asyncio.wait_for(
                _await_matching_response(), timeout=self._request_timeout_seconds
            )
        except TimeoutError as exc:
            raise CdpProtocolError(
                f"Keine Antwort auf '{method}' innerhalb von "
                f"{self._request_timeout_seconds}s"
            ) from exc

        if "error" in response:
            raise CdpProtocolError(f"CDP-Fehler bei '{method}': {response['error']}")
        result: dict[str, Any] = response.get("result", {})
        return result

    async def evaluate(self, expression: str) -> Any:
        """Fuehrt JavaScript im Kontext des Ziels aus und liefert den Wert zurueck.

        Nur fuer Ausdruecke gedacht, die ein harmloses, strukturelles Ergebnis
        liefern (Zahl, String, Bool, JSON-serialisierbares Objekt) -- niemals
        fuer das Auslesen von Cookies, LocalStorage-Inhalten oder aehnlichem
        (siehe redaction.py und Sicherheitsvorgabe im Repository).
        """
        result = await self.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        if result.get("exceptionDetails") is not None:
            raise CdpProtocolError(
                f"JavaScript-Fehler bei der Auswertung: {result['exceptionDetails']}"
            )
        return result.get("result", {}).get("value")
