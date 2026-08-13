from __future__ import annotations

import json
import socket
from collections.abc import AsyncIterator
from typing import Any

import pytest
import websockets

from tvcdp.cdp_client import CdpSession, CdpTarget
from tvcdp.config import CdpConfig


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class JsError:
    """Sentinel fuer ``ScriptedCdpServer.when()``: simuliert einen
    JavaScript-Fehler (z. B. einen voruebergehenden Zustand waehrend eines
    Uebergangs) statt eines regulaeren Rueckgabewerts."""

    def __init__(self, message: str) -> None:
        self.message = message


class ScriptedCdpServer:
    """Ein lokaler CDP-Fake-Server, dessen ``Runtime.evaluate``-Antworten pro
    Ausdruck vorab festgelegt werden -- macht Step-Tests unabhaengig von
    jeder echten Chromium-/TradingView-Instanz."""

    def __init__(self) -> None:
        self.responses: dict[str, list[Any]] = {}
        self.received_expressions: list[str] = []

    def when(self, expression: str, value: Any) -> None:
        """Registriert eine Antwort fuer einen Ausdruck. Mehrfacher Aufruf fuer
        denselben Ausdruck queued die Antworten (erster Aufruf -> erste
        Antwort, zweiter Aufruf -> zweite Antwort, ...); die letzte
        registrierte Antwort wiederholt sich, sobald die Warteschlange
        aufgebraucht ist. Ermoeglicht das Simulieren von Polling-Sequenzen
        (z. B. "noch nicht umgeschaltet" -> "umgeschaltet"). ``value`` kann
        ein ``JsError`` sein, um einen JavaScript-Fehler an dieser Stelle in
        der Sequenz zu simulieren."""
        self.responses.setdefault(expression, []).append(value)

    async def handler(self, connection: Any) -> None:
        async for raw_message in connection:
            message = json.loads(raw_message)
            request_id = message["id"]
            if message["method"] != "Runtime.evaluate":
                await connection.send(json.dumps({"id": request_id, "result": {}}))
                continue

            expression = message["params"]["expression"]
            self.received_expressions.append(expression)
            if expression not in self.responses:
                await connection.send(
                    json.dumps(
                        {
                            "id": request_id,
                            "result": {"exceptionDetails": {"text": f"unbekannt: {expression}"}},
                        }
                    )
                )
                continue

            queue = self.responses[expression]
            value = queue.pop(0) if len(queue) > 1 else queue[0]
            if isinstance(value, JsError):
                await connection.send(
                    json.dumps(
                        {
                            "id": request_id,
                            "result": {"exceptionDetails": {"text": value.message}},
                        }
                    )
                )
                continue

            await connection.send(
                json.dumps({"id": request_id, "result": {"result": {"value": value}}})
            )


@pytest.fixture
async def scripted_session() -> AsyncIterator[tuple[ScriptedCdpServer, CdpSession]]:
    server = ScriptedCdpServer()
    port = _free_port()
    async with websockets.serve(server.handler, "127.0.0.1", port):
        target = CdpTarget(
            id="1",
            title="TradingView",
            url="app://tv/",
            type="page",
            websocket_debugger_url=f"ws://127.0.0.1:{port}",
        )
        session = await CdpSession.connect(target, CdpConfig())
        try:
            yield server, session
        finally:
            await session.close()
