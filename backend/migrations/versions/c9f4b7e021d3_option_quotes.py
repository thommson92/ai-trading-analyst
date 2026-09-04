"""option quotes

Die abgerufenen Rohnotierungen der Optionsanalyse (ADR 0058, Festlegung 1).

Der Tageslauf fragt bis zu ``options.max_strikes`` Kontrakte je Kandidat ab
und behielt bisher hoechstens ``options.max_suggestions`` davon. Die uebrigen
verschwanden nach der Auswertung -- bei rund 36 Kandidaten etwa 400 echte
Notierungen je Handelstag. Genau sie tragen die Auskunft, die ADR 0058 fuer
die Kalibrierung des Bewertungsmodells braucht; vor allem die Notierungen
**ausserhalb** des Delta-Bandes, die als einzige etwas ueber die Form der
Volatilitaetskurve sagen.

**Eigene Tabelle und nicht JSONB wie ``options_strategies``**, nach dem
Kriterium, das die Migration ``f4a71c9e2d38`` fuer jene selbst genannt hat:
im Ganzen geschrieben, im Ganzen gelesen, nie gefiltert oder sortiert. Bei
den Rohnotierungen ist das Gegenteil der Zweck -- sie werden nach Moneyness
gruppiert, ueber Zeitraeume aggregiert und gegen die modellierte Praemie
gehalten.

Keine Spalten fuer Zeitpunkt und Aktienkurs: Beide stehen mit
``options_evaluated_at`` und ``options_underlying_price`` an der Elternzeile
und gelten fuer jede Notierung desselben Abrufs gleich.

Kein neuer Enumtyp, keine Aenderung an bestehenden Spalten. ``downgrade``
raeumt die Tabelle vollstaendig ab; verloren gehen dabei nur Messdaten, keine
Analyseergebnisse.

Revision ID: c9f4b7e021d3
Revises: b3e7f21a9c48
Create Date: 2026-09-04 08:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9f4b7e021d3"
down_revision: str | None = "b3e7f21a9c48"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "option_quotes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "screening_result_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("screening_results.id"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("expiration", sa.Date(), nullable=False),
        sa.Column("strike", sa.Float(), nullable=False),
        # Alles ausser Verfall und Strike darf fehlen: Nach Boersenschluss und
        # bei duenn gehandelten Kontrakten liefert IBKR einzelne Felder nicht
        # (ADR 0048). Was fehlt, bleibt fehlend.
        sa.Column("bid", sa.Float(), nullable=True),
        sa.Column("ask", sa.Float(), nullable=True),
        sa.Column("delta", sa.Float(), nullable=True),
        sa.Column("implied_volatility", sa.Float(), nullable=True),
        sa.Column("open_interest", sa.Integer(), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_option_quotes_screening_result_id",
        "option_quotes",
        ["screening_result_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_option_quotes_screening_result_id", table_name="option_quotes")
    op.drop_table("option_quotes")
