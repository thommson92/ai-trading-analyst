"""Tests des historischen Replays (G1-Pruefvorlage Abschnitt 4.1)."""

from __future__ import annotations

from ai_trading_analyst.domain.backtesting.replay import (
    deduplicate_with_cooldown,
    find_historical_decisions,
)
from ai_trading_analyst.domain.screening import (
    CandidateRuleParameters,
    IndicatorValues,
    SignalType,
)

from .conftest import BASELINE_EMA, RSI_AND_EMA_CROSS_FIRE, make_series

PARAMS = CandidateRuleParameters(
    required_crossing_signals=2, signal_lookback_previous_candles=5, warmup_candles=10
)
EXPECTED_COMBINATION = frozenset(
    {
        SignalType.RSI_CROSS,
        SignalType.EMA5_EMA20_CROSS,
        # Die ruhige Baseline enthaelt kein Abwaertskreuz, also ist das
        # Ausschlusskriterium erfuellt -- es steht in jeder Kombination mit.
        SignalType.NO_RECENT_EMA_DOWNCROSS,
    }
)


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
        Index 34 (29 = 34 - 5) und zaehlt dort mit.

        Allein traegt es die Qualifikation seit ADR 0057 aber nicht mehr: Die
        Torbedingung der Frische verlangt ein Kaufsignal auf ``t`` oder
        ``t-1``. Erst ein frisches zweites Signal auf 34 macht den
        Entscheidungspunkt -- und dass daraus zwei Kaufsignale werden, ist
        genau der Beitrag des alten.
        """
        nur_alt = make_series(40, indicator_overrides={29: RSI_AND_EMA_CROSS_FIRE})
        assert 34 not in {index for index, _ in find_historical_decisions(nur_alt, PARAMS)}

        mit_frischem = make_series(
            40,
            indicator_overrides={
                29: RSI_AND_EMA_CROSS_FIRE,
                34: IndicatorValues(rsi=50.0, rsi_ma=50.0, ema5=110.0, ema20=BASELINE_EMA),
            },
        )
        entscheidungen = dict(find_historical_decisions(mit_frischem, PARAMS))
        assert 34 in entscheidungen
        assert SignalType.RSI_CROSS in entscheidungen[34]

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
