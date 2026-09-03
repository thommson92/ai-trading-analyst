"""Formel-Tests fuer die fuenf Kriterien (G1-Pruefvorlage Abschnitt 2).

Die Beispiele A1-A6, B1-B6, C1-C6, D1-D6 und E1-E8 sind woertlich aus der
G1-Pruefvorlage uebernommen -- jede Tabellenzeile dort ist hier ein Testfall.
"""

from __future__ import annotations

import pytest

from ai_trading_analyst.domain.screening import (
    CandleSeries,
    DataIncompleteError,
    IndicatorValues,
    ema5_ema20_cross,
    no_recent_ema_downcross,
    price_ema20_breakout,
    rsi_cross,
    rsi_oversold,
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
            pytest.param(99.20, 100.00, 99.80, 100.60, 100.20, id="B1_kreuzung_auf_close"),
            pytest.param(100.00, 100.00, 100.00, 100.05, 100.00, id="B2_gleichheit_vorkerze"),
            pytest.param(98.50, 100.00, 100.20, 100.21, 100.20, id="B3_knapper_uebertritt"),
            pytest.param(99.20, 100.00, 101.80, 100.60, 100.20, id="B4_gap_up_zaehlt_jetzt"),
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


def series_for_oversold(*rsi_values: float | None) -> CandleSeries:
    return CandleSeries(
        candles=tuple(make_candle(i) for i in range(len(rsi_values))),
        indicators=tuple(
            IndicatorValues(rsi=rsi, rsi_ma=None, ema5=None, ema20=None) for rsi in rsi_values
        ),
    )


class TestSignalDRsiOversold:
    @pytest.mark.parametrize(
        "rsi",
        [
            pytest.param(22.4, id="D1_deutlich_ueberverkauft"),
            pytest.param(29.99, id="D2_knapp_darunter"),
        ],
    )
    def test_erfuellte_faelle(self, rsi: float) -> None:
        assert rsi_oversold(series_for_oversold(rsi), 0) is True

    @pytest.mark.parametrize(
        "rsi",
        [
            pytest.param(30.0, id="D3_gleichheit_genuegt_nicht"),
            pytest.param(30.01, id="D4_knapp_darueber"),
            pytest.param(47.0, id="D5_neutral"),
        ],
    )
    def test_nicht_erfuellte_faelle(self, rsi: float) -> None:
        assert rsi_oversold(series_for_oversold(rsi), 0) is False

    def test_fehlender_wert_loest_data_incomplete_aus(self) -> None:
        """D6 -- eine Datenluecke ist kein negatives Signal (Abschnitt 1.5)."""
        with pytest.raises(DataIncompleteError):
            rsi_oversold(series_for_oversold(None), 0)

    def test_index_ausserhalb_der_serie_loest_data_incomplete_aus(self) -> None:
        with pytest.raises(DataIncompleteError):
            rsi_oversold(series_for_oversold(25.0), 1)

    def test_braucht_keine_vorkerze(self) -> None:
        """Das einzige Kriterium ohne Bezug auf die Vorkerze: Es beschreibt
        einen Zustand, keinen Uebergang."""
        assert rsi_oversold(series_for_oversold(25.0), 0) is True


def series_for_downcross(*ema5_values: float | None, ema20: float = 100.0) -> CandleSeries:
    return CandleSeries(
        candles=tuple(make_candle(i) for i in range(len(ema5_values))),
        indicators=tuple(
            IndicatorValues(rsi=None, rsi_ma=None, ema5=ema5, ema20=None if ema5 is None else ema20)
            for ema5 in ema5_values
        ),
    )


_GLEICHSTAND = 100.0
_DARUEBER = 110.0
_DARUNTER = 90.0


class TestSignalENoRecentEmaDowncross:
    """Geprueft wird an ``t = 6``; die Kreuzungspositionen sind dann 2 bis 6."""

    def test_e1_durchgehend_oberhalb(self) -> None:
        series = series_for_downcross(*([_DARUEBER] * 7))
        assert no_recent_ema_downcross(series, 6) is True

    def test_e2_durchgehend_unterhalb(self) -> None:
        """Dauerhaft darunter ist kein *frisches* Abwaertskreuz."""
        series = series_for_downcross(*([_DARUNTER] * 7))
        assert no_recent_ema_downcross(series, 6) is True

    def test_e3_aufwaertskreuz_ist_die_falsche_richtung(self) -> None:
        series = series_for_downcross(
            _DARUNTER, _DARUNTER, _DARUNTER, _DARUNTER, _DARUEBER, _DARUEBER, _DARUEBER
        )
        assert no_recent_ema_downcross(series, 6) is True

    @pytest.mark.parametrize("position", [2, 4, 6], ids=["E4_aelteste", "E5_mitte", "E5_aktuelle"])
    def test_abwaertskreuz_im_pruefbereich_schliesst_aus(self, position: int) -> None:
        werte: list[float | None] = [_DARUEBER] * 7
        for index in range(position, 7):
            werte[index] = _DARUNTER
        series = series_for_downcross(*werte)
        assert no_recent_ema_downcross(series, 6) is False

    def test_e6_abwaertskreuz_eine_position_davor_zaehlt_nicht(self) -> None:
        """Kreuzung an Position 1 -- der Pruefbereich beginnt erst bei 2."""
        werte: list[float | None] = [_DARUEBER, *([_DARUNTER] * 6)]
        series = series_for_downcross(*werte)
        assert no_recent_ema_downcross(series, 6) is True

    def test_e7_gleichstand_ist_keine_unterschreitung(self) -> None:
        series = series_for_downcross(*([_GLEICHSTAND] * 7))
        assert no_recent_ema_downcross(series, 6) is True

    def test_e8_fehlender_wert_meldet_die_luecke_mit_ihrem_index(self) -> None:
        werte: list[float | None] = [_DARUEBER] * 7
        werte[1] = None
        series = series_for_downcross(*werte)
        with pytest.raises(DataIncompleteError) as fehler:
            no_recent_ema_downcross(series, 6)
        assert fehler.value.candle_index == 2, (
            "gemeldet wird die Kreuzungsposition, deren Vorkerze fehlt"
        )

    def test_zu_kurze_serie_loest_data_incomplete_aus(self) -> None:
        series = series_for_downcross(_DARUEBER, _DARUEBER)
        with pytest.raises(DataIncompleteError):
            no_recent_ema_downcross(series, 1)
