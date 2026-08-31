"""Zugriff auf die Finnhub-Analystenempfehlungen (``/stock/recommendation``).

Entschieden in
[ADR 0043](../../../../../docs/adr/0043-analystenempfehlungen-statt-kurszielen.md),
mitentschieden bereits in
[ADR 0017](../../../../../docs/adr/0017-finnhub-fuer-earnings-und-ratings.md).

Ein eigenes Modul neben ``provider.py``: Dessen Docstring beschreibt
ausdruecklich nur den Earnings-Kalender, und die beiden Endpunkte teilen
zwar Konto, Schluessel und Host, aber weder Antwortformat noch
Plausibilitaetsschranke.

**Kursziele holt dieses Modul nicht.** Der Endpunkt ist kostenpflichtig, und
keine Score-Komponente braucht sie (ADR 0043).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import httpx

from ai_trading_analyst.domain.analysis import (
    AnalystRecommendationsFormatError,
    AnalystRecommendationsProviderError,
    Stock,
)
from ai_trading_analyst.domain.analysts import (
    AnalystRecommendations,
    AnalystRecommendationStatus,
    RecommendationPeriod,
)
from ai_trading_analyst.infrastructure.throttle import Drossel
from ai_trading_analyst.observability.logging_setup import get_logger
from ai_trading_analyst.observability.secret_redaction import redact

_logger = get_logger(__name__)

_SOURCE_NAME = "finnhub"
_SOURCE_URL = "https://finnhub.io/api/v1/stock/recommendation"

_SUSPICIOUS_PERIOD_COUNT = 120
"""Finnhub liefert Monatsstaende. Mehr als zehn Jahre davon fuer ein einzelnes
Symbol deutet auf ein geaendertes Antwortformat hin -- besser abbrechen als
einer unplausiblen Antwort vertrauen (Muster ``_SUSPICIOUS_ENTRY_COUNT`` im
Earnings-Adapter)."""

_VOTE_FIELDS = ("strongBuy", "buy", "hold", "sell", "strongSell")


class FinnhubAnalystRecommendationsProviderError(AnalystRecommendationsProviderError):
    """Finnhub war nicht erreichbar."""


class FinnhubAnalystRecommendationsFormatError(
    FinnhubAnalystRecommendationsProviderError, AnalystRecommendationsFormatError
):
    """Finnhub war erreichbar, seine Antwort aber nicht auswertbar.

    Eine eigene Klasse, weil der Unterschied im Bericht steht: ``UNAVAILABLE``
    mit Grund ``provider_error`` heisst "nicht erreicht", mit Grund
    ``invalid_data`` heisst "erreicht, aber unlesbar". Der Earnings-Filter
    macht dieselbe Unterscheidung (ADR 0017); ohne eigene Klasse ginge sie
    hier verloren, und der dokumentierte Grund entstuende nie.
    """


@dataclass(frozen=True, slots=True)
class FinnhubRecommendationSettings:
    base_url: str
    api_key: str
    request_timeout_seconds: float
    months: int
    """Wie viele Monatsstaende hoechstens uebernommen werden. Der Endpunkt
    kennt keinen Zeitraumparameter -- er liefert, was er hat, und die
    Begrenzung geschieht hier."""
    max_requests_per_second: float


class FinnhubAnalystRecommendationsProvider:
    """Implementiert ``AnalystRecommendationsProvider`` gegen die Finnhub-REST-API."""

    def __init__(
        self,
        settings: FinnhubRecommendationSettings,
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

    def recommendations(self, stock: Stock) -> AnalystRecommendations:
        symbol = stock.symbol
        evaluated_at = self._now()
        self._drossel.warte()

        try:
            with httpx.Client(
                transport=self._transport, timeout=self._settings.request_timeout_seconds
            ) as client:
                response = client.get(
                    f"{self._settings.base_url}/stock/recommendation",
                    params={"symbol": symbol, "token": self._settings.api_key},
                )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            # Der Fehlertext von ``httpx`` enthaelt die vollstaendige URL --
            # samt Zugangsschluessel. Ohne Schwaerzung stuende er auf stderr.
            raise FinnhubAnalystRecommendationsProviderError(
                f"Analystenempfehlungen fuer '{symbol}' konnten nicht abgerufen werden: "
                f"{redact(str(error), self._settings.api_key)}"
            ) from error

        periods = self._parse(symbol, payload)
        if not periods:
            # Erreichbar, aber ohne Abdeckung. Das ist keine leere Verteilung
            # und erst recht kein "keine Meinung" (ADR 0043).
            _logger.info("Keine Analystenempfehlungen fuer %s -- no_coverage.", symbol)
            return AnalystRecommendations(
                status=AnalystRecommendationStatus.UNKNOWN,
                evaluated_at=evaluated_at,
                source=_SOURCE_NAME,
                source_url=_SOURCE_URL,
                retrieved_at=evaluated_at,
                reason="no_coverage",
            )

        return AnalystRecommendations(
            status=AnalystRecommendationStatus.COMPLETED,
            evaluated_at=evaluated_at,
            periods=periods,
            source=_SOURCE_NAME,
            source_url=_SOURCE_URL,
            retrieved_at=evaluated_at,
        )

    def _parse(self, symbol: str, payload: Any) -> tuple[RecommendationPeriod, ...]:
        if not isinstance(payload, list):
            raise FinnhubAnalystRecommendationsFormatError(
                f"Unerwartetes Antwortformat der Analystenempfehlungen fuer '{symbol}': "
                f"erwartet wurde eine Liste, geliefert {type(payload).__name__}."
            )

        if len(payload) > _SUSPICIOUS_PERIOD_COUNT:
            raise FinnhubAnalystRecommendationsFormatError(
                f"Analystenempfehlungen fuer '{symbol}' lieferten {len(payload)} Monatsstaende "
                "-- unplausibel viele fuer ein einzelnes Symbol, moeglicher Hinweis auf ein "
                "geaendertes Antwortformat."
            )

        parsed = [self._parse_entry(symbol, entry) for entry in payload]
        # Neuester zuerst -- die Reihenfolge ist Teil der Zusage von
        # ``AnalystRecommendations.periods``, nicht bloss Darstellung. Der
        # Anbieter sortiert bereits so; verlassen wird sich darauf nicht.
        parsed.sort(key=lambda period: period.period, reverse=True)
        return tuple(parsed[: self._settings.months])

    def _parse_entry(self, symbol: str, entry: Any) -> RecommendationPeriod:
        if not isinstance(entry, dict):
            raise FinnhubAnalystRecommendationsFormatError(
                f"Unerwartetes Antwortformat der Analystenempfehlungen fuer '{symbol}': "
                f"Eintrag ist kein Objekt, sondern {type(entry).__name__}."
            )
        try:
            period = date.fromisoformat(entry["period"])
            votes = [_as_count(entry[field]) for field in _VOTE_FIELDS]
        except (KeyError, TypeError, ValueError) as error:
            raise FinnhubAnalystRecommendationsFormatError(
                f"Unerwartetes Antwortformat der Analystenempfehlungen fuer '{symbol}': {error}"
            ) from error

        strong_buy, buy, hold, sell, strong_sell = votes
        return RecommendationPeriod(
            period=period,
            strong_buy=strong_buy,
            buy=buy,
            hold=hold,
            sell=sell,
            strong_sell=strong_sell,
        )


def _as_count(value: Any) -> int:
    """Eine Votenzahl aus der Antwort.

    Kein ``int(value)``: Das schluckte ``True`` als 1 und ``3.7`` als 3. Eine
    Stimmenzahl ist ganzzahlig und nicht negativ, sonst ist die Antwort nicht
    plausibel auswertbar.
    """
    if isinstance(value, bool):
        # Vor der int-Pruefung, weil ``bool`` in Python ein ``int`` ist:
        # ``True`` kaeme sonst als eine Stimme durch.
        raise TypeError("Votenzahl ist ein Wahrheitswert, keine ganze Zahl")
    if not isinstance(value, int):
        raise TypeError(f"Votenzahl ist keine ganze Zahl, sondern {type(value).__name__}")
    if value < 0:
        raise ValueError(f"Votenzahl ist negativ: {value}")
    return value
