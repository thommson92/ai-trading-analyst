"""Der Benachrichtigungsausgang.

Der Kanal ist als F10 noch nicht entschieden. Geprueft wird deshalb vor
allem, dass niemand faelschlich glaubt, es sei etwas versendet worden.
"""

from __future__ import annotations

import pytest

from ai_trading_analyst.config import NotificationsConfig
from ai_trading_analyst.infrastructure.notifications import (
    LoggingNotifier,
    NotificationChannelNotConfiguredError,
    build_notifier,
)


class TestAuswahl:
    def test_dry_run_ergibt_den_protokollierenden_ausgang(self) -> None:
        assert isinstance(build_notifier(NotificationsConfig()), LoggingNotifier)

    @pytest.mark.parametrize("kanal", ["telegram", "pushover"])
    def test_ein_nicht_gebauter_kanal_faellt_beim_start_auf(self, kanal: str) -> None:
        """Und nicht erst abends, wenn die Meldung ausbleibt."""
        config = NotificationsConfig(channel=kanal)

        with pytest.raises(NotificationChannelNotConfiguredError, match="F10"):
            build_notifier(config)


class TestProtokollierenderAusgang:
    def test_die_meldung_erscheint_als_fehler(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level("ERROR"):
            LoggingNotifier().send("Lauf ausgefallen", "Die TWS war nicht erreichbar.")

        assert "Lauf ausgefallen" in caplog.text
        assert "Die TWS war nicht erreichbar." in caplog.text

    def test_sie_sagt_ausdruecklich_dass_nichts_versendet_wurde(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Wer ins Protokoll sieht, soll nicht glauben, das Telefon habe
        geklingelt."""
        with caplog.at_level("ERROR"):
            LoggingNotifier().send("Betreff", "Text")

        assert "nicht versendet" in caplog.text
