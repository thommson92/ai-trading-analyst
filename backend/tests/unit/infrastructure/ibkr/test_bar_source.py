"""Die Teile der Barquelle, die ohne laufende TWS pruefbar sind.

Der eigentliche Verbindungsaufbau ist im Spike live gegen die TWS des
Projektinhabers belegt (``spikes/ibkr-marketdata/REPORT.md``, Frage 1 und 3)
und wird hier nicht nachgestellt -- ein Testdoppel fuer ``ib_async`` wuerde
nur die eigene Annahme ueber die Bibliothek pruefen.
"""

from __future__ import annotations

import pytest

from ai_trading_analyst.infrastructure.ibkr.bar_source import (
    SUPPORTED_BAR_MINUTES,
    ibkr_bar_size,
)


class TestBarGroesse:
    def test_die_minute_steht_in_der_einzahl(self) -> None:
        assert ibkr_bar_size(1) == "1 min"

    @pytest.mark.parametrize("minutes", [3, 5, 15])
    def test_alles_darueber_in_der_mehrzahl(self, minutes: int) -> None:
        assert ibkr_bar_size(minutes) == f"{minutes} mins"

    def test_eine_nicht_unterstuetzte_groesse_faellt_sofort_auf(self) -> None:
        # 13 teilt 195 zwar ohne Rest, IBKR kennt diese Bar-Groesse aber nicht.
        with pytest.raises(ValueError, match="13-Minuten-Bars"):
            ibkr_bar_size(13)

    def test_jede_unterstuetzte_groesse_teilt_die_kerze_ohne_rest(self) -> None:
        assert all(195 % minutes == 0 for minutes in SUPPORTED_BAR_MINUTES)
