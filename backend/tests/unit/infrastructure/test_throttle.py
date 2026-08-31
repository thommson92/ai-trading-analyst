"""Die Drossel, die EDGAR und Finnhub gemeinsam benutzen.

Sie stand bis zum Messlauf ueber die Watchliste nur im EDGAR-Adapter. Dass
Finnhub sie ebenso braucht, hat der Lauf gezeigt: vier von 192 Symbolen
gingen an ``429 Too Many Requests`` verloren (ADR 0046).
"""

from __future__ import annotations

import pytest

from ai_trading_analyst.infrastructure.throttle import Drossel


class TestDrossel:
    def test_sie_wartet_zwischen_zwei_anfragen(self) -> None:
        gewartet: list[float] = []
        drossel = Drossel(2.0, sleep=gewartet.append)

        drossel.warte()
        drossel.warte()

        assert len(gewartet) == 1
        assert gewartet[0] == pytest.approx(0.5, abs=0.05)

    def test_die_erste_anfrage_wartet_nicht(self) -> None:
        """Sonst kostete jeder Einzelaufruf den vollen Abstand -- bei einer
        Rate unter eins je Sekunde waere schon ``cli ratings --symbol AAPL``
        spuerbar langsamer, ohne dass es etwas schuetzte."""
        gewartet: list[float] = []

        Drossel(0.8, sleep=gewartet.append).warte()

        assert gewartet == []

    def test_eine_nichtpositive_rate_ist_ein_fehler(self) -> None:
        with pytest.raises(ValueError, match="positiv"):
            Drossel(0.0)
