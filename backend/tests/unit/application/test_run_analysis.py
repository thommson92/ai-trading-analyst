"""Tests des Anwendungsfalls RunAnalysisUseCase (Sprint 1B).

Prueft ausschliesslich Orchestrierung: Statusuebergaenge, Fehlerisolation je
Aktie und vollstaendiges Scheitern vor Beginn des Screenings. Die
Signalauswertung selbst ist bereits in ``tests/unit/domain/screening``
abgedeckt -- hier zaehlt nur, dass der Use Case sie korrekt aufruft und mit
dem Ergebnis richtig umgeht.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta

from ai_trading_analyst.application.run_analysis import AgentConcurrency, RunAnalysisUseCase
from ai_trading_analyst.domain.analysis import MarketDataProviderError, RunStatus, Stock
from ai_trading_analyst.domain.earnings import (
    EarningsFilterParameters,
    EarningsFilterStatus,
    NextEarningsDate,
)
from ai_trading_analyst.domain.fundamentals import FundamentalStatus
from ai_trading_analyst.domain.research import ResearchReport, ResearchStatus
from ai_trading_analyst.domain.screening import CandidateRuleParameters, ScreeningStatus
from ai_trading_analyst.domain.technical import (
    TechnicalAnalysisParameters,
    TechnicalAssessment,
    TechnicalAssessmentStatus,
    TechnicalSnapshot,
    TechnicalStatus,
)
from tests.unit.application.conftest import (
    FakeAnalysisRunRepository,
    FakeEarningsProvider,
    FakeFundamentalDataProvider,
    FakeMarketDataProvider,
    FakeProcessingErrorRepository,
    FakeResearchProvider,
    FakeScreeningResultRepository,
    FakeStockRepository,
    FakeTechnicalInterpreter,
    FakeUnitOfWork,
    InMemoryIntradayBarRepository,
    make_incomplete_series,
    make_series,
    make_stock,
)

_PARAMS = CandidateRuleParameters(
    required_signal_count=2, signal_lookback_previous_candles=5, warmup_candles=10
)
_EARNINGS_PARAMS = EarningsFilterParameters(configured_exclusion_candles=20, candles_per_day=2)
_SERIES_LENGTH = 11
_TECHNICAL_PARAMS = TechnicalAnalysisParameters(
    pivot_reach=1,
    atr_length=2,
    trend_lookback=2,
    extremes_lookback=3,
    history_candles=100,
)
"""Kleine Fenster, damit die elf Kerzen der Testreihe fuer eine
vollstaendige Chartauswertung reichen -- die Voreinstellungen aus ADR 0025
brauchen 40. Was die Auswertung inhaltlich rechnet, prueft
``tests/unit/domain/technical``; hier zaehlt nur, dass der Use Case sie
zur richtigen Zeit aufruft."""


def _build_use_case(
    provider: FakeMarketDataProvider,
    earnings_provider: FakeEarningsProvider | None = None,
    research_provider: FakeResearchProvider | None = None,
    technical_interpreter: FakeTechnicalInterpreter | None = None,
    fundamental_provider: FakeFundamentalDataProvider | None = None,
    technical_params: TechnicalAnalysisParameters | None = None,
    agent_concurrency: AgentConcurrency | None = None,
) -> tuple[
    RunAnalysisUseCase,
    FakeStockRepository,
    FakeAnalysisRunRepository,
    FakeScreeningResultRepository,
    FakeProcessingErrorRepository,
]:
    stocks_repo = FakeStockRepository()
    runs_repo = FakeAnalysisRunRepository()
    results_repo = FakeScreeningResultRepository()
    errors_repo = FakeProcessingErrorRepository()
    bars_repo = InMemoryIntradayBarRepository()

    def uow_factory() -> FakeUnitOfWork:
        return FakeUnitOfWork(stocks_repo, bars_repo, runs_repo, results_repo, errors_repo)

    use_case = RunAnalysisUseCase(
        provider,
        earnings_provider or FakeEarningsProvider(),
        research_provider or FakeResearchProvider(),
        technical_interpreter or FakeTechnicalInterpreter(),
        fundamental_provider or FakeFundamentalDataProvider(),
        uow_factory,
        _PARAMS,
        _EARNINGS_PARAMS,
        technical_params or _TECHNICAL_PARAMS,
        agent_concurrency=agent_concurrency,
    )
    return use_case, stocks_repo, runs_repo, results_repo, errors_repo


class TestVollstaendigErfolgreicherLauf:
    def test_alle_aktien_werden_gescreent_und_status_ist_completed(self) -> None:
        stock_a, stock_b = make_stock("AAA"), make_stock("BBB")
        provider = FakeMarketDataProvider(
            stocks=(stock_a, stock_b),
            series_by_symbol={
                "AAA": make_series(_SERIES_LENGTH, candidate=True),
                "BBB": make_series(_SERIES_LENGTH, candidate=False),
            },
        )
        use_case, stocks_repo, runs_repo, results_repo, errors_repo = _build_use_case(provider)

        summary = use_case.execute()

        assert summary.run.status == RunStatus.COMPLETED
        assert summary.run.number_of_stocks == 2
        assert summary.run.candidates_found == 1
        assert len(summary.outcomes) == 2
        assert not summary.errors
        assert {s.symbol for s in stocks_repo.added} == {"AAA", "BBB"}
        assert len(results_repo.added) == 2
        assert not errors_repo.added
        assert runs_repo.get(summary.run.id) == summary.run


class TestTeilweiseErfolgreicherLauf:
    def test_ein_providerfehler_fuehrt_zu_partially_completed(self) -> None:
        stock_a, stock_b = make_stock("AAA"), make_stock("BROKEN")
        provider = FakeMarketDataProvider(
            stocks=(stock_a, stock_b),
            series_by_symbol={"AAA": make_series(_SERIES_LENGTH, candidate=False)},
            error_symbols=frozenset({"BROKEN"}),
        )
        use_case, _, _, results_repo, errors_repo = _build_use_case(provider)

        summary = use_case.execute()

        assert summary.run.status == RunStatus.PARTIALLY_COMPLETED
        assert len(summary.outcomes) == 1
        assert summary.outcomes[0].stock.symbol == "AAA"
        assert len(summary.errors) == 1
        assert summary.errors[0].stock_symbol == "BROKEN"
        assert len(results_repo.added) == 1
        assert len(errors_repo.added) == 1

    def test_ein_fehler_stoppt_nicht_die_verarbeitung_der_uebrigen_aktien(self) -> None:
        """Fehlerisolation: BROKEN scheitert in der Mitte, CCC danach wird trotzdem verarbeitet."""
        stocks = (make_stock("AAA"), make_stock("BROKEN"), make_stock("CCC"))
        provider = FakeMarketDataProvider(
            stocks=stocks,
            series_by_symbol={
                "AAA": make_series(_SERIES_LENGTH, candidate=False),
                "CCC": make_series(_SERIES_LENGTH, candidate=False),
            },
            error_symbols=frozenset({"BROKEN"}),
        )
        use_case, _, _, results_repo, errors_repo = _build_use_case(provider)

        summary = use_case.execute()

        assert {o.stock.symbol for o in summary.outcomes} == {"AAA", "CCC"}
        assert {e.stock_symbol for e in summary.errors} == {"BROKEN"}
        assert len(results_repo.added) == 2
        assert len(errors_repo.added) == 1

    def test_unknown_data_incomplete_zaehlt_nicht_als_kandidat(self) -> None:
        stock = make_stock("INCOMPLETE")
        provider = FakeMarketDataProvider(
            stocks=(stock,), series_by_symbol={"INCOMPLETE": make_incomplete_series(_SERIES_LENGTH)}
        )
        use_case, *_ = _build_use_case(provider)

        summary = use_case.execute()

        assert summary.run.status == RunStatus.COMPLETED
        assert summary.run.candidates_found == 0
        assert summary.outcomes[0].result.status == ScreeningStatus.UNKNOWN_DATA_INCOMPLETE


class TestVollstaendigesScheiternVorScreeningbeginn:
    def test_fehlschlagende_aktienliste_fuehrt_direkt_zu_failed(self) -> None:
        provider = FakeMarketDataProvider(
            stocks=(),
            series_by_symbol={},
            list_stocks_error=MarketDataProviderError("Marktdatenanbieter nicht erreichbar"),
        )
        use_case, stocks_repo, runs_repo, results_repo, errors_repo = _build_use_case(provider)

        summary = use_case.execute()

        assert summary.run.status == RunStatus.FAILED
        assert summary.run.number_of_stocks == 0
        assert summary.run.error_message == "Marktdatenanbieter nicht erreichbar"
        assert not summary.outcomes
        assert not summary.errors
        assert not stocks_repo.added
        assert not results_repo.added
        assert not errors_repo.added
        persisted_run = runs_repo.get(summary.run.id)
        assert persisted_run is not None
        assert persisted_run.status == RunStatus.FAILED

    def test_leere_aktienliste_gilt_als_erfolgreich_abgeschlossen(self) -> None:
        """Kein Fehler, nur nichts zu tun -- kein Grund fuer FAILED."""
        provider = FakeMarketDataProvider(stocks=(), series_by_symbol={})
        use_case, *_ = _build_use_case(provider)

        summary = use_case.execute()

        assert summary.run.status == RunStatus.COMPLETED
        assert summary.run.number_of_stocks == 0


class TestEarningsFilter:
    def test_laeuft_nur_fuer_kandidaten(self) -> None:
        stock_a, stock_b = make_stock("CAND"), make_stock("NOCAND")
        provider = FakeMarketDataProvider(
            stocks=(stock_a, stock_b),
            series_by_symbol={
                "CAND": make_series(_SERIES_LENGTH, candidate=True),
                "NOCAND": make_series(_SERIES_LENGTH, candidate=False),
            },
        )
        earnings_provider = FakeEarningsProvider()
        use_case, *_ = _build_use_case(provider, earnings_provider)

        summary = use_case.execute()

        assert earnings_provider.calls == ["CAND"]
        by_symbol = {o.stock.symbol: o for o in summary.outcomes}
        assert by_symbol["CAND"].earnings is not None
        assert by_symbol["NOCAND"].earnings is None

    def test_provider_ohne_abdeckung_ergibt_unknown(self) -> None:
        stock = make_stock("CAND")
        provider = FakeMarketDataProvider(
            stocks=(stock,), series_by_symbol={"CAND": make_series(_SERIES_LENGTH, candidate=True)}
        )
        use_case, *_ = _build_use_case(provider, FakeEarningsProvider())

        summary = use_case.execute()

        earnings = summary.outcomes[0].earnings
        assert earnings is not None
        assert earnings.status is EarningsFilterStatus.UNKNOWN
        assert earnings.reason == "no_coverage"

    def test_providerausfall_ergibt_unknown_und_bleibt_kein_processing_error(self) -> None:
        stock = make_stock("CAND")
        provider = FakeMarketDataProvider(
            stocks=(stock,), series_by_symbol={"CAND": make_series(_SERIES_LENGTH, candidate=True)}
        )
        earnings_provider = FakeEarningsProvider(error_symbols=frozenset({"CAND"}))
        use_case, _, _, _, errors_repo = _build_use_case(provider, earnings_provider)

        summary = use_case.execute()

        assert summary.run.status == RunStatus.COMPLETED
        assert not summary.errors
        assert not errors_repo.added
        earnings = summary.outcomes[0].earnings
        assert earnings is not None
        assert earnings.status is EarningsFilterStatus.UNKNOWN
        assert earnings.reason == "provider_error"

    def test_unplausibler_termin_ergibt_unknown_und_bleibt_kein_processing_error(self) -> None:
        """Der Anbieter ist erreichbar, seine Antwort aber nicht plausibel

        (Termin vor der Entscheidungskerze) -- das darf die Aktie nicht in
        StockProcessingError verschieben, sondern nur den Earnings-Status auf
        UNKNOWN setzen (ADR 0017: Datenprobleme der Quelle sind kein
        Laufabbruch)."""
        stock = make_stock("CAND")
        provider = FakeMarketDataProvider(
            stocks=(stock,), series_by_symbol={"CAND": make_series(_SERIES_LENGTH, candidate=True)}
        )
        # Die Entscheidungskerze der Fixture-Serie liegt am 2024-01-03; ein
        # Termin davor ist fuer evaluate_earnings_filter unplausibel.
        earnings_provider = FakeEarningsProvider(
            next_by_symbol={
                "CAND": NextEarningsDate(
                    date=date(2024, 1, 1), source="fake", retrieved_at=datetime.now(UTC)
                )
            }
        )
        use_case, _, _, _, errors_repo = _build_use_case(provider, earnings_provider)

        summary = use_case.execute()

        assert summary.run.status == RunStatus.COMPLETED
        assert not summary.errors
        assert not errors_repo.added
        earnings = summary.outcomes[0].earnings
        assert earnings is not None
        assert earnings.status is EarningsFilterStatus.UNKNOWN
        assert earnings.reason == "invalid_data"


class TestFundamentaldatenImTageslauf:
    """ADR 0035 -- Umfang, Kurs und Entkopplung."""

    def _kandidat(self) -> FakeMarketDataProvider:
        stock = make_stock("CAND")
        return FakeMarketDataProvider(
            stocks=(stock,), series_by_symbol={"CAND": make_series(_SERIES_LENGTH, candidate=True)}
        )

    def test_laufen_fuer_kandidaten(self) -> None:
        use_case, *_ = _build_use_case(self._kandidat())

        summary = use_case.execute()

        fundamentals = summary.outcomes[0].fundamentals
        assert fundamentals is not None
        assert fundamentals.status is FundamentalStatus.COMPLETED

    def test_laufen_nicht_fuer_nicht_kandidaten(self) -> None:
        """Ein Abruf sind rund 4 MB. Ueber die volle Watchliste taeglich
        waeren das 800 MB fuer Zahlen, die sich vierteljaehrlich aendern
        (ADR 0035, Entscheidung 1)."""
        stock = make_stock("NOCAND")
        provider = FakeMarketDataProvider(
            stocks=(stock,),
            series_by_symbol={"NOCAND": make_series(_SERIES_LENGTH, candidate=False)},
        )
        fundamental_provider = FakeFundamentalDataProvider()
        use_case, *_ = _build_use_case(provider, fundamental_provider=fundamental_provider)

        summary = use_case.execute()

        assert summary.outcomes[0].fundamentals is None
        assert fundamental_provider.calls == []

    def test_der_kurs_ist_der_schluss_der_letzten_abgeschlossenen_kerze(self) -> None:
        """Genau der Kurs, auf dem Screening und Chartauswertung stehen --
        keine laufende Kerze und keine zweite Quelle (ADR 0035,
        Entscheidung 2)."""
        provider = self._kandidat()
        reihe = provider.get_candle_series(make_stock("CAND"))
        erwartet = reihe.candle(len(reihe) - 1).close
        fundamental_provider = FakeFundamentalDataProvider()
        use_case, *_ = _build_use_case(provider, fundamental_provider=fundamental_provider)

        use_case.execute()

        assert fundamental_provider.calls == [("CAND", erwartet)]

    def test_der_verwendete_kurs_steht_am_ergebnis(self) -> None:
        """Ohne ihn liesse sich ein Kurs-Gewinn-Verhaeltnis spaeter nicht
        nachrechnen, und die Kennzahl waere eine Behauptung."""
        use_case, *_ = _build_use_case(self._kandidat())

        summary = use_case.execute()

        fundamentals = summary.outcomes[0].fundamentals
        assert fundamentals is not None
        assert fundamentals.price_used is not None

    def test_ein_ausfall_kostet_nur_die_kennzahlen(self) -> None:
        """Ein nicht erreichbares EDGAR ist ein normaler Betriebszustand.

        Wuerde die Ausnahme in den umgebenden Fehlerisolations-Block laufen,
        verloere die Aktie ihr ganzes Ergebnis -- Screening, Chartauswertung
        und Earnings-Filter inklusive (ADR 0035, Entscheidung 3).
        """
        fundamental_provider = FakeFundamentalDataProvider(error_symbols=frozenset({"CAND"}))
        use_case, _, _, _, errors_repo = _build_use_case(
            self._kandidat(), fundamental_provider=fundamental_provider
        )

        summary = use_case.execute()

        assert summary.errors == ()
        assert errors_repo.added == []
        ergebnis = summary.outcomes[0]
        assert ergebnis.fundamentals is None
        assert ergebnis.technical is not None
        assert ergebnis.earnings is not None

    def test_ein_vertragsbruch_bleibt_ein_fehler(self) -> None:
        """Nur die Vertragsausnahme wird abgefangen. Eine rohe RuntimeError
        ist ein Programmfehler und soll als solcher sichtbar werden, statt
        als stille Luecke in den Kennzahlen zu enden."""
        fundamental_provider = FakeFundamentalDataProvider(crash_symbols=frozenset({"CAND"}))
        use_case, *_ = _build_use_case(
            self._kandidat(), fundamental_provider=fundamental_provider
        )

        summary = use_case.execute()

        assert summary.outcomes == ()
        assert len(summary.errors) == 1


class TestTechnischeChartauswertung:
    """Doc 10, Paragraph 6.8 -- und vor allem die Entkopplung aus CLAUDE.md:
    Faellt Research oder der Earnings-Anbieter aus, bleibt die technische
    Analyse vollstaendig."""

    def test_laeuft_fuer_kandidaten(self) -> None:
        stock = make_stock("CAND")
        provider = FakeMarketDataProvider(
            stocks=(stock,), series_by_symbol={"CAND": make_series(_SERIES_LENGTH, candidate=True)}
        )
        use_case, *_ = _build_use_case(provider)

        summary = use_case.execute()

        technical = summary.outcomes[0].technical
        assert technical is not None
        assert technical.status is TechnicalStatus.COMPLETED

    def test_laeuft_nicht_fuer_nicht_kandidaten(self) -> None:
        stock = make_stock("NOCAND")
        provider = FakeMarketDataProvider(
            stocks=(stock,),
            series_by_symbol={"NOCAND": make_series(_SERIES_LENGTH, candidate=False)},
        )
        use_case, *_ = _build_use_case(provider)

        summary = use_case.execute()

        assert summary.outcomes[0].technical is None

    def test_ausfall_des_earnings_anbieters_laesst_sie_vollstaendig(self) -> None:
        stock = make_stock("CAND")
        provider = FakeMarketDataProvider(
            stocks=(stock,), series_by_symbol={"CAND": make_series(_SERIES_LENGTH, candidate=True)}
        )
        earnings_provider = FakeEarningsProvider(error_symbols=frozenset({"CAND"}))
        use_case, *_ = _build_use_case(provider, earnings_provider)

        summary = use_case.execute()

        earnings = summary.outcomes[0].earnings
        assert earnings is not None
        assert earnings.status is EarningsFilterStatus.UNKNOWN
        technical = summary.outcomes[0].technical
        assert technical is not None
        assert technical.status is TechnicalStatus.COMPLETED

    def test_ausfall_des_research_anbieters_laesst_sie_vollstaendig(self) -> None:
        stock = make_stock("CAND")
        provider = FakeMarketDataProvider(
            stocks=(stock,), series_by_symbol={"CAND": make_series(_SERIES_LENGTH, candidate=True)}
        )
        earnings_provider = FakeEarningsProvider(
            next_by_symbol={
                "CAND": NextEarningsDate(
                    date=date(2024, 3, 1), source="fake", retrieved_at=datetime.now(UTC)
                )
            }
        )
        research_provider = FakeResearchProvider(error_symbols=frozenset({"CAND"}))
        use_case, *_ = _build_use_case(provider, earnings_provider, research_provider)

        summary = use_case.execute()

        research = summary.outcomes[0].research
        assert research is not None
        assert research.status is ResearchStatus.UNAVAILABLE
        technical = summary.outcomes[0].technical
        assert technical is not None
        assert technical.status is TechnicalStatus.COMPLETED

    def test_zu_kurze_historie_ist_kein_verarbeitungsfehler(self) -> None:
        """Sie ergibt ein Ergebnis mit ``INSUFFICIENT_DATA`` -- die Aktie
        bleibt ein normales Screening-Ergebnis, statt ganz zu verschwinden."""
        stock = make_stock("SHORT")
        provider = FakeMarketDataProvider(
            stocks=(stock,), series_by_symbol={"SHORT": make_series(_SERIES_LENGTH, candidate=True)}
        )
        # Fenster groesser als die Testreihe -- der Fall einer Aktie, die
        # erst seit Kurzem gehandelt wird.
        use_case, _, _, _, errors_repo = _build_use_case(
            provider,
            technical_params=TechnicalAnalysisParameters(extremes_lookback=40, history_candles=250),
        )

        summary = use_case.execute()

        technical = summary.outcomes[0].technical
        assert technical is not None
        assert technical.status is TechnicalStatus.INSUFFICIENT_DATA
        assert technical.reason == "too_few_candles"
        assert errors_repo.added == []


class TestKiEinordnung:
    """Der Technical Agent im Lauf (ADR 0026).

    Der wichtigste Test dieser Klasse ist die Entkopplung: Anders als
    Research laeuft die Einordnung fuer **jeden** Kandidaten mit auswertbarer
    Chartlage, auch wenn der Earnings-Filter ausgeschlagen hat.
    """

    @staticmethod
    def _kandidat() -> FakeMarketDataProvider:
        return FakeMarketDataProvider(
            stocks=(make_stock("CAND"),),
            series_by_symbol={"CAND": make_series(_SERIES_LENGTH, candidate=True)},
        )

    def test_laeuft_fuer_kandidaten(self) -> None:
        interpreter = FakeTechnicalInterpreter()
        use_case, *_ = _build_use_case(self._kandidat(), technical_interpreter=interpreter)

        summary = use_case.execute()

        assert interpreter.calls == ["CAND"]
        assessment = summary.outcomes[0].technical_assessment
        assert assessment is not None
        assert assessment.status is TechnicalAssessmentStatus.COMPLETED

    def test_laeuft_nicht_fuer_nicht_kandidaten(self) -> None:
        provider = FakeMarketDataProvider(
            stocks=(make_stock("NOCAND"),),
            series_by_symbol={"NOCAND": make_series(_SERIES_LENGTH, candidate=False)},
        )
        interpreter = FakeTechnicalInterpreter()
        use_case, *_ = _build_use_case(provider, technical_interpreter=interpreter)

        summary = use_case.execute()

        assert interpreter.calls == []
        assert summary.outcomes[0].technical_assessment is None

    def test_laeuft_auch_ohne_earnings_freigabe(self) -> None:
        """Die Entkopplung aus CLAUDE.md, festgenagelt: Der Earnings-Anbieter
        faellt aus, Research unterbleibt deshalb -- die Einordnung der
        Chartlage laeuft trotzdem. Gerade bei einem Kandidaten mit
        Earnings-Risiko ist sie interessant."""
        earnings_provider = FakeEarningsProvider(error_symbols=frozenset({"CAND"}))
        research_provider = FakeResearchProvider()
        interpreter = FakeTechnicalInterpreter()
        use_case, *_ = _build_use_case(
            self._kandidat(),
            earnings_provider,
            research_provider,
            technical_interpreter=interpreter,
        )

        summary = use_case.execute()

        assert research_provider.calls == []
        assert interpreter.calls == ["CAND"]
        assessment = summary.outcomes[0].technical_assessment
        assert assessment is not None
        assert assessment.status is TechnicalAssessmentStatus.COMPLETED

    def test_ein_anbieterausfall_bleibt_ohne_folgen_fuer_den_lauf(self) -> None:
        interpreter = FakeTechnicalInterpreter(error_symbols=frozenset({"CAND"}))
        use_case, _, _, _, errors_repo = _build_use_case(
            self._kandidat(), technical_interpreter=interpreter
        )

        summary = use_case.execute()

        assert summary.run.status == RunStatus.COMPLETED
        assert not errors_repo.added
        assessment = summary.outcomes[0].technical_assessment
        assert assessment is not None
        assert assessment.status is TechnicalAssessmentStatus.UNAVAILABLE
        assert assessment.reason == "provider_error"

    def test_ein_vertragsbruch_bleibt_ebenfalls_ohne_folgen(self) -> None:
        """Ein Anbieter, der eine rohe Ausnahme wirft, darf das fertige
        Screening-Ergebnis nicht mitreissen (ADR 0023, derselbe Befund beim
        Research Agent)."""
        interpreter = FakeTechnicalInterpreter(crash_symbols=frozenset({"CAND"}))
        use_case, _, _, _, errors_repo = _build_use_case(
            self._kandidat(), technical_interpreter=interpreter
        )

        summary = use_case.execute()

        assert summary.run.status == RunStatus.COMPLETED
        assert not errors_repo.added
        assessment = summary.outcomes[0].technical_assessment
        assert assessment is not None
        assert assessment.status is TechnicalAssessmentStatus.UNAVAILABLE
        assert assessment.reason == "provider_contract_violation"

    def test_der_deterministische_snapshot_bleibt_bei_einem_ausfall_vollstaendig(self) -> None:
        interpreter = FakeTechnicalInterpreter(error_symbols=frozenset({"CAND"}))
        use_case, *_ = _build_use_case(self._kandidat(), technical_interpreter=interpreter)

        summary = use_case.execute()

        technical = summary.outcomes[0].technical
        assert technical is not None
        assert technical.status is TechnicalStatus.COMPLETED
        assert technical.close is not None

    def test_beide_agenten_laufen_fuer_dieselbe_aktie(self) -> None:
        """Mit Earnings-Freigabe laufen beide -- sie teilen sich denselben
        Pool und stehen sich nicht im Weg."""
        earnings_provider = FakeEarningsProvider(
            next_by_symbol={
                "CAND": NextEarningsDate(
                    date=date(2024, 3, 1), source="fake", retrieved_at=datetime.now(UTC)
                )
            }
        )
        research_provider = FakeResearchProvider()
        interpreter = FakeTechnicalInterpreter()
        use_case, *_ = _build_use_case(
            self._kandidat(),
            earnings_provider,
            research_provider=research_provider,
            technical_interpreter=interpreter,
        )

        summary = use_case.execute()

        assert research_provider.calls == ["CAND"]
        assert interpreter.calls == ["CAND"]
        assert summary.outcomes[0].research is not None
        assert summary.outcomes[0].technical_assessment is not None

    def test_bei_mehreren_aktien_landet_jedes_ergebnis_beim_richtigen_symbol(self) -> None:
        """Der eigentliche Test der nebenlaeufigen Phase.

        Mit nur einer Aktie laeuft die Zuordnung Future -> Auftrag faktisch
        sequentiell und beweist nichts. Hier scheitern zwei von vier Aktien
        auf verschiedene Weise -- wenn die Zuordnung rutscht, bekommt der
        falsche Titel den Ausfall.
        """
        symbole = ["AAA", "BBB", "CCC", "DDD"]
        provider = FakeMarketDataProvider(
            stocks=tuple(make_stock(name) for name in symbole),
            series_by_symbol={
                name: make_series(_SERIES_LENGTH, candidate=True) for name in symbole
            },
        )
        interpreter = FakeTechnicalInterpreter(
            error_symbols=frozenset({"BBB"}), crash_symbols=frozenset({"CCC"})
        )
        use_case, *_ = _build_use_case(provider, technical_interpreter=interpreter)

        summary = use_case.execute()

        # Aus Arbeitsthreads gefuellt -- die Reihenfolge ist nicht zugesichert.
        assert set(interpreter.calls) == set(symbole)
        nach_symbol = {o.stock.symbol: o.technical_assessment for o in summary.outcomes}
        assert nach_symbol["AAA"] is not None
        assert nach_symbol["AAA"].status is TechnicalAssessmentStatus.COMPLETED
        assert nach_symbol["DDD"] is not None
        assert nach_symbol["DDD"].status is TechnicalAssessmentStatus.COMPLETED
        assert nach_symbol["BBB"] is not None
        assert nach_symbol["BBB"].reason == "provider_error"
        assert nach_symbol["CCC"] is not None
        assert nach_symbol["CCC"].reason == "provider_contract_violation"


class TestResearch:
    _EARNINGS_CLEAR = NextEarningsDate(
        date=date(2024, 3, 1), source="fake", retrieved_at=datetime.now(UTC)
    )
    """Weit genug in der Zukunft, um bei configured_exclusion_candles=20
    EARNINGS_CLEAR zu ergeben."""

    def test_laeuft_nur_wenn_earnings_clear_ist(self) -> None:
        stock = make_stock("CAND")
        provider = FakeMarketDataProvider(
            stocks=(stock,), series_by_symbol={"CAND": make_series(_SERIES_LENGTH, candidate=True)}
        )
        earnings_provider = FakeEarningsProvider(next_by_symbol={"CAND": self._EARNINGS_CLEAR})
        research_provider = FakeResearchProvider()
        use_case, *_ = _build_use_case(provider, earnings_provider, research_provider)

        summary = use_case.execute()

        earnings = summary.outcomes[0].earnings
        assert earnings is not None
        assert earnings.status is EarningsFilterStatus.EARNINGS_CLEAR
        assert research_provider.calls == ["CAND"]
        research = summary.outcomes[0].research
        assert research is not None
        assert research.status is ResearchStatus.COMPLETED

    def test_laeuft_nicht_wenn_earnings_nicht_clear_ist(self) -> None:
        stock = make_stock("CAND")
        provider = FakeMarketDataProvider(
            stocks=(stock,), series_by_symbol={"CAND": make_series(_SERIES_LENGTH, candidate=True)}
        )
        research_provider = FakeResearchProvider()
        # Standard-FakeEarningsProvider() -> keine Abdeckung -> UNKNOWN.
        use_case, *_ = _build_use_case(provider, FakeEarningsProvider(), research_provider)

        summary = use_case.execute()

        assert research_provider.calls == []
        assert summary.outcomes[0].research is None

    def test_laeuft_nicht_fuer_nicht_kandidaten(self) -> None:
        stock = make_stock("NOCAND")
        provider = FakeMarketDataProvider(
            stocks=(stock,),
            series_by_symbol={"NOCAND": make_series(_SERIES_LENGTH, candidate=False)},
        )
        research_provider = FakeResearchProvider()
        use_case, *_ = _build_use_case(provider, FakeEarningsProvider(), research_provider)

        use_case.execute()

        assert research_provider.calls == []

    def test_providerausfall_ergibt_unavailable_und_bleibt_kein_processing_error(self) -> None:
        stock = make_stock("CAND")
        provider = FakeMarketDataProvider(
            stocks=(stock,), series_by_symbol={"CAND": make_series(_SERIES_LENGTH, candidate=True)}
        )
        earnings_provider = FakeEarningsProvider(next_by_symbol={"CAND": self._EARNINGS_CLEAR})
        research_provider = FakeResearchProvider(error_symbols=frozenset({"CAND"}))
        use_case, _, _, _, errors_repo = _build_use_case(
            provider, earnings_provider, research_provider
        )

        summary = use_case.execute()

        assert summary.run.status == RunStatus.COMPLETED
        assert not summary.errors
        assert not errors_repo.added
        research = summary.outcomes[0].research
        assert research is not None
        assert research.status is ResearchStatus.UNAVAILABLE
        assert research.reason == "provider_error"

    def test_roher_anbieterfehler_kostet_nicht_das_screening_ergebnis(self) -> None:
        """CLAUDE.md: "Faellt Research aus, bleiben technische Analyse und
        Backtesting vollstaendig." Ein Anbieter, der entgegen seinem Vertrag
        eine rohe Ausnahme wirft, darf das fertig berechnete, deterministische
        Screening-Ergebnis nicht mitreissen."""
        stock = make_stock("CAND")
        provider = FakeMarketDataProvider(
            stocks=(stock,), series_by_symbol={"CAND": make_series(_SERIES_LENGTH, candidate=True)}
        )
        earnings_provider = FakeEarningsProvider(next_by_symbol={"CAND": self._EARNINGS_CLEAR})
        research_provider = FakeResearchProvider(crash_symbols=frozenset({"CAND"}))
        use_case, _, _, results_repo, errors_repo = _build_use_case(
            provider, earnings_provider, research_provider
        )

        summary = use_case.execute()

        assert summary.run.status == RunStatus.COMPLETED
        assert not summary.errors
        assert not errors_repo.added
        # Entscheidend: Das Screening-Ergebnis ist da, nicht verworfen.
        assert len(results_repo.added) == 1
        assert summary.run.candidates_found == 1
        research = summary.outcomes[0].research
        assert research is not None
        assert research.status is ResearchStatus.UNAVAILABLE
        assert research.reason == "provider_contract_violation"

    def test_gemischter_ausgang_ordnet_die_berichte_richtig_zu(self) -> None:
        """Scheitert eine von mehreren nebenlaeufigen Recherchen, muessen die
        uebrigen trotzdem ihren eigenen Bericht behalten."""
        stocks = tuple(make_stock(symbol) for symbol in ("AAA", "BBB", "CCC"))
        provider = FakeMarketDataProvider(
            stocks=stocks,
            series_by_symbol={
                s.symbol: make_series(_SERIES_LENGTH, candidate=True) for s in stocks
            },
        )
        earnings_provider = FakeEarningsProvider(
            next_by_symbol={s.symbol: self._EARNINGS_CLEAR for s in stocks}
        )
        research_provider = FakeResearchProvider(
            error_symbols=frozenset({"BBB"}), crash_symbols=frozenset({"CCC"})
        )
        use_case, *_ = _build_use_case(provider, earnings_provider, research_provider)

        summary = use_case.execute()

        assert [o.stock.symbol for o in summary.outcomes] == ["AAA", "BBB", "CCC"]
        berichte = {o.stock.symbol: o.research for o in summary.outcomes}
        assert berichte["AAA"] is not None
        assert berichte["AAA"].summary == "Fake-Recherche fuer AAA"
        assert berichte["BBB"] is not None
        assert berichte["BBB"].reason == "provider_error"
        assert berichte["CCC"] is not None
        assert berichte["CCC"].reason == "provider_contract_violation"

    def test_mehrere_kandidaten_werden_nebenlaeufig_recherchiert_ohne_verwechslung(self) -> None:
        """Die Research-Aufrufe je Aktie laufen nebenlaeufig (siehe
        ``RunAnalysisUseCase._run_agents_concurrently``) -- trotzdem muss
        jede Aktie exakt ihren eigenen Bericht bekommen, und die
        Ausgabereihenfolge bleibt die urspruengliche Aktienreihenfolge."""
        stocks = tuple(make_stock(symbol) for symbol in ("AAA", "BBB", "CCC", "DDD"))
        provider = FakeMarketDataProvider(
            stocks=stocks,
            series_by_symbol={
                s.symbol: make_series(_SERIES_LENGTH, candidate=True) for s in stocks
            },
        )
        earnings_provider = FakeEarningsProvider(
            next_by_symbol={s.symbol: self._EARNINGS_CLEAR for s in stocks}
        )
        research_provider = FakeResearchProvider()
        use_case, *_ = _build_use_case(provider, earnings_provider, research_provider)

        summary = use_case.execute()

        assert [o.stock.symbol for o in summary.outcomes] == ["AAA", "BBB", "CCC", "DDD"]
        assert set(research_provider.calls) == {"AAA", "BBB", "CCC", "DDD"}
        for outcome in summary.outcomes:
            assert outcome.research is not None
            assert outcome.research.summary == f"Fake-Recherche fuer {outcome.stock.symbol}"


class TestGetrennteAgentenPools:
    """R9: Eine haengende Recherche darf keine Einordnung aufhalten.

    Vor ADR 0040 teilten sich beide Agenten vier Plaetze. Ein realer
    Recherche-Aufruf dauert rund 15 Minuten (Messung 2026-08-24) und darf bis
    zu 900 Sekunden laufen -- solange belegte er einen der vier Plaetze,
    waehrend die Einordnungen warteten, die Sekunden brauchen.
    """

    _EARNINGS_CLEAR = NextEarningsDate(
        date=date(2024, 3, 1), source="fake", retrieved_at=datetime.now(UTC)
    )

    def test_haengende_recherche_haelt_die_einordnungen_nicht_auf(self) -> None:
        symbole = ("AAA", "BBB", "CCC", "DDD", "EEE")
        stocks = tuple(make_stock(symbol) for symbol in symbole)
        freigabe = threading.Event()
        alle_eingeordnet = threading.Event()

        class BlockierenderResearchProvider(FakeResearchProvider):
            def research(self, stock: Stock) -> ResearchReport:
                # Haelt so lange, bis der Test die Einordnungen gesehen hat.
                # Reichlich laenger als dessen eigene Wartezeit, damit bei
                # einem Fehlschlag die Zusicherung des Tests meldet und nicht
                # dieses Doppel.
                freigabe.wait(timeout=60.0)
                return super().research(stock)

        class ZaehlenderInterpreter(FakeTechnicalInterpreter):
            def interpret(self, stock: Stock, snapshot: TechnicalSnapshot) -> TechnicalAssessment:
                ergebnis = super().interpret(stock, snapshot)
                if len(self.calls) == len(symbole):
                    alle_eingeordnet.set()
                return ergebnis

        provider = FakeMarketDataProvider(
            stocks=stocks,
            series_by_symbol={
                s.symbol: make_series(_SERIES_LENGTH, candidate=True) for s in stocks
            },
        )
        interpreter = ZaehlenderInterpreter()
        use_case, *_ = _build_use_case(
            provider,
            FakeEarningsProvider(next_by_symbol={s.symbol: self._EARNINGS_CLEAR for s in stocks}),
            BlockierenderResearchProvider(),
            interpreter,
            # Ein Recherche-Platz, zwei Einordnungsplaetze.
            #
            # Fuenf Symbole, nicht drei: Der alte gemeinsame Pool hatte vier
            # Plaetze, und die Auftraege wechseln sich je Aktie ab
            # (Recherche, Einordnung, Recherche, ...). Drei blockierende
            # Recherchen lassen dort immer einen Platz frei, ueber den alle
            # Einordnungen doch noch durchkommen -- der Test waere gruen
            # geblieben. Erst ab fuenf sind alle vier Plaetze belegt.
            agent_concurrency=AgentConcurrency(research=1, technical=2),
        )

        lauf = ThreadPoolExecutor(max_workers=1)
        try:
            future = lauf.submit(use_case.execute)
            fertig = alle_eingeordnet.wait(timeout=10.0)
            # Zum Messzeitpunkt festhalten: Nach der Freigabe laufen die
            # Einordnungen ohnehin durch, und die Meldung waere irrefuehrend.
            eingeordnet = len(interpreter.calls)
            noch_blockiert = not future.done()
            freigabe.set()
            summary = future.result(timeout=30.0)
        finally:
            freigabe.set()
            lauf.shutdown(wait=True)

        assert fertig, (
            "Die Einordnungen liefen nicht durch, waehrend die Recherche haengt "
            f"-- nur {eingeordnet} von {len(symbole)}"
        )
        assert noch_blockiert, "Der Lauf war schon fertig; die Recherche hat gar nicht blockiert"
        assert sorted(interpreter.calls) == list(symbole)
        assert all(o.research is not None for o in summary.outcomes)


class TestVollstaendigesScheiternAllerAktien:
    def test_scheitern_aller_aktien_nach_screeningbeginn_fuehrt_zu_failed(self) -> None:
        stocks = (make_stock("A"), make_stock("B"))
        provider = FakeMarketDataProvider(
            stocks=stocks, series_by_symbol={}, error_symbols=frozenset({"A", "B"})
        )
        use_case, *_ = _build_use_case(provider)

        summary = use_case.execute()

        assert summary.run.status == RunStatus.FAILED
        assert not summary.outcomes
        assert len(summary.errors) == 2


class TestVeralteteDaten:
    """Ein Teilausfall beim Abruf darf keine Analyse auf altem Stand ergeben.

    Die Kerzenreihe kennt keinen Bezug zur Gegenwart: ``len(series) - 1``
    liefert die juengste vorhandene Kerze, gleich ob sie von heute oder von
    vorletzter Woche ist. Reisst die Verbindung zur TWS mitten im Abruf ab,
    sind einige Aktien frisch und die uebrigen alt -- und ohne Pruefung
    entstuende fuer die alten ein sauber aussehendes NOT_CANDIDATE.
    """

    def _lauf(self, erwartet: datetime | None) -> object:
        reihe = make_series(_SERIES_LENGTH, candidate=False)
        provider = FakeMarketDataProvider(
            stocks=(make_stock("AAA"),), series_by_symbol={"AAA": reihe}
        )
        stocks_repo = FakeStockRepository()
        bars_repo = InMemoryIntradayBarRepository()
        runs_repo = FakeAnalysisRunRepository()
        results_repo = FakeScreeningResultRepository()
        errors_repo = FakeProcessingErrorRepository()

        def uow_factory() -> FakeUnitOfWork:
            return FakeUnitOfWork(stocks_repo, bars_repo, runs_repo, results_repo, errors_repo)

        return RunAnalysisUseCase(
            provider,
            FakeEarningsProvider(),
            FakeResearchProvider(),
            FakeTechnicalInterpreter(),
            FakeFundamentalDataProvider(),
            uow_factory,
            _PARAMS,
            _EARNINGS_PARAMS,
            _TECHNICAL_PARAMS,
            expected_last_candle=erwartet,
        ).execute()

    @staticmethod
    def _letzte_kerze() -> datetime:
        reihe = make_series(_SERIES_LENGTH, candidate=False)
        return reihe.candle(len(reihe) - 1).timestamp

    def test_die_erwartete_kerze_laesst_den_lauf_durch(self) -> None:
        bericht = self._lauf(self._letzte_kerze())

        assert len(bericht.outcomes) == 1  # type: ignore[attr-defined]
        assert bericht.errors == ()  # type: ignore[attr-defined]

    def test_eine_abweichende_kerze_wird_als_fehler_gefuehrt(self) -> None:
        """Statt auf altem Stand gescreent zu werden."""
        bericht = self._lauf(self._letzte_kerze() + timedelta(minutes=195))

        assert bericht.outcomes == ()  # type: ignore[attr-defined]
        assert len(bericht.errors) == 1  # type: ignore[attr-defined]
        assert "fehlen die Daten" in bericht.errors[0].message  # type: ignore[attr-defined]

    def test_ein_teilausfall_schlaegt_auf_die_vollstaendigkeit_durch(self) -> None:
        """Woran der Dispatcher erkennt, dass der Abend nichts geworden ist.

        Der Lauf selbst wirft nicht -- er meldet je Aktie einen Fehler. Erst
        diese Kennzahl macht aus 'eine von zwei' ein Signal, das der
        Dispatcher auswerten kann.
        """
        veraltet = self._letzte_kerze() + timedelta(minutes=195)

        assert self._lauf(veraltet).completion_ratio == 0.0  # type: ignore[attr-defined]
        assert self._lauf(self._letzte_kerze()).completion_ratio == 1.0  # type: ignore[attr-defined]

    def test_ohne_erwartung_wird_nicht_geprueft(self) -> None:
        """Der manuelle Lauf: Dort entscheidet der Mensch, welchen Stand er
        sieht."""
        bericht = self._lauf(None)

        assert len(bericht.outcomes) == 1  # type: ignore[attr-defined]
        assert bericht.errors == ()  # type: ignore[attr-defined]
