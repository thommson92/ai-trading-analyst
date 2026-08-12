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

from ai_trading_analyst.domain.analysis import MarketDataProvider, MarketDataProviderError, Stock
from ai_trading_analyst.domain.screening import (
    AggregationResult,
    CandleAggregationError,
    CandleSeries,
    IncompleteReason,
    IndicatorParameters,
    SessionParameters,
    aggregate_intraday_bars,
    compute_indicator_values,
)
from ai_trading_analyst.observability.logging_setup import get_logger

from .bar_source import ContractSpec, HistoricalBarSource, IbkrBarSourceError

_logger = get_logger(__name__)

_STOCK_NAMESPACE = uuid.UUID("a1c0d3e5-0000-4000-8000-000000000002")
"""Erzeugt zu einem Symbol immer dieselbe Aktien-ID, damit wiederholte Laeufe
dieselbe Aktie treffen. Die Repositories sind zusaetzlich ueber das Symbol
idempotent."""


class IbkrMarketDataProvider(MarketDataProvider):
    def __init__(
        self,
        bar_source: HistoricalBarSource,
        watchlist: Sequence[ContractSpec],
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
                id=uuid.uuid5(_STOCK_NAMESPACE, contract.symbol),
                symbol=contract.symbol,
                # Die Heimatboerse ist die aussagekraeftigere Angabe; "SMART"
                # ist nur der Weg zur Abfrage, keine Boerse.
                exchange=contract.primary_exchange or contract.exchange,
            )
            for contract in self._watchlist
        )

    def get_candle_series(self, stock: Stock) -> CandleSeries:
        contract = next(
            (item for item in self._watchlist if item.symbol == stock.symbol), None
        )
        if contract is None:
            raise MarketDataProviderError(
                f"'{stock.symbol}' steht nicht auf der konfigurierten IBKR-Watchlist."
            )

        try:
            bars = self._bar_source.fetch_intraday_bars(contract)
        except IbkrBarSourceError as error:
            raise MarketDataProviderError(str(error)) from error

        try:
            aggregated = aggregate_intraday_bars(
                bars, self._native_bar_minutes, self._session_parameters
            )
        except CandleAggregationError as error:
            raise MarketDataProviderError(
                f"Die Bars fuer '{stock.symbol}' ergeben keine gueltigen Kerzen: {error}"
            ) from error

        candles = aggregated.candles
        self._reject_gaps(stock.symbol, aggregated)
        self._report_short_sessions(stock.symbol, aggregated)

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

    def close(self) -> None:
        """Gibt die TWS-Verbindung frei -- beim Herunterfahren der Anwendung."""
        self._bar_source.close()

    @staticmethod
    def _report_short_sessions(symbol: str, aggregated: AggregationResult) -> None:
        """Protokolliert unvollstaendige Handelstage, statt sie zu verschweigen.

        Die Kerze entfaellt zu Recht, aber die Reihe hat an dieser Stelle
        einen Handelstag mit nur einer statt zwei Kerzen. Wer spaeter ein
        Ergebnis nachvollzieht, soll das sehen koennen, ohne es aus den
        Rohdaten zu rekonstruieren. Die laufende Kerze am Ende der Reihe ist
        der Normalfall und bleibt unerwaehnt.
        """
        if not aggregated.candles:
            return
        letzte_kerze = aggregated.candles[-1].timestamp
        gemeldet = {
            IncompleteReason.SESSION_ENDED: ("verkuerzter Handelstag", "verkuerzte Handelstage"),
            IncompleteReason.SESSION_STARTED_LATE: (
                "Handelstag mit spaetem Beginn",
                "Handelstage mit spaetem Beginn",
            ),
        }
        for grund, (einzahl, mehrzahl) in gemeldet.items():
            betroffen = [
                gap
                for gap in aggregated.incomplete
                if gap.reason is grund and gap.timestamp < letzte_kerze
            ]
            if not betroffen:
                continue
            _logger.info(
                "%s: %d %s in der Historie -- dort entfaellt je eine Kerze "
                "(frueheste: %s)",
                symbol,
                len(betroffen),
                einzahl if len(betroffen) == 1 else mehrzahl,
                betroffen[0].timestamp.date().isoformat(),
            )

    @staticmethod
    def _reject_gaps(symbol: str, aggregated: AggregationResult) -> None:
        """Trennt echte Datenluecken von Kerzen, die es nie geben konnte.

        Unbedenklich ist eine unvollstaendige Kerze, wenn die Sitzung dort
        endete (verkuerzter Handelstag, laufende Kerze am Ende der Reihe) oder
        erst dort begann (erster Handelstag nach einem Boersengang,
        Eroeffnungsunterbrechung). In beiden Faellen fehlt nichts, es hat nur
        nicht mehr oder noch nicht Handel gegeben.

        Alles andere ist eine Luecke mitten in einem gehandelten Zeitraum. Sie
        stillschweigend zu uebergehen waere der gefaehrlichere Weg: Die
        verbleibenden Kerzen waeren nicht mehr zusammenhaengend, und RSI und
        EMA wuerden ueber Kurse gerechnet, die in Wirklichkeit nicht
        aufeinander folgen -- ohne dass an den Ergebniswerten irgendetwas
        darauf hindeutet.
        """
        gaps = [
            gap for gap in aggregated.incomplete if gap.reason is IncompleteReason.DATA_GAP
        ]
        if not gaps:
            return

        erste = gaps[0]
        raise MarketDataProviderError(
            f"IBKR hat fuer '{symbol}' eine lueckenhafte Historie geliefert: zur Kerze "
            f"{erste.timestamp.isoformat()} fehlen Bars ({erste.received_bars} von "
            f"{erste.expected_bars}), der erste ab {erste.first_missing_bar.isoformat()}. "
            "Weder ein verkuerzter Handelstag noch ein spaeter Handelsbeginn erklaeren das; "
            f"insgesamt {len(gaps)} betroffene Kerzen. Eine Kerzenreihe mit Loechern wuerde "
            "falsche Indikatorwerte ergeben."
        )
