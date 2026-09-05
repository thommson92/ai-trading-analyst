"""Repository- und UnitOfWork-Tests gegen echtes PostgreSQL."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ai_trading_analyst.domain.analysis import (
    AnalysisRun,
    RunStatus,
    Stock,
    StockProcessingError,
    StockScreeningOutcome,
)
from ai_trading_analyst.domain.analysts import (
    ANALYST_ANALYSIS_VERSION,
    AnalystRecommendations,
    AnalystRecommendationStatus,
)
from ai_trading_analyst.domain.backtesting import (
    BacktestConfidence,
    BacktestResult,
    HorizonMetrics,
    OptionsBacktestResult,
    OptionsBacktestScope,
    VariantMetrics,
)
from ai_trading_analyst.domain.backtesting.options_metrics import assumptions_of
from ai_trading_analyst.domain.backtesting.options_trade import (
    OPTIONS_BACKTEST_VERSION,
    OptionsBacktestParameters,
    OptionTrade,
    TradeOutcome,
)
from ai_trading_analyst.domain.earnings import EarningsFilterResult, EarningsFilterStatus
from ai_trading_analyst.domain.options import (
    LiquidityGrade,
    OptionQuote,
    OptionsAnalysis,
    OptionsStatus,
    PutSpread,
    PutStrategy,
)
from ai_trading_analyst.domain.report import (
    REPORT_SCHEMA_VERSION,
    ReportSection,
    StockReport,
    build_report,
)
from ai_trading_analyst.domain.research import (
    Citation,
    ResearchCoverage,
    ResearchEvidence,
    ResearchReport,
    ResearchStatus,
    SourceLicenseClass,
    SourceRank,
)
from ai_trading_analyst.domain.scoring import (
    ComponentName,
    Recommendation,
    RecommendationResult,
    ScoreComponent,
    ScoreConfidence,
    ScoreKind,
    ScoreResult,
    ScoreStatus,
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
from ai_trading_analyst.infrastructure.fixtures.analyst_recommendations_provider import (
    FixtureAnalystRecommendationsProvider,
)
from ai_trading_analyst.infrastructure.fixtures.fundamental_provider import (
    FixtureFundamentalDataProvider,
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

    def test_fundamentalkennzahlen_ueberleben_die_datenbank(
        self, uow_factory: UowFactory
    ) -> None:
        """ADR 0035 -- jede Kennzahl mit Einheit, Basis, Zeitraum und Herkunft.

        Zwei Kennzahlen desselben Berichts koennen verschiedene Zeitbezuege
        haben (ADR 0033 L2), weshalb Basis und Zeitraum an der Kennzahl
        stehen und nicht am Ergebnis.
        """
        stock = make_stock("WITHFUNDAMENTALS")
        run = make_run()
        fundamentals = FixtureFundamentalDataProvider().fundamentals(stock, price=232.14)
        assert fundamentals.metrics, "Die Vorlage muss Kennzahlen liefern"
        outcome = StockScreeningOutcome(
            analysis_run_id=run.id,
            stock=stock,
            result=ScreeningResult(status=ScreeningStatus.CANDIDATE),
            decision_candle_index=258,
            evaluated_at=datetime.now(UTC),
            signal_rule_version=SIGNAL_RULE_VERSION,
            fundamentals=fundamentals,
        )

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()

        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)

        assert persisted.fundamentals == fundamentals
        gelesen = persisted.fundamentals
        assert gelesen is not None
        # Der Kurs gehoert zum Ergebnis, nicht zum Aufruf: Ohne ihn liesse
        # sich ein Kurs-Gewinn-Verhaeltnis nicht nachrechnen.
        assert gelesen.price_used == 232.14
        # Die Quellenbindung aus CLAUDE.md -- vollstaendig, nicht nur der Tag.
        # Geprueft wird jedes Feld einzeln: Ein stillschweigend verlorenes
        # Einreichungsdatum faellt beim Vergleich der Objekte zwar auf, aber
        # erst, wenn jemand die Meldung liest.
        original = next(iter(fundamentals.metrics.values())).sources[0]
        quelle = next(iter(gelesen.metrics.values())).sources[0]
        assert (quelle.cik, quelle.accession, quelle.form, quelle.tag, quelle.filed) == (
            original.cik,
            original.accession,
            original.form,
            original.tag,
            original.filed,
        )

    def test_ein_ergebnis_ohne_fundamentaldaten_bleibt_ohne(
        self, uow_factory: UowFactory
    ) -> None:
        """Faellt EDGAR aus, bleibt das Feld leer -- kein Platzhalter, keine
        Nullwerte in achtzehn Zeilen."""
        stock = make_stock("NOFUNDAMENTALS")
        run = make_run()
        outcome = make_outcome(stock, ScreeningStatus.CANDIDATE, analysis_run_id=run.id)

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()

        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)

        assert persisted.fundamentals is None

    def test_analystenempfehlungen_ueberleben_die_datenbank(
        self, uow_factory: UowFactory
    ) -> None:
        """ADR 0043 -- die Verteilung roh, mit Quelle und Abrufzeitpunkt.

        Der Rundlauf geht ueber JSONB. Geprueft wird die **Reihenfolge**
        ausdruecklich mit: Sie ist Teil der Zusage von ``periods``, und eine
        Liste, die beim Lesen kippt, faellt beim Vergleich zweier Objekte mit
        gleichen Zahlen nicht auf.
        """
        stock = make_stock("FIXCAND")
        run = make_run()
        empfehlungen = FixtureAnalystRecommendationsProvider().recommendations(stock)
        assert empfehlungen.status is AnalystRecommendationStatus.COMPLETED
        assert len(empfehlungen.periods) > 1, "Die Vorlage braucht mehrere Monatsstaende"

        outcome = StockScreeningOutcome(
            analysis_run_id=run.id,
            stock=stock,
            result=ScreeningResult(status=ScreeningStatus.CANDIDATE),
            decision_candle_index=258,
            evaluated_at=datetime.now(UTC),
            signal_rule_version=SIGNAL_RULE_VERSION,
            analysts=empfehlungen,
        )

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()

        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)

        assert persisted.analysts == empfehlungen
        gelesen = persisted.analysts
        assert gelesen is not None
        assert [stand.period for stand in gelesen.periods] == [
            stand.period for stand in empfehlungen.periods
        ]
        # Jede der fuenf Votenklassen einzeln: Ein vertauschtes Paar faellt
        # beim Objektvergleich zwar auf, aber erst beim Lesen der Meldung.
        original, wieder = empfehlungen.periods[0], gelesen.periods[0]
        assert (
            wieder.strong_buy,
            wieder.buy,
            wieder.hold,
            wieder.sell,
            wieder.strong_sell,
        ) == (
            original.strong_buy,
            original.buy,
            original.hold,
            original.sell,
            original.strong_sell,
        )
        assert gelesen.source == "fixture"
        assert gelesen.retrieved_at is not None
        assert gelesen.analysis_version == ANALYST_ANALYSIS_VERSION

    def test_ein_ausfall_wird_als_ausfall_gespeichert(self, uow_factory: UowFactory) -> None:
        """Nicht als leeres Feld: "nicht abgefragt" und "abgefragt, keine
        Antwort" sind verschiedene Aussagen (ADR 0043)."""
        stock = make_stock("RATINGSDOWN")
        run = make_run()
        ausfall = AnalystRecommendations(
            status=AnalystRecommendationStatus.UNAVAILABLE,
            evaluated_at=datetime.now(UTC),
            reason="provider_error",
        )
        outcome = StockScreeningOutcome(
            analysis_run_id=run.id,
            stock=stock,
            result=ScreeningResult(status=ScreeningStatus.CANDIDATE),
            decision_candle_index=258,
            evaluated_at=datetime.now(UTC),
            signal_rule_version=SIGNAL_RULE_VERSION,
            analysts=ausfall,
        )

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()

        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)

        gelesen = persisted.analysts
        assert gelesen is not None
        assert gelesen.status is AnalystRecommendationStatus.UNAVAILABLE
        assert gelesen.reason == "provider_error"
        assert gelesen.periods == ()

    def test_ein_ergebnis_ohne_empfehlungen_bleibt_ohne(self, uow_factory: UowFactory) -> None:
        stock = make_stock("NORATINGS")
        run = make_run()
        outcome = make_outcome(stock, ScreeningStatus.CANDIDATE, analysis_run_id=run.id)

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()

        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)

        assert persisted.analysts is None

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

    def test_ein_zitat_ohne_rang_wird_zu_unranked(
        self, uow_factory: UowFactory, engine: Engine
    ) -> None:
        """Der NULL-Fall laesst sich ueber das Repository nicht herstellen:
        ``Citation.source_rank`` hat einen Vorgabewert, geschrieben wird also
        immer 'UNRANKED'. Eine Zeile aus der Zeit vor ADR 0029 traegt aber
        NULL -- deshalb hier auf die Spalte durchgegriffen. Ohne das bestuende
        die Zusicherung aus dem falschen Grund, und ein Wegfall der
        None-Behandlung liesse jeden Altbestand beim Lesen mit ValueError
        brechen."""
        stock = make_stock("NULLRANK")
        run = make_run()
        research = ResearchReport(
            status=ResearchStatus.COMPLETED,
            evaluated_at=datetime.now(UTC),
            model="claude-sonnet-5",
            prompt_version="research-v1",
            citations=(
                Citation(
                    url="https://sec.gov/alt",
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

        with engine.begin() as connection:
            connection.execute(text("UPDATE research_citations SET source_rank = NULL"))

        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)

        assert persisted.research is not None
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


class TestLatestCandidateAnalyses:
    """Die Abfrage der Wiederholsperre (ADR 0054) durch echtes PostgreSQL.

    Das Fenster ist ``since <= evaluated_at < until``: Die Untergrenze
    gehoert dazu (Tagesbeginn des aeltesten Sperrtages), die Obergrenze
    nicht -- der laufende Handelstag sperrt nie.
    """

    _SEIT = datetime(2026, 8, 26, 0, 0, tzinfo=UTC)
    _BIS = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)

    def _speichere(
        self,
        uow_factory: UowFactory,
        symbol: str,
        *,
        evaluated_at: datetime,
        status: ScreeningStatus = ScreeningStatus.CANDIDATE,
    ) -> None:
        stock = make_stock(symbol)
        run = make_run()
        outcome = replace(
            make_outcome(stock, status, analysis_run_id=run.id),
            evaluated_at=evaluated_at,
        )
        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()

    def _abfrage(self, uow_factory: UowFactory) -> dict[str, datetime]:
        with uow_factory() as uow:
            return dict(
                uow.screening_results.latest_candidate_analyses(
                    since=self._SEIT, until=self._BIS
                )
            )

    def test_nur_analysen_im_fenster_zaehlen(self, uow_factory: UowFactory) -> None:
        self._speichere(
            uow_factory, "SPERRE-DRIN", evaluated_at=self._SEIT + timedelta(days=2)
        )
        self._speichere(
            uow_factory, "SPERRE-DAVOR", evaluated_at=self._SEIT - timedelta(hours=1)
        )
        self._speichere(uow_factory, "SPERRE-HEUTE", evaluated_at=self._BIS + timedelta(hours=13))

        juengste = self._abfrage(uow_factory)

        assert set(juengste) == {"SPERRE-DRIN"}
        assert juengste["SPERRE-DRIN"] == self._SEIT + timedelta(days=2)

    def test_die_untergrenze_zaehlt_die_obergrenze_nicht(self, uow_factory: UowFactory) -> None:
        """`>=` unten, `<` oben: Der Tagesbeginn des aeltesten Sperrtages
        sperrt, der Beginn des laufenden Tages nicht mehr."""
        self._speichere(uow_factory, "SPERRE-UNTEN", evaluated_at=self._SEIT)
        self._speichere(uow_factory, "SPERRE-OBEN", evaluated_at=self._BIS)

        juengste = self._abfrage(uow_factory)

        assert set(juengste) == {"SPERRE-UNTEN"}

    def test_ohne_volle_analyse_zaehlt_nichts(self, uow_factory: UowFactory) -> None:
        self._speichere(
            uow_factory,
            "SPERRE-KEIN-KANDIDAT",
            evaluated_at=self._SEIT + timedelta(days=1),
            status=ScreeningStatus.NOT_CANDIDATE,
        )

        assert self._abfrage(uow_factory) == {}

    def test_die_juengste_analyse_eines_symbols_gewinnt(self, uow_factory: UowFactory) -> None:
        self._speichere(
            uow_factory, "SPERRE-DOPPELT", evaluated_at=self._SEIT + timedelta(days=1)
        )
        self._speichere(
            uow_factory, "SPERRE-DOPPELT", evaluated_at=self._SEIT + timedelta(days=2)
        )

        juengste = self._abfrage(uow_factory)

        assert juengste == {"SPERRE-DOPPELT": self._SEIT + timedelta(days=2)}


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

    def test_die_lauf_bindung_und_die_earnings_kennzeichnung_ueberleben(
        self, uow_factory: UowFactory, engine: Engine
    ) -> None:
        """ADR 0038: Der Backtest aus dem Tageslauf traegt die Lauf-ID, der aus
        ``cli backtest`` nicht. Und beide sagen, ob nahe Berichtstermine
        ausgeschlossen wurden -- heute nirgends."""
        stock = make_stock("BTR")
        run = make_run(status=RunStatus.RUNNING)
        horizon = HorizonMetrics(
            horizon=5,
            raw_event_count=2,
            deduplicated_event_count=2,
            hit_rate=0.5,
            mean_return=0.01,
            median_return=0.01,
            max_loss=-0.02,
            drawdown=-0.03,
            held_above_entry_rate=0.5,
            confidence=BacktestConfidence.LOW_SAMPLE,
        )

        def ergebnis(evaluated_at: datetime) -> BacktestResult:
            return BacktestResult(
                stock_id=stock.id,
                signal_types=frozenset({SignalType.RSI_CROSS, SignalType.EMA5_EMA20_CROSS}),
                signal_rule_version=SIGNAL_RULE_VERSION,
                evaluated_at=evaluated_at,
                history_start=datetime(2020, 1, 2, tzinfo=UTC),
                history_end=datetime(2025, 1, 2, tzinfo=UTC),
                horizons=(horizon,),
            )

        im_lauf = ergebnis(datetime(2026, 8, 30, 12, 0, tzinfo=UTC))
        auf_zuruf = ergebnis(datetime(2026, 8, 29, 12, 0, tzinfo=UTC))

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.backtest_results.add(im_lauf, run.id)
            uow.backtest_results.add(auf_zuruf)
            uow.commit()

        with uow_factory() as uow:
            alle = uow.backtest_results.list_for_stock(stock.id)

        assert len(alle) == 2
        assert all(not r.earnings_exclusion_applied for r in alle)

        # Die Lauf-Bindung steht in einer Spalte, die kein Port zurueckliest --
        # der Bericht holt die Statistik aus dem Screening-Ergebnis, nicht aus
        # der Tabelle. Geprueft wird sie deshalb direkt.
        with engine.connect() as verbindung:
            zeilen = verbindung.execute(
                text(
                    "SELECT evaluated_at, analysis_run_id FROM backtest_results "
                    "WHERE stock_id = :stock_id"
                ),
                {"stock_id": stock.id},
            ).all()
        zuordnung: dict[datetime, uuid.UUID | None] = {
            zeile[0]: zeile[1] for zeile in zeilen
        }
        assert zuordnung[im_lauf.evaluated_at] == run.id
        assert zuordnung[auf_zuruf.evaluated_at] is None


class TestStockReportRepository:
    """ADR 0039: Ein Bericht je Lauf und Aktie, nie ueberschrieben, und beim
    Lesen kommt das gespeicherte Dokument zurueck -- kein neu gebautes."""

    def _bericht(self, stock: Stock, run: AnalysisRun) -> StockReport:
        return build_report(
            make_outcome(stock, ScreeningStatus.CANDIDATE, analysis_run_id=run.id),
            created_at=datetime.now(UTC),
            app_version="0.1.0",
        )

    def test_ein_bericht_uebersteht_den_rundlauf(self, uow_factory: UowFactory) -> None:
        stock = make_stock("RPT")
        run = make_run(status=RunStatus.RUNNING)

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.stock_reports.add(self._bericht(stock, run))
            uow.commit()

        with uow_factory() as uow:
            (gespeichert,) = uow.stock_reports.list_for_run(run.id)

        assert gespeichert.symbol == "RPT"
        assert gespeichert.report_schema_version == REPORT_SCHEMA_VERSION
        assert gespeichert.app_version == "0.1.0"
        # Das JSONB kommt vollstaendig zurueck -- alle achtzehn Abschnitte.
        assert set(gespeichert.document["abschnitte"]) == {s.value for s in ReportSection}

    def test_ein_zweiter_bericht_zum_selben_lauf_wird_abgewiesen(
        self, uow_factory: UowFactory
    ) -> None:
        """Doc 10, Paragraph 8: Ein abgeschlossener Bericht wird nicht
        ueberschrieben. Die Unique Constraint verhindert auch das stille
        zweite Insert."""
        stock = make_stock("RPT2")
        run = make_run(status=RunStatus.RUNNING)

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.stock_reports.add(self._bericht(stock, run))
            uow.commit()

        with pytest.raises(IntegrityError), uow_factory() as uow:
            uow.stock_reports.add(self._bericht(stock, run))
            uow.commit()

    def test_ein_anderer_lauf_bekommt_keine_fremden_berichte(
        self, uow_factory: UowFactory
    ) -> None:
        stock = make_stock("RPT3")
        run_a, run_b = make_run(status=RunStatus.RUNNING), make_run(status=RunStatus.RUNNING)

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run_a)
            uow.analysis_runs.add(run_b)
            uow.stock_reports.add(self._bericht(stock, run_a))
            uow.commit()

        with uow_factory() as uow:
            assert uow.stock_reports.list_for_run(run_b.id) == []

    def test_die_sprint_5_spalten_bleiben_leer(self, uow_factory: UowFactory) -> None:
        """Scoring gehoert zu Sprint 5, die Formulierung zur KI-Haelfte. Beide
        Spalten stehen bereit und werden nicht gefuellt (ADR 0039)."""
        stock = make_stock("RPT4")
        run = make_run(status=RunStatus.RUNNING)

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.stock_reports.add(self._bericht(stock, run))
            uow.commit()

        with uow_factory() as uow:
            zeile = uow.stock_reports.list_for_run(run.id)[0]

        assert zeile.document["scoring_version"] is None
        empfehlung = zeile.document["abschnitte"][ReportSection.EMPFEHLUNG.value]
        assert not empfehlung["verfuegbar"]
        assert empfehlung["vorbehalte"]


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


class TestScores:
    """Beide Scores durch PostgreSQL und zurueck (ADR 0041, ADR 0045).

    Vier Spalten je Score, davon eine JSONB. Der Rundlauf ist der Test, der
    zaehlt: Was das Detail nicht wieder hergibt, ist im Bericht verloren --
    und Doc 10, Paragraph 6.11 verlangt neun Angaben, nicht eine Zahl.
    """

    @staticmethod
    def _score(
        *,
        kind: ScoreKind = ScoreKind.SWING,
        status: ScoreStatus = ScoreStatus.COMPLETED,
        value: float | None = 7.4,
    ) -> ScoreResult:
        return ScoreResult(
            kind=kind,
            status=status,
            version="1.0",
            value=value,
            components=(
                ScoreComponent(
                    name=ComponentName.TECHNICAL_SIGNALS,
                    weight=0.25,
                    value=10.0,
                    effective_weight=0.3125,
                    reason="3 von 3 Signalen",
                ),
                ScoreComponent(
                    name=ComponentName.OPTIONS_ATTRACTIVENESS,
                    weight=0.10,
                    value=None,
                    effective_weight=0.0,
                    reason="die Optionsanalyse ist noch nicht gebaut (ADR 0048)",
                ),
            ),
            coverage=0.8,
            confidence=ScoreConfidence.LOW_COVERAGE,
            positive_factors=("Technische Signale: 10.0",),
            negative_factors=(),
            limiting_risks=("Signalstatistik auf duenner Stichprobe",),
        )

    def _rundlauf(
        self, uow_factory: UowFactory, symbol: str, swing: ScoreResult, investment: ScoreResult
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
            swing_score=swing,
            investment_score=investment,
        )
        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()
        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)
        return persisted

    def test_ein_vollstaendiger_score_kommt_unveraendert_zurueck(
        self, uow_factory: UowFactory
    ) -> None:
        swing = self._score()
        investment = self._score(kind=ScoreKind.LONG_TERM, value=5.5)

        persisted = self._rundlauf(uow_factory, "SCORES", swing, investment)

        assert persisted.swing_score == swing
        assert persisted.investment_score == investment

    def test_die_beiden_scores_werden_nicht_vertauscht(self, uow_factory: UowFactory) -> None:
        """Sie stehen in zwei Spaltensaetzen mit demselben Zuschnitt -- ein
        vertauschter Praefix faende sonst niemand."""
        persisted = self._rundlauf(
            uow_factory,
            "SCORESWAP",
            self._score(value=9.9),
            self._score(kind=ScoreKind.LONG_TERM, value=1.1),
        )
        assert persisted.swing_score is not None
        assert persisted.investment_score is not None
        assert persisted.swing_score.kind is ScoreKind.SWING
        assert persisted.swing_score.value == 9.9
        assert persisted.investment_score.kind is ScoreKind.LONG_TERM
        assert persisted.investment_score.value == 1.1

    def test_eine_fehlende_komponente_bleibt_fehlend(self, uow_factory: UowFactory) -> None:
        """Kaeme sie als 0.0 zurueck, laese sich die Luecke spaeter als
        geprueft und schlecht -- genau die Verwechslung, die Doc 09
        ausschliesst."""
        persisted = self._rundlauf(
            uow_factory, "SCORESGAP", self._score(), self._score(kind=ScoreKind.LONG_TERM)
        )
        assert persisted.swing_score is not None
        assert persisted.swing_score.missing_components == (
            ComponentName.OPTIONS_ATTRACTIVENESS,
        )

    def test_ein_score_ohne_zahl_wird_als_solcher_gespeichert(
        self, uow_factory: UowFactory
    ) -> None:
        ohne = self._score(status=ScoreStatus.INSUFFICIENT_DATA, value=None)

        persisted = self._rundlauf(
            uow_factory, "SCORESNONE", ohne, self._score(kind=ScoreKind.LONG_TERM)
        )

        assert persisted.swing_score is not None
        assert persisted.swing_score.status is ScoreStatus.INSUFFICIENT_DATA
        assert persisted.swing_score.value is None

    def test_ohne_scores_bleiben_die_spalten_leer(self, uow_factory: UowFactory) -> None:
        stock = make_stock("SCORESOFF")
        run = make_run()
        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(
                make_outcome(stock, ScreeningStatus.NOT_CANDIDATE, analysis_run_id=run.id)
            )
            uow.commit()
        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)
        assert persisted.swing_score is None
        assert persisted.investment_score is None


class TestEmpfehlung:
    """Die Stufe samt Herleitung durch PostgreSQL und zurueck (ADR 0046).

    Die Spalte traegt die Stufe, das JSONB die Bausteine. Doc 10, Paragraph
    12 verlangt, dass zu jeder Empfehlung nachvollziehbar bleibt, worauf sie
    beruht -- was der Rundlauf nicht wieder hergibt, ist dafuer verloren.
    """

    @staticmethod
    def _empfehlung(level: Recommendation = Recommendation.CANDIDATE) -> RecommendationResult:
        return RecommendationResult(
            level=level,
            version="1.0",
            reasons=(
                "Swing-Score 7.0 ergibt CANDIDATE",
                "Investment-Score 3.0 senkt auf WATCH",
            ),
            applied_caps=("Berichtstermin unbekannt: hoechstens CANDIDATE",),
        )

    def _rundlauf(
        self, uow_factory: UowFactory, symbol: str, empfehlung: RecommendationResult | None
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
            recommendation=empfehlung,
        )
        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()
        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)
        return persisted

    def test_die_stufe_kommt_mit_ihrer_herleitung_zurueck(
        self, uow_factory: UowFactory
    ) -> None:
        empfehlung = self._empfehlung()

        persisted = self._rundlauf(uow_factory, "EMPF", empfehlung)

        assert persisted.recommendation == empfehlung

    @pytest.mark.parametrize("level", list(Recommendation))
    def test_jede_stufe_laesst_sich_speichern(
        self, uow_factory: UowFactory, level: Recommendation
    ) -> None:
        """Auch ``INSUFFICIENT_DATA``: Der Enumtyp stammt aus einer aelteren
        Migration, und ein fehlender Wert faellt sonst erst im Tageslauf auf."""
        persisted = self._rundlauf(
            uow_factory, f"EMPF-{level.value}", self._empfehlung(level)
        )

        assert persisted.recommendation is not None
        assert persisted.recommendation.level is level

    def test_ohne_empfehlung_bleiben_die_spalten_leer(self, uow_factory: UowFactory) -> None:
        persisted = self._rundlauf(uow_factory, "EMPFOFF", None)

        assert persisted.recommendation is None


class TestOptionsanalyse:
    """Die Put-Vorschlaege durch PostgreSQL und zurueck (ADR 0048).

    Neunzehn Felder je Vorschlag, davon acht, die fehlen duerfen. Genau die
    sind der Grund fuer diesen Rundlauf: Ein ``None``, das als ``0.0``
    zurueckkommt, saehe im Bericht aus wie eine gemessene Null -- ein Delta
    von null, ein Abstand zur Unterstuetzung von null.
    """

    @staticmethod
    def _strategie(**kwargs: Any) -> PutStrategy:
        vorgabe: dict[str, Any] = {
            "expiration": date(2026, 10, 2),
            "days_to_expiration": 31,
            "strike": 90.0,
            "distance_to_price_pct": 0.10,
            "premium": 1.80,
            "break_even": 88.20,
            "capital_at_risk": 9000.0,
            "simple_return": 0.02,
            "annualized_return": 0.2355,
            "liquidity": LiquidityGrade.ACCEPTABLE,
            "liquidity_warnings": ("Open Interest 30",),
            "bid": 1.80,
            "ask": 1.90,
            "mid": 1.85,
            "delta": 0.25,
            "implied_volatility": 0.31,
            "open_interest": 30,
            "volume": 60,
            "distance_to_support_pct": 0.044,
            "earnings_within_term": True,
        }
        return PutStrategy(**{**vorgabe, **kwargs})

    def _analyse(self, *strategien: PutStrategy, reason: str | None = None) -> OptionsAnalysis:
        return OptionsAnalysis(
            status=(
                OptionsStatus.COMPLETED if strategien else OptionsStatus.INSUFFICIENT_DATA
            ),
            evaluated_at=datetime.now(UTC),
            underlying_price=100.0,
            expiration=date(2026, 10, 2) if strategien else None,
            strategies=strategien,
            reason=reason,
        )

    def _rundlauf(
        self, uow_factory: UowFactory, symbol: str, analyse: OptionsAnalysis | None
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
            options=analyse,
        )
        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()
        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)
        return persisted

    def test_ein_vollstaendiger_vorschlag_kommt_unveraendert_zurueck(
        self, uow_factory: UowFactory
    ) -> None:
        analyse = self._analyse(self._strategie())

        persisted = self._rundlauf(uow_factory, "OPTVOLL", analyse)

        assert persisted.options == analyse

    def test_die_rangfolge_bleibt_erhalten(self, uow_factory: UowFactory) -> None:
        """JSONB ist eine Liste, keine Menge -- und die Reihenfolge **ist**
        die Aussage: Der erste Vorschlag ist der bestbewertete."""
        analyse = self._analyse(
            self._strategie(strike=96.0, annualized_return=0.31),
            self._strategie(strike=92.0, annualized_return=0.24),
            self._strategie(strike=88.0, annualized_return=0.17),
        )

        persisted = self._rundlauf(uow_factory, "OPTRANG", analyse)

        assert persisted.options is not None
        assert [s.strike for s in persisted.options.strategies] == [96.0, 92.0, 88.0]

    def test_fehlende_felder_kommen_als_fehlend_zurueck_nicht_als_null(
        self, uow_factory: UowFactory
    ) -> None:
        analyse = self._analyse(
            self._strategie(
                delta=None,
                implied_volatility=None,
                open_interest=None,
                volume=None,
                distance_to_support_pct=None,
                earnings_within_term=None,
            )
        )

        persisted = self._rundlauf(uow_factory, "OPTLEER", analyse)

        assert persisted.options is not None
        (strategie,) = persisted.options.strategies
        assert strategie.delta is None
        assert strategie.open_interest is None
        assert strategie.distance_to_support_pct is None
        # ``None`` und ``False`` sind verschiedene Aussagen ueber den
        # Berichtstermin -- die Datenbank darf sie nicht zusammenwerfen.
        assert strategie.earnings_within_term is None

    def test_ein_ergebnis_ohne_vorschlag_behaelt_seinen_grund(
        self, uow_factory: UowFactory
    ) -> None:
        analyse = self._analyse(reason="keine der 12 Notierungen lieferte ein Delta")

        persisted = self._rundlauf(uow_factory, "OPTOHNE", analyse)

        assert persisted.options is not None
        assert persisted.options.status is OptionsStatus.INSUFFICIENT_DATA
        assert persisted.options.reason == "keine der 12 Notierungen lieferte ein Delta"
        # Der Kurs bleibt: Er belegt, worauf die Strike-Auswahl stand.
        assert persisted.options.underlying_price == pytest.approx(100.0)

    def test_ohne_optionsanalyse_bleiben_die_spalten_leer(
        self, uow_factory: UowFactory
    ) -> None:
        persisted = self._rundlauf(uow_factory, "OPTAUS", None)

        assert persisted.options is None


class TestRohnotierungen:
    """Die abgerufenen Notierungen in ihrer eigenen Tabelle (ADR 0058,
    Festlegung 1).

    Sie werden **geschrieben, aber nicht zurueckgelesen**: Die Kalibrierung
    fragt die Tabelle, nicht das Domaenenobjekt. Deshalb prueft dieser Test
    gegen SQL und nicht gegen einen Rundlauf -- ein Rundlauf koennte gar
    nichts finden, und das saehe wie ein Fehler aus, wo Absicht ist.
    """

    @staticmethod
    def _notierung(strike: float, **kwargs: Any) -> OptionQuote:
        vorgabe: dict[str, Any] = {
            "expiration": date(2026, 10, 2),
            "strike": strike,
            "bid": 1.80,
            "ask": 1.90,
            "delta": -0.25,
            "implied_volatility": 0.31,
            "open_interest": 500,
            "volume": 60,
        }
        return OptionQuote(**{**vorgabe, **kwargs})

    def _schreibe(
        self,
        uow_factory: UowFactory,
        symbol: str,
        *notierungen: OptionQuote,
    ) -> uuid.UUID:
        stock = make_stock(symbol)
        run = make_run()
        outcome = StockScreeningOutcome(
            analysis_run_id=run.id,
            stock=stock,
            result=ScreeningResult(status=ScreeningStatus.CANDIDATE),
            decision_candle_index=258,
            evaluated_at=datetime.now(UTC),
            signal_rule_version=SIGNAL_RULE_VERSION,
            options=OptionsAnalysis(
                status=OptionsStatus.COMPLETED,
                evaluated_at=datetime.now(UTC),
                underlying_price=100.0,
                expiration=date(2026, 10, 2),
                quotes=notierungen,
            ),
        )
        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()
        return run.id

    def test_jede_abgerufene_notierung_landet_in_der_tabelle(
        self, uow_factory: UowFactory, session_factory: sessionmaker[Session]
    ) -> None:
        self._schreibe(
            uow_factory,
            "ROHVOLL",
            self._notierung(96.0),
            self._notierung(92.0),
            self._notierung(80.0, delta=-0.05),
        )

        with session_factory() as session:
            zeilen = session.execute(
                text(
                    "SELECT strike, delta FROM option_quotes ORDER BY position"
                )
            ).all()

        assert [float(strike) for strike, _ in zeilen] == [96.0, 92.0, 80.0]
        # Vorzeichenbehaftet, wie der Anbieter ihn liefert -- hier steht, was
        # ankam, nicht, was die Bewertung daraus machte.
        assert [float(delta) for _, delta in zeilen] == [-0.25, -0.25, -0.05]

    def test_fehlende_felder_bleiben_leer_und_werden_nicht_zu_null(
        self, uow_factory: UowFactory, session_factory: sessionmaker[Session]
    ) -> None:
        """Ein ``NULL``, das als ``0.0`` zurueckkaeme, saehe fuer die
        Kalibrierung wie ein gemessenes Delta von null aus."""
        self._schreibe(
            uow_factory,
            "ROHLEER",
            self._notierung(
                92.0,
                bid=None,
                delta=None,
                implied_volatility=None,
                open_interest=None,
                volume=None,
            ),
        )

        with session_factory() as session:
            (zeile,) = session.execute(
                text(
                    "SELECT bid, ask, delta, implied_volatility, open_interest, volume "
                    "FROM option_quotes"
                )
            ).all()

        bid, ask, delta, iv, oi, volumen = zeile
        assert bid is None
        assert delta is None
        assert iv is None
        assert oi is None
        assert volumen is None
        # Der gelieferte Wert bleibt daneben stehen -- fehlend ist nicht alles.
        assert float(ask) == pytest.approx(1.90)

    def test_ohne_optionsanalyse_entsteht_keine_zeile(
        self, uow_factory: UowFactory, session_factory: sessionmaker[Session]
    ) -> None:
        stock = make_stock("ROHAUS")
        run = make_run()
        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(
                StockScreeningOutcome(
                    analysis_run_id=run.id,
                    stock=stock,
                    result=ScreeningResult(status=ScreeningStatus.NOT_CANDIDATE),
                    decision_candle_index=258,
                    evaluated_at=datetime.now(UTC),
                    signal_rule_version=SIGNAL_RULE_VERSION,
                )
            )
            uow.commit()

        with session_factory() as session:
            anzahl = session.execute(text("SELECT count(*) FROM option_quotes")).scalar_one()

        assert anzahl == 0

    def test_das_domaenenobjekt_kommt_bewusst_ohne_sie_zurueck(
        self, uow_factory: UowFactory
    ) -> None:
        """Nagelt die Asymmetrie fest, statt sie dem naechsten Leser als Fehler
        erscheinen zu lassen: ``OptionsAnalysis.quotes`` ist eine
        Schreibrichtung. Wer sie eines Tages zurueckliest, aendert damit das
        Verhalten jedes Aufrufers -- und soll hier darueber stolpern."""
        run_id = self._schreibe(uow_factory, "ROHRUND", self._notierung(92.0))

        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run_id)

        assert persisted.options is not None
        assert persisted.options.quotes == ()


class TestRohnotierungenLesen:
    """Der Lesepfad fuer den Kalibrierungs-Messlauf (ADR 0058, Stufe 0).

    Der Verbund holt Symbol, Zeitpunkt und Aktienkurs von der Elternzeile --
    sie gehoeren zum Abruf, nicht zum Kontrakt. Faellt einer davon weg, ist
    die Notierung fuer den Vergleich wertlos.
    """

    def _lauf(
        self,
        uow_factory: UowFactory,
        symbol: str,
        analyse: OptionsAnalysis | None,
    ) -> None:
        stock = make_stock(symbol)
        run = make_run()
        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(
                StockScreeningOutcome(
                    analysis_run_id=run.id,
                    stock=stock,
                    result=ScreeningResult(status=ScreeningStatus.CANDIDATE),
                    decision_candle_index=258,
                    evaluated_at=datetime.now(UTC),
                    signal_rule_version=SIGNAL_RULE_VERSION,
                    options=analyse,
                )
            )
            uow.commit()

    def test_der_kontext_kommt_von_der_elternzeile_mit(
        self, uow_factory: UowFactory
    ) -> None:
        gemessen_am = datetime(2026, 9, 4, 17, 15, tzinfo=UTC)
        self._lauf(
            uow_factory,
            "LESEVOLL",
            OptionsAnalysis(
                status=OptionsStatus.COMPLETED,
                evaluated_at=gemessen_am,
                underlying_price=232.14,
                expiration=date(2026, 10, 16),
                quotes=(
                    OptionQuote(
                        expiration=date(2026, 10, 16),
                        strike=220.0,
                        bid=2.30,
                        ask=2.40,
                        delta=-0.22,
                        implied_volatility=0.25,
                        open_interest=1200,
                        volume=340,
                    ),
                ),
            ),
        )

        with uow_factory() as uow:
            (gelesen,) = uow.option_quotes.list_all()

        assert gelesen.symbol == "LESEVOLL"
        assert gelesen.observed_at == gemessen_am
        assert gelesen.underlying_price == pytest.approx(232.14)
        assert gelesen.quote.strike == pytest.approx(220.0)
        assert gelesen.quote.implied_volatility == pytest.approx(0.25)
        # Vorzeichenbehaftet, wie der Anbieter ihn lieferte.
        assert gelesen.quote.delta == pytest.approx(-0.22)
        # Der Mittelwert entsteht aus Geld und Brief -- er wird nicht gespeichert.
        assert gelesen.quote.mid == pytest.approx(2.35)

    def test_die_reihenfolge_des_abrufs_bleibt(self, uow_factory: UowFactory) -> None:
        self._lauf(
            uow_factory,
            "LESERANG",
            OptionsAnalysis(
                status=OptionsStatus.COMPLETED,
                evaluated_at=datetime.now(UTC),
                underlying_price=100.0,
                expiration=date(2026, 10, 16),
                quotes=tuple(
                    OptionQuote(expiration=date(2026, 10, 16), strike=strike, bid=1.0, ask=1.1)
                    for strike in (98.0, 95.0, 92.0)
                ),
            ),
        )

        with uow_factory() as uow:
            gelesen = uow.option_quotes.list_all()

        assert [q.quote.strike for q in gelesen] == [98.0, 95.0, 92.0]

    def test_ohne_notierungen_kommt_nichts_zurueck(self, uow_factory: UowFactory) -> None:
        self._lauf(uow_factory, "LESELEER", None)

        with uow_factory() as uow:
            assert uow.option_quotes.list_all() == ()


class TestSpreadRundlauf:
    """Der Strukturvergleich durch PostgreSQL und zurueck (ADR 0058, E11).

    Er wurde in der ersten Fassung gerechnet und **nirgends** gespeichert --
    die unabhaengige Review fand ihn als schweren Befund. Dieser Test haelt
    fest, dass er den Rundlauf ueberlebt.
    """

    def _rundlauf(
        self, uow_factory: UowFactory, symbol: str, analyse: OptionsAnalysis
    ) -> StockScreeningOutcome:
        stock = make_stock(symbol)
        run = make_run()
        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(
                StockScreeningOutcome(
                    analysis_run_id=run.id,
                    stock=stock,
                    result=ScreeningResult(status=ScreeningStatus.CANDIDATE),
                    decision_candle_index=258,
                    evaluated_at=datetime.now(UTC),
                    signal_rule_version=SIGNAL_RULE_VERSION,
                    options=analyse,
                )
            )
            uow.commit()
        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)
        return persisted

    @staticmethod
    def _analyse(
        spread: PutSpread | None = None, grund: str | None = None
    ) -> OptionsAnalysis:
        return OptionsAnalysis(
            status=OptionsStatus.COMPLETED,
            evaluated_at=datetime.now(UTC),
            underlying_price=232.14,
            expiration=date(2026, 10, 16),
            strategies=(
                PutStrategy(
                    expiration=date(2026, 10, 16),
                    days_to_expiration=35,
                    strike=220.0,
                    distance_to_price_pct=0.05,
                    premium=2.35,
                    break_even=217.65,
                    capital_at_risk=22_000.0,
                    simple_return=0.0107,
                    annualized_return=0.111,
                    liquidity=LiquidityGrade.GOOD,
                ),
            ),
            spread=spread,
            spread_reason=grund,
        )

    def test_ein_vollstaendiger_spread_kommt_unveraendert_zurueck(
        self, uow_factory: UowFactory
    ) -> None:
        spread = PutSpread(
            short_strike=220.0,
            hedge_strike=205.0,
            hedge_cost=0.68,
            net_credit=1.67,
            max_loss=13.33,
            capital_at_risk=1333.0,
            hedge_cost_share=0.2894,
            return_on_risk=0.1253,
            hedge_liquidity=LiquidityGrade.ACCEPTABLE,
            hedge_delta=0.07,
            hedge_open_interest=800,
            hedge_volume=120,
        )

        persisted = self._rundlauf(uow_factory, "SPRVOLL", self._analyse(spread))

        assert persisted.options is not None
        assert persisted.options.spread == spread

    def test_fehlende_felder_kommen_als_fehlend_zurueck(
        self, uow_factory: UowFactory
    ) -> None:
        """Ein ``None``, das als ``0.0`` zurueckkaeme, saehe im Bericht wie ein
        gemessenes Delta von null aus."""
        spread = PutSpread(
            short_strike=220.0,
            hedge_strike=205.0,
            hedge_cost=0.68,
            net_credit=1.67,
            max_loss=13.33,
            capital_at_risk=1333.0,
            hedge_cost_share=0.2894,
            return_on_risk=0.1253,
            hedge_liquidity=LiquidityGrade.POOR,
            hedge_delta=None,
            hedge_open_interest=None,
            hedge_volume=None,
        )

        persisted = self._rundlauf(uow_factory, "SPRLEER", self._analyse(spread))

        assert persisted.options is not None
        assert persisted.options.spread is not None
        assert persisted.options.spread.hedge_delta is None
        assert persisted.options.spread.hedge_open_interest is None
        assert persisted.options.spread.hedge_liquidity is LiquidityGrade.POOR

    def test_der_grund_ueberlebt_ebenfalls(self, uow_factory: UowFactory) -> None:
        """Die Optionsanalyse kann vollstaendig sein und der Vergleich
        trotzdem fehlen -- eigene Spalte, eigener Grund."""
        persisted = self._rundlauf(
            uow_factory,
            "SPRGRUND",
            self._analyse(grund="kein Strike unter dem Verkauf gelistet"),
        )

        assert persisted.options is not None
        assert persisted.options.spread is None
        assert persisted.options.spread_reason == "kein Strike unter dem Verkauf gelistet"
        # Der Grund der Optionsanalyse selbst bleibt davon unberuehrt.
        assert persisted.options.reason is None


class TestOptionsBacktestResultRepository:
    """ADR 0058, Festlegung 9 -- eigene Tabelle, eigene Version, angehaengt.

    Der Rundlauf muss beides tragen: eine Aktienzeile und die Zeile ueber alle
    Aktien (``stock_id is None``). Sie unterscheiden sich nur im Bereich, nie
    in den Kennzahlen -- und genau deshalb faellt eine Verwechslung ohne Test
    nicht auf.
    """

    @staticmethod
    def _kennzahlen(*, gemanagt: bool) -> VariantMetrics:
        return VariantMetrics(
            trades=8,
            win_rate=0.75,
            mean_profit=41.5,
            median_profit=38.0,
            total_profit=332.0,
            worst_profit=-260.0,
            mean_return_on_capital=0.0042,
            expired_worthless=0 if gemanagt else 6,
            assigned=0 if gemanagt else 2,
            take_profits=6 if gemanagt else 0,
            stops=1 if gemanagt else 0,
            closed_at_expiration=1 if gemanagt else 0,
        )

    def _ergebnis(
        self, *, belastbar: bool = True, kombination: frozenset[SignalType] | None = None
    ) -> OptionsBacktestResult:
        return OptionsBacktestResult(
            signal_types=kombination
            or frozenset({SignalType.RSI_CROSS, SignalType.EMA5_EMA20_CROSS}),
            episodes=11,
            trades=8,
            without_trade=3,
            held=self._kennzahlen(gemanagt=False) if belastbar else None,
            managed=self._kennzahlen(gemanagt=True) if belastbar else None,
            confidence=(
                BacktestConfidence.NORMAL
                if belastbar
                else BacktestConfidence.INSUFFICIENT_DATA
            ),
            assumptions=assumptions_of(OptionsBacktestParameters(volatility_uplift=1.25)),
        )

    @staticmethod
    def _bereich(stock_id: uuid.UUID | None, *, messung: uuid.UUID) -> OptionsBacktestScope:
        return OptionsBacktestScope(
            measurement_id=messung,
            measured_at=datetime(2026, 9, 5, 18, 0, tzinfo=UTC),
            signal_rule_version=SIGNAL_RULE_VERSION,
            stock_id=stock_id,
            stocks=1 if stock_id is not None else 4,
            history_start=datetime(2025, 1, 2, 14, 30, tzinfo=UTC),
            history_end=datetime(2026, 9, 4, 20, 0, tzinfo=UTC),
        )

    def test_rundlauf_ueber_aktienzeile_und_gesamtzeile(
        self, uow_factory: UowFactory
    ) -> None:
        stock = make_stock("OPTBT")
        messung = uuid.uuid4()
        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.options_backtest_results.add(
                self._bereich(stock.id, messung=messung), [self._ergebnis()]
            )
            uow.options_backtest_results.add(
                self._bereich(None, messung=messung), [self._ergebnis()]
            )
            uow.commit()

        with uow_factory() as uow:
            assert uow.options_backtest_results.latest_measurement_id() == messung
            zeilen = uow.options_backtest_results.list_for_measurement(messung)

        assert len(zeilen) == 2
        # Die Zeile ueber alle Aktien zuerst -- sie ist die Antwort auf die
        # Frage, die der Lauf gestellt hat.
        (gesamt_bereich, gesamt), (aktien_bereich, je_aktie) = zeilen
        assert gesamt_bereich.stock_id is None
        assert gesamt_bereich.stocks == 4
        assert aktien_bereich.stock_id == stock.id
        assert aktien_bereich.stocks == 1
        assert gesamt == je_aktie

    def test_die_kennzahlen_kommen_unveraendert_zurueck(
        self, uow_factory: UowFactory
    ) -> None:
        messung = uuid.uuid4()
        erwartet = self._ergebnis()
        with uow_factory() as uow:
            uow.options_backtest_results.add(self._bereich(None, messung=messung), [erwartet])
            uow.commit()

        with uow_factory() as uow:
            ((bereich, gelesen),) = uow.options_backtest_results.list_for_measurement(messung)

        assert gelesen == erwartet
        assert bereich == self._bereich(None, messung=messung)
        # Die Annahmen sind das einzige, was zwei Messungen desselben Tages
        # unterscheidet -- sie muessen vollstaendig zurueckkommen.
        assert gelesen.assumptions["volatilitaetsaufschlag"] == "1.25"
        assert gelesen.assumptions["version"] == OPTIONS_BACKTEST_VERSION

    def test_ohne_belastbare_stichprobe_bleiben_beide_varianten_leer(
        self, uow_factory: UowFactory
    ) -> None:
        """``None`` heisst keine Grundlage, nicht null -- und dann darf auch
        die Ausgangsverteilung nicht dastehen. Eine Verteilung ohne Kennzahlen
        sagte, es habe Trades gegeben, deren Ergebnis niemand ausweisen
        wollte."""
        messung = uuid.uuid4()
        with uow_factory() as uow:
            uow.options_backtest_results.add(
                self._bereich(None, messung=messung), [self._ergebnis(belastbar=False)]
            )
            uow.commit()

        with uow_factory() as uow:
            ((_, gelesen),) = uow.options_backtest_results.list_for_measurement(messung)

        assert gelesen.held is None
        assert gelesen.managed is None
        assert gelesen.confidence is BacktestConfidence.INSUFFICIENT_DATA
        # Die Grundgesamtheit steht trotzdem da: Elf Episoden ohne belastbare
        # Kennzahlen sind etwas anderes als keine Episoden.
        assert gelesen.episodes == 11
        assert gelesen.trades == 8

    @staticmethod
    def _trade(index: int, *, gemanagt: TradeOutcome) -> OptionTrade:
        return OptionTrade(
            entry_index=index,
            entry_date=date(2026, 3, 6),
            expiration=date(2026, 4, 17),
            days_to_expiration=42,
            strike=95.0,
            underlying_at_entry=100.0,
            volatility=0.28,
            premium=2.15,
            delta=-0.25,
            capital_at_risk=9_500.0,
            held_outcome=TradeOutcome.EXPIRED_WORTHLESS,
            held_profit=215.0,
            managed_outcome=gemanagt,
            managed_profit=-410.0,
            managed_exit_index=index + 20,
            underlying_at_expiration=102.5,
        )

    def test_die_einzeltrades_kommen_unveraendert_zurueck(
        self, uow_factory: UowFactory
    ) -> None:
        """Nachtrag zu Festlegung 9. Aus ihnen entsteht die eine Zahl je
        Aktie, die ein Vergleich zwischen Aktien braucht."""
        stock = make_stock("OPTTRADE")
        messung = uuid.uuid4()
        kombination = frozenset({SignalType.RSI_CROSS, SignalType.EMA5_EMA20_CROSS})
        erwartet = [
            self._trade(120, gemanagt=TradeOutcome.TAKE_PROFIT),
            self._trade(300, gemanagt=TradeOutcome.CLOSED_AT_EXPIRATION),
        ]
        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.options_backtest_results.add_trades(
                self._bereich(stock.id, messung=messung), {kombination: erwartet}
            )
            uow.commit()

        with uow_factory() as uow:
            gelesen = uow.options_backtest_results.list_trades_for_stock(messung, stock.id)

        assert [trade for _, trade in gelesen] == erwartet
        assert {k for k, _ in gelesen} == {kombination}

    def test_ein_trade_ohne_aktie_wird_abgewiesen(self, uow_factory: UowFactory) -> None:
        """Die Zeile ueber alle Aktien gibt es nur bei den Kennzahlen -- sie
        entsteht aus den Trades und ist keiner. Ohne diese Pruefung entstuenden
        Trades ohne Herkunft, und die Aktienansicht faende sie nie wieder."""
        messung = uuid.uuid4()
        with uow_factory() as uow, pytest.raises(ValueError, match="brauchen eine Aktie"):
            uow.options_backtest_results.add_trades(
                self._bereich(None, messung=messung),
                {
                    frozenset({SignalType.RSI_CROSS}): [
                        self._trade(1, gemanagt=TradeOutcome.STOPPED_OUT)
                    ]
                },
            )

    def test_eine_zweite_messung_ueberschreibt_die_erste_nicht(
        self, uow_factory: UowFactory
    ) -> None:
        """CLAUDE.md: Unveraenderlichkeit. Zwei Laeufe mit verschiedenem
        Volatilitaetsaufschlag sind zwei Befunde und nicht ein korrigierter --
        das Ergebnis gehoert ohnehin als Band ueber mehrere Aufschlaege
        gelesen."""
        erste, zweite = uuid.uuid4(), uuid.uuid4()
        with uow_factory() as uow:
            uow.options_backtest_results.add(self._bereich(None, messung=erste), [self._ergebnis()])
            uow.commit()
        with uow_factory() as uow:
            uow.options_backtest_results.add(
                self._bereich(None, messung=zweite), [self._ergebnis()]
            )
            uow.commit()

        with uow_factory() as uow:
            assert len(uow.options_backtest_results.list_for_measurement(erste)) == 1
            assert len(uow.options_backtest_results.list_for_measurement(zweite)) == 1
