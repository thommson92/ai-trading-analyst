"""Tests des Anwendungsfalls RunAnalysisUseCase (Sprint 1B).

Prueft ausschliesslich Orchestrierung: Statusuebergaenge, Fehlerisolation je
Aktie und vollstaendiges Scheitern vor Beginn des Screenings. Die
Signalauswertung selbst ist bereits in ``tests/unit/domain/screening``
abgedeckt -- hier zaehlt nur, dass der Use Case sie korrekt aufruft und mit
dem Ergebnis richtig umgeht.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from ai_trading_analyst.application.run_analysis import RunAnalysisUseCase
from ai_trading_analyst.domain.analysis import MarketDataProviderError, RunStatus
from ai_trading_analyst.domain.earnings import (
    EarningsFilterParameters,
    EarningsFilterStatus,
    NextEarningsDate,
)
from ai_trading_analyst.domain.research import ResearchStatus
from ai_trading_analyst.domain.screening import CandidateRuleParameters, ScreeningStatus
from tests.unit.application.conftest import (
    FakeAnalysisRunRepository,
    FakeEarningsProvider,
    FakeMarketDataProvider,
    FakeProcessingErrorRepository,
    FakeResearchProvider,
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
    research_provider: FakeResearchProvider | None = None,
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
        ``RunAnalysisUseCase._run_research_concurrently``) -- trotzdem muss
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
            uow_factory,
            _PARAMS,
            _EARNINGS_PARAMS,
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
