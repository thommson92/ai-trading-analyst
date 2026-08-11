"""Indikatorberechnung gegen die Vorgaben aus der G1-Pruefvorlage.

Die Referenzwerte stammen nicht aus dem Code selbst, sondern aus von Hand
nachvollziehbaren Faellen: konstante Reihen, monotone Reihen und die
Standard-RSI-Definition. Ein Test, der nur wiederholt, was die Implementierung
tut, wuerde einen Vorzeichenfehler mitmachen.
"""

from __future__ import annotations

import pytest

from ai_trading_analyst.domain.screening.indicators import (
    IndicatorParameters,
    UnsupportedSmoothingMethodError,
    compute_indicator_values,
    exponential_moving_average,
    relative_strength_index,
    simple_moving_average,
    smooth,
    wilder_moving_average,
)

G1_PARAMETERS = IndicatorParameters(
    rsi_length=14,
    rsi_method="wilder",
    rsi_ma_length=14,
    rsi_ma_type="sma",
    fast_ema_length=5,
    slow_ema_length=20,
)


class TestSimpleMovingAverage:
    def test_vor_dem_ersten_vollstaendigen_fenster_gibt_es_keinen_wert(self) -> None:
        assert simple_moving_average([1.0, 2.0, 3.0], 3)[:2] == [None, None]

    def test_durchschnitt_des_letzten_fensters(self) -> None:
        assert simple_moving_average([1.0, 2.0, 3.0, 4.0], 3) == [None, None, 2.0, 3.0]

    def test_eine_luecke_im_fenster_ergibt_keinen_wert_statt_eines_geschaetzten(self) -> None:
        result = simple_moving_average([1.0, None, 3.0, 4.0, 5.0], 3)
        assert result == [None, None, None, None, 4.0]


class TestExponentialMovingAverage:
    def test_startet_auf_dem_einfachen_durchschnitt_des_ersten_fensters(self) -> None:
        assert exponential_moving_average([2.0, 4.0, 6.0], 3)[2] == 4.0

    def test_konstante_reihe_bleibt_konstant(self) -> None:
        result = exponential_moving_average([5.0] * 10, 4)
        assert result[3:] == [5.0] * 7

    def test_neuer_wert_zieht_den_durchschnitt_mit_dem_erwarteten_gewicht(self) -> None:
        # Seed ueber [1, 1, 1] ist 1.0; alpha = 2/(3+1) = 0.5.
        result = exponential_moving_average([1.0, 1.0, 1.0, 3.0], 3)
        assert result[3] == 2.0

    def test_nach_einer_luecke_beginnt_die_glaettung_neu(self) -> None:
        result = exponential_moving_average([1.0, 1.0, 1.0, None, 2.0, 2.0, 2.0], 3)
        assert result[3] is None
        assert result[4] is None
        assert result[5] is None
        assert result[6] == 2.0


class TestWilderMovingAverage:
    def test_gewichtet_den_neuen_wert_mit_eins_durch_laenge(self) -> None:
        # Seed ueber [1, 1] ist 1.0; Wilder-Gewicht = 1/2.
        assert wilder_moving_average([1.0, 1.0, 3.0], 2)[2] == 2.0

    def test_konvergiert_langsamer_als_der_ema_gleicher_laenge(self) -> None:
        values: list[float | None] = [*([1.0] * 5), *([10.0] * 5)]
        wilder = wilder_moving_average(values, 5)[-1]
        ema = exponential_moving_average(values, 5)[-1]
        assert wilder is not None and ema is not None
        assert wilder < ema


class TestSmoothAuswahl:
    @pytest.mark.parametrize("method", ["sma", "ema", "wilder"])
    def test_alle_konfigurierbaren_methoden_sind_implementiert(self, method: str) -> None:
        assert smooth([1.0, 2.0, 3.0], 2, method)[-1] is not None

    def test_unbekannte_methode_scheitert_eindeutig(self) -> None:
        with pytest.raises(UnsupportedSmoothingMethodError, match="hull"):
            smooth([1.0, 2.0], 2, "hull")


class TestRelativeStrengthIndex:
    def test_erster_wert_liegt_am_index_der_laenge(self) -> None:
        closes = [float(value) for value in range(1, 40)]
        result = relative_strength_index(closes, 14)
        assert result[:14] == [None] * 14
        assert result[14] is not None

    def test_ausschliesslich_steigende_kurse_ergeben_hundert(self) -> None:
        closes = [float(value) for value in range(1, 40)]
        assert relative_strength_index(closes, 14)[-1] == 100.0

    def test_ausschliesslich_fallende_kurse_ergeben_null(self) -> None:
        closes = [float(value) for value in range(40, 1, -1)]
        assert relative_strength_index(closes, 14)[-1] == 0.0

    def test_gleich_grosse_gewinne_und_verluste_ergeben_fuenfzig(self) -> None:
        # Mit SMA-Glaettung enthaelt das 14er-Fenster genau sieben Gewinne und
        # sieben Verluste gleicher Groesse -- der RSI ist dann exakt 50.
        closes: list[float] = []
        price = 100.0
        for step in range(60):
            price += 1.0 if step % 2 == 0 else -1.0
            closes.append(price)
        assert relative_strength_index(closes, 14, "sma")[-1] == pytest.approx(50.0)

    def test_voellig_unbewegter_kurs_hat_keinen_definierten_rsi(self) -> None:
        # 0/0 ist nicht definiert. Ein erfundener Wert (100 oder 50) wuerde
        # als echtes Signal weiterverarbeitet -- deshalb bleibt er offen.
        assert relative_strength_index([100.0] * 30, 14)[-1] is None


class TestComputeIndicatorValues:
    def test_ergebnis_ist_genauso_lang_wie_die_kursreihe(self) -> None:
        closes = [100.0 + index for index in range(300)]
        values = compute_indicator_values(closes, G1_PARAMETERS)
        assert len(values) == len(closes)

    def test_am_anfang_fehlen_werte_statt_geraten_zu_werden(self) -> None:
        closes = [100.0 + index for index in range(300)]
        first = compute_indicator_values(closes, G1_PARAMETERS)[0]
        assert (first.rsi, first.rsi_ma, first.ema5, first.ema20) == (None, None, None, None)

    def test_nach_dem_warmup_sind_alle_vier_werte_vorhanden(self) -> None:
        closes = [100.0 + index for index in range(300)]
        last = compute_indicator_values(closes, G1_PARAMETERS)[-1]
        assert last.rsi is not None
        assert last.rsi_ma is not None
        assert last.ema5 is not None
        assert last.ema20 is not None

    def test_rsi_ma_mittelt_die_rsi_werte_und_nicht_den_preis(self) -> None:
        closes = [100.0 + index for index in range(300)]
        values = compute_indicator_values(closes, G1_PARAMETERS)
        rsi_series = relative_strength_index(closes, 14)
        expected = simple_moving_average(rsi_series, 14)
        assert [value.rsi_ma for value in values] == expected

    def test_der_schnelle_ema_folgt_dem_kurs_enger_als_der_langsame(self) -> None:
        closes = [100.0] * 50 + [120.0] * 10
        last = compute_indicator_values(closes, G1_PARAMETERS)[-1]
        assert last.ema5 is not None and last.ema20 is not None
        assert last.ema5 > last.ema20


class TestIndicatorParameters:
    def test_unbekannte_glaettung_faellt_beim_bauen_auf(self) -> None:
        with pytest.raises(UnsupportedSmoothingMethodError):
            IndicatorParameters(
                rsi_length=14,
                rsi_method="hull",
                rsi_ma_length=14,
                rsi_ma_type="sma",
                fast_ema_length=5,
                slow_ema_length=20,
            )

    def test_laenge_null_faellt_beim_bauen_auf(self) -> None:
        with pytest.raises(ValueError, match="rsi_length"):
            IndicatorParameters(
                rsi_length=0,
                rsi_method="wilder",
                rsi_ma_length=14,
                rsi_ma_type="sma",
                fast_ema_length=5,
                slow_ema_length=20,
            )
