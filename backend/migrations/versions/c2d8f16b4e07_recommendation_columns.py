"""recommendation columns

Die Empfehlungsstufe an ``screening_results`` (Doc 10, Paragraph 6.12
Punkt 16; ADR 0046).

Zwei Spalten nach dem Muster der Score-Spalten: die Stufe selbst, weil nach
ihr gefiltert wird, und Begruendung samt Deckelungen als JSONB, weil sie im
Ganzen geschrieben und im Ganzen gelesen werden.

**Der Enumtyp ``recommendation`` existiert bereits** -- ``d5a29c73e6b1`` hat
ihn fuer ``stock_reports`` angelegt. Deshalb ``create_type=False``, genau
umgekehrt zu ``b1c9e4a7d523``: Dort fehlte der Typ und musste angelegt
werden, hier waere ein zweites ``CREATE TYPE`` ein Fehler.

Revision ID: c2d8f16b4e07
Revises: b1c9e4a7d523
Create Date: 2026-08-31 15:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c2d8f16b4e07"
down_revision: str | None = "b1c9e4a7d523"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_recommendation = postgresql.ENUM(
    "STRONG_CANDIDATE",
    "CANDIDATE",
    "WATCH",
    "AVOID_FOR_NOW",
    "INSUFFICIENT_DATA",
    name="recommendation",
    create_type=False,
)


def upgrade() -> None:
    op.add_column("screening_results", sa.Column("recommendation", _recommendation, nullable=True))
    op.add_column(
        "screening_results",
        sa.Column("recommendation_detail", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("screening_results", "recommendation_detail")
    op.drop_column("screening_results", "recommendation")
    # Der Typ bleibt: ``stock_reports.recommendation`` benutzt ihn weiterhin.
