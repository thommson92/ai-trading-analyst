"""Formel-Tests fuer die drei Signale (G1-Pruefvorlage Abschnitt 2).

Die Beispiele A1-A6, B1-B6 und C1-C6 sind woertlich aus der G1-Pruefvorlage
uebernommen -- jede Tabellenzeile dort ist hier ein Testfall.
"""

from __future__ import annotations

import pytest

from ai_trading_analyst.domain.screening import (
    CandleSeries,
    DataIncompleteError,
    IndicatorValues,
    ema5_ema20_cross,
    price_ema20_breakout,
    rsi_cross,
)
from tests.unit.domain.screening.conftest import make_candle


def series_for_rsi(
    rsi_prev: float, rsi_ma_prev: float, rsi_curr: float, rsi_ma_curr: float
) -> CandleSeries:
    return CandleSeries(
        candles=(make_candle(0), make_candle(1)),
        indicators=(
            IndicatorValues(rsi=rsi_prev, rsi_ma=rsi_ma_prev, ema5=None, ema20=None),
            IndicatorValues(rsi=rsi_curr, rsi_ma=rsi_ma_curr, ema5=None, ema20=None),
        ),
    )


def series_for_price_breakout(
    close_prev: float, ema20_prev: float, open_curr: float, close_curr: float, ema20_curr: float
) -> CandleSeries:
    return CandleSeries(
        candles=(
            make_candle(0, close=close_prev),
            make_candle(1, open=open_curr, close=close_curr),
        ),
        indicators=(
            IndicatorValues(rsi=None, rsi_ma=None, ema5=None, ema20=ema20_prev),
            IndicatorValues(rsi=None, rsi_ma=None, ema5=None, ema20=ema20_curr),
        ),
    )


def series_for_ema_cross(
    ema5_prev: float, ema20_prev: float, ema5_curr: float, ema20_curr: float
) -> CandleSeries:
    return CandleSeries(
        candles=(make_candle(0), make_candle(1)),
        indicators=(
            IndicatorValues(rsi=None, rsi_ma=None, ema5=ema5_prev, ema20=ema20_prev),
            IndicatorValues(rsi=None, rsi_ma=None, ema5=ema5_curr, ema20=ema20_curr),
        ),
    )


class TestSignalARsiCross:
    @pytest.mark.parametrize(
        ("rsi_prev", "rsi_ma_prev", "rsi_curr", "rsi_ma_curr"),
        [
            pytest.param(38.2, 41.0, 45.7, 42.1, id="A1_klarer_uebertritt"),
            pytest.param(41.0, 41.0, 43.5, 41.8, id="A2_gleichheit_auf_vorkerze"),
            pytest.param(29.9, 30.0, 30.05, 30.0, id="A3_knapper_uebertritt"),
        ],
    )
    def test_erfuellte_faelle(
        self, rsi_prev: float, rsi_ma_prev: float, rsi_curr: float, rsi_ma_curr: float
    ) -> None:
        series = series_for_rsi(rsi_prev, rsi_ma_prev, rsi_curr, rsi_ma_curr)
        assert rsi_cross(series, 1) is True

    @pytest.mark.parametrize(
        ("rsi_prev", "rsi_ma_prev", "rsi_curr", "rsi_ma_curr"),
        [
            pytest.param(45.0, 42.0, 47.0, 43.0, id="A4_bereits_oberhalb"),
            pytest.param(38.0, 41.0, 41.0, 41.0, id="A5_gleichheit_auf_aktueller_kerze"),
            pytest.param(38.0, 41.0, 40.5, 41.0, id="A6_angenaehert_ohne_uebertritt"),
        ],
    )
    def test_nicht_erfuellte_faelle(
        self, rsi_prev: float, rsi_ma_prev: float, rsi_curr: float, rsi_ma_curr: float
    ) -> None:
        series = series_for_rsi(rsi_prev, rsi_ma_prev, rsi_curr, rsi_ma_curr)
        assert rsi_cross(series, 1) is False

    def test_fehlender_wert_loest_data_incomplete_aus(self) -> None:
        series = series_for_rsi(38.2, 41.0, 45.7, 42.1)
        broken = CandleSeries(
            candles=series.candles,
            indicators=(
                series.indicators[0],
                IndicatorValues(rsi=None, rsi_ma=42.1, ema5=None, ema20=None),
            ),
        )
        with pytest.raises(DataIncompleteError):
            rsi_cross(broken, 1)

    def test_fehlende_vorkerze_loest_data_incomplete_aus(self) -> None:
        series = series_for_rsi(38.2, 41.0, 45.7, 42.1)
        with pytest.raises(DataIncompleteError):
            rsi_cross(series, 0)


_PRICE_BREAKOUT_PARAM_NAMES = ("close_prev", "ema20_prev", "open_curr", "close_curr", "ema20_curr")


class TestSignalBPriceEma20Breakout:
    @pytest.mark.parametrize(
        _PRICE_BREAKOUT_PARAM_NAMES,
        [
            pytest.param(99.20, 100.00, 99.80, 100.60, 100.20, id="B1_alle_teilbedingungen"),
            pytest.param(100.00, 100.00, 100.00, 100.05, 100.00, id="B2_gleichheit_vorkerze"),
            pytest.param(98.50, 100.00, 100.20, 100.21, 100.20, id="B3_open_exakt_auf_ema20"),
        ],
    )
    def test_erfuellte_faelle(
        self,
        close_prev: float,
        ema20_prev: float,
        open_curr: float,
        close_curr: float,
        ema20_curr: float,
    ) -> None:
        series = series_for_price_breakout(
            close_prev, ema20_prev, open_curr, close_curr, ema20_curr
        )
        assert price_ema20_breakout(series, 1) is True

    @pytest.mark.parametrize(
        _PRICE_BREAKOUT_PARAM_NAMES,
        [
            pytest.param(99.20, 100.00, 101.80, 100.60, 100.20, id="B4_gap_up"),
            pytest.param(99.20, 100.00, 99.80, 100.20, 100.20, id="B5_gleichheit_auf_close"),
            pytest.param(100.50, 100.00, 99.80, 100.60, 100.20, id="B6_bereits_oberhalb"),
        ],
    )
    def test_nicht_erfuellte_faelle(
        self,
        close_prev: float,
        ema20_prev: float,
        open_curr: float,
        close_curr: float,
        ema20_curr: float,
    ) -> None:
        series = series_for_price_breakout(
            close_prev, ema20_prev, open_curr, close_curr, ema20_curr
        )
        assert price_ema20_breakout(series, 1) is False

    def test_fehlender_ema20_wert_loest_data_incomplete_aus(self) -> None:
        series = CandleSeries(
            candles=(make_candle(0, close=99.0), make_candle(1, open=99.5, close=100.5)),
            indicators=(
                IndicatorValues(rsi=None, rsi_ma=None, ema5=None, ema20=100.0),
                IndicatorValues(rsi=None, rsi_ma=None, ema5=None, ema20=None),
            ),
        )
        with pytest.raises(DataIncompleteError):
            price_ema20_breakout(series, 1)

    def test_fehlende_vorkerze_loest_data_incomplete_aus(self) -> None:
        series = series_for_price_breakout(99.20, 100.00, 99.80, 100.60, 100.20)
        with pytest.raises(DataIncompleteError):
            price_ema20_breakout(series, 0)


class TestSignalCEma5Ema20Cross:
    @pytest.mark.parametrize(
        ("ema5_prev", "ema20_prev", "ema5_curr", "ema20_curr"),
        [
            pytest.param(99.80, 100.00, 100.90, 100.50, id="C1_klarer_uebertritt"),
            pytest.param(100.00, 100.00, 100.30, 100.10, id="C2_gleichheit_auf_vorkerze"),
            pytest.param(99.95, 100.00, 100.001, 100.00, id="C3_knapper_uebertritt"),
        ],
    )
    def test_erfuellte_faelle(
        self, ema5_prev: float, ema20_prev: float, ema5_curr: float, ema20_curr: float
    ) -> None:
        series = series_for_ema_cross(ema5_prev, ema20_prev, ema5_curr, ema20_curr)
        assert ema5_ema20_cross(series, 1) is True

    @pytest.mark.parametrize(
        ("ema5_prev", "ema20_prev", "ema5_curr", "ema20_curr"),
        [
            pytest.param(100.50, 100.00, 100.90, 100.50, id="C4_bereits_oberhalb"),
            pytest.param(99.80, 100.00, 100.00, 100.00, id="C5_gleichheit_auf_aktueller_kerze"),
            pytest.param(99.50, 100.00, 99.90, 100.00, id="C6_angenaehert_ohne_uebertritt"),
        ],
    )
    def test_nicht_erfuellte_faelle(
        self, ema5_prev: float, ema20_prev: float, ema5_curr: float, ema20_curr: float
    ) -> None:
        series = series_for_ema_cross(ema5_prev, ema20_prev, ema5_curr, ema20_curr)
        assert ema5_ema20_cross(series, 1) is False

    def test_fehlender_ema5_wert_loest_data_incomplete_aus(self) -> None:
        series = CandleSeries(
            candles=(make_candle(0), make_candle(1)),
            indicators=(
                IndicatorValues(rsi=None, rsi_ma=None, ema5=99.0, ema20=100.0),
                IndicatorValues(rsi=None, rsi_ma=None, ema5=None, ema20=100.0),
            ),
        )
        with pytest.raises(DataIncompleteError):
            ema5_ema20_cross(series, 1)

    def test_fehlende_vorkerze_loest_data_incomplete_aus(self) -> None:
        series = series_for_ema_cross(99.80, 100.00, 100.90, 100.50)
        with pytest.raises(DataIncompleteError):
            ema5_ema20_cross(series, 0)
