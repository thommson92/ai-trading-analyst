"""lese-indizes fuer das dashboard

Zwei Indizes fuer die Abfragen, die mit der Lese-API entstanden sind
(ADR 0053):

``analysis_run_errors.analysis_run_id`` hatte weder Index noch Constraint.
``count_for_run`` laeuft bei **jedem** Aufruf der Laufdetailansicht darueber
-- ohne Index als vollstaendiger Durchlauf der Tabelle.

``stock_reports.stock_id`` ist bisher nur die **zweite** Spalte des
Eindeutigkeits-Constraints ``uq_stock_report_run_stock`` und damit als
fuehrende Spalte nicht nutzbar. Genau darauf filtern aber
``list_for_symbol`` und ``count_for_symbol`` -- die Analysehistorie einer
Aktie.

Beide Tabellen wachsen mit jedem Handelstag um die Groesse der Watchliste.
Heute faellt der Unterschied nicht auf; das ist kein Grund, ihn erst zu
beheben, wenn er auffaellt.

Revision ID: a7d3e05c81f4
Revises: f4a71c9e2d38
Create Date: 2026-09-01 16:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a7d3e05c81f4"
down_revision: str | None = "f4a71c9e2d38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_analysis_run_errors_analysis_run_id",
        "analysis_run_errors",
        ["analysis_run_id"],
    )
    op.create_index("ix_stock_reports_stock_id", "stock_reports", ["stock_id"])


def downgrade() -> None:
    op.drop_index("ix_stock_reports_stock_id", table_name="stock_reports")
    op.drop_index("ix_analysis_run_errors_analysis_run_id", table_name="analysis_run_errors")
