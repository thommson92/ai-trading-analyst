"""SQLAlchemy-Implementierungen der Domain-Ports (``domain.analysis.ports``)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ai_trading_analyst.domain.analysis import (
    AnalysisRun,
    RunStatus,
    Stock,
    StockProcessingError,
    StockScreeningOutcome,
)
from ai_trading_analyst.domain.earnings import EarningsFilterResult, EarningsFilterStatus
from ai_trading_analyst.domain.screening import (
    IntradayBar,
    ScreeningResult,
    ScreeningStatus,
    SignalEvent,
    SignalType,
)

from .orm import (
    AnalysisRunOrm,
    IntradayBarOrm,
    ProcessingErrorOrm,
    ScreeningResultOrm,
    SignalEventOrm,
    StockOrm,
)


class SqlAlchemyStockRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, stock: Stock) -> None:
        """Idempotent nach Symbol -- nicht nach id: ein Marktdatenanbieter, der
        fuer ein bereits bekanntes Symbol eine neue id liefert, soll den
        bestehenden Datensatz unberuehrt lassen statt mit einer IntegrityError
        abzubrechen (die Aktie waere sonst faelschlich ein StockProcessingError
        statt regulaer gescreent zu werden)."""
        statement = (
            pg_insert(StockOrm)
            .values(id=stock.id, symbol=stock.symbol, exchange=stock.exchange)
            .on_conflict_do_nothing(index_elements=["symbol"])
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
    earnings: EarningsFilterResult | None = None
    if row.earnings_status is not None:
        if row.earnings_evaluated_at is None:
            raise ValueError(
                f"Screening-Ergebnis {row.id}: earnings_evaluated_at fehlt trotz gesetztem "
                "earnings_status -- beide Spalten werden immer gemeinsam geschrieben."
            )
        earnings = EarningsFilterResult(
            status=EarningsFilterStatus(row.earnings_status),
            evaluated_at=row.earnings_evaluated_at,
            next_earnings_date=row.earnings_next_date,
            candles_until_earnings=row.earnings_candles_until,
            source=row.earnings_source,
            reason=row.earnings_reason,
        )
    return StockScreeningOutcome(
        analysis_run_id=row.analysis_run_id,
        stock=stock,
        result=result,
        decision_candle_index=row.decision_candle_index,
        evaluated_at=row.evaluated_at,
        signal_rule_version=row.signal_rule_version,
        earnings=earnings,
    )


class SqlAlchemyScreeningResultRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, outcome: StockScreeningOutcome) -> None:
        earnings = outcome.earnings
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
            earnings_status=earnings.status if earnings is not None else None,
            earnings_evaluated_at=earnings.evaluated_at if earnings is not None else None,
            earnings_next_date=earnings.next_earnings_date if earnings is not None else None,
            earnings_candles_until=(
                earnings.candles_until_earnings if earnings is not None else None
            ),
            earnings_source=earnings.source if earnings is not None else None,
            earnings_reason=earnings.reason if earnings is not None else None,
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


BARS_JE_INSERT = 1_000
"""Zeilen je Einfuegevorgang.

PostgreSQL nimmt hoechstens 65.535 Parameter je Anweisung entgegen. Bei
sieben Spalten je Bar reisst ein einzelnes Insert deshalb ab 9.363 Zeilen ab
-- nachgestellt und belegt. Der Standardzuschnitt (15-Minuten-Bars, ein Jahr
Historie) liegt mit rund 6.550 Bars knapp darunter und liefe heute noch
durch; fuenf Minuten Barbreite oder der in ADR 0014 (E3) vorgesehene
Fuenf-Jahres-Batch scheiterten sofort.

Tausend Zeilen belegen 7.000 Parameter -- reichlich Abstand, ohne die Zahl
der Anweisungen unnoetig hochzutreiben. Alle Bloecke laufen in derselben
Transaktion; ein Abbruch dazwischen laesst nichts halb Geschriebenes zurueck.
"""


class SqlAlchemyIntradayBarRepository:
    """Bar-Speicher fuer den Backfill.

    Alle Schreibvorgaenge sind ueber den Schluessel ``(symbol, start)``
    idempotent. Das ist keine Bequemlichkeit, sondern die Eigenschaft, die den
    Backfill wiederholbar macht: Ein abgebrochener Lauf wird schlicht erneut
    gestartet, und ueberlappende Zeitraeume kosten nichts.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def latest_start(self, symbol: str) -> datetime | None:
        return self._session.execute(
            select(func.max(IntradayBarOrm.start)).where(IntradayBarOrm.symbol == symbol)
        ).scalar_one_or_none()

    def add_all(self, symbol: str, bars: Sequence[IntradayBar]) -> int:
        if not bars:
            return 0
        self._reject_naive(symbol, bars)
        neu = 0
        for block in range(0, len(bars), BARS_JE_INSERT):
            neu += self._insert(symbol, bars[block : block + BARS_JE_INSERT])
        return neu

    @staticmethod
    def _reject_naive(symbol: str, bars: Sequence[IntradayBar]) -> None:
        """Naive Zeitstempel kommen hier nicht durch.

        Doc 10 untersagt sie, und ``ruff`` setzt das im eigenen Code ueber die
        ``DTZ``-Regeln durch. Eine Systemgrenze erreicht das nicht: PostgreSQL
        nimmt einen naiven Zeitstempel fuer eine ``timestamptz``-Spalte an und
        legt ihn in der Zeitzone der Datenbanksitzung aus -- serverabhaengig
        und damit nicht vorhersagbar. Zurueck kaeme ein zeitzonenbehafteter
        Wert, an dem nichts mehr auf den Fehler hinweist.

        Aus 09:30 New Yorker Zeit wuerde so 09:30 UTC. Der Bar laege
        ausserhalb des Sitzungsfensters, die Kerzenbildung verwuerfe ihn, und
        der Handelstag saehe aus wie einer ohne jede Lieferung -- der einzige
        Fall, den die Lueckenpruefung nicht erkennen kann.
        """
        naive = [bar.start for bar in bars if bar.start.tzinfo is None]
        if naive:
            raise ValueError(
                f"'{symbol}': {len(naive)} Bars ohne Zeitzone, erster {naive[0].isoformat()}. "
                "Zeitstempel muessen zeitzonenbehaftet sein (Doc 10)."
            )

    def _insert(self, symbol: str, bars: Sequence[IntradayBar]) -> int:
        statement = (
            pg_insert(IntradayBarOrm)
            .values(
                [
                    {
                        "symbol": symbol,
                        "start": bar.start,
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                    }
                    for bar in bars
                ]
            )
            .on_conflict_do_nothing(index_elements=["symbol", "start"])
            # Nicht ueber rowcount zaehlen: Bei einem Insert mit mehreren
            # Zeilen liefert der Treiber dafuer -1. RETURNING gibt bei
            # ON CONFLICT DO NOTHING ausschliesslich die tatsaechlich
            # geschriebenen Zeilen zurueck.
            .returning(IntradayBarOrm.start)
        )
        return len(self._session.execute(statement).all())

    def list_for(self, symbol: str) -> Sequence[IntradayBar]:
        rows = (
            self._session.execute(
                select(IntradayBarOrm)
                .where(IntradayBarOrm.symbol == symbol)
                .order_by(IntradayBarOrm.start)
            )
            .scalars()
            .all()
        )
        return tuple(
            IntradayBar(
                start=row.start,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
            )
            for row in rows
        )
