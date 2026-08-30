"""fundamentals columns and metrics

Deterministische Fundamentalanalyse (Doc 10, Paragraph 6.9; ADR 0035) auf
``screening_results``, nach demselben Muster wie die ``earnings_*``-,
``research_*``- und ``technical_*``-Spalten: einmal je Lauf und Aktie
gerechnet, nur bei ``CANDIDATE`` gesetzt.

Dazu die neue Tabelle ``fundamental_metrics``. Die Zahl der Kennzahlen ist
nicht fest -- was sich nicht rechnen liess, entsteht gar nicht --, und jede
traegt Einheit, Basis und Zeitraum einzeln, weil zwei Kennzahlen desselben
Berichts verschiedene Zeitbezuege haben koennen (ADR 0033 L2). Das passt
nicht in flache Spalten (Muster ``technical_zones``).

``fundamentals_price_used`` haelt den Kurs, mit dem die vier
bewertungsabhaengigen Kennzahlen gerechnet wurden -- den Schluss der letzten
abgeschlossenen Kerze. Ohne ihn liesse sich ein Kurs-Gewinn-Verhaeltnis
spaeter nicht nachrechnen.

Tag-Widersprueche und Quellen stehen als JSONB: geschrieben und im Ganzen
gelesen, nie gefiltert (Muster ``technical_parameters``).

``fundamentalstatus`` braucht ein ausdrueckliches ``create``/``drop`` -- ein
einzelnes ``op.add_column`` legt den Typ nicht mit an. ``metricname``,
``metricunit`` und ``metricbasis`` entstehen mit ``op.create_table``,
brauchen im Downgrade aber trotzdem ein ``DROP TYPE``.

Revision ID: b7e3d9a5c210
Revises: a4c7e91f30b2
Create Date: 2026-08-27 15:40:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7e3d9a5c210"
down_revision: str | None = "a4c7e91f30b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_fundamental_status = sa.Enum("COMPLETED", "INSUFFICIENT_DATA", name="fundamentalstatus")
_metric_name = sa.Enum(
    "REVENUE",
    "REVENUE_GROWTH",
    "NET_INCOME",
    "NET_INCOME_GROWTH",
    "FREE_CASH_FLOW",
    "GROSS_MARGIN",
    "OPERATING_MARGIN",
    "NET_MARGIN",
    "FREE_CASH_FLOW_MARGIN",
    "RETURN_ON_EQUITY",
    "RETURN_ON_ASSETS",
    "DEBT_TO_EQUITY",
    "CURRENT_RATIO",
    "SHARE_COUNT_GROWTH",
    "MARKET_CAPITALIZATION",
    "PRICE_EARNINGS_RATIO",
    "PRICE_SALES_RATIO",
    "PRICE_FREE_CASH_FLOW_RATIO",
    name="metricname",
)
_metric_unit = sa.Enum("CURRENCY", "FRACTION", "RATIO", "SHARES", name="metricunit")
_metric_basis = sa.Enum(
    "TRAILING_TWELVE_MONTHS", "FISCAL_YEAR", "POINT_IN_TIME", name="metricbasis"
)


def upgrade() -> None:
    bind = op.get_bind()
    _fundamental_status.create(bind, checkfirst=True)

    op.add_column(
        "screening_results",
        sa.Column("fundamentals_status", _fundamental_status, nullable=True),
    )
    op.add_column(
        "screening_results",
        sa.Column("fundamentals_analysis_version", sa.String(), nullable=True),
    )
    op.add_column(
        "screening_results",
        sa.Column("fundamentals_evaluated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("screening_results", sa.Column("fundamentals_reason", sa.String(), nullable=True))
    op.add_column(
        "screening_results", sa.Column("fundamentals_price_used", sa.Float(), nullable=True)
    )
    op.add_column(
        "screening_results",
        sa.Column("fundamentals_fiscal_years", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "screening_results",
        sa.Column("fundamentals_tag_conflicts", postgresql.JSONB(), nullable=True),
    )

    op.create_table(
        "fundamental_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "screening_result_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("screening_results.id"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", _metric_name, nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", _metric_unit, nullable=False),
        sa.Column("currency", sa.String(), nullable=True),
        sa.Column("basis", _metric_basis, nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sources", postgresql.JSONB(), nullable=False),
    )
    op.create_index(
        "ix_fundamental_metrics_screening_result_id",
        "fundamental_metrics",
        ["screening_result_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_fundamental_metrics_screening_result_id", table_name="fundamental_metrics")
    op.drop_table("fundamental_metrics")
    for spalte in (
        "fundamentals_tag_conflicts",
        "fundamentals_fiscal_years",
        "fundamentals_price_used",
        "fundamentals_reason",
        "fundamentals_evaluated_at",
        "fundamentals_analysis_version",
        "fundamentals_status",
    ):
        op.drop_column("screening_results", spalte)

    bind = op.get_bind()
    for typ in (_metric_basis, _metric_unit, _metric_name, _fundamental_status):
        typ.drop(bind, checkfirst=True)
