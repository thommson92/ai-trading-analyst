"""backtest episodes

Die gezaehlten Ereignisse des Signal-Backtests, eine Zeile je Episode und
Horizont (ADR 0061). Dasselbe Muster wie ``backtest_results``: kein
Unique-Constraint, kein Update-Pfad -- jede Auswertung haengt an.

``entry_at`` ist ein Zeitstempel und kein Kerzenindex. Der Tiefen-Backfill
fuegt aeltere Bars vorn an und verschoebe jeden Index; ``signal_events.
candle_index`` traegt genau diese Buerde, und diese Tabelle soll sie nicht
erben.

Die Kennzahlen je Horizont sind ``NULL``, wenn die Historie den Horizont
nicht erreicht -- der Horizont steht trotzdem als Zeile da, damit ein
fehlender Wert nicht aussieht wie ein nie gerechneter.

Revision ID: c7d1e5a92b04
Revises: a5e2c8b40f17
Create Date: 2026-09-18 22:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c7d1e5a92b04"
down_revision: str | None = "a5e2c8b40f17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backtest_episodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "stock_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stocks.id"),
            nullable=False,
        ),
        sa.Column(
            "analysis_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_runs.id"),
            nullable=True,
        ),
        sa.Column("signal_types", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("signal_rule_version", sa.String(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_close", sa.Float(), nullable=False),
        sa.Column("trigger_count", sa.Integer(), nullable=False),
        sa.Column("last_trigger_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon", sa.Integer(), nullable=False),
        sa.Column("return_pct", sa.Float(), nullable=True),
        sa.Column("max_loss", sa.Float(), nullable=True),
        sa.Column("drawdown", sa.Float(), nullable=True),
        sa.Column("held_above_entry", sa.Boolean(), nullable=True),
    )
    op.create_index(
        "ix_backtest_episodes_analysis_run_id", "backtest_episodes", ["analysis_run_id"]
    )
    op.create_index(
        "ix_backtest_episodes_stock_evaluated",
        "backtest_episodes",
        ["stock_id", "evaluated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_backtest_episodes_stock_evaluated", table_name="backtest_episodes")
    op.drop_index("ix_backtest_episodes_analysis_run_id", table_name="backtest_episodes")
    op.drop_table("backtest_episodes")
