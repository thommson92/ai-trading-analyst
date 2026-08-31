"""``OptionsDataProvider`` auf Basis der IBKR-Optionsketten (ADR 0048).

Der Adapter enthaelt **keine** Fachregel. Er holt dreimal und laesst
dazwischen jedes Mal die Domain entscheiden -- dasselbe Muster wie beim
EDGAR-Adapter, der ``compute_fundamental_snapshot`` ruft.

Die Reihenfolge ist der Kern und keine Bequemlichkeit:

1. ``option_chain`` liefert die Verfallstermine, ``select_expiration`` waehlt
   einen aus,
2. ``option_strikes`` liefert die zu **diesem** Termin gelisteten Strikes,
   ``select_strikes`` waehlt daraus das Moneyness-Band,
3. **erst dann** wird notiert -- jede Notierung kostet eine
   Marktdatenanfrage,
4. ``build_options_analysis`` bewertet, was zurueckkam, und filtert ueber das
   tatsaechlich gelieferte Delta.

Schritt 2 ist ein eigener Abruf, weil ein gemessener Befund es verlangt:
``reqSecDefOptParams`` liefert die **Vereinigung** aller Strikes ueber alle
Verfallstermine, und die Wochenoptionen haben engere Abstaende als die
Monatstermine. Ohne diesen Schritt gingen am 2026-08-31 bei AAPL sechs von
zwoelf Anfragen an Kontrakte, die es zu diesem Termin nicht gibt.

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

    def option_strikes(
        self, contract: ContractSpec, expiration: date
    ) -> tuple[float, ...]: ...

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
                _kein_termin_im_fenster(struktur, as_of=as_of, parameters=self._parameters),
                evaluated_at=evaluated_at,
                parameters=self._parameters,
                underlying_price=price,
            )

        # **Nicht** ``struktur.strikes``: Das ist die Vereinigung ueber alle
        # Verfallstermine (gemessener Befund, ADR 0048). Gefragt ist, was zu
        # *diesem* Termin gelistet ist -- sonst gehen Anfragen an Kontrakte,
        # die es nicht gibt, und die Auswahl schrumpft still.
        try:
            gelistet = self._source.option_strikes(contract, termin)
        except IbkrBarSourceError as error:
            raise OptionsDataProviderError(str(error)) from error
        if not gelistet:
            return unzureichend(
                f"zum {termin.isoformat()} ist kein einziger Put gelistet",
                evaluated_at=evaluated_at,
                parameters=self._parameters,
                underlying_price=price,
                expiration=termin,
            )

        strikes = select_strikes(gelistet, price=price, parameters=self._parameters)
        if not strikes:
            return unzureichend(
                f"kein Strike zwischen {self._parameters.min_moneyness:.0%} und "
                f"{self._parameters.max_moneyness:.0%} des Kurses von {price:.2f} gelistet "
                f"({len(gelistet)} Strikes zum {termin.isoformat()})",
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


_TERMINE_IN_DER_MELDUNG = 6
"""Wie viele Verfallstermine der Grund aufzaehlt. Genug, um eine Kette mit
Wochenoptionen von einer ohne zu unterscheiden -- und wenig genug, dass die
Zeile lesbar bleibt."""


def _kein_termin_im_fenster(
    struktur: OptionChainStructure, *, as_of: date, parameters: OptionsParameters
) -> str:
    """Warum das Zielfenster leer blieb -- mit den Zahlen, die es erklaeren.

    Der Messlauf vom 2026-08-31 liess 77 von 192 Titeln aus **einem** Grund
    ausfallen, und die Sammelmeldung "kein Verfallstermin gelistet" reichte
    nicht aus, um zwei sehr verschiedene Ursachen zu unterscheiden: eine
    Kette, die nur Monatsverfaelle fuehrt (dann liegt das Fenster zwischen
    zwei Terminen), und eine, bei der der Adapter die falsche Kette erwischt
    hat (dann fehlen die Wochentermine, die es gibt).

    Der Grund nennt deshalb die naechsten Termine auf beiden Seiten, die
    Handelsklasse und die Boerse. Eine Zeile je ausgefallenem Titel, und die
    Frage ist beantwortet, statt dass ein zweiter Messlauf noetig waere.
    """
    abstaende = sorted((termin - as_of).days for termin in struktur.expirations)
    darunter = [tage for tage in abstaende if tage < parameters.min_days_to_expiration]
    darueber = [tage for tage in abstaende if tage > parameters.max_days_to_expiration]
    nachbarn = (
        f"naechste {darunter[-1] if darunter else '--'} und "
        f"{darueber[0] if darueber else '--'} Tage"
    )
    liste = ", ".join(
        termin.isoformat() for termin in struktur.expirations[:_TERMINE_IN_DER_MELDUNG]
    )
    if len(struktur.expirations) > _TERMINE_IN_DER_MELDUNG:
        liste += ", ..."
    return (
        f"kein Verfallstermin zwischen {parameters.min_days_to_expiration} und "
        f"{parameters.max_days_to_expiration} Tagen gelistet -- {nachbarn} "
        f"(Klasse '{struktur.trading_class}' ueber {struktur.exchange}, "
        f"{len(struktur.expirations)} Termine: {liste})"
    )
