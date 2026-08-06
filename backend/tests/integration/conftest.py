"""Testinfrastruktur fuer echte PostgreSQL-Integrationstests.

SQLite ist hier bewusst kein Ersatz (Doc 10-Anforderung dieses Sprints):
JSON-Spalten, Enum-Typen und Constraint-Verhalten unterscheiden sich zwischen
SQLite und PostgreSQL genug, um Fehler zu verschleiern, die erst in
Produktion (PostgreSQL) auftreten wuerden.

Erwartet die Umgebungsvariable ``TEST_DATABASE_URL`` (bewusst ohne
``ATA_``-Praefix, damit die autouse-Fixture ``isolated_environment`` aus
``tests/conftest.py`` sie nicht mit den Secrets der Anwendung verwechselt
und loescht). Siehe README, Abschnitt "Tests".
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ai_trading_analyst.domain.analysis import AnalysisRun, RunStatus, Stock, StockScreeningOutcome
from ai_trading_analyst.domain.screening import (
    SIGNAL_RULE_VERSION,
    ScreeningResult,
    ScreeningStatus,
)
from ai_trading_analyst.infrastructure.persistence.orm import Base
from ai_trading_analyst.infrastructure.persistence.session import (
    build_engine,
    build_session_factory,
)
from ai_trading_analyst.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork

_TEST_DATABASE_URL_ENV = "TEST_DATABASE_URL"
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _run_alembic_upgrade(database_url: str) -> None:
    """Setzt ATA_DATABASE_URL nur fuer die Dauer des Alembic-Aufrufs
    (``migrations/env.py`` liest sie ueber ``Secrets``) und stellt den
    vorherigen Zustand danach wieder her."""
    previous = os.environ.get("ATA_DATABASE_URL")
    os.environ["ATA_DATABASE_URL"] = database_url
    try:
        config = Config(str(_BACKEND_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(_BACKEND_ROOT / "migrations"))
        command.upgrade(config, "head")
    finally:
        if previous is None:
            os.environ.pop("ATA_DATABASE_URL", None)
        else:
            os.environ["ATA_DATABASE_URL"] = previous


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get(_TEST_DATABASE_URL_ENV)
    if not url:
        pytest.fail(
            f"{_TEST_DATABASE_URL_ENV} ist nicht gesetzt. Diese Tests benoetigen echtes "
            "PostgreSQL, siehe README Abschnitt 'Tests' (z. B. "
            "'docker run -p 55432:5432 -e POSTGRES_USER=ata -e POSTGRES_PASSWORD=ata "
            "-e POSTGRES_DB=ata_test postgres:16-alpine' und "
            "TEST_DATABASE_URL=postgresql+psycopg://ata:ata@localhost:55432/ata_test)."
        )
    return url


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    """Setzt die Datenbank einmal pro Testsession vollstaendig zurueck und
    wendet die Alembic-Migration auf eine leere Datenbank an -- das ist
    zugleich der Migrationstest in ``test_migrations.py`` beobachtet nur das
    Ergebnis dieses Vorgangs."""
    eng = build_engine(database_url)
    with eng.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    _run_alembic_upgrade(database_url)
    yield eng
    eng.dispose()


@pytest.fixture()
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return build_session_factory(engine)


@pytest.fixture()
def uow_factory(session_factory: sessionmaker[Session]) -> Callable[[], SqlAlchemyUnitOfWork]:
    def factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return factory


@pytest.fixture(autouse=True)
def _clean_tables(engine: Engine) -> Iterator[None]:
    yield
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


def make_stock(symbol: str) -> Stock:
    return Stock(id=uuid.uuid5(uuid.NAMESPACE_DNS, symbol), symbol=symbol, exchange="NASDAQ")


def make_run(
    *, status: RunStatus = RunStatus.RUNNING, run_id: uuid.UUID | None = None
) -> AnalysisRun:
    return AnalysisRun(id=run_id or uuid.uuid4(), status=status, started_at=datetime.now(UTC))


def make_outcome(
    stock: Stock,
    status: ScreeningStatus,
    *,
    analysis_run_id: uuid.UUID,
    decision_candle_index: int = 258,
) -> StockScreeningOutcome:
    return StockScreeningOutcome(
        analysis_run_id=analysis_run_id,
        stock=stock,
        result=ScreeningResult(status=status),
        decision_candle_index=decision_candle_index,
        evaluated_at=datetime.now(UTC),
        signal_rule_version=SIGNAL_RULE_VERSION,
    )
