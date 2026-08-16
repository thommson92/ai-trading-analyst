"""Tests des Konfigurations-Loaders, inklusive der ausgelieferten default.yaml."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_trading_analyst.config import ConfigError, default_config_path, load_config
from ai_trading_analyst.config.loader import DEFAULT_CONFIG_ENV_VAR


class TestLoadConfig:
    def test_reads_a_minimal_file(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text("screening:\n  required_signal_count: 3\n", encoding="utf-8")

        loaded = load_config(path)

        assert loaded.config.screening.required_signal_count == 3
        assert loaded.source_path == path

    def test_comment_only_file_yields_defaults(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text("# nur ein Kommentar\n", encoding="utf-8")

        assert load_config(path).config.screening.required_signal_count == 2

    def test_fingerprint_changes_with_content(self, tmp_path: Path) -> None:
        """Doc 10 Paragraph 17 verlangt protokollierbare Konfigurationsaenderungen."""
        path = tmp_path / "config.yaml"
        path.write_text("logging:\n  level: INFO\n", encoding="utf-8")
        before = load_config(path).fingerprint

        path.write_text("logging:\n  level: DEBUG\n", encoding="utf-8")
        after = load_config(path).fingerprint

        assert before != after

    def test_missing_file_is_reported_clearly(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="nicht lesbar"):
            load_config(tmp_path / "fehlt.yaml")

    def test_broken_yaml_is_reported_clearly(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text("market:\n  - [unbalanced\n", encoding="utf-8")

        with pytest.raises(ConfigError, match="kein gueltiges YAML"):
            load_config(path)

    def test_non_mapping_file_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text("- eins\n- zwei\n", encoding="utf-8")

        with pytest.raises(ConfigError, match="Mapping"):
            load_config(path)

    def test_invalid_value_is_reported_with_the_file_path(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text("market:\n  timeframe_minutes: 200\n", encoding="utf-8")

        with pytest.raises(ConfigError, match="ungueltig"):
            load_config(path)


class TestDefaultConfigPath:
    def test_environment_variable_takes_precedence(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(DEFAULT_CONFIG_ENV_VAR, str(tmp_path / "eigene.yaml"))
        assert default_config_path() == tmp_path / "eigene.yaml"

    def test_falls_back_to_the_repository_file(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(DEFAULT_CONFIG_ENV_VAR, raising=False)
        assert default_config_path().name == "default.yaml"


class TestShippedDefaultConfig:
    """Die ausgelieferte config/default.yaml muss ladbar und plausibel sein."""

    def test_it_loads(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(DEFAULT_CONFIG_ENV_VAR, raising=False)
        assert load_config().config.market.timeframe_minutes == 195

    def test_it_contains_the_confirmed_gate_g1_indicator_parameters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gate G1 ist freigegeben (docs/adr/0010) -- die Datei enthaelt die
        bestaetigten Werte aus der G1-Pruefvorlage, nicht mehr None."""
        monkeypatch.delenv(DEFAULT_CONFIG_ENV_VAR, raising=False)
        indicators = load_config().config.require_indicators()
        assert indicators.rsi_length == 14
        assert indicators.rsi_method == "wilder"
        assert indicators.rsi_ma_length == 14
        assert indicators.rsi_ma_type == "sma"
        assert indicators.fast_ema_length == 5
        assert indicators.slow_ema_length == 20
        assert indicators.warmup_candles == 250

    def test_it_contains_the_llm_model_profiles(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ADR 0021 -- Anthropic API, gestufte Modellprofile je Analyseaufgabe."""
        monkeypatch.delenv(DEFAULT_CONFIG_ENV_VAR, raising=False)
        llm = load_config().config.llm
        assert llm.provider == "anthropic"
        assert llm.research.model == "claude-sonnet-5"
        assert llm.technical.model == "claude-haiku-4-5-20251001"
        assert llm.fundamental.model == "claude-haiku-4-5-20251001"
        assert llm.report.model == "claude-haiku-4-5-20251001"

    def test_it_contains_no_secret_like_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(DEFAULT_CONFIG_ENV_VAR, raising=False)
        content = default_config_path().read_text(encoding="utf-8").lower()

        for forbidden in ("password", "api_key", "apikey", "token", "secret"):
            assert forbidden not in content, f"Geheimnis-verdaechtiger Schluessel: {forbidden}"
