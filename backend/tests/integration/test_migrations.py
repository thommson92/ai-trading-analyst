"""Migrationstest: Alembic-Upgrade auf eine leere Datenbank.

Die eigentliche Migration laeuft bereits einmal pro Testsession in der
``engine``-Fixture (``tests/integration/conftest.py``) -- inklusive
vollstaendigem Zuruecksetzen des Schemas davor. Dieser Test beobachtet nur
das Ergebnis: alle erwarteten Tabellen existieren nach dem Upgrade.
"""

from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

EXPECTED_TABLES = {
    "stocks",
    "analysis_runs",
    "screening_results",
    "signal_events",
    "analysis_run_errors",
    "technical_zones",
}


def test_upgrade_on_empty_database_creates_all_expected_tables(engine: Engine) -> None:
    inspector = inspect(engine)
    assert EXPECTED_TABLES <= set(inspector.get_table_names())


def test_screening_results_have_the_unique_constraint_against_silent_overwrite(
    engine: Engine,
) -> None:
    inspector = inspect(engine)
    constraint_names = {
        constraint["name"] for constraint in inspector.get_unique_constraints("screening_results")
    }
    assert "uq_screening_result_run_stock" in constraint_names
