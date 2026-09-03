"""Anwendungsfall: historische Signalpruefung ueber den gespeicherten Bestand.

Reine Orchestrierung -- Replay, Episodenbildung und Kennzahlen liegen
vollstaendig in ``domain.backtesting``. Fehlerisolation je Aktie im Muster
von ``BackfillHistoryUseCase``: ein Ausfall bei einer Aktie beendet nicht
den Lauf.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ai_trading_analyst.domain.analysis import MarketDataProvider, Stock, UnitOfWork
from ai_trading_analyst.domain.backtesting import (
    BacktestParameters,
    BacktestResult,
    compute_backtest_results,
)
from ai_trading_analyst.domain.screening import SIGNAL_RULE_VERSION, CandidateRuleParameters
from ai_trading_analyst.observability.logging_setup import get_logger

_logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class StockBacktest:
    """Ergebnis der historischen Signalpruefung fuer eine Aktie."""

    symbol: str
    results: tuple[BacktestResult, ...] = field(default_factory=tuple)
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.error is not None


@dataclass(frozen=True, slots=True)
class BacktestReport:
    stocks: tuple[StockBacktest, ...] = field(default_factory=tuple)

    @property
    def failures(self) -> tuple[StockBacktest, ...]:
        return tuple(stock for stock in self.stocks if stock.failed)


class BacktestUseCase:
    def __init__(
        self,
        market_data_provider: MarketDataProvider,
        uow_factory: Callable[[], UnitOfWork],
        candidate_rule_params: CandidateRuleParameters,
        backtest_params: BacktestParameters,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._market_data_provider = market_data_provider
        self._uow_factory = uow_factory
        self._candidate_rule_params = candidate_rule_params
        self._backtest_params = backtest_params
        self._now = now

    def execute(self, stocks: Sequence[Stock] | None = None) -> BacktestReport:
        """``stocks`` uebersteuert die volle Watchlist -- fuer einen gezielten
        Einzelabruf ueber die Kommandozeile, nicht fuer den regulaeren Lauf."""
        selected = stocks if stocks is not None else self._market_data_provider.list_stocks()
        return BacktestReport(stocks=tuple(self._backtest_one(stock) for stock in selected))

    def _backtest_one(self, stock: Stock) -> StockBacktest:
        try:
            series = self._market_data_provider.get_candle_series(stock)
            results = compute_backtest_results(
                series,
                stock_id=stock.id,
                candidate_params=self._candidate_rule_params,
                backtest_params=self._backtest_params,
                signal_rule_version=SIGNAL_RULE_VERSION,
                evaluated_at=self._now(),
            )
            with self._uow_factory() as uow:
                uow.stocks.add(stock)
                for result in results:
                    uow.backtest_results.add(result)
                uow.commit()
        except Exception as error:  # Systemgrenze: eine Aktie, nicht der Lauf
            _logger.warning("%s: %s -- %s", stock.symbol, type(error).__name__, error)
            return StockBacktest(symbol=stock.symbol, error=f"{type(error).__name__}: {error}")

        return StockBacktest(symbol=stock.symbol, results=results)
