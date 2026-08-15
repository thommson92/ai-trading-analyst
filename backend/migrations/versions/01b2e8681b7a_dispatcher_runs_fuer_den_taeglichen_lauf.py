"""dispatcher_runs fuer den taeglichen Lauf

Der Zustand des Dispatchers (ADR 0019). Der Schluessel ist
(session_date, candle_close) und nicht der Handelstag allein: Wird spaeter
auch nach der zweiten Tageskerze gerechnet, sind das zwei getrennte Laeufe
desselben Tages.

Revision ID: 01b2e8681b7a
Revises: 8f2a41c7b903
Create Date: 2026-08-15 17:07:20.282405

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '01b2e8681b7a'
down_revision: str | None = '8f2a41c7b903'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('dispatcher_runs',
    sa.Column('session_date', sa.Date(), nullable=False),
    sa.Column('candle_close', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('first_attempt_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.String(), nullable=True),
    sa.Column('alert_sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('session_date', 'candle_close')
    )


def downgrade() -> None:
    op.drop_table('dispatcher_runs')
