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


def test_die_spalten_des_technical_agent_entstehen_durch_die_migration(engine: Engine) -> None:
    """Die Migration und die ORM-Abbildung muessen dieselben Spalten kennen.

    Ein einzelnes ``op.add_column`` mit einem Enum-Typ legt den Typ in
    Postgres nicht mit an -- fehlt das ausdrueckliche ``create``, scheitert
    schon das Upgrade. Dieser Test faellt dann sofort auf, statt erst beim
    ersten Lauf mit Einordnung.
    """
    spalten = {spalte["name"] for spalte in inspect(engine).get_columns("screening_results")}

    assert {
        "technical_ai_status",
        "technical_ai_evaluated_at",
        "technical_ai_model",
        "technical_ai_prompt_version",
        "technical_ai_interpreted_analysis_version",
        "technical_ai_summary",
        "technical_ai_trend_strength",
        "technical_ai_breakout_quality",
        "technical_ai_momentum_state",
        "technical_ai_false_signal_risk",
        "technical_ai_risk_reward_rating",
        "technical_ai_swing_entry_plausibility",
        "technical_ai_false_signal_risks",
        "technical_ai_confidence",
        "technical_ai_reason",
    } <= spalten


def test_die_chance_risiko_spalten_entstehen_durch_die_migration(engine: Engine) -> None:
    spalten = {spalte["name"] for spalte in inspect(engine).get_columns("screening_results")}

    assert {
        "technical_downside_to_support_pct",
        "technical_upside_to_resistance_pct",
        "technical_chance_risk_ratio",
    } <= spalten
