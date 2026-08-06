"""SQLAlchemy-Implementierungen der Domain-Ports (``domain.analysis.ports``)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ai_trading_analyst.domain.analysis import (
    AnalysisRun,
    RunStatus,
    Stock,
    StockProcessingError,
    StockScreeningOutcome,
)
from ai_trading_analyst.domain.screening import (
    ScreeningResult,
    ScreeningStatus,
    SignalEvent,
    SignalType,
)

from .orm import AnalysisRunOrm, ProcessingErrorOrm, ScreeningResultOrm, SignalEventOrm, StockOrm


class SqlAlchemyStockRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, stock: Stock) -> None:
        """Idempotent: ein bereits bekanntes Symbol wird nicht erneut eingefuegt."""
        statement = (
            pg_insert(StockOrm)
            .values(id=stock.id, symbol=stock.symbol, exchange=stock.exchange)
            .on_conflict_do_nothing(index_elements=["id"])
        )
        self._session.execute(statement)

    def get_by_symbol(self, symbol: str) -> Stock | None:
        row = self._session.execute(
            select(StockOrm).where(StockOrm.symbol == symbol)
        ).scalar_one_or_none()
        return None if row is None else Stock(id=row.id, symbol=row.symbol, exchange=row.exchange)

    def list_all(self) -> Sequence[Stock]:
        rows = self._session.execute(select(StockOrm)).scalars().all()
        return tuple(Stock(id=row.id, symbol=row.symbol, exchange=row.exchange) for row in rows)


def _run_from_row(row: AnalysisRunOrm) -> AnalysisRun:
    return AnalysisRun(
        id=row.id,
        status=RunStatus(row.status),
        started_at=row.started_at,
        completed_at=row.completed_at,
        number_of_stocks=row.number_of_stocks,
        candidates_found=row.candidates_found,
        error_message=row.error_message,
    )


class SqlAlchemyAnalysisRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, run: AnalysisRun) -> None:
        self._session.add(
            AnalysisRunOrm(
                id=run.id,
                status=run.status,
                started_at=run.started_at,
                completed_at=run.completed_at,
                number_of_stocks=run.number_of_stocks,
                candidates_found=run.candidates_found,
                error_message=run.error_message,
            )
        )

    def get(self, run_id: uuid.UUID) -> AnalysisRun | None:
        row = self._session.get(AnalysisRunOrm, run_id)
        return None if row is None else _run_from_row(row)

    def list_all(self) -> Sequence[AnalysisRun]:
        rows = (
            self._session.execute(select(AnalysisRunOrm).order_by(AnalysisRunOrm.started_at))
            .scalars()
            .all()
        )
        return tuple(_run_from_row(row) for row in rows)

    def update(self, run: AnalysisRun) -> None:
        row = self._session.get(AnalysisRunOrm, run.id)
        if row is None:
            raise LookupError(
                f"AnalysisRun {run.id} wurde nicht gefunden und kann nicht aktualisiert werden."
            )
        row.status = run.status
        row.completed_at = run.completed_at
        row.number_of_stocks = run.number_of_stocks
        row.candidates_found = run.candidates_found
        row.error_message = run.error_message


def _outcome_from_row(row: ScreeningResultOrm) -> StockScreeningOutcome:
    stock = Stock(id=row.stock.id, symbol=row.stock.symbol, exchange=row.stock.exchange)
    events = tuple(
        SignalEvent(signal_type=SignalType(event.signal_type), candle_index=event.candle_index)
        for event in row.signal_events
    )
    result = ScreeningResult(
        status=ScreeningStatus(row.status),
        fired_signal_types=frozenset(event.signal_type for event in events),
        signal_events=events,
        reason=row.reason,
        affected_index=row.affected_index,
    )
    return StockScreeningOutcome(
        analysis_run_id=row.analysis_run_id,
        stock=stock,
        result=result,
        decision_candle_index=row.decision_candle_index,
        evaluated_at=row.evaluated_at,
        signal_rule_version=row.signal_rule_version,
    )


class SqlAlchemyScreeningResultRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, outcome: StockScreeningOutcome) -> None:
        row = ScreeningResultOrm(
            id=uuid.uuid4(),
            analysis_run_id=outcome.analysis_run_id,
            stock_id=outcome.stock.id,
            status=outcome.result.status,
            reason=outcome.result.reason,
            affected_index=outcome.result.affected_index,
            decision_candle_index=outcome.decision_candle_index,
            evaluated_at=outcome.evaluated_at,
            signal_rule_version=outcome.signal_rule_version,
        )
        row.signal_events = [
            SignalEventOrm(
                id=uuid.uuid4(), signal_type=event.signal_type, candle_index=event.candle_index
            )
            for event in outcome.result.signal_events
        ]
        self._session.add(row)

    def list_for_run(self, run_id: uuid.UUID) -> Sequence[StockScreeningOutcome]:
        rows = (
            self._session.execute(
                select(ScreeningResultOrm).where(ScreeningResultOrm.analysis_run_id == run_id)
            )
            .scalars()
            .all()
        )
        return tuple(_outcome_from_row(row) for row in rows)


class SqlAlchemyProcessingErrorRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, error: StockProcessingError) -> None:
        self._session.add(
            ProcessingErrorOrm(
                id=uuid.uuid4(),
                analysis_run_id=error.analysis_run_id,
                stock_symbol=error.stock_symbol,
                message=error.message,
                occurred_at=error.occurred_at,
            )
        )

    def list_for_run(self, run_id: uuid.UUID) -> Sequence[StockProcessingError]:
        rows = (
            self._session.execute(
                select(ProcessingErrorOrm).where(ProcessingErrorOrm.analysis_run_id == run_id)
            )
            .scalars()
            .all()
        )
        return tuple(
            StockProcessingError(
                analysis_run_id=row.analysis_run_id,
                stock_symbol=row.stock_symbol,
                message=row.message,
                occurred_at=row.occurred_at,
            )
            for row in rows
        )
