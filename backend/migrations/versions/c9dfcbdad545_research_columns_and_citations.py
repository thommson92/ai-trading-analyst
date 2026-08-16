"""research columns and citations

Zehn nullable Spalten fuer den Research Agent (Doc 10, Paragraph 6.7 und 10;
ADR 0021, ADR 0022) auf ``screening_results``, nach demselben Muster wie die
``earnings_*``-Spalten: einmal je Lauf und Aktie berechnet, nur gesetzt, wenn
zusaetzlich der Earnings-Filter ``EARNINGS_CLEAR`` war.

Dazu die neue Tabelle ``research_citations`` -- ein Zitat hat mehrere Felder
und passt deshalb nicht in eine flache Spalte (Muster ``signal_events``).

``research_status`` braucht den Postgres-Enum-Typ explizit angelegt und
wieder entfernt -- anders als bei ``op.create_table`` legt ein einzelnes
``op.add_column`` den Typ nicht automatisch an. ``license_class`` auf
``research_citations`` entsteht dagegen automatisch mit der Tabelle, braucht
aber trotzdem ein explizites ``DROP TYPE`` im Downgrade.

Revision ID: c9dfcbdad545
Revises: 1af1a18978d4
Create Date: 2026-08-16 20:48:45.523105

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9dfcbdad545"
down_revision: str | None = "1af1a18978d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_research_status = sa.Enum("COMPLETED", "INSUFFICIENT_DATA", "UNAVAILABLE", name="researchstatus")


def upgrade() -> None:
    _research_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "screening_results", sa.Column("research_status", _research_status, nullable=True)
    )
    op.add_column(
        "screening_results",
        sa.Column("research_evaluated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("screening_results", sa.Column("research_model", sa.String(), nullable=True))
    op.add_column(
        "screening_results", sa.Column("research_prompt_version", sa.String(), nullable=True)
    )
    op.add_column("screening_results", sa.Column("research_summary", sa.String(), nullable=True))
    op.add_column(
        "screening_results",
        sa.Column("research_positive_factors", sa.ARRAY(sa.String()), nullable=True),
    )
    op.add_column(
        "screening_results",
        sa.Column("research_negative_factors", sa.ARRAY(sa.String()), nullable=True),
    )
    op.add_column(
        "screening_results", sa.Column("research_risks", sa.ARRAY(sa.String()), nullable=True)
    )
    op.add_column("screening_results", sa.Column("research_confidence", sa.Float(), nullable=True))
    op.add_column("screening_results", sa.Column("research_reason", sa.String(), nullable=True))

    op.create_table(
        "research_citations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("screening_result_id", sa.UUID(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cited_text", sa.String(), nullable=True),
        sa.Column(
            "license_class",
            sa.Enum("PRIMARY_SOURCE", "NEWS_MEDIA", "UNKNOWN", name="sourcelicenseclass"),
            nullable=False,
        ),
        sa.Column("transformation", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["screening_result_id"],
            ["screening_results.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("research_citations")
    op.execute("DROP TYPE IF EXISTS sourcelicenseclass")

    op.drop_column("screening_results", "research_reason")
    op.drop_column("screening_results", "research_confidence")
    op.drop_column("screening_results", "research_risks")
    op.drop_column("screening_results", "research_negative_factors")
    op.drop_column("screening_results", "research_positive_factors")
    op.drop_column("screening_results", "research_summary")
    op.drop_column("screening_results", "research_prompt_version")
    op.drop_column("screening_results", "research_model")
    op.drop_column("screening_results", "research_evaluated_at")
    op.drop_column("screening_results", "research_status")
    _research_status.drop(op.get_bind(), checkfirst=True)
