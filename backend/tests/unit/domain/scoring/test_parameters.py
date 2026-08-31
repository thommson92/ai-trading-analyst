"""Aus einer Kennzahl wird ein Teilwert (ADR 0045, Entscheidung 1).

Fuenf Stufen -- 2, 4, 6, 8, 10 -- und zwei Richtungen. Die Richtung ist der
Punkt, an dem ein Fehler am teuersten waere: Ein umgekehrt bewertetes KGV
machte aus dem teuersten Titel der Watchliste den guenstigsten.
"""

from __future__ import annotations

import pytest

from ai_trading_analyst.domain.scoring import MetricThresholds

AUFSTEIGEND = MetricThresholds(boundaries=(1.0, 2.0, 3.0, 4.0), higher_is_better=True)
ABSTEIGEND = MetricThresholds(boundaries=(1.0, 2.0, 3.0, 4.0), higher_is_better=False)


class TestHoeherIstBesser:
    @pytest.mark.parametrize(
        ("wert", "erwartet"),
        [(0.5, 2.0), (1.5, 4.0), (2.5, 6.0), (3.5, 8.0), (4.5, 10.0)],
    )
    def test_jedes_fuenftel_bekommt_seine_stufe(self, wert: float, erwartet: float) -> None:
        assert AUFSTEIGEND.score(wert) == erwartet

    def test_das_unterste_fuenftel_bekommt_zwei_und_nicht_null(self) -> None:
        """Ein Titel im untersten Fuenftel der Nettomarge hat trotzdem eine
        Nettomarge (ADR 0045). Mit 0 verschwaende die Komponente ihr ganzes
        Gewicht, obwohl sie gemessen wurde."""
        assert AUFSTEIGEND.score(-999.0) == 2.0

    def test_ein_wert_auf_der_grenze_faellt_in_das_bessere_fuenftel(self) -> None:
        """Die Grenzen sind selbst gemessene Werte der Watchliste."""
        assert AUFSTEIGEND.score(2.0) == 6.0
        assert AUFSTEIGEND.score(4.0) == 10.0


class TestNiedrigerIstBesser:
    @pytest.mark.parametrize(
        ("wert", "erwartet"),
        [(0.5, 10.0), (1.5, 8.0), (2.5, 6.0), (3.5, 4.0), (4.5, 2.0)],
    )
    def test_die_skala_ist_umgekehrt(self, wert: float, erwartet: float) -> None:
        assert ABSTEIGEND.score(wert) == erwartet

    def test_ein_wert_auf_der_grenze_faellt_ebenfalls_in_das_bessere_fuenftel(self) -> None:
        assert ABSTEIGEND.score(1.0) == 10.0
        assert ABSTEIGEND.score(4.0) == 4.0

    def test_die_beiden_richtungen_bewerten_denselben_wert_verschieden(self) -> None:
        """Der Test, der eine vertauschte Richtung fangen soll: Ohne ihn saehe
        eine Abbildung, die ``higher_is_better`` ignoriert, in beiden Klassen
        oben richtig aus."""
        assert AUFSTEIGEND.score(4.5) == 10.0
        assert ABSTEIGEND.score(4.5) == 2.0


class TestGrenzen:
    def test_unsortierte_grenzen_sind_ein_fehler(self) -> None:
        """Eine vertauschte Zeile in der Konfiguration ergaebe sonst eine
        Skala, die in der Mitte springt -- und niemand saehe es an."""
        with pytest.raises(ValueError, match="aufsteigen"):
            MetricThresholds(boundaries=(1.0, 3.0, 2.0, 4.0), higher_is_better=True)

    def test_gleiche_grenzen_sind_erlaubt(self) -> None:
        """Sie entstehen echt: Waechst eine Kennzahl bei mehr als einem
        Fuenftel der Watchliste um genau null, fallen zwei Quantile
        zusammen. Dann ist ein Fuenftel leer -- kein Fehler, nur eine
        Verteilung mit Stufe."""
        schwellen = MetricThresholds(boundaries=(1.0, 1.0, 2.0, 3.0), higher_is_better=True)
        assert schwellen.score(1.0) == 6.0
