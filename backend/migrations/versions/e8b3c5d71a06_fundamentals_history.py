"""screening results: fundamentals_history

Je Geschaeftsjahr die Kennzahlen dieses Jahres (ADR 0067) -- Grundlage der
Verlaufscharts im Kandidatenbericht. JSONB, weil die Reihe im Ganzen
geschrieben und im Ganzen gelesen wird.

NULL bei allem, was vorher gespeichert wurde: Eine Historie aus heutigen
Einreichungen waere nicht der damalige Stand.

Revision ID: e8b3c5d71a06
Revises: d4f6a1c7e9b2
Create Date: 2026-09-19 18:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "e8b3c5d71a06"
down_revision: str | None = "d4f6a1c7e9b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("screening_results", sa.Column("fundamentals_history", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("screening_results", "fundamentals_history")
