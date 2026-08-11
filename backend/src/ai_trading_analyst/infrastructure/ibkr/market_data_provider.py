"""``MarketDataProvider`` auf Basis der Interactive-Brokers-TWS-API.

Der erste produktive Marktdatenanbieter des Projekts (ADR 0014). Er setzt drei
Bausteine zusammen, die jeweils fuer sich getestet sind:

1. ``HistoricalBarSource`` liefert native Intraday-Bars (Infrastruktur),
2. ``aggregate_intraday_bars`` bildet daraus abgeschlossene
   195-Minuten-Kerzen (Domain),
3. ``compute_indicator_values`` berechnet RSI, RSI-MA, EMA5 und EMA20
   (Domain).

Der Provider selbst enthaelt keine Fachregel -- er verbindet nur. Faellt
irgendetwas davon aus, meldet er ``MarketDataProviderError``; der Use Case
isoliert den Fehler auf diese eine Aktie und der Screener stuft sie als
``UNKNOWN_DATA_INCOMPLETE`` ein. An keiner Stelle wird ein fehlender Wert
ersetzt oder geschaetzt.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from ai_trading_analyst.domain.analysis import MarketDataProvider, MarketDataProviderError, Stock
from ai_trading_analyst.domain.screening import (
    CandleAggregationError,
    CandleSeries,
    IndicatorParameters,
    SessionParameters,
    aggregate_intraday_bars,
    compute_indicator_values,
)

from .bar_source import HistoricalBarSource, IbkrBarSourceError

_STOCK_NAMESPACE = uuid.UUID("a1c0d3e5-0000-4000-8000-000000000002")
"""Erzeugt zu einem Symbol immer dieselbe Aktien-ID, damit wiederholte Laeufe
dieselbe Aktie treffen. Die Repositories sind zusaetzlich ueber das Symbol
idempotent."""


@dataclass(frozen=True, slots=True)
class WatchlistEntry:
    """Eine ueberwachte Aktie und ihr IBKR-Kontraktzuschnitt."""

    symbol: str
    exchange: str
    currency: str


class IbkrMarketDataProvider(MarketDataProvider):
    def __init__(
        self,
        bar_source: HistoricalBarSource,
        watchlist: Sequence[WatchlistEntry],
        session_parameters: SessionParameters,
        indicator_parameters: IndicatorParameters,
        native_bar_minutes: int,
    ) -> None:
        self._bar_source = bar_source
        self._watchlist = tuple(watchlist)
        self._session_parameters = session_parameters
        self._indicator_parameters = indicator_parameters
        self._native_bar_minutes = native_bar_minutes

    def list_stocks(self) -> Sequence[Stock]:
        """Liefert die konfigurierte Watchlist.

        Der Import einer bei IBKR gefuehrten Watchlist ist ein eigener Schritt
        (Sprint 2) -- bis dahin ist die Liste Konfiguration.
        """
        return tuple(
            Stock(
                id=uuid.uuid5(_STOCK_NAMESPACE, entry.symbol),
                symbol=entry.symbol,
                exchange=entry.exchange,
            )
            for entry in self._watchlist
        )

    def get_candle_series(self, stock: Stock) -> CandleSeries:
        entry = next((item for item in self._watchlist if item.symbol == stock.symbol), None)
        if entry is None:
            raise MarketDataProviderError(
                f"'{stock.symbol}' steht nicht auf der konfigurierten IBKR-Watchlist."
            )

        try:
            bars = self._bar_source.fetch_intraday_bars(
                entry.symbol, entry.exchange, entry.currency
            )
        except IbkrBarSourceError as error:
            raise MarketDataProviderError(str(error)) from error

        try:
            candles = aggregate_intraday_bars(
                bars, self._native_bar_minutes, self._session_parameters
            )
        except CandleAggregationError as error:
            raise MarketDataProviderError(
                f"Die Bars fuer '{stock.symbol}' ergeben keine gueltigen Kerzen: {error}"
            ) from error

        if not candles:
            raise MarketDataProviderError(
                f"IBKR hat fuer '{stock.symbol}' keine einzige abgeschlossene "
                f"{self._session_parameters.timeframe_minutes}-Minuten-Kerze geliefert "
                f"({len(bars)} native Bars empfangen)."
            )

        indicators = compute_indicator_values(
            [candle.close for candle in candles], self._indicator_parameters
        )
        return CandleSeries(candles=candles, indicators=indicators)
