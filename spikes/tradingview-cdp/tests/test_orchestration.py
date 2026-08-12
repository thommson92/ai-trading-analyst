from __future__ import annotations

import pytest

from tvcdp.cdp_client import CdpConnectionError, CdpTarget
from tvcdp.config import CdpConfig
from tvcdp.orchestration import discover_target

_TV_TARGET = CdpTarget(
    id="1", title="TradingView", url="app://tv/", type="page", websocket_debugger_url="ws://x"
)
_OTHER_TARGET = CdpTarget(
    id="2", title="DevTools", url="devtools://x", type="page", websocket_debugger_url="ws://y"
)


class TestDiscoverTarget:
    def test_gefundenes_ziel_wird_zurueckgegeben(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "tvcdp.orchestration.list_targets", lambda _c: [_TV_TARGET, _OTHER_TARGET]
        )

        outcome = discover_target(CdpConfig(), "TradingView")

        assert outcome.matched_target == _TV_TARGET
        assert outcome.connection_error is None

    def test_kein_treffer_liefert_none_ohne_fehler(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("tvcdp.orchestration.list_targets", lambda _c: [_OTHER_TARGET])

        outcome = discover_target(CdpConfig(), "TradingView")

        assert outcome.matched_target is None
        assert outcome.connection_error is None

    def test_verbindungsfehler_wird_eingefangen_und_gemeldet(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(_c: CdpConfig) -> list[CdpTarget]:
            raise CdpConnectionError("kein Port offen")

        monkeypatch.setattr("tvcdp.orchestration.list_targets", _raise)

        outcome = discover_target(CdpConfig(), "TradingView")

        assert outcome.matched_target is None
        assert outcome.connection_error == "kein Port offen"
