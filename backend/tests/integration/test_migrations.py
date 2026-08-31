"""Migrationstest: Alembic-Upgrade auf eine leere Datenbank.

Die eigentliche Migration laeuft bereits einmal pro Testsession in der
``engine``-Fixture (``tests/integration/conftest.py``) -- inklusive
vollstaendigem Zuruecksetzen des Schemas davor. Dieser Test beobachtet nur
das Ergebnis: alle erwarteten Tabellen existieren nach dem Upgrade.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from ai_trading_analyst.domain.screening import ScreeningStatus
from ai_trading_analyst.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from tests.integration.conftest import make_outcome, make_run, make_stock
from tests.integration.conftest import run_alembic as _run_alembic

UowFactory = Callable[[], SqlAlchemyUnitOfWork]

EXPECTED_TABLES = {
    "stocks",
    "analysis_runs",
    "screening_results",
    "signal_events",
    "analysis_run_errors",
    "technical_zones",
    "research_citations",
    "fundamental_metrics",
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


def test_die_spalten_der_fundamentalanalyse_entstehen_durch_die_migration(
    engine: Engine,
) -> None:
    """ADR 0035. Wie bei den technical_ai_*-Spalten: Ein ``op.add_column``
    mit einem Enum-Typ legt den Typ nicht mit an."""
    spalten = {spalte["name"] for spalte in inspect(engine).get_columns("screening_results")}

    assert {
        "fundamentals_status",
        "fundamentals_analysis_version",
        "fundamentals_evaluated_at",
        "fundamentals_reason",
        "fundamentals_price_used",
        "fundamentals_fiscal_years",
        "fundamentals_tag_conflicts",
    } <= spalten


def test_die_kennzahlentabelle_traegt_ihre_spalten_und_ihren_index(engine: Engine) -> None:
    """Der Index auf dem Fremdschluessel gehoert in **beide** Beschreibungen.

    Steht er nur in der Migration und nicht am ORM-Modell, erzeugt das
    naechste ``alembic revision --autogenerate`` ein ``drop_index`` -- der
    Index verschwaende bei der naechsten Gelegenheit unbemerkt wieder.
    """
    inspector = inspect(engine)
    spalten = {spalte["name"] for spalte in inspector.get_columns("fundamental_metrics")}

    assert {
        "id",
        "screening_result_id",
        "position",
        "name",
        "value",
        "unit",
        "currency",
        "basis",
        "period_start",
        "period_end",
        "retrieved_at",
        "sources",
    } <= spalten
    indizes = {index["name"] for index in inspector.get_indexes("fundamental_metrics")}
    assert "ix_fundamental_metrics_screening_result_id" in indizes


def test_die_chance_risiko_spalten_entstehen_durch_die_migration(engine: Engine) -> None:
    spalten = {spalte["name"] for spalte in inspect(engine).get_columns("screening_results")}

    assert {
        "technical_downside_to_support_pct",
        "technical_upside_to_resistance_pct",
        "technical_chance_risk_ratio",
    } <= spalten


def test_die_spalten_der_research_qualitaet_entstehen_durch_die_migration(
    engine: Engine,
) -> None:
    """ADR 0029 -- zwei neue Enum-Typen, sieben neue Spalten.

    Dieselbe Falle wie beim Technical Agent: Ein ``op.add_column`` mit einem
    Enum-Typ legt den Typ in Postgres nicht mit an. Ohne diesen Test faellt
    ein fehlendes ``create`` erst beim ersten Schreiben eines Berichts auf --
    also auf dem Server, im Tageslauf.
    """
    inspector = inspect(engine)
    ergebnisse = {spalte["name"] for spalte in inspector.get_columns("screening_results")}
    zitate = {spalte["name"] for spalte in inspector.get_columns("research_citations")}

    assert {
        "research_analysis_version",
        "research_coverage",
        "research_distinct_sources",
        "research_successful_fetches",
        "research_rejected_tool_calls",
        "research_dropped_citations",
    } <= ergebnisse
    assert {"source_rank", "source_age", "position"} <= zitate


def test_die_position_der_zitate_ist_verpflichtend(engine: Engine) -> None:
    """Die Rangreihenfolge haengt an dieser Spalte (ADR 0029). Waere sie
    nullable, koennte eine Zeile ohne Reihenfolge entstehen und das
    ``order_by`` liefe ins Leere."""
    spalten = {
        spalte["name"]: spalte for spalte in inspect(engine).get_columns("research_citations")
    }
    assert spalten["position"]["nullable"] is False


def test_die_score_spalten_entstehen_durch_die_migration(engine: Engine) -> None:
    """ADR 0041, ADR 0045 -- vier Spalten je Score und ein neuer Enum-Typ.

    Dieselbe Falle wie beim Technical Agent: Ein ``op.add_column`` mit einem
    Enum-Typ legt den Typ in Postgres nicht mit an. Ohne diesen Test faellt
    ein fehlendes ``create`` erst beim ersten Speichern eines Kandidaten auf
    -- also auf dem Server, im Tageslauf.
    """
    spalten = {spalte["name"] for spalte in inspect(engine).get_columns("screening_results")}

    assert {
        "swing_score",
        "swing_status",
        "swing_version",
        "swing_detail",
        "long_term_score",
        "long_term_status",
        "long_term_version",
        "long_term_detail",
    } <= spalten


def test_die_score_migration_laesst_sich_zurueckdrehen(
    engine: Engine, database_url: str, uow_factory: UowFactory
) -> None:
    """Hoch **und runter**, gegen eine Datenbank mit Inhalt.

    Ein Downgrade, das nur auf dem Papier steht, ist keiner: Der Enum-Typ
    ``scorestatus`` bleibt beim blossen ``drop_column`` zurueck, und der
    naechste Upgrade-Versuch scheitert dann an einem Typ, den es schon gibt.
    Der Test dreht deshalb wirklich zurueck und wieder vor.
    """
    stock = make_stock("MIGDOWN")
    run = make_run()
    with uow_factory() as uow:
        uow.stocks.add(stock)
        uow.analysis_runs.add(run)
        uow.screening_results.add(
            make_outcome(stock, ScreeningStatus.CANDIDATE, analysis_run_id=run.id)
        )
        uow.commit()

    _run_alembic(database_url, "downgrade", "-1")
    try:
        nach_unten = {
            spalte["name"] for spalte in inspect(engine).get_columns("screening_results")
        }
        assert "swing_score" not in nach_unten
        assert "long_term_detail" not in nach_unten
        assert "analyst_status" in nach_unten, "das Downgrade ging eine Stufe zu weit"
    finally:
        _run_alembic(database_url, "upgrade", "head")

    wieder_oben = {spalte["name"] for spalte in inspect(engine).get_columns("screening_results")}
    assert {"swing_score", "long_term_detail"} <= wieder_oben

    # Die Zeile hat beides ueberlebt. Ein Downgrade, das die Tabelle leert,
    # waere auf dem Server ein Datenverlust und kein Rueckbau.
    with uow_factory() as uow:
        (persisted,) = uow.screening_results.list_for_run(run.id)
    assert persisted.stock.symbol == "MIGDOWN"
    assert persisted.swing_score is None
