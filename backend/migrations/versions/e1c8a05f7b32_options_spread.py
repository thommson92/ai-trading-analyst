"""options spread

Der Put-Spread neben dem ungesicherten Verkauf (ADR 0058, Festlegung 11).

Zwei Spalten an ``screening_results``, nach dem Muster der uebrigen
``options_``-Spalten:

* ``options_spread`` als JSONB -- wie ``options_strategies`` und aus
  demselben Grund: im Ganzen geschrieben, im Ganzen gelesen, nie gefiltert
  oder sortiert. Anders als die Rohnotierungen aus ``c9f4b7e021d3``, ueber
  die aggregiert wird und die deshalb eine eigene Tabelle haben.
* ``options_spread_reason`` als Text. **Eigene Spalte neben
  ``options_reason``**: Die Optionsanalyse kann vollstaendig sein und der
  Strukturvergleich trotzdem fehlen -- kein Strike unter dem Verkauf
  gelistet, kein Mittelwert, die Absicherung kostet die ganze Praemie. Beide
  Gruende in eine Spalte zu legen hiesse, zwei verschiedene Ausfaelle zu
  verwechseln.

Kein neuer Enumtyp, keine Aenderung an bestehenden Spalten. ``downgrade``
entfernt beide wieder; verloren geht dabei der Strukturvergleich, nicht die
Optionsanalyse.

Revision ID: e1c8a05f7b32
Revises: c9f4b7e021d3
Create Date: 2026-09-04 17:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e1c8a05f7b32"
down_revision: str | None = "c9f4b7e021d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "screening_results",
        sa.Column("options_spread", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "screening_results",
        sa.Column("options_spread_reason", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("screening_results", "options_spread_reason")
    op.drop_column("screening_results", "options_spread")
