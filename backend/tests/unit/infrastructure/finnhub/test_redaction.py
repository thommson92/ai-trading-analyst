"""Schwaerzung des Zugangsschluessels in Fehlertexten."""

from __future__ import annotations

import pytest

from ai_trading_analyst.infrastructure.finnhub.redaction import redact


class TestSchwaerzung:
    def test_der_schluessel_verschwindet(self) -> None:
        text = "Server error for url 'https://finnhub.io/x?token=abcdef1234567890'"
        assert "abcdef1234567890" not in redact(text, "abcdef1234567890")

    def test_jedes_vorkommen_verschwindet(self) -> None:
        """Ein Fehlertext kann die URL mehrfach nennen -- eine Ersetzung
        allein liesse das zweite Vorkommen stehen."""
        schluessel = "abcdef1234567890"
        text = f"{schluessel} ... und nochmal {schluessel}"
        assert schluessel not in redact(text, schluessel)

    def test_der_uebrige_text_bleibt_lesbar(self) -> None:
        """Eine geschwaerzte Meldung muss noch sagen, was schiefging."""
        text = "Server error '500' for url 'https://finnhub.io/x?symbol=AAPL&token=abcdef1234567890'"
        geschwaerzt = redact(text, "abcdef1234567890")
        assert "500" in geschwaerzt
        assert "AAPL" in geschwaerzt


class TestKurzeGeheimnisse:
    @pytest.mark.parametrize("secret", ["", "a", "1234567"])
    def test_werden_uebergangen(self, secret: str) -> None:
        """Ein leerer String ersetzte jede Position im Text, ein einzelnes
        Zeichen zerschriebe ihn -- ohne etwas zu schuetzen. Ein echter
        Finnhub-Schluessel ist deutlich laenger."""
        text = "Server error '500' for url 'https://finnhub.io/x'"
        assert redact(text, secret) == text

    def test_acht_zeichen_werden_noch_geschwaerzt(self) -> None:
        """Die Grenze selbst -- sonst bliebe unklar, auf welcher Seite sie liegt."""
        assert redact("...12345678...", "12345678") == "...***..."
