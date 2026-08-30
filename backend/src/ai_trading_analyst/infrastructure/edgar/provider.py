"""Abruf der SEC-Einreichungen (ADR 0022, ADR 0032).

Zwei Anfragen je Aktie: einmal die Zuordnung Symbol zu CIK -- fuer den
ganzen Prozess nur einmal --, dann ``companyfacts`` fuer die Aktie selbst.
Kein Sprachmodell im Beschaffungspfad (ADR 0022).

Die SEC verlangt zwei Dinge ausdruecklich: einen ``User-Agent`` mit
Kontaktadresse und hoechstens zehn Anfragen je Sekunde. Beides steht hier
und nicht in der Aufrufstelle, damit es nicht vergessen werden kann.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from ai_trading_analyst.domain.analysis import FundamentalDataProviderError, Stock
from ai_trading_analyst.domain.fundamentals import (
    FundamentalParameters,
    FundamentalSnapshot,
    compute_fundamental_snapshot,
)
from ai_trading_analyst.observability.logging_setup import get_logger

from .companyfacts import CompanyFactsError, ResolvedFacts, resolve_company_facts

_logger = get_logger(__name__)

MAX_ANTWORT_BYTES = 32 * 1024 * 1024
"""Obergrenze je Antwort. Gemessen am 2026-08-24: Apple 3,8 MB, Honeywell
4,6 MB, Netflix 3,6 MB. Die Grenze liegt weit darueber und soll keinen
regulaeren Abruf treffen -- sie verhindert, dass eine unerwartet grosse oder
endlose Antwort den Arbeitsspeicher fuellt (ADR 0032 L6)."""

TICKER_INDEX_PATH = "/files/company_tickers.json"
COMPANY_FACTS_PATH = "/api/xbrl/companyfacts/CIK{cik:010d}.json"


class _AntwortZuGrossError(Exception):
    """Der Abbruch beim Lesen -- eigene Klasse, damit die Fangzeile darunter
    ihn nicht mit einem gewoehnlichen Uebertragungsfehler verwechselt."""

    def __init__(self, beschreibung: str, gelesen: int) -> None:
        super().__init__(
            f"{beschreibung}: Antwort ueberschreitet {MAX_ANTWORT_BYTES / 1e6:.0f} MB "
            f"(bereits {gelesen / 1e6:.1f} MB gelesen) und ist damit unplausibel."
        )


@dataclass(frozen=True, slots=True)
class EdgarConnectionSettings:
    """Verbindungsdaten fuer EDGAR.

    ``contact`` ist die Kontaktadresse im ``User-Agent``. Sie ist **kein
    Geheimnis** -- die SEC verlangt sie, damit sie bei auffaelligem
    Abrufverhalten jemanden erreichen kann. Sie gehoert deshalb in die
    Konfiguration und nicht zu den ``ATA_``-Umgebungsvariablen.
    """

    base_url: str
    index_base_url: str
    contact: str
    request_timeout_seconds: float
    max_requests_per_second: float

    @property
    def user_agent(self) -> str:
        return f"ai-trading-analyst {self.contact}"


class _Drossel:
    """Haelt den Mindestabstand zwischen zwei Anfragen ein.

    Threadsicher, obwohl der Tageslauf die Fundamentaldaten heute
    **sequentiell** holt (Phase 1 von ``RunAnalysisUseCase``, ausserhalb der
    Agenten-Pools). Die Sperre kostet nichts und haelt die Zusicherung, wenn
    der Beschaffungspfad spaeter nebenlaeufig wird -- eine Drossel, die das
    nicht beruecksichtigt, laesst genau dann zu viele Anfragen durch, wenn es
    darauf ankommt, und SEC EDGAR deckelt bei zehn je Sekunde.
    """

    def __init__(self, max_per_second: float, sleep: Callable[[float], None] = time.sleep) -> None:
        if max_per_second <= 0:
            raise ValueError(f"max_requests_per_second muss positiv sein, war {max_per_second}")
        self._mindestabstand = 1.0 / max_per_second
        self._sleep = sleep
        self._sperre = threading.Lock()
        self._zuletzt = 0.0

    def warte(self) -> None:
        with self._sperre:
            jetzt = time.monotonic()
            rest = self._zuletzt + self._mindestabstand - jetzt
            if rest > 0:
                self._sleep(rest)
                jetzt += rest
            self._zuletzt = jetzt


def _schreibweisen(symbol: str) -> tuple[str, ...]:
    """Das Symbol und seine Varianten fuer Aktiengattungen.

    Klassenaktien schreibt jede Quelle anders: Die Watchlist fuehrt Berkshire
    als ``BRK.B``, IBKR als ``BRK B``, die SEC als ``BRK-B``. Ohne diese
    Uebersetzung meldete der Lauf einen fehlenden Emittenten, wo nur die
    Schreibweise abweicht -- und eine Messung der Tag-Abdeckung zaehlte einen
    Fehlschlag, der mit Tags nichts zu tun hat.

    Bewusst keine Suche und keine Aehnlichkeit: nur die beiden Trennzeichen,
    die tatsaechlich vorkommen. Ein Symbol, das die SEC nicht kennt, soll
    weiterhin fehlschlagen und nicht auf ein aehnliches umgebogen werden.
    """
    gross = symbol.upper()
    varianten = [gross, gross.replace(".", "-"), gross.replace(" ", "-")]
    return tuple(dict.fromkeys(varianten))


class EdgarFundamentalDataProvider:
    """Implementiert ``FundamentalDataProvider`` gegen die EDGAR-REST-API."""

    def __init__(
        self,
        settings: EdgarConnectionSettings,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        parameters: FundamentalParameters | None = None,
    ) -> None:
        self._settings = settings
        self._parameters = parameters or FundamentalParameters()
        self._now = now
        self._transport = transport
        """Nur fuer Tests gesetzt (``httpx.MockTransport``)."""
        self._drossel = _Drossel(settings.max_requests_per_second, sleep)
        self._cik_index: Mapping[str, int] | None = None
        self._index_sperre = threading.Lock()

    def fundamentals(self, stock: Stock, price: float | None = None) -> FundamentalSnapshot:
        """Holt die Einreichungen und rechnet die Kennzahlen daraus.

        ``price`` ist die optionale, nicht blockierende Eingabe aus ADR 0032.
        Der Adapter beschafft **keinen** Kurs; er reicht durch, was er
        bekommt, und rechnet ohne ihn alles Uebrige.

        Das Rechnen selbst liegt in der Domain -- hier steht nur die
        Beschaffung. Dasselbe Verhaeltnis wie beim IBKR-Provider, der Kerzen
        holt und die Indikatorformeln der Domain darauf anwendet.
        """
        facts, abgerufen = self._company_facts(stock)
        return compute_fundamental_snapshot(
            symbol=stock.symbol,
            figures=facts.figures,
            trailing=facts.trailing,
            shares_outstanding=facts.shares_outstanding,
            price=price,
            retrieved_at=abgerufen,
            evaluated_at=self._now(),
            parameters=self._parameters,
            tag_conflicts=facts.conflicts,
        )

    def _company_facts(self, stock: Stock) -> tuple[ResolvedFacts, datetime]:
        """Aufgeloeste Jahreswerte und der Zeitpunkt ihres Abrufs.

        Der Abrufzeitpunkt gehoert zum Ergebnis, weil Doc 10, Paragraph 6.9
        ihn an jeder Kennzahl verlangt -- er hier zu ermitteln und nicht in
        der Aufrufstelle stellt sicher, dass er den tatsaechlichen Abruf
        meint und nicht den Beginn des Laufs.
        """
        cik = self._cik_fuer(stock.symbol)
        rohwert = self._hole(
            self._settings.base_url,
            COMPANY_FACTS_PATH.format(cik=cik),
            beschreibung=f"companyfacts fuer '{stock.symbol}'",
        )
        abgerufen = self._now()
        try:
            return resolve_company_facts(rohwert), abgerufen
        except CompanyFactsError as error:
            raise FundamentalDataProviderError(
                f"Einreichungen fuer '{stock.symbol}' nicht auswertbar: {error}"
            ) from error

    def _cik_fuer(self, symbol: str) -> int:
        index = self._ticker_index()
        for schreibweise in _schreibweisen(symbol):
            cik = index.get(schreibweise)
            if cik is not None:
                return cik
        raise FundamentalDataProviderError(
            f"Kein SEC-Emittent zum Symbol '{symbol}'. Die SEC fuehrt nur "
            "US-berichtspflichtige Unternehmen (ADR 0032 L3)."
        )

    def _ticker_index(self) -> Mapping[str, int]:
        """Die Zuordnung Symbol zu CIK, einmal je Prozess.

        Die Datei aendert sich taeglich, aber innerhalb eines Laufs nicht --
        und sie einmal je Aktie zu holen waere bei rund 95 Titeln der
        Watchlist die mit Abstand teuerste Anfrage des Laufs.
        """
        with self._index_sperre:
            if self._cik_index is None:
                self._cik_index = self._lade_ticker_index()
            return self._cik_index

    def _lade_ticker_index(self) -> dict[str, int]:
        rohwert = self._hole(
            self._settings.index_base_url,
            TICKER_INDEX_PATH,
            beschreibung="Symbolverzeichnis der SEC",
        )
        if not isinstance(rohwert, dict):
            raise FundamentalDataProviderError(
                "Symbolverzeichnis der SEC hat ein unerwartetes Format"
            )
        index: dict[str, int] = {}
        for eintrag in rohwert.values():
            if isinstance(eintrag, dict):
                ticker, cik = eintrag.get("ticker"), eintrag.get("cik_str")
                if isinstance(ticker, str) and isinstance(cik, int):
                    index[ticker.upper()] = cik
        if not index:
            raise FundamentalDataProviderError("Symbolverzeichnis der SEC enthielt keinen Eintrag")
        _logger.info("SEC-Symbolverzeichnis geladen: %d Eintraege", len(index))
        return index

    def _hole(self, base_url: str, pfad: str, *, beschreibung: str) -> Any:
        self._drossel.warte()
        try:
            with httpx.Client(
                transport=self._transport,
                timeout=self._settings.request_timeout_seconds,
                headers={"User-Agent": self._settings.user_agent},
            ) as client:
                # Ohne ``follow_redirects``: Eine Umleitung waere bei einer
                # festen, konfigurierten Adresse kein normaler Zustand,
                # sondern ein Hinweis -- ihr blind zu folgen hiesse, eine
                # fremde Antwort als die der SEC zu verarbeiten.
                # Stueckweise gelesen, nicht als Ganzes: Eine Grenze, die
                # erst am fertig gepufferten Rumpf prueft, kommt zu spaet --
                # der Speicher ist dann schon belegt. Abgebrochen wird beim
                # ersten Stueck, das darueber hinausgeht.
                with client.stream("GET", f"{base_url}{pfad}") as antwort:
                    antwort.raise_for_status()
                    stuecke: list[bytes] = []
                    gelesen = 0
                    for stueck in antwort.iter_bytes():
                        gelesen += len(stueck)
                        if gelesen > MAX_ANTWORT_BYTES:
                            raise _AntwortZuGrossError(beschreibung, gelesen)
                        stuecke.append(stueck)
            return json.loads(b"".join(stuecke))
        except _AntwortZuGrossError as error:
            raise FundamentalDataProviderError(str(error)) from error
        except (httpx.HTTPError, ValueError) as error:
            raise FundamentalDataProviderError(
                f"{beschreibung} konnte nicht abgerufen werden: {error}"
            ) from error
