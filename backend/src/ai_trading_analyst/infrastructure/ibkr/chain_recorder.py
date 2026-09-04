"""Mitschnitt einer echten IBKR-Optionskette (A2-M7).

Warum es diesen Mitschnitt ueberhaupt braucht: Von den drei Anbietern, deren
Antwortformat die Auswertung traegt, ist genau einer **nicht** ueber HTTP
erreichbar. Finnhub laesst sich mit einem einzigen ``curl`` einfrieren; die
TWS-Schnittstelle spricht ein eigenes Protokoll ueber einen lokalen Socket,
und ohne laufende TWS gibt es keine Antwort zum Aufheben.

Aufgezeichnet wird, was die TWS auf die drei Abrufe geantwortet hat, und
**nur** das: keine bewertete Analyse, keine abgeleitete Groesse. Was daraus
folgt, rechnet der Test aus denselben Rohdaten noch einmal aus. Ein
Mitschnitt der fertigen Analyse wuerde die Rechnung mit einfrieren und
koennte eine Formataenderung des Anbieters nicht mehr von einer
Verfahrensaenderung unterscheiden.

**Zwei Ebenen, und die zweite kam durch eine Review dazu.** Zuerst hing der
Mitschnitt nur an ``OptionChainSource`` -- dort, wo auch der Adapter haengt.
Das friert aber bereits uebersetzte ``OptionQuote``-Werte ein: Benennt IBKR
ein Ticker-Feld um, bildet ``_als_quote`` es still auf ``None`` ab, und kein
Test bemerkt es (Review vom 2026-09-01). ``RohNotierungenSammler`` setzt
deshalb eine Ebene tiefer an und haelt die unuebersetzten Ticker fest.

- ``RecordingOptionChainSource`` -- Kettenstruktur: Termine, Strikes,
  uebersetzte Notierungen. Deckt Terminwahl, Strike-Band, Delta-Filter und
  Renditeformel ab.
- ``RohNotierungenSammler`` -- die Felder, wie die TWS sie stellte. Deckt
  ``_als_quote`` ab, also die Uebersetzung selbst.

Die Aufzeichnung ist **passiv**: Sie reicht jeden Aufruf unveraendert
weiter und aendert an keinem Ergebnis etwas. Ein Lauf mit ``--record`` und
einer ohne liefern dieselbe Analyse.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from ai_trading_analyst.domain.analysis import ContractSpec
from ai_trading_analyst.domain.options import OptionQuote

from .bar_source import OptionChainStructure
from .option_chain import OptionChainSource

DATEIFORMAT = 2
"""Version des Dateiformats. Sie steht in jeder Aufzeichnung, damit ein
spaeterer Leser eine alte Datei erkennt, statt sie stillschweigend halb zu
verstehen.

``2`` fuegt den Abschnitt ``rohe_notierungen`` hinzu (siehe
``RohNotierungenSammler``). Eine Datei mit ``1`` ist weiterhin lesbar, deckt
aber die Uebersetzung ``_als_quote`` nicht ab."""

NICHT_ENDLICH = "nan"
"""Wie ein nicht endlicher Gleitkommawert in der Datei steht.

IBKR schreibt fehlende Zahlen als ``NaN``, und JSON kennt dafuer keinen
Wert. Die Alternative -- ``null`` -- waere die Uebersetzung, die dieser
Mitschnitt gerade nicht vorwegnehmen soll: Ob aus ``NaN`` ein ``None`` wird,
entscheidet ``_als_quote``, und genau das gehoert prueffaehig zu bleiben."""


class RohNotierungenSammler:
    """Sammelt die **unuebersetzten** Ticker der TWS.

    Er haengt an ``IbAsyncBarSource(on_option_tickers=...)`` und damit eine
    Ebene unter ``RecordingOptionChainSource``. Der Grund ist ein Befund der
    Review vom 2026-09-01: Der Mitschnitt am Protokoll ``OptionChainSource``
    friert bereits uebersetzte ``OptionQuote``-Werte ein. Eine Umbenennung auf
    Anbieterseite -- ``putOpenInterest`` heisst kuenftig anders -- bildet
    ``_als_quote`` still auf ``None`` ab, und kein Test bemerkt es.

    Getrennt vom Mitschnitt und **vor** ihm gebaut, weil die Reihenfolge es
    verlangt: Der Mitschnitt umschliesst die Quelle, die Quelle braucht den
    Sammler. Ein Sammler, der den Mitschnitt kennte, waere ein Kreis.
    """

    def __init__(self) -> None:
        self.eintraege: list[dict[str, Any]] = []

    def __call__(self, tickers: Sequence[Any]) -> None:
        # Der letzte Abruf gewinnt: Je Aufzeichnung wird genau ein
        # Verfallstermin notiert, und ein zweiter Aufruf hiesse, dass der
        # erste nicht der ist, der in der Datei steht.
        self.eintraege = [_ticker_als_json(ticker) for ticker in tickers]


class RecordingOptionChainSource:
    """Legt die Antworten der TWS neben ihre Fragen und schreibt beides weg.

    Bewusst je Symbol eine Datei und bewusst nur der letzte Lauf: Der
    Mitschnitt soll ein *Beispiel* sein, kein Bestand. Wer eine zweite Aktie
    braucht, ruft den Befehl ein zweites Mal auf.
    """

    def __init__(
        self,
        inner: OptionChainSource,
        target: Path,
        *,
        price: float,
        as_of: date,
        market_data_type: int,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        rohe: RohNotierungenSammler | None = None,
    ) -> None:
        self._inner = inner
        self._target = target
        self._now = now
        self._rohe = rohe
        self._mitschnitt: dict[str, Any] = {
            "dateiformat": DATEIFORMAT,
            "aufgezeichnet_am": now().isoformat(),
            "kurs": price,
            "stichtag": as_of.isoformat(),
            "marktdatentyp": market_data_type,
        }

    def option_chain(self, contract: ContractSpec) -> OptionChainStructure:
        struktur = self._inner.option_chain(contract)
        self._mitschnitt["symbol"] = contract.symbol
        self._mitschnitt["option_chain"] = {
            "expirations": [termin.isoformat() for termin in struktur.expirations],
            "trading_class": struktur.trading_class,
            "exchange": struktur.exchange,
        }
        return struktur

    def option_strikes(
        self, contract: ContractSpec, expiration: date, trading_class: str
    ) -> tuple[float, ...]:
        strikes = self._inner.option_strikes(contract, expiration, trading_class)
        self._mitschnitt["option_strikes"] = {
            "expiration": expiration.isoformat(),
            "trading_class": trading_class,
            "strikes": list(strikes),
        }
        return strikes

    def option_quotes(
        self,
        contract: ContractSpec,
        expiration: date,
        strikes: Sequence[float],
        market_data_type: int,
        trading_class: str,
    ) -> Sequence[OptionQuote]:
        quotes = self._inner.option_quotes(
            contract, expiration, strikes, market_data_type, trading_class
        )
        abschnitt = {
            "expiration": expiration.isoformat(),
            "trading_class": trading_class,
            "market_data_type": market_data_type,
            # Angefragt und geliefert getrennt: Dass die TWS zu einzelnen
            # Kontrakten nichts zurueckgibt, ist selbst ein Befund (ADR 0048)
            # und geht verloren, wenn nur die Antworten dastehen.
            "angefragte_strikes": list(strikes),
            "quotes": [_quote_als_json(quote) for quote in quotes],
        }
        # **Der erste Abruf bleibt stehen.** Seit ADR 0058, Festlegung 11 folgt
        # ein zweiter, gezielter fuer den Absicherungs-Strike. Wuerde er den
        # ersten ueberschreiben, enthielte die Aufzeichnung genau eine
        # Notierung statt des Moneyness-Bandes -- und damit nicht mehr das,
        # wofuer sie eingefroren wird.
        if "option_quotes" in self._mitschnitt:
            self._mitschnitt.setdefault("weitere_option_quotes", []).append(abschnitt)
        else:
            self._mitschnitt["option_quotes"] = abschnitt
        if self._rohe is not None:
            # Neben den uebersetzten Notierungen, nicht statt ihrer: Der
            # Contract-Test rechnet die Uebersetzung aus den Rohfeldern nach
            # und vergleicht sie mit dem, was damals herauskam.
            self._mitschnitt["rohe_notierungen"] = self._rohe.eintraege
        return quotes

    def write(self) -> None:
        """Schreibt die Aufzeichnung -- auch eine unvollstaendige.

        Bricht der Lauf nach dem ersten Abruf ab, weil kein Verfallstermin im
        Fenster liegt, ist gerade **das** der interessante Fall: Die Datei
        enthaelt dann die Terminliste und sonst nichts, und das steht ihr an.
        """
        self._target.parent.mkdir(parents=True, exist_ok=True)
        self._target.write_text(
            json.dumps(self._mitschnitt, indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def _zahl_als_json(wert: Any) -> Any:
    """Gleitkommazahlen unveraendert, nicht endliche als ``"nan"``.

    Kein ``None`` und keine 0: Beides waere schon eine Deutung, und die zu
    pruefen ist der Zweck dieser Aufzeichnung.
    """
    if isinstance(wert, float) and not math.isfinite(wert):
        return NICHT_ENDLICH
    return wert


def _ticker_als_json(ticker: Any) -> dict[str, Any]:
    """Die Felder eines ``ib_async``-Tickers, die ``_als_quote`` liest.

    Bewusst genau diese und keine weiteren: Ein Ticker traegt Dutzende Felder,
    die die Auswertung nie ansieht -- sie aufzuheben vergroesserte die Datei,
    ohne einen Test zu tragen. Alles ueber ``getattr``, weil ein fehlendes
    Attribut hier dasselbe bedeutet wie in ``_als_quote``: Es gab nichts.
    """
    contract = getattr(ticker, "contract", None)
    greeks = getattr(ticker, "modelGreeks", None)
    return {
        "contract": {
            "lastTradeDateOrContractMonth": getattr(
                contract, "lastTradeDateOrContractMonth", None
            ),
            "strike": _zahl_als_json(getattr(contract, "strike", None)),
            "tradingClass": getattr(contract, "tradingClass", None),
            "conId": getattr(contract, "conId", None),
        },
        "bid": _zahl_als_json(getattr(ticker, "bid", None)),
        "ask": _zahl_als_json(getattr(ticker, "ask", None)),
        "volume": _zahl_als_json(getattr(ticker, "volume", None)),
        "putOpenInterest": _zahl_als_json(getattr(ticker, "putOpenInterest", None)),
        # ``null`` heisst hier "modelGreeks fehlte ganz" -- der Fall, in dem
        # die Optionsmarktdaten-Berechtigung fehlt (Fehler 10091). Er ist von
        # "Greeks da, Delta darin leer" zu unterscheiden.
        "modelGreeks": None
        if greeks is None
        else {
            "delta": _zahl_als_json(getattr(greeks, "delta", None)),
            "impliedVol": _zahl_als_json(getattr(greeks, "impliedVol", None)),
        },
    }


def _quote_als_json(quote: OptionQuote) -> dict[str, Any]:
    """Die Notierung Feld fuer Feld.

    Von Hand statt ueber ``asdict``: Das ist ein Dateiformat, und ein
    umbenanntes Feld soll hier auffallen und nicht still die Datei aendern.
    ``mid`` fehlt absichtlich -- es ist gerechnet, nicht geliefert.
    """
    return {
        "expiration": quote.expiration.isoformat(),
        "strike": quote.strike,
        "bid": quote.bid,
        "ask": quote.ask,
        "delta": quote.delta,
        "implied_volatility": quote.implied_volatility,
        "open_interest": quote.open_interest,
        "volume": quote.volume,
    }
