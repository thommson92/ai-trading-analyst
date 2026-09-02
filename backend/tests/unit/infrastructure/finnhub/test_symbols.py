"""Tests der Symboluebersetzung IBKR -> Finnhub."""

from __future__ import annotations

from ai_trading_analyst.infrastructure.finnhub.symbols import finnhub_symbol


class TestFinnhubSymbol:
    def test_klassenaktie_wird_uebersetzt(self) -> None:
        assert finnhub_symbol("BRK B") == "BRK.B"

    def test_gewoehnliches_symbol_bleibt_unveraendert(self) -> None:
        assert finnhub_symbol("AAPL") == "AAPL"

    def test_idempotent(self) -> None:
        assert finnhub_symbol(finnhub_symbol("BRK B")) == "BRK.B"

    def test_randbereinigung(self) -> None:
        assert finnhub_symbol(" brk b ") == "BRK.B"
