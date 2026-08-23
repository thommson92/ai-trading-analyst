"""technical agent columns

Die KI-Einordnung der Chartauswertung (Doc 10, Paragraph 6.8 "Qualitative
Interpretation"; ADR 0026) auf ``screening_results``, in einem eigenen
Spaltensatz mit Praefix ``technical_ai_``.

Getrennt von den ``technical_``-Spalten, weil Doc 10, Paragraph 6.8
ausdruecklich verlangt, dass deterministische Berechnung und KI-Interpretation
getrennt gespeichert werden. Kein Codepfad schreibt aus dem einen Satz in den
anderen.

Keine eigene Tabelle wie bei ``technical_zones`` oder ``research_citations``:
Die Feldzahl ist fest, es gibt nichts zu wiederholen.

Sieben neue Enum-Typen. Das ist bewusst in Kauf genommen -- jede kuenftige
Stufe braucht ein ``ALTER TYPE ... ADD VALUE`` --, weil das Repo durchgaengig
Enum-Spalten verwendet und die Datenbank so einen Tippfehler abfaengt, statt
ihn als Text durchzureichen.

**Fallstrick:** Ein einzelnes ``op.add_column`` legt den Postgres-Enum-Typ
*nicht* mit an (dieselbe Falle wie in ``d3f7a2c81e45`` und
``c9dfcbdad545``). Jeder Typ braucht deshalb ein ausdrueckliches ``create``
davor und ein ``DROP TYPE`` im Downgrade.

Revision ID: f2b8d6104a37
Revises: e5a1c47b92d0
Create Date: 2026-08-22 22:10:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "f2b8d6104a37"
down_revision: str | None = "e5a1c47b92d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_status = sa.Enum(
    "COMPLETED", "INSUFFICIENT_DATA", "UNAVAILABLE", name="technicalassessmentstatus"
)
_trend_strength = sa.Enum("STRONG", "MODERATE", "WEAK", "ABSENT", name="trendstrength")
_breakout_quality = sa.Enum(
    "CONFIRMED", "TENTATIVE", "FAILED", "NO_BREAKOUT", name="breakoutquality"
)
_momentum_state = sa.Enum("OVERBOUGHT", "NEUTRAL", "OVERSOLD", name="momentumstate")
_false_signal_risk = sa.Enum("LOW", "MEDIUM", "HIGH", name="falsesignalrisk")
_risk_reward_rating = sa.Enum(
    "FAVOURABLE", "BALANCED", "UNFAVOURABLE", "NOT_ASSESSABLE", name="riskrewardrating"
)
_swing_entry = sa.Enum(
    "PLAUSIBLE", "QUESTIONABLE", "IMPLAUSIBLE", name="swingentryplausibility"
)

_ENUMS = (
    _status,
    _trend_strength,
    _breakout_quality,
    _momentum_state,
    _false_signal_risk,
    _risk_reward_rating,
    _swing_entry,
)

_PLAIN_COLUMNS = (
    "technical_ai_model",
    "technical_ai_prompt_version",
    "technical_ai_interpreted_analysis_version",
    "technical_ai_summary",
    "technical_ai_reason",
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in _ENUMS:
        enum_type.create(bind, checkfirst=True)

    op.add_column("screening_results", sa.Column("technical_ai_status", _status, nullable=True))
    op.add_column(
        "screening_results",
        sa.Column("technical_ai_evaluated_at", sa.DateTime(timezone=True), nullable=True),
    )
    for name in _PLAIN_COLUMNS:
        op.add_column("screening_results", sa.Column(name, sa.String(), nullable=True))
    op.add_column(
        "screening_results",
        sa.Column("technical_ai_trend_strength", _trend_strength, nullable=True),
    )
    op.add_column(
        "screening_results",
        sa.Column("technical_ai_breakout_quality", _breakout_quality, nullable=True),
    )
    op.add_column(
        "screening_results",
        sa.Column("technical_ai_momentum_state", _momentum_state, nullable=True),
    )
    op.add_column(
        "screening_results",
        sa.Column("technical_ai_false_signal_risk", _false_signal_risk, nullable=True),
    )
    op.add_column(
        "screening_results",
        sa.Column("technical_ai_risk_reward_rating", _risk_reward_rating, nullable=True),
    )
    op.add_column(
        "screening_results",
        sa.Column("technical_ai_swing_entry_plausibility", _swing_entry, nullable=True),
    )
    op.add_column(
        "screening_results",
        sa.Column("technical_ai_false_signal_risks", ARRAY(sa.String()), nullable=True),
    )
    op.add_column(
        "screening_results", sa.Column("technical_ai_confidence", sa.Float(), nullable=True)
    )


def downgrade() -> None:
    for name in (
        "technical_ai_confidence",
        "technical_ai_false_signal_risks",
        "technical_ai_swing_entry_plausibility",
        "technical_ai_risk_reward_rating",
        "technical_ai_false_signal_risk",
        "technical_ai_momentum_state",
        "technical_ai_breakout_quality",
        "technical_ai_trend_strength",
        *_PLAIN_COLUMNS,
        "technical_ai_evaluated_at",
        "technical_ai_status",
    ):
        op.drop_column("screening_results", name)

    for enum_type in _ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {enum_type.name}")
