"""Der Benachrichtigungsausgang.

Zwei Umsetzungen (ADR 0024): ``LoggingNotifier`` als ausgelieferter
Standard -- geprueft wird vor allem, dass niemand faelschlich glaubt, es sei
etwas versendet worden -- und ``TelegramNotifier``, der tatsaechlich
zustellt. Wie bei ``FinnhubEarningsProvider`` laeuft alles, was sich ohne
echtes Netzwerk pruefen laesst, ueber ``httpx.MockTransport``.
"""

from __future__ import annotations

import json

import httpx
import pytest

from ai_trading_analyst.config import NotificationsConfig, Secrets, TelegramConfig
from ai_trading_analyst.domain.scheduling import NotifierError
from ai_trading_analyst.infrastructure.notifications import (
    MAX_TEXT_ZEICHEN,
    LoggingNotifier,
    NotificationChannelNotConfiguredError,
    TelegramNotifier,
    TelegramSettings,
    build_notifier,
)


def _secrets(token: str | None = "bot-token") -> Secrets:
    return Secrets(_env_file=None, notification_token=token)


class TestAuswahl:
    def test_dry_run_ergibt_den_protokollierenden_ausgang(self) -> None:
        notifier = build_notifier(NotificationsConfig(), _secrets(token=None))
        assert isinstance(notifier, LoggingNotifier)

    def test_telegram_ergibt_den_telegram_ausgang(self) -> None:
        config = NotificationsConfig(channel="telegram", telegram=TelegramConfig(chat_id="12345"))
        notifier = build_notifier(config, _secrets())
        assert isinstance(notifier, TelegramNotifier)

    def test_telegram_ohne_chat_id_faellt_beim_start_auf(self) -> None:
        config = NotificationsConfig(channel="telegram")

        with pytest.raises(NotificationChannelNotConfiguredError, match="chat_id"):
            build_notifier(config, _secrets())

    def test_telegram_ohne_token_faellt_beim_start_auf(self) -> None:
        """Derselbe Fehler wie bei den Anbieter-Geheimnissen -- vor dem
        Backfill, nicht erst beim ersten Sendeversuch."""
        config = NotificationsConfig(channel="telegram", telegram=TelegramConfig(chat_id="12345"))

        with pytest.raises(Exception, match="ATA_NOTIFICATION_TOKEN"):
            build_notifier(config, _secrets(token=None))

    def test_pushover_ist_weiterhin_nicht_gebaut(self) -> None:
        """Ein nicht gebauter Kanal faellt beim Start auf, nicht erst
        abends, wenn die Meldung ausbleibt."""
        config = NotificationsConfig(channel="pushover")

        with pytest.raises(NotificationChannelNotConfiguredError, match="ADR 0024"):
            build_notifier(config, _secrets())


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


SETTINGS = TelegramSettings(
    token="bot-token",
    chat_id="12345",
    base_url="https://api.telegram.org",
    request_timeout_seconds=1.0,
)


def _notifier(handler: httpx.MockTransport) -> TelegramNotifier:
    return TelegramNotifier(SETTINGS, transport=handler)


class TestTelegramAusgang:
    def test_stellt_ueber_sendmessage_zu(self) -> None:
        gesehen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            gesehen.append(request)
            return httpx.Response(200, json={"ok": True})

        _notifier(httpx.MockTransport(handler)).send("Betreff", "Text")

        assert len(gesehen) == 1
        anfrage = gesehen[0]
        assert anfrage.url.path == "/botbot-token/sendMessage"
        payload = anfrage.read()
        assert b'"chat_id":"12345"' in payload
        assert b"Betreff" in payload
        assert b"Text" in payload

    def test_ein_fehlerstatus_wird_zu_notifiererror(self) -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(401))

        with pytest.raises(NotifierError):
            _notifier(transport).send("Betreff", "Text")

    @pytest.mark.parametrize("status", [401, 429, 500])
    def test_der_statuscode_landet_in_der_fehlermeldung(self, status: int) -> None:
        """401, 429 und 5xx sind verschiedene Ursachen -- falscher Token,
        Ratenlimit, Telegram-Ausfall -- und sollen im Protokoll unterscheidbar
        bleiben, ohne dass der Token dafuer noetig ist."""
        transport = httpx.MockTransport(lambda request: httpx.Response(status))

        with pytest.raises(NotifierError, match=str(status)):
            _notifier(transport).send("Betreff", "Text")

    def test_ein_verbindungsfehler_wird_zu_notifiererror(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Verbindung abgelehnt", request=request)

        with pytest.raises(NotifierError, match="ConnectError"):
            _notifier(httpx.MockTransport(handler)).send("Betreff", "Text")

    def test_der_bot_token_erscheint_nicht_im_fehlertext(self) -> None:
        """Der Token steckt im Pfad und damit in httpx' eigenem Fehlertext --
        der darf nicht ins Protokoll wandern."""
        transport = httpx.MockTransport(lambda request: httpx.Response(401))

        with pytest.raises(NotifierError) as fehler:
            _notifier(transport).send("Betreff", "Text")

        assert "bot-token" not in str(fehler.value)


class TestKuerzung:
    """Eine zu lange Meldung wird gekuerzt, nicht verworfen (ADR 0040).

    Telegram lehnt ueber 4096 Zeichen mit einem 400 ab; daraus wuerde ein
    ``NotifierError``, den der Aufrufer protokolliert -- aus "viele
    Kandidaten" wuerde "keine Nachricht", ausgerechnet am Tag mit dem meisten
    zu melden. Die Zusicherung stand seit ADR 0040 im Code und war bis hier
    ungeprueft.
    """

    def test_ein_zu_langer_text_wird_auf_die_grenze_gekuerzt(self) -> None:
        gesendet: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            gesendet.append(json.loads(request.content)["text"])
            return httpx.Response(200, json={"ok": True})

        _notifier(httpx.MockTransport(handler)).send("Betreff", "x" * (MAX_TEXT_ZEICHEN + 500))

        (text,) = gesendet
        assert len(text) <= MAX_TEXT_ZEICHEN

    def test_die_kuerzung_ist_als_kuerzung_erkennbar(self) -> None:
        """Eine stillschweigend abgeschnittene Liste saehe aus wie eine
        vollstaendige."""
        gesendet: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            gesendet.append(json.loads(request.content)["text"])
            return httpx.Response(200, json={"ok": True})

        _notifier(httpx.MockTransport(handler)).send("Betreff", "x" * (MAX_TEXT_ZEICHEN + 500))

        assert "gekuerzt" in gesendet[0]

    def test_ein_kurzer_text_bleibt_unangetastet(self) -> None:
        gesendet: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            gesendet.append(json.loads(request.content)["text"])
            return httpx.Response(200, json={"ok": True})

        _notifier(httpx.MockTransport(handler)).send("Betreff", "kurz und knapp")

        assert gesendet == ["Betreff\n\nkurz und knapp"]
