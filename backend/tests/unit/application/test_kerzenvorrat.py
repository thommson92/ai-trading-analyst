"""Der Vorrat gerechneter Kerzenserien (ADR 0072)."""

from __future__ import annotations

from ai_trading_analyst.application.kerzenvorrat import Kerzenvorrat

from .conftest import make_series


class TestKerzenvorrat:
    def test_was_abgelegt_wurde_kommt_zurueck(self) -> None:
        vorrat = Kerzenvorrat()
        reihe = make_series(300, candidate=False)
        vorrat.lege_ab("AAPL", reihe)
        assert vorrat.hole("AAPL") is reihe

    def test_ein_fehltreffer_ist_kein_fehler(self) -> None:
        """Der Normalfall, nicht der Ausnahmezustand.

        Die Wiederholsperre (ADR 0054) nimmt der Analyse taeglich ein paar
        Dutzend Titel ab; die brauchen trotzdem einen Chart. Wer hier eine
        Ausnahme wuerfe, machte aus dem Regelfall einen Stoerfall.
        """
        assert Kerzenvorrat().hole("AAPL") is None

    def test_eine_zweite_ablage_ersetzt_die_erste(self) -> None:
        vorrat = Kerzenvorrat()
        vorrat.lege_ab("AAPL", make_series(300, candidate=False))
        zweite = make_series(320, candidate=False)
        vorrat.lege_ab("AAPL", zweite)
        assert vorrat.hole("AAPL") is zweite
        assert len(vorrat) == 1
