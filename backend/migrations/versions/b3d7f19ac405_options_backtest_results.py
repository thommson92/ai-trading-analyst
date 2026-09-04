"""options backtest results

Die eigene Tabelle des Optionsbacktests (ADR 0058, Festlegung 9).

**Eigene Tabelle und nicht die Spalten der echten Optionsanalyse.** Jede Zahl
darin ist modelliert -- die Praemie gerechnet, der Verfallskalender
konstruiert, das Strike-Raster angenommen. Eine modellierte Praemie darf an
keiner Stelle neben einer notierten stehen, ohne dass man beide unterscheiden
kann.

``stock_id`` ist ``NULL`` in der Zeile ueber **alle** Aktien einer Messung.
Sie entsteht aus den Einzeltrades und nicht als Mittel der Aktienzeilen; ein
Mittel von Mitteln gewichtete eine Aktie mit drei Trades so schwer wie eine
mit dreissig.

Kein Unique-Constraint und kein neuer Enumtyp: ``backtest_confidence``
existiert seit der Aktienseite, deshalb ``create_type=False``. Ein zweites
``create`` scheitert -- dieselbe Falle wie bei den Empfehlungsspalten.

Revision ID: b3d7f19ac405
Revises: e1c8a05f7b32
Create Date: 2026-09-05 09:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b3d7f19ac405"
down_revision: str | None = "e1c8a05f7b32"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KONFIDENZ = postgresql.ENUM(
    "INSUFFICIENT_DATA",
    "LOW_SAMPLE",
    "NORMAL",
    name="backtestconfidence",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "options_backtest_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("measurement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "stock_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stocks.id"),
            nullable=True,
        ),
        sa.Column("stocks", sa.Integer(), nullable=False),
        sa.Column("signal_types", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("signal_rule_version", sa.String(), nullable=False),
        sa.Column("options_backtest_version", sa.String(), nullable=False),
        sa.Column("history_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("history_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("episodes", sa.Integer(), nullable=False),
        sa.Column("trades", sa.Integer(), nullable=False),
        sa.Column("without_trade", sa.Integer(), nullable=False),
        sa.Column("confidence", _KONFIDENZ, nullable=False),
        sa.Column("held_win_rate", sa.Float(), nullable=True),
        sa.Column("held_mean_profit", sa.Float(), nullable=True),
        sa.Column("held_median_profit", sa.Float(), nullable=True),
        sa.Column("held_total_profit", sa.Float(), nullable=True),
        sa.Column("held_worst_profit", sa.Float(), nullable=True),
        sa.Column("held_mean_return_on_capital", sa.Float(), nullable=True),
        sa.Column("held_outcomes", postgresql.JSONB(), nullable=True),
        sa.Column("managed_win_rate", sa.Float(), nullable=True),
        sa.Column("managed_mean_profit", sa.Float(), nullable=True),
        sa.Column("managed_median_profit", sa.Float(), nullable=True),
        sa.Column("managed_total_profit", sa.Float(), nullable=True),
        sa.Column("managed_worst_profit", sa.Float(), nullable=True),
        sa.Column("managed_mean_return_on_capital", sa.Float(), nullable=True),
        sa.Column("managed_outcomes", postgresql.JSONB(), nullable=True),
        sa.Column("assumptions", postgresql.JSONB(), nullable=False),
    )
    op.create_index(
        "ix_options_backtest_results_measurement_id",
        "options_backtest_results",
        ["measurement_id"],
    )
    op.create_index(
        "ix_options_backtest_results_stock_id",
        "options_backtest_results",
        ["stock_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_options_backtest_results_stock_id", table_name="options_backtest_results"
    )
    op.drop_index(
        "ix_options_backtest_results_measurement_id",
        table_name="options_backtest_results",
    )
    op.drop_table("options_backtest_results")
