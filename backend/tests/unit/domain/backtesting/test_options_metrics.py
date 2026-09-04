"""Tests der Kennzahlen simulierter Put-Verkaeufe (ADR 0058, Stufe 1)."""

from __future__ import annotations

from datetime import date

import pytest

from ai_trading_analyst.domain.backtesting import BacktestConfidence, BacktestParameters
from ai_trading_analyst.domain.backtesting.options_metrics import (
    SIGNAL_BUCHSTABEN,
    compute_options_backtest_results,
    kombinationskuerzel,
    summarize_variant,
)
from ai_trading_analyst.domain.backtesting.options_trade import (
    OptionsBacktestParameters,
    OptionTrade,
    TradeOutcome,
)
from ai_trading_analyst.domain.backtesting.values import qualifying_combinations
from ai_trading_analyst.domain.screening import SignalType

OPTIONEN = OptionsBacktestParameters()
BACKTEST = BacktestParameters(
    horizons=(5, 10, 20),
    minimum_sample_size=10,
    normal_confidence_sample_size=30,
    history_years=5,
)
KOMBINATION = frozenset(
    {
        SignalType.RSI_CROSS,
        SignalType.PRICE_EMA20_BREAKOUT,
        SignalType.NO_RECENT_EMA_DOWNCROSS,
    }
)


def trade(
    *,
    gehalten: float,
    gemanagt: float,
    kapital: float = 10_000.0,
    ergebnis: TradeOutcome = TradeOutcome.EXPIRED_WORTHLESS,
    gemanagtes_ergebnis: TradeOutcome = TradeOutcome.TAKE_PROFIT,
) -> OptionTrade:
    return OptionTrade(
        entry_index=100,
        entry_date=date(2026, 3, 6),
        expiration=date(2026, 4, 17),
        days_to_expiration=42,
        strike=kapital / 100.0,
        underlying_at_entry=110.0,
        volatility=0.28,
        premium=2.0,
        delta=-0.25,
        capital_at_risk=kapital,
        held_outcome=ergebnis,
        held_profit=gehalten,
        managed_outcome=gemanagtes_ergebnis,
        managed_profit=gemanagt,
        managed_exit_index=120,
        underlying_at_expiration=112.0,
    )


class TestKriterienbuchstaben:
    def test_jeder_signaltyp_hat_einen_buchstaben(self) -> None:
        """Die Zusicherung, die der Docstring gibt: Ein neuer Signaltyp bekaeme
        sonst stillschweigend keinen Buchstaben und verschwaende aus jeder
        Kombination der Tabelle."""
        assert set(SIGNAL_BUCHSTABEN.values()) == set(SignalType)

    def test_die_buchstaben_stehen_in_der_reihenfolge_der_pruefvorlage(self) -> None:
        assert list(SIGNAL_BUCHSTABEN) == ["A", "B", "C", "D", "E"]
        assert SIGNAL_BUCHSTABEN["A"] is SignalType.RSI_CROSS
        assert SIGNAL_BUCHSTABEN["E"] is SignalType.NO_RECENT_EMA_DOWNCROSS

    def test_eine_kombination_wird_zu_ihren_buchstaben(self) -> None:
        assert kombinationskuerzel(KOMBINATION) == "ABE"
        assert kombinationskuerzel(frozenset(SignalType)) == "ABCDE"
        assert kombinationskuerzel(frozenset()) == ""

    def test_verschiedene_kombinationen_ergeben_verschiedene_kuerzel(self) -> None:
        """Der Grund fuer die Buchstaben: Ausgeschrieben muessten die Namen in
        der Tabelle abgeschnitten werden, und zwei Kombinationen saehen dann
        gleich aus."""
        kuerzel = [kombinationskuerzel(k) for k in qualifying_combinations(2)]

        assert len(set(kuerzel)) == len(kuerzel)


class TestVariantenkennzahlen:
    def test_die_kennzahlen_stehen_auf_den_einzelergebnissen(self) -> None:
        kennzahlen = summarize_variant(
            [100.0, -50.0, 200.0, 25.0],
            [10_000.0] * 4,
            [TradeOutcome.EXPIRED_WORTHLESS] * 3 + [TradeOutcome.ASSIGNED],
        )

        assert kennzahlen is not None
        assert kennzahlen.trades == 4
        assert kennzahlen.win_rate == pytest.approx(0.75)
        assert kennzahlen.mean_profit == pytest.approx(68.75)
        assert kennzahlen.median_profit == pytest.approx(62.5)
        assert kennzahlen.total_profit == pytest.approx(275.0)
        assert kennzahlen.worst_profit == pytest.approx(-50.0)
        assert kennzahlen.mean_return_on_capital == pytest.approx(0.006875)
        assert kennzahlen.expired_worthless == 3
        assert kennzahlen.assigned == 1

    def test_der_schlechteste_trade_bleibt_sichtbar(self) -> None:
        """Die Zahl, die eine gute Quote nicht zeigt: neun kleine Gewinne und
        ein grosser Verlust."""
        kennzahlen = summarize_variant(
            [50.0] * 9 + [-5_000.0], [10_000.0] * 10, [TradeOutcome.EXPIRED_WORTHLESS] * 10
        )

        assert kennzahlen is not None
        assert kennzahlen.win_rate == pytest.approx(0.9)
        assert kennzahlen.worst_profit == pytest.approx(-5_000.0)
        assert kennzahlen.mean_profit is not None
        assert kennzahlen.mean_profit < 0.0

    def test_ohne_trades_gibt_es_keine_kennzahlen(self) -> None:
        assert summarize_variant([], [], []) is None


class TestErgebnisJeKombination:
    def test_beide_varianten_bleiben_getrennt(self) -> None:
        """Sie zu einer Zahl zu verrechnen waere derselbe Fehler wie eine
        gemeinsame 'Erfolgsquote' (CLAUDE.md) -- der Unterschied zwischen
        ihnen ist die Aussage."""
        trades = [trade(gehalten=200.0, gemanagt=60.0) for _ in range(12)]

        (ergebnis,) = [
            e
            for e in compute_options_backtest_results(
                {KOMBINATION: trades},
                options_params=OPTIONEN,
                backtest_params=BACKTEST,
                required_crossing_signals=2,
            )
            if e.signal_types == KOMBINATION
        ]

        assert ergebnis.held is not None
        assert ergebnis.managed is not None
        assert ergebnis.held.mean_profit == pytest.approx(200.0)
        assert ergebnis.managed.mean_profit == pytest.approx(60.0)

    def test_episoden_ohne_trade_bleiben_gezaehlt(self) -> None:
        """Eine Kombination mit zwanzig Episoden und drei Trades ist etwas
        anderes als eine mit drei Episoden und drei Trades -- ohne die Zahl
        haetten beide dieselbe Zeile."""
        eintraege = [trade(gehalten=100.0, gemanagt=30.0) for _ in range(12)] + [None] * 8

        (ergebnis,) = [
            e
            for e in compute_options_backtest_results(
                {KOMBINATION: eintraege},
                options_params=OPTIONEN,
                backtest_params=BACKTEST,
                required_crossing_signals=2,
            )
            if e.signal_types == KOMBINATION
        ]

        assert ergebnis.episodes == 20
        assert ergebnis.trades == 12
        assert ergebnis.without_trade == 8

    def test_unter_der_mindeststichprobe_bleiben_die_kennzahlen_leer(self) -> None:
        """Eine Trefferquote aus vier Trades ist keine Trefferquote -- die
        Kennzahlen bleiben ``None``, nicht nur niedrig eingestuft. Dieselbe
        Schwelle wie die Aktienseite."""
        trades = [trade(gehalten=100.0, gemanagt=30.0) for _ in range(4)]

        (ergebnis,) = [
            e
            for e in compute_options_backtest_results(
                {KOMBINATION: trades},
                options_params=OPTIONEN,
                backtest_params=BACKTEST,
                required_crossing_signals=2,
            )
            if e.signal_types == KOMBINATION
        ]

        assert ergebnis.confidence is BacktestConfidence.INSUFFICIENT_DATA
        assert ergebnis.held is None
        assert ergebnis.managed is None
        # Die Grundgesamtheit bleibt trotzdem sichtbar.
        assert ergebnis.trades == 4

    def test_alle_moeglichen_kombinationen_kommen_zurueck(self) -> None:
        """Auch leere -- kein stillschweigendes Weglassen (Projektkonvention)."""
        ergebnisse = compute_options_backtest_results(
            {},
            options_params=OPTIONEN,
            backtest_params=BACKTEST,
            required_crossing_signals=2,
        )

        assert len(ergebnisse) == len(qualifying_combinations(2))
        assert all(e.episodes == 0 for e in ergebnisse)

    def test_die_annahmen_stehen_an_jedem_ergebnis(self) -> None:
        """Verfallskalender, Raster, Aufschlag und Abschlag machen aus
        demselben Kurspfad andere Zahlen -- ohne sie waere die Zeile nicht
        deutbar."""
        ergebnisse = compute_options_backtest_results(
            {KOMBINATION: [trade(gehalten=1.0, gemanagt=1.0)]},
            options_params=OptionsBacktestParameters(volatility_uplift=1.42),
            backtest_params=BACKTEST,
            required_crossing_signals=2,
        )

        annahmen = ergebnisse[0].assumptions
        assert annahmen["volatilitaetsaufschlag"] == "1.42"
        assert annahmen["kalender"] == "monatsverfaelle-dritter-freitag"
        assert annahmen["version"] == "optionsbacktest-v1"
