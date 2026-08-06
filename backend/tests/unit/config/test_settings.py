"""Tests der Konfigurationsvalidierung."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_trading_analyst.config import (
    AppConfig,
    BacktestingConfig,
    DataAvailabilityConfig,
    EarningsFilterConfig,
    GateNotClearedError,
    IndicatorConfig,
    MarketConfig,
    MissingSecretError,
    Secrets,
)


class TestMarketConfig:
    def test_default_session_yields_exactly_two_candles(self) -> None:
        market = MarketConfig()
        assert market.regular_session_minutes // market.timeframe_minutes == 2

    def test_rejects_timeframe_that_does_not_divide_the_session(self) -> None:
        with pytest.raises(ValidationError, match="Vielfaches"):
            MarketConfig(regular_session_minutes=390, timeframe_minutes=200)

    def test_rejects_candle_index_beyond_the_session(self) -> None:
        with pytest.raises(ValidationError, match="ausserhalb"):
            MarketConfig(daily_candle_index=3)

    def test_rejects_zero_timeframe(self) -> None:
        with pytest.raises(ValidationError):
            MarketConfig(timeframe_minutes=0)


class TestEarningsFilterConfig:
    def test_default_uses_the_conservative_upper_bound(self) -> None:
        assert EarningsFilterConfig().configured_exclusion_candles == 20

    def test_rejects_configured_value_outside_the_documented_range(self) -> None:
        with pytest.raises(ValidationError, match="zwischen"):
            EarningsFilterConfig(configured_exclusion_candles=25)


class TestBacktestingConfig:
    def test_default_horizons_match_the_specification(self) -> None:
        assert BacktestingConfig().horizons == (5, 10, 20)

    def test_cooldown_matches_the_screening_lookback(self) -> None:
        """F5: Der Cooldown entspricht der Lookback-Laenge der Kandidatenregel."""
        assert BacktestingConfig().cooldown_candles == AppConfig().screening.lookback_closed_candles

    def test_rejects_inverted_confidence_thresholds(self) -> None:
        with pytest.raises(ValidationError, match="minimum_sample_size"):
            BacktestingConfig(minimum_sample_size=30, normal_confidence_sample_size=10)

    def test_rejects_empty_horizons(self) -> None:
        with pytest.raises(ValidationError, match="horizons"):
            BacktestingConfig(horizons=())


class TestDataAvailabilityConfig:
    def test_rejects_wait_budget_that_allows_no_poll(self) -> None:
        with pytest.raises(ValidationError, match="Pollversuch"):
            DataAvailabilityConfig(grace_period_seconds=600, max_wait_seconds=600)


class TestUnknownKeys:
    def test_unknown_key_is_an_error_rather_than_a_silent_default(self) -> None:
        """Ein Tippfehler in der YAML-Datei muss auffallen."""
        with pytest.raises(ValidationError):
            AppConfig.model_validate({"screening": {"required_signal_cout": 2}})


class TestGateG1:
    def test_indicators_are_absent_by_default(self) -> None:
        assert AppConfig().indicators is None

    def test_requiring_indicators_fails_with_an_explicit_gate_message(self) -> None:
        with pytest.raises(GateNotClearedError, match="Gate G1"):
            AppConfig().require_indicators()

    def test_indicator_config_has_no_defaults_at_all(self) -> None:
        """Kein Feld darf einen Default haben -- sonst koennte still geraten werden."""
        with pytest.raises(ValidationError):
            IndicatorConfig.model_validate({})

    def test_indicators_are_usable_once_supplied(self) -> None:
        config = AppConfig.model_validate(
            {
                "indicators": {
                    "rsi_length": 14,
                    "rsi_method": "wilder",
                    "rsi_ma_length": 14,
                    "rsi_ma_type": "sma",
                    "fast_ema_length": 5,
                    "slow_ema_length": 20,
                    "warmup_candles": 200,
                }
            }
        )
        assert config.require_indicators().rsi_length == 14


class TestSecrets:
    def test_missing_secret_names_the_expected_environment_variable(self) -> None:
        with pytest.raises(MissingSecretError, match="ATA_DATABASE_URL"):
            Secrets().require("database_url")

    def test_unknown_secret_field_is_rejected(self) -> None:
        with pytest.raises(KeyError):
            Secrets().require("does_not_exist")

    def test_secret_is_read_from_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATA_SESSION_SECRET", "s3cret")
        assert Secrets().require("session_secret") == "s3cret"

    def test_secret_is_not_exposed_by_repr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Ein versehentlich geloggtes Settings-Objekt darf nichts verraten."""
        monkeypatch.setenv("ATA_SESSION_SECRET", "s3cret")
        assert "s3cret" not in repr(Secrets())
