"""Tests der Sperrfenster-Rechnung (ADR 0054)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from ai_trading_analyst.domain.analysis import (
    RepeatSuppressionParameters,
    suppression_window,
)

_NY = ZoneInfo("America/New_York")
_JETZT = datetime(2026, 9, 1, 16, 0, tzinfo=_NY)


class TestSuppressionWindow:
    def test_sieben_tage_umfassen_die_sechs_kalendertage_vor_heute(self) -> None:
        """window_days zaehlt den Analysetag mit: Tag 0 analysiert, Tag 7
        wieder dran -- gesperrt sind die Kalendertage 1 bis 6 danach."""
        fenster = suppression_window(_JETZT, RepeatSuppressionParameters(window_days=7))
        assert fenster is not None
        seit, bis = fenster
        assert bis == datetime(2026, 9, 1, 0, 0, tzinfo=_NY)
        assert seit == bis - timedelta(days=6)

    def test_der_laufende_tag_sperrt_nicht(self) -> None:
        """Die Obergrenze ist der Tagesbeginn -- ein Wiederholungslauf
        desselben Tages sieht die Zeilen eines abgebrochenen Laufs nicht."""
        fenster = suppression_window(_JETZT, RepeatSuppressionParameters(window_days=7))
        assert fenster is not None
        _, bis = fenster
        analyse_heute = _JETZT - timedelta(hours=3)
        assert not analyse_heute < bis

    def test_null_schaltet_die_sperre_ab(self) -> None:
        assert suppression_window(_JETZT, RepeatSuppressionParameters(window_days=0)) is None

    def test_fenster_eins_ist_leer(self) -> None:
        """1 hiesse "nur der Analysetag sperrt" -- der sperrt aber nie;
        das Fenster ist dann leer, nicht negativ."""
        fenster = suppression_window(_JETZT, RepeatSuppressionParameters(window_days=1))
        assert fenster is not None
        seit, bis = fenster
        assert seit == bis

    def test_das_fenster_bleibt_zeitzonenbewusst(self) -> None:
        fenster = suppression_window(
            datetime(2026, 9, 1, 20, 0, tzinfo=UTC), RepeatSuppressionParameters(window_days=7)
        )
        assert fenster is not None
        seit, bis = fenster
        assert seit.tzinfo is not None
        assert bis.tzinfo is not None
