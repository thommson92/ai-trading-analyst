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
    expirations_in_window,
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
        self, contract: ContractSpec, expiration: date, trading_class: str
    ) -> tuple[float, ...]: ...

    def option_quotes(
        self,
        contract: ContractSpec,
        expiration: date,
        strikes: Sequence[float],
        market_data_type: int,
        trading_class: str,
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
            struktur.expirations,
            as_of=as_of,
            parameters=self._parameters,
            next_earnings_date=next_earnings_date,
        )
        if termin is None:
            return unzureichend(
                _kein_zulaessiger_termin(
                    struktur,
                    as_of=as_of,
                    parameters=self._parameters,
                    next_earnings_date=next_earnings_date,
                ),
                evaluated_at=evaluated_at,
                parameters=self._parameters,
                underlying_price=price,
            )

        # **Nicht** ``struktur.strikes``: Das ist die Vereinigung ueber alle
        # Verfallstermine (gemessener Befund, ADR 0048). Gefragt ist, was zu
        # *diesem* Termin gelistet ist -- sonst gehen Anfragen an Kontrakte,
        # die es nicht gibt, und die Auswahl schrumpft still.
        try:
            # Mit der Handelsklasse aus Schritt 1: Ohne sie saehe der Abruf
            # wieder alle Klassen des Basiswerts, und die Wahl der reichsten
            # Kette waere folgenlos.
            gelistet = self._source.option_strikes(
                contract, termin, struktur.trading_class
            )
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
                contract, termin, strikes, self._market_data_type, struktur.trading_class
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


def _kein_zulaessiger_termin(
    struktur: OptionChainStructure,
    *,
    as_of: date,
    parameters: OptionsParameters,
    next_earnings_date: date | None,
) -> str:
    """Warum kein Verfallstermin uebrig blieb -- mit den Zahlen, die es erklaeren.

    Zwei Bedingungen koennen die Liste leeren, und sie fuehren zu ganz
    verschiedenen Schluessen: Das Laufzeitfenster kann zwischen zwei
    Monatsverfaellen liegen (dann ist es zu schmal), oder der naechste
    Berichtstermin liegt vor allen zulaessigen Terminen (dann ist der Titel
    schlicht zu nah an seinen Zahlen). Der Grund benennt, welche es war.

    Beim Messlauf am 2026-08-31 fielen 77 von 192 Titeln aus, und die alte
    Sammelmeldung reichte nicht, um eine Kette mit reinen Monatsverfaellen
    von einer zu unterscheiden, bei der der Adapter die falsche
    Handelsklasse erwischt hatte. Deshalb stehen Handelsklasse, Boerse und
    die naechsten Termine auf beiden Seiten dabei.
    """
    im_fenster = expirations_in_window(
        struktur.expirations, as_of=as_of, parameters=parameters
    )
    herkunft = (
        f"Klasse '{struktur.trading_class}' ueber {struktur.exchange}, "
        f"{len(struktur.expirations)} Termine: {_termine(struktur.expirations)}"
    )
    if im_fenster and next_earnings_date is not None:
        return (
            f"jeder Verfallstermin im Fenster liegt nach dem Berichtstermin am "
            f"{next_earnings_date.isoformat()} -- fruehester zulaessiger waere der "
            f"{im_fenster[0].isoformat()} ({herkunft})"
        )
    abstaende = sorted((termin - as_of).days for termin in struktur.expirations)
    darunter = [tage for tage in abstaende if tage < parameters.min_days_to_expiration]
    darueber = [tage for tage in abstaende if tage > parameters.max_days_to_expiration]
    return (
        f"kein Verfallstermin zwischen {parameters.min_days_to_expiration} und "
        f"{parameters.max_days_to_expiration} Tagen gelistet -- naechste "
        f"{darunter[-1] if darunter else '--'} und "
        f"{darueber[0] if darueber else '--'} Tage ({herkunft})"
    )


def _termine(expirations: Sequence[date]) -> str:
    liste = ", ".join(termin.isoformat() for termin in expirations[:_TERMINE_IN_DER_MELDUNG])
    return liste + ", ..." if len(expirations) > _TERMINE_IN_DER_MELDUNG else liste
