"""Tests des Anwendungsfalls RunAnalysisUseCase (Sprint 1B).

Prueft ausschliesslich Orchestrierung: Statusuebergaenge, Fehlerisolation je
Aktie und vollstaendiges Scheitern vor Beginn des Screenings. Die
Signalauswertung selbst ist bereits in ``tests/unit/domain/screening``
abgedeckt -- hier zaehlt nur, dass der Use Case sie korrekt aufruft und mit
dem Ergebnis richtig umgeht.
"""

from __future__ import annotations

from ai_trading_analyst.application.run_analysis import RunAnalysisUseCase
from ai_trading_analyst.domain.analysis import MarketDataProviderError, RunStatus
from ai_trading_analyst.domain.earnings import EarningsFilterParameters, EarningsFilterStatus
from ai_trading_analyst.domain.screening import CandidateRuleParameters, ScreeningStatus
from tests.unit.application.conftest import (
    FakeAnalysisRunRepository,
    FakeEarningsProvider,
    FakeMarketDataProvider,
    FakeProcessingErrorRepository,
    FakeScreeningResultRepository,
    FakeStockRepository,
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


def _build_use_case(
    provider: FakeMarketDataProvider,
    earnings_provider: FakeEarningsProvider | None = None,
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
        uow_factory,
        _PARAMS,
        _EARNINGS_PARAMS,
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
