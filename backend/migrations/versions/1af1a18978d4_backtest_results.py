"""backtest results

Neue Tabelle fuer die historische Signalpruefung (Doc 07; G1-Pruefvorlage
Abschnitt 4). Eine Zeile je Aktie, Signalkombination und Horizont -- kein
Update-Pfad, jede Neuberechnung ist ein neues, zeitgestempeltes Insert.

Revision ID: 1af1a18978d4
Revises: 814650c8b620
Create Date: 2026-08-16 14:18:25.199325

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1af1a18978d4"
down_revision: str | None = "814650c8b620"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backtest_results",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("stock_id", sa.UUID(), nullable=False),
        sa.Column("signal_types", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("signal_rule_version", sa.String(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("history_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("history_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon", sa.Integer(), nullable=False),
        sa.Column("raw_event_count", sa.Integer(), nullable=False),
        sa.Column("deduplicated_event_count", sa.Integer(), nullable=False),
        sa.Column("hit_rate", sa.Float(), nullable=True),
        sa.Column("mean_return", sa.Float(), nullable=True),
        sa.Column("median_return", sa.Float(), nullable=True),
        sa.Column("max_loss", sa.Float(), nullable=True),
        sa.Column("drawdown", sa.Float(), nullable=True),
        sa.Column("held_above_entry_rate", sa.Float(), nullable=True),
        sa.Column(
            "confidence",
            sa.Enum("INSUFFICIENT_DATA", "LOW_SAMPLE", "NORMAL", name="backtestconfidence"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["stock_id"],
            ["stocks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("backtest_results")
    op.execute("DROP TYPE IF EXISTS backtestconfidence")
