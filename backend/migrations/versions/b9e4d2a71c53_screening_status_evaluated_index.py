"""screening results: index on (status, evaluated_at)

Die Sperrabfrage ``latest_candidate_analyses`` lief bis ADR 0062 einmal je
Tageslauf; seither laeuft sie je Lauf in jeder Laufansicht und im Export.
Ohne Index war das ein Tabellenscan je Lauf -- quadratisch in der Zahl der
Laeufe.

Revision ID: b9e4d2a71c53
Revises: c7d1e5a92b04
Create Date: 2026-09-19 00:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "b9e4d2a71c53"
down_revision: str | None = "c7d1e5a92b04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_screening_results_status_evaluated",
        "screening_results",
        ["status", "evaluated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_screening_results_status_evaluated", table_name="screening_results")
