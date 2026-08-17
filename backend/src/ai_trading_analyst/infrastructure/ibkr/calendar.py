"""Boersenkalender aus den Handelszeiten der TWS (ADR 0019).

IBKR liefert zu jedem Kontrakt die Handelszeiten der Boerse -- mit
Feiertagen und verkuerzten Tagen, aus derselben Quelle, die auch die Kurse
liefert. Ein eigener Feiertagskalender waere eine Liste, die jaehrlich
stimmen muss; ein Fehler darin fuehrte zu einem uebersprungenen Handelstag,
und das faellt niemandem auf.

Gelesen wird ``liquidHours``, nicht ``tradingHours``: Gerechnet wird
ausschliesslich auf der regulaeren Sitzung, und ``tradingHours`` enthaelt
auch den vor- und nachboerslichen Handel.

Das Parsen ist bewusst von der Abfrage getrennt. Es ist reine Textarbeit und
damit ohne laufende TWS pruefbar -- gerade die Sonderfaelle (Feiertag,
verkuerzter Tag, Zeitumstellung) treten selten genug auf, dass man sie nicht
abwarten will.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from ai_trading_analyst.domain.analysis import ContractSpec, MarketDataProviderError
from ai_trading_analyst.domain.scheduling import TradingCalendarError, TradingSession


class LiquidHoursSource(Protocol):
    """Der Teil der TWS-Anbindung, den der Kalender braucht."""

    def liquid_hours(self, contract: ContractSpec) -> tuple[str, str]: ...


class LiquidHoursError(ValueError):
    """Die Handelszeiten waren nicht lesbar."""


def parse_liquid_hours(text: str, timezone: str) -> dict[date, TradingSession | None]:
    """Uebersetzt IBKRs ``liquidHours`` in Sitzungen je Tag.

    Das Format ist eine Kette aus Abschnitten, getrennt durch Semikolon::

        20260814:0930-20260814:1600;20260815:CLOSED

    ``CLOSED`` heisst Feiertag oder Wochenende; im Ergebnis steht dafuer
    ``None``, damit sich "kein Handelstag" von "kein Eintrag vorhanden"
    unterscheiden laesst.

    Ein Abschnitt kann ueber Mitternacht laufen; massgeblich fuer den
    Handelstag ist deshalb das Datum des **Beginns**.
    """
    zone = ZoneInfo(timezone)
    sitzungen: dict[date, TradingSession | None] = {}
    for abschnitt in text.split(";"):
        abschnitt = abschnitt.strip()
        if not abschnitt:
            continue
        if abschnitt.endswith(":CLOSED"):
            tag = _parse_day(abschnitt.split(":", 1)[0])
            sitzungen[tag] = None
            continue
        beginn, ende = _parse_span(abschnitt, zone)
        sitzungen[beginn.date()] = TradingSession(
            session_date=beginn.date(), open=beginn, close=ende
        )
    if not sitzungen:
        raise LiquidHoursError(f"Keine Handelszeiten erkennbar in '{text}'")
    return sitzungen


def _parse_span(abschnitt: str, zone: ZoneInfo) -> tuple[datetime, datetime]:
    teile = abschnitt.split("-")
    if len(teile) != 2:
        raise LiquidHoursError(f"Abschnitt ohne Zeitspanne: '{abschnitt}'")
    return _parse_moment(teile[0], zone), _parse_moment(teile[1], zone)


def _parse_moment(rohwert: str, zone: ZoneInfo) -> datetime:
    tag, _, uhrzeit = rohwert.partition(":")
    if len(uhrzeit) != 4 or not uhrzeit.isdigit():
        raise LiquidHoursError(f"Unerwartete Uhrzeit: '{rohwert}'")
    try:
        # Vier Ziffern heisst noch nicht gueltig: '2400' und '1265' kommen bis
        # hierher. Ein roher ValueError liefe am Aufrufer vorbei, der nur
        # TradingCalendarError abfaengt -- der Dispatcher braeche dann mit
        # einem Traceback ab, statt auf die angenommene Sitzung auszuweichen.
        zeit = datetime.strptime(uhrzeit, "%H%M").time()  # noqa: DTZ007 -- nur die Uhrzeit
    except ValueError as error:
        raise LiquidHoursError(f"Unerwartete Uhrzeit: '{rohwert}'") from error
    return datetime.combine(_parse_day(tag), zeit, tzinfo=zone)


def _parse_day(rohwert: str) -> date:
    if len(rohwert) != 8 or not rohwert.isdigit():
        raise LiquidHoursError(f"Unerwartetes Datum: '{rohwert}'")
    try:
        return date(int(rohwert[:4]), int(rohwert[4:6]), int(rohwert[6:]))
    except ValueError as error:
        raise LiquidHoursError(f"Unerwartetes Datum: '{rohwert}'") from error


class IbkrTradingCalendar:
    """``TradingCalendar`` ueber die Handelszeiten eines Referenzkontrakts.

    Gefragt wird stellvertretend **eine** Aktie der Watchlist. Die
    Handelszeiten gelten fuer die Boerse, nicht fuer das einzelne Papier; ein
    eigener Konfigurationsschluessel dafuer waere eine Stellschraube mehr, die
    stimmen muss, ohne etwas zu gewinnen.

    Die Antwort wird fuer die Lebensdauer des Prozesses behalten. Der
    Dispatcher laeuft einmal und fragt einmal -- ein Zwischenspeicher ueber
    Tage hinweg waere hier falsch, weil sich Kalender aendern.
    """

    def __init__(self, source: LiquidHoursSource, contract: ContractSpec) -> None:
        self._source = source
        self._contract = contract
        self._sessions: dict[date, TradingSession | None] | None = None

    def session_on(self, day: date) -> TradingSession | None:
        sessions = self._load()
        if day not in sessions:
            # IBKR liefert nur ein Fenster um den heutigen Tag. Ein Datum
            # ausserhalb ist keine Aussage ueber einen Feiertag, sondern eine
            # fehlende Auskunft -- und die darf nicht als "kein Handelstag"
            # durchgehen.
            raise TradingCalendarError(
                f"Die Handelszeiten von '{self._contract.symbol}' enthalten keinen "
                f"Eintrag fuer {day.isoformat()}."
            )
        return sessions[day]

    def _load(self) -> dict[date, TradingSession | None]:
        if self._sessions is not None:
            return self._sessions
        try:
            rohwert, zeitzone = self._source.liquid_hours(self._contract)
        except MarketDataProviderError as error:
            raise TradingCalendarError(str(error)) from error
        try:
            self._sessions = parse_liquid_hours(rohwert, zeitzone)
        except (LiquidHoursError, KeyError) as error:
            raise TradingCalendarError(
                f"Handelszeiten von '{self._contract.symbol}' nicht lesbar: {error}"
            ) from error
        return self._sessions
