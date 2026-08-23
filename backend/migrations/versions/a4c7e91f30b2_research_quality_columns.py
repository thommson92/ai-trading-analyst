"""research quality columns

Das E5-Paket aus dem Repository-Audit (ADR 0029): Quellenrang, Quellenalter,
Abdeckung und die Zahlen, aus denen sie entsteht.

**Alle Spalten sind nullable, und das ist keine Bequemlichkeit.** Abgeschlossene
Analysen werden nicht ueberschrieben (CLAUDE.md) -- vor dieser Migration
geschriebene Berichte bekommen also keinen Rang und keine Abdeckung
nachgereicht. Ein alter Bericht weiss nichts darueber, wie breit er belegt war,
und soll das auch nicht behaupten. Der Lesepfad in ``repositories.py`` bildet
das ab: fehlender Rang wird ``UNRANKED``, fehlende Zahlen bleiben ``None``.

``position`` haelt die Rangreihenfolge aus ``rank_and_cap`` fest -- ohne sie
waere sie nach dem ersten Neuladen verloren, weil eine Relationship ohne
``order_by`` die Reihenfolge der Datenbank ueberlaesst (Muster
``technical_zones.position``). Sie ist die einzige NOT-NULL-Spalte dieser
Migration: bestehende Zeilen bekommen 0 und damit eine definierte, wenn auch
bedeutungslose Reihenfolge.

``research_analysis_version`` haelt fest, unter welcher Fassung der
deterministischen Regel ein ``research_coverage``-Wert entstanden ist --
getrennt von ``research_prompt_version``, weil beide sich unabhaengig aendern.

``source_rank`` steht bewusst **neben** ``license_class`` statt sie zu
ersetzen: Die Lizenzklasse beantwortet, was mit dem Inhalt rechtlich geschehen
darf, der Rang, wie belastbar er ist.

**Fallstrick:** Ein einzelnes ``op.add_column`` legt den Postgres-Enum-Typ
*nicht* mit an (dieselbe Falle wie in ``f2b8d6104a37``, ``d3f7a2c81e45`` und
``c9dfcbdad545``). Beide Typen brauchen deshalb ein ausdrueckliches ``create``
davor und ein ``DROP TYPE`` im Downgrade.

Revision ID: a4c7e91f30b2
Revises: f2b8d6104a37
Create Date: 2026-08-23 21:30:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4c7e91f30b2"
down_revision: str | None = "f2b8d6104a37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_source_rank = sa.Enum(
    "REGULATORY",
    "COMPANY",
    "FINANCIAL_MEDIA",
    "GENERAL_MEDIA",
    "AGGREGATOR",
    "UNRANKED",
    name="sourcerank",
)
_coverage = sa.Enum("BROAD", "LIMITED", "THIN", name="researchcoverage")

_ENUMS = (_source_rank, _coverage)

_EVIDENCE_COLUMNS = (
    "research_distinct_sources",
    "research_successful_fetches",
    "research_rejected_tool_calls",
    "research_dropped_citations",
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in _ENUMS:
        enum_type.create(bind, checkfirst=True)

    op.add_column("research_citations", sa.Column("source_rank", _source_rank, nullable=True))
    op.add_column("research_citations", sa.Column("source_age", sa.String(), nullable=True))
    # Bestehende Zeilen bekommen 0 und behalten damit eine definierte, wenn
    # auch bedeutungslose Reihenfolge; NOT NULL erst danach.
    op.add_column(
        "research_citations",
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("research_citations", "position", server_default=None)

    op.add_column(
        "screening_results", sa.Column("research_analysis_version", sa.String(), nullable=True)
    )
    op.add_column("screening_results", sa.Column("research_coverage", _coverage, nullable=True))
    for name in _EVIDENCE_COLUMNS:
        op.add_column("screening_results", sa.Column(name, sa.Integer(), nullable=True))


def downgrade() -> None:
    for name in _EVIDENCE_COLUMNS:
        op.drop_column("screening_results", name)
    op.drop_column("screening_results", "research_coverage")
    op.drop_column("screening_results", "research_analysis_version")

    op.drop_column("research_citations", "position")
    op.drop_column("research_citations", "source_age")
    op.drop_column("research_citations", "source_rank")

    bind = op.get_bind()
    for enum_type in _ENUMS:
        enum_type.drop(bind, checkfirst=True)
