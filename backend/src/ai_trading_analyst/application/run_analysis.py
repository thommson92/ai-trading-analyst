"""Anwendungsfall: manuell gestarteter Analyse-Lauf (Sprint 1B).

Reine Orchestrierung. Enthaelt keine Signalformeln -- die Kandidatenpruefung
laeuft ausschliesslich ueber ``ai_trading_analyst.domain.screening.evaluate_candidate``
(Doc 10, Paragraph 9).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from ai_trading_analyst.domain.analysis import (
    AnalysisRun,
    AnalysisRunSummary,
    MarketDataProvider,
    MarketDataProviderError,
    RunStatus,
    StockProcessingError,
    StockScreeningOutcome,
    UnitOfWork,
)
from ai_trading_analyst.domain.screening import (
    SIGNAL_RULE_VERSION,
    CandidateRuleParameters,
    ScreeningStatus,
    evaluate_candidate,
)


class RunAnalysisUseCase:
    """Bezieht Aktien ueber einen ``MarketDataProvider``, screent jede Aktie
    mit dem freigegebenen Domain-Screener und persistiert das Ergebnis.

    Fehler bei einer einzelnen Aktie werden isoliert: sie fuehren nicht dazu,
    dass der gesamte Lauf abbricht, sondern werden als
    ``StockProcessingError`` erfasst. Scheitert bereits die Aktienliste
    selbst, wird der Lauf als Ganzes ``FAILED``, ohne dass das Screening
    ueberhaupt beginnt.
    """

    def __init__(
        self,
        market_data_provider: MarketDataProvider,
        uow_factory: Callable[[], UnitOfWork],
        candidate_rule_params: CandidateRuleParameters,
    ) -> None:
        self._market_data_provider = market_data_provider
        self._uow_factory = uow_factory
        self._candidate_rule_params = candidate_rule_params

    def execute(self) -> AnalysisRunSummary:
        run = AnalysisRun(id=uuid4(), status=RunStatus.RUNNING, started_at=datetime.now(UTC))
        with self._uow_factory() as uow:
            uow.analysis_runs.add(run)
            uow.commit()

        try:
            stocks = self._market_data_provider.list_stocks()
        except MarketDataProviderError as exc:
            run.status = RunStatus.FAILED
            run.completed_at = datetime.now(UTC)
            run.error_message = str(exc)
            with self._uow_factory() as uow:
                uow.analysis_runs.update(run)
                uow.commit()
            return AnalysisRunSummary(run=run)

        run.number_of_stocks = len(stocks)
        run.status = RunStatus.SCREENING
        with self._uow_factory() as uow:
            uow.analysis_runs.update(run)
            uow.commit()

        outcomes: list[StockScreeningOutcome] = []
        errors: list[StockProcessingError] = []

        for stock in stocks:
            try:
                series = self._market_data_provider.get_candle_series(stock)
                decision_index = len(series) - 1
                result = evaluate_candidate(series, decision_index, self._candidate_rule_params)
                outcome = StockScreeningOutcome(
                    analysis_run_id=run.id,
                    stock=stock,
                    result=result,
                    decision_candle_index=decision_index,
                    evaluated_at=datetime.now(UTC),
                    signal_rule_version=SIGNAL_RULE_VERSION,
                )
                with self._uow_factory() as uow:
                    uow.stocks.add(stock)
                    uow.screening_results.add(outcome)
                    uow.commit()
                outcomes.append(outcome)
            except Exception as exc:  # Fehlerisolation je Aktie (Doc 10)
                error = StockProcessingError(
                    analysis_run_id=run.id,
                    stock_symbol=stock.symbol,
                    message=str(exc),
                    occurred_at=datetime.now(UTC),
                )
                with self._uow_factory() as uow:
                    uow.processing_errors.add(error)
                    uow.commit()
                errors.append(error)

        run.candidates_found = sum(
            1 for outcome in outcomes if outcome.result.status == ScreeningStatus.CANDIDATE
        )
        run.completed_at = datetime.now(UTC)
        if not errors:
            run.status = RunStatus.COMPLETED
        elif outcomes:
            run.status = RunStatus.PARTIALLY_COMPLETED
        else:
            run.status = RunStatus.FAILED

        with self._uow_factory() as uow:
            uow.analysis_runs.update(run)
            uow.commit()

        return AnalysisRunSummary(run=run, outcomes=tuple(outcomes), errors=tuple(errors))
