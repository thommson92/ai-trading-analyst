"""Migrationstest: Alembic-Upgrade auf eine leere Datenbank.

Die eigentliche Migration laeuft bereits einmal pro Testsession in der
``engine``-Fixture (``tests/integration/conftest.py``) -- inklusive
vollstaendigem Zuruecksetzen des Schemas davor. Dieser Test beobachtet nur
das Ergebnis: alle erwarteten Tabellen existieren nach dem Upgrade.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from ai_trading_analyst.domain.backtesting import (
    BacktestConfidence,
    BacktestResult,
    HorizonMetrics,
)
from ai_trading_analyst.domain.screening import (
    SIGNAL_RULE_VERSION,
    ScreeningStatus,
    SignalType,
)
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


def test_die_empfehlungsspalten_entstehen_durch_die_migration(engine: Engine) -> None:
    """ADR 0046 -- zwei Spalten, aber **kein** neuer Enumtyp.

    Der Typ ``recommendation`` existiert seit ``d5a29c73e6b1`` fuer
    ``stock_reports``. Ihn ein zweites Mal anzulegen scheitert; deshalb
    ``create_type=False`` -- genau umgekehrt zum Fall der Score-Spalten.
    """
    spalten = {spalte["name"] for spalte in inspect(engine).get_columns("screening_results")}

    assert {"recommendation", "recommendation_detail"} <= spalten


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


def test_beide_tabellen_fuehren_den_score_im_selben_typ(engine: Engine) -> None:
    """Dieselbe Zahl, derselbe Typ. ``stock_reports`` trug die beiden Spalten
    schon als ``double precision``, gefuellt werden sie erst jetzt."""
    inspector = inspect(engine)
    ergebnisse = {s["name"]: s["type"] for s in inspector.get_columns("screening_results")}
    berichte = {s["name"]: s["type"] for s in inspector.get_columns("stock_reports")}

    assert str(ergebnisse["swing_score"]) == "NUMERIC(4, 1)"
    assert str(berichte["swing_score"]) == "NUMERIC(4, 1)"
    assert str(berichte["investment_score"]) == "NUMERIC(4, 1)"


def _typ_existiert(engine: Engine, name: str) -> bool:
    with engine.connect() as verbindung:
        treffer = verbindung.execute(
            text("SELECT 1 FROM pg_type WHERE typname = :name"), {"name": name}
        ).first()
    return treffer is not None


def test_die_migrationen_von_sprint_fuenf_lassen_sich_zurueckdrehen(
    engine: Engine, database_url: str, uow_factory: UowFactory
) -> None:
    """Hoch **und runter**, gegen eine Datenbank mit Inhalt.

    Ein Downgrade, das nur auf dem Papier steht, ist keiner: Der Enum-Typ
    ``scorestatus`` bleibt beim blossen ``drop_column`` zurueck, und der
    naechste Upgrade-Versuch scheitert dann an einem Typ, den es schon gibt.
    Der Test dreht deshalb wirklich zurueck und wieder vor.

    **Drei Stufen auf einmal** -- Scores, Empfehlung und Optionsanalyse --,
    und ausdruecklich gegen eine feste Revision statt gegen ``-1``: Sonst
    prueft der Test nach der naechsten Migration etwas anderes, ohne dass
    jemand ihn angefasst hat.
    """
    vor_sprint_fuenf = "a7c31d4e8f92"
    stock = make_stock("MIGDOWN")
    run = make_run()
    with uow_factory() as uow:
        uow.stocks.add(stock)
        uow.analysis_runs.add(run)
        uow.screening_results.add(
            make_outcome(stock, ScreeningStatus.CANDIDATE, analysis_run_id=run.id)
        )
        uow.commit()

    _run_alembic(database_url, "downgrade", vor_sprint_fuenf)
    try:
        nach_unten = {
            spalte["name"] for spalte in inspect(engine).get_columns("screening_results")
        }
        assert "swing_score" not in nach_unten
        assert "long_term_detail" not in nach_unten
        assert "recommendation" not in nach_unten
        assert "recommendation_detail" not in nach_unten
        assert "options_status" not in nach_unten
        assert "options_strategies" not in nach_unten
        # Der Enumtyp ``optionsstatus`` muss mit weg -- anders als
        # ``recommendation`` benutzt ihn keine zweite Tabelle. Ein
        # zurueckgebliebener Typ faellt beim Wiederhochfahren nicht auf
        # (``checkfirst``), aber er ist Muell in der Datenbank, und beim
        # naechsten Statuswert stimmte er still nicht mehr.
        assert not _typ_existiert(engine, "optionsstatus")
        assert "analyst_status" in nach_unten, "das Downgrade ging eine Stufe zu weit"
        # Der Enumtyp ``recommendation`` bleibt: ``stock_reports`` benutzt ihn
        # weiter. Ihn mitzuloeschen brach die Tabelle daneben.
        berichtsspalten = {s["name"] for s in inspect(engine).get_columns("stock_reports")}
        assert "recommendation" in berichtsspalten
        berichte = {s["name"]: s["type"] for s in inspect(engine).get_columns("stock_reports")}
        assert str(berichte["swing_score"]) == "DOUBLE PRECISION", (
            "der Typwechsel in stock_reports wurde nicht zurueckgenommen"
        )
    finally:
        _run_alembic(database_url, "upgrade", "head")

    wieder_oben = {spalte["name"] for spalte in inspect(engine).get_columns("screening_results")}
    assert {
        "swing_score",
        "long_term_detail",
        "recommendation",
        "recommendation_detail",
        "options_status",
        "options_strategies",
        "options_underlying_price",
    } <= wieder_oben

    # Die Zeile hat beides ueberlebt. Ein Downgrade, das die Tabelle leert,
    # waere auf dem Server ein Datenverlust und kein Rueckbau.
    with uow_factory() as uow:
        (persisted,) = uow.screening_results.list_for_run(run.id)
    assert persisted.stock.symbol == "MIGDOWN"
    assert persisted.swing_score is None
    assert persisted.recommendation is None
    assert persisted.options is None


def _enum_werte(engine: Engine, typname: str) -> list[str]:
    with engine.connect() as verbindung:
        zeilen = verbindung.execute(
            text(
                "SELECT e.enumlabel FROM pg_enum e "
                "JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = :typname ORDER BY e.enumsortorder"
            ),
            {"typname": typname},
        ).scalars()
        return list(zeilen)


def test_signaltype_kennt_die_neuen_kriterien(engine: Engine) -> None:
    """Die beiden neuen Werte stehen **hinten** (ADR 0056).

    ``ALTER TYPE ... ADD VALUE`` haengt an, die Python-Definitionsreihenfolge
    tut dasselbe. Laufen die beiden auseinander, faellt das hier auf und nicht
    erst an einer sortierten Abfrage.
    """
    assert _enum_werte(engine, "signaltype") == [
        "RSI_CROSS",
        "PRICE_EMA20_BREAKOUT",
        "EMA5_EMA20_CROSS",
        "RSI_OVERSOLD",
        "NO_RECENT_EMA_DOWNCROSS",
    ]


def test_das_downgrade_des_signaltype_baut_den_dreiwertigen_typ_wieder_auf(
    engine: Engine, database_url: str
) -> None:
    vor_den_neuen_kriterien = "a7d3e05c81f4"
    _run_alembic(database_url, "downgrade", vor_den_neuen_kriterien)
    try:
        assert _enum_werte(engine, "signaltype") == [
            "RSI_CROSS",
            "PRICE_EMA20_BREAKOUT",
            "EMA5_EMA20_CROSS",
        ]
        assert not _typ_existiert(engine, "signaltype_alt"), (
            "der umbenannte Typ ist Muell in der Datenbank und muss mit weg"
        )
    finally:
        _run_alembic(database_url, "upgrade", "head")

    assert "RSI_OVERSOLD" in _enum_werte(engine, "signaltype")


def test_das_downgrade_bricht_auch_bei_belegten_backtest_zeilen_ab(
    engine: Engine, database_url: str, uow_factory: UowFactory
) -> None:
    """``backtest_results.signal_types`` ist ein Textarray und traegt den
    Enumtyp nicht -- der Typwechsel ginge daran vorbei, das Auslesen braeche
    danach beim Zurueckwandeln in ``SignalType``. Der Waechter sieht deshalb
    auf beide Tabellen.
    """
    stock = make_stock("BTDOWN")
    jetzt = datetime.now(UTC)
    ergebnis = BacktestResult(
        stock_id=stock.id,
        signal_types=frozenset(
            {SignalType.RSI_CROSS, SignalType.NO_RECENT_EMA_DOWNCROSS}
        ),
        signal_rule_version=SIGNAL_RULE_VERSION,
        evaluated_at=jetzt,
        history_start=jetzt,
        history_end=jetzt,
        horizons=(
            HorizonMetrics(
                horizon=5,
                raw_event_count=0,
                deduplicated_event_count=0,
                hit_rate=None,
                mean_return=None,
                median_return=None,
                max_loss=None,
                drawdown=None,
                held_above_entry_rate=None,
                confidence=BacktestConfidence.INSUFFICIENT_DATA,
            ),
        ),
    )
    with uow_factory() as uow:
        uow.stocks.add(stock)
        uow.backtest_results.add(ergebnis)
        uow.commit()

    with pytest.raises(RuntimeError, match="unlesbar"):
        _run_alembic(database_url, "downgrade", "a7d3e05c81f4")

    assert "NO_RECENT_EMA_DOWNCROSS" in _enum_werte(engine, "signaltype")
