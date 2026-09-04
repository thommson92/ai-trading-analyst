"""Tests des Put-Spreads (ADR 0058, Festlegung 11).

Geprueft wird gegen die Beispielrechnung des Entscheidungsdokuments -- AAPL
bei 232, Verkauf des 220ers, Absicherung mit dem 205er -- und gegen die
Grenzfaelle, in denen kein Spread entsteht. Jeder davon nennt einen Grund im
Klartext statt einer Luecke.
"""

from __future__ import annotations

from datetime import date

import pytest

from ai_trading_analyst.domain.options import (
    REASON_CREDIT_EXCEEDS_WIDTH,
    REASON_HEDGE_NOT_CHEAPER,
    REASON_HEDGE_WITHOUT_MID,
    LiquidityGrade,
    OptionQuote,
    PutSpread,
    PutStrategy,
    evaluate_spread,
    select_hedge_strike,
)

VERFALL = date(2026, 10, 16)


def verkauf(*, strike: float = 220.0, praemie: float = 2.35) -> PutStrategy:
    return PutStrategy(
        expiration=VERFALL,
        days_to_expiration=35,
        strike=strike,
        distance_to_price_pct=0.05,
        premium=praemie,
        break_even=strike - praemie,
        capital_at_risk=strike * 100,
        simple_return=praemie / strike,
        annualized_return=0.11,
        liquidity=LiquidityGrade.GOOD,
    )


def absicherung(*, strike: float = 205.0, geld: float = 0.63, brief: float = 0.73) -> OptionQuote:
    return OptionQuote(
        expiration=VERFALL,
        strike=strike,
        bid=geld,
        ask=brief,
        delta=-0.07,
        implied_volatility=0.29,
        open_interest=800,
        volume=120,
    )


class TestStrikewahl:
    def test_der_gelistete_strike_naechst_der_zielbreite_gewinnt(self) -> None:
        gelistet = [190.0, 195.0, 200.0, 205.0, 210.0, 215.0, 220.0, 225.0]

        gewaehlt = select_hedge_strike(
            gelistet, short_strike=220.0, price=232.0, width_pct=0.065
        )

        # 220 - 232*0.065 = 204.9 -> naechster gelisteter ist 205.
        assert gewaehlt == pytest.approx(205.0)

    def test_strikes_auf_oder_ueber_dem_verkauf_scheiden_aus(self) -> None:
        """Ein gekaufter Put auf gleicher Hoehe nimmt kein Risiko weg und
        kostet die ganze Praemie."""
        gewaehlt = select_hedge_strike(
            [220.0, 225.0, 230.0], short_strike=220.0, price=232.0, width_pct=0.065
        )

        assert gewaehlt is None

    def test_bei_gleichstand_gewinnt_der_tiefere(self) -> None:
        """Er nimmt mehr Risiko weg -- und die Wahl bleibt reproduzierbar."""
        gewaehlt = select_hedge_strike(
            [200.0, 210.0], short_strike=220.0, price=200.0, width_pct=0.10
        )

        assert gewaehlt == pytest.approx(200.0)

    def test_ohne_gelistete_strikes_gibt_es_keinen(self) -> None:
        assert select_hedge_strike([], short_strike=220.0, price=232.0, width_pct=0.065) is None


class TestBewertung:
    def test_die_beispielrechnung_des_entscheidungsdokuments(self) -> None:
        """AAPL bei 232: Verkauf 220 fuer 2,35, Absicherung 205 fuer 0,68."""
        ergebnis = evaluate_spread(
            verkauf(), absicherung(), liquidity=LiquidityGrade.GOOD
        )

        assert isinstance(ergebnis, PutSpread)
        assert ergebnis.hedge_cost == pytest.approx(0.68)
        assert ergebnis.net_credit == pytest.approx(1.67)
        assert ergebnis.max_loss == pytest.approx(13.33)
        assert ergebnis.capital_at_risk == pytest.approx(1333.0)
        assert ergebnis.hedge_cost_share == pytest.approx(0.68 / 2.35)
        assert ergebnis.return_on_risk == pytest.approx(1.67 / 13.33)

    def test_die_rendite_auf_riskiertes_kapital_uebertrifft_die_des_verkaufs(self) -> None:
        """Die eine Zahl, die beide Strukturen vergleichbar macht -- und die
        den CSP fast immer schlecht aussehen laesst, solange man das Kapital
        anderweitig einsetzen koennte."""
        kurz = verkauf()
        ergebnis = evaluate_spread(kurz, absicherung(), liquidity=LiquidityGrade.GOOD)

        assert isinstance(ergebnis, PutSpread)
        rendite_csp = kurz.premium / kurz.strike
        assert ergebnis.return_on_risk > rendite_csp * 10

    def test_das_delta_kommt_als_betrag(self) -> None:
        ergebnis = evaluate_spread(
            verkauf(), absicherung(), liquidity=LiquidityGrade.ACCEPTABLE
        )

        assert isinstance(ergebnis, PutSpread)
        assert ergebnis.hedge_delta == pytest.approx(0.07)
        assert ergebnis.hedge_liquidity is LiquidityGrade.ACCEPTABLE


class TestKeinSpread:
    """Jeder Fall nennt einen Grund im Klartext -- sonst stuende dort eine
    Luecke, die niemand erklaeren kann."""

    def test_ohne_mittelwert_der_absicherung(self) -> None:
        ergebnis = evaluate_spread(
            verkauf(), absicherung(geld=None), liquidity=LiquidityGrade.POOR  # type: ignore[arg-type]
        )

        assert ergebnis == REASON_HEDGE_WITHOUT_MID

    def test_wenn_die_absicherung_die_ganze_praemie_kostet(self) -> None:
        """Eine Gutschrift von null ist kein Verkauf mehr. Kommt bei sehr
        steilem Skew tatsaechlich vor."""
        ergebnis = evaluate_spread(
            verkauf(), absicherung(geld=2.40, brief=2.50), liquidity=LiquidityGrade.GOOD
        )

        assert ergebnis == REASON_HEDGE_NOT_CHEAPER

    def test_wenn_die_gutschrift_die_spannweite_uebersteigt(self) -> None:
        """Ein risikoloser Gewinn -- den stellt kein Markt. Er entsteht aus
        zwei Notierungen, die nicht zueinander passen."""
        ergebnis = evaluate_spread(
            verkauf(praemie=3.00),
            absicherung(strike=218.0, geld=0.10, brief=0.20),
            liquidity=LiquidityGrade.POOR,
        )

        assert ergebnis == REASON_CREDIT_EXCEEDS_WIDTH
