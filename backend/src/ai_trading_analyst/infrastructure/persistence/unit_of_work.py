"""SQLAlchemy-Implementierung von ``domain.analysis.ports.UnitOfWork``."""

from __future__ import annotations

from types import TracebackType
from typing import Self

from sqlalchemy.orm import Session, sessionmaker

from ai_trading_analyst.domain.analysis import (
    AnalysisRunRepository,
    IntradayBarRepository,
    ProcessingErrorRepository,
    ScreeningResultRepository,
    StockRepository,
)

from .repositories import (
    SqlAlchemyAnalysisRunRepository,
    SqlAlchemyIntradayBarRepository,
    SqlAlchemyProcessingErrorRepository,
    SqlAlchemyScreeningResultRepository,
    SqlAlchemyStockRepository,
)


class SqlAlchemyUnitOfWork:
    """Eine Instanz entspricht genau einer Transaktion: Betreten oeffnet eine
    Session, Verlassen ohne vorherigen ``commit()`` rollt zurueck."""

    stocks: StockRepository
    intraday_bars: IntradayBarRepository
    analysis_runs: AnalysisRunRepository
    screening_results: ScreeningResultRepository
    processing_errors: ProcessingErrorRepository

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> Self:
        self._session = self._session_factory()
        self.stocks = SqlAlchemyStockRepository(self._session)
        self.intraday_bars = SqlAlchemyIntradayBarRepository(self._session)
        self.analysis_runs = SqlAlchemyAnalysisRunRepository(self._session)
        self.screening_results = SqlAlchemyScreeningResultRepository(self._session)
        self.processing_errors = SqlAlchemyProcessingErrorRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            if exc_type is not None:
                session.rollback()
        finally:
            session.close()
            self._session = None

    def commit(self) -> None:
        self._require_session().commit()

    def rollback(self) -> None:
        self._require_session().rollback()

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("UnitOfWork wurde ausserhalb eines 'with'-Blocks verwendet.")
        return self._session
