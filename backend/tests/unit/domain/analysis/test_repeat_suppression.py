"""Tests der Sperrfenster-Rechnung (ADR 0054)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ai_trading_analyst.domain.analysis import (
    RepeatSuppressionParameters,
    suppression_cutoff,
)

_JETZT = datetime(2026, 9, 1, 20, 0, tzinfo=UTC)


class TestSuppressionCutoff:
    def test_sieben_tage_ergeben_den_cutoff_sieben_tage_zurueck(self) -> None:
        cutoff = suppression_cutoff(_JETZT, RepeatSuppressionParameters(window_days=7))
        assert cutoff == _JETZT - timedelta(days=7)

    def test_null_schaltet_die_sperre_ab(self) -> None:
        assert suppression_cutoff(_JETZT, RepeatSuppressionParameters(window_days=0)) is None

    def test_der_cutoff_bleibt_zeitzonenbewusst(self) -> None:
        cutoff = suppression_cutoff(_JETZT, RepeatSuppressionParameters(window_days=7))
        assert cutoff is not None
        assert cutoff.tzinfo is not None
