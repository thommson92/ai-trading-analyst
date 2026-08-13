"""intraday_bars fuer den historischen Backfill

Gespeichert werden die **nativen Bars des Anbieters**, nicht die daraus
gebildeten 195-Minuten-Kerzen. Die Aggregationsregeln haben sich mehrfach
geaendert; laegen nur Kerzen vor, verlangte jede Korrektur einen erneuten
Abruf ueber ein Jahr und alle Symbole.

Revision ID: 8f2a41c7b903
Revises: 44017205de13
Create Date: 2026-08-13

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8f2a41c7b903"
down_revision: str | None = "44017205de13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "intraday_bars",
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        # Der zusammengesetzte Schluessel macht den Backfill wiederholbar:
        # Derselbe Bar zweimal geliefert ist kein Fehler, sondern ein
        # uebergangener Konflikt.
        sa.PrimaryKeyConstraint("symbol", "start"),
    )


def downgrade() -> None:
    op.drop_table("intraday_bars")
