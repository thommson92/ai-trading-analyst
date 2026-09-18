"""Tests der Kennzahlenberechnung (Doc 07 "Kennzahlen")."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import ClassVar

import pytest

from ai_trading_analyst.domain.backtesting.metrics import (
    compute_backtest,
    compute_backtest_results,
    compute_episode_outcome,
    compute_horizon_metrics,
    group_by_combination,
)
from ai_trading_analyst.domain.backtesting.replay import HistoricalDecision
from ai_trading_analyst.domain.backtesting.values import BacktestConfidence, BacktestParameters
from ai_trading_analyst.domain.screening import (
    CONFIRMATION_SIGNALS,
    CROSSING_SIGNALS,
    CandidateRuleParameters,
    CandleSeries,
    SignalType,
)

from .conftest import RSI_AND_EMA_CROSS_FIRE, make_series

COMBO = frozenset({SignalType.RSI_CROSS, SignalType.EMA5_EMA20_CROSS})
PERMISSIVE_PARAMS = BacktestParameters(
    horizons=(5,),
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
        decisions = [
            HistoricalDecision(index=1, combination=COMBO, signal_firings=frozenset()),
            HistoricalDecision(index=2, combination=rsi_only, signal_firings=frozenset()),
            HistoricalDecision(index=10, combination=COMBO, signal_firings=frozenset()),
        ]
        grouped = group_by_combination(decisions)
        assert grouped[COMBO] == (1, 10)
        assert grouped[rsi_only] == (2,)


class TestVollstaendigeBerechnung:
    def test_alle_qualifizierenden_kombinationen_sind_immer_vertreten(self) -> None:
        series = make_series(20)  # feuert nie
        params = BacktestParameters(
            horizons=(5, 10),
            minimum_sample_size=10,
            normal_confidence_sample_size=30,
            history_years=5,
        )
        candidate_params = CandidateRuleParameters(
            required_crossing_signals=2, signal_lookback_previous_candles=5, warmup_candles=10
        )
        results = compute_backtest_results(
            series,
            stock_id=uuid.uuid4(),
            candidate_params=candidate_params,
            backtest_params=params,
            signal_rule_version="test-version",
            evaluated_at=datetime.now(UTC),
        )
        # Vier Kaufsignal-Kombinationen (drei Paare und das Tripel) mal drei
        # Zusatz-Kombinationen (D, E, beide).
        assert len(results) == 12
        assert all(
            horizon.deduplicated_event_count == 0
            and horizon.confidence is BacktestConfidence.INSUFFICIENT_DATA
            for result in results
            for horizon in result.horizons
        )

    def test_anzahl_der_kombinationen_folgt_der_geforderten_signalzahl(self) -> None:
        """Werden alle drei Kaufsignale verlangt, bleibt nur noch deren
        eine Kombination -- mal drei Zusatz-Kombinationen (G1-Pruefvorlage
        Abschnitt 4.3). Die Menge folgt der Schwelle, sie wird nirgends
        gepflegt."""
        series = make_series(20)
        params = BacktestParameters(
            horizons=(5,),
            minimum_sample_size=10,
            normal_confidence_sample_size=30,
            history_years=5,
        )
        candidate_params = CandidateRuleParameters(
            required_crossing_signals=3, signal_lookback_previous_candles=5, warmup_candles=10
        )
        results = compute_backtest_results(
            series,
            stock_id=uuid.uuid4(),
            candidate_params=candidate_params,
            backtest_params=params,
            signal_rule_version="test-version",
            evaluated_at=datetime.now(UTC),
        )
        assert len(results) == 3
        assert frozenset(SignalType) in {result.signal_types for result in results}
        assert all(
            result.signal_types >= CROSSING_SIGNALS
            and bool(result.signal_types & CONFIRMATION_SIGNALS)
            for result in results
        )


class TestHistorienfenster:
    CANDIDATE_PARAMS = CandidateRuleParameters(
        required_crossing_signals=2, signal_lookback_previous_candles=5, warmup_candles=10
    )

    def test_kerzen_vor_dem_cutoff_werden_nicht_repliziert(self) -> None:
        series = make_series(40)
        cutoff_reference = series.candle(20).timestamp
        evaluated_at = cutoff_reference + timedelta(days=365)
        params = BacktestParameters(
            horizons=(5,),
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


class TestEpisodenergebnis:
    """Die eine Rechnung hinter Aggregat und Einzelwert (ADR 0061)."""

    SERIES = make_series(6, closes={0: 100.0, 1: 102.0, 2: 101.0, 3: 103.0, 4: 99.0, 5: 105.0})

    def test_einzelwert_und_aggregat_sagen_dasselbe(self) -> None:
        einzeln = compute_episode_outcome(self.SERIES, 0, 5)
        aggregat = compute_horizon_metrics(
            self.SERIES, [0], raw_event_count=1, horizon=5, params=PERMISSIVE_PARAMS
        )
        assert einzeln.return_pct == aggregat.mean_return == pytest.approx(0.05)
        assert einzeln.max_loss == aggregat.max_loss == pytest.approx(-0.01)
        assert einzeln.drawdown == aggregat.drawdown == pytest.approx((103.0 - 99.0) / 103.0)
        assert einzeln.held_above_entry is False
        assert aggregat.held_above_entry_rate == 0.0

    def test_ohne_vollstaendigen_pfad_bleibt_alles_leer_aber_der_horizont_steht(self) -> None:
        einzeln = compute_episode_outcome(make_series(10), 8, 5)
        assert einzeln.horizon == 5
        assert einzeln.return_pct is None
        assert einzeln.max_loss is None
        assert einzeln.drawdown is None
        assert einzeln.held_above_entry is None


class TestEpisodenAusDerVollstaendigenRechnung:
    CANDIDATE_PARAMS = CandidateRuleParameters(
        required_crossing_signals=2, signal_lookback_previous_candles=5, warmup_candles=10
    )
    PARAMS = BacktestParameters(
        horizons=(5, 10, 20),
        minimum_sample_size=1,
        normal_confidence_sample_size=1,
        history_years=5,
    )

    def _serie_mit_einem_ereignis(self) -> tuple[CandleSeries, int]:
        # Ein Kreuz an Kerze 12 -- einer ersten Tageskerze nach dem Warmup.
        # E (kein Abwaertskreuz) gilt an jeder Entscheidungskerze von selbst.
        series = make_series(
            40, indicator_overrides={12: RSI_AND_EMA_CROSS_FIRE}, closes={12: 101.0}
        )
        return series, 12

    def test_die_episode_traegt_zeitstempel_und_kurs_der_einstiegskerze(self) -> None:
        series, index = self._serie_mit_einem_ereignis()
        rechnung = compute_backtest(
            series,
            stock_id=uuid.uuid4(),
            candidate_params=self.CANDIDATE_PARAMS,
            backtest_params=self.PARAMS,
            signal_rule_version="test-version",
            evaluated_at=datetime.now(UTC),
        )
        assert len(rechnung.episodes) >= 1
        erste = rechnung.episodes[0]
        kerze = series.candle(index)
        assert erste.entry_at == kerze.timestamp
        assert erste.entry_close == kerze.close
        assert erste.trigger_count >= 1
        assert erste.last_trigger_at >= erste.entry_at
        assert [h.horizon for h in erste.horizons] == [5, 10, 20]

    def test_episoden_je_kombination_decken_die_stichprobe_des_kuerzesten_horizonts(self) -> None:
        """Die Aggregate zaehlen genau die Episoden, die hier stehen. Beim
        kuerzesten Horizont reicht die Historie fuer jedes Ereignis, das
        ueberhaupt bis dorthin reicht -- also muss die Zahl uebereinstimmen."""
        series, _ = self._serie_mit_einem_ereignis()
        rechnung = compute_backtest(
            series,
            stock_id=uuid.uuid4(),
            candidate_params=self.CANDIDATE_PARAMS,
            backtest_params=self.PARAMS,
            signal_rule_version="test-version",
            evaluated_at=datetime.now(UTC),
        )
        for ergebnis in rechnung.results:
            kuerzester = min(ergebnis.horizons, key=lambda h: h.horizon)
            vollstaendige = [
                e
                for e in rechnung.episodes
                if e.signal_types == ergebnis.signal_types
                and e.horizons[0].return_pct is not None
            ]
            assert len(vollstaendige) == kuerzester.deduplicated_event_count
