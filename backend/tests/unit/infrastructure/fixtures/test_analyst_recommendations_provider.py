"""Der Fixture-Anbieter der Analystenempfehlungen (ADR 0043).

Er ist der Standard: Start, Tests und ein Lauf ohne Finnhub-Zugang haengen an
ihm. Was er zusichert, ist deshalb keine Testkulisse, sondern Vertrag.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from ai_trading_analyst.domain.analysis import AnalystRecommendationsProviderError, Stock
from ai_trading_analyst.domain.analysts import AnalystRecommendationStatus
from ai_trading_analyst.infrastructure.fixtures.analyst_recommendations_provider import (
    FixtureAnalystRecommendationsProvider,
)

BEZUG = date(2026, 8, 30)


def _stock(symbol: str) -> Stock:
    return Stock(id=uuid.uuid4(), symbol=symbol, exchange="NASDAQ")


def _provider() -> FixtureAnalystRecommendationsProvider:
    return FixtureAnalystRecommendationsProvider(reference_date=lambda: BEZUG)


class TestAbdeckung:
    def test_ein_bekanntes_symbol_liefert_die_verteilung(self) -> None:
        ergebnis = _provider().recommendations(_stock("FIXCAND"))

        assert ergebnis.status is AnalystRecommendationStatus.COMPLETED
        assert len(ergebnis.periods) == 4
        assert ergebnis.source == "fixture"

    def test_die_monatsstaende_haengen_am_bezugsdatum_nicht_am_kalender(self) -> None:
        """Wie beim Earnings-Fixture: Das Szenario bleibt stabil, auch wenn
        die Zeit weiterlaeuft."""
        staende = _provider().recommendations(_stock("FIXCAND")).periods

        assert [stand.period for stand in staende] == [
            date(2026, 8, 1),
            date(2026, 7, 1),
            date(2026, 6, 1),
            date(2026, 5, 1),
        ]

    def test_der_jahreswechsel_wird_richtig_gerechnet(self) -> None:
        """Ein Monatsstand drei Monate vor Februar liegt im Vorjahr."""
        provider = FixtureAnalystRecommendationsProvider(reference_date=lambda: date(2026, 2, 15))
        staende = provider.recommendations(_stock("FIXCAND")).periods
        assert staende[-1].period == date(2025, 11, 1)

    def test_ein_unbekanntes_symbol_ist_ohne_abdeckung(self) -> None:
        """Ein Fixture-Lauf muss mit jeder Watchlist zurechtkommen."""
        ergebnis = _provider().recommendations(_stock("NIEGEHOERT"))

        assert ergebnis.status is AnalystRecommendationStatus.UNKNOWN
        assert ergebnis.reason == "no_coverage"


class TestVerschiedeneVerteilungen:
    """Die Fixtures sind absichtlich ungleich.

    Beim letzten Mal blieben zwei Berichtsmutationen gruen, weil die Fixtures
    zu gleichfoermig waren -- wo alle Werte gleich sind, faellt eine
    Verwechslung nicht auf.
    """

    def test_zustimmung_und_ablehnung_sind_unterscheidbar(self) -> None:
        zustimmung = _provider().recommendations(_stock("FIXCAND")).latest
        ablehnung = _provider().recommendations(_stock("EARNCLEAR")).latest
        assert zustimmung is not None and ablehnung is not None

        assert zustimmung.strong_buy > zustimmung.strong_sell
        assert ablehnung.strong_sell > ablehnung.strong_buy

    def test_innerhalb_eines_standes_ist_keine_votenklasse_wie_die_andere(self) -> None:
        stand = _provider().recommendations(_stock("FIXCAND")).latest
        assert stand is not None
        werte = (stand.strong_buy, stand.buy, stand.hold, stand.sell, stand.strong_sell)
        assert len(set(werte)) == len(werte), "gleiche Werte verdecken eine Vertauschung"

    def test_die_zustimmung_veraendert_sich_ueber_die_monate(self) -> None:
        """Die Veraenderung ist ein eigenstaendiges Signal (ADR 0043) -- ein
        Fixture mit vier gleichen Staenden koennte das nicht zeigen."""
        staende = _provider().recommendations(_stock("FIXCAND")).periods
        assert staende[0].strong_buy > staende[-1].strong_buy


class TestFehlerfall:
    def test_das_fehlersymbol_wirft_die_vertragsausnahme(self) -> None:
        """Es hat naturgemaess keine Monatsstaende. Wuerde der Anbieter zuerst
        darauf pruefen, liefe es stillschweigend als "keine Abdeckung" durch
        -- und der Fehlerpfad waere ungetestet."""
        with pytest.raises(AnalystRecommendationsProviderError):
            _provider().recommendations(_stock("RATINGERROR"))


class TestQuellenadresse:
    """Ein Fixture-Lauf darf im Bericht nicht die Adresse des echten Dienstes
    als Herkunft ausweisen (ADR 0043; Muster ``FixtureResearchProvider``).

    Ausgeliefert steht ``analyst_ratings.provider`` auf ``fixture`` -- das ist
    also der **Normalfall**, nicht der Ausnahmefall.
    """

    def test_die_adresse_verweist_nicht_auf_finnhub(self) -> None:
        ergebnis = _provider().recommendations(_stock("FIXCAND"))

        assert ergebnis.source_url is not None
        assert "finnhub" not in ergebnis.source_url

    def test_auch_ohne_abdeckung_bleibt_die_adresse_die_des_fixtures(self) -> None:
        ergebnis = _provider().recommendations(_stock("NIEGEHOERT"))

        assert ergebnis.source_url is not None
        assert "finnhub" not in ergebnis.source_url
