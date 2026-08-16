"""Anwendungsfall: manuell gestarteter Analyse-Lauf (Sprint 1B).

Reine Orchestrierung. Enthaelt keine Signalformeln -- die Kandidatenpruefung
laeuft ausschliesslich ueber ``ai_trading_analyst.domain.screening.evaluate_candidate``
(Doc 10, Paragraph 9).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from uuid import uuid4

from ai_trading_analyst.domain.analysis import (
    AnalysisRun,
    AnalysisRunSummary,
    EarningsProvider,
    EarningsProviderError,
    MarketDataProvider,
    MarketDataProviderError,
    ResearchProvider,
    ResearchProviderError,
    RunStatus,
    Stock,
    StockProcessingError,
    StockScreeningOutcome,
    UnitOfWork,
)
from ai_trading_analyst.domain.earnings import (
    EarningsFilterParameters,
    EarningsFilterResult,
    EarningsFilterStatus,
    evaluate_earnings_filter,
)
from ai_trading_analyst.domain.research import ResearchReport, ResearchStatus
from ai_trading_analyst.domain.screening import (
    SIGNAL_RULE_VERSION,
    CandidateRuleParameters,
    ScreeningStatus,
    evaluate_candidate,
)
from ai_trading_analyst.observability.logging_setup import get_logger

_logger = get_logger(__name__)


class RunAnalysisUseCase:
    """Bezieht Aktien ueber einen ``MarketDataProvider``, screent jede Aktie
    mit dem freigegebenen Domain-Screener und persistiert das Ergebnis.

    Fehler bei einer einzelnen Aktie werden isoliert: sie fuehren nicht dazu,
    dass der gesamte Lauf abbricht, sondern werden als
    ``StockProcessingError`` erfasst. Scheitert bereits die Aktienliste
    selbst, wird der Lauf als Ganzes ``FAILED``, ohne dass das Screening
    ueberhaupt beginnt.

    Der Earnings-Filter (Doc 10, Paragraph 6.5) laeuft ausschliesslich fuer
    Aktien, die der Screener als ``CANDIDATE`` einstuft. Ein Ausfall des
    Earnings-Anbieters ist kein Verarbeitungsfehler der Aktie -- er ergibt
    ``EarningsFilterStatus.UNKNOWN`` und die Aktie bleibt ein normales
    Ergebnis, statt in ``StockProcessingError`` zu landen (ADR 0017: die
    technische Analyse laeuft unabhaengig vom Earnings-Filter weiter).

    Der Research Agent (Doc 10, Paragraph 6.7; ADR 0021, ADR 0022) laeuft
    danach, ausschliesslich fuer Aktien, die zusaetzlich den Earnings-Filter
    mit ``EARNINGS_CLEAR`` bestanden haben. Ein Ausfall des
    Research-Anbieters ist wie beim Earnings-Filter kein Verarbeitungsfehler
    der Aktie -- er ergibt ``ResearchStatus.UNAVAILABLE`` statt eines
    ``StockProcessingError`` (CLAUDE.md: Research darf die technische
    Analyse und das Backtesting nie blockieren).
    """

    def __init__(
        self,
        market_data_provider: MarketDataProvider,
        earnings_provider: EarningsProvider,
        research_provider: ResearchProvider,
        uow_factory: Callable[[], UnitOfWork],
        candidate_rule_params: CandidateRuleParameters,
        earnings_filter_params: EarningsFilterParameters,
    ) -> None:
        self._market_data_provider = market_data_provider
        self._earnings_provider = earnings_provider
        self._research_provider = research_provider
        self._uow_factory = uow_factory
        self._candidate_rule_params = candidate_rule_params
        self._earnings_filter_params = earnings_filter_params

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
                evaluated_at = datetime.now(UTC)

                earnings: EarningsFilterResult | None = None
                research: ResearchReport | None = None
                if result.status == ScreeningStatus.CANDIDATE:
                    earnings = self._evaluate_earnings(
                        stock, series.candles[decision_index].timestamp.date(), evaluated_at
                    )
                    if earnings.status == EarningsFilterStatus.EARNINGS_CLEAR:
                        research = self._evaluate_research(stock, evaluated_at)

                outcome = StockScreeningOutcome(
                    analysis_run_id=run.id,
                    stock=stock,
                    result=result,
                    decision_candle_index=decision_index,
                    evaluated_at=evaluated_at,
                    signal_rule_version=SIGNAL_RULE_VERSION,
                    earnings=earnings,
                    research=research,
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

    def _evaluate_earnings(
        self, stock: Stock, as_of: date, evaluated_at: datetime
    ) -> EarningsFilterResult:
        """Wertet den Earnings-Filter fuer eine bereits qualifizierte Aktie aus.

        Ein Ausfall des Anbieters wird hier abgefangen, nicht im aufrufenden
        Fehlerisolations-Block: Er soll ``EarningsFilterStatus.UNKNOWN``
        ergeben, nicht die Aktie als Ganzes in ``StockProcessingError``
        verschieben (ADR 0017).
        """
        try:
            next_earnings = self._earnings_provider.next_earnings_date(stock)
        except EarningsProviderError:
            return EarningsFilterResult(
                status=EarningsFilterStatus.UNKNOWN,
                evaluated_at=evaluated_at,
                reason="provider_error",
            )

        try:
            return evaluate_earnings_filter(
                next_earnings, as_of, self._earnings_filter_params, evaluated_at
            )
        except ValueError as exc:
            # Der Anbieter selbst ist erreichbar, seine Antwort aber nicht
            # plausibel auswertbar (z. B. ein Termin vor der Entscheidungskerze).
            # Das ist ein Datenproblem der Quelle, kein Ausfall -- dieselbe
            # Einstufung wie ein Ausfall (ADR 0017), aber mit eigenem Grund.
            _logger.warning(
                "Earnings-Termin fuer %s konnte nicht ausgewertet werden: %s",
                stock.symbol,
                exc,
            )
            return EarningsFilterResult(
                status=EarningsFilterStatus.UNKNOWN,
                evaluated_at=evaluated_at,
                reason="invalid_data",
            )

    def _evaluate_research(self, stock: Stock, evaluated_at: datetime) -> ResearchReport:
        """Wertet den Research Agent fuer eine bereits qualifizierte Aktie aus.

        Muster ``_evaluate_earnings``: Ein Ausfall des Anbieters wird hier
        abgefangen, nicht im aufrufenden Fehlerisolations-Block -- er soll
        ``ResearchStatus.UNAVAILABLE`` ergeben, nicht die Aktie als Ganzes in
        ``StockProcessingError`` verschieben (CLAUDE.md, Doc 10: Research
        darf die technische Analyse nie blockieren).
        """
        try:
            return self._research_provider.research(stock)
        except ResearchProviderError as exc:
            _logger.warning(
                "Research fuer %s konnte nicht abgerufen werden: %s", stock.symbol, exc
            )
            return ResearchReport(
                status=ResearchStatus.UNAVAILABLE,
                evaluated_at=evaluated_at,
                model=None,
                prompt_version=None,
                reason="provider_error",
            )
