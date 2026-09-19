"""signal events: candle_at

Der Kerzenzeitpunkt neben dem Index (ADR 0066). Der Index zeigt nach einem
Tiefen-Backfill auf eine andere Kerze; der Bericht braucht das Datum.
NULL bei allem, was vorher gespeichert wurde -- keine Rueckrechnung.

Revision ID: d4f6a1c7e9b2
Revises: b9e4d2a71c53
Create Date: 2026-09-19 16:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4f6a1c7e9b2"
down_revision: str | None = "b9e4d2a71c53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "signal_events", sa.Column("candle_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("signal_events", "candle_at")
