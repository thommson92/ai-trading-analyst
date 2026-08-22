"""chance risk columns

Weg bis zur naechsten Unterstuetzung, Weg bis zum naechsten Widerstand und
ihr Verhaeltnis (ADR 0026), als Teil der deterministischen Chartauswertung
(Doc 10, Paragraph 6.8) auf ``screening_results``.

Die Kennzahl wird bewusst berechnet und gespeichert statt bei Bedarf aus den
Zonen abgeleitet: Doc 10, Paragraph 6.11 nennt sie als Scoring-Komponente und
Paragraph 6.10 den Abstand zur naechsten Unterstuetzung als Eingabe der
Optionsanalyse. Wuerde sie erst beim Lesen entstehen, verschoebe eine spaetere
Aenderung der Herleitung rueckwirkend die Zahlen abgeschlossener Analysen --
das verbietet CLAUDE.md ("Abgeschlossene Analysen werden nicht ueberschrieben").

Drei einfache ``float``-Spalten, kein neuer Enum-Typ -- hier ist deshalb
nichts explizit anzulegen.

Revision ID: e5a1c47b92d0
Revises: d3f7a2c81e45
Create Date: 2026-08-22 21:40:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5a1c47b92d0"
down_revision: str | None = "d3f7a2c81e45"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    "technical_downside_to_support_pct",
    "technical_upside_to_resistance_pct",
    "technical_chance_risk_ratio",
)


def upgrade() -> None:
    for name in _COLUMNS:
        op.add_column("screening_results", sa.Column(name, sa.Float(), nullable=True))


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.drop_column("screening_results", name)
