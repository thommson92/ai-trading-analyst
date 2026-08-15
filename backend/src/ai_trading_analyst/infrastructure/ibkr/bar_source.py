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
import logging
import threading
import time
import warnings
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from ai_trading_analyst.domain.analysis import (
    ContractSpec,
    MarketDataProviderError,
)
from ai_trading_analyst.domain.screening import IntradayBar
from ai_trading_analyst.observability.logging_setup import get_logger

_logger = get_logger(__name__)

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


def _silence_account_logging() -> None:
    """Haelt die Protokollierung von ``ib_async`` auf Warnungen und Fehler.

    Beim Verbindungsaufbau synchronisiert ``ib_async.IB`` Konto- und
    Positionsdaten und protokolliert sie auf INFO-Ebene im Klartext -- im
    Spike ein echter Sicherheitsfund (REPORT.md, Frage 1, "Sicherheitsfund").
    Dieses Projekt braucht keine einzige dieser Angaben: Es liest Kurse.
    Warnungen und Fehler bleiben sichtbar, damit ein Problem an der
    Schnittstelle nicht stillschweigend verschwindet.
    """
    logging.getLogger("ib_async").setLevel(logging.WARNING)


class IbkrBarSourceError(MarketDataProviderError):
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


def ibkr_duration(days: int) -> str:
    """Uebersetzt eine Tagesangabe in die Zeitraumangabe der IBKR-API.

    Tagesangaben nimmt die API bis 365 an; darueber ist in Jahren zu rechnen.
    Aufgerundet wird bewusst -- lieber ein paar Bars zu viel als eine Luecke,
    zumal doppelte Bars beim Speichern ohnehin uebergangen werden.
    """
    if days < 1:
        raise ValueError(f"days muss mindestens 1 sein, ist aber {days}")
    if days <= 365:
        return f"{days} D"
    return f"{-(-days // 365)} Y"


_ZEITRAUMEINHEITEN = {"D": 1, "W": 7, "M": 30, "Y": 365}


def duration_in_days(duration: str) -> int:
    """Uebersetzt eine Zeitraumangabe der IBKR-API in Tage.

    Die Umkehrung von ``ibkr_duration``, gebraucht fuer den Vergleich zwischen
    angefragtem und geliefertem Zeitraum: Der Standardzeitraum steht in der
    Konfiguration in IBKR-Schreibweise, die Kuerzungspruefung rechnet in Tagen.
    Naeherungsweise -- ein Monat gilt als 30 Tage -- was fuer einen Vergleich
    von Groessenordnungen genuegt.
    """
    teile = duration.split()
    if len(teile) != 2 or teile[1] not in _ZEITRAUMEINHEITEN:
        raise ValueError(
            f"'{duration}' ist keine IBKR-Zeitraumangabe. Erwartet wird eine Zahl und "
            f"eine Einheit, etwa '1 Y' oder '30 D' ({', '.join(_ZEITRAUMEINHEITEN)})."
        )
    try:
        anzahl = int(teile[0])
    except ValueError as error:
        raise ValueError(f"'{duration}' beginnt nicht mit einer ganzen Zahl.") from error
    if anzahl < 1:
        raise ValueError(f"'{duration}' ergibt keinen Zeitraum.")
    return anzahl * _ZEITRAUMEINHEITEN[teile[1]]


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
        minimum_request_interval_seconds: float = 0.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._settings = settings
        self._bar_size = ibkr_bar_size(native_bar_minutes)
        self._bar_minutes = native_bar_minutes
        self._now = now
        self._duration = duration
        self._minimum_request_interval = minimum_request_interval_seconds
        self._sleep = sleep
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._ib: Any | None = None
        self._owner_thread: int | None = None
        self._last_request_at: float | None = None

    def fetch_intraday_bars(
        self, contract: ContractSpec, days: int | None = None
    ) -> Sequence[IntradayBar]:
        with self._lock:
            return self._fetch(contract, days)

    def _fetch(self, contract: ContractSpec, days: int | None) -> Sequence[IntradayBar]:
        symbol = contract.symbol
        try:
            ib = self._connection()
            from ib_async import Stock

            stock = Stock(
                symbol,
                contract.exchange,
                contract.currency,
                primaryExchange=contract.primary_exchange or "",
            )
            contracts = ib.qualifyContracts(stock)
            if not contracts:
                # Die Heimatboerse gehoert in die Meldung: Sie stammt aus der
                # Watchlist, und eine Abweichung zwischen deren Bezeichnung
                # und der von IBKR ist die wahrscheinlichste Ursache.
                raise IbkrBarSourceError(
                    f"IBKR kennt keinen Kontrakt fuer '{symbol}' an "
                    f"'{contract.exchange}' ({contract.currency}, Heimatboerse "
                    f"{contract.primary_exchange or 'nicht angegeben'})"
                )
            self._wait_for_pacing()
            bars = ib.reqHistoricalData(
                contracts[0],
                endDateTime="",
                durationStr=self._duration if days is None else ibkr_duration(days),
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

        return self._on_grid(
            symbol,
            self._without_running_bar(
                IntradayBar(
                    start=bar.date,
                    open=float(bar.open),
                    high=float(bar.high),
                    low=float(bar.low),
                    close=float(bar.close),
                    volume=float(bar.volume),
                )
                for bar in bars
            ),
        )

    def _without_running_bar(self, bars: Iterable[IntradayBar]) -> Sequence[IntradayBar]:
        """Laesst den noch laufenden Bar weg.

        Auf ``endDateTime=""`` antwortet IBKR bis zum aktuellen Augenblick --
        der letzte Bar einer waehrend der Sitzung gestellten Anfrage ist
        deshalb noch nicht fertig. Sein Schluss, Hoch, Tief und Volumen sind
        Zwischenstaende.

        Fuer das Screening war das folgenlos: Die Kerze, zu der er gehoert,
        ist selbst unfertig und faellt ohnehin heraus. Der Bestand aber ist
        dauerhaft. Ein einmal abgelegter Bar wird nie ueberschrieben -- die
        Ablage laesst Dubletten bewusst fallen, damit ein wiederholter Lauf
        nichts anrichtet. Der Zwischenstand bliebe also fuer immer stehen,
        auch wenn ein spaeterer Lauf denselben Bar fertig liefert, und
        verfaelschte still die Kerze, die spaeter aus ihm entsteht.

        Dieselbe Regel wie fuer Kerzen, eine Ebene tiefer: Was noch laeuft,
        zaehlt nicht.
        """
        grenze = self._now() - timedelta(minutes=self._bar_minutes)
        return tuple(bar for bar in bars if bar.start <= grenze)

    def _on_grid(self, symbol: str, bars: Sequence[IntradayBar]) -> Sequence[IntradayBar]:
        """Laesst Bars weg, die nicht auf dem Raster ihrer eigenen Groesse liegen.

        Am **Anfang** des angefragten Fensters schneidet IBKR ab: Statt beim
        naechsten Rasterpunkt zu beginnen, kommt gelegentlich ein Bar mit dem
        exakten Zeitstempel der Anfrage zurueck -- ``12:07:06`` statt
        ``12:15:00``. Beobachtet beim ersten Jahresabruf ueber 192 Symbole,
        bei vier davon.

        Ein solcher Bar ist nicht verwertbar: Er laesst sich keiner
        195-Minuten-Kerze zuordnen, und die Kerzenbildung weist deshalb die
        **gesamte** Reihe zurueck. Beim Abruf je Lauf war das folgenlos, weil
        die naechste Antwort anders ausfiel. Im Bestand bliebe der Bar liegen
        und machte die Aktie dauerhaft unbrauchbar.

        Verworfen wird deshalb hier, an der Systemgrenze, und nicht still: Was
        wegfaellt, steht im Protokoll. Die strenge Pruefung der Kerzenbildung
        bleibt bestehen -- sie ist die Wache fuer alles, was trotzdem
        durchkommt, etwa aus einem Bestand aelterer Laeufe.

        Das Raster ergibt sich aus der Bar-Groesse: Die regulaere Sitzung
        beginnt um 09:30, und alle unterstuetzten Groessen teilen sowohl die
        Stunde als auch die halbe Stunde ohne Rest.
        """
        passend = tuple(
            bar
            for bar in bars
            if bar.start.second == 0
            and bar.start.microsecond == 0
            and bar.start.minute % self._bar_minutes == 0
        )
        if len(passend) < len(bars):
            verworfen = [bar.start for bar in bars if bar not in passend]
            _logger.warning(
                "%s: %d Bars ausserhalb des %d-Minuten-Rasters verworfen (%s)",
                symbol,
                len(bars) - len(passend),
                self._bar_minutes,
                ", ".join(zeitpunkt.isoformat() for zeitpunkt in verworfen[:5]),
            )
        return passend

    def close(self) -> None:
        """Trennt die Verbindung. Mehrfach aufrufbar, scheitert nie."""
        with self._lock:
            self._drop_connection()

    def _wait_for_pacing(self) -> None:
        """Haelt den Mindestabstand zwischen zwei Historienanfragen ein.

        IBKR begrenzt historische Anfragen auf 60 innerhalb von zehn Minuten.
        Wer das ueberschreitet, bekommt keine Fehlermeldung pro Anfrage,
        sondern eine Pacing-Sperre fuer die ganze Verbindung -- bei einer
        Watchlist mit dreistelliger Symbolzahl faellt der Lauf sonst
        mittendrin aus. Der Abstand wird deshalb hier eingehalten und nicht
        der Gegenstelle ueberlassen.
        """
        if self._minimum_request_interval <= 0:
            return
        now = self._monotonic()
        if self._last_request_at is not None:
            wait = self._minimum_request_interval - (now - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
        self._last_request_at = self._monotonic()

    def _connection(self) -> Any:
        if self._ib is not None:
            if self._owner_thread == threading.get_ident() and self._ib.isConnected():
                return self._ib
            self._drop_connection()

        # ib_async wird bewusst erst hier importiert: Der Import legt einen
        # Event-Loop an und ist damit ein Seiteneffekt, den weder ein Testlauf
        # noch ein Anwendungsstart ohne IBKR-Betrieb ausloesen soll.
        _ensure_event_loop_exists()
        _silence_account_logging()
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
