"""End-to-End-Tests der gesamten Kette: FixtureMarketDataProvider ->
RunAnalysisUseCase -> deterministischer Screener -> PostgreSQL.

Die Fixture-Daten enthalten immer einen kontrollierten Providerfehler (siehe
``infrastructure/fixtures/data/v1/stocks.json``) -- ein vollstaendiger Lauf
mit den Standard-Fixtures ist deshalb zugleich der Test fuer den teilweise
erfolgreichen Lauf (``PARTIALLY_COMPLETED``). Ein vollstaendiges Scheitern
*vor* Beginn des Screenings kann die Fixture-Daten dagegen nicht erzeugen
(``list_stocks`` schlaegt dort nie fehl) und wird deshalb mit einem
eigenen, absichtlich immer scheiternden Provider getestet.
"""

from __future__ import annotations

from collections.abc import Callable

from ai_trading_analyst.application.run_analysis import RunAnalysisUseCase
from ai_trading_analyst.domain.analysis import MarketDataProviderError, RunStatus, Stock
from ai_trading_analyst.domain.screening import (
    CandidateRuleParameters,
    CandleSeries,
    ScreeningStatus,
)
from ai_trading_analyst.infrastructure.fixtures.market_data_provider import (
    FixtureMarketDataProvider,
)
from ai_trading_analyst.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork

UowFactory = Callable[[], SqlAlchemyUnitOfWork]

_PARAMS = CandidateRuleParameters(
    required_signal_count=2, signal_lookback_previous_candles=5, warmup_candles=250
)


class _AlwaysFailingMarketDataProvider:
    def list_stocks(self) -> tuple[Stock, ...]:
        raise MarketDataProviderError("Marktdatenanbieter vollstaendig nicht erreichbar")

    def get_candle_series(self, stock: Stock) -> CandleSeries:  # pragma: no cover - nie erreicht
        raise AssertionError("get_candle_series wird nie aufgerufen, wenn list_stocks scheitert")


def test_vollstaendiger_fixture_basierter_lauf_ist_teilweise_erfolgreich(
    uow_factory: UowFactory,
) -> None:
    use_case = RunAnalysisUseCase(FixtureMarketDataProvider(), uow_factory, _PARAMS)

    summary = use_case.execute()

    assert summary.run.status == RunStatus.PARTIALLY_COMPLETED
    assert summary.run.number_of_stocks == 4
    assert summary.run.candidates_found == 1

    outcomes_by_symbol = {o.stock.symbol: o.result.status for o in summary.outcomes}
    assert outcomes_by_symbol == {
        "FIXCAND": ScreeningStatus.CANDIDATE,
        "FIXNOCAND": ScreeningStatus.NOT_CANDIDATE,
        "FIXINCOMPLETE": ScreeningStatus.UNKNOWN_DATA_INCOMPLETE,
    }
    assert {e.stock_symbol for e in summary.errors} == {"FIXERROR"}

    with uow_factory() as uow:
        persisted_outcomes = uow.screening_results.list_for_run(summary.run.id)
        persisted_errors = uow.processing_errors.list_for_run(summary.run.id)
        persisted_run = uow.analysis_runs.get(summary.run.id)

    assert len(persisted_outcomes) == 3
    assert len(persisted_errors) == 1
    assert persisted_run == summary.run


def test_vollstaendiges_scheitern_vor_screeningbeginn_wird_nicht_teilweise_persistiert(
    uow_factory: UowFactory,
) -> None:
    use_case = RunAnalysisUseCase(_AlwaysFailingMarketDataProvider(), uow_factory, _PARAMS)

    summary = use_case.execute()

    assert summary.run.status == RunStatus.FAILED
    assert summary.run.number_of_stocks == 0
    assert "nicht erreichbar" in (summary.run.error_message or "")
    assert not summary.outcomes
    assert not summary.errors

    with uow_factory() as uow:
        assert uow.screening_results.list_for_run(summary.run.id) == ()
        assert uow.processing_errors.list_for_run(summary.run.id) == ()
        persisted_run = uow.analysis_runs.get(summary.run.id)
    assert persisted_run is not None
    assert persisted_run.status == RunStatus.FAILED
