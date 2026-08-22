"""Ausgang fuer Meldungen an den Nutzer.

Der Kanal ist als F10 noch nicht entschieden (siehe
``docs/adr/README.md``). Bis dahin gibt es genau eine Umsetzung: Sie
protokolliert. Der **Ausloeser** entsteht trotzdem schon jetzt, damit der
Dispatcher spaeter nicht angefasst werden muss, nur weil ein Push-Dienst
dazukommt (ADR 0019).
"""

from __future__ import annotations

from ai_trading_analyst.config.settings import NotificationsConfig
from ai_trading_analyst.observability.logging_setup import get_logger

_logger = get_logger(__name__)


class NotificationChannelNotConfiguredError(RuntimeError):
    """Ein Kanal ist eingestellt, den es noch nicht gibt."""


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


def build_notifier(config: NotificationsConfig) -> LoggingNotifier:
    """Waehlt den Kanal anhand der Konfiguration.

    ``telegram`` und ``pushover`` sind im Schema bereits vorgesehen, aber
    nicht entschieden und nicht gebaut. Wer sie einstellt, soll das sofort
    erfahren -- und nicht abends feststellen, dass eine Meldung ausgeblieben
    ist.
    """
    if config.channel != "dry_run":
        raise NotificationChannelNotConfiguredError(
            f"notifications.channel steht auf '{config.channel}', dieser Kanal ist aber "
            "noch nicht ausgewaehlt und nicht umgesetzt (F10). Zulaessig ist derzeit "
            "nur 'dry_run'."
        )
    return LoggingNotifier()
