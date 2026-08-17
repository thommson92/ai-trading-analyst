"""Tests der Kennzahlenberechnung (Doc 07 "Kennzahlen")."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import ClassVar

import pytest

from ai_trading_analyst.domain.backtesting.metrics import (
    compute_backtest_results,
    compute_horizon_metrics,
    group_by_combination,
)
from ai_trading_analyst.domain.backtesting.values import BacktestConfidence, BacktestParameters
from ai_trading_analyst.domain.screening import CandidateRuleParameters, SignalType

from .conftest import make_series

COMBO = frozenset({SignalType.RSI_CROSS, SignalType.EMA5_EMA20_CROSS})
PERMISSIVE_PARAMS = BacktestParameters(
    horizons=(5,),
    cooldown_candles=5,
    minimum_sample_size=1,
    normal_confidence_sample_size=1,
    history_years=5,
)


class TestHorizontUeberSerienendeHinaus:
    def test_ereignis_ohne_vollstaendigen_pfad_wird_ausgeschlossen(self) -> None:
        series = make_series(10)  # Kerzen 0..9, Horizont 5 ab Index 8 reicht nicht.
        metrics = compute_horizon_metrics(
            series, [8], raw_event_count=1, horizon=5, params=PERMISSIVE_PARAMS
        )
        assert metrics.deduplicated_event_count == 0
        assert metrics.confidence is BacktestConfidence.INSUFFICIENT_DATA
        assert metrics.hit_rate is None
        assert metrics.mean_return is None
        assert metrics.max_loss is None
        assert metrics.drawdown is None
        assert metrics.held_above_entry_rate is None


class TestKennzahlenAnEinemKonstruiertenKursverlauf:
    """Einstieg bei Index 0 (close=100), Horizont 5, Kurse 102/101/103/99/105."""

    SERIES = make_series(6, closes={0: 100.0, 1: 102.0, 2: 101.0, 3: 103.0, 4: 99.0, 5: 105.0})

    def test_rueckgabe_ist_der_schlusskurs_am_horizont_relativ_zum_einstieg(self) -> None:
        metrics = compute_horizon_metrics(
            self.SERIES, [0], raw_event_count=1, horizon=5, params=PERMISSIVE_PARAMS
        )
        assert metrics.mean_return is not None
        assert metrics.mean_return == (105.0 - 100.0) / 100.0

    def test_trefferquote_ist_positiv_wenn_der_horizont_ueber_dem_einstieg_liegt(self) -> None:
        metrics = compute_horizon_metrics(
            self.SERIES, [0], raw_event_count=1, horizon=5, params=PERMISSIVE_PARAMS
        )
        assert metrics.hit_rate == 1.0

    def test_maximaler_verlust_ist_relativ_zum_einstieg(self) -> None:
        """99 ist der schlechteste Schlusskurs nach Einstieg: (99-100)/100."""
        metrics = compute_horizon_metrics(
            self.SERIES, [0], raw_event_count=1, horizon=5, params=PERMISSIVE_PARAMS
        )
        assert metrics.max_loss is not None
        assert metrics.max_loss == (99.0 - 100.0) / 100.0

    def test_drawdown_ist_relativ_zum_laufenden_hoechststand(self) -> None:
        """Hoechststand vor dem Einbruch ist 103 (Index 3), Einbruch auf 99
        (Index 4): (103-99)/103 -- nicht (100-99)/100 wie beim maximalen
        Verlust."""
        metrics = compute_horizon_metrics(
            self.SERIES, [0], raw_event_count=1, horizon=5, params=PERMISSIVE_PARAMS
        )
        assert metrics.drawdown is not None
        assert metrics.drawdown == (103.0 - 99.0) / 103.0

    def test_dauerhaftes_halten_ist_falsch_wenn_eine_kerze_unter_den_einstieg_faellt(self) -> None:
        metrics = compute_horizon_metrics(
            self.SERIES, [0], raw_event_count=1, horizon=5, params=PERMISSIVE_PARAMS
        )
        assert metrics.held_above_entry_rate == 0.0

    def test_dauerhaftes_halten_ist_wahr_wenn_jede_kerze_ueber_dem_einstieg_bleibt(self) -> None:
        series = make_series(6, closes={0: 100.0, 1: 101.0, 2: 102.0, 3: 103.0, 4: 104.0, 5: 105.0})
        metrics = compute_horizon_metrics(
            series, [0], raw_event_count=1, horizon=5, params=PERMISSIVE_PARAMS
        )
        assert metrics.held_above_entry_rate == 1.0


class TestKonfidenzstufen:
    SERIES: ClassVar = make_series(20, closes={i: 100.0 + i for i in range(20)})
    INDICES: ClassVar = list(range(10))  # 10 Ereignisse

    def test_unterhalb_des_mindestwerts_ist_insufficient_data_ohne_kennzahlen(self) -> None:
        params = BacktestParameters(
            horizons=(1,),
            cooldown_candles=5,
            minimum_sample_size=11,
            normal_confidence_sample_size=20,
            history_years=5,
        )
        metrics = compute_horizon_metrics(
            self.SERIES, self.INDICES, raw_event_count=10, horizon=1, params=params
        )
        assert metrics.confidence is BacktestConfidence.INSUFFICIENT_DATA
        assert metrics.mean_return is None

    def test_zwischen_mindestwert_und_normalwert_ist_low_sample_mit_kennzahlen(self) -> None:
        params = BacktestParameters(
            horizons=(1,),
            cooldown_candles=5,
            minimum_sample_size=5,
            normal_confidence_sample_size=20,
            history_years=5,
        )
        metrics = compute_horizon_metrics(
            self.SERIES, self.INDICES, raw_event_count=10, horizon=1, params=params
        )
        assert metrics.confidence is BacktestConfidence.LOW_SAMPLE
        assert metrics.mean_return is not None

    def test_ab_dem_normalwert_ist_normal(self) -> None:
        params = BacktestParameters(
            horizons=(1,),
            cooldown_candles=5,
            minimum_sample_size=5,
            normal_confidence_sample_size=10,
            history_years=5,
        )
        metrics = compute_horizon_metrics(
            self.SERIES, self.INDICES, raw_event_count=10, horizon=1, params=params
        )
        assert metrics.confidence is BacktestConfidence.NORMAL


class TestGruppierung:
    def test_gruppiert_nach_exakter_kombination(self) -> None:
        rsi_only = frozenset({SignalType.RSI_CROSS})
        decisions = [(1, COMBO), (2, rsi_only), (10, COMBO)]
        grouped = group_by_combination(decisions)
        assert grouped[COMBO] == (1, 10)
        assert grouped[rsi_only] == (2,)


class TestVollstaendigeBerechnung:
    def test_alle_vier_kombinationen_sind_immer_vertreten(self) -> None:
        series = make_series(20)  # feuert nie
        params = BacktestParameters(
            horizons=(5, 10),
            cooldown_candles=5,
            minimum_sample_size=10,
            normal_confidence_sample_size=30,
            history_years=5,
        )
        candidate_params = CandidateRuleParameters(
            required_signal_count=2, signal_lookback_previous_candles=5, warmup_candles=10
        )
        results = compute_backtest_results(
            series,
            stock_id=uuid.uuid4(),
            candidate_params=candidate_params,
            backtest_params=params,
            signal_rule_version="test-version",
            evaluated_at=datetime.now(UTC),
        )
        assert len(results) == 4
        assert all(
            horizon.deduplicated_event_count == 0
            and horizon.confidence is BacktestConfidence.INSUFFICIENT_DATA
            for result in results
            for horizon in result.horizons
        )

    def test_anzahl_der_kombinationen_folgt_required_signal_count(self) -> None:
        """Bei required_signal_count=3 qualifiziert nur noch die eine
        Dreier-Kombination -- nicht mehr die drei Zweier-Kombinationen aus
        dem Standardfall (G1-Pruefvorlage Abschnitt 4.3)."""
        series = make_series(20)
        params = BacktestParameters(
            horizons=(5,),
            cooldown_candles=5,
            minimum_sample_size=10,
            normal_confidence_sample_size=30,
            history_years=5,
        )
        candidate_params = CandidateRuleParameters(
            required_signal_count=3, signal_lookback_previous_candles=5, warmup_candles=10
        )
        results = compute_backtest_results(
            series,
            stock_id=uuid.uuid4(),
            candidate_params=candidate_params,
            backtest_params=params,
            signal_rule_version="test-version",
            evaluated_at=datetime.now(UTC),
        )
        assert len(results) == 1
        assert results[0].signal_types == frozenset(SignalType)


class TestHistorienfenster:
    CANDIDATE_PARAMS = CandidateRuleParameters(
        required_signal_count=2, signal_lookback_previous_candles=5, warmup_candles=10
    )

    def test_kerzen_vor_dem_cutoff_werden_nicht_repliziert(self) -> None:
        series = make_series(40)
        cutoff_reference = series.candle(20).timestamp
        evaluated_at = cutoff_reference + timedelta(days=365)
        params = BacktestParameters(
            horizons=(5,),
            cooldown_candles=5,
            minimum_sample_size=10,
            normal_confidence_sample_size=30,
            history_years=1,
        )
        results = compute_backtest_results(
            series,
            stock_id=uuid.uuid4(),
            candidate_params=self.CANDIDATE_PARAMS,
            backtest_params=params,
            signal_rule_version="test-version",
            evaluated_at=evaluated_at,
        )
        assert results[0].history_start == cutoff_reference
        assert results[0].history_end == series.candle(39).timestamp

    def test_eine_serie_vollstaendig_ausserhalb_des_fensters_wirft_einen_fehler(self) -> None:
        series = make_series(10)
        evaluated_at = series.candle(0).timestamp + timedelta(days=3650)
        params = BacktestParameters(
            horizons=(5,),
            cooldown_candles=5,
            minimum_sample_size=10,
            normal_confidence_sample_size=30,
            history_years=1,
        )
        with pytest.raises(ValueError, match="innerhalb der letzten"):
            compute_backtest_results(
                series,
                stock_id=uuid.uuid4(),
                candidate_params=self.CANDIDATE_PARAMS,
                backtest_params=params,
                signal_rule_version="test-version",
                evaluated_at=evaluated_at,
            )
