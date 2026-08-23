"""Repository- und UnitOfWork-Tests gegen echtes PostgreSQL."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.exc import IntegrityError

from ai_trading_analyst.domain.analysis import (
    RunStatus,
    Stock,
    StockProcessingError,
    StockScreeningOutcome,
)
from ai_trading_analyst.domain.backtesting import (
    BacktestConfidence,
    BacktestResult,
    HorizonMetrics,
)
from ai_trading_analyst.domain.earnings import EarningsFilterResult, EarningsFilterStatus
from ai_trading_analyst.domain.research import (
    Citation,
    ResearchCoverage,
    ResearchEvidence,
    ResearchReport,
    ResearchStatus,
    SourceLicenseClass,
    SourceRank,
)
from ai_trading_analyst.domain.screening import (
    SIGNAL_RULE_VERSION,
    IntradayBar,
    ScreeningResult,
    ScreeningStatus,
    SignalEvent,
    SignalType,
)
from ai_trading_analyst.domain.technical import (
    TECHNICAL_ANALYSIS_VERSION,
    BreakoutQuality,
    FalseSignalRisk,
    MomentumState,
    PriceZone,
    RiskRewardRating,
    SwingEntryPlausibility,
    TechnicalAnalysisParameters,
    TechnicalAssessment,
    TechnicalAssessmentStatus,
    TechnicalSnapshot,
    TechnicalStatus,
    TrendDirection,
    TrendStrength,
    ZoneKind,
    ZoneStrength,
)
from ai_trading_analyst.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from tests.integration.conftest import make_outcome, make_run, make_stock

UowFactory = Callable[[], SqlAlchemyUnitOfWork]


class TestStockRepository:
    def test_add_is_idempotent_fuer_dasselbe_symbol(self, uow_factory: UowFactory) -> None:
        stock = make_stock("IDEMP")
        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.stocks.add(stock)
            uow.commit()

        with uow_factory() as uow:
            assert len(uow.stocks.list_all()) == 1
            assert uow.stocks.get_by_symbol("IDEMP") == stock

    def test_unbekanntes_symbol_liefert_none(self, uow_factory: UowFactory) -> None:
        with uow_factory() as uow:
            assert uow.stocks.get_by_symbol("NICHT_VORHANDEN") is None

    def test_add_ist_idempotent_auch_bei_abweichender_id_fuer_dasselbe_symbol(
        self, uow_factory: UowFactory
    ) -> None:
        """Ein Marktdatenanbieter, der fuer ein bereits bekanntes Symbol eine
        neue id liefert, darf den bestehenden Datensatz nicht per
        IntegrityError zum Absturz bringen -- Idempotenz gilt nach Symbol,
        nicht nach id (siehe SqlAlchemyStockRepository.add)."""
        original = make_stock("SAMESYMBOL")
        with_different_id = Stock(
            id=make_stock("EIN_ANDERES_SYMBOL").id, symbol="SAMESYMBOL", exchange="NYSE"
        )

        with uow_factory() as uow:
            uow.stocks.add(original)
            uow.commit()

        with uow_factory() as uow:
            uow.stocks.add(with_different_id)
            uow.commit()

        with uow_factory() as uow:
            assert len(uow.stocks.list_all()) == 1
            assert uow.stocks.get_by_symbol("SAMESYMBOL") == original


class TestAnalysisRunRepository:
    def test_roundtrip_add_get_update(self, uow_factory: UowFactory) -> None:
        run = make_run(status=RunStatus.RUNNING)
        with uow_factory() as uow:
            uow.analysis_runs.add(run)
            uow.commit()

        with uow_factory() as uow:
            fetched = uow.analysis_runs.get(run.id)
        assert fetched == run

        run.status = RunStatus.COMPLETED
        run.candidates_found = 3
        with uow_factory() as uow:
            uow.analysis_runs.update(run)
            uow.commit()

        with uow_factory() as uow:
            updated = uow.analysis_runs.get(run.id)
        assert updated is not None
        assert updated.status == RunStatus.COMPLETED
        assert updated.candidates_found == 3

    def test_erneute_abfrage_eines_abgeschlossenen_laufs_liefert_konsistente_daten(
        self, uow_factory: UowFactory
    ) -> None:
        run = make_run(status=RunStatus.COMPLETED)
        with uow_factory() as uow:
            uow.analysis_runs.add(run)
            uow.commit()

        with uow_factory() as uow:
            first = uow.analysis_runs.get(run.id)
        with uow_factory() as uow:
            second = uow.analysis_runs.get(run.id)

        assert first == second == run

    def test_update_eines_unbekannten_laufs_schlaegt_eindeutig_fehl(
        self, uow_factory: UowFactory
    ) -> None:
        run = make_run()
        with pytest.raises(LookupError):
            with uow_factory() as uow:
                uow.analysis_runs.update(run)
                uow.commit()


class TestScreeningResultRepository:
    @pytest.mark.parametrize(
        "status",
        [
            ScreeningStatus.CANDIDATE,
            ScreeningStatus.NOT_CANDIDATE,
            ScreeningStatus.UNKNOWN_DATA_INCOMPLETE,
        ],
    )
    def test_alle_drei_screening_status_koennen_gespeichert_und_gelesen_werden(
        self, uow_factory: UowFactory, status: ScreeningStatus
    ) -> None:
        stock = make_stock(f"STATUS-{status.value}")
        run = make_run()
        outcome = make_outcome(stock, status, analysis_run_id=run.id)

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()

        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)
        assert persisted.result.status == status
        assert persisted.stock == stock
        assert persisted.earnings is None

    def test_earnings_ergebnis_wird_mitgespeichert(self, uow_factory: UowFactory) -> None:
        stock = make_stock("WITHEARNINGS")
        run = make_run()
        earnings = EarningsFilterResult(
            status=EarningsFilterStatus.EARNINGS_EXCLUDED,
            evaluated_at=datetime.now(UTC),
            next_earnings_date=date(2026, 9, 1),
            candles_until_earnings=6,
            source="finnhub",
        )
        outcome = StockScreeningOutcome(
            analysis_run_id=run.id,
            stock=stock,
            result=ScreeningResult(status=ScreeningStatus.CANDIDATE),
            decision_candle_index=258,
            evaluated_at=datetime.now(UTC),
            signal_rule_version=SIGNAL_RULE_VERSION,
            earnings=earnings,
        )

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()

        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)
        assert persisted.earnings == earnings

    def test_unknown_earnings_ergebnis_mit_grund_wird_mitgespeichert(
        self, uow_factory: UowFactory
    ) -> None:
        stock = make_stock("WITHUNKNOWNEARNINGS")
        run = make_run()
        earnings = EarningsFilterResult(
            status=EarningsFilterStatus.UNKNOWN,
            evaluated_at=datetime.now(UTC),
            reason="no_coverage",
        )
        outcome = StockScreeningOutcome(
            analysis_run_id=run.id,
            stock=stock,
            result=ScreeningResult(status=ScreeningStatus.CANDIDATE),
            decision_candle_index=258,
            evaluated_at=datetime.now(UTC),
            signal_rule_version=SIGNAL_RULE_VERSION,
            earnings=earnings,
        )

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()

        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)
        assert persisted.earnings == earnings
        assert persisted.earnings is not None
        assert persisted.earnings.next_earnings_date is None

    def test_signal_events_werden_mitgespeichert(self, uow_factory: UowFactory) -> None:
        stock = make_stock("WITHEVENTS")
        run = make_run()
        events = (
            SignalEvent(signal_type=SignalType.RSI_CROSS, candle_index=254),
            SignalEvent(signal_type=SignalType.PRICE_EMA20_BREAKOUT, candle_index=257),
        )
        outcome = StockScreeningOutcome(
            analysis_run_id=run.id,
            stock=stock,
            result=ScreeningResult(
                status=ScreeningStatus.CANDIDATE,
                fired_signal_types=frozenset({event.signal_type for event in events}),
                signal_events=events,
            ),
            decision_candle_index=258,
            evaluated_at=datetime.now(UTC),
            signal_rule_version=SIGNAL_RULE_VERSION,
        )

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()

        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)
        assert persisted.result.signal_events == events
        assert persisted.result.fired_signal_types == frozenset(
            {SignalType.RSI_CROSS, SignalType.PRICE_EMA20_BREAKOUT}
        )

    def test_chartauswertung_mit_zonen_wird_mitgespeichert(self, uow_factory: UowFactory) -> None:
        stock = make_stock("WITHTECHNICAL")
        run = make_run()
        bestaetigt = datetime.now(UTC)
        zones = (
            PriceZone(
                lower=98.0,
                upper=101.0,
                kind=ZoneKind.PRICE_INSIDE,
                strength=ZoneStrength.STRONG,
                touch_count=6,
                last_confirmed_at=bestaetigt,
                distance_pct=0.0,
                pivot_count=4,
            ),
            PriceZone(
                lower=104.0,
                upper=107.0,
                kind=ZoneKind.RESISTANCE,
                strength=ZoneStrength.MODERATE,
                touch_count=3,
                last_confirmed_at=bestaetigt - timedelta(days=2),
                distance_pct=0.04,
                pivot_count=2,
            ),
            PriceZone(
                lower=88.0,
                upper=91.0,
                kind=ZoneKind.SUPPORT,
                strength=ZoneStrength.WEAK,
                touch_count=2,
                last_confirmed_at=bestaetigt - timedelta(days=9),
                distance_pct=0.09,
                pivot_count=2,
            ),
        )
        technical = TechnicalSnapshot(
            status=TechnicalStatus.COMPLETED,
            evaluated_at=datetime.now(UTC),
            analysis_version=TECHNICAL_ANALYSIS_VERSION,
            parameters=TechnicalAnalysisParameters(zone_tolerance_pct=0.02).as_mapping(),
            candle_timestamp=datetime.now(UTC) - timedelta(minutes=195),
            close=100.0,
            trend=TrendDirection.UP,
            rsi=61.5,
            ema5=99.5,
            ema20=97.25,
            distance_to_ema5_pct=0.005,
            distance_to_ema20_pct=0.028,
            atr=2.4,
            atr_pct=0.024,
            recent_high=107.0,
            recent_high_at=bestaetigt - timedelta(days=2),
            recent_low=88.5,
            recent_low_at=bestaetigt - timedelta(days=9),
            zones=zones,
        )
        outcome = StockScreeningOutcome(
            analysis_run_id=run.id,
            stock=stock,
            result=ScreeningResult(status=ScreeningStatus.CANDIDATE),
            decision_candle_index=258,
            evaluated_at=datetime.now(UTC),
            signal_rule_version=SIGNAL_RULE_VERSION,
            technical=technical,
        )

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()

        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)

        assert persisted.technical == technical
        assert persisted.technical is not None
        assert persisted.technical.parameters is not None
        # Die Parameter machen erst nachvollziehbar, nach welchem Massstab
        # gerechnet wurde -- Doc 14 fordert dazu auf, sie nachzuziehen.
        assert persisted.technical.parameters["zone_tolerance_pct"] == 0.02

    def test_zonenreihenfolge_ueberlebt_die_datenbank(self, uow_factory: UowFactory) -> None:
        """Die Sortierung nach Abstand zum Kurs ist Teil der Aussage.

        Anders als bei den Zitaten hat die Zonen-Relationship deshalb ein
        ``order_by`` -- ohne das gaebe die Datenbank die Zonen in
        unbestimmter Reihenfolge zurueck, und die naechstgelegene Zone waere
        beim Wiedereinlesen nicht mehr die erste.
        """
        stock = make_stock("ZONEORDER")
        run = make_run()
        bestaetigt = datetime.now(UTC)
        abstaende = (0.0, 0.02, 0.05, 0.11)
        zones = tuple(
            PriceZone(
                lower=100.0 - index,
                upper=101.0 - index,
                kind=ZoneKind.SUPPORT,
                strength=ZoneStrength.WEAK,
                touch_count=2,
                last_confirmed_at=bestaetigt,
                distance_pct=abstand,
                pivot_count=2,
            )
            for index, abstand in enumerate(abstaende)
        )
        outcome = StockScreeningOutcome(
            analysis_run_id=run.id,
            stock=stock,
            result=ScreeningResult(status=ScreeningStatus.CANDIDATE),
            decision_candle_index=258,
            evaluated_at=datetime.now(UTC),
            signal_rule_version=SIGNAL_RULE_VERSION,
            technical=TechnicalSnapshot(
                status=TechnicalStatus.COMPLETED,
                evaluated_at=datetime.now(UTC),
                close=100.0,
                zones=zones,
            ),
        )

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()

        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)

        assert persisted.technical is not None
        assert tuple(zone.distance_pct for zone in persisted.technical.zones) == abstaende

    def test_unvollstaendige_chartauswertung_wird_ohne_ersatzwerte_gespeichert(
        self, uow_factory: UowFactory
    ) -> None:
        """INSUFFICIENT_DATA hat weder Kurs noch Zonen -- die Spalten bleiben
        NULL, statt beim Wiedereinlesen einen gerechneten Wert vorzutaeuschen."""
        stock = make_stock("TECHNICALINSUFFICIENT")
        run = make_run()
        technical = TechnicalSnapshot(
            status=TechnicalStatus.INSUFFICIENT_DATA,
            evaluated_at=datetime.now(UTC),
            reason="too_few_candles",
        )
        outcome = StockScreeningOutcome(
            analysis_run_id=run.id,
            stock=stock,
            result=ScreeningResult(status=ScreeningStatus.CANDIDATE),
            decision_candle_index=12,
            evaluated_at=datetime.now(UTC),
            signal_rule_version=SIGNAL_RULE_VERSION,
            technical=technical,
        )

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()

        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)

        assert persisted.technical == technical
        assert persisted.technical is not None
        assert persisted.technical.close is None
        assert persisted.technical.zones == ()

    def test_ergebnis_ohne_chartauswertung_bleibt_ohne(self, uow_factory: UowFactory) -> None:
        """Ein Nichtkandidat wird nicht ausgewertet -- und liest sich als
        ``None`` zurueck, nicht als leere Auswertung."""
        stock = make_stock("NOTECHNICAL")
        run = make_run()
        outcome = make_outcome(stock, ScreeningStatus.NOT_CANDIDATE, analysis_run_id=run.id)

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()

        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)

        assert persisted.technical is None

    def test_research_bericht_mit_zitaten_wird_mitgespeichert(
        self, uow_factory: UowFactory
    ) -> None:
        stock = make_stock("WITHRESEARCH")
        run = make_run()
        citations = (
            Citation(
                url="https://sec.gov/filing",
                title="SEC-Filing",
                retrieved_at=datetime.now(UTC),
                cited_text="ein zitierter Ausschnitt",
                license_class=SourceLicenseClass.PRIMARY_SOURCE,
                transformation="zusammengefasst",
                source_rank=SourceRank.REGULATORY,
                source_age="3 days ago",
            ),
            Citation(
                url="https://example.com/news",
                title="Nachrichtenartikel",
                retrieved_at=datetime.now(UTC),
                cited_text=None,
                license_class=SourceLicenseClass.UNKNOWN,
                transformation="aggregiert aus mehreren Quellen",
                source_rank=SourceRank.UNRANKED,
                source_age=None,
            ),
        )
        research = ResearchReport(
            status=ResearchStatus.COMPLETED,
            evaluated_at=datetime.now(UTC),
            model="claude-sonnet-5",
            prompt_version="research-v1",
            summary="Zusammenfassung",
            positive_factors=("Faktor A",),
            negative_factors=("Faktor B",),
            risks=("Risiko A",),
            confidence=0.7,
            citations=citations,
            coverage=ResearchCoverage.LIMITED,
            evidence=ResearchEvidence(
                distinct_sources=4,
                successful_fetches=1,
                rejected_tool_calls=2,
                dropped_citations=2,
            ),
        )
        outcome = StockScreeningOutcome(
            analysis_run_id=run.id,
            stock=stock,
            result=ScreeningResult(status=ScreeningStatus.CANDIDATE),
            decision_candle_index=258,
            evaluated_at=datetime.now(UTC),
            signal_rule_version=SIGNAL_RULE_VERSION,
            research=research,
        )

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()

        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)
        assert persisted.research is not None
        # Die Zitat-Relationship hat kein ``order_by`` (wie ``signal_events``),
        # die Lesereihenfolge ist also datenbankabhaengig. Geprueft wird
        # deshalb die Menge der Zitate, nicht ihre Reihenfolge -- sonst haenge
        # der Test an einer Zusage, die das Schema nicht gibt.
        assert set(persisted.research.citations) == set(citations)
        assert persisted.research == replace(research, citations=persisted.research.citations)
        assert len(persisted.research.citations) == 2
        # Rang, Quellenalter und die Abdeckungszahlen ueberstehen den
        # Round-Trip (ADR 0029) -- ohne sie waere die Abdeckung nach dem
        # Neuladen eine Stufe ohne Begruendung.
        assert persisted.research.coverage is ResearchCoverage.LIMITED
        assert persisted.research.evidence == research.evidence
        nach_url = {citation.url: citation for citation in persisted.research.citations}
        assert nach_url["https://sec.gov/filing"].source_rank is SourceRank.REGULATORY
        assert nach_url["https://sec.gov/filing"].source_age == "3 days ago"
        assert nach_url["https://example.com/news"].source_age is None

    def test_ein_bericht_vor_adr_0029_behauptet_keine_abdeckung(
        self, uow_factory: UowFactory
    ) -> None:
        """Berichte aus der Zeit vor den neuen Spalten liegen mit NULL in der
        Datenbank. Sie bekommen ``None`` statt Nullen -- ein alter Bericht
        weiss nichts ueber seine Abdeckung und soll das nicht behaupten."""
        stock = make_stock("PREADR29")
        run = make_run()
        research = ResearchReport(
            status=ResearchStatus.COMPLETED,
            evaluated_at=datetime.now(UTC),
            model="claude-sonnet-5",
            prompt_version="research-v1",
            summary="Zusammenfassung",
            confidence=0.7,
            citations=(
                Citation(
                    url="https://sec.gov/altes-filing",
                    title="SEC-Filing",
                    retrieved_at=datetime.now(UTC),
                    cited_text=None,
                    license_class=SourceLicenseClass.PRIMARY_SOURCE,
                    transformation="zusammengefasst",
                ),
            ),
        )
        outcome = StockScreeningOutcome(
            analysis_run_id=run.id,
            stock=stock,
            result=ScreeningResult(status=ScreeningStatus.CANDIDATE),
            decision_candle_index=258,
            evaluated_at=datetime.now(UTC),
            signal_rule_version=SIGNAL_RULE_VERSION,
            research=research,
        )

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()

        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)

        assert persisted.research is not None
        assert persisted.research.coverage is None
        assert persisted.research.evidence is None
        assert persisted.research.citations[0].source_rank is SourceRank.UNRANKED

    def test_research_bericht_ohne_ergebnis_wird_mitgespeichert(
        self, uow_factory: UowFactory
    ) -> None:
        """UNAVAILABLE hat weder Modell noch Zitate -- beide Spalten bleiben NULL."""
        stock = make_stock("WITHUNAVAILABLERESEARCH")
        run = make_run()
        research = ResearchReport(
            status=ResearchStatus.UNAVAILABLE,
            evaluated_at=datetime.now(UTC),
            model=None,
            prompt_version=None,
            reason="provider_error",
        )
        outcome = StockScreeningOutcome(
            analysis_run_id=run.id,
            stock=stock,
            result=ScreeningResult(status=ScreeningStatus.CANDIDATE),
            decision_candle_index=258,
            evaluated_at=datetime.now(UTC),
            signal_rule_version=SIGNAL_RULE_VERSION,
            research=research,
        )

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()

        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)
        assert persisted.research == research
        assert persisted.research is not None
        assert persisted.research.model is None
        assert persisted.research.citations == ()

    def test_zweites_ergebnis_fuer_dieselbe_aktie_im_selben_lauf_wird_abgelehnt(
        self, uow_factory: UowFactory
    ) -> None:
        """Abgeschlossene Screening-Ergebnisse werden nicht stillschweigend
        ueberschrieben -- die Datenbank erzwingt das zusaetzlich zur Anwendungslogik."""
        stock = make_stock("NOOVERWRITE")
        run = make_run()
        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(
                make_outcome(stock, ScreeningStatus.NOT_CANDIDATE, analysis_run_id=run.id)
            )
            uow.commit()

        with pytest.raises(IntegrityError):
            with uow_factory() as uow:
                uow.screening_results.add(
                    make_outcome(stock, ScreeningStatus.CANDIDATE, analysis_run_id=run.id)
                )
                uow.commit()


class TestBacktestResultRepository:
    def test_ein_ergebnis_mit_mehreren_horizonten_uebersteht_den_rundlauf(
        self, uow_factory: UowFactory
    ) -> None:
        stock = make_stock("BACKTESTED")
        combination = frozenset({SignalType.RSI_CROSS, SignalType.EMA5_EMA20_CROSS})
        evaluated_at = datetime.now(UTC)
        result = BacktestResult(
            stock_id=stock.id,
            signal_types=combination,
            signal_rule_version=SIGNAL_RULE_VERSION,
            evaluated_at=evaluated_at,
            history_start=datetime(2020, 1, 2, tzinfo=UTC),
            history_end=datetime(2025, 1, 2, tzinfo=UTC),
            horizons=(
                HorizonMetrics(
                    horizon=5,
                    raw_event_count=12,
                    deduplicated_event_count=9,
                    hit_rate=0.667,
                    mean_return=0.021,
                    median_return=0.018,
                    max_loss=-0.05,
                    drawdown=0.07,
                    held_above_entry_rate=0.55,
                    confidence=BacktestConfidence.NORMAL,
                ),
                HorizonMetrics(
                    horizon=20,
                    raw_event_count=12,
                    deduplicated_event_count=3,
                    hit_rate=None,
                    mean_return=None,
                    median_return=None,
                    max_loss=None,
                    drawdown=None,
                    held_above_entry_rate=None,
                    confidence=BacktestConfidence.INSUFFICIENT_DATA,
                ),
            ),
        )

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.backtest_results.add(result)
            uow.commit()

        with uow_factory() as uow:
            (persisted,) = uow.backtest_results.list_for_stock(stock.id)

        assert persisted.signal_types == combination
        assert persisted.evaluated_at == evaluated_at
        assert {h.horizon for h in persisted.horizons} == {5, 20}
        by_horizon = {h.horizon: h for h in persisted.horizons}
        assert by_horizon[5] == result.horizons[0]
        assert by_horizon[20] == result.horizons[1]

    def test_ein_anderes_symbol_bekommt_keine_fremden_ergebnisse(
        self, uow_factory: UowFactory
    ) -> None:
        stock_a, stock_b = make_stock("BTA"), make_stock("BTB")
        combination = frozenset({SignalType.RSI_CROSS, SignalType.PRICE_EMA20_BREAKOUT})
        horizon = HorizonMetrics(
            horizon=5,
            raw_event_count=1,
            deduplicated_event_count=1,
            hit_rate=1.0,
            mean_return=0.01,
            median_return=0.01,
            max_loss=0.0,
            drawdown=0.0,
            held_above_entry_rate=1.0,
            confidence=BacktestConfidence.LOW_SAMPLE,
        )
        result_a = BacktestResult(
            stock_id=stock_a.id,
            signal_types=combination,
            signal_rule_version=SIGNAL_RULE_VERSION,
            evaluated_at=datetime.now(UTC),
            history_start=datetime(2020, 1, 2, tzinfo=UTC),
            history_end=datetime(2025, 1, 2, tzinfo=UTC),
            horizons=(horizon,),
        )

        with uow_factory() as uow:
            uow.stocks.add(stock_a)
            uow.stocks.add(stock_b)
            uow.backtest_results.add(result_a)
            uow.commit()

        with uow_factory() as uow:
            assert uow.backtest_results.list_for_stock(stock_b.id) == ()


class TestProcessingErrorRepository:
    def test_fehlerisolation_zwischen_zwei_aktien_bleibt_unabhaengig_nachvollziehbar(
        self, uow_factory: UowFactory
    ) -> None:
        run = make_run()
        stock_ok = make_stock("OK1")
        with uow_factory() as uow:
            uow.analysis_runs.add(run)
            uow.stocks.add(stock_ok)
            uow.screening_results.add(
                make_outcome(stock_ok, ScreeningStatus.NOT_CANDIDATE, analysis_run_id=run.id)
            )
            uow.processing_errors.add(
                StockProcessingError(
                    analysis_run_id=run.id,
                    stock_symbol="BROKEN1",
                    message="Simulierter Fehler",
                    occurred_at=datetime.now(UTC),
                )
            )
            uow.commit()

        with uow_factory() as uow:
            outcomes = uow.screening_results.list_for_run(run.id)
            errors = uow.processing_errors.list_for_run(run.id)

        assert len(outcomes) == 1
        assert outcomes[0].stock.symbol == "OK1"
        assert len(errors) == 1
        assert errors[0].stock_symbol == "BROKEN1"


class TestTransaktionsverhalten:
    def test_nicht_committete_aenderungen_werden_beim_normalen_verlassen_verworfen(
        self, uow_factory: UowFactory
    ) -> None:
        stock = make_stock("NOCOMMIT")
        with uow_factory() as uow:
            uow.stocks.add(stock)
            # kein uow.commit()

        with uow_factory() as uow:
            assert uow.stocks.get_by_symbol("NOCOMMIT") is None

    def test_eine_exception_rollt_alle_ausstehenden_aenderungen_zurueck(
        self, uow_factory: UowFactory
    ) -> None:
        stock = make_stock("ROLLBACK")

        class _SimulatedFailureError(Exception):
            pass

        with pytest.raises(_SimulatedFailureError):
            with uow_factory() as uow:
                uow.stocks.add(stock)
                raise _SimulatedFailureError("simulierter Fehler mitten in der Transaktion")

        with uow_factory() as uow:
            assert uow.stocks.get_by_symbol("ROLLBACK") is None

    def test_explizites_rollback_verwirft_aenderungen_ohne_exception(
        self, uow_factory: UowFactory
    ) -> None:
        stock = make_stock("EXPLICITROLLBACK")
        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.rollback()

        with uow_factory() as uow:
            assert uow.stocks.get_by_symbol("EXPLICITROLLBACK") is None


def make_bar(start: datetime, close: float = 100.0) -> IntradayBar:
    return IntradayBar(
        start=start, open=close, high=close + 1, low=close - 1, close=close, volume=1_000.0
    )


class TestIntradayBarRepository:
    """Der Speicher, von dem der Backfill lebt. Entscheidend ist nicht das
    Schreiben, sondern dass ein wiederholter Lauf nichts kaputt macht."""

    NEW_YORK = ZoneInfo("America/New_York")

    def _bars(self, anzahl: int, ab: datetime | None = None) -> list[IntradayBar]:
        beginn = ab or datetime(2026, 3, 10, 9, 30, tzinfo=self.NEW_YORK)
        return [make_bar(beginn + timedelta(minutes=15 * index)) for index in range(anzahl)]

    def test_ein_naiver_zeitstempel_wird_abgewiesen(self, uow_factory: UowFactory) -> None:
        """Doc 10 untersagt naive Zeitstempel; ``ruff`` setzt das nur im
        eigenen Code durch, nicht an der Systemgrenze.

        PostgreSQL naehme den Wert an und legte ihn in der Zeitzone der
        Datenbanksitzung aus -- serverabhaengig. Zurueck kaeme ein
        zeitzonenbehafteter Wert, an dem nichts mehr auf den Fehler hinweist:
        Aus 09:30 New Yorker Zeit waere 09:30 UTC geworden, der Bar laege
        ausserhalb des Sitzungsfensters, und der Handelstag saehe aus wie
        einer ohne jede Lieferung.
        """
        naiv = make_bar(datetime(2026, 3, 10, 9, 30))  # noqa: DTZ001 -- genau darum geht es

        with uow_factory() as uow, pytest.raises(ValueError, match="ohne Zeitzone"):
            uow.intraday_bars.add_all("AAPL", [naiv])

    def test_ein_naiver_zeitstempel_unter_vielen_faellt_auf(self, uow_factory: UowFactory) -> None:
        """Auch als einzelner Ausreisser in einer sonst sauberen Lieferung."""
        bars = self._bars(10)
        bars[7] = make_bar(datetime(2026, 3, 10, 11, 15))  # noqa: DTZ001

        with uow_factory() as uow, pytest.raises(ValueError, match="ohne Zeitzone"):
            uow.intraday_bars.add_all("AAPL", bars)

    def test_nichts_wird_geschrieben_wenn_ein_zeitstempel_naiv_ist(
        self, uow_factory: UowFactory
    ) -> None:
        """Sonst laege die halbe Lieferung im Bestand und der naechste Lauf
        hielte die Luecke faelschlich fuer gefuellt."""
        bars = self._bars(10)
        bars[7] = make_bar(datetime(2026, 3, 10, 11, 15))  # noqa: DTZ001

        with uow_factory() as uow:
            with pytest.raises(ValueError):
                uow.intraday_bars.add_all("AAPL", bars)
            uow.commit()

        with uow_factory() as uow:
            assert uow.intraday_bars.latest_start("AAPL") is None

    def test_ohne_daten_gibt_es_keinen_letzten_stand(self, uow_factory: UowFactory) -> None:
        """Der Fall des allerersten Laufs -- er entscheidet, ob ein ganzes Jahr
        oder nur ein Tag geholt wird."""
        with uow_factory() as uow:
            assert uow.intraday_bars.latest_start("LEER") is None

    def test_der_letzte_stand_ist_der_juengste_bar(self, uow_factory: UowFactory) -> None:
        bars = self._bars(5)
        with uow_factory() as uow:
            uow.intraday_bars.add_all("AAPL", bars)
            uow.commit()

        with uow_factory() as uow:
            assert uow.intraday_bars.latest_start("AAPL") == bars[-1].start

    def test_der_erste_stand_ist_der_aelteste_bar(self, uow_factory: UowFactory) -> None:
        """Der Ansatzpunkt des Tiefen-Backfills (ADR 0028).

        Er fuellt rueckwaerts, nicht vorwaerts -- und weil dieser Wert mit
        jedem geschriebenen Fenster weiter zurueckwandert, setzt ein
        abgebrochener Lauf ohne Zutun genau dort wieder an.
        """
        bars = self._bars(5)
        with uow_factory() as uow:
            uow.intraday_bars.add_all("AAPL", bars)
            uow.commit()

        with uow_factory() as uow:
            assert uow.intraday_bars.earliest_start("AAPL") == bars[0].start

    def test_ohne_daten_gibt_es_keinen_ersten_stand(self, uow_factory: UowFactory) -> None:
        with uow_factory() as uow:
            assert uow.intraday_bars.earliest_start("LEER") is None

    def test_der_erste_stand_wandert_mit_aelteren_bars_zurueck(
        self, uow_factory: UowFactory
    ) -> None:
        """Die Eigenschaft, auf der die Fortsetzbarkeit beruht."""
        spaet = self._bars(3)
        frueh = self._bars(3, ab=datetime(2025, 3, 10, 9, 30, tzinfo=self.NEW_YORK))
        with uow_factory() as uow:
            uow.intraday_bars.add_all("AAPL", spaet)
            uow.commit()
        with uow_factory() as uow:
            assert uow.intraday_bars.earliest_start("AAPL") == spaet[0].start
            uow.intraday_bars.add_all("AAPL", frueh)
            uow.commit()

        with uow_factory() as uow:
            assert uow.intraday_bars.earliest_start("AAPL") == frueh[0].start

    def test_derselbe_lauf_zweimal_schreibt_nichts_doppelt(self, uow_factory: UowFactory) -> None:
        """Die Eigenschaft, die den Backfill wiederholbar macht: Ein
        abgebrochener Lauf wird schlicht erneut gestartet."""
        bars = self._bars(5)
        with uow_factory() as uow:
            assert uow.intraday_bars.add_all("AAPL", bars) == 5
            uow.commit()

        with uow_factory() as uow:
            assert uow.intraday_bars.add_all("AAPL", bars) == 0
            uow.commit()

        with uow_factory() as uow:
            assert len(uow.intraday_bars.list_for("AAPL")) == 5

    def test_ueberlappende_zeitraeume_zaehlen_nur_das_neue(self, uow_factory: UowFactory) -> None:
        """Zwei Laeufe ueberlappen sich zwangslaeufig -- der zweite beginnt am
        letzten bekannten Bar, damit keine Luecke entsteht."""
        with uow_factory() as uow:
            uow.intraday_bars.add_all("AAPL", self._bars(5))
            uow.commit()

        with uow_factory() as uow:
            assert uow.intraday_bars.add_all("AAPL", self._bars(8)) == 3
            uow.commit()

        with uow_factory() as uow:
            assert len(uow.intraday_bars.list_for("AAPL")) == 8

    def test_bars_kommen_zeitlich_aufsteigend_zurueck(self, uow_factory: UowFactory) -> None:
        """Die Aggregation verlaesst sich nicht darauf, aber eine falsche
        Reihenfolge waere ein stiller Fehler."""
        bars = self._bars(6)
        with uow_factory() as uow:
            uow.intraday_bars.add_all("AAPL", list(reversed(bars)))
            uow.commit()

        with uow_factory() as uow:
            gelesen = uow.intraday_bars.list_for("AAPL")
            assert [bar.start for bar in gelesen] == [bar.start for bar in bars]

    def test_zwei_aktien_teilen_sich_keinen_bestand(self, uow_factory: UowFactory) -> None:
        with uow_factory() as uow:
            uow.intraday_bars.add_all("AAPL", self._bars(5))
            uow.intraday_bars.add_all("MSFT", self._bars(2))
            uow.commit()

        with uow_factory() as uow:
            assert len(uow.intraday_bars.list_for("AAPL")) == 5
            assert len(uow.intraday_bars.list_for("MSFT")) == 2

    def test_der_zeitpunkt_ueberlebt_die_datenbank(self, uow_factory: UowFactory) -> None:
        """Naive Zeitstempel sind untersagt (Doc 10). Was hineingeht, muss
        denselben Zeitpunkt bezeichnen, wenn es herauskommt."""
        bar = make_bar(datetime(2026, 3, 10, 9, 30, tzinfo=self.NEW_YORK))
        with uow_factory() as uow:
            uow.intraday_bars.add_all("AAPL", [bar])
            uow.commit()

        with uow_factory() as uow:
            gelesen = uow.intraday_bars.list_for("AAPL")[0]
            assert gelesen.start.tzinfo is not None
            assert gelesen.start == bar.start

    def test_eine_leere_lieferung_ist_kein_fehler(self, uow_factory: UowFactory) -> None:
        """Kommt an einem Feiertag nichts zurueck, ist das der Normalfall."""
        with uow_factory() as uow:
            assert uow.intraday_bars.add_all("AAPL", []) == 0
            uow.commit()

    def test_mehr_bars_als_postgres_parameter_erlaubt(self, uow_factory: UowFactory) -> None:
        """PostgreSQL nimmt hoechstens 65.535 Parameter je Anweisung.

        Bei sieben Spalten je Bar reisst ein einzelnes Insert ab 9.363 Zeilen
        ab. Ein Jahr Fuenf-Minuten-Bars liegt darueber, ebenso der in ADR 0014
        vorgesehene Fuenf-Jahres-Batch -- der Fall ist also nicht konstruiert,
        sondern der naechste Ausbauschritt.
        """
        bars = self._bars(12_000)

        with uow_factory() as uow:
            assert uow.intraday_bars.add_all("VIELE", bars) == 12_000
            uow.commit()

        with uow_factory() as uow:
            assert len(uow.intraday_bars.list_for("VIELE")) == 12_000

    def test_auch_ueber_die_grenze_hinweg_bleibt_es_idempotent(
        self, uow_factory: UowFactory
    ) -> None:
        """Die Stueckelung darf die Eigenschaft nicht aufweichen, auf der die
        Wiederholbarkeit beruht."""
        bars = self._bars(12_000)
        with uow_factory() as uow:
            uow.intraday_bars.add_all("VIELE", bars)
            uow.commit()

        with uow_factory() as uow:
            assert uow.intraday_bars.add_all("VIELE", bars) == 0
            uow.commit()

        with uow_factory() as uow:
            assert len(uow.intraday_bars.list_for("VIELE")) == 12_000

    def test_werte_bleiben_unveraendert(self, uow_factory: UowFactory) -> None:
        bar = make_bar(datetime(2026, 3, 10, 9, 30, tzinfo=self.NEW_YORK), close=123.45)
        with uow_factory() as uow:
            uow.intraday_bars.add_all("AAPL", [bar])
            uow.commit()

        with uow_factory() as uow:
            assert uow.intraday_bars.list_for("AAPL")[0] == bar


class TestKiEinordnung:
    """Die KI-Einordnung der Chartauswertung (ADR 0026).

    Getrennt gespeichert von der deterministischen Auswertung, wie Doc 10,
    Paragraph 6.8 es verlangt -- der letzte Test dieser Klasse sichert genau
    das zu.
    """

    @staticmethod
    def _assessment(**overrides: object) -> TechnicalAssessment:
        felder: dict[str, object] = {
            "status": TechnicalAssessmentStatus.COMPLETED,
            "evaluated_at": datetime.now(UTC),
            "model": "claude-haiku-4-5-20251001",
            "prompt_version": "technical-agent-v1",
            "interpreted_analysis_version": TECHNICAL_ANALYSIS_VERSION,
            "summary": "Aufwaertstrend ueber beiden Durchschnitten, Widerstand in Reichweite.",
            "trend_strength": TrendStrength.MODERATE,
            "breakout_quality": BreakoutQuality.NO_BREAKOUT,
            "momentum_state": MomentumState.NEUTRAL,
            "false_signal_risk": FalseSignalRisk.MEDIUM,
            "risk_reward_rating": RiskRewardRating.BALANCED,
            "swing_entry_plausibility": SwingEntryPlausibility.QUESTIONABLE,
            "false_signal_risks": ("Kurs dicht unter einer starken Widerstandszone",),
            "confidence": 0.6,
        }
        felder.update(overrides)
        return TechnicalAssessment(**felder)  # type: ignore[arg-type]

    @staticmethod
    def _snapshot() -> TechnicalSnapshot:
        return TechnicalSnapshot(
            status=TechnicalStatus.COMPLETED,
            evaluated_at=datetime.now(UTC),
            analysis_version=TECHNICAL_ANALYSIS_VERSION,
            parameters=TechnicalAnalysisParameters().as_mapping(),
            close=100.0,
            trend=TrendDirection.UP,
            downside_to_support_pct=0.02,
            upside_to_resistance_pct=0.05,
            chance_risk_ratio=2.5,
        )

    def _persist(
        self,
        uow_factory: UowFactory,
        symbol: str,
        assessment: TechnicalAssessment | None,
    ) -> StockScreeningOutcome:
        stock = make_stock(symbol)
        run = make_run()
        outcome = StockScreeningOutcome(
            analysis_run_id=run.id,
            stock=stock,
            result=ScreeningResult(status=ScreeningStatus.CANDIDATE),
            decision_candle_index=258,
            evaluated_at=datetime.now(UTC),
            signal_rule_version=SIGNAL_RULE_VERSION,
            technical=self._snapshot(),
            technical_assessment=assessment,
        )
        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()
        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)
        return persisted

    def test_eine_vollstaendige_einordnung_ueberlebt_die_datenbank(
        self, uow_factory: UowFactory
    ) -> None:
        assessment = self._assessment()

        persisted = self._persist(uow_factory, "WITHAI", assessment)

        assert persisted.technical_assessment == assessment

    def test_die_chance_risiko_werte_ueberleben_die_datenbank(
        self, uow_factory: UowFactory
    ) -> None:
        persisted = self._persist(uow_factory, "WITHRATIO", self._assessment())

        assert persisted.technical is not None
        assert persisted.technical.downside_to_support_pct == 0.02
        assert persisted.technical.upside_to_resistance_pct == 0.05
        assert persisted.technical.chance_risk_ratio == 2.5

    def test_ein_ausfall_wird_als_solcher_gespeichert(self, uow_factory: UowFactory) -> None:
        """Kein Ersatztext: Bei UNAVAILABLE bleiben alle Inhaltsfelder leer,
        und genau so kommen sie zurueck."""
        assessment = TechnicalAssessment(
            status=TechnicalAssessmentStatus.UNAVAILABLE,
            evaluated_at=datetime.now(UTC),
            model=None,
            prompt_version=None,
            reason="provider_error",
        )

        persisted = self._persist(uow_factory, "AIFAILED", assessment)

        assert persisted.technical_assessment == assessment
        assert persisted.technical_assessment is not None
        assert persisted.technical_assessment.summary is None
        assert persisted.technical_assessment.false_signal_risks == ()

    def test_ohne_einordnung_bleibt_das_feld_leer(self, uow_factory: UowFactory) -> None:
        """Eine Zeile aus der Zeit vor dem Technical Agent liest als ``None``
        zurueck -- nie als Fehler."""
        persisted = self._persist(uow_factory, "NOAI", None)

        assert persisted.technical_assessment is None
        assert persisted.technical is not None

    def test_die_einordnung_veraendert_die_deterministischen_werte_nicht(
        self, uow_factory: UowFactory
    ) -> None:
        """Doc 10, Paragraph 6.8: getrennt gespeichert. Derselbe Snapshot,
        einmal mit und einmal ohne Einordnung, muss identisch zurueckkommen."""
        mit = self._persist(uow_factory, "SEPARATEA", self._assessment())
        ohne = self._persist(uow_factory, "SEPARATEB", None)

        assert mit.technical is not None
        assert ohne.technical is not None
        assert mit.technical.close == ohne.technical.close
        assert mit.technical.chance_risk_ratio == ohne.technical.chance_risk_ratio
        assert mit.technical.trend == ohne.technical.trend
        assert mit.technical.analysis_version == ohne.technical.analysis_version
