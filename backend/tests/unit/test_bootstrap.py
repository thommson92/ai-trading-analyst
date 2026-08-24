"""Auswahl des Marktdatenanbieters in der Composition Root.

Der Rest von ``build_app`` braucht eine Datenbank und wird in den
Integrationstests geprueft. Die Anbieterauswahl selbst ist eine reine
Entscheidung ueber der Konfiguration und gehoert deshalb hierher: Sie
entscheidet, ob ein Lauf mit Fixture-Daten oder gegen die echte TWS arbeitet
-- eine Verwechslung waere im Betrieb teuer.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

import pytest
from pydantic import ValidationError

from ai_trading_analyst.bootstrap import (
    build_backtest_params,
    build_bar_source,
    build_earnings_provider,
    build_market_data_provider,
    build_research_provider,
    build_technical_interpreter,
    project_root,
)
from ai_trading_analyst.config.settings import (
    AppConfig,
    EarningsFilterConfig,
    IbkrConfig,
    IndicatorConfig,
    MarketDataConfig,
    MissingSecretError,
    ResearchConfig,
    Secrets,
    TechnicalAgentConfig,
)
from ai_trading_analyst.infrastructure.anthropic import (
    AnthropicResearchProvider,
    AnthropicTechnicalInterpreter,
)
from ai_trading_analyst.infrastructure.finnhub import FinnhubEarningsProvider
from ai_trading_analyst.infrastructure.fixtures.earnings_provider import FixtureEarningsProvider
from ai_trading_analyst.infrastructure.fixtures.market_data_provider import (
    FixtureMarketDataProvider,
)
from ai_trading_analyst.infrastructure.fixtures.research_provider import FixtureResearchProvider
from ai_trading_analyst.infrastructure.fixtures.technical_interpreter import (
    FixtureTechnicalInterpreter,
)
from ai_trading_analyst.infrastructure.ibkr import (
    ContractSpec,
    IbAsyncBarSource,
    IbkrMarketDataProvider,
)
from ai_trading_analyst.infrastructure.persistence.stored_bar_source import StoredBarSource
from ai_trading_analyst.infrastructure.watchlists import WatchlistError
from tests.unit.application.conftest import (
    FakeAnalysisRunRepository,
    FakeProcessingErrorRepository,
    FakeScreeningResultRepository,
    FakeStockRepository,
    FakeUnitOfWork,
    InMemoryIntradayBarRepository,
)

INDICATORS = IndicatorConfig(
    rsi_length=14,
    rsi_method="wilder",
    rsi_ma_length=14,
    rsi_ma_type="sma",
    fast_ema_length=5,
    slow_ema_length=20,
    warmup_candles=250,
)


def ibkr_config(source: Literal["live", "stored"] = "live", **overrides: object) -> AppConfig:
    """Standard hier ist ``live``, damit diese Tests ohne Datenbank auskommen.

    Die Wahl der Barquelle ist in ``TestBarquelle`` eigens geprueft.
    """
    return AppConfig(
        market_data=MarketDataConfig(
            provider="ibkr",
            source=source,
            ibkr=IbkrConfig(**overrides),
        ),
        indicators=INDICATORS,
    )


@pytest.fixture
def wurzel_mit_watchlist(tmp_path: Path) -> Path:
    directory = tmp_path / "watchlists"
    directory.mkdir()
    (directory / "test.txt").write_text("NASDAQ:AAPL,NYSE:JPM", encoding="utf-8")
    return tmp_path


class TestAnbieterauswahl:
    def test_standard_ist_der_fixture_anbieter(self, tmp_path: Path) -> None:
        config = AppConfig(indicators=INDICATORS)
        assert config.market_data.provider == "fixture"
        provider = build_market_data_provider(config, INDICATORS, tmp_path)
        assert isinstance(provider, FixtureMarketDataProvider)

    def test_ibkr_wird_nur_auf_ausdrueckliche_konfiguration_gebaut(
        self, wurzel_mit_watchlist: Path
    ) -> None:
        provider = build_market_data_provider(ibkr_config(), INDICATORS, wurzel_mit_watchlist)
        assert isinstance(provider, IbkrMarketDataProvider)

    def test_die_watchlist_kommt_aus_den_dateien(self, wurzel_mit_watchlist: Path) -> None:
        provider = build_market_data_provider(ibkr_config(), INDICATORS, wurzel_mit_watchlist)
        stocks = provider.list_stocks()
        assert [stock.symbol for stock in stocks] == ["AAPL", "JPM"]
        assert [stock.exchange for stock in stocks] == ["NASDAQ", "NYSE"]

    def test_eine_uebergebene_watchlist_uebersteuert_die_dateien(self, tmp_path: Path) -> None:
        # Fuer den gezielten Einzelabruf ueber die Kommandozeile -- hier gibt
        # es bewusst gar kein Watchlist-Verzeichnis.
        provider = build_market_data_provider(
            ibkr_config(), INDICATORS, tmp_path, (ContractSpec(symbol="TSLA"),)
        )
        assert [stock.symbol for stock in provider.list_stocks()] == ["TSLA"]

    def test_ein_fehlendes_watchlist_verzeichnis_scheitert_beim_start(self, tmp_path: Path) -> None:
        with pytest.raises(WatchlistError, match="existiert nicht"):
            build_market_data_provider(ibkr_config(), INDICATORS, tmp_path)

    def test_der_aufbau_stellt_keine_verbindung_her(self, wurzel_mit_watchlist: Path) -> None:
        """Ein Anwendungsstart ohne laufende TWS darf nicht scheitern.

        Die Verbindung entsteht erst beim ersten Abruf -- ADR 0014, E2: Nach
        einem Neustart laeuft die TWS erst nach manueller Anmeldung wieder,
        und bis dahin soll die Anwendung startfaehig bleiben.
        """
        provider = build_market_data_provider(
            ibkr_config(host="127.0.0.1", port=1), INDICATORS, wurzel_mit_watchlist
        )
        assert isinstance(provider, IbkrMarketDataProvider)


class TestEarningsAnbieterauswahl:
    def test_standard_ist_der_fixture_anbieter(self) -> None:
        config = AppConfig(indicators=INDICATORS)
        assert config.earnings_filter.provider == "fixture"
        provider = build_earnings_provider(config, Secrets(_env_file=None))
        assert isinstance(provider, FixtureEarningsProvider)

    def test_finnhub_ohne_secret_scheitert_verstaendlich(self) -> None:
        config = AppConfig(
            indicators=INDICATORS, earnings_filter=EarningsFilterConfig(provider="finnhub")
        )
        with pytest.raises(MissingSecretError, match="ATA_FINNHUB_API_KEY"):
            build_earnings_provider(config, Secrets(_env_file=None))

    def test_finnhub_mit_secret_wird_ohne_netzwerkzugriff_gebaut(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATA_FINNHUB_API_KEY", "test-key")
        config = AppConfig(
            indicators=INDICATORS, earnings_filter=EarningsFilterConfig(provider="finnhub")
        )
        provider = build_earnings_provider(config, Secrets(_env_file=None))
        assert isinstance(provider, FinnhubEarningsProvider)


class TestResearchAnbieterauswahl:
    def test_standard_ist_der_fixture_anbieter(self) -> None:
        config = AppConfig(indicators=INDICATORS)
        assert config.research.provider == "fixture"
        provider = build_research_provider(config, Secrets(_env_file=None))
        assert isinstance(provider, FixtureResearchProvider)

    def test_anthropic_ohne_secret_scheitert_verstaendlich(self) -> None:
        config = AppConfig(indicators=INDICATORS, research=ResearchConfig(provider="anthropic"))
        with pytest.raises(MissingSecretError, match="ATA_LLM_API_KEY"):
            build_research_provider(config, Secrets(_env_file=None))

    def test_anthropic_mit_secret_wird_ohne_netzwerkzugriff_gebaut(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATA_LLM_API_KEY", "test-key")
        config = AppConfig(indicators=INDICATORS, research=ResearchConfig(provider="anthropic"))
        provider = build_research_provider(config, Secrets(_env_file=None))
        assert isinstance(provider, AnthropicResearchProvider)

    def test_die_zitatobergrenze_aus_der_konfiguration_kommt_beim_anbieter_an(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``max_citations`` steuert, wie viele Belege gespeichert werden
        (ADR 0029). Ohne diesen Test bliebe die YAML-Einstellung wirkungslos,
        falls die Verdrahtung in ``bootstrap`` je wegfaellt -- die Vorgabe
        haette weitergegolten und nichts waere rot geworden."""
        monkeypatch.setenv("ATA_LLM_API_KEY", "test-key")
        config = AppConfig(
            indicators=INDICATORS,
            research=ResearchConfig(provider="anthropic", max_citations=7),
        )
        provider = build_research_provider(config, Secrets(_env_file=None))
        assert isinstance(provider, AnthropicResearchProvider)
        assert provider._max_citations == 7


class TestTechnicalAgentAnbieterauswahl:
    def test_standard_ist_der_fixture_anbieter(self) -> None:
        config = AppConfig(indicators=INDICATORS)
        assert config.technical_agent.provider == "fixture"
        interpreter = build_technical_interpreter(config, Secrets(_env_file=None))
        assert isinstance(interpreter, FixtureTechnicalInterpreter)

    def test_anthropic_ohne_secret_scheitert_verstaendlich(self) -> None:
        config = AppConfig(
            indicators=INDICATORS, technical_agent=TechnicalAgentConfig(provider="anthropic")
        )
        with pytest.raises(MissingSecretError, match="ATA_LLM_API_KEY"):
            build_technical_interpreter(config, Secrets(_env_file=None))

    def test_anthropic_mit_secret_wird_ohne_netzwerkzugriff_gebaut(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATA_LLM_API_KEY", "test-key")
        config = AppConfig(
            indicators=INDICATORS, technical_agent=TechnicalAgentConfig(provider="anthropic")
        )
        interpreter = build_technical_interpreter(config, Secrets(_env_file=None))
        assert isinstance(interpreter, AnthropicTechnicalInterpreter)

    def test_das_modellprofil_kommt_aus_llm_technical(self) -> None:
        """Nicht aus ``llm.research``: Der Technical Agent interpretiert nur
        bereits gerechnete Werte und laeuft deshalb auf einem guenstigeren
        Modell (ADR 0021, Modellstufung)."""
        config = AppConfig(indicators=INDICATORS)
        assert config.llm.technical.model != config.llm.research.model


class TestBarquelle:
    """Woher der regulaere Lauf seine Bars nimmt.

    Der Standard ist der Bestand: Nur so liefert dieselbe Analyse morgen
    dasselbe Ergebnis -- IBKRs Ein-Jahres-Fenster wandert mit der Uhr. Und
    nur so kommt der Lauf ohne angemeldete TWS aus (ADR 0014, E2).
    """

    @staticmethod
    def _uow_factory() -> Callable[[], FakeUnitOfWork]:
        def factory() -> FakeUnitOfWork:
            return FakeUnitOfWork(
                FakeStockRepository(),
                InMemoryIntradayBarRepository(),
                FakeAnalysisRunRepository(),
                FakeScreeningResultRepository(),
                FakeProcessingErrorRepository(),
            )

        return factory

    def test_der_standard_ist_der_bestand(self) -> None:
        assert AppConfig(indicators=INDICATORS).market_data.source == "stored"

    def test_stored_ergibt_die_bestandsquelle(self) -> None:
        quelle = build_bar_source(ibkr_config(source="stored"), self._uow_factory())
        assert isinstance(quelle, StoredBarSource)

    def test_live_ergibt_die_tws_quelle(self) -> None:
        quelle = build_bar_source(ibkr_config(source="live"), self._uow_factory())
        assert isinstance(quelle, IbAsyncBarSource)

    def test_live_kommt_ohne_datenbank_aus(self) -> None:
        """Der gezielte Einzelabruf ueber die Kommandozeile soll ohne
        Datenbank laufen."""
        assert isinstance(build_bar_source(ibkr_config(source="live"), None), IbAsyncBarSource)

    def test_stored_ohne_datenbank_scheitert_verstaendlich(self) -> None:
        with pytest.raises(ValueError, match="keine Datenbank"):
            build_bar_source(ibkr_config(source="stored"), None)

    def test_der_provider_bekommt_die_bestandsquelle(self, wurzel_mit_watchlist: Path) -> None:
        """Der eigentliche Punkt: Auch der persistierte Lauf hinter der API
        rechnet auf dem Bestand, nicht nur das Kommandozeilenwerkzeug."""
        provider = build_market_data_provider(
            ibkr_config(source="stored"),
            INDICATORS,
            wurzel_mit_watchlist,
            uow_factory=self._uow_factory(),
        )

        assert isinstance(provider, IbkrMarketDataProvider)
        assert isinstance(provider._bar_source, StoredBarSource)


class TestProjektwurzel:
    def test_die_wurzel_liegt_ueber_dem_konfigurationsverzeichnis(self, tmp_path: Path) -> None:
        assert project_root(tmp_path / "config" / "default.yaml") == tmp_path


class TestBacktestParameter:
    def test_werte_kommen_unveraendert_aus_der_konfiguration(self) -> None:
        config = AppConfig(indicators=INDICATORS)
        params = build_backtest_params(config)
        assert params.horizons == config.backtesting.horizons
        assert params.cooldown_candles == config.backtesting.cooldown_candles
        assert params.minimum_sample_size == config.backtesting.minimum_sample_size
        assert (
            params.normal_confidence_sample_size == config.backtesting.normal_confidence_sample_size
        )
        assert params.history_years == config.backtesting.history_years


class TestKonfigurationspruefung:
    def test_eine_bar_groesse_die_die_kerze_nicht_fuellt_faellt_beim_laden_auf(self) -> None:
        with pytest.raises(ValidationError, match="ohne Rest"):
            AppConfig(
                market_data=MarketDataConfig(ibkr=IbkrConfig(native_bar_minutes=7)),
                indicators=INDICATORS,
            )

    def test_ein_negativer_anfrageabstand_wird_abgelehnt(self) -> None:
        with pytest.raises(ValidationError):
            IbkrConfig(minimum_request_interval_seconds=-1.0)
