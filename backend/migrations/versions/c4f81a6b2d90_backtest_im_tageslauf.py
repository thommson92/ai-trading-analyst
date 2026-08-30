"""backtest im tageslauf

Der Backtest laeuft ab jetzt fuer jeden Kandidaten im Tageslauf (ADR 0038,
Entscheidung 1). Damit braucht ``backtest_results`` zwei Spalten:

``analysis_run_id`` bindet das Ergebnis an den Lauf, in dem es entstand.
**Nullable**, denn ``cli backtest`` rechnet weiterhin ohne Lauf -- und die
bereits gespeicherten Zeilen gehoeren zu keinem. Ein Index darauf, weil der
Report Generator genau darueber liest.

``earnings_exclusion_applied`` haelt fest, ob Ereignisse nahe einem
Berichtstermin aus dem Replay ausgeschlossen wurden. Heute durchgehend
``false``: Historische Termine gibt es nicht (ADR 0017 L9). Die Spalte steht
mit, damit die Zeilen die Wahrheit ueber sich selbst sagen, sobald E3
entschieden ist -- statt rueckwirkend so auszusehen, als waeren sie gefiltert
worden.

``server_default`` steht nur fuer die Dauer der Migration da: Die bestehenden
Zeilen brauchen einen Wert, die Anwendung setzt ihn danach selbst. Er wird
anschliessend wieder entfernt, damit die Spalte nicht still einen Wert
ergaenzt, den niemand gerechnet hat.

Revision ID: c4f81a6b2d90
Revises: b7e3d9a5c210
Create Date: 2026-08-30 17:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4f81a6b2d90"
down_revision: str | None = "b7e3d9a5c210"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "backtest_results",
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_backtest_results_analysis_run_id", "backtest_results", ["analysis_run_id"]
    )
    op.create_foreign_key(
        "fk_backtest_results_analysis_run_id",
        "backtest_results",
        "analysis_runs",
        ["analysis_run_id"],
        ["id"],
    )
    op.add_column(
        "backtest_results",
        sa.Column(
            "earnings_exclusion_applied",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("backtest_results", "earnings_exclusion_applied", server_default=None)


def downgrade() -> None:
    op.drop_column("backtest_results", "earnings_exclusion_applied")
    op.drop_constraint(
        "fk_backtest_results_analysis_run_id", "backtest_results", type_="foreignkey"
    )
    op.drop_index("ix_backtest_results_analysis_run_id", table_name="backtest_results")
    op.drop_column("backtest_results", "analysis_run_id")
