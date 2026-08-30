"""stock reports

Der Analysebericht (Doc 10, Paragraph 6.12; ADR 0039).

``stock_reports`` haelt einen Datensatz je Lauf und Aktie. Die Unique
Constraint verhindert ein zweites, stillschweigend ueberschreibendes Insert --
dasselbe Muster wie ``uq_screening_result_run_stock``; ein abgeschlossener
Bericht wird nicht ueberschrieben (Doc 10, Paragraph 8).

``document`` ist die verbindliche Fassung als JSONB. Sie verdoppelt Daten aus
``screening_results``, und genau das ist die Zusicherung: Ein Bericht, der bei
jedem Abruf neu entstuende, aenderte sich still mit jeder Codeaenderung.

``scoring_version``, ``recommendation``, ``swing_score``, ``investment_score``
und ``summary`` bleiben vorerst leer: Scoring gehoert zu Sprint 5, die
Formulierung zur KI-Haelfte. Sie stehen trotzdem hier, damit Sprint 5 sie
fuellen kann, ohne das Schema zu heben.

Der Typ ``recommendation`` entsteht mit ``op.create_table`` von selbst,
verschwindet aber beim ``drop_table`` **nicht** -- er braucht im Downgrade ein
ausdrueckliches ``DROP TYPE`` (Muster ``metricname`` in b7e3d9a5c210).

Dazu ``screening_results.fundamentals_company_name`` -- der amtliche Name des
Registranten aus dem SEC-Symbolverzeichnis, die einzige Quelle fuer
Berichtspunkt 1 (ADR 0039, Entscheidung 5).

Revision ID: d5a29c73e6b1
Revises: c4f81a6b2d90
Create Date: 2026-08-30 18:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d5a29c73e6b1"
down_revision: str | None = "c4f81a6b2d90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_recommendation = sa.Enum(
    "STRONG_CANDIDATE",
    "CANDIDATE",
    "WATCH",
    "AVOID_FOR_NOW",
    "INSUFFICIENT_DATA",
    name="recommendation",
)


def upgrade() -> None:
    op.add_column(
        "screening_results",
        sa.Column("fundamentals_company_name", sa.String(), nullable=True),
    )

    op.create_table(
        "stock_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "analysis_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_runs.id"),
            nullable=False,
        ),
        sa.Column(
            "stock_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stocks.id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_schema_version", sa.String(), nullable=False),
        sa.Column("app_version", sa.String(), nullable=False),
        sa.Column("scoring_version", sa.String(), nullable=True),
        sa.Column("recommendation", _recommendation, nullable=True),
        sa.Column("swing_score", sa.Float(), nullable=True),
        sa.Column("investment_score", sa.Float(), nullable=True),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("analysis_run_id", "stock_id", name="uq_stock_report_run_stock"),
    )
    op.create_index("ix_stock_reports_analysis_run_id", "stock_reports", ["analysis_run_id"])


def downgrade() -> None:
    op.drop_index("ix_stock_reports_analysis_run_id", table_name="stock_reports")
    op.drop_table("stock_reports")
    _recommendation.drop(op.get_bind(), checkfirst=False)
    op.drop_column("screening_results", "fundamentals_company_name")
