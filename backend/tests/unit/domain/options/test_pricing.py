"""Tests des Optionspreis-Modells (ADR 0058).

Geprueft wird gegen **unabhaengige** Massstaebe, nicht gegen die eigene
Ausgabe: einen Lehrbuchwert, die Put-Call-Paritaet und die Grenzfaelle, in
denen die richtige Antwort ohne Modell feststeht. Ein Test, der nur
nachschreibt, was die Funktion heute liefert, haette jede Vorzeichenumkehr
mitgemacht.
"""

from __future__ import annotations

import math

import pytest

from ai_trading_analyst.domain.options import (
    TRADING_DAYS_PER_YEAR,
    normal_cdf,
    price_put,
    realized_volatility,
)


class TestNormalverteilung:
    def test_die_bekannten_stuetzstellen_stimmen(self) -> None:
        assert normal_cdf(0.0) == pytest.approx(0.5)
        assert normal_cdf(1.0) == pytest.approx(0.8413447461, abs=1e-9)
        assert normal_cdf(-1.96) == pytest.approx(0.0249978952, abs=1e-9)

    def test_sie_ist_symmetrisch(self) -> None:
        for x in (0.25, 1.0, 2.5):
            assert normal_cdf(x) + normal_cdf(-x) == pytest.approx(1.0)


class TestBewertung:
    def test_der_lehrbuchwert_wird_getroffen(self) -> None:
        """Hull, *Options, Futures and Other Derivatives*: Ein europaeischer
        Put auf einen Kurs von 42 mit Strike 40, Zins 10 %, Volatilitaet 20 %
        und einem halben Jahr Restlaufzeit ist 0,81 wert.

        Der Wert stammt von ausserhalb dieses Projekts -- das ist sein Sinn.
        """
        preis = price_put(
            spot=42.0,
            strike=40.0,
            years_to_expiration=0.5,
            volatility=0.20,
            risk_free_rate=0.10,
        )
        assert preis.premium == pytest.approx(0.8086, abs=5e-5)

    def test_die_put_call_paritaet_haelt(self) -> None:
        """``C - P = S - K e^(-rT)`` gilt fuer jedes korrekte
        Black-Scholes-Paar. Der Call wird hier eigens gerechnet: Die Paritaet
        prueft die Formel gegen eine Beziehung, die von ihr unabhaengig ist.
        """
        spot, strike, zins, vola, jahre = 100.0, 95.0, 0.04, 0.25, 0.25
        put = price_put(
            spot=spot,
            strike=strike,
            years_to_expiration=jahre,
            volatility=vola,
            risk_free_rate=zins,
        )
        streuung = vola * math.sqrt(jahre)
        d1 = (math.log(spot / strike) + (zins + 0.5 * vola**2) * jahre) / streuung
        call = spot * normal_cdf(d1) - strike * math.exp(-zins * jahre) * normal_cdf(
            d1 - streuung
        )

        assert call - put.premium == pytest.approx(
            spot - strike * math.exp(-zins * jahre), abs=1e-9
        )

    def test_das_delta_eines_puts_liegt_zwischen_minus_eins_und_null(self) -> None:
        for strike in (60.0, 90.0, 100.0, 110.0, 160.0):
            preis = price_put(
                spot=100.0,
                strike=strike,
                years_to_expiration=0.1,
                volatility=0.3,
                risk_free_rate=0.04,
            )
            assert -1.0 <= preis.delta <= 0.0

    def test_ein_tieferer_strike_ist_billiger(self) -> None:
        """Monotonie: Je weiter aus dem Geld, desto weniger wert. Faengt eine
        Vorzeichenverwechslung, die der Lehrbuchwert allein durchliesse."""
        praemien = [
            price_put(
                spot=100.0,
                strike=strike,
                years_to_expiration=0.1,
                volatility=0.3,
                risk_free_rate=0.04,
            ).premium
            for strike in (80.0, 85.0, 90.0, 95.0)
        ]
        assert praemien == sorted(praemien)

    def test_mehr_volatilitaet_ist_mehr_wert(self) -> None:
        praemien = [
            price_put(
                spot=100.0,
                strike=90.0,
                years_to_expiration=0.1,
                volatility=vola,
                risk_free_rate=0.04,
            ).premium
            for vola in (0.15, 0.25, 0.35, 0.45)
        ]
        assert praemien == sorted(praemien)


class TestGrenzfaelle:
    """Wo die richtige Antwort ohne Modell feststeht, muss sie herauskommen --
    exakt und nicht als Ausweichen vor einer Division durch null."""

    def test_am_verfall_bleibt_der_innere_wert(self) -> None:
        preis = price_put(
            spot=90.0,
            strike=100.0,
            years_to_expiration=0.0,
            volatility=0.3,
            risk_free_rate=0.05,
        )
        assert preis.premium == pytest.approx(10.0)
        assert preis.delta == pytest.approx(-1.0)

    def test_am_verfall_aus_dem_geld_ist_er_wertlos(self) -> None:
        preis = price_put(
            spot=110.0,
            strike=100.0,
            years_to_expiration=0.0,
            volatility=0.3,
            risk_free_rate=0.05,
        )
        assert preis.premium == pytest.approx(0.0)
        assert preis.delta == pytest.approx(0.0)

    def test_ohne_volatilitaet_bleibt_der_abgezinste_abstand(self) -> None:
        """Bewegt sich nichts, gibt es keine Unsicherheit zu bewerten. Der Put
        ist dann genau den abgezinsten Betrag wert, um den der Terminkurs
        unter dem Strike liegt."""
        preis = price_put(
            spot=90.0,
            strike=100.0,
            years_to_expiration=1.0,
            volatility=0.0,
            risk_free_rate=0.05,
        )
        assert preis.premium == pytest.approx(100.0 * math.exp(-0.05) - 90.0)

    def test_ein_kurs_von_null_ist_kein_grenzfall_sondern_ein_fehler(self) -> None:
        """Aus echten Kerzen kann er nicht kommen -- deshalb laut abbrechen
        statt still etwas zurueckgeben."""
        with pytest.raises(ValueError, match="Kurs"):
            price_put(
                spot=0.0,
                strike=100.0,
                years_to_expiration=0.1,
                volatility=0.3,
                risk_free_rate=0.04,
            )

    def test_ein_strike_von_null_ebenso(self) -> None:
        with pytest.raises(ValueError, match="Strike"):
            price_put(
                spot=100.0,
                strike=0.0,
                years_to_expiration=0.1,
                volatility=0.3,
                risk_free_rate=0.04,
            )


class TestRealisierteVolatilitaet:
    def test_eine_bekannte_streuung_kommt_annualisiert_zurueck(self) -> None:
        """Kurse, die sich taeglich um denselben Faktor abwechselnd auf und ab
        bewegen: Die Renditen sind ``+r`` und ``-r``, ihre
        Stichprobenstreuung ist bei geradem Vorzeichenwechsel bekannt."""
        faktor = 1.01
        closes = [100.0 * faktor ** (i % 2) for i in range(21)]

        vola = realized_volatility(closes, periods_per_year=TRADING_DAYS_PER_YEAR)

        assert vola is not None
        renditen = [math.log(faktor), -math.log(faktor)] * 10
        erwartet = (
            math.sqrt(sum(r**2 for r in renditen) / (len(renditen) - 1))
            * math.sqrt(TRADING_DAYS_PER_YEAR)
        )
        assert vola == pytest.approx(erwartet)

    def test_ein_konstanter_kurs_hat_keine_volatilitaet(self) -> None:
        assert realized_volatility([100.0] * 30) == pytest.approx(0.0)

    def test_zu_wenige_kurse_ergeben_keinen_wert(self) -> None:
        """Zwei Renditen sind das Wenigste, woraus eine Stichprobenstreuung
        entsteht -- darunter bleibt die Kennzahl fehlend, nicht null
        (CLAUDE.md)."""
        assert realized_volatility([]) is None
        assert realized_volatility([100.0]) is None
        assert realized_volatility([100.0, 101.0]) is None
        assert realized_volatility([100.0, 101.0, 102.0]) is not None

    def test_ein_kurs_von_null_ergibt_keinen_wert(self) -> None:
        """Der Logarithmus haette hier keine Antwort. Fehlend ist die richtige,
        kein Ueberspringen der betroffenen Kerze -- eine Luecke in der Reihe
        macht die uebrigen Renditen falsch, nicht nur weniger."""
        assert realized_volatility([100.0, 0.0, 102.0, 103.0]) is None

    def test_die_annualisierung_skaliert_mit_der_wurzel(self) -> None:
        closes = [100.0, 101.0, 99.5, 102.0, 100.5, 103.0]

        eins = realized_volatility(closes, periods_per_year=1)
        zwohundert = realized_volatility(closes, periods_per_year=252)

        assert eins is not None
        assert zwohundert is not None
        assert zwohundert == pytest.approx(eins * math.sqrt(252))
