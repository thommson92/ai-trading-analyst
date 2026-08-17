"""In-Memory-Fakes fuer die Domain-Ports -- keine Datenbank, keine Fixtures.

Testet ausschliesslich die Orchestrierung des Use Case (Reihenfolge,
Statusuebergaenge, Fehlerisolation), nicht die Persistenz selbst (dafuer
``tests/integration``).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Self

from ai_trading_analyst.domain.analysis import (
    AnalysisRun,
    AnalysisRunRepository,
    BacktestResultRepository,
    EarningsProviderError,
    IntradayBarRepository,
    MarketDataProviderError,
    ProcessingErrorRepository,
    ResearchProviderError,
    ScreeningResultRepository,
    Stock,
    StockProcessingError,
    StockRepository,
    StockScreeningOutcome,
)
from ai_trading_analyst.domain.backtesting import BacktestResult
from ai_trading_analyst.domain.earnings import NextEarningsDate
from ai_trading_analyst.domain.research import ResearchReport, ResearchStatus
from ai_trading_analyst.domain.screening import (
    Candle,
    CandleSeries,
    IndicatorValues,
    IntradayBar,
)

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

    def list_all(self) -> tuple[AnalysisRun, ...]:
        return tuple(self._runs.values())

    def update(self, run: AnalysisRun) -> None:
        self._runs[run.id] = run


class FakeScreeningResultRepository:
    def __init__(self) -> None:
        self.added: list[StockScreeningOutcome] = []

    def add(self, outcome: StockScreeningOutcome) -> None:
        self.added.append(outcome)

    def list_for_run(self, run_id: uuid.UUID) -> tuple[StockScreeningOutcome, ...]:
        return tuple(o for o in self.added if o.analysis_run_id == run_id)


class FakeBacktestResultRepository:
    def __init__(self) -> None:
        self.added: list[BacktestResult] = []

    def add(self, result: BacktestResult) -> None:
        self.added.append(result)

    def list_for_stock(self, stock_id: uuid.UUID) -> tuple[BacktestResult, ...]:
        return tuple(r for r in self.added if r.stock_id == stock_id)


class FakeProcessingErrorRepository:
    def __init__(self) -> None:
        self.added: list[StockProcessingError] = []

    def add(self, error: StockProcessingError) -> None:
        self.added.append(error)

    def list_for_run(self, run_id: uuid.UUID) -> tuple[StockProcessingError, ...]:
        return tuple(e for e in self.added if e.analysis_run_id == run_id)


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
    ) -> None:
        self.stocks = stocks
        self.intraday_bars = intraday_bars
        self.analysis_runs = analysis_runs
        self.screening_results = screening_results
        self.processing_errors = processing_errors
        self.backtest_results = backtest_results or FakeBacktestResultRepository()

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
