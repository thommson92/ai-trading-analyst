"""API-Schemas (Presentation-Schicht) -- reine Uebersetzung, keine Fachlogik."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from ai_trading_analyst.application.read_run_overview import RunOverview
from ai_trading_analyst.domain.analysis import AnalysisRun, RunStatus
from ai_trading_analyst.domain.backtesting import (
    BacktestConfidence,
    BacktestResult,
    HorizonMetrics,
    OptionsBacktestResult,
    OptionsBacktestScope,
    PooledMetrics,
    SignalCombination,
    VariantMetrics,
    kombinationskuerzel,
)
from ai_trading_analyst.domain.backtesting.options_trade import OptionTrade, TradeOutcome
from ai_trading_analyst.domain.report import StoredReport
from ai_trading_analyst.domain.scoring import Recommendation


class Page[T](BaseModel):
    """Eine Seite einer Liste.

    ``total`` gehoert dazu, nicht nur die Eintraege: Ohne die Gesamtzahl
    koennte die Oberflaeche nicht sagen, ob eine weitere Seite existiert --
    sie muesste raten oder blind weiterblaettern.
    """

    items: list[T]
    total: int
    limit: int
    offset: int


class AnalysisRunResponse(BaseModel):
    id: UUID
    status: RunStatus
    started_at: datetime
    completed_at: datetime | None
    number_of_stocks: int
    candidates_found: int
    error_message: str | None

    @classmethod
    def from_domain(cls, run: AnalysisRun) -> AnalysisRunResponse:
        return cls(
            id=run.id,
            status=run.status,
            started_at=run.started_at,
            completed_at=run.completed_at,
            number_of_stocks=run.number_of_stocks,
            candidates_found=run.candidates_found,
            error_message=run.error_message,
        )


class AnalysisRunDetailResponse(AnalysisRunResponse):
    """Ein Lauf mit den Zahlen, die nicht an ihm selbst stehen."""

    earnings_excluded: int
    earnings_unknown: int
    module_errors: int

    @classmethod
    def from_overview(cls, overview: RunOverview) -> AnalysisRunDetailResponse:
        run = overview.run
        return cls(
            id=run.id,
            status=run.status,
            started_at=run.started_at,
            completed_at=run.completed_at,
            number_of_stocks=run.number_of_stocks,
            candidates_found=run.candidates_found,
            error_message=run.error_message,
            earnings_excluded=overview.earnings_excluded,
            earnings_unknown=overview.earnings_unknown,
            module_errors=overview.module_errors,
        )


class ReportSummaryResponse(BaseModel):
    """Die Kurzfassung eines Berichts -- was in einer Liste steht.

    Genau die Werte, die als eigene Spalten an ``stock_reports`` liegen. Wer
    mehr braucht, holt das Dokument; alles andere hiesse, es hier in Teilen
    nachzubauen.
    """

    report_id: UUID
    symbol: str
    created_at: datetime
    recommendation: Recommendation | None
    swing_score: float | None
    investment_score: float | None

    @classmethod
    def from_domain(cls, report: StoredReport) -> ReportSummaryResponse:
        return cls(
            report_id=report.id,
            symbol=report.symbol,
            created_at=report.created_at,
            recommendation=report.recommendation,
            swing_score=report.swing_score,
            investment_score=report.investment_score,
        )


class HealthResponse(BaseModel):
    status: str = "ok"


class ReadinessResponse(BaseModel):
    status: str
    database: str


class VariantMetricsResponse(BaseModel):
    """Kennzahlen einer Ausstiegsvariante.

    ``null`` heisst durchgehend **keine Grundlage**, nicht null -- deshalb ist
    das ganze Objekt ``null``, wenn die Stichprobe nicht traegt, statt seine
    Felder einzeln zu leeren.
    """

    trades: int
    win_rate: float | None
    mean_profit: float | None
    median_profit: float | None
    total_profit: float | None
    worst_profit: float | None
    mean_return_on_capital: float | None
    outcomes: dict[str, int]

    @classmethod
    def from_domain(cls, kennzahlen: VariantMetrics) -> VariantMetricsResponse:
        return cls(
            trades=kennzahlen.trades,
            win_rate=kennzahlen.win_rate,
            mean_profit=kennzahlen.mean_profit,
            median_profit=kennzahlen.median_profit,
            total_profit=kennzahlen.total_profit,
            worst_profit=kennzahlen.worst_profit,
            mean_return_on_capital=kennzahlen.mean_return_on_capital,
            outcomes={
                "EXPIRED_WORTHLESS": kennzahlen.expired_worthless,
                "ASSIGNED": kennzahlen.assigned,
                "TAKE_PROFIT": kennzahlen.take_profits,
                "STOPPED_OUT": kennzahlen.stops,
                "CLOSED_AT_EXPIRATION": kennzahlen.closed_at_expiration,
            },
        )

    @classmethod
    def optional(cls, kennzahlen: VariantMetrics | None) -> VariantMetricsResponse | None:
        return None if kennzahlen is None else cls.from_domain(kennzahlen)


class OptionsMeasurementResponse(BaseModel):
    """Eine Messung des Optionsbacktests (ADR 0058, Festlegung 9).

    ``assumptions`` steht bewusst am Kopf und nicht im Kleingedruckten: Zwei
    Messungen desselben Tages unterscheiden sich **nur** darin, und jede Zahl
    darunter ist eine Modellzahl.
    """

    measurement_id: UUID
    measured_at: datetime
    signal_rule_version: str
    stocks: int
    history_start: datetime
    history_end: datetime
    assumptions: dict[str, str]

    @classmethod
    def from_domain(
        cls, scope: OptionsBacktestScope, assumptions: Mapping[str, str]
    ) -> OptionsMeasurementResponse:
        return cls(
            measurement_id=scope.measurement_id,
            measured_at=scope.measured_at,
            signal_rule_version=scope.signal_rule_version,
            stocks=scope.stocks,
            history_start=scope.history_start,
            history_end=scope.history_end,
            assumptions=dict(assumptions),
        )


class OptionsCombinationResponse(BaseModel):
    """Das Ergebnis einer Signalkombination.

    ``letters`` sind die Kriterienbuchstaben der G1-Pruefvorlage. Ausgeschrieben
    ist die laengste Kombination 84 Zeichen lang; in einer Tabelle muesste sie
    abgeschnitten werden, und zwei verschiedene saehen dann gleich aus.
    """

    signal_types: list[str]
    letters: str
    episodes: int
    trades: int
    without_trade: int
    confidence: BacktestConfidence
    held: VariantMetricsResponse | None
    managed: VariantMetricsResponse | None

    @classmethod
    def from_domain(cls, result: OptionsBacktestResult) -> OptionsCombinationResponse:
        return cls(
            signal_types=sorted(signal.value for signal in result.signal_types),
            letters=kombinationskuerzel(result.signal_types),
            episodes=result.episodes,
            trades=result.trades,
            without_trade=result.without_trade,
            confidence=result.confidence,
            held=VariantMetricsResponse.optional(result.held),
            managed=VariantMetricsResponse.optional(result.managed),
        )


class OptionsStockRowResponse(BaseModel):
    """Eine Aktie in der Gesamtuebersicht.

    Die Kennzahlen sind ueber **alle** Kombinationen gepoolt und aus den
    Einzeltrades gerechnet -- nicht aus den Kombinationszeilen gemittelt. Ein
    Mittel von Mitteln gewichtete eine Aktie mit drei Trades so schwer wie
    eine mit dreissig (ADR 0058, Nachtrag zu Festlegung 9).
    """

    stock_id: UUID
    symbol: str
    trades: int
    confidence: BacktestConfidence
    held: VariantMetricsResponse | None
    managed: VariantMetricsResponse | None

    @classmethod
    def from_domain(
        cls, stock_id: UUID, symbol: str, gepoolt: PooledMetrics
    ) -> OptionsStockRowResponse:
        return cls(
            stock_id=stock_id,
            symbol=symbol,
            trades=gepoolt.trades,
            confidence=gepoolt.confidence,
            held=VariantMetricsResponse.optional(gepoolt.held),
            managed=VariantMetricsResponse.optional(gepoolt.managed),
        )


class OptionsMeasurementDetailResponse(BaseModel):
    """Eine Messung mit allem, was die Gesamtuebersicht braucht.

    ``overall`` ist die Zeile ueber alle Aktien je Kombination, ``stocks`` die
    Aktienzeilen ueber alle Kombinationen. Beide sind aus denselben
    Einzeltrades gerechnet und keine ist eine Zusammenfassung der anderen.
    """

    measurement: OptionsMeasurementResponse
    overall: list[OptionsCombinationResponse]
    stocks: list[OptionsStockRowResponse]


class OptionsTradeResponse(BaseModel):
    """Ein einzelner simulierter Put-Verkauf.

    ``underlying_at_entry`` und ``underlying_at_expiration`` sind **gemessen**,
    alles andere ist modelliert. Der Unterschied steht im Feldkommentar der
    Datenbank und gehoert auch hierher.
    """

    letters: str
    entry_index: int
    entry_date: date
    underlying_at_entry: float
    strike: float
    delta: float
    volatility: float
    premium: float
    capital_at_risk: float
    expiration: date
    days_to_expiration: int
    underlying_at_expiration: float
    held_outcome: TradeOutcome
    held_profit: float
    managed_outcome: TradeOutcome
    managed_profit: float
    managed_exit_index: int

    @classmethod
    def from_domain(
        cls, kombination: SignalCombination, trade: OptionTrade
    ) -> OptionsTradeResponse:
        return cls(
            letters=kombinationskuerzel(kombination),
            entry_index=trade.entry_index,
            entry_date=trade.entry_date,
            underlying_at_entry=trade.underlying_at_entry,
            strike=trade.strike,
            delta=trade.delta,
            volatility=trade.volatility,
            premium=trade.premium,
            capital_at_risk=trade.capital_at_risk,
            expiration=trade.expiration,
            days_to_expiration=trade.days_to_expiration,
            underlying_at_expiration=trade.underlying_at_expiration,
            held_outcome=trade.held_outcome,
            held_profit=trade.held_profit,
            managed_outcome=trade.managed_outcome,
            managed_profit=trade.managed_profit,
            managed_exit_index=trade.managed_exit_index,
        )


class HorizonMetricsResponse(BaseModel):
    """Ein Horizont des Signal-Backtests.

    Trefferquote und dauerhaftes Halten oberhalb des Einstiegs stehen
    **nebeneinander** und werden nirgends zu einer Erfolgsquote verrechnet
    (``CLAUDE.md``, "Backtesting").
    """

    horizon: int
    raw_event_count: int
    deduplicated_event_count: int
    hit_rate: float | None
    mean_return: float | None
    median_return: float | None
    max_loss: float | None
    drawdown: float | None
    held_above_entry_rate: float | None
    confidence: BacktestConfidence

    @classmethod
    def from_domain(cls, horizon: HorizonMetrics) -> HorizonMetricsResponse:
        return cls(
            horizon=horizon.horizon,
            raw_event_count=horizon.raw_event_count,
            deduplicated_event_count=horizon.deduplicated_event_count,
            hit_rate=horizon.hit_rate,
            mean_return=horizon.mean_return,
            median_return=horizon.median_return,
            max_loss=horizon.max_loss,
            drawdown=horizon.drawdown,
            held_above_entry_rate=horizon.held_above_entry_rate,
            confidence=horizon.confidence,
        )


class SignalBacktestResponse(BaseModel):
    """Der Signal-Backtest einer Kombination ueber alle Horizonte."""

    signal_types: list[str]
    letters: str
    signal_rule_version: str
    evaluated_at: datetime
    history_start: datetime
    history_end: datetime
    horizons: list[HorizonMetricsResponse]

    @classmethod
    def from_domain(cls, result: BacktestResult) -> SignalBacktestResponse:
        return cls(
            signal_types=sorted(signal.value for signal in result.signal_types),
            letters=kombinationskuerzel(result.signal_types),
            signal_rule_version=result.signal_rule_version,
            evaluated_at=result.evaluated_at,
            history_start=result.history_start,
            history_end=result.history_end,
            horizons=[HorizonMetricsResponse.from_domain(h) for h in result.horizons],
        )


class StockBacktestResponse(BaseModel):
    """Beides zu einer Aktie -- und ausdruecklich **getrennt**.

    Der Signal-Backtest sagt, ob das Signal traegt; der Optionsbacktest, ob
    sich damit Geld verdienen liesse. Zwei Fragen, nie eine gemeinsame Zahl.
    ``measurement`` ist ``null``, wenn noch kein Messlauf lief -- dann fehlt
    die Optionsseite ganz, und das ist eine Auskunft.
    """

    symbol: str
    signal_backtests: list[SignalBacktestResponse]
    measurement: OptionsMeasurementResponse | None
    combinations: list[OptionsCombinationResponse]
    pooled: OptionsStockRowResponse | None
    trades: list[OptionsTradeResponse]
