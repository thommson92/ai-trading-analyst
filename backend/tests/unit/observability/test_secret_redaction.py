"""Geheimnisse aus allem entfernen, was nach aussen geschrieben wird.

Der gemessene Befund steht im Modul-Docstring von ``secret_redaction``: Der
Finnhub-Schluessel stand in der URL und damit in drei Kanaelen -- im
Fehlertext, in **jeder erfolgreichen** ``httpx``-Anfragezeile und in der
``__cause__``-Kette hinter einer bereits geschwaerzten Meldung.

Die Tests hier decken alle drei ab. Der erste war vorher schon geschlossen,
die beiden anderen nicht.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from ai_trading_analyst.observability.secret_redaction import (
    forget_secrets,
    redact,
    redact_registered,
    register_secret,
)


@pytest.fixture(autouse=True)
def _leere_anmeldung() -> Iterator[None]:
    """Die Anmeldung ist modulweit. Ohne Aufraeumen truege ein Test das
    Geheimnis des vorigen mit sich -- und eine fehlende Anmeldung fiele
    nicht auf, weil ein frueherer Test sie schon vorgenommen hat."""
    forget_secrets()
    yield
    forget_secrets()


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
    def test_die_uebergehung_wird_beim_anmelden_protokolliert(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Stillschweigend uebergangen stuende das Geheimnis unbemerkt im
        Protokoll -- der Fall, der am schwersten auffaellt.

        Die Warnung sitzt am **Anmelden**, nicht am Schwaerzen: ``redact``
        laeuft im Fehlerpfad und je Logzeile; von dort aus warnte sie
        entweder tausendfach oder wuerde selbst wieder protokolliert.
        """
        with caplog.at_level("WARNING"):
            register_secret("kurz")

        assert any("geschwaerzt" in eintrag.message for eintrag in caplog.records)

    def test_ein_zu_kurzes_geheimnis_wird_nicht_angemeldet(self) -> None:
        """Angemeldet zerschriebe es jede Logzeile, in der zufaellig dieselben
        vier Zeichen vorkommen."""
        register_secret("kurz")
        assert redact_registered("kurz und knapp") == "kurz und knapp"

    def test_das_anmelden_wirft_nie(self) -> None:
        """Ein Schutznetz darf nicht die Ursache sein, dass ein Lauf nicht
        startet. Ob ein Wert plausibel ist, prueft ``Secrets``."""
        register_secret("")
        register_secret("x")


class TestAngemeldeteGeheimnisse:
    def test_ein_angemeldetes_geheimnis_verschwindet(self) -> None:
        register_secret("abcdef1234567890")
        assert "abcdef1234567890" not in redact_registered("token=abcdef1234567890")

    def test_ohne_anmeldung_bleibt_der_text_unveraendert(self) -> None:
        """Der Normalfall in Tests und bei einem Lauf ohne Zugangsdaten."""
        assert redact_registered("voellig harmlos") == "voellig harmlos"

    def test_mehrere_geheimnisse_werden_alle_entfernt(self) -> None:
        """Ein Lauf haelt Datenbank-URL, LLM-Schluessel, Telegram-Token und
        Finnhub-Schluessel gleichzeitig."""
        register_secret("erstes-geheimnis-lang")
        register_secret("zweites-geheimnis-lang")

        geschwaerzt = redact_registered("a=erstes-geheimnis-lang b=zweites-geheimnis-lang")

        assert "erstes-geheimnis-lang" not in geschwaerzt
        assert "zweites-geheimnis-lang" not in geschwaerzt
