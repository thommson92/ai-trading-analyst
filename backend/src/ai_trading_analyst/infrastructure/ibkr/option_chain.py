"""``OptionsDataProvider`` auf Basis der IBKR-Optionsketten (ADR 0048).

Der Adapter enthaelt **keine** Fachregel. Er holt zweimal -- erst den Bauplan
der Kette, dann die Notierungen der ausgewaehlten Kontrakte -- und laesst
dazwischen und danach die Domain entscheiden. Dasselbe Muster wie beim
EDGAR-Adapter, der ``compute_fundamental_snapshot`` ruft.

Die Reihenfolge ist der Kern und keine Bequemlichkeit:

1. ``select_expiration`` waehlt aus den gelisteten Verfallsterminen einen,
2. ``select_strikes`` waehlt daraus die Strikes im Moneyness-Band,
3. **erst dann** wird notiert -- jede Notierung kostet eine
   Marktdatenanfrage,
4. ``build_options_analysis`` bewertet, was zurueckkam, und filtert ueber das
   tatsaechlich gelieferte Delta.

Ein Schaetzwert fuer das Delta vor Schritt 3 wuerde die Reihenfolge
umdrehen und waere ein erfundener Wert (CLAUDE.md).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from typing import Protocol

from ai_trading_analyst.domain.analysis import (
    ContractSpec,
    OptionsDataProviderError,
    Stock,
)
from ai_trading_analyst.domain.options import (
    OptionQuote,
    OptionsAnalysis,
    OptionsParameters,
    build_options_analysis,
    select_expiration,
    select_strikes,
    unzureichend,
)
from ai_trading_analyst.domain.technical import PriceZone
from ai_trading_analyst.observability.logging_setup import get_logger

from .bar_source import IbkrBarSourceError, OptionChainStructure

_logger = get_logger(__name__)


class OptionChainSource(Protocol):
    """Der Teil der TWS-Anbindung, den die Optionsanalyse braucht.

    Schmal geschnitten und als Protokoll geführt, damit der Adapter ohne
    laufende TWS pruefbar ist -- dasselbe Argument wie bei
    ``HistoricalBarSource`` und ``LiquidHoursSource``.
    """

    def option_chain(self, contract: ContractSpec) -> OptionChainStructure: ...

    def option_quotes(
        self,
        contract: ContractSpec,
        expiration: date,
        strikes: Sequence[float],
        market_data_type: int,
    ) -> Sequence[OptionQuote]: ...


class IbkrOptionsProvider:
    """Bewertete Cash-Secured-Put-Vorschlaege aus der IBKR-Optionskette."""

    def __init__(
        self,
        source: OptionChainSource,
        watchlist: Sequence[ContractSpec],
        parameters: OptionsParameters,
        market_data_type: int,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._source = source
        self._watchlist = tuple(watchlist)
        self._parameters = parameters
        self._market_data_type = market_data_type
        self._now = now

    def options(
        self,
        stock: Stock,
        *,
        price: float,
        as_of: date,
        zones: Sequence[PriceZone] = (),
        next_earnings_date: date | None = None,
    ) -> OptionsAnalysis:
        contract = next(
            (item for item in self._watchlist if item.symbol == stock.symbol), None
        )
        if contract is None:
            raise OptionsDataProviderError(
                f"'{stock.symbol}' steht nicht auf der konfigurierten IBKR-Watchlist."
            )

        try:
            struktur = self._source.option_chain(contract)
        except IbkrBarSourceError as error:
            raise OptionsDataProviderError(str(error)) from error

        evaluated_at = self._now()
        termin = select_expiration(
            struktur.expirations, as_of=as_of, parameters=self._parameters
        )
        if termin is None:
            return unzureichend(
                f"kein Verfallstermin zwischen {self._parameters.min_days_to_expiration} und "
                f"{self._parameters.max_days_to_expiration} Tagen gelistet "
                f"({len(struktur.expirations)} Termine in der Kette)",
                evaluated_at=evaluated_at,
                parameters=self._parameters,
                underlying_price=price,
            )

        strikes = select_strikes(struktur.strikes, price=price, parameters=self._parameters)
        if not strikes:
            return unzureichend(
                f"kein Strike zwischen {self._parameters.min_moneyness:.0%} und "
                f"{self._parameters.max_moneyness:.0%} des Kurses von {price:.2f} gelistet "
                f"({len(struktur.strikes)} Strikes in der Kette)",
                evaluated_at=evaluated_at,
                parameters=self._parameters,
                underlying_price=price,
                expiration=termin,
            )

        try:
            quotes = self._source.option_quotes(
                contract, termin, strikes, self._market_data_type
            )
        except IbkrBarSourceError as error:
            raise OptionsDataProviderError(str(error)) from error

        _logger.info(
            "%s: %d von %d angefragten Put-Notierungen zum %s erhalten",
            stock.symbol,
            len(quotes),
            len(strikes),
            termin.isoformat(),
        )
        return build_options_analysis(
            quotes,
            price=price,
            expiration=termin,
            as_of=as_of,
            evaluated_at=evaluated_at,
            parameters=self._parameters,
            zones=zones,
            next_earnings_date=next_earnings_date,
        )
