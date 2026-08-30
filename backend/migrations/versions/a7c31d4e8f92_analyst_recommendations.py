"""analyst recommendations

Die Votenverteilung der Analysten je Monatsstand (Doc 10, Paragraph 6.12
Punkt 9; ADR 0043).

Sieben Spalten an ``screening_results``, nach dem Muster des
``fundamentals_``-Blocks. ``analyst_periods`` ist JSONB und keine
Kindtabelle: Die Verteilung wird im Ganzen geschrieben und im Ganzen gelesen,
nie gefiltert oder sortiert, und es sind hoechstens vier Eintraege je Aktie
und Lauf.

Der Typ ``analystrecommendationstatus`` entsteht mit ``op.add_column``
**nicht** von selbst -- anders als bei ``op.create_table``. Er wird deshalb
ausdruecklich angelegt und im Downgrade ausdruecklich wieder entfernt (Muster
``metricname`` in b7e3d9a5c210).

Revision ID: a7c31d4e8f92
Revises: d5a29c73e6b1
Create Date: 2026-08-30 22:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7c31d4e8f92"
down_revision: str | None = "d5a29c73e6b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_analyst_status = sa.Enum(
    "COMPLETED",
    "UNKNOWN",
    "UNAVAILABLE",
    name="analystrecommendationstatus",
)

_COLUMNS = (
    "analyst_status",
    "analyst_analysis_version",
    "analyst_evaluated_at",
    "analyst_source",
    "analyst_retrieved_at",
    "analyst_reason",
    "analyst_periods",
)


def upgrade() -> None:
    bind = op.get_bind()
    _analyst_status.create(bind, checkfirst=False)

    op.add_column(
        "screening_results",
        sa.Column("analyst_status", _analyst_status, nullable=True),
    )
    op.add_column(
        "screening_results", sa.Column("analyst_analysis_version", sa.String(), nullable=True)
    )
    op.add_column(
        "screening_results",
        sa.Column("analyst_evaluated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("screening_results", sa.Column("analyst_source", sa.String(), nullable=True))
    op.add_column(
        "screening_results",
        sa.Column("analyst_retrieved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("screening_results", sa.Column("analyst_reason", sa.String(), nullable=True))
    op.add_column(
        "screening_results", sa.Column("analyst_periods", postgresql.JSONB(), nullable=True)
    )


def downgrade() -> None:
    for column in reversed(_COLUMNS):
        op.drop_column("screening_results", column)
    _analyst_status.drop(op.get_bind(), checkfirst=False)
