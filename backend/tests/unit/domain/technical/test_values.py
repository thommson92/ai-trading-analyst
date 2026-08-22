"""Parametervalidierung und abgeleitete Groessen (ADR 0025)."""

from __future__ import annotations

import pytest

from ai_trading_analyst.domain.technical import TechnicalAnalysisParameters

from .conftest import small_params


class TestParameterValidierung:
    @pytest.mark.parametrize(
        ("feld", "wert"),
        [
            ("pivot_reach", 0),
            ("zone_tolerance_pct", 0.0),
            ("min_touches", 0),
            ("max_zones_per_side", 0),
            ("atr_length", 0),
            ("trend_lookback", 0),
            ("trend_flat_pct", -0.1),
            ("extremes_lookback", 0),
        ],
    )
    def test_unbrauchbare_werte_brechen_sofort_ab(self, feld: str, wert: float) -> None:
        """Ein Fenster der Groesse null faellt sonst erst im Betrieb auf, und
        zwar als leeres Ergebnis statt als Fehler."""
        with pytest.raises(ValueError, match=feld):
            small_params(**{feld: wert})

    def test_staerkeschwellen_muessen_aufsteigend_sein(self) -> None:
        with pytest.raises(ValueError, match="strong_touch_count"):
            small_params(min_touches=2, moderate_touch_count=5, strong_touch_count=3)

    def test_zonenfenster_muss_das_laengste_benoetigte_fenster_abdecken(self) -> None:
        """Sonst waere ein Teil der Auswertung dauerhaft nicht berechenbar,
        ohne dass die Konfiguration darauf hinweist."""
        with pytest.raises(ValueError, match="history_candles"):
            small_params(history_candles=5, extremes_lookback=40)


class TestMindestlaenge:
    def test_mindestlaenge_folgt_dem_laengsten_fenster(self) -> None:
        params = TechnicalAnalysisParameters(
            pivot_reach=3,
            atr_length=14,
            trend_lookback=10,
            extremes_lookback=40,
            history_candles=250,
        )

        assert params.minimum_candles == 40

    def test_voreinstellung_ist_in_sich_stimmig(self) -> None:
        params = TechnicalAnalysisParameters()

        assert params.history_candles >= params.minimum_candles
