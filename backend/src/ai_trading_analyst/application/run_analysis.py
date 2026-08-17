"""Anwendungsfall: manuell gestarteter Analyse-Lauf (Sprint 1B).

Reine Orchestrierung. Enthaelt keine Signalformeln -- die Kandidatenpruefung
laeuft ausschliesslich ueber ``ai_trading_analyst.domain.screening.evaluate_candidate``
(Doc 10, Paragraph 9).
"""

from __future__ import annotations

import concurrent.futures
from collections.abc import Callable
from dataclasses import dataclass
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
    ScreeningResult,
    ScreeningStatus,
    evaluate_candidate,
)
from ai_trading_analyst.observability.logging_setup import get_logger

_logger = get_logger(__name__)

_MAX_CONCURRENT_RESEARCH = 4
"""Obergrenze gleichzeitiger Research-Aufrufe. Jeder Aufruf ist unabhaengig
(kein gemeinsamer veraenderlicher Zustand ausser dem laut Anthropic-SDK
threadsicheren HTTP-Client) -- eine unbegrenzte Nebenlaeufigkeit wuerde bei
vielen Kandidaten gleichzeitig ebenso viele teure LLM-Gespraeche parallel
auslösen, statt nur die Wartezeit zu verkuerzen."""


@dataclass
class _PreparedOutcome:
    """Ergebnis der schnellen, sequentiellen Screening-/Earnings-Phase einer
    Aktie -- Research (Netzwerk, mehrere Sekunden bis Minuten) und
    Persistenz folgen erst danach, siehe ``RunAnalysisUseCase.execute``."""

    stock: Stock
    result: ScreeningResult
    decision_index: int
    evaluated_at: datetime
    earnings: EarningsFilterResult | None
    needs_research: bool
    research: ResearchReport | None = None


@dataclass
class _PreparedError:
    stock: Stock
    exc: Exception


_PreparedItem = _PreparedOutcome | _PreparedError


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

    Der Research Agent (Doc 10, Paragraph 6.7; ADR 0021, ADR 0023) laeuft
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

        # Phase 1 (sequentiell, schnell): Screening und Earnings-Filter je
        # Aktie. Phase 2 (nebenlaeufig): die deutlich langsameren
        # Research-Aufrufe fuer alle Kandidaten mit EARNINGS_CLEAR auf
        # einmal. Phase 3 (sequentiell): Persistenz in der urspruenglichen
        # Aktienreihenfolge -- fuer Aufrufer wie CLI/Frontend bleibt die
        # Reihenfolge von ``outcomes``/``errors`` unveraendert, unabhaengig
        # davon, welche Recherche zuerst fertig wurde.
        prepared = [self._prepare_stock(stock) for stock in stocks]
        self._run_research_concurrently(prepared)

        outcomes: list[StockScreeningOutcome] = []
        errors: list[StockProcessingError] = []

        for item in prepared:
            if isinstance(item, _PreparedError):
                errors.append(self._persist_error(run, item.stock, item.exc))
                continue
            try:
                outcomes.append(self._persist_outcome(run, item))
            except Exception as exc:  # Fehlerisolation je Aktie (Doc 10)
                errors.append(self._persist_error(run, item.stock, exc))

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

    def _prepare_stock(self, stock: Stock) -> _PreparedItem:
        """Screening und Earnings-Filter fuer eine Aktie -- ohne Research
        (folgt nebenlaeufig in ``_run_research_concurrently``) und ohne
        Persistenz (folgt sequentiell in ``_persist_outcome``)."""
        try:
            series = self._market_data_provider.get_candle_series(stock)
            decision_index = len(series) - 1
            result = evaluate_candidate(series, decision_index, self._candidate_rule_params)
            evaluated_at = datetime.now(UTC)

            earnings: EarningsFilterResult | None = None
            needs_research = False
            if result.status == ScreeningStatus.CANDIDATE:
                earnings = self._evaluate_earnings(
                    stock, series.candles[decision_index].timestamp.date(), evaluated_at
                )
                needs_research = earnings.status == EarningsFilterStatus.EARNINGS_CLEAR

            return _PreparedOutcome(
                stock=stock,
                result=result,
                decision_index=decision_index,
                evaluated_at=evaluated_at,
                earnings=earnings,
                needs_research=needs_research,
            )
        except Exception as exc:  # Fehlerisolation je Aktie (Doc 10)
            return _PreparedError(stock=stock, exc=exc)

    def _run_research_concurrently(self, prepared: list[_PreparedItem]) -> None:
        pending = [
            item for item in prepared if isinstance(item, _PreparedOutcome) and item.needs_research
        ]
        if not pending:
            return

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(_MAX_CONCURRENT_RESEARCH, len(pending))
        ) as executor:
            futures = {
                executor.submit(self._evaluate_research, item.stock, item.evaluated_at): item
                for item in pending
            }
            for future in concurrent.futures.as_completed(futures):
                item = futures[future]
                try:
                    item.research = future.result()
                except Exception:
                    # ``_evaluate_research`` faengt bereits alles ab; hier
                    # bliebe nur ein Ausfall des Executors selbst. Auch der
                    # darf das Screening-Ergebnis nicht kosten.
                    _logger.exception(
                        "Nebenlaeufige Recherche fuer %s ist ausgefallen", item.stock.symbol
                    )
                    item.research = self._unavailable_research(
                        item.evaluated_at, "provider_error"
                    )

    def _persist_outcome(self, run: AnalysisRun, item: _PreparedOutcome) -> StockScreeningOutcome:
        outcome = StockScreeningOutcome(
            analysis_run_id=run.id,
            stock=item.stock,
            result=item.result,
            decision_candle_index=item.decision_index,
            evaluated_at=item.evaluated_at,
            signal_rule_version=SIGNAL_RULE_VERSION,
            earnings=item.earnings,
            research=item.research,
        )
        with self._uow_factory() as uow:
            uow.stocks.add(item.stock)
            uow.screening_results.add(outcome)
            uow.commit()
        return outcome

    def _persist_error(
        self, run: AnalysisRun, stock: Stock, exc: Exception
    ) -> StockProcessingError:
        error = StockProcessingError(
            analysis_run_id=run.id,
            stock_symbol=stock.symbol,
            message=str(exc),
            occurred_at=datetime.now(UTC),
        )
        with self._uow_factory() as uow:
            uow.processing_errors.add(error)
            uow.commit()
        return error

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

        Fehlerbehandlung nach dem Muster ``_evaluate_earnings``: Ein Ausfall
        des Anbieters wird hier abgefangen, nicht im aufrufenden
        Fehlerisolations-Block -- er soll ``ResearchStatus.UNAVAILABLE``
        ergeben, nicht die Aktie als Ganzes in ``StockProcessingError``
        verschieben (CLAUDE.md, Doc 10: Research darf die technische Analyse
        nie blockieren).

        Anders als bei ``_evaluate_earnings`` uebernimmt ein erfolgreicher
        Bericht **nicht** das uebergebene ``evaluated_at``: Der Anbieter
        stempelt seinen eigenen, tatsaechlichen Bearbeitungszeitpunkt --
        Research ist ein mehrere Gespraechsrunden langer, nebenlaeufig zu
        anderen Aktien laufender Vorgang (siehe
        ``RunAnalysisUseCase._run_research_concurrently``), keine
        Momentaufnahme wie der Earnings-Filter. ``evaluated_at`` wird nur im
        Fehlerfall unten verwendet, wo kein eigener Zeitpunkt vom Anbieter
        vorliegt.
        """
        try:
            return self._research_provider.research(stock)
        except ResearchProviderError as exc:
            _logger.warning("Research fuer %s konnte nicht abgerufen werden: %s", stock.symbol, exc)
            return self._unavailable_research(evaluated_at, "provider_error")
        except Exception as exc:
            # Ein Anbieter, der entgegen seinem Vertrag eine rohe Exception
            # wirft, darf das fertige Screening-Ergebnis nicht mitreissen --
            # das waere genau die Kopplung, die CLAUDE.md ausschliesst
            # ("Faellt Research aus, bleiben technische Analyse und
            # Backtesting vollstaendig"). Deshalb hier abgefangen und nicht
            # erst in der Fehlerisolation je Aktie, die die ganze Aktie
            # verwerfen wuerde.
            _logger.exception(
                "Research-Anbieter hat fuer %s eine unerwartete Ausnahme geworfen (%s)",
                stock.symbol,
                type(exc).__name__,
            )
            return self._unavailable_research(evaluated_at, "provider_contract_violation")

    def _unavailable_research(self, evaluated_at: datetime, reason: str) -> ResearchReport:
        return ResearchReport(
            status=ResearchStatus.UNAVAILABLE,
            evaluated_at=evaluated_at,
            model=None,
            prompt_version=None,
            reason=reason,
        )
