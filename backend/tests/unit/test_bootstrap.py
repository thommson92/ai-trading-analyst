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

import httpx
import pytest
from pydantic import ValidationError

from ai_trading_analyst.bootstrap import (
    build_analyst_recommendations_provider,
    build_backtest_params,
    build_bar_source,
    build_earnings_provider,
    build_finnhub_earnings_provider,
    build_fundamental_data_provider,
    build_market_data_provider,
    build_research_provider,
    build_scoring_params,
    build_technical_interpreter,
    project_root,
)
from ai_trading_analyst.config.loader import load_config
from ai_trading_analyst.config.settings import (
    AnalystRatingsConfig,
    AppConfig,
    EarningsFilterConfig,
    EdgarConfig,
    FinnhubConfig,
    FundamentalsConfig,
    IbkrConfig,
    IndicatorConfig,
    MarketDataConfig,
    MetricThresholdConfig,
    MissingSecretError,
    ResearchConfig,
    ScoringConfig,
    ScreeningConfig,
    Secrets,
    TechnicalAgentConfig,
)
from ai_trading_analyst.domain.fundamentals import MetricName
from ai_trading_analyst.domain.scoring import SCORED_METRICS, ComponentName
from ai_trading_analyst.infrastructure.anthropic import (
    AnthropicResearchProvider,
    AnthropicTechnicalInterpreter,
)
from ai_trading_analyst.infrastructure.anthropic.client import VERBINDUNGSAUFBAU_SEKUNDEN
from ai_trading_analyst.infrastructure.edgar import EdgarFundamentalDataProvider
from ai_trading_analyst.infrastructure.finnhub import (
    FinnhubAnalystRecommendationsProvider,
    FinnhubEarningsProvider,
)
from ai_trading_analyst.infrastructure.fixtures.analyst_recommendations_provider import (
    FixtureAnalystRecommendationsProvider,
)
from ai_trading_analyst.infrastructure.fixtures.earnings_provider import FixtureEarningsProvider
from ai_trading_analyst.infrastructure.fixtures.fundamental_provider import (
    FixtureFundamentalDataProvider,
)
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


class TestFundamentalAnbieterauswahl:
    def test_standard_ist_der_fixture_anbieter(self) -> None:
        config = AppConfig(indicators=INDICATORS)
        assert config.fundamentals.provider == "fixture"
        assert isinstance(
            build_fundamental_data_provider(config, Secrets(_env_file=None)),
            FixtureFundamentalDataProvider,
        )

    def test_edgar_ohne_kontaktadresse_scheitert_verstaendlich(self) -> None:
        """Die SEC verlangt sie im User-Agent und antwortet ohne sie mit 403.
        Der Fehler kommt hier statt als 403 mitten im Lauf."""
        config = AppConfig(
            indicators=INDICATORS, fundamentals=FundamentalsConfig(provider="edgar")
        )
        with pytest.raises(MissingSecretError, match="ATA_EDGAR_CONTACT"):
            build_fundamental_data_provider(config, Secrets(_env_file=None))

    def test_eine_leere_kontaktadresse_zaehlt_als_nicht_gesetzt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``ATA_EDGAR_CONTACT=`` aus der ``.env.example`` darf nicht als
        gesetzt durchgehen -- sonst faende der Fehler erst als 403 statt."""
        monkeypatch.setenv("ATA_EDGAR_CONTACT", "   ")
        config = AppConfig(
            indicators=INDICATORS, fundamentals=FundamentalsConfig(provider="edgar")
        )
        with pytest.raises(MissingSecretError, match="ATA_EDGAR_CONTACT"):
            build_fundamental_data_provider(config, Secrets(_env_file=None))

    def test_edgar_mit_kontaktadresse_wird_ohne_netzwerkzugriff_gebaut(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATA_EDGAR_CONTACT", "pruefer@example.org")
        config = AppConfig(
            indicators=INDICATORS, fundamentals=FundamentalsConfig(provider="edgar")
        )
        assert isinstance(
            build_fundamental_data_provider(config, Secrets(_env_file=None)),
            EdgarFundamentalDataProvider,
        )

    def test_die_kontaktadresse_steht_nicht_in_der_konfiguration(self) -> None:
        """Das Repository ist oeffentlich. Eine wieder eingefuegte
        ``contact``-Zeile in ``config/default.yaml`` soll den Start brechen und
        nicht still eine private Mailadresse veroeffentlichen."""
        assert "contact" not in EdgarConfig.model_fields
        with pytest.raises(ValidationError):
            EdgarConfig(contact="wer@example.org")  # type: ignore[call-arg]


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

    def test_timeout_und_wiederholungszahl_kommen_beim_anbieter_an(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dieselbe Luecke wie bei ``max_citations``, nur teurer.

        ``build_client`` ist fuer sich getestet -- aber niemand prueft, dass
        der Adapter seine Konfiguration dorthin durchreicht. Faellt die
        Weitergabe weg, gilt still der SDK-Standard: zwei Wiederholungen einer
        Anfrage, die 900 Sekunden dauern darf. Genau die stillen, trotzdem
        berechneten Versuche, gegen die die Einstellung gebaut ist.
        """
        monkeypatch.setenv("ATA_LLM_API_KEY", "test-key")
        config = AppConfig(
            indicators=INDICATORS,
            research=ResearchConfig(
                provider="anthropic", request_timeout_seconds=123, max_retries=0
            ),
        )
        provider = build_research_provider(config, Secrets(_env_file=None))
        assert isinstance(provider, AnthropicResearchProvider)
        assert provider._client.max_retries == 0
        timeout = provider._client.timeout
        assert isinstance(timeout, httpx.Timeout)
        assert timeout.read == 123.0
        assert timeout.connect == VERBINDUNGSAUFBAU_SEKUNDEN


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

    def test_timeout_und_wiederholungszahl_kommen_beim_interpreter_an(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dieselbe Zusicherung wie beim Research-Adapter -- beide bauen ihren
        Client ueber ``build_client``, und beide koennten die Weitergabe
        verlieren, ohne dass etwas rot wird."""
        monkeypatch.setenv("ATA_LLM_API_KEY", "test-key")
        config = AppConfig(
            indicators=INDICATORS,
            technical_agent=TechnicalAgentConfig(
                provider="anthropic", request_timeout_seconds=45, max_retries=3
            ),
        )
        interpreter = build_technical_interpreter(config, Secrets(_env_file=None))
        assert isinstance(interpreter, AnthropicTechnicalInterpreter)
        assert interpreter._client.max_retries == 3
        timeout = interpreter._client.timeout
        assert isinstance(timeout, httpx.Timeout)
        assert timeout.read == 45.0
        assert timeout.connect == VERBINDUNGSAUFBAU_SEKUNDEN

    def test_das_modellprofil_kommt_aus_llm_technical(self) -> None:
        """Nicht aus ``llm.research``: Der Technical Agent interpretiert nur
        bereits gerechnete Werte und laeuft deshalb auf einem guenstigeren
        Modell (ADR 0021, Modellstufung)."""
        config = AppConfig(indicators=INDICATORS)
        assert config.llm.technical.model != config.llm.research.model


class TestAnalystenAnbieterauswahl:
    """ADR 0043 -- Auswahl und Verdrahtung.

    Die Verdrahtung ist der eigentliche Punkt: ``months`` und
    ``request_timeout_seconds`` sind beide ``PositiveInt``, eine Verwechslung
    waere typkorrekt und bliebe ohne Test gruen.
    """

    def test_standard_ist_der_fixture_anbieter(self) -> None:
        config = AppConfig(indicators=INDICATORS)
        assert config.analyst_ratings.provider == "fixture"
        provider = build_analyst_recommendations_provider(config, Secrets(_env_file=None))
        assert isinstance(provider, FixtureAnalystRecommendationsProvider)

    def test_finnhub_ohne_secret_scheitert_verstaendlich(self) -> None:
        config = AppConfig(
            indicators=INDICATORS,
            analyst_ratings=AnalystRatingsConfig(provider="finnhub"),
        )
        with pytest.raises(MissingSecretError, match="ATA_FINNHUB_API_KEY"):
            build_analyst_recommendations_provider(config, Secrets(_env_file=None))

    def test_finnhub_mit_secret_wird_ohne_netzwerkzugriff_gebaut(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATA_FINNHUB_API_KEY", "test-key")
        config = AppConfig(
            indicators=INDICATORS,
            analyst_ratings=AnalystRatingsConfig(provider="finnhub"),
        )
        provider = build_analyst_recommendations_provider(config, Secrets(_env_file=None))
        assert isinstance(provider, FinnhubAnalystRecommendationsProvider)

    def test_jede_einstellung_landet_an_ihrem_platz(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Alle drei Zahlen **verschieden**: Bei gleichen Werten koennte eine
        Vertauschung von ``months`` und ``request_timeout_seconds`` nicht
        auffallen."""
        monkeypatch.setenv("ATA_FINNHUB_API_KEY", "test-key")
        config = AppConfig(
            indicators=INDICATORS,
            analyst_ratings=AnalystRatingsConfig(provider="finnhub", months=6),
            finnhub=FinnhubConfig(base_url="https://example.test/v1", request_timeout_seconds=3),
        )

        provider = build_analyst_recommendations_provider(config, Secrets(_env_file=None))

        assert isinstance(provider, FinnhubAnalystRecommendationsProvider)
        assert provider._settings.months == 6
        assert provider._settings.request_timeout_seconds == 3.0
        assert provider._settings.base_url == "https://example.test/v1"
        assert provider._settings.api_key == "test-key"


class TestFinnhubAbschnittWirdRichtigVerdrahtet:
    """ADR 0043 hat Host und Zeitgrenze aus ``earnings_filter`` herausgeloest.

    Der Schematest prueft, dass die Schluessel am neuen Ort liegen. Hier geht
    es darum, dass der Earnings-Adapter sie auch **von dort** liest -- und das
    Kalenderfenster weiterhin von seinem alten Platz.
    """

    def test_der_earnings_adapter_liest_host_und_fenster_von_zwei_stellen(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATA_FINNHUB_API_KEY", "test-key")
        config = AppConfig(
            indicators=INDICATORS,
            finnhub=FinnhubConfig(base_url="https://example.test/v1", request_timeout_seconds=3),
            earnings_filter=EarningsFilterConfig(
                provider="finnhub", lookahead_calendar_days=45
            ),
        )

        provider = build_finnhub_earnings_provider(config, Secrets(_env_file=None))

        assert provider._settings.base_url == "https://example.test/v1"
        assert provider._settings.request_timeout_seconds == 3.0
        # Aus dem **anderen** Abschnitt -- der Wert beschreibt den Endpunkt,
        # nicht den Zugang.
        assert provider._settings.lookahead_calendar_days == 45

    def test_beide_endpunkte_teilen_sich_einen_schluessel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ein Konto, ein Schluessel -- wer nur einen der beiden scharf
        schaltet, braucht ihn trotzdem ganz."""
        monkeypatch.setenv("ATA_FINNHUB_API_KEY", "gemeinsamer-schluessel")
        config = AppConfig(
            indicators=INDICATORS,
            earnings_filter=EarningsFilterConfig(provider="finnhub"),
            analyst_ratings=AnalystRatingsConfig(provider="finnhub"),
        )

        earnings = build_finnhub_earnings_provider(config, Secrets(_env_file=None))
        ratings = build_analyst_recommendations_provider(config, Secrets(_env_file=None))

        assert isinstance(ratings, FinnhubAnalystRecommendationsProvider)
        assert earnings._settings.api_key == ratings._settings.api_key


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


class TestScoringParameter:
    """Die eine Stelle, die Konfiguration und Domain zugleich kennt.

    ``config`` kennt die Kennzahlenliste nicht, die Domain kennt keine
    YAML-Datei. Ein Tippfehler im Kennzahlennamen kann deshalb nur hier
    auffallen -- und er soll beim Start auffallen, nicht als
    stillschweigend uebersprungene Kennzahl in einem Ergebnis.
    """

    @staticmethod
    def _thresholds(**overrides: MetricThresholdConfig) -> dict[str, MetricThresholdConfig]:
        vollstaendig = {
            name.value: MetricThresholdConfig(
                boundaries=(1.0, 2.0, 3.0, 4.0), higher_is_better=True
            )
            for name in SCORED_METRICS
        }
        vollstaendig.update(overrides)
        return vollstaendig

    def _config(self, thresholds: dict[str, MetricThresholdConfig]) -> AppConfig:
        return AppConfig(indicators=INDICATORS, scoring=ScoringConfig(thresholds=thresholds))

    def test_werte_kommen_unveraendert_aus_der_konfiguration(self) -> None:
        config = self._config(self._thresholds())
        params = build_scoring_params(config)
        assert params.minimum_coverage == config.scoring.minimum_coverage
        assert params.normal_confidence_coverage == config.scoring.normal_confidence_coverage
        assert params.swing_version == config.scoring.swing_version
        assert params.long_term_version == config.scoring.long_term_version

    def test_die_feldnamen_werden_zu_komponentennamen(self) -> None:
        params = build_scoring_params(self._config(self._thresholds()))
        assert params.swing_weights[ComponentName.TECHNICAL_SIGNALS] == 0.25
        assert params.long_term_weights[ComponentName.BALANCE_SHEET_QUALITY] == 0.20
        assert set(params.long_term_weights) == {
            ComponentName.PROFITABILITY,
            ComponentName.GROWTH,
            ComponentName.VALUATION,
            ComponentName.BALANCE_SHEET_QUALITY,
        }

    def test_eine_fehlende_schwelle_bricht_den_start_ab(self) -> None:
        """Ohne Abbruch fiele die Kennzahl still aus der Komponente -- und
        der Score saehe vollstaendig aus."""
        unvollstaendig = self._thresholds()
        del unvollstaendig[MetricName.NET_MARGIN.value]
        with pytest.raises(ValueError, match="NET_MARGIN"):
            build_scoring_params(self._config(unvollstaendig))

    def test_ein_unbekannter_kennzahlenname_bricht_den_start_ab(self) -> None:
        with pytest.raises(ValueError, match="NETTOMARGE"):
            build_scoring_params(self._config(self._thresholds(NETTOMARGE=MetricThresholdConfig(
                boundaries=(1.0, 2.0, 3.0, 4.0), higher_is_better=True
            ))))

    def test_eine_signalzahl_ohne_teilwert_bricht_den_start_ab(self) -> None:
        """``SIGNAL_TEILWERTE`` kennt drei und zwei Signale, weil
        ``required_signal_count`` auf zwei steht. Auf eins gesetzt verloere
        jeder Ein-Signal-Kandidat still ein Viertel des Swing-Gewichts."""
        config = AppConfig(
            indicators=INDICATORS,
            screening=ScreeningConfig(required_signal_count=1),
            scoring=ScoringConfig(thresholds=self._thresholds()),
        )
        with pytest.raises(ValueError, match="keinen Teilwert"):
            build_scoring_params(config)

    def test_die_ausgelieferte_konfiguration_reicht_aus(self) -> None:
        """Der Test, der die echte ``config/default.yaml`` prueft: Sie ist
        das, was auf dem Server laeuft."""
        params = build_scoring_params(load_config().config)
        assert SCORED_METRICS <= params.thresholds.keys()
        assert params.thresholds[MetricName.PRICE_EARNINGS_RATIO].higher_is_better is False
