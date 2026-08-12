"""Der IBKR-Provider gegen eine eingesetzte Barquelle.

Kein Test hier braucht eine laufende TWS, ein IBKR-Konto oder Netzwerk: Der
Provider haengt nur an ``HistoricalBarSource``, und genau diese Naht wird
besetzt. Geprueft wird das Zusammenspiel -- Bars rein, Kerzen mit Indikatoren
raus -- und vor allem das Verhalten im Fehlerfall, der im Betrieb der
Normalfall ist (TWS nach einem Neustart nicht angemeldet).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from ai_trading_analyst.domain.analysis import MarketDataProviderError, Stock
from ai_trading_analyst.domain.screening import (
    IndicatorParameters,
    IntradayBar,
    SessionParameters,
)
from ai_trading_analyst.infrastructure.ibkr.bar_source import ContractSpec, IbkrBarSourceError
from ai_trading_analyst.infrastructure.ibkr.market_data_provider import IbkrMarketDataProvider

NEW_YORK = ZoneInfo("America/New_York")
SESSION = SessionParameters(
    timezone="America/New_York",
    session_open=time(9, 30),
    session_minutes=390,
    timeframe_minutes=195,
)
INDICATORS = IndicatorParameters(
    rsi_length=14,
    rsi_method="wilder",
    rsi_ma_length=14,
    rsi_ma_type="sma",
    fast_ema_length=5,
    slow_ema_length=20,
)
WATCHLIST = (
    ContractSpec(symbol="AAPL", primary_exchange="NASDAQ"),
    ContractSpec(symbol="MSFT", primary_exchange="NASDAQ"),
)


class FakeBarSource:
    """Liefert vorbereitete Bars oder scheitert kontrolliert."""

    def __init__(
        self,
        bars_by_symbol: dict[str, Sequence[IntradayBar]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._bars_by_symbol = bars_by_symbol or {}
        self._error = error
        self.calls: list[ContractSpec] = []
        self.closed = 0

    def fetch_intraday_bars(self, contract: ContractSpec) -> Sequence[IntradayBar]:
        self.calls.append(contract)
        if self._error is not None:
            raise self._error
        return self._bars_by_symbol.get(contract.symbol, ())

    def close(self) -> None:
        self.closed += 1


def trading_days(count: int, first_day: date = date(2026, 3, 2)) -> list[IntradayBar]:
    """Vollstaendige Handelstage zu je zwei Kerzen, mit steigendem Kurs."""
    bars: list[IntradayBar] = []
    price = 100.0
    for day_offset in range(count):
        session_start = datetime.combine(
            first_day + timedelta(days=day_offset), time(9, 30), tzinfo=NEW_YORK
        )
        for index in range(26):
            price += 0.5
            bars.append(
                IntradayBar(
                    start=session_start + timedelta(minutes=15 * index),
                    open=price,
                    high=price + 0.25,
                    low=price - 0.25,
                    close=price,
                    volume=1_000.0,
                )
            )
    return bars


def build_provider(bar_source: FakeBarSource) -> IbkrMarketDataProvider:
    return IbkrMarketDataProvider(
        bar_source=bar_source,
        watchlist=WATCHLIST,
        session_parameters=SESSION,
        indicator_parameters=INDICATORS,
        native_bar_minutes=15,
    )


class TestListStocks:
    def test_liefert_die_konfigurierte_watchlist(self) -> None:
        stocks = build_provider(FakeBarSource()).list_stocks()
        assert [stock.symbol for stock in stocks] == ["AAPL", "MSFT"]

    def test_dieselbe_aktie_erhaelt_ueber_laeufe_hinweg_dieselbe_id(self) -> None:
        erste = build_provider(FakeBarSource()).list_stocks()
        zweite = build_provider(FakeBarSource()).list_stocks()
        assert [stock.id for stock in erste] == [stock.id for stock in zweite]

    def test_leere_watchlist_liefert_keine_aktien_statt_eines_platzhalters(self) -> None:
        provider = IbkrMarketDataProvider(
            bar_source=FakeBarSource(),
            watchlist=(),
            session_parameters=SESSION,
            indicator_parameters=INDICATORS,
            native_bar_minutes=15,
        )
        assert provider.list_stocks() == ()


class TestGetCandleSeries:
    def test_bars_werden_zu_kerzen_mit_indikatoren(self) -> None:
        provider = build_provider(FakeBarSource({"AAPL": trading_days(20)}))
        stock = provider.list_stocks()[0]

        series = provider.get_candle_series(stock)

        assert len(series) == 40
        assert len(series.indicators) == 40
        letzte = series.indicator(len(series) - 1)
        assert letzte.rsi is not None
        assert letzte.rsi_ma is not None
        assert letzte.ema5 is not None
        assert letzte.ema20 is not None

    def test_der_kontraktzuschnitt_der_watchlist_wird_durchgereicht(self) -> None:
        bar_source = FakeBarSource({"AAPL": trading_days(20)})
        provider = build_provider(bar_source)
        provider.get_candle_series(provider.list_stocks()[0])
        assert bar_source.calls == [ContractSpec(symbol="AAPL", primary_exchange="NASDAQ")]

    def test_am_anfang_der_reihe_fehlen_indikatorwerte_statt_geraten_zu_werden(self) -> None:
        provider = build_provider(FakeBarSource({"AAPL": trading_days(20)}))
        erste = provider.get_candle_series(provider.list_stocks()[0]).indicator(0)
        assert (erste.rsi, erste.rsi_ma, erste.ema5, erste.ema20) == (None, None, None, None)

    def test_eine_laufende_kerze_kommt_nicht_in_die_reihe(self) -> None:
        bars = trading_days(1)[:20]  # erste Kerze vollstaendig, zweite laeuft
        provider = build_provider(FakeBarSource({"AAPL": bars}))
        series = provider.get_candle_series(provider.list_stocks()[0])
        assert len(series) == 1
        assert series.candle(0).daily_candle_index == 1


class TestFehlerverhalten:
    def test_nicht_erreichbare_tws_wird_als_providerfehler_gemeldet(self) -> None:
        bar_source = FakeBarSource(
            error=IbkrBarSourceError("Keine Verbindung zur TWS auf 127.0.0.1:7496")
        )
        provider = build_provider(bar_source)
        with pytest.raises(MarketDataProviderError, match="Keine Verbindung zur TWS"):
            provider.get_candle_series(provider.list_stocks()[0])

    def test_ohne_abgeschlossene_kerze_gibt_es_keine_leere_reihe_sondern_einen_fehler(
        self,
    ) -> None:
        provider = build_provider(FakeBarSource({"AAPL": trading_days(1)[:5]}))
        with pytest.raises(MarketDataProviderError, match="keine einzige abgeschlossene"):
            provider.get_candle_series(provider.list_stocks()[0])

    def test_unbrauchbare_bars_werden_als_providerfehler_gemeldet(self) -> None:
        bars = trading_days(1)
        provider = build_provider(FakeBarSource({"AAPL": [*bars, bars[0]]}))
        with pytest.raises(MarketDataProviderError, match="keine gueltigen Kerzen"):
            provider.get_candle_series(provider.list_stocks()[0])

    def test_aktie_ausserhalb_der_watchlist_wird_abgelehnt(self) -> None:
        provider = build_provider(FakeBarSource())
        fremde = Stock(id=provider.list_stocks()[0].id, symbol="TSLA", exchange="SMART")
        with pytest.raises(MarketDataProviderError, match="Watchlist"):
            provider.get_candle_series(fremde)


class TestLueckenInDerHistorie:
    """Eine fehlende Kerze mitten in der Reihe darf nicht stillschweigend
    herausfallen: RSI und EMA wuerden sonst ueber Kurse gerechnet, die gar
    nicht aufeinander folgen."""

    def test_eine_fehlende_kerze_mitten_in_der_historie_wird_zum_fehler(self) -> None:
        bars = trading_days(20)
        del bars[3]  # ein Bar aus der ersten Kerze des ersten Tages
        provider = build_provider(FakeBarSource({"AAPL": bars}))
        with pytest.raises(MarketDataProviderError, match="lueckenhafte Historie"):
            provider.get_candle_series(provider.list_stocks()[0])

    def test_die_fehlermeldung_benennt_die_betroffene_kerze(self) -> None:
        bars = trading_days(20)
        del bars[3]
        provider = build_provider(FakeBarSource({"AAPL": bars}))
        with pytest.raises(MarketDataProviderError, match="12 von 13"):
            provider.get_candle_series(provider.list_stocks()[0])

    def test_eine_laufende_kerze_am_ende_ist_keine_luecke(self) -> None:
        bars = trading_days(20)[:-6]  # letzte Kerze unvollstaendig
        provider = build_provider(FakeBarSource({"AAPL": bars}))
        series = provider.get_candle_series(provider.list_stocks()[0])
        assert len(series) == 39

    def test_die_fehlermeldung_benennt_den_ersten_fehlenden_bar(self) -> None:
        bars = trading_days(20)
        del bars[3]
        provider = build_provider(FakeBarSource({"AAPL": bars}))
        with pytest.raises(MarketDataProviderError, match="ab 2026-03-02T10:15:00"):
            provider.get_candle_series(provider.list_stocks()[0])

    def test_ein_spaeter_handelsbeginn_ist_keine_luecke(self) -> None:
        """Der Fall SPCX vom 12.06.2026, live gegen die TWS aufgetreten.

        Am ersten Handelstag nach einem Boersengang beginnt der Handel erst
        mittags. Die erste Kerze des Tages entfaellt, die Reihe bleibt
        gueltig -- ein Fehler haette die Aktie dauerhaft aus dem Screening
        genommen.
        """
        bars = trading_days(20)
        del bars[:9]  # Handel beginnt erst um 11:45 statt 09:30
        provider = build_provider(FakeBarSource({"AAPL": bars}))

        series = provider.get_candle_series(provider.list_stocks()[0])

        assert len(series) == 39  # 40 minus die erste Kerze des ersten Tages

    def test_ein_verkuerzter_handelstag_mitten_in_der_historie_ist_keine_luecke(self) -> None:
        """Der Fall vom 28.11.2025, live gegen die TWS aufgetreten.

        An einem verkuerzten Handelstag kann die zweite Kerze nicht
        vollstaendig werden. Sie entfaellt, die Reihe bleibt gueltig -- ein
        Fehler waere hier falsch und haette die gesamte Watchlist blockiert.
        """
        bars = trading_days(20)
        # Vom fuenften Handelstag nur die ersten 14 Bars behalten: 09:30-13:00.
        del bars[4 * 26 + 14 : 5 * 26]
        provider = build_provider(FakeBarSource({"AAPL": bars}))

        series = provider.get_candle_series(provider.list_stocks()[0])

        assert len(series) == 39  # 40 minus die zweite Kerze des kurzen Tages
        assert series.indicator(len(series) - 1).ema20 is not None


class TestVerbindungsfreigabe:
    def test_close_reicht_bis_zur_barquelle_durch(self) -> None:
        bar_source = FakeBarSource()
        provider = build_provider(bar_source)
        provider.close()
        assert bar_source.closed == 1
