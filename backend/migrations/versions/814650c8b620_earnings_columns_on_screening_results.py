"""earnings columns on screening results

Sechs nullable Spalten fuer den Earnings-Filter (Doc 10, Paragraph 6.5;
ADR 0020), nach demselben Muster wie ``reason``/``affected_index`` auf
derselben Tabelle: die Entscheidung wird einmal je Lauf und Aktie berechnet
und ist nur bei ``CANDIDATE`` gesetzt, sonst durchgehend NULL.

``earnings_status`` braucht den Postgres-Enum-Typ explizit angelegt und
wieder entfernt -- anders als bei ``op.create_table`` legt ein einzelnes
``op.add_column`` den Typ nicht automatisch an.

Revision ID: 814650c8b620
Revises: 8f2a41c7b903
Create Date: 2026-08-16 01:36:45.768658

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "814650c8b620"
down_revision: str | None = "8f2a41c7b903"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_earnings_filter_status = sa.Enum(
    "EARNINGS_CLEAR", "EARNINGS_EXCLUDED", "UNKNOWN", name="earningsfilterstatus"
)


def upgrade() -> None:
    _earnings_filter_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "screening_results",
        sa.Column("earnings_status", _earnings_filter_status, nullable=True),
    )
    op.add_column(
        "screening_results",
        sa.Column("earnings_evaluated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("screening_results", sa.Column("earnings_next_date", sa.Date(), nullable=True))
    op.add_column(
        "screening_results", sa.Column("earnings_candles_until", sa.Integer(), nullable=True)
    )
    op.add_column("screening_results", sa.Column("earnings_source", sa.String(), nullable=True))
    op.add_column("screening_results", sa.Column("earnings_reason", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("screening_results", "earnings_reason")
    op.drop_column("screening_results", "earnings_source")
    op.drop_column("screening_results", "earnings_candles_until")
    op.drop_column("screening_results", "earnings_next_date")
    op.drop_column("screening_results", "earnings_evaluated_at")
    op.drop_column("screening_results", "earnings_status")
    _earnings_filter_status.drop(op.get_bind(), checkfirst=True)
