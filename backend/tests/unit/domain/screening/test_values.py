"""Tests der Wertobjekte selbst -- unabhaengig von den Signalformeln."""

from __future__ import annotations

import pytest

from ai_trading_analyst.domain.screening import CandleSeries, IndicatorValues
from tests.unit.domain.screening.conftest import make_candle


def test_candle_series_erzwingt_gleiche_laenge() -> None:
    with pytest.raises(ValueError, match="gleich lang"):
        CandleSeries(
            candles=(make_candle(0), make_candle(1)),
            indicators=(IndicatorValues(rsi=None, rsi_ma=None, ema5=None, ema20=None),),
        )


def test_candle_series_len_entspricht_kerzenanzahl() -> None:
    series = CandleSeries(
        candles=(make_candle(0), make_candle(1), make_candle(2)),
        indicators=tuple(
            IndicatorValues(rsi=None, rsi_ma=None, ema5=None, ema20=None) for _ in range(3)
        ),
    )
    assert len(series) == 3
