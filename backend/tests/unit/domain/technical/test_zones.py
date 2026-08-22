"""Zonenbildung: Swing-Punkte, Buendelung, Beruehrungen (ADR 0025)."""

from __future__ import annotations

import itertools

import pytest

from ai_trading_analyst.domain.technical import (
    PriceZone,
    ZoneKind,
    ZoneStrength,
    build_zones,
    find_swing_points,
)

from .conftest import series_from_ohlc, series_from_prices, small_params, timestamp_at


def zone_of_kind(zones: tuple[PriceZone, ...], kind: ZoneKind) -> PriceZone:
    """Die eine Zone der gesuchten Art.

    Die Testreihen laufen ein Niveau wiederholt an und pendeln dabei ebenso
    wiederholt zur Ausgangslage zurueck -- beides ergibt zu Recht eine Zone.
    Die Auswahl macht sichtbar, welche der beiden ein Test gerade meint.
    """
    treffer = [zone for zone in zones if zone.kind is kind]
    assert len(treffer) == 1, f"erwartet genau eine Zone der Art {kind}, gefunden {len(treffer)}"
    return treffer[0]


class TestFindSwingPoints:
    def test_zickzack_ergibt_je_wendepunkt_einen_swing_punkt(self) -> None:
        series = series_from_prices([100, 110, 100, 112, 100])

        points = find_swing_points(series.candles, 0, len(series), pivot_reach=1)

        assert [(point.index, point.is_high) for point in points] == [
            (1, True),
            (2, False),
            (3, True),
        ]

    def test_juengste_kerzen_bilden_keinen_wendepunkt(self) -> None:
        """Ohne ``pivot_reach`` Kerzen rechts ist ein Hoch nicht bestaetigt.

        Sonst meldete jedes neue Verlaufshoch sofort eine Widerstandszone --
        genau da, wo der Kurs gerade steht.
        """
        series = series_from_prices([100, 105, 100, 120])

        points = find_swing_points(series.candles, 0, len(series), pivot_reach=1)

        assert 3 not in [point.index for point in points]

    def test_plateau_ergibt_nur_den_aeltesten_punkt(self) -> None:
        series = series_from_prices([100, 110, 110, 110, 100])

        punkte = find_swing_points(series.candles, 0, 5, pivot_reach=1)
        highs = [point.index for point in punkte if point.is_high]

        assert highs == [1]

    def test_ausschnitt_begrenzt_die_suche(self) -> None:
        series = series_from_prices([100, 110, 100, 110, 100, 110, 100])

        points = find_swing_points(series.candles, 3, 6, pivot_reach=1)

        assert [point.index for point in points] == [4]

    def test_reach_zwei_verlangt_zwei_kerzen_je_seite(self) -> None:
        series = series_from_prices([100, 101, 110, 101, 100])

        punkte = find_swing_points(series.candles, 0, 5, pivot_reach=2)
        assert [point.index for point in punkte if point.is_high] == [2]
        assert find_swing_points(series.candles, 0, 4, pivot_reach=2) == ()


class TestZonenbildung:
    def test_mehrfach_getestetes_niveau_wird_eine_zone(self) -> None:
        series = series_from_prices([100, 110, 100, 110, 100, 110, 100])

        zones = build_zones(series.candles, 0, len(series), close=100.0, params=small_params())

        widerstand = [zone for zone in zones if zone.kind is ZoneKind.RESISTANCE]
        assert len(widerstand) == 1
        assert widerstand[0].lower <= 110.0 <= widerstand[0].upper

    def test_weit_auseinanderliegende_punkte_bleiben_getrennte_zonen(self) -> None:
        series = series_from_prices([100, 110, 100, 110, 100, 130, 100, 130, 100])

        zones = build_zones(series.candles, 0, len(series), close=100.0, params=small_params())

        mitten = sorted(round(zone.midpoint) for zone in zones if zone.kind is ZoneKind.RESISTANCE)
        assert mitten == [110, 130]

    def test_zonengrenzen_sind_genau_die_spanne_der_wendepunkte(self) -> None:
        """Kein aufgeweitetes Band um den Mittelwert -- genau das erzeugte in
        ``v1`` durchgaengig ueberlappende Zonen (ADR 0025, Revision)."""
        params = small_params(zone_tolerance_pct=0.02, min_touches=1)
        series = series_from_prices([100.0, 110.0, 100.0, 111.5, 100.0])

        zones = build_zones(series.candles, 0, len(series), close=100.0, params=params)
        widerstand = zone_of_kind(zones, ZoneKind.RESISTANCE)

        assert (widerstand.lower, widerstand.upper) == (110.0, 111.5)

    def test_ein_einzelner_wendepunkt_ergibt_ein_niveau_ohne_breite(self) -> None:
        """Eine Mindestbreite haette das Niveau zu einem Band gemacht, das
        allein durch seine Breite Beruehrungen einsammelt -- in ``v1`` kam ein
        einzelner Wendepunkt so auf acht Beruehrungen und wurde STRONG."""
        params = small_params(min_touches=1)
        series = series_from_prices([100.0, 110.0, 100.0])

        zones = build_zones(series.candles, 0, len(series), close=100.0, params=params)
        widerstand = zone_of_kind(zones, ZoneKind.RESISTANCE)

        assert widerstand.lower == widerstand.upper == 110.0
        assert widerstand.pivot_count == 1
        assert widerstand.strength is ZoneStrength.WEAK

    def test_benachbarte_zonen_ueberlappen_einander_nicht(self) -> None:
        """Der Kernfehler von ``v1``: Die Buendelung trennte ab einer
        Toleranz, das Band war aber zwei Toleranzen breit. Bei AAPL
        ueberlappte dadurch jede Zone ihre Nachbarn."""
        series = series_from_prices([100.0, 110.0, 100.0, 110.0, 100.0, 111.5, 100.0, 111.5, 100.0])

        zones = build_zones(series.candles, 0, len(series), close=100.0, params=small_params())

        nach_preis = sorted(zones, key=lambda zone: zone.lower)
        for unten, oben in itertools.pairwise(nach_preis):
            assert unten.upper < oben.lower, f"{unten.upper} und {oben.lower} ueberlappen"

    def test_zone_unterhalb_des_kurses_ist_unterstuetzung(self) -> None:
        series = series_from_prices([100, 90, 100, 90, 100])

        zones = build_zones(series.candles, 0, len(series), close=100.0, params=small_params())

        unterstuetzung = zone_of_kind(zones, ZoneKind.SUPPORT)
        assert unterstuetzung.lower <= 90.0 <= unterstuetzung.upper

    def test_kurs_innerhalb_der_zone_wird_eigens_gekennzeichnet(self) -> None:
        """Weder Halt noch Deckel -- die Zuordnung zu einer Seite waere hier
        gerade dann falsch, wenn sie am meisten zaehlt."""
        series = series_from_prices([100, 110, 100, 110, 100])

        zones = build_zones(series.candles, 0, len(series), close=110.0, params=small_params())

        innen = zone_of_kind(zones, ZoneKind.PRICE_INSIDE)
        assert innen.lower <= 110.0 <= innen.upper
        assert innen.distance_pct == 0.0

    def test_abstand_misst_bis_zur_naechsten_kante(self) -> None:
        series = series_from_prices([100, 90, 100, 90, 100])

        zones = build_zones(series.candles, 0, len(series), close=100.0, params=small_params())

        zone = zone_of_kind(zones, ZoneKind.SUPPORT)
        assert zone.distance_pct == pytest.approx((100.0 - zone.upper) / 100.0)

    def test_einmal_beruehrtes_niveau_ist_keine_zone(self) -> None:
        series = series_from_prices([100, 130, 100, 101, 100, 101, 100])

        zones = build_zones(series.candles, 0, len(series), close=100.0, params=small_params())

        assert all(round(zone.midpoint) != 130 for zone in zones)


class TestBeruehrungen:
    def test_zusammenhaengender_aufenthalt_zaehlt_als_eine_beruehrung(self) -> None:
        """Sonst haenge die Staerke daran, wie lange der Kurs in der Zone
        feststeckte, statt daran, wie oft er an ihr abgeprallt ist."""
        series = series_from_prices([100, 110, 110, 110, 110, 100, 100])

        zones = build_zones(
            series.candles, 0, len(series), close=100.0, params=small_params(min_touches=1)
        )

        widerstand = next(zone for zone in zones if zone.kind is ZoneKind.RESISTANCE)
        assert widerstand.touch_count == 1

    def test_getrennte_anlaeufe_zaehlen_einzeln(self) -> None:
        series = series_from_prices([100, 110, 100, 110, 100, 110, 100])

        zones = build_zones(series.candles, 0, len(series), close=100.0, params=small_params())

        widerstand = next(zone for zone in zones if zone.kind is ZoneKind.RESISTANCE)
        assert widerstand.touch_count == 3

    def test_letzte_bestaetigung_ist_die_juengste_beruehrung(self) -> None:
        series = series_from_prices([100, 110, 100, 110, 100, 110, 100])

        widerstand = next(
            zone
            for zone in build_zones(series.candles, 0, len(series), 100.0, small_params())
            if zone.kind is ZoneKind.RESISTANCE
        )

        assert widerstand.last_confirmed_at == timestamp_at(5)

    def test_kerzenspanne_beruehrt_die_zone_auch_ohne_schlusskurs_darin(self) -> None:
        """Getestet wird eine Zone durch das Hoch der Kerze, nicht erst durch
        ihren Schluss."""
        series = series_from_ohlc(
            [(100, 99, 99), (110, 100, 100), (100, 99, 99), (110, 100, 100), (100, 99, 99)]
        )

        zones = build_zones(series.candles, 0, len(series), close=99.0, params=small_params())

        assert any(zone.kind is ZoneKind.RESISTANCE for zone in zones)


class TestStaerkeUndAuswahl:
    def test_staerke_folgt_der_zahl_der_wendepunkte(self) -> None:
        """Nicht der Beruehrungen: Eine Preisregion, in der der Kurs nur
        herumwandert, sammelt ebenso viele Beruehrungen wie eine, an der er
        umkehrt -- in ``v1`` wurden beide STRONG."""
        params = small_params(moderate_pivot_count=2, strong_pivot_count=3)
        preise = [100.0, 110.0, 100.0, 110.0, 100.0, 110.0, 100.0, 110.0, 100.0]
        preise += [130.0, 100.0, 130.0, 100.0]
        series = series_from_prices(preise)

        zones = build_zones(series.candles, 0, len(series), close=100.0, params=params)
        nach_preis = {round(zone.midpoint): zone for zone in zones}

        assert nach_preis[110].pivot_count == 4
        assert nach_preis[110].strength is ZoneStrength.STRONG
        assert nach_preis[130].pivot_count == 2
        assert nach_preis[130].strength is ZoneStrength.MODERATE

    def test_viele_beruehrungen_machen_eine_zone_ohne_wendepunkte_nicht_stark(self) -> None:
        """Der Fall aus dem AAPL-Lauf: ein Wendepunkt, acht Beruehrungen.
        Der Kurs wandert durch die Region, kehrt dort aber nicht um."""
        params = small_params(min_touches=2, moderate_pivot_count=3, strong_pivot_count=5)
        # 105 wird einmal zum Wendepunkt und danach mehrfach durchlaufen.
        preise = [100.0, 105.0, 100.0, 105.0, 110.0, 105.0, 100.0, 105.0, 110.0]
        series = series_from_prices(preise)

        zones = build_zones(series.candles, 0, len(series), close=110.0, params=params)
        bei_105 = next(zone for zone in zones if zone.lower <= 105.0 <= zone.upper)

        assert bei_105.touch_count >= 3
        assert bei_105.pivot_count <= 2
        assert bei_105.strength is ZoneStrength.WEAK

    def test_je_seite_bleiben_nur_die_naechstgelegenen_zonen(self) -> None:
        preise = [100.0]
        for hoch in (110.0, 120.0, 130.0, 140.0):
            preise += [hoch, 100.0, hoch, 100.0]
        series = series_from_prices(preise)

        zones = build_zones(
            series.candles, 0, len(series), close=100.0, params=small_params(max_zones_per_side=2)
        )

        widerstaende = sorted(
            round(zone.midpoint) for zone in zones if zone.kind is ZoneKind.RESISTANCE
        )
        assert widerstaende == [110, 120]

    def test_ergebnis_ist_nach_abstand_sortiert(self) -> None:
        preise = [100.0]
        for hoch in (110.0, 130.0):
            preise += [hoch, 100.0, hoch, 100.0]
        preise += [80.0, 100.0, 80.0, 100.0]
        series = series_from_prices(preise)

        zones = build_zones(series.candles, 0, len(series), close=100.0, params=small_params())

        assert [zone.distance_pct for zone in zones] == sorted(zone.distance_pct for zone in zones)

    def test_ohne_wendepunkte_bleibt_die_liste_leer(self) -> None:
        """Ein zulaessiges Ergebnis, kein Fehler."""
        series = series_from_prices([100.0 + index for index in range(10)])

        assert build_zones(series.candles, 0, len(series), close=109.0, params=small_params()) == ()
