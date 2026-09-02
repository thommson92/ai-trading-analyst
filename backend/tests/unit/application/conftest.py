"""In-Memory-Fakes fuer die Domain-Ports -- keine Datenbank, keine Fixtures.

Testet ausschliesslich die Orchestrierung des Use Case (Reihenfolge,
Statusuebergaenge, Fehlerisolation), nicht die Persistenz selbst (dafuer
``tests/integration``).
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from types import TracebackType
from typing import Self

from ai_trading_analyst.domain.analysis import (
    AnalysisRun,
    AnalysisRunRepository,
    AnalystRecommendationsFormatError,
    AnalystRecommendationsProviderError,
    BacktestResultRepository,
    EarningsProviderError,
    FundamentalDataProviderError,
    IntradayBarRepository,
    MarketDataProviderError,
    OptionsDataProviderError,
    ProcessingErrorRepository,
    ResearchProviderError,
    RunStatus,
    ScreeningResultRepository,
    Stock,
    StockProcessingError,
    StockReportRepository,
    StockRepository,
    StockScreeningOutcome,
    TechnicalInterpreterError,
)
from ai_trading_analyst.domain.analysts import AnalystRecommendations
from ai_trading_analyst.domain.backtesting import BacktestResult
from ai_trading_analyst.domain.earnings import EarningsFilterStatus, NextEarningsDate
from ai_trading_analyst.domain.fundamentals import FundamentalSnapshot
from ai_trading_analyst.domain.options import OptionsAnalysis, OptionsParameters
from ai_trading_analyst.domain.report import StockReport, StoredReport, as_document
from ai_trading_analyst.domain.research import ResearchReport, ResearchStatus
from ai_trading_analyst.domain.screening import (
    Candle,
    CandleSeries,
    IndicatorValues,
    IntradayBar,
    ScreeningStatus,
)
from ai_trading_analyst.domain.technical import (
    PriceZone,
    TechnicalAssessment,
    TechnicalAssessmentStatus,
    TechnicalSnapshot,
    TechnicalStatus,
    TrendStrength,
)
from ai_trading_analyst.infrastructure.fixtures.analyst_recommendations_provider import (
    FixtureAnalystRecommendationsProvider,
)
from ai_trading_analyst.infrastructure.fixtures.fundamental_provider import (
    FixtureFundamentalDataProvider,
)
from ai_trading_analyst.infrastructure.fixtures.options_provider import FixtureOptionsProvider

_EPOCH = datetime(2024, 1, 2, 12, 45, tzinfo=UTC)
_TIMEFRAME = timedelta(minutes=195)
_BASELINE = IndicatorValues(rsi=50.0, rsi_ma=50.0, ema5=100.0, ema20=100.0)
_CANDIDATE_INDICATORS = IndicatorValues(rsi=60.0, rsi_ma=50.0, ema5=110.0, ema20=100.0)


def make_stock(symbol: str) -> Stock:
    return Stock(id=uuid.uuid5(uuid.NAMESPACE_DNS, symbol), symbol=symbol, exchange="NASDAQ")


def make_series(length: int, *, candidate: bool) -> CandleSeries:
    """``candidate=True`` laesst genau auf der letzten Kerze zwei Signaltypen
    gleichzeitig feuern (RSI_CROSS und EMA5_EMA20_CROSS) -- alles davor bleibt
    Baseline und feuert nie (siehe domain/screening-Tests fuer das Prinzip)."""
    candles = tuple(
        Candle(
            timestamp=_EPOCH + i * _TIMEFRAME,
            daily_candle_index=1 if i % 2 == 0 else 2,
            open=100.0,
            high=100.0,
            low=100.0,
            close=100.0,
            volume=1_000.0,
        )
        for i in range(length)
    )
    indicators = [_BASELINE] * length
    if candidate:
        indicators[-1] = _CANDIDATE_INDICATORS
    return CandleSeries(candles=candles, indicators=tuple(indicators))


def make_incomplete_series(length: int) -> CandleSeries:
    candles = tuple(
        Candle(
            timestamp=_EPOCH + i * _TIMEFRAME,
            daily_candle_index=1 if i % 2 == 0 else 2,
            open=100.0,
            high=100.0,
            low=100.0,
            close=100.0,
            volume=1_000.0,
        )
        for i in range(length)
    )
    indicators = [_BASELINE] * length
    indicators[-2] = IndicatorValues(rsi=None, rsi_ma=None, ema5=None, ema20=None)
    return CandleSeries(candles=candles, indicators=tuple(indicators))


class FakeMarketDataProvider:
    def __init__(
        self,
        stocks: tuple[Stock, ...],
        series_by_symbol: dict[str, CandleSeries],
        error_symbols: frozenset[str] = frozenset(),
        list_stocks_error: Exception | None = None,
    ) -> None:
        self._stocks = stocks
        self._series_by_symbol = series_by_symbol
        self._error_symbols = error_symbols
        self._list_stocks_error = list_stocks_error

    def list_stocks(self) -> tuple[Stock, ...]:
        if self._list_stocks_error is not None:
            raise self._list_stocks_error
        return self._stocks

    def get_candle_series(self, stock: Stock) -> CandleSeries:
        if stock.symbol in self._error_symbols:
            raise MarketDataProviderError(f"Simulierter Providerfehler fuer {stock.symbol}")
        return self._series_by_symbol[stock.symbol]


class FakeEarningsProvider:
    """Erwartet keine echte Abdeckung -- ``next_by_symbol`` haelt explizit
    hinterlegte Termine, alles andere ergibt ``None`` (keine Abdeckung)."""

    def __init__(
        self,
        next_by_symbol: dict[str, NextEarningsDate] | None = None,
        error_symbols: frozenset[str] = frozenset(),
    ) -> None:
        self._next_by_symbol = next_by_symbol or {}
        self._error_symbols = error_symbols
        self.calls: list[str] = []

    def next_earnings_date(self, stock: Stock) -> NextEarningsDate | None:
        self.calls.append(stock.symbol)
        if stock.symbol in self._error_symbols:
            raise EarningsProviderError(f"Simulierter Providerfehler fuer {stock.symbol}")
        return self._next_by_symbol.get(stock.symbol)


class FakeFundamentalDataProvider:
    """Testdoppel der Fundamentaldatenquelle (Muster ``FakeEarningsProvider``).

    ``error_symbols`` wirft die Vertragsausnahme, ``crash_symbols`` eine rohe
    ``RuntimeError`` -- also einen Vertragsbruch. Das erste darf nur die
    Kennzahlen kosten, das zweite die Aktie (ADR 0035, Entscheidung 3).
    """

    def __init__(
        self,
        error_symbols: frozenset[str] = frozenset(),
        crash_symbols: frozenset[str] = frozenset(),
    ) -> None:
        self._error_symbols = error_symbols
        self._crash_symbols = crash_symbols
        self.calls: list[tuple[str, float | None]] = []

    def fundamentals(self, stock: Stock, price: float | None = None) -> FundamentalSnapshot:
        self.calls.append((stock.symbol, price))
        if stock.symbol in self._error_symbols:
            raise FundamentalDataProviderError(f"Simulierter Providerfehler fuer {stock.symbol}")
        if stock.symbol in self._crash_symbols:
            raise RuntimeError(f"Vertragsbruch fuer {stock.symbol}")
        return FixtureFundamentalDataProvider().fundamentals(stock, price=price)


class FakeOptionsDataProvider:
    """Testdoppel der Optionsdatenquelle (Muster ``FakeFundamentalDataProvider``).

    ``error_symbols`` wirft die Vertragsausnahme, ``crash_symbols`` eine rohe
    ``RuntimeError`` -- also einen Vertragsbruch. Das erste darf nur Punkt 13
    und die Optionsattraktivitaet kosten, das zweite die Aktie (ADR 0048).
    """

    def __init__(
        self,
        error_symbols: frozenset[str] = frozenset(),
        crash_symbols: frozenset[str] = frozenset(),
    ) -> None:
        self._error_symbols = error_symbols
        self._crash_symbols = crash_symbols
        self.calls: list[tuple[str, float, date, int, date | None]] = []

    def options(
        self,
        stock: Stock,
        *,
        price: float,
        as_of: date,
        zones: Sequence[PriceZone] = (),
        next_earnings_date: date | None = None,
    ) -> OptionsAnalysis:
        self.calls.append((stock.symbol, price, as_of, len(zones), next_earnings_date))
        if stock.symbol in self._error_symbols:
            raise OptionsDataProviderError(f"Simulierter Providerfehler fuer {stock.symbol}")
        if stock.symbol in self._crash_symbols:
            raise RuntimeError(f"Vertragsbruch fuer {stock.symbol}")
        return FixtureOptionsProvider(OptionsParameters()).options(
            stock,
            price=price,
            as_of=as_of,
            zones=zones,
            next_earnings_date=next_earnings_date,
        )


class FakeAnalystRecommendationsProvider:
    """Testdoppel der Analystenempfehlungen (Muster ``FakeFundamentalDataProvider``).

    ``error_symbols`` wirft die Vertragsausnahme, ``crash_symbols`` eine rohe
    ``RuntimeError`` -- also einen Vertragsbruch. Das erste darf nur Punkt 9
    kosten, das zweite die Aktie (ADR 0043).
    """

    def __init__(
        self,
        error_symbols: frozenset[str] = frozenset(),
        crash_symbols: frozenset[str] = frozenset(),
        format_symbols: frozenset[str] = frozenset(),
    ) -> None:
        self._error_symbols = error_symbols
        self._crash_symbols = crash_symbols
        self._format_symbols = format_symbols
        """Der Anbieter war erreichbar, seine Antwort aber unlesbar -- ein
        eigener Grund im Bericht (ADR 0043)."""
        self.calls: list[str] = []

    def recommendations(self, stock: Stock) -> AnalystRecommendations:
        self.calls.append(stock.symbol)
        if stock.symbol in self._format_symbols:
            raise AnalystRecommendationsFormatError(
                f"Simulierte unlesbare Antwort fuer {stock.symbol}"
            )
        if stock.symbol in self._error_symbols:
            raise AnalystRecommendationsProviderError(
                f"Simulierter Providerfehler fuer {stock.symbol}"
            )
        if stock.symbol in self._crash_symbols:
            raise RuntimeError(f"Vertragsbruch fuer {stock.symbol}")
        return FixtureAnalystRecommendationsProvider().recommendations(stock)


class FakeTechnicalInterpreter:
    """Testdoppel des Technical Agent (Muster ``FakeResearchProvider``).

    ``error_symbols`` wirft die Vertragsausnahme, ``crash_symbols`` eine rohe
    ``RuntimeError`` -- also einen Vertragsbruch. Beide muessen den Lauf
    unberuehrt lassen.
    """

    def __init__(
        self,
        error_symbols: frozenset[str] = frozenset(),
        crash_symbols: frozenset[str] = frozenset(),
    ) -> None:
        self.error_symbols = error_symbols
        self.crash_symbols = crash_symbols
        self.calls: list[str] = []

    def interpret(self, stock: Stock, snapshot: TechnicalSnapshot) -> TechnicalAssessment:
        self.calls.append(stock.symbol)
        if stock.symbol in self.error_symbols:
            raise TechnicalInterpreterError(f"{stock.symbol}: Anbieter nicht erreichbar")
        if stock.symbol in self.crash_symbols:
            raise RuntimeError(f"{stock.symbol}: roher Fehler entgegen dem Vertrag")
        if snapshot.status is not TechnicalStatus.COMPLETED:
            return TechnicalAssessment(
                status=TechnicalAssessmentStatus.INSUFFICIENT_DATA,
                evaluated_at=datetime.now(UTC),
                model=None,
                prompt_version=None,
                reason="snapshot_insufficient",
            )
        return TechnicalAssessment(
            status=TechnicalAssessmentStatus.COMPLETED,
            evaluated_at=datetime.now(UTC),
            model="fake",
            prompt_version="fake-v1",
            interpreted_analysis_version=snapshot.analysis_version,
            trend_strength=TrendStrength.MODERATE,
            summary=f"Fake-Einordnung fuer {stock.symbol}",
        )


class FakeResearchProvider:
    """Liefert standardmaessig einen kanonischen ``COMPLETED``-Bericht;
    ``error_symbols`` loest ``ResearchProviderError`` aus (Muster
    ``FakeEarningsProvider``), ``crash_symbols`` eine rohe Ausnahme --
    also einen Anbieter, der seinen Vertrag bricht."""

    def __init__(
        self,
        error_symbols: frozenset[str] = frozenset(),
        crash_symbols: frozenset[str] = frozenset(),
    ) -> None:
        self._error_symbols = error_symbols
        self._crash_symbols = crash_symbols
        self.calls: list[str] = []

    def research(self, stock: Stock) -> ResearchReport:
        self.calls.append(stock.symbol)
        if stock.symbol in self._crash_symbols:
            raise RuntimeError(f"Vertragsbruch des Anbieters fuer {stock.symbol}")
        if stock.symbol in self._error_symbols:
            raise ResearchProviderError(f"Simulierter Providerfehler fuer {stock.symbol}")
        return ResearchReport(
            status=ResearchStatus.COMPLETED,
            evaluated_at=datetime.now(UTC),
            model="fake-model",
            prompt_version="fake-v1",
            summary=f"Fake-Recherche fuer {stock.symbol}",
        )


class FakeStockRepository:
    def __init__(self) -> None:
        self.added: list[Stock] = []

    def add(self, stock: Stock) -> None:
        if stock.symbol not in {s.symbol for s in self.added}:
            self.added.append(stock)

    def get_by_symbol(self, symbol: str) -> Stock | None:
        return next((s for s in self.added if s.symbol == symbol), None)

    def list_all(self) -> tuple[Stock, ...]:
        return tuple(self.added)


class FakeAnalysisRunRepository:
    def __init__(self) -> None:
        self._runs: dict[uuid.UUID, AnalysisRun] = {}

    def add(self, run: AnalysisRun) -> None:
        self._runs[run.id] = run

    def get(self, run_id: uuid.UUID) -> AnalysisRun | None:
        return self._runs.get(run_id)

    def list_recent(
        self, *, limit: int, offset: int, status: Sequence[RunStatus] | None = None
    ) -> tuple[AnalysisRun, ...]:
        passend = [run for run in self._runs.values() if status is None or run.status in status]
        passend.sort(key=lambda run: run.started_at, reverse=True)
        return tuple(passend[offset : offset + limit])

    def count(self, *, status: Sequence[RunStatus] | None = None) -> int:
        return sum(1 for run in self._runs.values() if status is None or run.status in status)

    def update(self, run: AnalysisRun) -> None:
        self._runs[run.id] = run


class FakeScreeningResultRepository:
    def __init__(self) -> None:
        self.added: list[StockScreeningOutcome] = []

    def add(self, outcome: StockScreeningOutcome) -> None:
        self.added.append(outcome)

    def list_for_run(self, run_id: uuid.UUID) -> tuple[StockScreeningOutcome, ...]:
        return tuple(o for o in self.added if o.analysis_run_id == run_id)

    def count_by_earnings_status(self, run_id: uuid.UUID) -> dict[EarningsFilterStatus, int]:
        gezaehlt: Counter[EarningsFilterStatus] = Counter()
        for outcome in self.list_for_run(run_id):
            if outcome.earnings is not None:
                gezaehlt[outcome.earnings.status] += 1
        return dict(gezaehlt)

    def latest_candidate_analyses(
        self, *, since: datetime, until: datetime
    ) -> dict[str, datetime]:
        # Gleiche Zusagen wie die SQL-Implementierung: nur volle Analysen
        # (ScreeningStatus.CANDIDATE), Fenster since <= t < until,
        # juengstes evaluated_at je Symbol.
        juengste: dict[str, datetime] = {}
        for outcome in self.added:
            if outcome.result.status is not ScreeningStatus.CANDIDATE:
                continue
            if not since <= outcome.evaluated_at < until:
                continue
            bisher = juengste.get(outcome.stock.symbol)
            if bisher is None or outcome.evaluated_at > bisher:
                juengste[outcome.stock.symbol] = outcome.evaluated_at
        return juengste


class FakeBacktestResultRepository:
    def __init__(self) -> None:
        self.added: list[tuple[BacktestResult, uuid.UUID | None]] = []

    def add(self, result: BacktestResult, analysis_run_id: uuid.UUID | None = None) -> None:
        self.added.append((result, analysis_run_id))

    @property
    def results(self) -> tuple[BacktestResult, ...]:
        return tuple(result for result, _ in self.added)

    def list_for_stock(self, stock_id: uuid.UUID) -> tuple[BacktestResult, ...]:
        return tuple(r for r, _ in self.added if r.stock_id == stock_id)



def _berichtskennung(report: StockReport) -> uuid.UUID:
    """Dieselbe Eindeutigkeit wie in der Datenbank: ein Bericht je Lauf und
    Aktie (``uq_stock_report_run_stock``). Abgeleitet statt gewuerfelt, damit
    zweimaliges Lesen desselben Berichts dieselbe Kennung ergibt."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"{report.analysis_run_id}/{report.stock_id}")


class FakeStockReportRepository:
    def __init__(self) -> None:
        self.added: list[StockReport] = []

    def add(self, report: StockReport) -> None:
        self.added.append(report)

    def _gespeichert(self, bericht: StockReport) -> StoredReport:
        return StoredReport(
            id=_berichtskennung(bericht),
            symbol=bericht.symbol,
            created_at=bericht.created_at,
            report_schema_version=bericht.report_schema_version,
            app_version=bericht.app_version,
            recommendation=(
                bericht.recommendation.level if bericht.recommendation is not None else None
            ),
            swing_score=bericht.swing_score.value if bericht.swing_score is not None else None,
            investment_score=(
                bericht.investment_score.value if bericht.investment_score is not None else None
            ),
            document=as_document(bericht),
        )

    def list_for_run(self, analysis_run_id: uuid.UUID) -> tuple[StoredReport, ...]:
        return tuple(
            self._gespeichert(bericht)
            for bericht in self.added
            if bericht.analysis_run_id == analysis_run_id
        )

    def get(self, report_id: uuid.UUID) -> StoredReport | None:
        return next(
            (
                self._gespeichert(bericht)
                for bericht in self.added
                if _berichtskennung(bericht) == report_id
            ),
            None,
        )

    def list_for_symbol(self, symbol: str, *, limit: int, offset: int) -> tuple[StoredReport, ...]:
        passend = sorted(
            (bericht for bericht in self.added if bericht.symbol == symbol),
            key=lambda bericht: bericht.created_at,
            reverse=True,
        )
        return tuple(self._gespeichert(bericht) for bericht in passend[offset : offset + limit])

    def count_for_symbol(self, symbol: str) -> int:
        return sum(1 for bericht in self.added if bericht.symbol == symbol)


class FakeProcessingErrorRepository:
    def __init__(self) -> None:
        self.added: list[StockProcessingError] = []

    def add(self, error: StockProcessingError) -> None:
        self.added.append(error)

    def list_for_run(self, run_id: uuid.UUID) -> tuple[StockProcessingError, ...]:
        return tuple(e for e in self.added if e.analysis_run_id == run_id)

    def count_for_run(self, run_id: uuid.UUID) -> int:
        return len(self.list_for_run(run_id))


class InMemoryIntradayBarRepository:
    """Bar-Speicher fuer Use-Case-Tests.

    Bildet die eine Eigenschaft nach, auf die es ankommt: Ein zweites Mal
    geschriebener Bar zaehlt nicht noch einmal. Ohne sie wuerde ein Test die
    Wiederholbarkeit des Backfills nur scheinbar pruefen.
    """

    def __init__(self) -> None:
        self._bars: dict[str, dict[datetime, IntradayBar]] = {}

    def latest_start(self, symbol: str) -> datetime | None:
        vorhanden = self._bars.get(symbol)
        return max(vorhanden) if vorhanden else None

    def latest_start_overall(self) -> datetime | None:
        alle = [start for bestand in self._bars.values() for start in bestand]
        return max(alle) if alle else None

    def earliest_start(self, symbol: str) -> datetime | None:
        vorhanden = self._bars.get(symbol)
        return min(vorhanden) if vorhanden else None

    def add_all(self, symbol: str, bars: Sequence[IntradayBar]) -> int:
        bestand = self._bars.setdefault(symbol, {})
        neu = [bar for bar in bars if bar.start not in bestand]
        for bar in neu:
            bestand[bar.start] = bar
        return len(neu)

    def list_for(self, symbol: str) -> Sequence[IntradayBar]:
        bestand = self._bars.get(symbol, {})
        return tuple(bestand[start] for start in sorted(bestand))


class FakeUnitOfWork:
    """Keine echten Transaktionsgrenzen -- fuer Use-Case-Tests genuegt ein
    geteiltes In-Memory-Repository-Set, das jeder Aufruf der Factory wieder
    zurueckgibt.

    Die Attribute sind bewusst auf die Protocol-Typen annotiert (nicht auf
    die konkreten Fake-Klassen): ``UnitOfWork`` deklariert sie als
    veraenderliche Attribute, wofuer mypy invariante Uebereinstimmung
    verlangt -- mit den konkreten Fake-Typen waere die Protocol-Konformanz
    sonst ein Typfehler."""

    def __init__(
        self,
        stocks: StockRepository,
        intraday_bars: IntradayBarRepository,
        analysis_runs: AnalysisRunRepository,
        screening_results: ScreeningResultRepository,
        processing_errors: ProcessingErrorRepository,
        backtest_results: BacktestResultRepository | None = None,
        stock_reports: StockReportRepository | None = None,
    ) -> None:
        self.stocks = stocks
        self.intraday_bars = intraday_bars
        self.analysis_runs = analysis_runs
        self.screening_results = screening_results
        self.processing_errors = processing_errors
        self.backtest_results = backtest_results or FakeBacktestResultRepository()
        self.stock_reports = stock_reports or FakeStockReportRepository()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass
