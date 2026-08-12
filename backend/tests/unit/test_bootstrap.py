"""Auswahl des Marktdatenanbieters in der Composition Root.

Der Rest von ``build_app`` braucht eine Datenbank und wird in den
Integrationstests geprueft. Die Anbieterauswahl selbst ist eine reine
Entscheidung ueber der Konfiguration und gehoert deshalb hierher: Sie
entscheidet, ob ein Lauf mit Fixture-Daten oder gegen die echte TWS arbeitet
-- eine Verwechslung waere im Betrieb teuer.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_trading_analyst.bootstrap import build_market_data_provider, project_root
from ai_trading_analyst.config.settings import (
    AppConfig,
    IbkrConfig,
    IndicatorConfig,
    MarketDataConfig,
)
from ai_trading_analyst.infrastructure.fixtures.market_data_provider import (
    FixtureMarketDataProvider,
)
from ai_trading_analyst.infrastructure.ibkr import ContractSpec, IbkrMarketDataProvider
from ai_trading_analyst.infrastructure.watchlists import WatchlistError

INDICATORS = IndicatorConfig(
    rsi_length=14,
    rsi_method="wilder",
    rsi_ma_length=14,
    rsi_ma_type="sma",
    fast_ema_length=5,
    slow_ema_length=20,
    warmup_candles=250,
)


def ibkr_config(**overrides: object) -> AppConfig:
    return AppConfig(
        market_data=MarketDataConfig(provider="ibkr", ibkr=IbkrConfig(**overrides)),
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

    def test_ein_fehlendes_watchlist_verzeichnis_scheitert_beim_start(
        self, tmp_path: Path
    ) -> None:
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


class TestProjektwurzel:
    def test_die_wurzel_liegt_ueber_dem_konfigurationsverzeichnis(self, tmp_path: Path) -> None:
        assert project_root(tmp_path / "config" / "default.yaml") == tmp_path


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
