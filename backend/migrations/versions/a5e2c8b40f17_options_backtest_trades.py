"""options backtest trades

Die Einzeltrades des Optionsbacktests (ADR 0058, Nachtrag zu Festlegung 9).

**Eigene Tabelle statt JSONB an der Ergebniszeile.** Ueber diese Zeilen wird
gruppiert, gefiltert und aggregiert -- daraus entsteht die eine Zahl je Aktie,
die ein Vergleich zwischen Aktien braucht und die sich aus den Kennzahlen je
Signalkombination nicht mitteln laesst.

``stock_id`` ist **nicht** nullbar: Ein Trade gehoert immer zu genau einer
Aktie. Die Zeile ueber alle Aktien gibt es nur bei den Kennzahlen, und sie
entsteht aus eben diesen Trades.

Ein **neuer** Enumtyp ``tradeoutcome`` -- anders als ``backtestconfidence``,
den ``b3d7f19ac405`` mit ``create_type=False`` wiederverwendet. Hier gab es
ihn noch nicht, also legt ihn diese Migration an und raeumt ihn im
``downgrade`` wieder weg. Ein zurueckgelassener Typ liesse das naechste
``upgrade`` scheitern.

Revision ID: a5e2c8b40f17
Revises: b3d7f19ac405
Create Date: 2026-09-05 11:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a5e2c8b40f17"
down_revision: str | None = "b3d7f19ac405"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WERTE = (
    "EXPIRED_WORTHLESS",
    "ASSIGNED",
    "TAKE_PROFIT",
    "STOPPED_OUT",
    "CLOSED_AT_EXPIRATION",
)

_AUSGANG = postgresql.ENUM(*_WERTE, name="tradeoutcome")
"""Zum Anlegen und Wegraeumen des Typs."""

_SPALTE = postgresql.ENUM(*_WERTE, name="tradeoutcome", create_type=False)
"""Zum Verwenden in den Spalten. **Zwei Objekte, und das ist kein Versehen:**
``create_table`` legt einen Enumtyp seiner Spalten selbst mit an. Mit
demselben Objekt liefe das ``CREATE TYPE`` ein zweites Mal und schluege mit
``DuplicateObject`` fehl."""


def upgrade() -> None:
    _AUSGANG.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "options_backtest_trades",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("measurement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "stock_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stocks.id"),
            nullable=False,
        ),
        sa.Column("signal_types", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("entry_index", sa.Integer(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("underlying_at_entry", sa.Float(), nullable=False),
        sa.Column("strike", sa.Float(), nullable=False),
        sa.Column("delta", sa.Float(), nullable=False),
        sa.Column("volatility", sa.Float(), nullable=False),
        sa.Column("premium", sa.Float(), nullable=False),
        sa.Column("capital_at_risk", sa.Float(), nullable=False),
        sa.Column("expiration", sa.Date(), nullable=False),
        sa.Column("days_to_expiration", sa.Integer(), nullable=False),
        sa.Column("underlying_at_expiration", sa.Float(), nullable=False),
        sa.Column("held_outcome", _SPALTE, nullable=False),
        sa.Column("held_profit", sa.Float(), nullable=False),
        sa.Column("managed_outcome", _SPALTE, nullable=False),
        sa.Column("managed_profit", sa.Float(), nullable=False),
        sa.Column("managed_exit_index", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_options_backtest_trades_measurement_id",
        "options_backtest_trades",
        ["measurement_id"],
    )
    op.create_index(
        "ix_options_backtest_trades_stock_id",
        "options_backtest_trades",
        ["stock_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_options_backtest_trades_stock_id", table_name="options_backtest_trades"
    )
    op.drop_index(
        "ix_options_backtest_trades_measurement_id",
        table_name="options_backtest_trades",
    )
    op.drop_table("options_backtest_trades")
    _AUSGANG.drop(op.get_bind(), checkfirst=True)
