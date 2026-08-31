"""score columns

Die beiden Scores an ``screening_results`` (Doc 10, Paragraph 6.11;
ADR 0041, ADR 0045).

Vier Spalten je Score und nicht vierzehn: Sortiert und gefiltert wird
ausschliesslich nach dem Gesamtwert; Teilwerte, Gewichte, Abdeckung,
Konfidenz, Faktoren und begrenzende Risiken werden im Ganzen geschrieben und
im Ganzen gelesen. Dasselbe Argument wie bei ``technical_parameters`` und
``fundamentals_tag_conflicts`` -- und es heisst, dass eine neue Komponente
keine Migration braucht.

``NUMERIC(4,1)`` fuer den Gesamtwert: Ein Score traegt genau eine
Nachkommastelle.

Der Typ ``scorestatus`` entsteht mit ``op.add_column`` **nicht** von selbst
(Muster ``analystrecommendationstatus`` in a7c31d4e8f92) und wird deshalb
ausdruecklich angelegt und im Downgrade wieder entfernt.

Revision ID: b1c9e4a7d523
Revises: a7c31d4e8f92
Create Date: 2026-08-31 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b1c9e4a7d523"
down_revision: str | None = "a7c31d4e8f92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_score_status = sa.Enum("COMPLETED", "INSUFFICIENT_DATA", name="scorestatus")

_PREFIXES = ("swing", "long_term")


def upgrade() -> None:
    _score_status.create(op.get_bind(), checkfirst=False)

    for prefix in _PREFIXES:
        op.add_column(
            "screening_results",
            sa.Column(f"{prefix}_score", sa.Numeric(4, 1), nullable=True),
        )
        op.add_column(
            "screening_results",
            sa.Column(f"{prefix}_status", _score_status, nullable=True),
        )
        op.add_column(
            "screening_results", sa.Column(f"{prefix}_version", sa.String(), nullable=True)
        )
        op.add_column(
            "screening_results", sa.Column(f"{prefix}_detail", postgresql.JSONB(), nullable=True)
        )


def downgrade() -> None:
    for prefix in reversed(_PREFIXES):
        for spalte in ("detail", "version", "status", "score"):
            op.drop_column("screening_results", f"{prefix}_{spalte}")
    _score_status.drop(op.get_bind(), checkfirst=False)
