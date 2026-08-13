from __future__ import annotations

import pytest

from tvcdp.config import SpikeConfig


class TestSpikeConfigExpectedLayout:
    def test_ohne_umgebungsvariable_ist_expected_layout_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("TVCDP_EXPECTED_LAYOUT", raising=False)

        config = SpikeConfig.from_env()

        assert config.expected_layout is None

    def test_gesetzte_umgebungsvariable_wird_uebernommen(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TVCDP_EXPECTED_LAYOUT", "/chart/AbCdEf12/")

        config = SpikeConfig.from_env()

        assert config.expected_layout == "/chart/AbCdEf12/"

    def test_leere_umgebungsvariable_gilt_als_nicht_gesetzt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TVCDP_EXPECTED_LAYOUT", "")

        config = SpikeConfig.from_env()

        assert config.expected_layout is None


class TestSpikeConfigMultiSymbolSwitchTimeoutSeconds:
    def test_ohne_umgebungsvariable_gilt_der_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("TVCDP_MULTI_SYMBOL_SWITCH_TIMEOUT_SECONDS", raising=False)

        config = SpikeConfig.from_env()

        assert config.multi_symbol_switch_timeout_seconds == 8.0

    def test_gesetzte_umgebungsvariable_wird_uebernommen(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TVCDP_MULTI_SYMBOL_SWITCH_TIMEOUT_SECONDS", "5.5")

        config = SpikeConfig.from_env()

        assert config.multi_symbol_switch_timeout_seconds == 5.5
