"""Tests des Fixture-Optionsanbieters -- vor allem des Strukturvergleichs.

Der Anbieter ist kein Beiwerk: Der Standardlauf von ``dispatch`` steht auf
ihm. Was er **nicht** liefert, fehlt in jedem Testlauf und in jedem Bericht,
der ohne TWS entsteht -- und saehe dann anders aus als der Scharfbetrieb.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from ai_trading_analyst.domain.analysis import OptionsDataProviderError, Stock
from ai_trading_analyst.domain.options import (
    OptionsAnalysis,
    OptionsParameters,
    OptionsStatus,
    PutSpread,
)
from ai_trading_analyst.infrastructure.fixtures.options_provider import (
    FixtureOptionsProvider,
)

STICHTAG = date(2026, 9, 4)


def aktie(symbol: str = "FIXCAND") -> Stock:
    return Stock(id=uuid.uuid4(), symbol=symbol, exchange="NASDAQ")


def analysiere(
    *, price: float = 230.0, parameters: OptionsParameters | None = None
) -> OptionsAnalysis:
    provider = FixtureOptionsProvider(parameters or OptionsParameters())
    return provider.options(aktie(), price=price, as_of=STICHTAG)


class TestStrukturvergleich:
    def test_auch_der_fixture_lauf_liefert_einen_spread(self) -> None:
        """Sonst sagte ein Fixture-Bericht etwas anderes ueber die Ausgabe aus
        als der Scharfbetrieb -- genau davor warnt der Modul-Docstring des
        Anbieters."""
        analyse = analysiere()

        assert analyse.status is OptionsStatus.COMPLETED
        assert isinstance(analyse.spread, PutSpread)
        assert analyse.spread_reason is None
        assert analyse.spread.hedge_strike < analyse.strategies[0].strike

    def test_die_absicherung_erscheint_nicht_doppelt(self) -> None:
        """Sie liegt in der konstruierten Kette schon vor. Ein zweites Mal
        angehaengt entstuende eine Dublette in ``option_quotes``, ueber die
        die Kalibrierung mittelte."""
        analyse = analysiere()

        strikes = [q.strike for q in analyse.quotes]
        assert len(strikes) == len(set(strikes))
        assert analyse.spread is not None
        assert analyse.spread.hedge_strike in strikes

    def test_die_kennzahlen_haengen_zusammen(self) -> None:
        """Was hier steht, muss sich aus den Rohgroessen nachrechnen lassen."""
        analyse = analysiere()
        spread = analyse.spread
        verkauf = analyse.strategies[0]

        assert isinstance(spread, PutSpread)
        assert spread.net_credit == pytest.approx(verkauf.premium - spread.hedge_cost)
        assert spread.max_loss == pytest.approx(
            (verkauf.strike - spread.hedge_strike) - spread.net_credit
        )
        assert spread.return_on_risk == pytest.approx(spread.net_credit / spread.max_loss)
        assert spread.hedge_cost_share == pytest.approx(spread.hedge_cost / verkauf.premium)

    def test_eine_zu_grosse_zielbreite_faellt_auf_den_tiefsten_strike(self) -> None:
        """Gewaehlt wird der **naechstliegende** gelistete Strike, nicht der
        genaue Zielabstand. Weist das Ziel unter das Raster, bleibt der
        tiefste uebrig -- kein Ausfall, sondern die aeusserste Absicherung,
        die es gibt. Das Raster deckelt damit, wie breit ein Spread werden
        kann."""
        weit = analysiere(parameters=OptionsParameters(hedge_width_pct=0.90))
        normal = analysiere()

        assert isinstance(weit.spread, PutSpread)
        assert isinstance(normal.spread, PutSpread)
        assert weit.spread.hedge_strike < normal.spread.hedge_strike
        # Breiter heisst mehr Risiko und mehr Gutschrift -- beides zusammen.
        assert weit.spread.max_loss > normal.spread.max_loss
        assert weit.spread.net_credit > normal.spread.net_credit

    def test_die_absicherung_kann_ausserhalb_des_notierten_bandes_liegen(self) -> None:
        """Das Moneyness-Band begrenzt, welche Kontrakte **notiert** werden --
        nicht, welche gelistet sind. Der IBKR-Weg reicht ebenso alle
        gelisteten Strikes in die Wahl, nicht nur die abgefragten; sonst
        haenge die Breite des Spreads daran, wie viele Notierungen der
        Tageslauf sich gerade leistet.
        """
        eng = FixtureOptionsProvider(
            OptionsParameters(min_moneyness=0.95, max_moneyness=0.99)
        )

        analyse = eng.options(aktie(), price=230.0, as_of=STICHTAG)

        assert isinstance(analyse.spread, PutSpread)
        notierte = [q.strike for q in analyse.quotes]
        assert analyse.spread.hedge_strike < min(
            s for s in notierte if s != analyse.spread.hedge_strike
        )

    def test_ohne_vorschlag_gibt_es_auch_keinen_vergleich(self) -> None:
        """Und keinen Grund: Wo nichts verkauft wird, ist nichts abzusichern.
        Der Grund der Optionsanalyse selbst steht in ``reason``."""
        provider = FixtureOptionsProvider(
            OptionsParameters(min_delta=0.99, max_delta=1.0)
        )

        analyse = provider.options(aktie(), price=230.0, as_of=STICHTAG)

        assert analyse.status is OptionsStatus.INSUFFICIENT_DATA
        assert analyse.spread is None
        assert analyse.spread_reason is None
        assert analyse.reason is not None


class TestAnbieterausfall:
    def test_das_fehlersymbol_bricht_ab(self) -> None:
        provider = FixtureOptionsProvider(OptionsParameters())

        with pytest.raises(OptionsDataProviderError):
            provider.options(aktie("FIXERROR"), price=230.0, as_of=STICHTAG)
