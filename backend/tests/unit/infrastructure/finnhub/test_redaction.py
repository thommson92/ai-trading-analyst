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


class TestProzentkodierung:
    def test_auch_die_kodierte_form_verschwindet(self) -> None:
        """``httpx`` kodiert Query-Werte. Ein Schluessel mit Sonderzeichen
        stuende sonst in veraenderter Schreibweise unverdeckt im Text."""
        schluessel = "abc/def+ghi=jkl"
        text = f"for url 'https://finnhub.io/x?token=abc%2Fdef%2Bghi%3Djkl' ({schluessel})"

        geschwaerzt = redact(text, schluessel)

        assert schluessel not in geschwaerzt
        assert "abc%2Fdef%2Bghi%3Djkl" not in geschwaerzt


class TestKurzerSchluesselMeldetSich:
    def test_die_uebergehung_wird_protokolliert(self, caplog: pytest.LogCaptureFixture) -> None:
        """Stillschweigend uebergangen stuende das Geheimnis unbemerkt im
        Protokoll -- der Fall, der am schwersten auffaellt."""
        with caplog.at_level("WARNING"):
            redact("irgendein Text", "kurz")

        assert any("geschwaerzt" in eintrag.message for eintrag in caplog.records)
