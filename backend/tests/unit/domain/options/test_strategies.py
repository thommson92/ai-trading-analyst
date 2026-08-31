"""Auswahl und Bewertung der Cash Secured Puts (ADR 0048).

Die Rechenwege sind einfach genug, dass jeder einzeln geprueft wird -- und
genau deshalb faellt eine Verwechslung sonst nicht auf: Praemie, Break-even
und Kapitalbindung stehen alle in derselben Groessenordnung, und ein
vertauschter Nenner sieht plausibel aus.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from ai_trading_analyst.domain.options import (
    LiquidityGrade,
    OptionQuote,
    OptionsAnalysis,
    OptionsParameters,
    OptionsStatus,
    PutStrategy,
    build_options_analysis,
    expirations_in_window,
    select_expiration,
    select_strikes,
)
from ai_trading_analyst.domain.technical import PriceZone, ZoneKind, ZoneStrength

STICHTAG = date(2026, 9, 1)
BEWERTET_AM = datetime(2026, 9, 1, 20, 30, tzinfo=UTC)
PARAMETER = OptionsParameters()


def notierung(
    strike: float,
    *,
    bid: float | None = 2.0,
    ask: float | None = 2.1,
    delta: float | None = -0.25,
    expiration: date = date(2026, 10, 2),
    open_interest: int | None = 500,
    volume: int | None = 60,
    implied_volatility: float | None = 0.3,
) -> OptionQuote:
    return OptionQuote(
        expiration=expiration,
        strike=strike,
        bid=bid,
        ask=ask,
        delta=delta,
        implied_volatility=implied_volatility,
        open_interest=open_interest,
        volume=volume,
    )


def zone(lower: float, upper: float, kind: ZoneKind = ZoneKind.SUPPORT) -> PriceZone:
    return PriceZone(
        lower=lower,
        upper=upper,
        kind=kind,
        strength=ZoneStrength.MODERATE,
        touch_count=3,
        last_confirmed_at=datetime(2026, 8, 20, 13, 45, tzinfo=UTC),
        distance_pct=0.05,
        pivot_count=2,
    )


class TestVerfallsterminwahl:
    def test_der_termin_naechst_der_bevorzugten_laufzeit_gewinnt(self) -> None:
        # Bevorzugt sind 35 Tage, also der 6. Oktober.
        termine = [date(2026, 9, 25), date(2026, 10, 2), date(2026, 10, 30)]
        assert select_expiration(termine, as_of=STICHTAG, parameters=PARAMETER) == date(
            2026, 10, 2
        )

    def test_die_bevorzugte_laufzeit_ist_nicht_die_fenstermitte(self) -> None:
        """Die Trennung ist der Kern: Das Fenster 21-60 haette die Mitte bei
        40,5 Tagen, bevorzugt sind aber 35. Am Messtag 2026-08-31 fiel die
        Wahl damit weiter auf den 2. Oktober -- die 115 gemessenen Werte
        bleiben gueltig."""
        messtag = date(2026, 8, 31)
        termine = [date(2026, 10, 2), date(2026, 10, 9)]

        assert select_expiration(termine, as_of=messtag, parameters=PARAMETER) == date(
            2026, 10, 2
        )

    def test_termine_ausserhalb_des_fensters_zaehlen_nicht(self) -> None:
        # 12 Tage und 90 Tage -- beide ausserhalb von 21 bis 60.
        termine = [date(2026, 9, 13), date(2026, 11, 30)]
        assert select_expiration(termine, as_of=STICHTAG, parameters=PARAMETER) is None

    @pytest.mark.parametrize(
        ("grenze", "tage"),
        [(date(2026, 9, 22), 21), (date(2026, 10, 31), 60)],
        ids=["untere", "obere"],
    )
    def test_die_fenstergrenzen_selbst_liegen_drin(self, grenze: date, tage: int) -> None:
        """Ein ``<`` statt ``<=`` schnitte je einen Verfallstermin ab."""
        assert (grenze - STICHTAG).days == tage
        assert select_expiration([grenze], as_of=STICHTAG, parameters=PARAMETER) == grenze

    def test_die_zulaessigen_termine_kommen_aufsteigend(self) -> None:
        """Darauf steht der Gleichstand: ``select_expiration`` verzichtet auf
        einen Tiebreak im Sortierschluessel, weil ``min`` bei Gleichstand den
        ersten Treffer behaelt -- und der erste ist der frueheste."""
        termine = [date(2026, 10, 9), date(2026, 9, 25), date(2026, 10, 2)]

        assert expirations_in_window(
            termine, as_of=STICHTAG, parameters=PARAMETER
        ) == (date(2026, 9, 25), date(2026, 10, 2), date(2026, 10, 9))

    def test_bei_gleichstand_gewinnt_der_fruehere_termin(self) -> None:
        # 32 und 38 Tage liegen beide drei Tage von den bevorzugten 35 weg.
        # Bewusst unsortiert uebergeben: Die Reihenfolge darf nicht vom
        # Aufrufer abhaengen.
        termine = [date(2026, 10, 9), date(2026, 10, 3)]
        assert select_expiration(termine, as_of=STICHTAG, parameters=PARAMETER) == date(
            2026, 10, 3
        )

    def test_ein_fenster_ab_breite_35_trifft_jeden_monatsverfall(self) -> None:
        """Der Grund fuer die Verbreiterung, ausgerechnet statt geglaubt.

        Zwei aufeinander folgende dritte Freitage liegen 28 oder 35 Tage
        auseinander. Ein Fenster schmaler als 35 Tage kann deshalb zwischen
        zwei Monatsverfaelle fallen -- am 2026-08-31 traf das 77 von 192
        Titeln der Watchliste.
        """
        for vorlauf in range(35):
            for abstand in (28, 35):
                naechster = STICHTAG + timedelta(days=vorlauf)
                termine = [naechster, naechster + timedelta(days=abstand)]
                assert (
                    select_expiration(termine, as_of=STICHTAG, parameters=PARAMETER)
                    is not None
                ), f"Vorlauf {vorlauf}, Abstand {abstand} faellt durch das Fenster"


class TestStrikeauswahl:
    def test_nur_strikes_im_moneyness_band(self) -> None:
        # Band 80 bis 99 Prozent von 100.
        gewaehlt = select_strikes([70, 80, 95, 99, 100, 110], price=100, parameters=PARAMETER)
        assert gewaehlt == (99.0, 95.0, 80.0)

    def test_die_naechsten_am_kurs_bleiben_bei_der_kuerzung(self) -> None:
        eng = OptionsParameters(max_strikes=2)
        gewaehlt = select_strikes([82, 90, 98], price=100, parameters=eng)
        assert gewaehlt == (98.0, 90.0)

    def test_ohne_passenden_strike_bleibt_die_auswahl_leer(self) -> None:
        assert select_strikes([120, 130], price=100, parameters=PARAMETER) == ()


class TestRechenwege:
    def strategie(self) -> PutStrategy:
        analyse = build_options_analysis(
            [notierung(90.0, bid=1.80, ask=1.90)],
            price=100.0,
            expiration=date(2026, 10, 2),
            as_of=STICHTAG,
            evaluated_at=BEWERTET_AM,
            parameters=PARAMETER,
        )
        assert analyse.status is OptionsStatus.COMPLETED
        return analyse.strategies[0]

    def test_die_praemie_ist_der_mittelwert_nicht_der_geldkurs(self) -> None:
        """ADR 0048, Festlegung 6. Bei liquiden Optionen fuellt ein Limit
        nahe der Mitte; der Geldkurs untertriebe die Rendite."""
        strategie = self.strategie()
        assert strategie.premium == pytest.approx(1.85)
        assert strategie.bid == pytest.approx(1.80)
        assert strategie.ask == pytest.approx(1.90)

    def test_einfache_rendite_bezieht_sich_auf_den_strike(self) -> None:
        # Kapital ist der Strike, nicht der Aktienkurs: 1,85 / 90.
        assert self.strategie().simple_return == pytest.approx(1.85 / 90)

    def test_annualisiert_wird_linear_auf_kalendertagen(self) -> None:
        # 31 Tage bis zum 2. Oktober, (1,85 / 90) * 365 / 31.
        assert self.strategie().annualized_return == pytest.approx(
            (1.85 / 90) * 365 / 31
        )

    def test_break_even_und_kapitalbindung(self) -> None:
        strategie = self.strategie()
        assert strategie.break_even == pytest.approx(88.15)
        assert strategie.capital_at_risk == pytest.approx(9000.0)

    def test_abstand_zum_kurs_bezieht_sich_auf_den_kurs(self) -> None:
        assert self.strategie().distance_to_price_pct == pytest.approx(
            0.10
        )

    def test_das_delta_wird_als_betrag_gefuehrt(self) -> None:
        assert self.strategie().delta == pytest.approx(0.25)


class TestDeltaFilter:
    def bewerte(self, delta: float | None) -> OptionsAnalysis:
        return build_options_analysis(
            [notierung(90.0, delta=delta)],
            price=100.0,
            expiration=date(2026, 10, 2),
            as_of=STICHTAG,
            evaluated_at=BEWERTET_AM,
            parameters=PARAMETER,
        )

    @pytest.mark.parametrize("delta", [-0.09, -0.41])
    def test_ausserhalb_des_bandes_entsteht_kein_vorschlag(self, delta: float) -> None:
        analyse = self.bewerte(delta)
        assert analyse.status is OptionsStatus.INSUFFICIENT_DATA
        assert "Delta-Band" in (analyse.reason or "")

    @pytest.mark.parametrize("delta", [-0.10, -0.40])
    def test_die_bandgrenzen_selbst_zaehlen_dazu(self, delta: float) -> None:
        assert self.bewerte(delta).status is OptionsStatus.COMPLETED

    def test_ohne_delta_wird_keines_geschaetzt(self) -> None:
        """Der Fall nach Boersenschluss ohne Marktdatenberechtigung.

        Ein aus der Moneyness abgeleitetes Delta waere ein erfundener Wert.
        Der Grund benennt deshalb genau das -- er unterscheidet sich vom
        Grund "lag nicht im Band", weil die Abhilfe eine andere ist.
        """
        analyse = self.bewerte(None)
        assert analyse.status is OptionsStatus.INSUFFICIENT_DATA
        assert analyse.reason == "keine der 1 Notierungen lieferte ein Delta"


class TestPraemie:
    @pytest.mark.parametrize(
        ("bid", "ask"),
        [(None, 2.1), (2.0, None), (None, None)],
        ids=["ohne_geld", "ohne_brief", "ohne_beides"],
    )
    def test_ein_halber_mittelwert_ist_keiner(
        self, bid: float | None, ask: float | None
    ) -> None:
        analyse = build_options_analysis(
            [notierung(90.0, bid=bid, ask=ask)],
            price=100.0,
            expiration=date(2026, 10, 2),
            as_of=STICHTAG,
            evaluated_at=BEWERTET_AM,
            parameters=PARAMETER,
        )
        assert analyse.status is OptionsStatus.INSUFFICIENT_DATA
        assert analyse.reason == "keine der 1 Notierungen hatte Geld- und Briefkurs"

    def test_ohne_notierung_zeigt_der_grund_auf_den_anbieter(self) -> None:
        analyse = build_options_analysis(
            [],
            price=100.0,
            expiration=date(2026, 10, 2),
            as_of=STICHTAG,
            evaluated_at=BEWERTET_AM,
            parameters=PARAMETER,
        )
        assert analyse.status is OptionsStatus.INSUFFICIENT_DATA
        assert "keine einzige Notierung" in (analyse.reason or "")
        # Der Kurs bleibt stehen: Er belegt, worauf gerechnet wurde.
        assert analyse.underlying_price == pytest.approx(100.0)


class TestLiquiditaet:
    def bewerte(self, **kwargs: Any) -> PutStrategy:
        analyse = build_options_analysis(
            [notierung(90.0, **kwargs)],
            price=100.0,
            expiration=date(2026, 10, 2),
            as_of=STICHTAG,
            evaluated_at=BEWERTET_AM,
            parameters=PARAMETER,
        )
        return analyse.strategies[0]

    def test_ohne_verletzung_gilt_die_liquiditaet_als_gut(self) -> None:
        assert self.bewerte().liquidity is LiquidityGrade.GOOD

    def test_eine_verletzung_ergibt_akzeptabel(self) -> None:
        strategie = self.bewerte(open_interest=30)
        assert strategie.liquidity is LiquidityGrade.ACCEPTABLE
        assert strategie.liquidity_warnings == ("Open Interest 30",)

    def test_zwei_verletzungen_ergeben_schlecht(self) -> None:
        strategie = self.bewerte(open_interest=30, volume=2)
        assert strategie.liquidity is LiquidityGrade.POOR
        assert len(strategie.liquidity_warnings) == 2

    def test_die_spanne_wird_am_mittelwert_gemessen(self) -> None:
        # 2,00 zu 2,40 sind 0,40 auf einen Mittelwert von 2,20 -- 18 Prozent.
        strategie = self.bewerte(bid=2.0, ask=2.4)
        assert strategie.liquidity_warnings == ("Geld-Brief-Spanne 18.2%",)

    def test_nicht_geliefert_ist_nicht_verletzt(self) -> None:
        """Fehlende Werte bestrafen nicht (CLAUDE.md).

        ``reqTickers`` fordert Open Interest nicht standardmaessig an. Wuerde
        das Fehlen als Verletzung zaehlen, waere praktisch jeder Vorschlag
        aus dem Tageslauf mindestens ``ACCEPTABLE``, ohne dass daran etwas
        gemessen waere.
        """
        strategie = self.bewerte(open_interest=None, volume=None)
        assert strategie.liquidity is LiquidityGrade.GOOD
        assert strategie.open_interest is None


class TestRangfolge:
    def analyse(self, quotes: list[OptionQuote]) -> OptionsAnalysis:
        return build_options_analysis(
            quotes,
            price=100.0,
            expiration=date(2026, 10, 2),
            as_of=STICHTAG,
            evaluated_at=BEWERTET_AM,
            parameters=PARAMETER,
        )

    def test_absteigend_nach_annualisierter_rendite(self) -> None:
        analyse = self.analyse(
            [
                notierung(88.0, bid=1.00, ask=1.05, delta=-0.15),
                notierung(96.0, bid=2.50, ask=2.60, delta=-0.38),
                notierung(92.0, bid=1.70, ask=1.75, delta=-0.26),
            ]
        )
        renditen = [s.annualized_return for s in analyse.strategies]
        assert renditen == sorted(renditen, reverse=True)
        assert analyse.strategies[0].strike == pytest.approx(96.0)

    def test_schlechte_liquiditaet_steht_nie_oben(self) -> None:
        """Doc 10, Paragraph 6.10 -- nicht verschwiegen, aber nie bevorzugt.

        Der illiquide Kontrakt hat hier die **hoechste** Rendite; ohne die
        Regel stuende er an erster Stelle.
        """
        analyse = self.analyse(
            [
                notierung(96.0, bid=3.00, ask=4.00, delta=-0.38, open_interest=5, volume=0),
                notierung(92.0, bid=1.70, ask=1.75, delta=-0.26),
            ]
        )
        assert analyse.strategies[0].strike == pytest.approx(92.0)
        assert analyse.strategies[1].liquidity is LiquidityGrade.POOR

    def test_es_bleiben_hoechstens_so_viele_wie_konfiguriert(self) -> None:
        analyse = self.analyse([notierung(strike) for strike in (96.0, 94.0, 92.0, 90.0)])
        assert len(analyse.strategies) == PARAMETER.max_suggestions


class TestKopplungen:
    """Die beiden optionalen Eingaben -- beide nicht blockierend (CLAUDE.md)."""

    def analyse(self, **kwargs: Any) -> OptionsAnalysis:
        return build_options_analysis(
            [notierung(90.0)],
            price=100.0,
            expiration=date(2026, 10, 2),
            as_of=STICHTAG,
            evaluated_at=BEWERTET_AM,
            parameters=PARAMETER,
            **kwargs,
        )

    def test_ohne_zonen_bleibt_nur_das_zonenfeld_leer(self) -> None:
        strategie = self.analyse().strategies[0]
        assert strategie.distance_to_support_pct is None
        assert strategie.annualized_return > 0

    def test_der_strike_ueber_der_zone_ergibt_einen_positiven_abstand(self) -> None:
        strategie = self.analyse(zones=[zone(84.0, 86.0)]).strategies[0]
        # (90 - 86) / 90.
        assert strategie.distance_to_support_pct == pytest.approx(4 / 90)

    def test_der_strike_unter_der_zone_ergibt_einen_negativen_abstand(self) -> None:
        strategie = self.analyse(zones=[zone(94.0, 96.0)]).strategies[0]
        assert strategie.distance_to_support_pct == pytest.approx(-4 / 90)

    def test_innerhalb_der_zone_ist_der_abstand_null(self) -> None:
        strategie = self.analyse(zones=[zone(88.0, 92.0)]).strategies[0]
        assert strategie.distance_to_support_pct == pytest.approx(0.0)

    def test_widerstandszonen_zaehlen_nicht(self) -> None:
        """Nur Unterstuetzungen koennen einen Strike unter dem Kurs halten."""
        strategie = self.analyse(
            zones=[zone(94.0, 96.0, kind=ZoneKind.RESISTANCE)]
        ).strategies[0]
        assert strategie.distance_to_support_pct is None

    def test_die_naechstgelegene_zone_gewinnt(self) -> None:
        strategie = self.analyse(
            zones=[zone(70.0, 72.0), zone(86.0, 88.0)]
        ).strategies[0]
        assert strategie.distance_to_support_pct == pytest.approx(2 / 90)

    def test_der_berichtstermin_wirkt_schon_bei_der_terminwahl(self) -> None:
        """Entscheidung des Projektinhabers, 2026-08-31 (ADR 0048).

        Am Messtag trugen die drei hoechsten Praemienrenditen der Watchliste
        -- ORCL 71 %, STX 72 %, MU 64 % -- alle einen Berichtstermin
        innerhalb der Laufzeit. Das ist keine Gelegenheit, sondern die
        Verguetung fuer genau das Risiko, das ein Put-Verkaeufer traegt.

        Gewaehlt wird deshalb der naechstfruehere Verfall **vor** dem
        Termin -- und weil das schon bei der Auswahl geschieht, kommt eine
        Notierung, die ohnehin ausschiede, gar nicht erst zustande.
        """
        termine = [date(2026, 9, 25), date(2026, 10, 2), date(2026, 10, 9)]

        gewaehlt = select_expiration(
            termine,
            as_of=STICHTAG,
            parameters=PARAMETER,
            next_earnings_date=date(2026, 10, 5),
        )

        # Ohne den Termin faellt die Wahl auf den 9. Oktober (38 Tage, am
        # naechsten an den bevorzugten 35).
        assert select_expiration(termine, as_of=STICHTAG, parameters=PARAMETER) == date(
            2026, 10, 9
        )
        assert gewaehlt == date(2026, 10, 2)

    def test_ein_verfall_am_berichtstag_zaehlt_nicht_als_davor(self) -> None:
        """Ob die Zahlen vor der Eroeffnung oder nach dem Schluss kommen,
        weiss die Quelle nicht -- ein Verfall am Berichtstag waere ein
        Wagnis auf diese Unbekannte."""
        assert (
            select_expiration(
                [date(2026, 10, 2)],
                as_of=STICHTAG,
                parameters=PARAMETER,
                next_earnings_date=date(2026, 10, 2),
            )
            is None
        )

    def test_ohne_zulaessigen_termin_vor_den_zahlen_entsteht_keiner(self) -> None:
        assert (
            select_expiration(
                [date(2026, 10, 2), date(2026, 10, 9)],
                as_of=STICHTAG,
                parameters=PARAMETER,
                next_earnings_date=date(2026, 9, 15),
            )
            is None
        )

    def test_ein_termin_nach_dem_verfall_laesst_den_vorschlag_stehen(self) -> None:
        strategie = self.analyse(
            next_earnings_date=date(2026, 11, 5)
        ).strategies[0]
        assert strategie.earnings_within_term is False

    def test_ein_unbekannter_termin_schraenkt_die_wahl_nicht_ein(self) -> None:
        """Fehlende Daten bestrafen nicht (CLAUDE.md).

        Wuerde ein unbekannter Termin einschraenken, bliebe von der
        Optionsanalyse bei jedem Symbol ohne Earnings-Abdeckung nichts
        uebrig.
        """
        termine = [date(2026, 9, 25), date(2026, 10, 2), date(2026, 10, 9)]

        assert select_expiration(
            termine, as_of=STICHTAG, parameters=PARAMETER, next_earnings_date=None
        ) == date(2026, 10, 9)
        assert self.analyse().strategies[0].earnings_within_term is None


class TestParameterAmErgebnis:
    def test_die_auswahlparameter_stehen_am_ergebnis(self) -> None:
        """CLAUDE.md: Versionierung an jedem Ergebnis.

        Ohne sie waere ``analysis_version`` eine leere Zusage -- das
        Zielfenster ist konfigurierbar, und eine Rendite aus einem
        60-Tage-Kontrakt ist eine andere Zahl als eine aus einem 30-Tage-.
        """
        analyse = build_options_analysis(
            [notierung(90.0)],
            price=100.0,
            expiration=date(2026, 10, 2),
            as_of=STICHTAG,
            evaluated_at=BEWERTET_AM,
            parameters=PARAMETER,
        )
        assert analyse.parameters["min_delta"] == pytest.approx(0.10)
        assert analyse.parameters["max_days_to_expiration"] == pytest.approx(60.0)
        assert analyse.parameters["target_days_to_expiration"] == pytest.approx(35.0)
