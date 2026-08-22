"""Zusammenfuehrung der deterministischen Chartauswertung (Doc 10, Paragraph 6.8)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_trading_analyst.domain.screening import IndicatorValues
from ai_trading_analyst.domain.technical import (
    TECHNICAL_ANALYSIS_VERSION,
    TechnicalStatus,
    TrendDirection,
    average_true_range,
    compute_technical_snapshot,
    true_ranges,
)

from .conftest import series_from_ohlc, series_from_prices, small_params, timestamp_at

EVALUATED_AT = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


def _indicators(*, rsi: float, ema5: float, ema20: float) -> IndicatorValues:
    return IndicatorValues(rsi=rsi, rsi_ma=rsi, ema5=ema5, ema20=ema20)


class TestTrueRange:
    def test_erste_kerze_hat_keine_true_range(self) -> None:
        """Ohne Vorgaenger gibt es keinen Vergleichswert -- der Wert bleibt
        fehlend statt auf die blosse Spanne zurueckzufallen."""
        series = series_from_ohlc([(105, 95, 100), (106, 96, 101)])

        assert true_ranges(series.candles)[0] is None

    def test_kurslueecke_zaehlt_zur_spanne(self) -> None:
        """Springt der Kurs ueber Nacht, ist die Bewegung groesser als die
        Kerzenspanne -- genau dafuer gibt es die True Range."""
        series = series_from_ohlc([(105, 95, 100), (120, 118, 119)])

        assert true_ranges(series.candles)[1] == pytest.approx(20.0)

    def test_atr_liegt_erst_nach_dem_ersten_vollen_fenster_vor(self) -> None:
        series = series_from_ohlc([(105, 95, 100)] * 5)

        werte = average_true_range(series.candles, length=2)

        assert werte[0] is None
        assert werte[1] is None
        assert werte[2] == pytest.approx(10.0)


class TestTrend:
    def test_steigender_ema20_mit_ema5_darueber_ist_aufwaerts(self) -> None:
        series = series_from_prices(
            [100.0] * 6,
            indicators={
                1: _indicators(rsi=50, ema5=100, ema20=100),
                3: _indicators(rsi=55, ema5=112, ema20=110),
            },
        )

        snapshot = compute_technical_snapshot(series, 3, small_params(), EVALUATED_AT)

        assert snapshot.trend is TrendDirection.UP

    def test_fallender_ema20_mit_ema5_darunter_ist_abwaerts(self) -> None:
        series = series_from_prices(
            [100.0] * 6,
            indicators={
                1: _indicators(rsi=50, ema5=100, ema20=100),
                3: _indicators(rsi=45, ema5=88, ema20=90),
            },
        )

        snapshot = compute_technical_snapshot(series, 3, small_params(), EVALUATED_AT)

        assert snapshot.trend is TrendDirection.DOWN

    def test_kaum_bewegter_ema20_ist_seitwaerts(self) -> None:
        series = series_from_prices(
            [100.0] * 6,
            indicators={
                1: _indicators(rsi=50, ema5=100, ema20=100.0),
                3: _indicators(rsi=50, ema5=101, ema20=100.2),
            },
        )

        snapshot = compute_technical_snapshot(series, 3, small_params(), EVALUATED_AT)

        assert snapshot.trend is TrendDirection.SIDEWAYS

    def test_widerspruch_zwischen_steigung_und_lage_ist_seitwaerts(self) -> None:
        """Der EMA20 steigt, der EMA5 ist aber schon darunter gefallen: Die
        Richtung ist offen, und eine Festlegung wuerde dem Bericht eine
        Eindeutigkeit vorspiegeln, die die Kursreihe nicht hergibt."""
        series = series_from_prices(
            [100.0] * 6,
            indicators={
                1: _indicators(rsi=50, ema5=100, ema20=100),
                3: _indicators(rsi=50, ema5=108, ema20=110),
            },
        )

        snapshot = compute_technical_snapshot(series, 3, small_params(), EVALUATED_AT)

        assert snapshot.trend is TrendDirection.SIDEWAYS

    def test_fehlende_ema_werte_ergeben_keinen_trend_statt_seitwaerts(self) -> None:
        """``None`` heisst nicht berechenbar. ``SIDEWAYS`` waere ein Befund,
        den die Daten nicht hergeben."""
        series = series_from_prices([100.0] * 6)

        snapshot = compute_technical_snapshot(series, 3, small_params(), EVALUATED_AT)

        assert snapshot.trend is None
        assert snapshot.status is TechnicalStatus.COMPLETED


class TestSnapshot:
    def test_zu_kurze_serie_ergibt_insufficient_data(self) -> None:
        params = small_params(extremes_lookback=5, history_candles=100)
        series = series_from_prices([100.0, 101.0, 102.0])

        snapshot = compute_technical_snapshot(series, 2, params, EVALUATED_AT)

        assert snapshot.status is TechnicalStatus.INSUFFICIENT_DATA
        assert snapshot.reason == "too_few_candles"

    def test_unvollstaendiges_ergebnis_enthaelt_keine_ersatzwerte(self) -> None:
        params = small_params(extremes_lookback=5, history_candles=100)
        series = series_from_prices([100.0, 101.0, 102.0])

        snapshot = compute_technical_snapshot(series, 2, params, EVALUATED_AT)

        assert snapshot.close is None
        assert snapshot.atr is None
        assert snapshot.trend is None
        assert snapshot.zones == ()

    def test_jedes_ergebnis_traegt_die_verfahrensversion(self) -> None:
        series = series_from_prices([100.0] * 6)

        for index in (2, 5):
            snapshot = compute_technical_snapshot(series, index, small_params(), EVALUATED_AT)
            assert snapshot.analysis_version == TECHNICAL_ANALYSIS_VERSION

    def test_abstaende_zu_den_gleitenden_durchschnitten(self) -> None:
        series = series_from_prices(
            [100.0] * 6, indicators={3: _indicators(rsi=60, ema5=100.0, ema20=80.0)}
        )

        snapshot = compute_technical_snapshot(series, 3, small_params(), EVALUATED_AT)

        assert snapshot.distance_to_ema5_pct == pytest.approx(0.0)
        assert snapshot.distance_to_ema20_pct == pytest.approx(0.25)

    def test_extrempunkte_beziehen_sich_auf_das_konfigurierte_fenster(self) -> None:
        series = series_from_prices([200.0, 50.0, 100.0, 120.0, 90.0, 110.0])

        snapshot = compute_technical_snapshot(
            series, 5, small_params(extremes_lookback=3), EVALUATED_AT
        )

        assert snapshot.recent_high == 120.0
        assert snapshot.recent_high_at == timestamp_at(3)
        assert snapshot.recent_low == 90.0
        assert snapshot.recent_low_at == timestamp_at(4)

    def test_auswertung_bezieht_sich_auf_die_uebergebene_kerze_nicht_auf_die_letzte(self) -> None:
        series = series_from_prices([100.0, 101.0, 102.0, 103.0, 104.0, 999.0])

        snapshot = compute_technical_snapshot(series, 4, small_params(), EVALUATED_AT)

        assert snapshot.close == 104.0
        assert snapshot.candle_timestamp == timestamp_at(4)
        assert snapshot.recent_high == 104.0

    def test_zonensuche_endet_an_der_ausgewerteten_kerze(self) -> None:
        """Kerzen nach der Entscheidungskerze duerfen nicht einfliessen --
        sonst enthielte ein Backtest-Ergebnis Wissen aus der Zukunft."""
        preise = [*[100.0, 110.0, 100.0, 110.0, 100.0], *[300.0, 250.0, 300.0, 250.0, 300.0]]
        series = series_from_prices(preise)

        snapshot = compute_technical_snapshot(series, 4, small_params(), EVALUATED_AT)

        assert all(zone.upper < 200.0 for zone in snapshot.zones)

    def test_zonenfenster_ist_auf_history_candles_begrenzt(self) -> None:
        alt = [100.0, 130.0, 100.0, 130.0, 100.0]
        neu = [100.0, 110.0, 100.0, 110.0, 100.0, 100.0]
        series = series_from_prices([*alt, *neu])

        snapshot = compute_technical_snapshot(
            series, len(alt) + len(neu) - 1, small_params(history_candles=6), EVALUATED_AT
        )

        assert all(round(zone.midpoint) != 130 for zone in snapshot.zones)

    def test_index_ausserhalb_der_serie_ist_ein_programmfehler(self) -> None:
        series = series_from_prices([100.0] * 5)

        with pytest.raises(IndexError):
            compute_technical_snapshot(series, 5, small_params(), EVALUATED_AT)
