"""options columns

Die Optionsanalyse an ``screening_results`` (Doc 10, Paragraph 6.12
Punkt 13; ADR 0048).

Sieben Spalten nach dem Muster der ``fundamentals_``-Spalten: Kopfangaben
einzeln, die Vorschlaege als JSONB. Neunzehn Felder je Vorschlag als Spalten
waeren mehr als fuer alle uebrigen Analysemodule zusammen, und gefiltert oder
sortiert wird nach keinem von ihnen.

``options_underlying_price`` ist kein Beiwerk: Ohne den Kurs, auf dem die
Strike-Auswahl stand, liesse sich der Abstand eines Strikes zum Kurs spaeter
nicht nachrechnen -- dasselbe Argument wie bei
``fundamentals_price_used``.

**Der Enumtyp ``optionsstatus`` ist neu.** Anders als bei ``c2d8f16b4e07``
legt Alembic ihn hier also an; ``downgrade`` raeumt ihn wieder ab, weil ihn
keine andere Tabelle benutzt.

Revision ID: f4a71c9e2d38
Revises: c2d8f16b4e07
Create Date: 2026-08-31 18:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f4a71c9e2d38"
down_revision: str | None = "c2d8f16b4e07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_options_status = postgresql.ENUM(
    "COMPLETED",
    "INSUFFICIENT_DATA",
    name="optionsstatus",
    create_type=False,
)


def upgrade() -> None:
    _options_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "screening_results", sa.Column("options_status", _options_status, nullable=True)
    )
    op.add_column(
        "screening_results", sa.Column("options_analysis_version", sa.String(), nullable=True)
    )
    op.add_column(
        "screening_results",
        sa.Column("options_evaluated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("screening_results", sa.Column("options_reason", sa.String(), nullable=True))
    op.add_column(
        "screening_results", sa.Column("options_underlying_price", sa.Float(), nullable=True)
    )
    op.add_column("screening_results", sa.Column("options_expiration", sa.Date(), nullable=True))
    op.add_column(
        "screening_results", sa.Column("options_strategies", postgresql.JSONB(), nullable=True)
    )


def downgrade() -> None:
    for spalte in (
        "options_strategies",
        "options_expiration",
        "options_underlying_price",
        "options_reason",
        "options_evaluated_at",
        "options_analysis_version",
        "options_status",
    ):
        op.drop_column("screening_results", spalte)
    _options_status.drop(op.get_bind(), checkfirst=True)
