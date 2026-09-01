"""Dauerhaft nutzbarer Testprovider fuer die Optionsanalyse (ADR 0048).

Ohne ihn braeuchte jeder ``dispatch``-Lauf und jeder Test eine laufende TWS
samt Optionsmarktdaten-Abo. Der Anbieter erzeugt eine **rechnerisch
konstruierte** Kette aus dem uebergebenen Kurs -- keine gemessenen Preise
und keine Behauptung, echte zu sein.

Zwei Entscheidungen wie bei den uebrigen Fixture-Anbietern:

* **Nicht an feste Kalenderdaten gebunden.** Der Verfallstermin entsteht
  relativ zum Stichtag, damit das Szenario stabil bleibt, waehrend die Zeit
  weiterlaeuft.
* **Bewusst ungleichfoermig.** Die Praemienhoehe unterscheidet sich je
  Symbol. Gleichfoermige Fixtures haben beim letzten Mal zwei
  Berichtsmutationen gruen bleiben lassen; wo alle Werte gleich sind, faellt
  eine Verwechslung nicht auf.

Nicht hinterlegte Symbole bekommen den mittleren Faktor -- ein Fixture-Lauf
kommt so mit jeder Watchlist zurecht.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta

from ai_trading_analyst.domain.analysis import OptionsDataProviderError, Stock
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

_MONEYNESS_STUFEN = (0.98, 0.955, 0.93, 0.905, 0.88, 0.855, 0.83)
"""Strike-Raster als Anteil des Kurses -- 2,5 Prozentpunkte Abstand, wie es
bei US-Standardwerten ueblich ist."""

_PRAEMIENFAKTOR = {
    "FIXCAND": 1.0,
    "FIXNOCAND": 0.55,
    "FIXINCOMPLETE": 1.8,
}
"""Wie hoch die Praemien eines Symbols ausfallen -- die Fixture-Entsprechung
unterschiedlicher impliziter Volatilitaet. Ohne diese Streuung haetten alle
Symbole denselben Score-Teilwert."""

_STANDARDFAKTOR = 1.0

_FEHLERSYMBOL = "FIXERROR"
"""Ein Symbol, das den Anbieterausfall ausloest. Der Weg ueber
``OptionsDataProviderError`` wird sonst nie durchlaufen, obwohl er der
wahrscheinlichste Betriebszustand ist: eine nicht angemeldete TWS."""


class FixtureOptionsProvider:
    """Konstruiert eine Optionskette aus dem uebergebenen Kurs."""

    def __init__(
        self,
        parameters: OptionsParameters,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._parameters = parameters
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
        if stock.symbol == _FEHLERSYMBOL:
            raise OptionsDataProviderError(
                f"Fixture-Anbieterausfall fuer '{stock.symbol}' (fest hinterlegt)."
            )

        evaluated_at = self._now()
        # Mit ``next_earnings_date``, wie der IBKR-Anbieter: Ohne ihn entstuende
        # hier ein Vorschlag mit ``earnings_within_term=True`` -- ein Zustand,
        # den die Produktion nie erzeugt. Der Standardlauf von ``dispatch``
        # steht auf diesem Anbieter und pruefte dann etwas anderes als das,
        # was spaeter laeuft.
        termin = select_expiration(
            _verfallstermine(as_of),
            as_of=as_of,
            parameters=self._parameters,
            next_earnings_date=next_earnings_date,
        )
        if termin is None:
            return unzureichend(
                "die Fixture-Kette enthaelt keinen Termin im Zielfenster",
                evaluated_at=evaluated_at,
                parameters=self._parameters,
                underlying_price=price,
            )

        strikes = select_strikes(
            (round(price * stufe, 1) for stufe in _MONEYNESS_STUFEN),
            price=price,
            parameters=self._parameters,
        )
        faktor = _PRAEMIENFAKTOR.get(stock.symbol, _STANDARDFAKTOR)
        quotes = [
            _notierung(strike, price=price, expiration=termin, faktor=faktor)
            for strike in strikes
        ]
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


def _verfallstermine(as_of: date) -> tuple[date, ...]:
    """Woechentliche Termine ueber ein Vierteljahr, jeweils freitags."""
    erster_freitag = as_of + timedelta(days=(4 - as_of.weekday()) % 7 or 7)
    return tuple(erster_freitag + timedelta(weeks=woche) for woche in range(13))


def _notierung(
    strike: float, *, price: float, expiration: date, faktor: float
) -> OptionQuote:
    """Eine konstruierte Notierung -- Delta und Praemie fallen mit dem Abstand.

    Bewusst eine gerade Linie und kein nachgebautes Optionspreismodell: Ein
    Fixture soll nachvollziehbar sein, nicht echt aussehen. Was es liefert,
    ist plausibel geordnet -- naeher am Geld heisst hoeheres Delta und
    hoehere Praemie --, und mehr braucht ein Testlauf nicht.
    """
    moneyness = strike / price
    delta = max(0.02, (moneyness - 0.80) * 2.2)
    praemie = round(strike * 0.025 * delta * faktor, 2)
    return OptionQuote(
        expiration=expiration,
        strike=strike,
        bid=praemie,
        ask=round(praemie * 1.04, 2),
        delta=-delta,
        implied_volatility=round(0.20 * faktor, 4),
        open_interest=int(2000 * delta),
        volume=int(300 * delta),
    )
