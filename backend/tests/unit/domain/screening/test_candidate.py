"""Tests der 2-aus-3-Kandidatenregel und des Sechs-Kerzen-Fensters.

Fachliche Grundlage: G1-Pruefvorlage Abschnitt 3 und 1.5. Baseline-Kerzen
feuern nie (siehe conftest); jeder Test ueberschreibt gezielt einzelne Kerzen,
um genau ein Verhalten zu isolieren.
"""

from __future__ import annotations

import pytest

import ai_trading_analyst.domain.screening.candidate as candidate_module
from ai_trading_analyst.domain.screening import (
    CandidateRuleParameters,
    DataIncompleteError,
    IndicatorValues,
    ScreeningStatus,
    SignalType,
    evaluate_candidate,
)
from tests.unit.domain.screening.conftest import (
    build_series,
    incomplete_indicators,
    price_ema20_breakout_candle_at,
    rsi_cross_fires,
)

SERIES_LENGTH = 30
DECISION_INDEX = 20
PARAMS = CandidateRuleParameters(
    required_signal_count=2, signal_lookback_previous_candles=5, warmup_candles=10
)


class TestFensterGrenzen:
    def test_signal_auf_t_minus_5_zaehlt(self) -> None:
        """t-5 ist die aelteste noch zum Fenster gehoerende Kerze (Abschnitt 3.2)."""
        series = build_series(SERIES_LENGTH, indicator_overrides={15: rsi_cross_fires()})
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert SignalType.RSI_CROSS in result.fired_signal_types

    def test_signal_auf_t_minus_6_zaehlt_nicht(self) -> None:
        """t-6 liegt bereits ausserhalb des Sechs-Kerzen-Fensters."""
        series = build_series(SERIES_LENGTH, indicator_overrides={14: rsi_cross_fires()})
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert SignalType.RSI_CROSS not in result.fired_signal_types
        assert result.status != ScreeningStatus.UNKNOWN_DATA_INCOMPLETE

    def test_signal_auf_t_plus_1_wird_niemals_einbezogen(self) -> None:
        series = build_series(
            SERIES_LENGTH, indicator_overrides={DECISION_INDEX + 1: rsi_cross_fires()}
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert SignalType.RSI_CROSS not in result.fired_signal_types
        assert result.status != ScreeningStatus.UNKNOWN_DATA_INCOMPLETE


class TestZaehlungDerSignaltypen:
    def test_zwei_unterschiedliche_signale_auf_derselben_kerze(self) -> None:
        series = build_series(
            SERIES_LENGTH,
            indicator_overrides={
                DECISION_INDEX: IndicatorValues(rsi=60.0, rsi_ma=50.0, ema5=110.0, ema20=100.0)
            },
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.fired_signal_types == frozenset(
            {SignalType.RSI_CROSS, SignalType.EMA5_EMA20_CROSS}
        )
        assert result.status == ScreeningStatus.CANDIDATE

    def test_zwei_unterschiedliche_signale_auf_verschiedenen_kerzen(self) -> None:
        """Beispiel aus der G1-Pruefvorlage, Abschnitt 3.5:
        RSI_CROSS auf t-4, PRICE_EMA20_BREAKOUT auf t-1."""
        series = build_series(
            SERIES_LENGTH,
            indicator_overrides={DECISION_INDEX - 4: rsi_cross_fires()},
            candle_overrides={
                DECISION_INDEX - 1: price_ema20_breakout_candle_at(DECISION_INDEX - 1)
            },
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.status == ScreeningStatus.CANDIDATE
        assert result.fired_signal_types == frozenset(
            {SignalType.RSI_CROSS, SignalType.PRICE_EMA20_BREAKOUT}
        )
        positions = {event.signal_type: event.candle_index for event in result.signal_events}
        assert positions[SignalType.RSI_CROSS] == DECISION_INDEX - 4
        assert positions[SignalType.PRICE_EMA20_BREAKOUT] == DECISION_INDEX - 1

    def test_nur_ein_signaltyp_fuehrt_zu_not_candidate(self) -> None:
        series = build_series(
            SERIES_LENGTH, indicator_overrides={DECISION_INDEX: rsi_cross_fires()}
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.fired_signal_types == frozenset({SignalType.RSI_CROSS})
        assert result.status == ScreeningStatus.NOT_CANDIDATE

    def test_dreifaches_auftreten_desselben_signaltyps_zaehlt_nur_einmal(self) -> None:
        series = build_series(
            SERIES_LENGTH,
            indicator_overrides={
                DECISION_INDEX - 5: rsi_cross_fires(),
                DECISION_INDEX - 3: rsi_cross_fires(),
                DECISION_INDEX - 1: rsi_cross_fires(),
            },
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.fired_signal_types == frozenset({SignalType.RSI_CROSS})
        assert result.status == ScreeningStatus.NOT_CANDIDATE
        assert len(result.signal_events) == 1
        assert result.signal_events[0].candle_index == DECISION_INDEX - 5


class TestFehlendeDaten:
    @pytest.mark.parametrize("missing_index", list(range(14, 21)))
    def test_fehlende_daten_an_jeder_relevanten_fensterposition(self, missing_index: int) -> None:
        """t-6 bis t: jede davon wird von mindestens einer Signalformel als
        Vor- oder aktuelle Kerze benoetigt (Abschnitt 1.5)."""
        series = build_series(
            SERIES_LENGTH, indicator_overrides={missing_index: incomplete_indicators()}
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.status == ScreeningStatus.UNKNOWN_DATA_INCOMPLETE
        assert result.affected_index == missing_index

    def test_fehlende_daten_ausserhalb_des_relevanten_bereichs_bleiben_ohne_wirkung(self) -> None:
        series = build_series(SERIES_LENGTH, indicator_overrides={13: incomplete_indicators()})
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.status != ScreeningStatus.UNKNOWN_DATA_INCOMPLETE

    def test_fehlende_daten_werden_nie_als_negatives_signal_gewertet(self) -> None:
        """Explizite Regel aus Abschnitt 1.5: keine stillschweigende Einstufung
        als Nicht-Kandidat bei Datenluecke."""
        series = build_series(
            SERIES_LENGTH, indicator_overrides={DECISION_INDEX: incomplete_indicators()}
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.status not in (ScreeningStatus.NOT_CANDIDATE, ScreeningStatus.CANDIDATE)


class TestVerteidigungGegenUnerwarteteDataIncomplete:
    def test_evaluate_candidate_stuerzt_nicht_ab_wenn_signalfunktion_data_incomplete_meldet(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Zweite Verteidigungslinie (Abschnitt 1.5): meldet eine Signalfunktion
        trotz vorgelagerter Vollstaendigkeitspruefung eine Datenluecke, bricht
        evaluate_candidate nicht mit einer unbehandelten Exception ab, sondern
        liefert UNKNOWN_DATA_INCOMPLETE."""

        def _always_incomplete(series: object, t: int) -> bool:
            raise DataIncompleteError(candle_index=t, required=("TEST",))

        monkeypatch.setattr(
            candidate_module, "_SIGNAL_FUNCTIONS", {SignalType.RSI_CROSS: _always_incomplete}
        )
        series = build_series(SERIES_LENGTH)
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.status == ScreeningStatus.UNKNOWN_DATA_INCOMPLETE


class TestWarmup:
    def test_kerze_vor_warmup_grenze_ist_unbestimmt(self) -> None:
        series = build_series(PARAMS.warmup_candles)
        result = evaluate_candidate(series, PARAMS.warmup_candles - 1, PARAMS)
        assert result.status == ScreeningStatus.UNKNOWN_DATA_INCOMPLETE
        assert result.reason == "warmup_insufficient"

    def test_erste_auswertbare_kerze_liegt_exakt_auf_der_warmup_grenze(self) -> None:
        series = build_series(SERIES_LENGTH)
        result = evaluate_candidate(series, PARAMS.warmup_candles, PARAMS)
        assert result.reason != "warmup_insufficient"
