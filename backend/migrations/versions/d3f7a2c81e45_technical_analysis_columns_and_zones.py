"""technical analysis columns and zones

Deterministische Chartauswertung (Doc 10, Paragraph 6.8; ADR 0025) auf
``screening_results``, nach demselben Muster wie die ``earnings_*``- und
``research_*``-Spalten: einmal je Lauf und Aktie berechnet, nur bei
``CANDIDATE`` gesetzt.

Dazu die neue Tabelle ``technical_zones``. Anders als beim Earnings-Filter
ist die Zahl der Zonen nicht fest, und jede traegt die sieben von Doc 10
verlangten Angaben -- das passt nicht in flache Spalten (Muster
``research_citations``).

Die Parameter des Laufs stehen als JSONB an der Zeile: Doc 14 fordert
ausdruecklich dazu auf, Zonenbreite und Schwellen zwischen Laeufen
nachzuziehen -- ohne sie waere die Verfahrensversion allein eine leere
Zusage. JSONB statt elf Spalten, weil sie nur geschrieben und gelesen werden.

Die drei Enum-Typen auf ``screening_results`` (``technicalstatus``,
``trenddirection``) brauchen ein explizites ``create``/``drop``: Ein
einzelnes ``op.add_column`` legt den Typ nicht mit an. ``zonekind`` und
``zonestrength`` entstehen dagegen automatisch mit ``op.create_table``,
brauchen im Downgrade aber trotzdem ein ausdrueckliches ``DROP TYPE``.

Revision ID: d3f7a2c81e45
Revises: 01b2e8681b7a
Create Date: 2026-08-22 10:12:33.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d3f7a2c81e45"
down_revision: str | None = "01b2e8681b7a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_technical_status = sa.Enum("COMPLETED", "INSUFFICIENT_DATA", name="technicalstatus")
_trend_direction = sa.Enum("UP", "DOWN", "SIDEWAYS", name="trenddirection")

_FLOAT_COLUMNS = (
    "technical_close",
    "technical_rsi",
    "technical_ema5",
    "technical_ema20",
    "technical_distance_to_ema5_pct",
    "technical_distance_to_ema20_pct",
    "technical_atr",
    "technical_atr_pct",
    "technical_recent_high",
    "technical_recent_low",
)

_TIMESTAMP_COLUMNS = (
    "technical_evaluated_at",
    "technical_candle_timestamp",
    "technical_recent_high_at",
    "technical_recent_low_at",
)

_TEXT_COLUMNS = (
    "technical_analysis_version",
    "technical_reason",
)


def upgrade() -> None:
    _technical_status.create(op.get_bind(), checkfirst=True)
    _trend_direction.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "screening_results", sa.Column("technical_status", _technical_status, nullable=True)
    )
    op.add_column(
        "screening_results", sa.Column("technical_trend", _trend_direction, nullable=True)
    )
    for name in _TIMESTAMP_COLUMNS:
        op.add_column(
            "screening_results", sa.Column(name, sa.DateTime(timezone=True), nullable=True)
        )
    for name in _TEXT_COLUMNS:
        op.add_column("screening_results", sa.Column(name, sa.String(), nullable=True))
    op.add_column(
        "screening_results",
        sa.Column("technical_parameters", postgresql.JSONB(), nullable=True),
    )
    for name in _FLOAT_COLUMNS:
        op.add_column("screening_results", sa.Column(name, sa.Float(), nullable=True))

    op.create_table(
        "technical_zones",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("screening_result_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("lower", sa.Float(), nullable=False),
        sa.Column("upper", sa.Float(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("SUPPORT", "RESISTANCE", "PRICE_INSIDE", name="zonekind"),
            nullable=False,
        ),
        sa.Column(
            "strength",
            sa.Enum("WEAK", "MODERATE", "STRONG", name="zonestrength"),
            nullable=False,
        ),
        sa.Column("touch_count", sa.Integer(), nullable=False),
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("distance_pct", sa.Float(), nullable=False),
        sa.Column("pivot_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["screening_result_id"],
            ["screening_results.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("technical_zones")
    op.execute("DROP TYPE IF EXISTS zonekind")
    op.execute("DROP TYPE IF EXISTS zonestrength")

    op.drop_column("screening_results", "technical_parameters")
    for name in (*_FLOAT_COLUMNS, *_TEXT_COLUMNS, *_TIMESTAMP_COLUMNS):
        op.drop_column("screening_results", name)
    op.drop_column("screening_results", "technical_trend")
    op.drop_column("screening_results", "technical_status")

    _trend_direction.drop(op.get_bind(), checkfirst=True)
    _technical_status.drop(op.get_bind(), checkfirst=True)
