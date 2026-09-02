"""signaltype um RSI_OVERSOLD und NO_RECENT_EMA_DOWNCROSS erweitert

Die Kandidatenregel steht seit ADR 0056 auf fuenf Kriterien; zwei davon
sind neu und brauchen ihren Wert im Enumtyp ``signaltype``, ueber den
``signal_events.signal_type`` definiert ist.

``ALTER TYPE ... ADD VALUE`` laeuft hier in einem ``autocommit_block``:
``env.py`` fuehrt Migrationen in einer Transaktion aus, und ein in
derselben Transaktion angelegter Enumwert ist bis zum Commit nicht
benutzbar. Der Block macht das Muster unabhaengig von der
PostgreSQL-Version sicher.

Das Downgrade baut den Typ neu auf -- PostgreSQL kennt kein
``DROP VALUE``. Es **bricht ab**, sobald Zeilen die neuen Werte tragen:
Ein Schema mit drei Werten kann Daten mit fuenf nicht wahrheitsgemaess
abbilden, und Zeilen zu loeschen, um ein Downgrade zu ermoeglichen, waere
ein Verstoss gegen die Unveraenderlichkeit abgeschlossener Analysen
(Doc 10, Paragraph 6.11).

Revision ID: b3e7f21a9c48
Revises: a7d3e05c81f4
Create Date: 2026-09-02 19:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "b3e7f21a9c48"
down_revision: str | None = "a7d3e05c81f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEUE_WERTE = ("RSI_OVERSOLD", "NO_RECENT_EMA_DOWNCROSS")
_ALTE_WERTE = ("RSI_CROSS", "PRICE_EMA20_BREAKOUT", "EMA5_EMA20_CROSS")


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for wert in _NEUE_WERTE:
            op.execute(f"ALTER TYPE signaltype ADD VALUE IF NOT EXISTS '{wert}'")


def downgrade() -> None:
    werte = ", ".join(f"'{wert}'" for wert in _NEUE_WERTE)
    verbindung = op.get_bind()
    belegt = verbindung.execute(
        text(f"SELECT count(*) FROM signal_events WHERE signal_type IN ({werte})")
    ).scalar_one()
    if belegt:
        raise RuntimeError(
            f"{belegt} Signalereignisse tragen die Werte {werte}. Ein Downgrade "
            "wuerde sie unlesbar machen; abgeschlossene Analysen werden nicht "
            "veraendert. Die Zeilen muessen zuerst bewusst entfernt werden."
        )

    alte_werte = ", ".join(f"'{wert}'" for wert in _ALTE_WERTE)
    op.execute("ALTER TYPE signaltype RENAME TO signaltype_alt")
    op.execute(f"CREATE TYPE signaltype AS ENUM ({alte_werte})")
    op.execute(
        "ALTER TABLE signal_events ALTER COLUMN signal_type "
        "TYPE signaltype USING signal_type::text::signaltype"
    )
    op.execute("DROP TYPE signaltype_alt")
