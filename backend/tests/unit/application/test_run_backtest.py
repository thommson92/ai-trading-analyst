"""Tests des Anwendungsfalls BacktestUseCase.

Prueft ausschliesslich Orchestrierung: Persistenz je Aktie und
Fehlerisolation. Replay, Deduplizierung und Kennzahlen sind bereits in
``tests/unit/domain/backtesting`` abgedeckt.
"""

from __future__ import annotations

from ai_trading_analyst.application.run_backtest import BacktestUseCase
from ai_trading_analyst.domain.backtesting import BacktestParameters
from ai_trading_analyst.domain.screening import CandidateRuleParameters
from tests.unit.application.conftest import (
    FakeAnalysisRunRepository,
    FakeBacktestResultRepository,
    FakeMarketDataProvider,
    FakeProcessingErrorRepository,
    FakeScreeningResultRepository,
    FakeStockRepository,
    FakeUnitOfWork,
    InMemoryIntradayBarRepository,
    make_series,
    make_stock,
)

CANDIDATE_PARAMS = CandidateRuleParameters(
    required_crossing_signals=2, signal_lookback_previous_candles=5, warmup_candles=10
)
BACKTEST_PARAMS = BacktestParameters(
    horizons=(5,),
    cooldown_candles=5,
    minimum_sample_size=1,
    normal_confidence_sample_size=1,
    history_years=5,
)
SERIES_LENGTH = 20


def _build_use_case(
    provider: FakeMarketDataProvider,
) -> tuple[BacktestUseCase, FakeBacktestResultRepository, FakeStockRepository]:
    backtest_results_repo = FakeBacktestResultRepository()
    stocks_repo = FakeStockRepository()

    def uow_factory() -> FakeUnitOfWork:
        return FakeUnitOfWork(
            stocks_repo,
            InMemoryIntradayBarRepository(),
            FakeAnalysisRunRepository(),
            FakeScreeningResultRepository(),
            FakeProcessingErrorRepository(),
            backtest_results_repo,
        )

    use_case = BacktestUseCase(provider, uow_factory, CANDIDATE_PARAMS, BACKTEST_PARAMS)
    return use_case, backtest_results_repo, stocks_repo


class TestErfolgreicherLauf:
    def test_jede_aktie_bekommt_alle_kombinationen_persistiert(self) -> None:
        stock_a, stock_b = make_stock("AAA"), make_stock("BBB")
        provider = FakeMarketDataProvider(
            stocks=(stock_a, stock_b),
            series_by_symbol={
                "AAA": make_series(SERIES_LENGTH, candidate=False),
                "BBB": make_series(SERIES_LENGTH, candidate=False),
            },
        )
        use_case, backtest_results_repo, _ = _build_use_case(provider)

        report = use_case.execute()

        assert {s.symbol for s in report.stocks} == {"AAA", "BBB"}
        assert not report.failures
        assert len(backtest_results_repo.added) == 24  # 12 Kombinationen je Aktie
        stock_ids = {result.stock_id for result in backtest_results_repo.results}
        assert stock_ids == {stock_a.id, stock_b.id}

    def test_die_aktie_wird_vor_den_ergebnissen_gespeichert(self) -> None:
        """Sonst schlaegt die Fremdschluesselbeziehung auf 'stocks' fehl,
        sobald echte Persistenz statt eines Fakes im Spiel ist."""
        stock = make_stock("AAA")
        provider = FakeMarketDataProvider(
            stocks=(stock,),
            series_by_symbol={"AAA": make_series(SERIES_LENGTH, candidate=False)},
        )
        use_case, _, stocks_repo = _build_use_case(provider)

        use_case.execute()

        assert stock in stocks_repo.added


class TestFehlerisolation:
    def test_ein_providerfehler_bleibt_auf_die_betroffene_aktie_beschraenkt(self) -> None:
        stock_a, stock_b = make_stock("AAA"), make_stock("BROKEN")
        provider = FakeMarketDataProvider(
            stocks=(stock_a, stock_b),
            series_by_symbol={"AAA": make_series(SERIES_LENGTH, candidate=False)},
            error_symbols=frozenset({"BROKEN"}),
        )
        use_case, backtest_results_repo, _ = _build_use_case(provider)

        report = use_case.execute()

        assert {s.symbol for s in report.failures} == {"BROKEN"}
        by_symbol = {s.symbol: s for s in report.stocks}
        assert by_symbol["AAA"].results
        assert by_symbol["BROKEN"].results == ()
        assert len(backtest_results_repo.added) == 12  # nur AAA

    def test_leere_aktienliste_ergibt_einen_leeren_bericht(self) -> None:
        provider = FakeMarketDataProvider(stocks=(), series_by_symbol={})
        use_case, backtest_results_repo, _ = _build_use_case(provider)

        report = use_case.execute()

        assert report.stocks == ()
        assert not report.failures
        assert not backtest_results_repo.added
