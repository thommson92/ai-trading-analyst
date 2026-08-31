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

Bars sind das Hauptgeschaeft dieses Moduls, aber nicht sein einziges: Auch
die Handelszeiten (``liquid_hours``, ADR 0019) und die Optionsketten
(``option_chain``/``option_quotes``, ADR 0048) laufen hier durch. Der Grund
ist in allen drei Faellen derselbe -- IBKR laesst je Client-ID genau eine
Verbindung zu, und derselbe Lock serialisiert die Zugriffe. Ausgewertet wird
das Geholte jeweils anderswo (``calendar.py``, ``option_chain.py``).

Sicherheitsgrenze (ADR 0014, Dimension 1): Hier wird ausschliesslich gelesen.
Es gibt in diesem Modul keinen ordererzeugenden Aufruf, und das ist die
verbindliche Beschraenkung -- nicht der TWS-weite Schalter "Read-Only API",
der auch die auf derselben TWS-Instanz laufende Fremdanwendung an echten
Orderuebermittlungen hindern wuerde.
"""

from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
import warnings
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ai_trading_analyst.domain.analysis import (
    ContractSpec,
    MarketDataProviderError,
)
from ai_trading_analyst.domain.options import OptionQuote
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

    **Achtung, gemessener Befund:** Bei Intraday-Bars zaehlt IBKR die
    Tagesangabe in **Handelstagen**, nicht in Kalendertagen. Die
    offizielle Dokumentation sagt dazu nichts; belegt ist es durch die
    Tiefenmessung vom 2026-08-23 (ADR 0028), bei der zwoelf Fenster zu je
    ``365 D`` nicht zwoelf, sondern 17,4 Jahre abdeckten -- je Fenster rund
    9.455 Bars, also 364 Handelstage oder etwa 530 Kalendertage.

    Fuer den taeglichen Backfill ist das folgenlos, dort wird ohnehin
    grosszuegig angefragt. Wer aber einen Zeitraum *ausrechnet* -- der
    Tiefen-Backfill tut das --, muss in Handelstagen rechnen, sonst holt er
    fast das Anderthalbfache des Noetigen.
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


@dataclass(frozen=True, slots=True)
class OptionChainStructure:
    """Der Bauplan einer Optionskette: was gelistet ist, ohne jeden Preis.

    Getrennt von den Notierungen, weil die Trennung eine Entscheidung ist:
    Erst aus Verfallsterminen und Strikes waehlt die Domain aus, **was**
    ueberhaupt notiert werden soll -- und jede Notierung kostet eine
    Marktdatenanfrage (ADR 0048, Festlegung 5).
    """

    expirations: tuple[date, ...]
    strikes: tuple[float, ...]
    trading_class: str
    exchange: str


def _bevorzugte_kette(ketten: Sequence[Any]) -> Any:
    """Die SMART-Kette, sonst die mit den meisten Verfallsterminen."""
    for kette in ketten:
        if str(kette.exchange) == "SMART":
            return kette
    return max(ketten, key=lambda kette: len(kette.expirations))


def _verfallstermine(symbol: str, roh: Iterable[str]) -> tuple[date, ...]:
    """Uebersetzt IBKRs ``YYYYMMDD`` in Datumswerte, aufsteigend.

    Ein Eintrag, der nicht diesem Format folgt, wird verworfen und
    protokolliert -- nicht geraten. IBKR liefert fuer manche Basiswerte auch
    Monatsangaben ohne Tag, und ein daraus ergaenzter Tag waere ein
    erfundener Verfallstermin.
    """
    termine: list[date] = []
    verworfen: list[str] = []
    for eintrag in roh:
        try:
            termine.append(datetime.strptime(eintrag, "%Y%m%d").replace(tzinfo=UTC).date())
        except ValueError:
            verworfen.append(eintrag)
    if verworfen:
        _logger.warning(
            "%s: %d Verfallstermine ohne Tagesangabe verworfen (%s)",
            symbol,
            len(verworfen),
            ", ".join(verworfen[:5]),
        )
    return tuple(sorted(termine))


def _put_schablone(
    symbol: str, currency: str, expiration: date, strike: float | None = None
) -> Any:
    """Ein Put-Kontrakt fuer ``ib_async`` -- mit oder ohne Strike.

    Ohne Strike ist er die Anfrage "alle Puts dieses Termins"
    (``reqContractDetails``), mit Strike der konkrete Kontrakt.

    Ueber ``SMART``, wie bei den Aktien: Die Weiterleitung sucht die Boerse
    mit dem besten Preis. Eine feste Optionsboerse waere eine Annahme
    darueber, wo ein Kontrakt am liquidesten ist.
    """
    from ib_async import Option

    return Option(
        symbol,
        expiration.strftime("%Y%m%d"),
        strike if strike is not None else 0.0,
        "P",
        exchange="SMART",
        currency=currency,
    )


def _zahl(wert: Any) -> float | None:
    """``None`` fuer alles, was keine Zahl ist -- IBKRs ``nan`` eingeschlossen."""
    if wert is None:
        return None
    try:
        zahl = float(wert)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(zahl) else zahl


def _preis(wert: Any) -> float | None:
    """Wie ``_zahl``, aber ``None`` auch fuer IBKRs ``-1`` ("kein Kurs").

    Ein Geld- oder Briefkurs von -1 ist keine Notierung, sondern IBKRs
    Schreibweise fuer "es liegt keine vor". Als Zahl weitergereicht ergaebe
    er eine negative Praemie und einen unsinnigen Mittelwert.
    """
    zahl = _zahl(wert)
    return None if zahl is None or zahl <= 0 else zahl


def _ganzzahl(wert: Any) -> int | None:
    zahl = _zahl(wert)
    return None if zahl is None or zahl < 0 else int(zahl)


def _als_quote(ticker: Any) -> OptionQuote:
    """Uebersetzt einen ``ib_async``-Ticker in die Notierung der Domain.

    ``modelGreeks`` fehlt, solange die Optionsmarktdaten-Berechtigung fehlt
    (Spike: ``Error 10091``) -- und moeglicherweise auch ausserhalb der
    Handelszeiten. Das Delta bleibt dann leer, und die Domain verwirft den
    Kontrakt mit benanntem Grund, statt eines zu schaetzen.
    """
    greeks = getattr(ticker, "modelGreeks", None)
    return OptionQuote(
        expiration=datetime.strptime(ticker.contract.lastTradeDateOrContractMonth, "%Y%m%d")
        .replace(tzinfo=UTC)
        .date(),
        strike=float(ticker.contract.strike),
        bid=_preis(getattr(ticker, "bid", None)),
        ask=_preis(getattr(ticker, "ask", None)),
        delta=None if greeks is None else _zahl(getattr(greeks, "delta", None)),
        implied_volatility=(
            None if greeks is None else _zahl(getattr(greeks, "impliedVol", None))
        ),
        # ``reqTickers`` fordert Open Interest nicht standardmaessig an; das
        # Feld bleibt deshalb oft leer. Es erzeugt dann keine Warnung
        # (CLAUDE.md: fehlende Werte bestrafen nicht) und fehlt sichtbar.
        open_interest=_ganzzahl(getattr(ticker, "putOpenInterest", None)),
        volume=_ganzzahl(getattr(ticker, "volume", None)),
    )


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

    def fetch_window(
        self, contract: ContractSpec, end: datetime | None, days: int
    ) -> Sequence[IntradayBar]:
        """Bars eines Fensters, das nicht jetzt endet (``HistoricalBarWindowSource``).

        Derselbe Abruf wie ``fetch_intraday_bars``, nur mit gesetztem
        ``endDateTime``. Die Tiefenmessung arbeitet sich damit Fenster fuer
        Fenster zurueck; ohne diesen Weg liesse sich nur beantworten, was
        **bis heute** zurueckreicht, nicht, wo die Historie tatsaechlich
        endet.

        Der laufende Bar wird hier nicht ausgesondert: Ein Fenster, das in der
        Vergangenheit endet, enthaelt keinen. Fuer ``end=None`` uebernimmt
        ``_fetch`` diese Aufgabe wie bisher.
        """
        with self._lock:
            return self._fetch(contract, days, end=end)

    def option_chain(self, contract: ContractSpec) -> OptionChainStructure:
        """Verfallstermine und Strikes einer Aktie -- **ohne** Marktdaten.

        Aus derselben Verbindung und unter demselben Lock wie die Bars, aus
        dem Grund, den ``liquid_hours`` schon nennt: IBKR laesst je Client-ID
        genau eine Verbindung zu.

        ``reqSecDefOptParams`` kostet keine Marktdatenberechtigung -- der
        Spike hat die Struktur schon vor der Abo-Aktivierung bekommen
        (REPORT.md, Frage 6). Die 11-Sekunden-Drossel gilt hier **nicht**: Sie
        deckt IBKRs Grenze fuer *historische* Anfragen ab, und die ist ein
        eigener Zaehler.

        IBKR antwortet mit einer Kette **je Boerse**. Genommen wird die von
        ``SMART`` -- ueber diese Weiterleitung wird auch abgefragt --, sonst
        die mit den meisten Verfallsterminen.
        """
        with self._lock:
            try:
                ib = self._connection()
                stock = self._qualified(ib, contract)
                ketten = ib.reqSecDefOptParams(stock.symbol, "", stock.secType, stock.conId)
            except IbkrBarSourceError:
                raise
            except Exception as error:  # Systemgrenze: jede Bibliotheksausnahme
                raise IbkrBarSourceError(
                    f"Optionskette fuer '{contract.symbol}' nicht abrufbar: {error}"
                ) from error
        if not ketten:
            raise IbkrBarSourceError(
                f"IBKR liefert keine Optionskette fuer '{contract.symbol}' -- fuer diesen "
                "Basiswert sind keine Optionen gelistet."
            )
        kette = _bevorzugte_kette(ketten)
        return OptionChainStructure(
            expirations=_verfallstermine(contract.symbol, kette.expirations),
            strikes=tuple(sorted(float(strike) for strike in kette.strikes)),
            trading_class=str(kette.tradingClass),
            exchange=str(kette.exchange),
        )

    def option_strikes(self, contract: ContractSpec, expiration: date) -> tuple[float, ...]:
        """Die Strikes, die zu **diesem** Verfallstermin tatsaechlich gelistet sind.

        Ein eigener Aufruf, und zwar aus einem gemessenen Grund:
        ``reqSecDefOptParams`` liefert die **Vereinigung** aller Strikes ueber
        alle Verfallstermine. Am 2026-08-31 hatte AAPL bei den Wochenoptionen
        2,50er Abstaende, beim Termin am 25. September aber 5,00er -- von
        zwoelf angefragten Kontrakten existierten sechs nicht (``Error 200``).
        Die Auswahl halbierte sich, und jede vergebliche Anfrage kostete
        trotzdem eine Marktdatenzeile.

        ``reqContractDetails`` kostet **keine** Marktdatenberechtigung. Ein
        Aufruf je Kandidat ist der Preis dafuer, dass danach jeder angefragte
        Kontrakt auch existiert.
        """
        with self._lock:
            try:
                ib = self._connection()
                stock = self._qualified(ib, contract)
                details = ib.reqContractDetails(
                    _put_schablone(stock.symbol, contract.currency, expiration)
                )
            except IbkrBarSourceError:
                raise
            except Exception as error:  # Systemgrenze: jede Bibliotheksausnahme
                raise IbkrBarSourceError(
                    f"Gelistete Strikes fuer '{contract.symbol}' zum "
                    f"{expiration.isoformat()} nicht abrufbar: {error}"
                ) from error
        return tuple(sorted({float(eintrag.contract.strike) for eintrag in details}))

    def option_quotes(
        self,
        contract: ContractSpec,
        expiration: date,
        strikes: Sequence[float],
        market_data_type: int,
    ) -> Sequence[OptionQuote]:
        """Notierungen der genannten Put-Strikes zu einem Verfallstermin.

        ``market_data_type`` waehlt IBKRs Marktdatenmodus: ``1`` live,
        ``2`` "frozen" (bei offener Boerse wie live, bei geschlossener der
        letzte festgestellte Stand). Welcher gilt, steht in der Konfiguration
        und nicht hier (ADR 0048) -- der Tageslauf laeuft im offenen Markt,
        eine Einzelprobe am Abend nicht.

        Ein Kontrakt, den IBKR nicht aufloest, faellt weg -- gelistete Strikes
        gibt es nicht zu jedem Verfallstermin. Was fehlt, bleibt fehlend: An
        keiner Stelle tritt hier ein Ersatzwert an die Stelle eines nicht
        gelieferten Feldes.
        """
        if not strikes:
            return ()
        with self._lock:
            try:
                ib = self._connection()
                stock = self._qualified(ib, contract)
                ib.reqMarketDataType(market_data_type)
                kontrakte = self._qualifizierte_puts(ib, stock, contract, expiration, strikes)
                if not kontrakte:
                    return ()
                tickers = ib.reqTickers(*kontrakte)
            except IbkrBarSourceError:
                raise
            except Exception as error:  # Systemgrenze: jede Bibliotheksausnahme
                raise IbkrBarSourceError(
                    f"Optionsnotierungen fuer '{contract.symbol}' nicht abrufbar: {error}"
                ) from error
        return tuple(_als_quote(ticker) for ticker in tickers if ticker.contract is not None)

    def _qualifizierte_puts(
        self,
        ib: Any,
        stock: Any,
        contract: ContractSpec,
        expiration: date,
        strikes: Sequence[float],
    ) -> list[Any]:
        puts = [
            _put_schablone(stock.symbol, contract.currency, expiration, strike)
            for strike in strikes
        ]
        # ``qualifyContracts`` laesst nicht aufloesbare Kontrakte einfach weg
        # und protokolliert sie -- genau das gewuenschte Verhalten: Ein
        # Strike, den es zu diesem Verfallstermin nicht gibt, ist kein Fehler.
        aufgeloest: list[Any] = list(ib.qualifyContracts(*puts))
        if len(aufgeloest) < len(puts):
            _logger.info(
                "%s: %d von %d Put-Kontrakten zum %s nicht gelistet",
                contract.symbol,
                len(puts) - len(aufgeloest),
                len(puts),
                expiration.isoformat(),
            )
        return aufgeloest

    def liquid_hours(self, contract: ContractSpec) -> tuple[str, str]:
        """Handelszeiten der regulaeren Sitzung und die Zeitzone der Boerse.

        Der Boersenkalender (ADR 0019) kommt aus derselben Verbindung wie die
        Bars -- IBKR laesst je Client-ID nur eine zu, und derselbe Lock
        serialisiert beide Zugriffe.

        Nicht ``tradingHours``: Gerechnet wird auf der regulaeren Sitzung, und
        ``tradingHours`` enthaelt auch vor- und nachboerslichen Handel.
        """
        with self._lock:
            try:
                ib = self._connection()
                details = ib.reqContractDetails(self._qualified(ib, contract))
            except IbkrBarSourceError:
                raise
            except Exception as error:  # Systemgrenze: jede Bibliotheksausnahme
                raise IbkrBarSourceError(
                    f"Handelszeiten fuer '{contract.symbol}' nicht abrufbar: {error}"
                ) from error
            if not details:
                raise IbkrBarSourceError(
                    f"IBKR liefert keine Kontraktdetails fuer '{contract.symbol}'"
                )
            return str(details[0].liquidHours), str(details[0].timeZoneId)

    def _qualified(self, ib: Any, contract: ContractSpec) -> Any:
        from ib_async import Stock

        stock = Stock(
            contract.symbol,
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
                f"IBKR kennt keinen Kontrakt fuer '{contract.symbol}' an "
                f"'{contract.exchange}' ({contract.currency}, Heimatboerse "
                f"{contract.primary_exchange or 'nicht angegeben'})"
            )
        return contracts[0]

    def _fetch(
        self, contract: ContractSpec, days: int | None, end: datetime | None = None
    ) -> Sequence[IntradayBar]:
        symbol = contract.symbol
        try:
            ib = self._connection()
            contracts = [self._qualified(ib, contract)]
            self._wait_for_pacing()
            bars = ib.reqHistoricalData(
                contracts[0],
                # ib_async formatiert ein zeitzonenbehaftetes datetime selbst in
                # die UTC-Schreibweise der API; "" heisst "bis jetzt".
                endDateTime="" if end is None else end,
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

        umgewandelt = (
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
        # Nur ein bis jetzt reichendes Fenster kann einen laufenden Bar
        # enthalten. Bei gesetztem 'end' waere dieselbe Pruefung schaedlich:
        # Sie mass gegen die aktuelle Uhrzeit und verwuerfe nichts, aber sie
        # behauptete eine Aussage ueber ein Fenster, das laengst geschlossen
        # ist.
        gefiltert = self._without_running_bar(umgewandelt) if end is None else tuple(umgewandelt)
        return self._on_grid(symbol, gefiltert)

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
        # Beides in **einem** Durchgang. Die Verworfenen nachtraeglich ueber
        # 'bar not in passend' zu suchen, war ein quadratischer Vergleich
        # ueber Wertobjekte: Bei einem Jahresfenster mit rund 9.500 Bars
        # kostete ein einziger schiefer Bar knapp 15 Sekunden reine
        # Rechenzeit. Der Tiefen-Backfill stellt diese Anfrage je Aktie
        # fuenfmal.
        passend: list[IntradayBar] = []
        verworfen: list[datetime] = []
        for bar in bars:
            auf_raster = (
                bar.start.second == 0
                and bar.start.microsecond == 0
                and bar.start.minute % self._bar_minutes == 0
            )
            if auf_raster:
                passend.append(bar)
            else:
                verworfen.append(bar.start)
        if verworfen:
            _logger.warning(
                "%s: %d Bars ausserhalb des %d-Minuten-Rasters verworfen (%s)",
                symbol,
                len(verworfen),
                self._bar_minutes,
                ", ".join(zeitpunkt.isoformat() for zeitpunkt in verworfen[:5]),
            )
        return tuple(passend)

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
