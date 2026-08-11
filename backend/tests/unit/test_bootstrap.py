"""Auswahl des Marktdatenanbieters in der Composition Root.

Der Rest von ``build_app`` braucht eine Datenbank und wird in den
Integrationstests geprueft. Die Anbieterauswahl selbst ist eine reine
Entscheidung ueber der Konfiguration und gehoert deshalb hierher: Sie
entscheidet, ob ein Lauf mit Fixture-Daten oder gegen die echte TWS arbeitet
-- eine Verwechslung waere im Betrieb teuer.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_trading_analyst.bootstrap import build_market_data_provider
from ai_trading_analyst.config.settings import (
    AppConfig,
    IbkrConfig,
    IbkrWatchlistEntryConfig,
    IndicatorConfig,
    MarketDataConfig,
)
from ai_trading_analyst.infrastructure.fixtures.market_data_provider import (
    FixtureMarketDataProvider,
)
from ai_trading_analyst.infrastructure.ibkr import IbkrMarketDataProvider

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
    watchlist = (IbkrWatchlistEntryConfig(symbol="AAPL"),)
    return AppConfig(
        market_data=MarketDataConfig(
            provider="ibkr", ibkr=IbkrConfig(watchlist=watchlist, **overrides)
        ),
        indicators=INDICATORS,
    )


class TestAnbieterauswahl:
    def test_standard_ist_der_fixture_anbieter(self) -> None:
        config = AppConfig(indicators=INDICATORS)
        assert config.market_data.provider == "fixture"
        assert isinstance(build_market_data_provider(config, INDICATORS), FixtureMarketDataProvider)

    def test_ibkr_wird_nur_auf_ausdrueckliche_konfiguration_gebaut(self) -> None:
        provider = build_market_data_provider(ibkr_config(), INDICATORS)
        assert isinstance(provider, IbkrMarketDataProvider)

    def test_die_konfigurierte_watchlist_landet_im_anbieter(self) -> None:
        provider = build_market_data_provider(ibkr_config(), INDICATORS)
        stocks = provider.list_stocks()
        assert [stock.symbol for stock in stocks] == ["AAPL"]
        assert [stock.exchange for stock in stocks] == ["SMART"]

    def test_der_aufbau_stellt_keine_verbindung_her(self) -> None:
        """Ein Anwendungsstart ohne laufende TWS darf nicht scheitern.

        Die Verbindung entsteht erst beim ersten Abruf -- ADR 0014, E2: Nach
        einem Neustart laeuft die TWS erst nach manueller Anmeldung wieder,
        und bis dahin soll die Anwendung startfaehig bleiben.
        """
        provider = build_market_data_provider(
            ibkr_config(host="127.0.0.1", port=1), INDICATORS
        )
        assert isinstance(provider, IbkrMarketDataProvider)


class TestKonfigurationspruefung:
    def test_eine_bar_groesse_die_die_kerze_nicht_fuellt_faellt_beim_laden_auf(self) -> None:
        with pytest.raises(ValidationError, match="ohne Rest"):
            AppConfig(
                market_data=MarketDataConfig(ibkr=IbkrConfig(native_bar_minutes=7)),
                indicators=INDICATORS,
            )
