"""Ausgang fuer Meldungen an den Nutzer.

Der Ausloeser entsteht im Dispatcher (ADR 0019), der Kanal ist seit
[ADR 0024](../../../../docs/adr/0024-benachrichtigungskanal-telegram.md)
entschieden: Telegram.

Zwei Umsetzungen. ``LoggingNotifier`` bleibt der ausgelieferte Standard und
protokolliert nur -- so laufen Tests und ein frisch aufgesetzter Server ohne
Zugangsdaten. ``TelegramNotifier`` stellt tatsaechlich zu.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from ai_trading_analyst.config.settings import NotificationsConfig, Secrets
from ai_trading_analyst.domain.scheduling import Notifier, NotifierError
from ai_trading_analyst.observability.logging_setup import get_logger

_logger = get_logger(__name__)


class NotificationChannelNotConfiguredError(RuntimeError):
    """Ein Kanal ist eingestellt, den es noch nicht gibt oder dem etwas fehlt."""


class LoggingNotifier:
    """Schreibt die Meldung ins Protokoll, statt sie zu versenden.

    Kein stiller Ersatz: Die Meldung erscheint auf ERROR-Ebene und nennt
    ausdruecklich, dass sie nicht versendet wurde. Wer ins Log sieht, soll
    nicht glauben, das Telefon habe geklingelt.
    """

    def send(self, subject: str, body: str) -> None:
        _logger.error(
            "MELDUNG (nicht versendet -- kein Kanal eingerichtet): %s -- %s", subject, body
        )


@dataclass(frozen=True, slots=True)
class TelegramSettings:
    """Adresse und Zugang des Bots.

    ``token`` ist das Geheimnis und stammt aus ``ATA_NOTIFICATION_TOKEN``;
    ``chat_id`` ist nur eine Adresse und steht in der Konfiguration.
    """

    token: str
    chat_id: str
    base_url: str
    request_timeout_seconds: float


class TelegramNotifier:
    """Stellt Meldungen ueber die Telegram Bot API zu (ADR 0024).

    Ein einzelner POST auf ``sendMessage``, kein Verbindungsmanagement: Der
    Kanal wird nur im Fehlerfall angefasst, und das hoechstens ein paar Mal
    im Jahr.

    **Der Meldungstext bleibt bewusst duenn.** Er verlaesst das eigene Netz,
    deshalb enthaelt er nur Handelstag, Kerzenzeitpunkt und Ursache -- keine
    Kurse, keine Kandidaten, keine Analyseergebnisse.
    """

    def __init__(
        self, settings: TelegramSettings, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._settings = settings
        self._transport = transport
        """Nur fuer Tests gesetzt (``httpx.MockTransport``). ``None`` verwendet
        den echten Transport von ``httpx``."""

    def send(self, subject: str, body: str) -> None:
        try:
            with httpx.Client(
                transport=self._transport, timeout=self._settings.request_timeout_seconds
            ) as client:
                response = client.post(
                    f"{self._settings.base_url}/bot{self._settings.token}/sendMessage",
                    json={"chat_id": self._settings.chat_id, "text": f"{subject}\n\n{body}"},
                )
            response.raise_for_status()
        except httpx.HTTPError as error:
            # Der Token steckt im Pfad und damit in httpx' Fehlertext. Nur der
            # Typ und die Statuszeile wandern deshalb weiter -- eine
            # Fehlermeldung landet im Protokoll, und dort hat er nichts zu
            # suchen.
            raise NotifierError(
                f"Telegram hat die Meldung nicht angenommen ({type(error).__name__})."
            ) from None


def build_notifier(config: NotificationsConfig, secrets: Secrets) -> Notifier:
    """Waehlt den Kanal anhand der Konfiguration.

    Scheitert **vor** dem Lauf, wenn ein Kanal eingestellt ist, dem etwas
    fehlt. Das ist Absicht: ``command_dispatch`` ruft das hier vor dem
    halbstuendigen Backfill auf, und wer eine unvollstaendige Einstellung
    hinterlassen hat, soll das sofort erfahren -- nicht abends daran merken,
    dass eine Meldung ausgeblieben ist.

    ``pushover`` steht weiterhin im Schema und ist weiterhin nicht gebaut
    (ADR 0024).
    """
    if config.channel == "dry_run":
        return LoggingNotifier()

    if config.channel == "telegram":
        if config.telegram.chat_id is None:
            raise NotificationChannelNotConfiguredError(
                "notifications.channel steht auf 'telegram', aber "
                "notifications.telegram.chat_id ist nicht gesetzt. Ohne Empfaenger "
                "gibt es niemanden zu benachrichtigen."
            )
        return TelegramNotifier(
            TelegramSettings(
                token=secrets.require("notification_token"),
                chat_id=config.telegram.chat_id,
                base_url=config.telegram.base_url,
                request_timeout_seconds=config.telegram.request_timeout_seconds,
            )
        )

    raise NotificationChannelNotConfiguredError(
        f"notifications.channel steht auf '{config.channel}', dieser Kanal ist aber "
        "nicht umgesetzt (ADR 0024). Zulaessig sind 'dry_run' und 'telegram'."
    )
