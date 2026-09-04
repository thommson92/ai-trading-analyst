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
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from ai_trading_analyst.application.run_analysis import RunAnalysisUseCase
from ai_trading_analyst.domain.analysis import MarketDataProviderError, RunStatus, Stock
from ai_trading_analyst.domain.backtesting import BacktestParameters
from ai_trading_analyst.domain.earnings import EarningsFilterParameters, EarningsFilterStatus
from ai_trading_analyst.domain.options import OptionsParameters
from ai_trading_analyst.domain.research import ResearchStatus
from ai_trading_analyst.domain.scoring import ScoringParameters
from ai_trading_analyst.domain.screening import (
    CandidateRuleParameters,
    CandleSeries,
    ScreeningStatus,
)
from ai_trading_analyst.domain.technical import (
    TechnicalAnalysisParameters,
    TechnicalAssessmentStatus,
    TechnicalStatus,
)
from ai_trading_analyst.infrastructure.fixtures.analyst_recommendations_provider import (
    FixtureAnalystRecommendationsProvider,
)
from ai_trading_analyst.infrastructure.fixtures.earnings_provider import FixtureEarningsProvider
from ai_trading_analyst.infrastructure.fixtures.fundamental_provider import (
    FixtureFundamentalDataProvider,
)
from ai_trading_analyst.infrastructure.fixtures.market_data_provider import (
    FixtureMarketDataProvider,
)
from ai_trading_analyst.infrastructure.fixtures.options_provider import FixtureOptionsProvider
from ai_trading_analyst.infrastructure.fixtures.research_provider import FixtureResearchProvider
from ai_trading_analyst.infrastructure.fixtures.technical_interpreter import (
    FixtureTechnicalInterpreter,
)
from ai_trading_analyst.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork

UowFactory = Callable[[], SqlAlchemyUnitOfWork]

_PARAMS = CandidateRuleParameters(
    required_crossing_signals=2, signal_lookback_previous_candles=5, warmup_candles=250
)
_EARNINGS_PARAMS = EarningsFilterParameters(configured_exclusion_candles=20, candles_per_day=2)
# Deckungsgleich mit dem Entscheidungskerzen-Datum der Fixture-Kerzenserie
# (_EPOCH + 258 * 195min in infrastructure/fixtures/market_data_provider.py)
# -- damit die Kerzenzaehlung des Earnings-Filters mit dem festen
# Fixture-Kalender uebereinstimmt statt mit dem realen Tagesdatum.
_FIXTURE_DECISION_DATE = date(2024, 2, 6)

_TECHNICAL_PARAMS = TechnicalAnalysisParameters()
"""Bewusst die Voreinstellungen aus ADR 0025 und keine verkleinerten
Fenster: Die Fixture-Serie ist lang genug, und damit prueft dieser Lauf
zugleich, dass die ausgelieferten Werte in sich stimmig sind."""

_BACKTEST_PARAMS = BacktestParameters(
    horizons=(5, 10, 20),
    minimum_sample_size=10,
    normal_confidence_sample_size=30,
    history_years=5,
)
"""Aus demselben Grund die ausgelieferten Werte aus ``config/default.yaml``."""


class _AlwaysFailingMarketDataProvider:
    def list_stocks(self) -> tuple[Stock, ...]:
        raise MarketDataProviderError("Marktdatenanbieter vollstaendig nicht erreichbar")

    def get_candle_series(self, stock: Stock) -> CandleSeries:  # pragma: no cover - nie erreicht
        raise AssertionError("get_candle_series wird nie aufgerufen, wenn list_stocks scheitert")


def test_vollstaendiger_fixture_basierter_lauf_ist_teilweise_erfolgreich(
    uow_factory: UowFactory, scoring_params: ScoringParameters
) -> None:
    earnings_provider = FixtureEarningsProvider(reference_date=lambda: _FIXTURE_DECISION_DATE)
    use_case = RunAnalysisUseCase(
        FixtureMarketDataProvider(),
        earnings_provider,
        FixtureResearchProvider(),
        FixtureTechnicalInterpreter(),
        FixtureFundamentalDataProvider(),
        FixtureAnalystRecommendationsProvider(),
        FixtureOptionsProvider(OptionsParameters()),
        uow_factory,
        _PARAMS,
        _EARNINGS_PARAMS,
        _TECHNICAL_PARAMS,
        _BACKTEST_PARAMS,
        scoring_params,
    )

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

    earnings_by_symbol = {o.stock.symbol: o.earnings for o in summary.outcomes}
    fixcand_earnings = earnings_by_symbol["FIXCAND"]
    assert fixcand_earnings is not None
    assert fixcand_earnings.status is EarningsFilterStatus.EARNINGS_CLEAR
    assert fixcand_earnings.source == "fixture"
    assert earnings_by_symbol["FIXNOCAND"] is None
    assert earnings_by_symbol["FIXINCOMPLETE"] is None

    # Die Chartauswertung laeuft fuer jeden Kandidaten, unabhaengig vom
    # Earnings-Filter und vom Research Agent (Doc 10, Paragraph 6.8).
    technical_by_symbol = {o.stock.symbol: o.technical for o in summary.outcomes}
    fixcand_technical = technical_by_symbol["FIXCAND"]
    assert fixcand_technical is not None
    assert fixcand_technical.status is TechnicalStatus.COMPLETED
    assert fixcand_technical.close is not None
    assert fixcand_technical.atr is not None
    assert technical_by_symbol["FIXNOCAND"] is None
    assert technical_by_symbol["FIXINCOMPLETE"] is None

    # Die KI-Einordnung haengt am Snapshot und an nichts sonst (ADR 0026) --
    # anders als Research, das zusaetzlich EARNINGS_CLEAR verlangt.
    assessment_by_symbol = {o.stock.symbol: o.technical_assessment for o in summary.outcomes}
    fixcand_assessment = assessment_by_symbol["FIXCAND"]
    assert fixcand_assessment is not None
    assert fixcand_assessment.status is TechnicalAssessmentStatus.COMPLETED
    assert fixcand_assessment.interpreted_analysis_version == fixcand_technical.analysis_version
    assert assessment_by_symbol["FIXNOCAND"] is None
    assert assessment_by_symbol["FIXINCOMPLETE"] is None

    # Research laeuft nur, wenn zusaetzlich EARNINGS_CLEAR ist (Doc 10, Paragraph 6.7).
    research_by_symbol = {o.stock.symbol: o.research for o in summary.outcomes}
    fixcand_research = research_by_symbol["FIXCAND"]
    assert fixcand_research is not None
    assert fixcand_research.status is ResearchStatus.COMPLETED
    assert fixcand_research.citations
    assert research_by_symbol["FIXNOCAND"] is None
    assert research_by_symbol["FIXINCOMPLETE"] is None

    with uow_factory() as uow:
        persisted_outcomes = uow.screening_results.list_for_run(summary.run.id)
        persisted_errors = uow.processing_errors.list_for_run(summary.run.id)
        persisted_run = uow.analysis_runs.get(summary.run.id)

    assert len(persisted_outcomes) == 3
    assert len(persisted_errors) == 1
    assert persisted_run == summary.run

    persisted_fixcand = next(o for o in persisted_outcomes if o.stock.symbol == "FIXCAND")
    assert persisted_fixcand.technical == fixcand_technical
    assert persisted_fixcand.technical_assessment == fixcand_assessment
    assert persisted_fixcand.earnings == fixcand_earnings
    assert persisted_fixcand.research == fixcand_research


def test_vollstaendiges_scheitern_vor_screeningbeginn_wird_nicht_teilweise_persistiert(
    uow_factory: UowFactory, scoring_params: ScoringParameters
) -> None:
    use_case = RunAnalysisUseCase(
        _AlwaysFailingMarketDataProvider(),
        FixtureEarningsProvider(),
        FixtureResearchProvider(),
        FixtureTechnicalInterpreter(),
        FixtureFundamentalDataProvider(),
        FixtureAnalystRecommendationsProvider(),
        FixtureOptionsProvider(OptionsParameters()),
        uow_factory,
        _PARAMS,
        _EARNINGS_PARAMS,
        _TECHNICAL_PARAMS,
        _BACKTEST_PARAMS,
        scoring_params,
    )

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


def test_der_lauf_legt_die_abgerufenen_rohnotierungen_ab(
    uow_factory: UowFactory,
    scoring_params: ScoringParameters,
    session_factory: sessionmaker[Session],
) -> None:
    """Die Kette vom Abruf bis in die Tabelle, an einem Stueck (ADR 0058,
    Festlegung 1).

    Die Domaenen- und Repository-Tests decken die beiden Enden ab; dieser
    deckt die Verdrahtung dazwischen. Ohne ihn bliebe eine Umstellung im
    Application-Layer, die ``options`` nicht mehr durchreicht, unbemerkt --
    alle uebrigen Zusicherungen ueber die Optionsanalyse blieben gruen, weil
    sie an den Spalten der Elternzeile haengen und nicht an dieser Tabelle.

    Geprueft wird gegen SQL und nicht gegen das Domaenenobjekt: Die
    Notierungen werden bewusst nicht zurueckgelesen.
    """
    use_case = RunAnalysisUseCase(
        FixtureMarketDataProvider(),
        FixtureEarningsProvider(reference_date=lambda: _FIXTURE_DECISION_DATE),
        FixtureResearchProvider(),
        FixtureTechnicalInterpreter(),
        FixtureFundamentalDataProvider(),
        FixtureAnalystRecommendationsProvider(),
        FixtureOptionsProvider(OptionsParameters()),
        uow_factory,
        _PARAMS,
        _EARNINGS_PARAMS,
        _TECHNICAL_PARAMS,
        _BACKTEST_PARAMS,
        scoring_params,
    )

    summary = use_case.execute()

    fixcand = next(o for o in summary.outcomes if o.stock.symbol == "FIXCAND")
    assert fixcand.options is not None

    with session_factory() as session:
        zeilen = session.execute(
            text(
                "SELECT q.strike FROM option_quotes q "
                "JOIN screening_results r ON r.id = q.screening_result_id "
                "JOIN stocks s ON s.id = r.stock_id "
                "WHERE s.symbol = 'FIXCAND' ORDER BY q.position"
            )
        ).scalars().all()

    # Mehr Notierungen als Vorschlaege -- das ist der ganze Punkt der
    # Festlegung: Der Rest verschwand bisher nach der Auswertung.
    assert len(zeilen) > len(fixcand.options.strategies)
    assert [float(strike) for strike in zeilen] == [
        quote.strike for quote in fixcand.options.quotes
    ]

    # Ein Titel ohne Kandidatenstatus bekommt keine Optionsanalyse und
    # deshalb auch keine Notierungen.
    with session_factory() as session:
        ohne = session.execute(
            text(
                "SELECT count(*) FROM option_quotes q "
                "JOIN screening_results r ON r.id = q.screening_result_id "
                "JOIN stocks s ON s.id = r.stock_id WHERE s.symbol = 'FIXNOCAND'"
            )
        ).scalar_one()
    assert ohne == 0
