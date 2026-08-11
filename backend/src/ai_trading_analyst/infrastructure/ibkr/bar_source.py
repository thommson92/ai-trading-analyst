"""Zugriff auf historische Intraday-Bars der Interactive-Brokers-TWS-API.

Freigegeben durch [ADR 0014](../../../../../docs/adr/0014-ibkr-produktivintegration-freigegeben.md).
Der technische Nachweis stammt aus dem abgeschlossenen Spike
(``spikes/ibkr-marketdata/REPORT.md``) -- dieser Adapter ist eine
Neuimplementierung auf Basis der dortigen Erkenntnisse, kein uebernommener
Spike-Code.

Zwei Dinge trennt dieses Modul bewusst:

* ``HistoricalBarSource`` ist die schmale Schnittstelle, die der Provider
  braucht. Sie laesst sich ohne laufende TWS mit einem Doppel besetzen -- die
  Unit-Tests und die CI brauchen deshalb weder Netzwerk noch IBKR-Konto.
* ``IbAsyncBarSource`` ist die einzige Stelle im Produktivcode, die
  ``ib_async`` kennt.

Sicherheitsgrenze (ADR 0014, Dimension 1): Hier wird ausschliesslich gelesen.
Es gibt in diesem Modul keinen ordererzeugenden Aufruf, und das ist die
verbindliche Beschraenkung -- nicht der TWS-weite Schalter "Read-Only API",
der auch die auf derselben TWS-Instanz laufende Fremdanwendung an echten
Orderuebermittlungen hindern wuerde.
"""

from __future__ import annotations

import asyncio
import threading
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from ai_trading_analyst.domain.screening import IntradayBar

SUPPORTED_BAR_MINUTES = (1, 3, 5, 15)
"""Bar-Groessen, die IBKR anbietet **und** die 195 Minuten ohne Rest teilen."""


def _ensure_event_loop_exists() -> None:
    """Stellt sicher, dass der aktuelle Thread einen Event-Loop hat.

    ``ib_async`` ist im Kern asynchron und erwartet auch fuer seine
    synchronen Aufrufe einen Event-Loop im aufrufenden Thread. FastAPI fuehrt
    synchrone Endpunkte in Worker-Threads aus, die keinen haben -- ohne diese
    Vorbereitung scheitert bereits ``IB()`` mit "There is no current event
    loop in thread". Denselben Effekt hat ab Python 3.14 auch der Import
    selbst (Spike-Fund, REPORT.md, Frage 1).
    """
    with warnings.catch_warnings():
        # Ohne gesetzten Loop warnt Python 3.12 an dieser Stelle, ab 3.14
        # scheitert der Aufruf. Beides ist hier kein Problem, sondern genau
        # die Information, die gebraucht wird: Es gibt noch keinen Loop.
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            asyncio.get_event_loop()
            return
        except RuntimeError:
            pass
    asyncio.set_event_loop(asyncio.new_event_loop())


class IbkrBarSourceError(RuntimeError):
    """Die TWS war nicht erreichbar oder hat keine verwertbaren Bars geliefert.

    Der haeufigste Fall ist der erwartete Betriebszustand aus ADR 0014,
    Einschraenkung E2: Nach einem Neustart laeuft die TWS erst nach manueller
    Anmeldung wieder.
    """


@dataclass(frozen=True, slots=True)
class IbkrConnectionSettings:
    """Verbindungsparameter -- Konfiguration, keine Geheimnisse.

    ``client_id`` muss sich von der Client-ID jeder anderen Anwendung an
    derselben TWS-Instanz unterscheiden (ADR 0013, Nachtrag zur Koexistenz mit
    der Trade Automation Toolbox).
    """

    host: str
    port: int
    client_id: int
    connect_timeout_seconds: float


def ibkr_bar_size(native_bar_minutes: int) -> str:
    """Uebersetzt eine Bar-Groesse in die Schreibweise der TWS-API.

    IBKR akzeptiert nur eine feste Liste von Bar-Groessen ("5 mins", "15 mins",
    ...), und die Einzahl gilt ausschliesslich fuer die Minute. Eine nicht
    unterstuetzte Groesse faellt hier auf -- nicht erst als Fehlermeldung der
    Gegenstelle mitten im Lauf.
    """
    if native_bar_minutes not in SUPPORTED_BAR_MINUTES:
        raise ValueError(
            f"IBKR liefert keine {native_bar_minutes}-Minuten-Bars. Unterstuetzt und mit "
            f"195 Minuten vereinbar: {', '.join(str(value) for value in SUPPORTED_BAR_MINUTES)}."
        )
    return "1 min" if native_bar_minutes == 1 else f"{native_bar_minutes} mins"


class HistoricalBarSource(Protocol):
    """Liefert native Intraday-Bars einer Aktie, aeltester Bar zuerst."""

    def fetch_intraday_bars(
        self, symbol: str, exchange: str, currency: str
    ) -> Sequence[IntradayBar]:
        """Raises:
        IbkrBarSourceError: wenn die Bars nicht beschafft werden konnten.
        """
        ...

    def close(self) -> None:
        """Gibt eine gehaltene Verbindung frei. Muss mehrfach aufrufbar sein."""
        ...


class IbAsyncBarSource:
    """``HistoricalBarSource`` gegen eine laufende TWS-Instanz.

    Die Verbindung wird beim ersten Abruf aufgebaut und fuer alle weiteren
    Symbole offengehalten: Der Spike hat gezeigt, dass ein Watchlist-Durchlauf
    ueber eine einzige Verbindung deutlich schneller ist und die Pacing-Limits
    der API schont (REPORT.md, Frage 7).

    Zwei Eigenheiten von ``ib_async`` bestimmen den Zuschnitt dieser Klasse:

    * Eine ``IB``-Instanz haengt am Event-Loop des Threads, in dem sie
      entstanden ist, und ist von einem anderen Thread aus nicht benutzbar.
      FastAPI fuehrt synchrone Endpunkte in wechselnden Worker-Threads aus --
      die Verbindung wird deshalb an ihren Thread gebunden und bei einem
      Wechsel sauber neu aufgebaut, statt eine tote Verbindung
      weiterzuverwenden.
    * IBKR laesst je Client-ID genau eine Verbindung zu. Zwei gleichzeitige
      Laeufe wuerden sich gegenseitig verdraengen; ein Lock serialisiert sie
      deshalb, statt das der Gegenstelle zu ueberlassen.
    """

    def __init__(
        self,
        settings: IbkrConnectionSettings,
        native_bar_minutes: int,
        duration: str,
    ) -> None:
        self._settings = settings
        self._bar_size = ibkr_bar_size(native_bar_minutes)
        self._duration = duration
        self._lock = threading.Lock()
        self._ib: Any | None = None
        self._owner_thread: int | None = None

    def fetch_intraday_bars(
        self, symbol: str, exchange: str, currency: str
    ) -> Sequence[IntradayBar]:
        with self._lock:
            return self._fetch(symbol, exchange, currency)

    def _fetch(self, symbol: str, exchange: str, currency: str) -> Sequence[IntradayBar]:
        try:
            ib = self._connection()
            from ib_async import Stock

            contracts = ib.qualifyContracts(Stock(symbol, exchange, currency))
            if not contracts:
                raise IbkrBarSourceError(
                    f"IBKR kennt keinen Kontrakt fuer '{symbol}' an '{exchange}' ({currency})"
                )
            bars = ib.reqHistoricalData(
                contracts[0],
                endDateTime="",
                durationStr=self._duration,
                barSizeSetting=self._bar_size,
                whatToShow="TRADES",
                # Nur regulaere Handelszeiten -- Extended Hours fliessen nie in
                # eine 195-Minuten-Kerze ein (G1-Pruefvorlage, Abschnitt 1.1).
                useRTH=True,
                # formatDate=2 liefert zeitzonenbehaftete Zeitstempel; alles
                # andere waere ein naiver Zeitstempel und damit unzulaessig.
                formatDate=2,
            )
        except IbkrBarSourceError:
            raise
        except Exception as error:  # Systemgrenze: jede Bibliotheksausnahme
            raise IbkrBarSourceError(
                f"Historische Bars fuer '{symbol}' konnten nicht abgerufen werden: {error}"
            ) from error

        return tuple(
            IntradayBar(
                start=bar.date,
                open=float(bar.open),
                high=float(bar.high),
                low=float(bar.low),
                close=float(bar.close),
                volume=float(bar.volume),
            )
            for bar in bars
        )

    def close(self) -> None:
        """Trennt die Verbindung. Mehrfach aufrufbar, scheitert nie."""
        with self._lock:
            self._drop_connection()

    def _connection(self) -> Any:
        if self._ib is not None:
            if self._owner_thread == threading.get_ident() and self._ib.isConnected():
                return self._ib
            self._drop_connection()

        # ib_async wird bewusst erst hier importiert: Der Import legt einen
        # Event-Loop an und ist damit ein Seiteneffekt, den weder ein Testlauf
        # noch ein Anwendungsstart ohne IBKR-Betrieb ausloesen soll.
        _ensure_event_loop_exists()
        from ib_async import IB

        # ib_async.IB.__init__ ist selbst unannotiert -- die Ausnahme bleibt
        # auf diese eine Zeile begrenzt.
        ib: Any = IB()  # type: ignore[no-untyped-call]
        try:
            ib.connect(
                self._settings.host,
                self._settings.port,
                clientId=self._settings.client_id,
                timeout=self._settings.connect_timeout_seconds,
            )
        except Exception as error:  # Systemgrenze: TWS nicht erreichbar
            raise IbkrBarSourceError(
                f"Keine Verbindung zur TWS auf {self._settings.host}:{self._settings.port} "
                f"mit Client-ID {self._settings.client_id}: {error}. Nach einem Neustart "
                "muss die TWS manuell gestartet und angemeldet werden (ADR 0014, E2)."
            ) from error
        self._ib = ib
        self._owner_thread = threading.get_ident()
        return ib

    def _drop_connection(self) -> None:
        ib, self._ib, self._owner_thread = self._ib, None, None
        if ib is None:
            return
        try:
            ib.disconnect()
        except Exception:
            # Eine Verbindung, die sich nicht sauber trennen laesst, ist
            # bereits verloren. Der Abruf darf daran nicht scheitern.
            pass
