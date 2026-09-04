"""Tests des historischen Put-Verkaufs (ADR 0058, Stufe 1).

Geprueft wird gegen Kurspfade, deren Ausgang **ohne Modell** feststeht: Ein
Put auf eine Aktie, die nie unter den Strike faellt, verfaellt wertlos und
bringt genau die Praemie. Einer auf eine Aktie, die abstuerzt, wird
angedient, und der Verlust ist Strike minus Schlusskurs. Alles, was das
Modell beitraegt, steckt in der Praemie -- und die steht in beiden Faellen
als eigener Wert am Ergebnis, statt in einer Summe zu verschwinden.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from ai_trading_analyst.domain.backtesting.options_trade import (
    OptionsBacktestParameters,
    TradeOutcome,
    simulate_put_sale,
)
from ai_trading_analyst.domain.options import KONTRAKTGROESSE
from ai_trading_analyst.domain.screening import Candle, CandleSeries, IndicatorValues

NEW_YORK = ZoneInfo("America/New_York")
PARAMETER = OptionsBacktestParameters()
OHNE_ABSCHLAG = OptionsBacktestParameters(execution_haircut=0.0)

_ERSTE_KERZE = datetime(2026, 1, 2, 9, 30, tzinfo=NEW_YORK)
"""Ein Freitag. Die Reihe laeuft von dort ueber Werktage weiter."""


def handelsreihe(closes: list[float]) -> CandleSeries:
    """Zwei Kerzen je Werktag, mit den uebergebenen Schlusskursen.

    Wochenenden werden uebersprungen -- ohne das lagen Verfallstermine
    regelmaessig auf Kerzen, die es an einem echten Freitag nicht gaebe, und
    die Restlaufzeiten stimmten nicht mit dem Kalender ueberein.
    """
    kerzen = []
    zeitpunkt = _ERSTE_KERZE
    for index, close in enumerate(closes):
        position = index % 2
        if position == 0 and index > 0:
            zeitpunkt = zeitpunkt.replace(hour=9, minute=30) + timedelta(days=1)
            while zeitpunkt.weekday() >= 5:
                zeitpunkt += timedelta(days=1)
        elif position == 1:
            zeitpunkt = zeitpunkt.replace(hour=13, minute=15)
        kerzen.append(
            Candle(
                timestamp=zeitpunkt,
                daily_candle_index=position + 1,
                open=close,
                high=close,
                low=close,
                close=close,
                volume=1_000.0,
            )
        )
    indikatoren = tuple(
        IndicatorValues(rsi=50.0, rsi_ma=50.0, ema5=99.0, ema20=99.0) for _ in closes
    )
    return CandleSeries(candles=tuple(kerzen), indicators=indikatoren)


def _schwankend(anzahl: int, *, um: float = 100.0, ausschlag: float = 1.0) -> list[float]:
    """Eine Reihe mit echter, aber kleiner Bewegung.

    Der Wechsel laeuft ueber den **Tag** (``i // 2``) und nicht ueber die
    Kerze: Bei zwei Kerzen je Tag traegt sonst jeder Tagesschluss denselben
    Wert, die realisierte Volatilitaet ist null, und es entstuende gar kein
    Trade. Genau darauf sind die ersten Fassungen dieser Tests
    hereingefallen.
    """
    return [um + (ausschlag if (i // 2) % 2 else -ausschlag) for i in range(anzahl)]


VORLAUF = 90
"""Kerzen vor dem Einstieg -- genug fuer das 30-Handelstage-Fenster."""


def ohne_tage(series: CandleSeries, weglassen: Callable[[date], bool]) -> CandleSeries:
    """Dieselbe Reihe ohne bestimmte Handelstage.

    Filtert Kerzen **und** Indikatoren zusammen -- ``CandleSeries`` verlangt
    gleiche Laenge, und das aus gutem Grund: Ein Indikator am falschen Index
    gehoerte zu einer anderen Kerze.
    """
    behalten = [
        (kerze, indikator)
        for kerze, indikator in zip(series.candles, series.indicators, strict=True)
        if not weglassen(kerze.timestamp.astimezone(NEW_YORK).date())
    ]
    return CandleSeries(
        candles=tuple(kerze for kerze, _ in behalten),
        indicators=tuple(indikator for _, indikator in behalten),
    )


class TestVollstaendigerTrade:
    def test_eine_ruhige_aktie_laesst_den_put_wertlos_verfallen(self) -> None:
        """Der Ausgang steht ohne Modell fest: Bleibt der Kurs ueber dem
        Strike, ist der Gewinn genau die vereinnahmte Praemie."""
        series = handelsreihe(_schwankend(VORLAUF + 80))

        trade = simulate_put_sale(
            series, VORLAUF, OHNE_ABSCHLAG, exchange_timezone=NEW_YORK
        )

        assert trade is not None
        assert trade.held_outcome is TradeOutcome.EXPIRED_WORTHLESS
        assert trade.held_profit == pytest.approx(trade.premium * KONTRAKTGROESSE)
        assert trade.strike < trade.underlying_at_entry
        assert -1.0 < trade.delta < 0.0

    def test_ein_absturz_fuehrt_zur_andienung(self) -> None:
        """Auch dieser Ausgang steht fest: Der Verlust ist Strike minus
        Schlusskurs, gegengerechnet mit der Praemie."""
        closes = _schwankend(VORLAUF + 10) + [40.0] * 70
        series = handelsreihe(closes)

        trade = simulate_put_sale(
            series, VORLAUF, OHNE_ABSCHLAG, exchange_timezone=NEW_YORK
        )

        assert trade is not None
        assert trade.held_outcome is TradeOutcome.ASSIGNED
        erwartet = (
            trade.premium - (trade.strike - trade.underlying_at_expiration)
        ) * KONTRAKTGROESSE
        assert trade.held_profit == pytest.approx(erwartet)
        assert trade.held_profit < 0.0

    def test_der_verfall_ist_ein_dritter_freitag(self) -> None:
        series = handelsreihe(_schwankend(VORLAUF + 80))

        trade = simulate_put_sale(
            series, VORLAUF, PARAMETER, exchange_timezone=NEW_YORK
        )

        assert trade is not None
        assert trade.expiration.weekday() == 4
        assert 15 <= trade.expiration.day <= 21
        assert (
            PARAMETER.min_days_to_expiration
            <= trade.days_to_expiration
            <= PARAMETER.max_days_to_expiration
        )


class TestManagementregeln:
    def test_der_zeitwert_allein_loest_die_gewinnmitnahme_aus(self) -> None:
        """Der Punkt der gemanagten Variante: Sie reagiert auf den Wert des
        Kontrakts, nicht auf den Kurs. Ein Put, der bei unveraendertem Kurs
        altert, faellt -- und genau das loest hier aus."""
        series = handelsreihe(_schwankend(VORLAUF + 80))

        trade = simulate_put_sale(
            series, VORLAUF, OHNE_ABSCHLAG, exchange_timezone=NEW_YORK
        )

        assert trade is not None
        assert trade.managed_outcome is TradeOutcome.TAKE_PROFIT
        assert trade.managed_exit_index < VORLAUF + 40
        # Weniger als die volle Praemie, aber positiv.
        assert 0.0 < trade.managed_profit < trade.held_profit

    def test_ein_absturz_loest_den_rueckkauf_aus(self) -> None:
        closes = _schwankend(VORLAUF + 4) + [55.0] * 76
        series = handelsreihe(closes)

        trade = simulate_put_sale(
            series, VORLAUF, OHNE_ABSCHLAG, exchange_timezone=NEW_YORK
        )

        assert trade is not None
        assert trade.managed_outcome is TradeOutcome.STOPPED_OUT
        # Der Stop begrenzt: Er kostet weniger als das Halten bis zum Verfall.
        assert trade.managed_profit > trade.held_profit
        assert trade.managed_exit_index < len(series) - 1

    def test_der_ausfuehrungsabschlag_wirkt_auf_beiden_seiten(self) -> None:
        """Einmal beim Verkauf, einmal beim Rueckkauf -- und genau das soll er
        zeigen: Jede Managementregel kostet eine zusaetzliche Transaktion."""
        series = handelsreihe(_schwankend(VORLAUF + 80))

        ohne = simulate_put_sale(
            series, VORLAUF, OHNE_ABSCHLAG, exchange_timezone=NEW_YORK
        )
        mit = simulate_put_sale(series, VORLAUF, PARAMETER, exchange_timezone=NEW_YORK)

        assert ohne is not None
        assert mit is not None
        assert mit.premium < ohne.premium
        assert mit.managed_profit < ohne.managed_profit
        # Der gehaltene Trade zahlt nur einmal -- kein Rueckkauf am Verfall.
        assert mit.held_profit < ohne.held_profit


class TestKeinTrade:
    """Jeder Grund ist sachlich, keiner ein Fehler -- und ``None`` ist eine
    Aussage ueber die Grundlage, die der Aufrufer zaehlt."""

    def test_ohne_genug_kurshistorie_entsteht_keiner(self) -> None:
        series = handelsreihe(_schwankend(60))

        assert simulate_put_sale(series, 1, PARAMETER, exchange_timezone=NEW_YORK) is None

    def test_ohne_bewegung_gibt_es_keine_volatilitaet_und_keinen_trade(self) -> None:
        """Eine konstante Reihe hat die realisierte Volatilitaet null. Ein
        Put waere dann wertlos, und ein Vorschlag ohne Praemie ist keiner."""
        series = handelsreihe([100.0] * (VORLAUF + 80))

        assert (
            simulate_put_sale(series, VORLAUF, PARAMETER, exchange_timezone=NEW_YORK)
            is None
        )

    def test_endet_die_reihe_vor_dem_verfall_entsteht_keiner(self) -> None:
        """Ein bei Reihenende abgeschnittener Trade saehe wie ein Ergebnis
        aus -- dasselbe Argument wie bei den Horizonten der Aktienseite."""
        series = handelsreihe(_schwankend(VORLAUF + 6))

        assert (
            simulate_put_sale(series, VORLAUF, PARAMETER, exchange_timezone=NEW_YORK)
            is None
        )


class TestLookAhead:
    def test_die_volatilitaet_kennt_nur_kerzen_vor_dem_einstieg(self) -> None:
        """Doc 10 Paragraph 6.6. Ein Sprung **nach** dem Einstieg darf die
        unterstellte Volatilitaet nicht veraendern -- sonst haette der
        Verkaeufer eine Praemie bekommen, die auf Zukunft steht."""
        ruhig = handelsreihe(_schwankend(VORLAUF + 80))
        mit_sprung = handelsreihe(
            _schwankend(VORLAUF + 1) + _schwankend(79, um=100.0, ausschlag=25.0)
        )

        a = simulate_put_sale(ruhig, VORLAUF, PARAMETER, exchange_timezone=NEW_YORK)
        b = simulate_put_sale(mit_sprung, VORLAUF, PARAMETER, exchange_timezone=NEW_YORK)

        assert a is not None
        assert b is not None
        assert a.volatility == pytest.approx(b.volatility)
        assert a.premium == pytest.approx(b.premium)
        assert a.strike == pytest.approx(b.strike)


class TestVolatilitaetsaufschlag:
    def test_ein_hoeherer_aufschlag_schiebt_den_strike_weiter_vom_geld(self) -> None:
        """Der Aufschlag ist gesetzt und nicht gemessen (Festlegung 2) -- das
        Ergebnis gehoert deshalb als Band ueber mehrere Aufschlaege gelesen.

        Zugesichert wird der **Strike**, nicht die Praemie: Bei hoeherer
        Volatilitaet traegt derselbe Strike ein groesseres Delta, die Suche
        nach 0,25 wandert also weiter aus dem Geld. Die Praemie ist deshalb
        nicht monoton -- ein tieferer Strike kann trotz hoeherer Volatilitaet
        billiger sein. Eine Monotonie-Zusicherung auf die Praemie waere
        schlicht falsch, und die erste Fassung dieses Tests behauptete sie.
        """
        series = handelsreihe(_schwankend(VORLAUF + 80))

        strikes = []
        volatilitaeten = []
        for aufschlag in (1.0, 1.15, 1.3, 1.5):
            trade = simulate_put_sale(
                series,
                VORLAUF,
                OptionsBacktestParameters(
                    volatility_uplift=aufschlag, execution_haircut=0.0
                ),
                exchange_timezone=NEW_YORK,
            )
            assert trade is not None
            strikes.append(trade.strike)
            volatilitaeten.append(trade.volatility)

        assert volatilitaeten == sorted(volatilitaeten)
        assert volatilitaeten[-1] > volatilitaeten[0]
        assert strikes == sorted(strikes, reverse=True)
        assert strikes[-1] < strikes[0]


class TestZeitzone:
    def test_der_stichtag_kommt_aus_der_boersenzeit(self) -> None:
        """Kerzen koennen in jeder Zone ankommen. Derselbe Augenblick, in UTC
        datiert, muss denselben Handelstag und damit dieselbe Restlaufzeit
        ergeben."""
        series = handelsreihe(_schwankend(VORLAUF + 80))
        in_utc = CandleSeries(
            candles=tuple(
                Candle(
                    timestamp=k.timestamp.astimezone(UTC),
                    daily_candle_index=k.daily_candle_index,
                    open=k.open,
                    high=k.high,
                    low=k.low,
                    close=k.close,
                    volume=k.volume,
                )
                for k in series.candles
            ),
            indicators=series.indicators,
        )

        a = simulate_put_sale(series, VORLAUF, PARAMETER, exchange_timezone=NEW_YORK)
        b = simulate_put_sale(in_utc, VORLAUF, PARAMETER, exchange_timezone=NEW_YORK)

        assert a is not None
        assert b is not None
        assert a.entry_date == b.entry_date
        assert a.expiration == b.expiration
        assert a.days_to_expiration == b.days_to_expiration
        assert a.premium == pytest.approx(b.premium)


class TestBekannteKalenderfaelle:
    @pytest.mark.parametrize(
        ("jahr", "monat", "tag"),
        [
            (2021, 1, 15),
            (2024, 2, 16),
            (2026, 9, 18),
            (2026, 10, 16),
            (2026, 5, 15),
        ],
    )
    def test_dritte_freitage(self, jahr: int, monat: int, tag: int) -> None:
        from ai_trading_analyst.domain.options import third_friday

        assert third_friday(jahr, monat) == date(jahr, monat, tag)


class TestRueckfallAufDieGrundlinie:
    """Trades, die **keine** der beiden Marken erreichen.

    ADR 0058 Festlegung 7 nennt genau sie als Zweck des Backtests: Die
    rechnerische Grenze von rund 86 Prozent gilt nur, wenn jeder Trade an
    einer der Marken endet. Wie viele stattdessen bis zum Verfall laufen,
    ist eine der Fragen, die der Lauf beantworten soll.
    """

    @pytest.mark.parametrize("anteil", [0.10, 0.33, 0.50, 0.90, 0.99])
    def test_ein_wertlos_verfallender_put_wird_immer_vorher_glattgestellt(
        self, anteil: float
    ) -> None:
        """Ein Befund, kein Randfall: Verfaellt der Put wertlos, faellt sein
        Preis auf dem Weg dorthin unter **jede** Gewinnmarke unter hundert
        Prozent. Die gemanagte Variante vereinnahmt deshalb nie die volle
        Praemie -- auch dann nicht, wenn das Halten sie gebracht haette.

        Das ist genau die Haelfte der Rechnung aus ADR 0058 Festlegung 7: Die
        Gewinne sind gedeckelt, die Verluste nicht, und daher stammt die
        Grenze von rund 86 Prozent Trefferquote.
        """
        weit = OptionsBacktestParameters(
            take_profit_fraction=anteil, stop_multiple=100.0, execution_haircut=0.0
        )
        series = handelsreihe(_schwankend(VORLAUF + 80))

        trade = simulate_put_sale(series, VORLAUF, weit, exchange_timezone=NEW_YORK)

        assert trade is not None
        assert trade.held_outcome is TradeOutcome.EXPIRED_WORTHLESS
        assert trade.managed_outcome is TradeOutcome.TAKE_PROFIT
        assert 0.0 < trade.managed_profit < trade.held_profit

    def test_auch_bei_andienung_faellt_er_auf_die_grundlinie_zurueck(self) -> None:
        """Ein Absturz ohne erreichten Stop: Der Verlust ist der volle."""
        weit = OptionsBacktestParameters(
            take_profit_fraction=0.99, stop_multiple=100.0, execution_haircut=0.0
        )
        closes = _schwankend(VORLAUF + 10) + [40.0] * 70
        series = handelsreihe(closes)

        trade = simulate_put_sale(series, VORLAUF, weit, exchange_timezone=NEW_YORK)

        assert trade is not None
        assert trade.held_outcome is TradeOutcome.ASSIGNED
        assert trade.managed_outcome is TradeOutcome.ASSIGNED
        assert trade.managed_profit == pytest.approx(trade.held_profit)


class TestAbrechnungskerze:
    def test_ein_feiertag_am_verfall_laesst_den_vortag_abrechnen(self) -> None:
        """Faellt der dritte Freitag auf einen Feiertag -- Karfreitag trifft
        ihn regelmaessig --, gibt es an ihm keine Kerze. Der Handel des
        Vortags ist dann der letzte und bestimmt die Andienung."""
        vollstaendig = handelsreihe(_schwankend(VORLAUF + 80))
        referenz = simulate_put_sale(
            vollstaendig, VORLAUF, OHNE_ABSCHLAG, exchange_timezone=NEW_YORK
        )
        assert referenz is not None

        gekuerzt = ohne_tage(vollstaendig, lambda tag: tag == referenz.expiration)

        trade = simulate_put_sale(
            gekuerzt, VORLAUF, OHNE_ABSCHLAG, exchange_timezone=NEW_YORK
        )

        assert trade is not None
        assert trade.expiration == referenz.expiration
        # Abgerechnet wird auf dem Vortag, nicht auf irgendeiner Kerze.
        abrechnung = gekuerzt.candle(
            next(
                i
                for i in range(len(gekuerzt) - 1, -1, -1)
                if gekuerzt.candle(i).timestamp.astimezone(NEW_YORK).date()
                <= trade.expiration
            )
        )
        assert trade.underlying_at_expiration == pytest.approx(abrechnung.close)

    def test_ein_loch_ueber_den_verfall_hinweg_erzeugt_keinen_trade(self) -> None:
        """Der Befund der Review: Ohne Abstandsgrenze wuerde der Trade auf
        einem Kurs abgerechnet, der Wochen vor dem Verfall liegt -- und saehe
        trotzdem wie ein vollstaendiges Ergebnis aus."""
        vollstaendig = handelsreihe(_schwankend(VORLAUF + 80))
        referenz = simulate_put_sale(
            vollstaendig, VORLAUF, PARAMETER, exchange_timezone=NEW_YORK
        )
        assert referenz is not None

        loch_ab = referenz.expiration - timedelta(days=28)
        loch_bis = referenz.expiration + timedelta(days=3)
        mit_loch = ohne_tage(vollstaendig, lambda tag: loch_ab <= tag <= loch_bis)

        assert (
            simulate_put_sale(mit_loch, VORLAUF, PARAMETER, exchange_timezone=NEW_YORK)
            is None
        )


class TestStrikeRaster:
    def test_ueber_zweihundert_dollar_gilt_der_fuenferschritt(self) -> None:
        from ai_trading_analyst.domain.options import snap_to_strike_grid, strike_step

        assert strike_step(15.0) == pytest.approx(1.0)
        assert strike_step(100.0) == pytest.approx(2.5)
        assert strike_step(232.0) == pytest.approx(5.0)
        assert snap_to_strike_grid(231.7, price=232.0) == pytest.approx(230.0)
        assert snap_to_strike_grid(97.4, price=100.0) == pytest.approx(97.5)
