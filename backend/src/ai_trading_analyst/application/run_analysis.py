"""Anwendungsfall: manuell gestarteter Analyse-Lauf (Sprint 1B).

Reine Orchestrierung. Enthaelt keine Signalformeln -- die Kandidatenpruefung
laeuft ausschliesslich ueber ``ai_trading_analyst.domain.screening.evaluate_candidate``
(Doc 10, Paragraph 9).
"""

from __future__ import annotations

import concurrent.futures
import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal
from uuid import uuid4

from ai_trading_analyst.domain.analysis import (
    AnalysisRun,
    AnalysisRunSummary,
    AnalystRecommendationsFormatError,
    AnalystRecommendationsProvider,
    AnalystRecommendationsProviderError,
    EarningsProvider,
    EarningsProviderError,
    FundamentalDataProvider,
    FundamentalDataProviderError,
    MarketDataProvider,
    MarketDataProviderError,
    ResearchProvider,
    ResearchProviderError,
    RunStatus,
    Stock,
    StockProcessingError,
    StockScreeningOutcome,
    TechnicalInterpreter,
    TechnicalInterpreterError,
    UnitOfWork,
)
from ai_trading_analyst.domain.analysts import (
    AnalystRecommendations,
    AnalystRecommendationStatus,
)
from ai_trading_analyst.domain.backtesting import (
    BacktestParameters,
    BacktestResult,
    compute_backtest_results,
)
from ai_trading_analyst.domain.earnings import (
    EarningsFilterParameters,
    EarningsFilterResult,
    EarningsFilterStatus,
    evaluate_earnings_filter,
)
from ai_trading_analyst.domain.fundamentals import FundamentalSnapshot
from ai_trading_analyst.domain.report import (
    StockReport,
    as_document,
    build_report,
    render_notification,
)
from ai_trading_analyst.domain.research import ResearchReport, ResearchStatus
from ai_trading_analyst.domain.scheduling import Notifier, NotifierError
from ai_trading_analyst.domain.scoring import (
    RecommendationResult,
    ScoreResult,
    ScoringParameters,
    compute_long_term_score,
    compute_swing_score,
    derive_recommendation,
)
from ai_trading_analyst.domain.screening import (
    SIGNAL_RULE_VERSION,
    CandidateRuleParameters,
    CandleSeries,
    ScreeningResult,
    ScreeningStatus,
    evaluate_candidate,
)
from ai_trading_analyst.domain.technical import (
    TechnicalAnalysisParameters,
    TechnicalAssessment,
    TechnicalAssessmentStatus,
    TechnicalSnapshot,
    compute_technical_snapshot,
)
from ai_trading_analyst.observability.logging_setup import get_logger

_logger = get_logger(__name__)

_Agentenart = Literal["research", "technical"]
"""Diskriminator der beiden Auftragsarten in der nebenlaeufigen Phase.

Ein ``Literal`` und kein freier ``str``: mypy prueft damit jede Aufrufstelle.
Ein Tippfehler landete sonst im ``else``-Zweig und wiese ein
Research-Ergebnis dem Feld der Einordnung zu.
"""

@dataclass(frozen=True, slots=True)
class AgentConcurrency:
    """Wie viele Modellaufrufe je Agent gleichzeitig laufen duerfen.

    **Je Agent ein eigener Pool** (ADR 0037, Risiko R9). Vorher teilten sich
    beide vier Plaetze; eine haengende Recherche belegte bis zu
    ``research.request_timeout_seconds`` (900 s) einen davon, waehrend die
    Einordnungen warteten -- die bei einem realen Lauf Sekunden dauern.

    Eine Obergrenze braucht es trotzdem je Pool: Jeder Aufruf ist unabhaengig
    (kein gemeinsamer veraenderlicher Zustand ausser dem laut Anthropic-SDK
    threadsicheren HTTP-Client), aber unbegrenzte Nebenlaeufigkeit wuerde bei
    vielen Kandidaten ebenso viele teure Gespraeche gleichzeitig auslösen,
    statt die Wartezeit je Aufruf zu verkuerzen.
    """

    research: int = 2
    technical: int = 4

    def fuer(self, art: _Agentenart) -> int:
        return self.research if art == "research" else self.technical


@dataclass
class _PreparedOutcome:
    """Ergebnis der schnellen, sequentiellen Screening-/Earnings-Phase einer
    Aktie -- Research (Netzwerk, mehrere Sekunden bis Minuten) und
    Persistenz folgen erst danach, siehe ``RunAnalysisUseCase.execute``."""

    stock: Stock
    result: ScreeningResult
    decision_index: int
    evaluated_at: datetime
    technical: TechnicalSnapshot | None
    fundamentals: FundamentalSnapshot | None
    analysts: AnalystRecommendations | None
    earnings: EarningsFilterResult | None
    backtest: tuple[BacktestResult, ...]
    needs_research: bool
    research: ResearchReport | None = None
    technical_assessment: TechnicalAssessment | None = None


@dataclass
class _PreparedError:
    stock: Stock
    exc: Exception


_PreparedItem = _PreparedOutcome | _PreparedError


class StaleDataError(RuntimeError):
    """Fuer diese Aktie fehlen die Daten des laufenden Handelstages.

    Kein Defekt, sondern ein Teilausfall beim Abruf. Die Aktie wird als
    Verarbeitungsfehler gefuehrt statt auf altem Stand gescreent.
    """


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

    Die deterministische Chartauswertung (Doc 10, Paragraph 6.8) laeuft
    ebenfalls nur fuer Kandidaten, aber **vor** dem Earnings-Filter und
    unabhaengig von dessen Ergebnis: Sie rechnet allein auf der bereits
    geholten Kerzenserie und kann deshalb gar nicht an einer externen Quelle
    scheitern. Reicht die Historie nicht, ist ihr Ergebnis
    ``TechnicalStatus.INSUFFICIENT_DATA`` -- kein Verarbeitungsfehler der
    Aktie.

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
        technical_interpreter: TechnicalInterpreter,
        fundamental_data_provider: FundamentalDataProvider,
        analyst_recommendations_provider: AnalystRecommendationsProvider,
        uow_factory: Callable[[], UnitOfWork],
        candidate_rule_params: CandidateRuleParameters,
        earnings_filter_params: EarningsFilterParameters,
        technical_params: TechnicalAnalysisParameters,
        backtest_params: BacktestParameters,
        scoring_params: ScoringParameters,
        expected_last_candle: datetime | None = None,
        agent_concurrency: AgentConcurrency | None = None,
        app_version: str = "",
        notifier: Notifier | None = None,
        notify_without_candidates: bool = False,
        market_timezone: str = "America/New_York",
    ) -> None:
        self._market_data_provider = market_data_provider
        self._earnings_provider = earnings_provider
        self._research_provider = research_provider
        self._technical_interpreter = technical_interpreter
        self._fundamental_data_provider = fundamental_data_provider
        self._analyst_recommendations_provider = analyst_recommendations_provider
        self._uow_factory = uow_factory
        self._candidate_rule_params = candidate_rule_params
        self._earnings_filter_params = earnings_filter_params
        self._technical_params = technical_params
        self._backtest_params = backtest_params
        self._scoring_params = scoring_params
        self._expected_last_candle = expected_last_candle
        self._agent_concurrency = agent_concurrency or AgentConcurrency()
        self._app_version = app_version
        self._notifier = notifier
        self._notify_without_candidates = notify_without_candidates
        self._market_timezone = market_timezone

    def _require_expected_candle(self, series: CandleSeries, decision_index: int) -> None:
        """Ist die juengste Kerze die, um die es geht?

        Ohne diese Pruefung entscheidet allein ``len(series) - 1``, und die
        Kerzenreihe kennt keinen Bezug zur Gegenwart. Eine Aktie, deren
        Bestand vor drei Tagen endet, ergaebe damit ein sauber aussehendes
        CANDIDATE oder NOT_CANDIDATE, an dem nichts auf das Alter hinweist --
        genau die Analyse, die aussieht wie die heutige und es nicht ist.

        Der Fall entsteht im automatischen Lauf leicht: Reisst die Verbindung
        zur TWS mitten im Abruf ab, sind einige Aktien frisch und die
        uebrigen von gestern.

        Ohne ``expected_last_candle`` (manueller Lauf, Backtesting) wird nicht
        geprueft -- dort entscheidet der Mensch, welchen Stand er sieht.
        """
        if self._expected_last_candle is None:
            return
        vorhanden = series.candle(decision_index).timestamp
        if vorhanden != self._expected_last_candle:
            raise StaleDataError(
                f"Die juengste Kerze ist {vorhanden.isoformat()}, erwartet wurde "
                f"{self._expected_last_candle.isoformat()}. Fuer diese Aktie fehlen "
                "die Daten des laufenden Handelstages."
            )

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
        self._run_agents_concurrently(prepared)

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

        summary = AnalysisRunSummary(run=run, outcomes=tuple(outcomes), errors=tuple(errors))
        self._notify(summary)
        return summary

    def _notify(self, summary: AnalysisRunSummary) -> None:
        """Die kompakte Zusammenfassung an den Kanal (ADR 0040).

        Nur wenn ein Notifier hineingereicht wurde -- der Tageslauf tut das,
        ein manuelles ``cli screen`` nicht. Ein unerreichbarer Kanal darf den
        Lauf nicht nachtraeglich scheitern lassen (ADR 0024): Er ist eine
        Systemgrenze, und das Ergebnis steht zu diesem Zeitpunkt bereits in
        der Datenbank.
        """
        if self._notifier is None:
            return
        if not summary.run.candidates_found and not self._notify_without_candidates:
            return
        try:
            # Auch das Rendern gehoert hinein: Der Docstring sagt, dass der
            # Kanal den Lauf nicht nachtraeglich scheitern laesst, und das
            # Ergebnis steht zu diesem Zeitpunkt bereits in der Datenbank.
            betreff, text = render_notification(summary, timezone=self._market_timezone)
            self._notifier.send(betreff, text)
        except NotifierError as error:
            _logger.error("Ergebnismeldung ging nicht raus: %s", error)
        except Exception:
            _logger.exception("Ergebnismeldung liess sich nicht erzeugen")

    def _prepare_stock(self, stock: Stock) -> _PreparedItem:
        """Screening und Earnings-Filter fuer eine Aktie -- ohne Research
        (folgt nebenlaeufig in ``_run_agents_concurrently``) und ohne
        Persistenz (folgt sequentiell in ``_persist_outcome``)."""
        try:
            series = self._market_data_provider.get_candle_series(stock)
            decision_index = len(series) - 1
            self._require_expected_candle(series, decision_index)
            result = evaluate_candidate(series, decision_index, self._candidate_rule_params)
            evaluated_at = datetime.now(UTC)

            technical: TechnicalSnapshot | None = None
            fundamentals: FundamentalSnapshot | None = None
            analysts: AnalystRecommendations | None = None
            earnings: EarningsFilterResult | None = None
            backtest: tuple[BacktestResult, ...] = ()
            needs_research = False
            if result.status == ScreeningStatus.CANDIDATE:
                # Bewusst vor dem Earnings-Filter und unabhaengig von dessen
                # Ergebnis: Die Chartauswertung rechnet ausschliesslich auf
                # der ohnehin geholten Kerzenserie. Sie hinter den Filter zu
                # haengen wuerde sie ohne Not von einer externen Quelle
                # abhaengig machen, die ausfallen kann (CLAUDE.md:
                # Analysemodule sind entkoppelt).
                technical = compute_technical_snapshot(
                    series, decision_index, self._technical_params, evaluated_at
                )
                # Aus demselben Grund und auf derselben Kerzenserie: Der
                # Backtest rechnet ohne Netz (ADR 0038).
                backtest = self._evaluate_backtest(stock, series, evaluated_at)
                # Der Kurs der letzten **abgeschlossenen** Kerze, genau der,
                # auf dem Screening und Chartauswertung stehen (ADR 0035,
                # Entscheidung 2). Das Fundamentalmodul beschafft keinen
                # eigenen und leitet keinen ab.
                fundamentals = self._evaluate_fundamentals(
                    stock, series.candles[decision_index].close
                )
                # Ebenfalls unabhaengig vom Earnings-Filter und vom Research
                # Agent: Berichtspunkt 9 soll auch dann stehen, wenn die
                # Recherche ausgefallen ist (ADR 0043).
                analysts = self._evaluate_analyst_recommendations(stock, evaluated_at)
                earnings = self._evaluate_earnings(
                    stock, series.candles[decision_index].timestamp.date(), evaluated_at
                )
                needs_research = earnings.status == EarningsFilterStatus.EARNINGS_CLEAR

            return _PreparedOutcome(
                stock=stock,
                result=result,
                decision_index=decision_index,
                evaluated_at=evaluated_at,
                technical=technical,
                fundamentals=fundamentals,
                analysts=analysts,
                earnings=earnings,
                backtest=backtest,
                needs_research=needs_research,
            )
        except Exception as exc:  # Fehlerisolation je Aktie (Doc 10)
            return _PreparedError(stock=stock, exc=exc)

    def _run_agents_concurrently(self, prepared: list[_PreparedItem]) -> None:
        """Phase 2: die langsamen Modellaufrufe, alle auf einmal.

        **Je Agent ein eigener Pool** (ADR 0037, Risiko R9). Bei einem
        gemeinsamen Pool belegte eine haengende Recherche bis zu
        ``research.request_timeout_seconds`` (900 s) einen der vier Plaetze,
        waehrend die Einordnungen warteten -- die Sekunden dauern. Ein realer
        Recherche-Aufruf braucht rund 15 Minuten (Messung 2026-08-24), die
        Grenze war also nicht theoretisch.

        Zugewiesen wird ausschliesslich im Hauptthread aus ``as_completed``
        heraus -- die Arbeiter schreiben nichts.
        """
        auftraege: list[tuple[_PreparedOutcome, _Agentenart]] = []
        for item in prepared:
            if not isinstance(item, _PreparedOutcome):
                continue
            if item.needs_research:
                auftraege.append((item, "research"))
            # Anders als Research haengt die Einordnung an keinem anderen
            # Modul: Sie laeuft fuer jeden Kandidaten mit auswertbarer
            # Chartlage, auch bei nahem Earnings-Termin (CLAUDE.md:
            # Analysemodule sind entkoppelt; ADR 0026).
            if item.technical is not None:
                auftraege.append((item, "technical"))

        if not auftraege:
            return

        nach_art: dict[_Agentenart, list[_PreparedOutcome]] = {"research": [], "technical": []}
        for item, art in auftraege:
            nach_art[art].append(item)

        # ExitStack statt geschachtelter with-Bloecke: Beide Pools muessen
        # offen sein, waehrend ``as_completed`` ueber die Auftraege beider
        # laeuft. Geschachtelt liefe der aeussere Pool sonst leer, bis der
        # innere fertig ist -- genau die Serialisierung, die R9 beseitigt.
        with contextlib.ExitStack() as stack:
            futures: dict[
                concurrent.futures.Future[ResearchReport | TechnicalAssessment],
                tuple[_PreparedOutcome, _Agentenart],
            ] = {}
            for art, posten in nach_art.items():
                if not posten:
                    continue
                executor = stack.enter_context(
                    concurrent.futures.ThreadPoolExecutor(
                        max_workers=min(self._agent_concurrency.fuer(art), len(posten)),
                        thread_name_prefix=f"agent-{art}",
                    )
                )
                for item in posten:
                    futures[executor.submit(self._agent_result, item, art)] = (item, art)

            for future in concurrent.futures.as_completed(futures):
                item, art = futures[future]
                try:
                    self._assign_agent_result(item, art, future.result())
                except Exception:
                    # ``_agent_result`` faengt bereits alles ab; hier bliebe
                    # nur ein Ausfall des Executors selbst. Auch der darf das
                    # Screening-Ergebnis nicht kosten.
                    _logger.exception(
                        "Nebenlaeufiger Agentenlauf (%s) fuer %s ist ausgefallen",
                        art,
                        item.stock.symbol,
                    )
                    self._assign_agent_result(
                        item, art, self._unavailable_result(item, art, "provider_error")
                    )

    def _agent_result(
        self, item: _PreparedOutcome, art: _Agentenart
    ) -> ResearchReport | TechnicalAssessment:
        """Laeuft im Arbeitsthread und **liefert** nur -- er schreibt nichts.

        Die Zuweisung bleibt dem Hauptthread vorbehalten
        (``_assign_agent_result``). Bei zwei Auftragsarten je Aktie schrieben
        sonst zwei Threads in dasselbe Objekt; dass sie verschiedene Felder
        traefen, waere eine Zusicherung, die man beim naechsten Agenten
        vergisst.
        """
        if art == "research":
            return self._evaluate_research(item.stock, item.evaluated_at)
        assert item.technical is not None
        return self._evaluate_technical_assessment(item.stock, item.technical, item.evaluated_at)

    @staticmethod
    def _assign_agent_result(
        item: _PreparedOutcome,
        art: _Agentenart,
        ergebnis: ResearchReport | TechnicalAssessment,
    ) -> None:
        if isinstance(ergebnis, ResearchReport):
            item.research = ergebnis
        else:
            item.technical_assessment = ergebnis

    def _unavailable_result(
        self, item: _PreparedOutcome, art: _Agentenart, reason: str
    ) -> ResearchReport | TechnicalAssessment:
        if art == "research":
            return self._unavailable_research(item.evaluated_at, reason)
        return self._unavailable_assessment(item.evaluated_at, reason, item.technical)

    def _bewertung(
        self, item: _PreparedOutcome
    ) -> tuple[ScoreResult | None, ScoreResult | None, RecommendationResult | None]:
        """Beide Scores und die Empfehlungsstufe aus dem, was schon gerechnet
        ist (Doc 09; ADR 0041, ADR 0046).

        **Nur fuer Kandidaten** -- ueber die uebrigen wird nicht berichtet,
        und ein Score fuer eine Aktie, die kein Kandidat ist, beantwortete
        eine Frage, die niemand gestellt hat.

        Ohne Fehlerisolation und ohne Netz: Das ist reine Rechnung auf
        bereits vorliegenden Werten. Eine fehlende Eingabe ergibt eine
        fehlende Komponente, keine Ausnahme -- und unterhalb der
        Mindestabdeckung ``INSUFFICIENT_DATA`` statt einer Zahl.
        """
        if item.result.status is not ScreeningStatus.CANDIDATE:
            return None, None, None
        swing = compute_swing_score(
            item.result,
            backtest=item.backtest,
            assessment=item.technical_assessment,
            analysts=item.analysts,
            parameters=self._scoring_params,
        )
        investment = compute_long_term_score(item.fundamentals, parameters=self._scoring_params)
        empfehlung = derive_recommendation(
            swing=swing,
            investment=investment,
            false_signal_risk=(
                item.technical_assessment.false_signal_risk
                if item.technical_assessment is not None
                else None
            ),
            earnings_status=item.earnings.status if item.earnings is not None else None,
            parameters=self._scoring_params,
        )
        return swing, investment, empfehlung

    def _persist_outcome(self, run: AnalysisRun, item: _PreparedOutcome) -> StockScreeningOutcome:
        swing_score, investment_score, empfehlung = self._bewertung(item)
        outcome = StockScreeningOutcome(
            analysis_run_id=run.id,
            stock=item.stock,
            result=item.result,
            decision_candle_index=item.decision_index,
            evaluated_at=item.evaluated_at,
            signal_rule_version=SIGNAL_RULE_VERSION,
            technical=item.technical,
            fundamentals=item.fundamentals,
            analysts=item.analysts,
            technical_assessment=item.technical_assessment,
            earnings=item.earnings,
            research=item.research,
            backtest=item.backtest,
            swing_score=swing_score,
            investment_score=investment_score,
            recommendation=empfehlung,
        )
        bericht = self._build_report(outcome)
        with self._uow_factory() as uow:
            uow.stocks.add(item.stock)
            uow.screening_results.add(outcome)
            # In derselben Transaktion wie das Screening-Ergebnis: Beide
            # gehoeren zu demselben Lauf und derselben Kerze, eines ohne das
            # andere waere ein halber Datensatz (ADR 0038).
            for backtest_result in item.backtest:
                uow.backtest_results.add(backtest_result, run.id)
            if bericht is not None:
                uow.stock_reports.add(bericht)
            uow.commit()
        return outcome

    def _build_report(self, outcome: StockScreeningOutcome) -> StockReport | None:
        """Der Bericht zu einem Kandidaten -- oder ``None``.

        Nur fuer Kandidaten (ADR 0039): Ueber sie wird berichtet, ueber die
        uebrigen nicht. Ein Lauf ohne Kandidaten hinterlaesst keine Berichte;
        gespeichert wird er trotzdem, in ``analysis_runs``.

        **Ausserhalb der Transaktion und mit eigener Fehlerisolation.** Der
        Bericht ist ein abgeleitetes Artefakt: Er fuehrt zusammen, was schon
        gerechnet ist. Scheitert das Zusammenfuehren -- etwa weil ein
        Teilergebnis ein Feld traegt, das die Dokumenterzeugung nicht kennt --,
        darf das nicht das deterministische Screening-Ergebnis kosten, das
        daneben steht. Es waere genau die Kopplung, die CLAUDE.md ausschliesst.
        """
        if outcome.result.status != ScreeningStatus.CANDIDATE:
            return None
        try:
            bericht = build_report(
                outcome, created_at=datetime.now(UTC), app_version=self._app_version
            )
            # Eine Vorprobe, deren Ergebnis verworfen wird: Das Repository
            # bildet das Dokument selbst, aber erst **innerhalb** der
            # Transaktion -- ein Fehler dabei risse das Screening-Ergebnis mit.
            # Hier faellt er vorher auf und kostet nur den Bericht. Der Preis
            # ist ein zweiter Durchlauf je Kandidat.
            as_document(bericht)
        except Exception:
            _logger.exception(
                "Bericht fuer %s liess sich nicht erzeugen -- das Screening-Ergebnis "
                "bleibt davon unberuehrt",
                outcome.stock.symbol,
            )
            return None
        return bericht

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

    def _evaluate_backtest(
        self, stock: Stock, series: CandleSeries, evaluated_at: datetime
    ) -> tuple[BacktestResult, ...]:
        """Die historische Signalstatistik einer bereits qualifizierten Aktie
        (Doc 10, Paragraph 7; ADR 0038).

        Reine Domain-Rechnung auf der schon geladenen Kerzenserie -- kein
        Netz, keine externe Quelle.

        Gefangen wird ausschliesslich der eine dokumentierte Fall: Im
        Betrachtungsfenster liegt keine Kerze, dann gibt es keine Statistik
        und der Bericht weist Punkt 5 als Luecke aus. Jeder andere Fehler
        waere ein Programmfehler und schlaegt bewusst in die Fehlerisolation
        je Aktie durch, statt still zu verschwinden.
        """
        try:
            return compute_backtest_results(
                series,
                stock_id=stock.id,
                candidate_params=self._candidate_rule_params,
                backtest_params=self._backtest_params,
                signal_rule_version=SIGNAL_RULE_VERSION,
                evaluated_at=evaluated_at,
            )
        except ValueError as error:
            _logger.warning(
                "Keine historische Signalstatistik fuer %s: %s", stock.symbol, error
            )
            return ()

    def _evaluate_fundamentals(self, stock: Stock, price: float) -> FundamentalSnapshot | None:
        """Die Fundamentalkennzahlen einer bereits qualifizierten Aktie.

        Der Ausfall wird **hier** gefangen und nicht im umgebenden
        Fehlerisolations-Block. Der Unterschied ist der ganze Zweck der
        Methode: Dort wuerde eine Ausnahme die Aktie als Ganzes in einen
        ``StockProcessingError`` verschieben und Screening, Chartauswertung
        und Earnings-Filter gleich mit wegwerfen. Ein nicht erreichbares
        EDGAR ist aber ein normaler Betriebszustand (ADR 0035, Entscheidung
        3; Muster ``_evaluate_earnings``).

        Es entsteht dann kein Ersatzwert und kein Platzhalter -- das Feld
        bleibt leer.
        """
        try:
            return self._fundamental_data_provider.fundamentals(stock, price=price)
        except FundamentalDataProviderError as error:
            _logger.warning("Fundamentaldaten fuer %s nicht verfuegbar: %s", stock.symbol, error)
            return None

    def _evaluate_analyst_recommendations(
        self, stock: Stock, evaluated_at: datetime
    ) -> AnalystRecommendations:
        """Die Analystenempfehlungen einer bereits qualifizierten Aktie.

        Fehlerbehandlung nach dem Muster ``_evaluate_earnings``: Ein Ausfall
        des Anbieters wird **hier** abgefangen und nicht im umgebenden
        Fehlerisolations-Block. Dort verschoebe er die Aktie als Ganzes in
        einen ``StockProcessingError`` und wuerfe Screening, Chartauswertung
        und Backtest gleich mit weg.

        Anders als ``_evaluate_fundamentals`` gibt diese Methode nie ``None``
        zurueck: Ein Ausfall ist ``UNAVAILABLE`` mit Grund. "Nicht abgefragt"
        und "abgefragt, keine Antwort" sind verschiedene Aussagen, und der
        Bericht soll sie unterscheiden koennen (ADR 0043).
        """
        try:
            return self._analyst_recommendations_provider.recommendations(stock)
        except AnalystRecommendationsFormatError as error:
            # Der Anbieter war erreichbar, seine Antwort aber nicht lesbar.
            # Ein eigener Grund, weil das etwas anderes ueber die Datenlage
            # sagt als ein Ausfall -- dieselbe Unterscheidung wie beim
            # Earnings-Filter.
            _logger.warning(
                "Analystenempfehlungen fuer %s nicht auswertbar: %s", stock.symbol, error
            )
            return AnalystRecommendations(
                status=AnalystRecommendationStatus.UNAVAILABLE,
                evaluated_at=evaluated_at,
                reason="invalid_data",
            )
        except AnalystRecommendationsProviderError as error:
            _logger.warning(
                "Analystenempfehlungen fuer %s nicht verfuegbar: %s", stock.symbol, error
            )
            return AnalystRecommendations(
                status=AnalystRecommendationStatus.UNAVAILABLE,
                evaluated_at=evaluated_at,
                reason="provider_error",
            )

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
        ``RunAnalysisUseCase._run_agents_concurrently``), keine
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

    def _evaluate_technical_assessment(
        self, stock: Stock, snapshot: TechnicalSnapshot, evaluated_at: datetime
    ) -> TechnicalAssessment:
        """Die KI-Einordnung einer Aktie, nie blockierend.

        Spiegelt ``_evaluate_research`` Zeile fuer Zeile: Faellt der Anbieter
        aus, entsteht ein ``UNAVAILABLE``-Ergebnis statt einer Ausnahme. Der
        deterministische Snapshot ist zu diesem Zeitpunkt laengst fertig
        gerechnet und bleibt vollstaendig erhalten (CLAUDE.md: Analysemodule
        sind entkoppelt).
        """
        try:
            return self._technical_interpreter.interpret(stock, snapshot)
        except TechnicalInterpreterError as exc:
            _logger.warning("Einordnung fuer %s nicht verfuegbar: %s", stock.symbol, exc)
            return self._unavailable_assessment(evaluated_at, "provider_error", snapshot)
        except Exception as exc:
            # Ein Anbieter, der entgegen seinem Vertrag eine rohe Exception
            # wirft, darf das fertige Screening-Ergebnis nicht mitreissen
            # (ADR 0023, derselbe Befund beim Research Agent).
            _logger.exception(
                "Anbieter des Technical Agent hat fuer %s eine unerwartete Ausnahme geworfen: %s",
                stock.symbol,
                exc,
            )
            return self._unavailable_assessment(
                evaluated_at, "provider_contract_violation", snapshot
            )

    def _unavailable_assessment(
        self,
        evaluated_at: datetime,
        reason: str,
        snapshot: TechnicalSnapshot | None = None,
    ) -> TechnicalAssessment:
        return TechnicalAssessment(
            status=TechnicalAssessmentStatus.UNAVAILABLE,
            evaluated_at=evaluated_at,
            model=None,
            prompt_version=None,
            interpreted_analysis_version=(None if snapshot is None else snapshot.analysis_version),
            reason=reason,
        )

    def _unavailable_research(self, evaluated_at: datetime, reason: str) -> ResearchReport:
        return ResearchReport(
            status=ResearchStatus.UNAVAILABLE,
            evaluated_at=evaluated_at,
            model=None,
            prompt_version=None,
            reason=reason,
        )
