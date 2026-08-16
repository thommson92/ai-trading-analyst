"""Tests des historischen Replays (G1-Pruefvorlage Abschnitt 4.1)."""

from __future__ import annotations

from ai_trading_analyst.domain.backtesting.replay import (
    deduplicate_with_cooldown,
    find_historical_decisions,
)
from ai_trading_analyst.domain.screening import CandidateRuleParameters, SignalType

from .conftest import RSI_AND_EMA_CROSS_FIRE, make_series

PARAMS = CandidateRuleParameters(
    required_signal_count=2, signal_lookback_previous_candles=5, warmup_candles=10
)
EXPECTED_COMBINATION = frozenset({SignalType.RSI_CROSS, SignalType.EMA5_EMA20_CROSS})


class TestEntscheidungszeitpunkte:
    def test_nur_die_erste_tageskerze_ist_ein_entscheidungspunkt(self) -> None:
        # Index 30 ist gerade (erste Tageskerze), 31 ungerade (zweite).
        series = make_series(
            40,
            indicator_overrides={30: RSI_AND_EMA_CROSS_FIRE, 31: RSI_AND_EMA_CROSS_FIRE},
        )
        decisions = find_historical_decisions(series, PARAMS)
        indices = {index for index, _ in decisions}
        assert 30 in indices
        assert 31 not in indices

    def test_ein_signal_auf_der_zweiten_tageskerze_wirkt_in_ein_spaeteres_fenster(self) -> None:
        """Index 29 (zweite Tageskerze) liegt im Sechs-Kerzen-Fenster von
        Index 34 (29 = 34 - 5) -- die Qualifikation dort zaehlt trotzdem."""
        series = make_series(40, indicator_overrides={29: RSI_AND_EMA_CROSS_FIRE})
        decisions = find_historical_decisions(series, PARAMS)
        indices = {index for index, _ in decisions}
        assert 34 in indices

    def test_gefundene_kombination_entspricht_den_gefeuerten_signaltypen(self) -> None:
        series = make_series(40, indicator_overrides={30: RSI_AND_EMA_CROSS_FIRE})
        decisions = find_historical_decisions(series, PARAMS)
        by_index = dict(decisions)
        assert by_index[30] == EXPECTED_COMBINATION

    def test_keine_qualifikation_ergibt_keine_entscheidungen(self) -> None:
        series = make_series(40)
        assert find_historical_decisions(series, PARAMS) == ()


class TestCooldownDeduplizierung:
    def test_ereignisse_innerhalb_der_cooldown_frist_werden_verworfen(self) -> None:
        decisions = [
            (10, EXPECTED_COMBINATION),
            (12, EXPECTED_COMBINATION),
            (20, EXPECTED_COMBINATION),
            (21, EXPECTED_COMBINATION),
            (30, EXPECTED_COMBINATION),
        ]
        result = deduplicate_with_cooldown(decisions, cooldown_candles=5)
        assert [index for index, _ in result] == [10, 20, 30]

    def test_genau_die_cooldown_distanz_wird_noch_verworfen(self) -> None:
        decisions = [(10, EXPECTED_COMBINATION), (15, EXPECTED_COMBINATION)]
        result = deduplicate_with_cooldown(decisions, cooldown_candles=5)
        assert [index for index, _ in result] == [10]

    def test_eine_kerze_ueber_der_cooldown_distanz_wird_behalten(self) -> None:
        decisions = [(10, EXPECTED_COMBINATION), (16, EXPECTED_COMBINATION)]
        result = deduplicate_with_cooldown(decisions, cooldown_candles=5)
        assert [index for index, _ in result] == [10, 16]

    def test_leere_liste_bleibt_leer(self) -> None:
        assert deduplicate_with_cooldown([], cooldown_candles=5) == ()
