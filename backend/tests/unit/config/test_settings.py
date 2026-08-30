"""Tests der Konfigurationsvalidierung."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_trading_analyst.config import (
    AnalystRatingsConfig,
    AppConfig,
    BacktestingConfig,
    DataAvailabilityConfig,
    EarningsFilterConfig,
    GateNotClearedError,
    IndicatorConfig,
    LlmConfig,
    MarketConfig,
    MissingSecretError,
    ModelProfile,
    ResearchConfig,
    Secrets,
)
from ai_trading_analyst.config.settings import project_env_file


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
        assert (
            BacktestingConfig().cooldown_candles
            == AppConfig().screening.signal_lookback_previous_candles
        )

    def test_rejects_inverted_confidence_thresholds(self) -> None:
        with pytest.raises(ValidationError, match="minimum_sample_size"):
            BacktestingConfig(minimum_sample_size=30, normal_confidence_sample_size=10)

    def test_rejects_empty_horizons(self) -> None:
        with pytest.raises(ValidationError, match="horizons"):
            BacktestingConfig(horizons=())


class TestLlmConfig:
    def test_default_provider_ist_anthropic(self) -> None:
        assert LlmConfig().provider == "anthropic"

    def test_jede_aufgabe_hat_ein_eigenes_modellprofil(self) -> None:
        llm = LlmConfig()
        assert llm.research.model
        assert llm.technical.model
        assert llm.fundamental.model
        assert llm.report.model

    def test_ein_teilweise_angegebenes_profil_uebernimmt_den_rest_vom_standard(self) -> None:
        llm = LlmConfig(research=ModelProfile(model="ein-anderes-modell"))
        assert llm.research.model == "ein-anderes-modell"
        assert llm.technical.model == LlmConfig().technical.model

    def test_ein_unbekannter_anbieter_wird_abgelehnt(self) -> None:
        with pytest.raises(ValidationError):
            LlmConfig(provider="openai")

    def test_fallback_ist_standardmaessig_nicht_gesetzt(self) -> None:
        assert ModelProfile(model="claude-sonnet-5").fallback_model is None


class TestResearchConfig:
    def test_default_provider_ist_fixture(self) -> None:
        """Wie bei EarningsFilterConfig: Start und Tests ohne Anthropic-Zugang."""
        assert ResearchConfig().provider == "fixture"

    def test_default_allowlist_enthaelt_sec_gov(self) -> None:
        assert "sec.gov" in ResearchConfig().fetch_allowed_domains

    def test_ein_unbekannter_anbieter_wird_abgelehnt(self) -> None:
        with pytest.raises(ValidationError):
            ResearchConfig(provider="openai")

    def test_eine_leere_allowlist_ist_erlaubt(self) -> None:
        """Bewusst keine Einschraenkung -- aber nicht der ausgelieferte Standard."""
        assert ResearchConfig(fetch_allowed_domains=()).fetch_allowed_domains == ()

    def test_kostenbudget_ist_vorbelegt(self) -> None:
        """Ohne Deckel hat ein realer Lauf 256.000 Eingabe-Token verbraucht
        (ADR 0023, "Kostenkontrolle") -- die Voreinstellung darf das nicht
        wieder offenlassen."""
        config = ResearchConfig()
        assert config.max_fetch_content_tokens > 0
        assert config.max_input_tokens_per_symbol > 0

    def test_ein_budget_von_null_wird_abgelehnt(self) -> None:
        with pytest.raises(ValidationError):
            ResearchConfig(max_fetch_content_tokens=0)


class TestDataAvailabilityConfig:
    def test_rejects_wait_budget_that_allows_no_poll(self) -> None:
        with pytest.raises(ValidationError, match="Pollversuch"):
            DataAvailabilityConfig(grace_period_seconds=600, max_wait_seconds=600)


class TestAnalystRatingsConfig:
    """ADR 0043."""

    def test_fixture_bleibt_der_standard(self) -> None:
        """Wie beim Earnings-Filter: Start und Tests ohne Finnhub-Zugang."""
        assert AnalystRatingsConfig().provider == "fixture"

    def test_vier_monatsstaende_als_voreinstellung(self) -> None:
        assert AnalystRatingsConfig().months == 4

    def test_ein_unbekannter_anbieter_wird_abgelehnt(self) -> None:
        with pytest.raises(ValidationError):
            AnalystRatingsConfig(provider="alphavantage")

    def test_null_monatsstaende_werden_abgelehnt(self) -> None:
        """Ein Abruf, der nichts uebernimmt, waere ein Abruf ohne Zweck."""
        with pytest.raises(ValidationError):
            AnalystRatingsConfig(months=0)


class TestFinnhubAbschnittUmgezogen:
    """ADR 0043: ein Konto, ein Schluessel, ein Host -- zwei Endpunkte."""

    def test_host_und_zeitgrenze_stehen_jetzt_oben(self) -> None:
        config = AppConfig.model_validate(
            {"finnhub": {"base_url": "https://example.test/v1", "request_timeout_seconds": 3}}
        )
        assert config.finnhub.base_url == "https://example.test/v1"
        assert config.finnhub.request_timeout_seconds == 3

    def test_das_kalenderfenster_bleibt_beim_earnings_filter(self) -> None:
        """Es beschreibt den Endpunkt, nicht den Zugang."""
        config = AppConfig.model_validate({"earnings_filter": {"lookahead_calendar_days": 45}})
        assert config.earnings_filter.lookahead_calendar_days == 45

    def test_der_alte_schluesselort_bricht_den_start_ab(self) -> None:
        """Eine still uebergangene Umbenennung waere schlimmer als ein
        Abbruch: Der Lauf liefe mit Voreinstellungen weiter, waehrend die
        Datei etwas anderes sagt."""
        with pytest.raises(ValidationError):
            AppConfig.model_validate(
                {"earnings_filter": {"finnhub": {"base_url": "https://example.test/v1"}}}
            )


class TestUnknownKeys:
    def test_unknown_key_is_an_error_rather_than_a_silent_default(self) -> None:
        """Ein Tippfehler in der YAML-Datei muss auffallen."""
        with pytest.raises(ValidationError):
            AppConfig.model_validate({"screening": {"required_signal_cout": 2}})


class TestGateG1:
    """Gate G1 ist freigegeben (docs/adr/0010); die Sicherung bleibt bestehen:
    eine Konfiguration ohne den Abschnitt 'indicators' bricht weiterhin mit
    einem klaren Fehler ab, statt mit fehlenden Parametern zu rechnen."""

    def test_indicators_are_absent_without_explicit_configuration(self) -> None:
        assert AppConfig().indicators is None

    def test_requiring_indicators_fails_with_an_explicit_message(self) -> None:
        with pytest.raises(GateNotClearedError, match="'indicators' fehlt"):
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
            Secrets(_env_file=None).require("database_url")

    def test_unknown_secret_field_is_rejected(self) -> None:
        with pytest.raises(KeyError):
            Secrets(_env_file=None).require("does_not_exist")

    def test_secret_is_read_from_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATA_SESSION_SECRET", "s3cret")
        assert Secrets(_env_file=None).require("session_secret") == "s3cret"

    def test_secret_is_not_exposed_by_repr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Ein versehentlich geloggtes Settings-Objekt darf nichts verraten."""
        monkeypatch.setenv("ATA_SESSION_SECRET", "s3cret")
        assert "s3cret" not in repr(Secrets(_env_file=None))

    @pytest.mark.parametrize("leer", ["", "   ", "\t"])
    def test_an_empty_value_counts_as_not_set(
        self, monkeypatch: pytest.MonkeyPatch, leer: str
    ) -> None:
        """``.env.example`` liefert die noch ungebrauchten Schluessel leer aus.

        Ohne diese Normalisierung liefe ``require`` glatt durch und gaebe eine
        leere Zeichenkette weiter -- der Frueh-Abbruch vor dem halbstuendigen
        Backfill waere uebersprungen, und der Abend endete mit lauter
        degradierten Kandidaten und Rueckgabewert 0.
        """
        monkeypatch.setenv("ATA_FINNHUB_API_KEY", leer)
        with pytest.raises(MissingSecretError, match="ATA_FINNHUB_API_KEY"):
            Secrets(_env_file=None).require("finnhub_api_key")

    def test_a_value_with_surrounding_whitespace_is_kept_as_is(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Normalisiert wird nur der leere Fall -- ein echter Schluessel
        bleibt unangetastet, auch wenn er versehentlich Leerzeichen traegt."""
        monkeypatch.setenv("ATA_FINNHUB_API_KEY", " abc123 ")
        assert Secrets(_env_file=None).require("finnhub_api_key") == " abc123 "


class TestSecretsAusDatei:
    """Ohne die ``.env`` bleibt der Backfill auf dem Server unbedienbar.

    Der erste Inbetriebnahmeversuch scheiterte genau hier: ``.env.example``
    ist eingecheckt und weist das Kopieren an, gelesen hat die Datei aber
    niemand.
    """

    def test_die_datei_wird_gelesen(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("ATA_DATABASE_URL=postgresql+psycopg://a:b@localhost:5432/ata\n")

        secrets = Secrets(_env_file=env_file)

        assert secrets.require("database_url").endswith("/ata")

    def test_die_echte_umgebungsvariable_gewinnt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sonst liesse sich ein Lauf nicht mehr gezielt umlenken."""
        env_file = tmp_path / ".env"
        env_file.write_text("ATA_SESSION_SECRET=aus-der-datei\n")
        monkeypatch.setenv("ATA_SESSION_SECRET", "aus-der-umgebung")

        assert Secrets(_env_file=env_file).require("session_secret") == "aus-der-umgebung"

    def test_gesucht_wird_im_projektwurzelverzeichnis(self) -> None:
        """Nicht in ``backend/`` -- dort wird gestartet, dort liegt sie nicht."""
        pfad = project_env_file()

        assert pfad.name == ".env"
        assert (pfad.parent / "config" / "default.yaml").exists()
        assert (pfad.parent / ".env.example").exists()

    def test_eine_fehlende_datei_ist_kein_fehler(self, tmp_path: Path) -> None:
        """Auf Entwicklungsrechnern und in der CI gibt es keine ``.env``."""
        with pytest.raises(MissingSecretError):
            Secrets(_env_file=tmp_path / "gibt-es-nicht").require("database_url")
