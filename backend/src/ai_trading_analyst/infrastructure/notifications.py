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


MAX_TEXT_ZEICHEN = 4096
"""Harte Grenze von ``sendMessage``. Darueber antwortet Telegram mit 400."""

_KUERZUNGSHINWEIS = "\n[... gekuerzt, vollstaendig im Bericht]"


def _gekuerzt(text: str) -> str:
    """Kuerzt auf die Laenge, die Telegram annimmt -- und sagt es.

    Ohne das faellt eine lange Meldung **ganz** aus: Der 400 wird zu einem
    ``NotifierError``, der Aufrufer protokolliert und schweigt. Aus "viele
    Kandidaten" wuerde damit "keine Nachricht" -- der schlechteste Ausgang,
    und ausgerechnet an dem Tag, an dem am meisten zu melden ist.

    Die Kuerzung wird gekennzeichnet, weil eine stillschweigend abgeschnittene
    Liste aussaehe wie eine vollstaendige.

    Geschnitten wird an der letzten **Blockgrenze** (Leerzeile) vor dem Limit
    (ADR 0055): Seit die Meldung Bloecke traegt, saehe ein Schnitt mitten im
    Wort nach einem Defekt aus, und ein halber Block behauptete Angaben, die
    er nicht mehr enthaelt. Ein Blockschnitt, der mehr als die Haelfte des
    Fensters verwerfen wuerde, faellt auf den harten Schnitt zurueck --
    sonst kollabierte eine Meldung, deren einzige Leerzeile die hinter dem
    Betreff ist, auf den blossen Betreff.
    """
    if len(text) <= MAX_TEXT_ZEICHEN:
        return text
    grenze = MAX_TEXT_ZEICHEN - len(_KUERZUNGSHINWEIS)
    # rfind verlangt das vollstaendige "\n\n" vor dem Ende-Index; grenze + 2
    # erlaubt damit genau die Schnittstellen, deren Rumpf noch in die Grenze
    # passt (schnitt <= grenze).
    schnitt = text.rfind("\n\n", 0, grenze + 2)
    if schnitt < grenze // 2:
        schnitt = grenze
    return text[:schnitt] + _KUERZUNGSHINWEIS


class TelegramNotifier:
    """Stellt Meldungen ueber die Telegram Bot API zu (ADR 0024).

    Ein einzelner POST auf ``sendMessage``, kein Verbindungsmanagement.

    **Der Meldungstext bleibt bewusst duenn**, weil er das eigene Netz
    verlaesst. Wie duenn, entscheidet der Absender, nicht dieser Adapter:

    - Ein ausgefallener Lauf meldet Handelstag, Kerzenzeitpunkt und Ursache
      (ADR 0024).
    - Ein erfolgreicher Lauf meldet je Kandidat einen Block aus Symbol,
      Stufe, Signalzahl, Scores und -- bei empfohlenen Stufen -- dem besten
      Put-Vorschlag; **keinen Modell-Freitext** (ADR 0040/0047/0055, die
      ADR 0024 an dieser Stelle bewusst lockern).

    ``sendMessage`` lehnt Texte ueber ``MAX_TEXT_ZEICHEN`` mit einem 400 ab.
    Der Adapter kuerzt deshalb selbst und kennzeichnet die Kuerzung: Eine zu
    lange Meldung soll ankommen und nicht ausfallen -- der Kanal ist gebaut,
    um stille Ausfaelle sichtbar zu machen, und duerfte nicht selbst einer
    werden.
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
                    json={
                        "chat_id": self._settings.chat_id,
                        "text": _gekuerzt(f"{subject}\n\n{body}"),
                    },
                )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            # Der Statuscode allein verraet nichts -- der Token steckt im
            # Pfad und damit in httpx' eigenem Fehlertext, der deshalb NICHT
            # weiterwandert. Der Code unterscheidet aber "Token falsch" (401)
            # von "zu viele Anfragen" (429) von "Telegram ist down" (5xx),
            # und genau das braucht, wer die Meldung im Protokoll liest.
            raise NotifierError(
                f"Telegram hat die Meldung mit Status {error.response.status_code} abgelehnt."
            ) from None
        except httpx.HTTPError as error:
            # Verbindungsfehler tragen keinen Status -- nur der Ausnahmetyp
            # wandert weiter, aus demselben Grund wie oben.
            raise NotifierError(
                f"Telegram war nicht erreichbar ({type(error).__name__})."
            ) from None


def build_notifier(config: NotificationsConfig, secrets: Secrets) -> Notifier:
    """Waehlt den Kanal anhand der Konfiguration.

    Scheitert **vor** dem Lauf, wenn ein Kanal eingestellt ist, dem etwas
    fehlt. Das ist Absicht: ``command_dispatch`` ruft das hier vor dem
    halbstuendigen Backfill auf, und wer eine unvollstaendige Einstellung
    hinterlassen hat, soll das sofort erfahren -- nicht abends daran merken,
    dass eine Meldung ausgeblieben ist.

    Es gibt genau zwei Kanaele. ``pushover`` stand bis 2026-09-01 im Schema,
    ohne je gebaut zu sein; die Konfiguration nimmt den Wert nicht mehr an
    (ADR 0024, Nachtrag). Damit faellt hier auch der Zweig weg, der einen
    eingestellten Kanal wieder zurueckweisen musste.
    """
    if config.channel == "dry_run":
        return LoggingNotifier()

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
