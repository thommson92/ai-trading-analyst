"""Zugriff auf den Finnhub-Earnings-Kalender.

Freigegeben durch [ADR 0017](../../../../../docs/adr/0017-finnhub-fuer-earnings-und-ratings.md),
Statusmodell und Kerzenzaehlung durch
[ADR 0020](../../../../../docs/adr/0020-earnings-filter-status-und-handelstagskalender.md).

Anders als der IBKR-Adapter haelt dieser Client keine dauerhafte Verbindung:
Finnhub wird nur fuer die Kandidaten eines Tages angefragt (ADR 0017, rund
10 bis 20 Symbole), das rechtfertigt kein Verbindungsmanagement wie bei der
paced, dauerhaft gehaltenen IBKR-Verbindung. ``httpx`` hat zudem keinen
Event-Loop-Nebeneffekt wie ``ib_async`` -- ein regulaerer Modul-Import genuegt.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from ai_trading_analyst.domain.analysis import EarningsProviderError, Stock
from ai_trading_analyst.domain.earnings import NextEarningsDate
from ai_trading_analyst.infrastructure.throttle import Drossel
from ai_trading_analyst.observability.logging_setup import get_logger
from ai_trading_analyst.observability.secret_redaction import redact

_logger = get_logger(__name__)

_SOURCE_NAME = "finnhub"
_SUSPICIOUS_ENTRY_COUNT = 50
"""Kein einzelnes Symbol kann in einem wenige Wochen kurzen Fenster
plausibel mehr Termine haben. Eine so grosse Antwort deutet auf ein
unerwartetes Antwortformat hin (ADR 0017 L4: stille Kuerzung bei 1500
Treffern) -- besser abbrechen als einer unplausiblen Antwort vertrauen."""


class FinnhubEarningsProviderError(EarningsProviderError):
    """Finnhub war nicht erreichbar oder hat keine verwertbare Antwort geliefert."""


@dataclass(frozen=True, slots=True)
class FinnhubConnectionSettings:
    base_url: str
    api_key: str
    request_timeout_seconds: float
    lookahead_calendar_days: int
    max_requests_per_second: float


class FinnhubEarningsProvider:
    """Implementiert ``EarningsProvider`` gegen die Finnhub-REST-API."""

    def __init__(
        self,
        settings: FinnhubConnectionSettings,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        drossel: Drossel | None = None,
    ) -> None:
        self._settings = settings
        self._now = now
        self._drossel = drossel or Drossel(settings.max_requests_per_second, sleep)
        """**Eine Drossel je Konto, nicht je Endpunkt.** Finnhubs Grenze von
        60 Anfragen je Minute gilt fuer den Zugangsschluessel; der Tageslauf
        fragt je Kandidat beide Endpunkte unmittelbar nacheinander. Mit zwei
        eigenen Drosseln liesse jede den ersten Aufruf sofort durch, und aus
        einer Anfrage je Sekunde wuerden zwei. ``bootstrap`` reicht deshalb
        dieselbe herein; der Default gilt nur fuer Tests und Einzelaufrufe."""
        self._transport = transport
        """Nur fuer Tests gesetzt (``httpx.MockTransport``). ``None`` verwendet
        den echten Transport von ``httpx``."""

    def next_earnings_date(self, stock: Stock) -> NextEarningsDate | None:
        symbol = stock.symbol
        today = self._now().date()
        self._drossel.warte()
        window_end = today + timedelta(days=self._settings.lookahead_calendar_days)

        try:
            with httpx.Client(
                transport=self._transport, timeout=self._settings.request_timeout_seconds
            ) as client:
                response = client.get(
                    f"{self._settings.base_url}/calendar/earnings",
                    params={
                        "symbol": symbol,
                        "from": today.isoformat(),
                        "to": window_end.isoformat(),
                        "token": self._settings.api_key,
                    },
                )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            # Der Fehlertext von ``httpx`` enthaelt die vollstaendige URL --
            # samt Zugangsschluessel. Ohne Schwaerzung stuende er auf stderr.
            raise FinnhubEarningsProviderError(
                f"Earnings-Kalender fuer '{symbol}' konnte nicht abgerufen werden: "
                f"{redact(str(error), self._settings.api_key)}"
            ) from error

        return self._parse_earliest_entry(symbol, payload)

    def _parse_earliest_entry(
        self, symbol: str, payload: dict[str, Any]
    ) -> NextEarningsDate | None:
        entries = payload.get("earningsCalendar") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            raise FinnhubEarningsProviderError(
                f"Unerwartetes Antwortformat des Earnings-Kalenders fuer '{symbol}': "
                f"Feld 'earningsCalendar' fehlt oder ist keine Liste."
            )

        if len(entries) > _SUSPICIOUS_ENTRY_COUNT:
            raise FinnhubEarningsProviderError(
                f"Earnings-Kalender fuer '{symbol}' lieferte {len(entries)} Eintraege in einem "
                f"{self._settings.lookahead_calendar_days}-Tage-Fenster -- unplausibel viele "
                "fuer ein einzelnes Symbol, moeglicher Hinweis auf ein geaendertes "
                "Antwortformat (ADR 0017 L4)."
            )

        if not entries:
            return None

        try:
            earliest = min(entries, key=lambda entry: entry["date"])
            earnings_date = date.fromisoformat(earliest["date"])
        except (KeyError, TypeError, ValueError) as error:
            raise FinnhubEarningsProviderError(
                f"Unerwartetes Antwortformat des Earnings-Kalenders fuer '{symbol}': {error}"
            ) from error

        return NextEarningsDate(date=earnings_date, source=_SOURCE_NAME, retrieved_at=self._now())
