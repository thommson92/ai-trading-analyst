from __future__ import annotations

import json
import socket
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import websockets

from tvcdp.cdp_client import (
    CdpConnectionError,
    CdpProtocolError,
    CdpSession,
    CdpTarget,
    list_targets,
)
from tvcdp.config import CdpConfig


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class TestListTargets:
    def test_erfolgreiche_antwort_wird_in_cdptargets_umgewandelt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        raw_targets = [
            {
                "id": "abc",
                "title": "TradingView",
                "url": "app://tradingview/",
                "type": "page",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/abc",
            }
        ]

        class _FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> list[dict[str, Any]]:
                return raw_targets

        monkeypatch.setattr(
            "tvcdp.cdp_client.httpx.get", lambda *_a, **_kw: _FakeResponse()
        )

        targets = list_targets(CdpConfig())

        assert targets == [
            CdpTarget(
                id="abc",
                title="TradingView",
                url="app://tradingview/",
                type="page",
                websocket_debugger_url="ws://127.0.0.1:9222/devtools/page/abc",
            )
        ]

    def test_kein_lauschender_port_ergibt_cdpconnectionerror(self) -> None:
        unused_port = _free_port()
        config = CdpConfig(port=unused_port, connect_timeout_seconds=1.0)

        with pytest.raises(CdpConnectionError):
            list_targets(config)

    def test_connect_timeout_ergibt_ebenfalls_cdpconnectionerror(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regressionstest: auf einem echten Windows Server wurde ein nicht
        lauschender Port nicht mit einem sofortigen ECONNREFUSED (httpx.ConnectError)
        beantwortet, sondern mit einem Timeout (httpx.ConnectTimeout) -- vermutlich
        weil eine Firewall Pakete verwirft statt sie abzulehnen. ConnectTimeout ist
        keine Unterklasse von ConnectError, wurde also vorher nicht abgefangen und
        ist ungefangen bis zum Aufrufer durchgereicht worden."""

        def _raise_connect_timeout(*_a: Any, **_kw: Any) -> Any:
            raise httpx.ConnectTimeout("timed out")

        monkeypatch.setattr("tvcdp.cdp_client.httpx.get", _raise_connect_timeout)

        with pytest.raises(CdpConnectionError):
            list_targets(CdpConfig())

    def test_fehlendes_pflichtfeld_ergibt_cdpprotocolerror(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> list[dict[str, Any]]:
                return [{"id": "abc"}]  # webSocketDebuggerUrl fehlt

        monkeypatch.setattr(
            "tvcdp.cdp_client.httpx.get", lambda *_a, **_kw: _FakeResponse()
        )

        with pytest.raises(CdpProtocolError):
            list_targets(CdpConfig())


class _FakeCdpServer:
    """Minimaler lokaler WebSocket-Server, der wie ein CDP-Ziel antwortet --
    real genug (echter WebSocket-Handshake, echtes JSON-Framing), um die
    Session-Mechanik ohne eine echte Chromium-Instanz zu pruefen."""

    def __init__(self) -> None:
        self.received_methods: list[str] = []

    async def handler(self, connection: Any) -> None:
        async for raw_message in connection:
            message = json.loads(raw_message)
            self.received_methods.append(message["method"])
            request_id = message["id"]

            if message["method"] == "Runtime.evaluate":
                expression = message["params"]["expression"]
                if expression == "raise":
                    await connection.send(
                        json.dumps(
                            {
                                "id": request_id,
                                "result": {"exceptionDetails": {"text": "Boom"}},
                            }
                        )
                    )
                else:
                    await connection.send(
                        json.dumps({"id": request_id, "result": {"result": {"value": 42}}})
                    )
            elif message["method"] == "Trigger.protocolError":
                await connection.send(json.dumps({"id": request_id, "error": {"message": "nope"}}))
            elif message["method"] == "Trigger.neverRespond":
                continue
            else:
                await connection.send(json.dumps({"id": request_id, "result": {}}))


@pytest.fixture
async def fake_server() -> AsyncIterator[tuple[_FakeCdpServer, str]]:
    server_state = _FakeCdpServer()
    port = _free_port()
    async with websockets.serve(server_state.handler, "127.0.0.1", port):
        yield server_state, f"ws://127.0.0.1:{port}"


class TestCdpSession:
    async def test_evaluate_liefert_den_wert_aus_dem_ergebnis(
        self, fake_server: tuple[_FakeCdpServer, str]
    ) -> None:
        _, ws_url = fake_server
        target = CdpTarget(
            id="1", title="t", url="u", type="page", websocket_debugger_url=ws_url
        )
        async with await CdpSession.connect(target, CdpConfig()) as session:
            value = await session.evaluate("1 + 1")

        assert value == 42  # der Fake-Server liefert immer 42 fuer nicht-'raise'-Ausdruecke

    async def test_javascript_exception_wird_zu_cdpprotocolerror(
        self, fake_server: tuple[_FakeCdpServer, str]
    ) -> None:
        _, ws_url = fake_server
        target = CdpTarget(
            id="1", title="t", url="u", type="page", websocket_debugger_url=ws_url
        )
        async with await CdpSession.connect(target, CdpConfig()) as session:
            with pytest.raises(CdpProtocolError, match="JavaScript-Fehler"):
                await session.evaluate("raise")

    async def test_cdp_fehlerantwort_wird_zu_cdpprotocolerror(
        self, fake_server: tuple[_FakeCdpServer, str]
    ) -> None:
        _, ws_url = fake_server
        target = CdpTarget(
            id="1", title="t", url="u", type="page", websocket_debugger_url=ws_url
        )
        async with await CdpSession.connect(target, CdpConfig()) as session:
            with pytest.raises(CdpProtocolError, match="nope"):
                await session.send("Trigger.protocolError")

    async def test_ausbleibende_antwort_fuehrt_zu_timeout_fehler(
        self, fake_server: tuple[_FakeCdpServer, str]
    ) -> None:
        _, ws_url = fake_server
        target = CdpTarget(
            id="1", title="t", url="u", type="page", websocket_debugger_url=ws_url
        )
        config = CdpConfig(request_timeout_seconds=0.2)
        async with await CdpSession.connect(target, config) as session:
            with pytest.raises(CdpProtocolError, match="Keine Antwort"):
                await session.send("Trigger.neverRespond")

    async def test_verbindung_zu_nicht_lauschendem_port_ergibt_cdpconnectionerror(
        self,
    ) -> None:
        target = CdpTarget(
            id="1",
            title="t",
            url="u",
            type="page",
            websocket_debugger_url=f"ws://127.0.0.1:{_free_port()}",
        )
        with pytest.raises(CdpConnectionError):
            await CdpSession.connect(target, CdpConfig(connect_timeout_seconds=1.0))

    async def test_events_ohne_passende_id_werden_uebersprungen(
        self, fake_server: tuple[_FakeCdpServer, str]
    ) -> None:
        """Ein Event mit fremder id (asynchrone CDP-Nachricht) darf die
        eigentliche Antwort nicht verdecken."""

        class _ServerWithSpuriousEvent(_FakeCdpServer):
            async def handler(self, connection: Any) -> None:
                async for raw_message in connection:
                    message = json.loads(raw_message)
                    request_id = message["id"]
                    await connection.send(json.dumps({"id": 99999, "result": {"noise": True}}))
                    await connection.send(
                        json.dumps({"id": request_id, "result": {"result": {"value": 7}}})
                    )

        server_state = _ServerWithSpuriousEvent()
        port = _free_port()
        async with websockets.serve(server_state.handler, "127.0.0.1", port):
            target = CdpTarget(
                id="1",
                title="t",
                url="u",
                type="page",
                websocket_debugger_url=f"ws://127.0.0.1:{port}",
            )
            async with await CdpSession.connect(target, CdpConfig()) as session:
                value = await session.evaluate("whatever")

        assert value == 7
