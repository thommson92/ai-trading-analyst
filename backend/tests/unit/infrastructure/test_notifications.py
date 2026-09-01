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
from pydantic import ValidationError

from ai_trading_analyst.config import NotificationsConfig, Secrets, TelegramConfig
from ai_trading_analyst.domain.report import render_notification
from ai_trading_analyst.domain.scheduling import NotifierError
from ai_trading_analyst.infrastructure.notifications import (
    MAX_TEXT_ZEICHEN,
    LoggingNotifier,
    NotificationChannelNotConfiguredError,
    TelegramNotifier,
    TelegramSettings,
    build_notifier,
)
from tests.unit.domain.report.test_notification import kandidat, zusammenfassung


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

    def test_pushover_nimmt_die_konfiguration_nicht_mehr_an(self) -> None:
        """Der nie gebaute Kanal ist aus dem Schema verschwunden (ADR 0024,
        Nachtrag). Vorher nahm die Konfiguration ihn an und die Anwendung
        wies ihn zurueck -- ein Versprechen ohne Deckung."""
        with pytest.raises(ValidationError):
            NotificationsConfig(channel="pushover")


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


class TestLaengeEinerEchtenMeldung:
    """Wie viele Kandidaten passen, bevor gekuerzt wird (ADR 0047).

    **Gemessen an dem, was tatsaechlich versendet wird** -- also an
    ``Betreff + Leerzeile + Text``, nicht am Text allein. Der erste Anlauf
    dieses Tests mass nur den Text und war damit um eine Zeile zu
    optimistisch; der Betreff waechst ausserdem mit der Kandidatenzahl.

    Der Test steht hier und nicht beim Renderer: Die Grenze ist eine
    Eigenschaft des Kanals.
    """

    @staticmethod
    def _laenge(anzahl: int, *, voll: bool) -> int:
        gesendet: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            gesendet.append(json.loads(request.content)["text"])
            return httpx.Response(200, json={"ok": True})

        betreff, text = render_notification(
            zusammenfassung(
                *(
                    kandidat(f"SYM{i:04d}", swing=8.6, investment=5.5, voll=voll)
                    for i in range(anzahl)
                ),
                aktien=200,
            ),
            timezone="America/New_York",
        )
        _notifier(httpx.MockTransport(handler)).send(betreff, text)
        return len(gesendet[0])

    def test_im_unguenstigsten_fall_passen_vierundzwanzig(self) -> None:
        """Drei Signale, Fehlsignalrisiko und Earnings-Hinweis -- die
        laengstmoegliche Zeile."""
        assert self._laenge(24, voll=True) <= MAX_TEXT_ZEICHEN
        assert self._laenge(25, voll=True) == MAX_TEXT_ZEICHEN

    def test_mit_der_kurzen_zeile_passen_einundfuenfzig(self) -> None:
        assert self._laenge(51, voll=False) <= MAX_TEXT_ZEICHEN
        assert self._laenge(52, voll=False) == MAX_TEXT_ZEICHEN

    def test_jenseits_der_grenze_wird_gekuerzt_und_nicht_verworfen(self) -> None:
        """Der eigentliche Zweck: Aus "viele Kandidaten" darf nicht "keine
        Nachricht" werden."""
        gesendet: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            gesendet.append(json.loads(request.content)["text"])
            return httpx.Response(200, json={"ok": True})

        betreff, text = render_notification(
            zusammenfassung(
                *(
                    kandidat(f"SYM{i:04d}", swing=8.6, investment=5.5, voll=True)
                    for i in range(60)
                ),
                aktien=200,
            ),
            timezone="America/New_York",
        )
        _notifier(httpx.MockTransport(handler)).send(betreff, text)

        assert "gekuerzt" in gesendet[0]
        assert "SYM0000" in gesendet[0], "der beste Kandidat ist trotz Kuerzung dabei"
