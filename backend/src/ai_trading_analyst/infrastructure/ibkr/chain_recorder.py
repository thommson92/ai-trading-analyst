"""Mitschnitt einer echten IBKR-Optionskette (A2-M7).

Warum es diesen Mitschnitt ueberhaupt braucht: Von den drei Anbietern, deren
Antwortformat die Auswertung traegt, ist genau einer **nicht** ueber HTTP
erreichbar. Finnhub laesst sich mit einem einzigen ``curl`` einfrieren; die
TWS-Schnittstelle spricht ein eigenes Protokoll ueber einen lokalen Socket,
und ohne laufende TWS gibt es keine Antwort zum Aufheben.

Der Mitschnitt haengt sich deshalb an derselben Stelle ein, an der auch der
Adapter haengt -- an ``OptionChainSource``. Aufgezeichnet wird, was die TWS
auf die drei Abrufe geantwortet hat, und **nur** das: keine bewertete
Analyse, keine abgeleitete Groesse. Was daraus folgt, rechnet der Test aus
denselben Rohdaten noch einmal aus. Ein Mitschnitt der fertigen Analyse
wuerde die Rechnung mit einfrieren und koennte eine Formataenderung des
Anbieters nicht mehr von einer Verfahrensaenderung unterscheiden.

Die Aufzeichnung ist **passiv**: Sie reicht jeden Aufruf unveraendert
weiter und aendert an keinem Ergebnis etwas. Ein Lauf mit ``--record`` und
einer ohne liefern dieselbe Analyse.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from ai_trading_analyst.domain.analysis import ContractSpec
from ai_trading_analyst.domain.options import OptionQuote

from .bar_source import OptionChainStructure
from .option_chain import OptionChainSource

DATEIFORMAT = 1
"""Version des Dateiformats. Sie steht in jeder Aufzeichnung, damit ein
spaeterer Leser eine alte Datei erkennt, statt sie stillschweigend halb zu
verstehen."""


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
    ) -> None:
        self._inner = inner
        self._target = target
        self._now = now
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
        self._mitschnitt["option_quotes"] = {
            "expiration": expiration.isoformat(),
            "trading_class": trading_class,
            "market_data_type": market_data_type,
            # Angefragt und geliefert getrennt: Dass die TWS zu einzelnen
            # Kontrakten nichts zurueckgibt, ist selbst ein Befund (ADR 0048)
            # und geht verloren, wenn nur die Antworten dastehen.
            "angefragte_strikes": list(strikes),
            "quotes": [_quote_als_json(quote) for quote in quotes],
        }
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
