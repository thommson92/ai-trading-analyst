"""Der Mitschnitt der IBKR-Optionskette (A2-M7).

Zwei Eigenschaften machen ihn brauchbar, und beide sind hier geprueft: Er
aendert am Ergebnis nichts, und er schreibt auch dann, wenn der Abruf
mittendrin endet.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from ai_trading_analyst.domain.analysis import ContractSpec, Stock
from ai_trading_analyst.domain.options import OptionQuote, OptionsParameters
from ai_trading_analyst.infrastructure.ibkr import (
    IbkrOptionsProvider,
    OptionChainStructure,
)
from ai_trading_analyst.infrastructure.ibkr.chain_recorder import (
    DATEIFORMAT,
    RecordingOptionChainSource,
)

AAPL = ContractSpec(symbol="AAPL", exchange="SMART", currency="USD", primary_exchange="NASDAQ")
AKTIE = Stock(id=uuid4(), symbol="AAPL", exchange="NASDAQ")
STICHTAG = date(2026, 9, 1)
AUFGEZEICHNET_AM = datetime(2026, 9, 1, 16, 55, tzinfo=UTC)
VERFALL = date(2026, 10, 16)


class FakeQuelle:
    """Ein Doppel des ``OptionChainSource``-Protokolls mit festen Antworten."""

    def __init__(
        self,
        *,
        expirations: tuple[date, ...] = (VERFALL,),
        gelistet: tuple[float, ...] = (200.0, 210.0, 220.0, 230.0),
        quotes: Sequence[OptionQuote] = (),
    ) -> None:
        self._expirations = expirations
        self._gelistet = gelistet
        self._quotes = tuple(quotes)

    def option_chain(self, contract: ContractSpec) -> OptionChainStructure:
        return OptionChainStructure(
            expirations=self._expirations, trading_class="AAPL", exchange="SMART"
        )

    def option_strikes(
        self, contract: ContractSpec, expiration: date, trading_class: str
    ) -> tuple[float, ...]:
        return self._gelistet

    def option_quotes(
        self,
        contract: ContractSpec,
        expiration: date,
        strikes: Sequence[float],
        market_data_type: int,
        trading_class: str,
    ) -> Sequence[OptionQuote]:
        return self._quotes


def _mitschnitt(quelle: FakeQuelle, ziel: Path) -> RecordingOptionChainSource:
    return RecordingOptionChainSource(
        quelle,
        ziel,
        price=232.14,
        as_of=STICHTAG,
        market_data_type=2,
        now=lambda: AUFGEZEICHNET_AM,
    )


def _provider(kette: RecordingOptionChainSource) -> IbkrOptionsProvider:
    return IbkrOptionsProvider(
        kette,
        watchlist=[AAPL],
        parameters=OptionsParameters(),
        market_data_type=2,
        now=lambda: AUFGEZEICHNET_AM,
    )


def _quote(strike: float, **felder: float | int | None) -> OptionQuote:
    werte: dict[str, float | int | None] = {
        "bid": 3.0,
        "ask": 3.4,
        "delta": -0.25,
        "implied_volatility": 0.31,
        "open_interest": 1200,
        "volume": 84,
    }
    werte.update(felder)
    return OptionQuote(expiration=VERFALL, strike=strike, **werte)  # type: ignore[arg-type]


class TestVollstaendigerLauf:
    def test_alle_drei_abrufe_stehen_in_der_datei(self, tmp_path: Path) -> None:
        ziel = tmp_path / "kette.json"
        quelle = FakeQuelle(quotes=[_quote(210.0), _quote(220.0)])
        kette = _mitschnitt(quelle, ziel)

        _provider(kette).options(AKTIE, price=232.14, as_of=STICHTAG)
        kette.write()

        datei = json.loads(ziel.read_text(encoding="utf-8"))
        assert datei["dateiformat"] == DATEIFORMAT
        assert datei["symbol"] == "AAPL"
        assert datei["kurs"] == 232.14
        assert datei["stichtag"] == "2026-09-01"
        assert datei["aufgezeichnet_am"] == "2026-09-01T16:55:00+00:00"
        assert datei["option_chain"]["expirations"] == ["2026-10-16"]
        assert datei["option_chain"]["trading_class"] == "AAPL"
        assert datei["option_strikes"]["strikes"] == [200.0, 210.0, 220.0, 230.0]
        assert datei["option_quotes"]["expiration"] == "2026-10-16"

    def test_jedes_feld_der_notierung_steht_einzeln_da(self, tmp_path: Path) -> None:
        """Sonst laesst sich aus der Datei nicht mehr nachrechnen, was das
        Verfahren daraus gemacht hat -- und genau das soll sie hergeben."""
        ziel = tmp_path / "kette.json"
        kette = _mitschnitt(FakeQuelle(quotes=[_quote(210.0)]), ziel)

        _provider(kette).options(AKTIE, price=232.14, as_of=STICHTAG)
        kette.write()

        (notierung,) = json.loads(ziel.read_text(encoding="utf-8"))["option_quotes"]["quotes"]
        assert notierung == {
            "expiration": "2026-10-16",
            "strike": 210.0,
            "bid": 3.0,
            "ask": 3.4,
            "delta": -0.25,
            "implied_volatility": 0.31,
            "open_interest": 1200,
            "volume": 84,
        }

    def test_ein_fehlendes_feld_bleibt_leer(self, tmp_path: Path) -> None:
        """Kein Ersatzwert, auch nicht in der Aufzeichnung: Eine Null im
        Mitschnitt waere spaeter von einer echten Null nicht zu unterscheiden."""
        ziel = tmp_path / "kette.json"
        kette = _mitschnitt(FakeQuelle(quotes=[_quote(210.0, open_interest=None)]), ziel)

        _provider(kette).options(AKTIE, price=232.14, as_of=STICHTAG)
        kette.write()

        (notierung,) = json.loads(ziel.read_text(encoding="utf-8"))["option_quotes"]["quotes"]
        assert notierung["open_interest"] is None

    def test_angefragte_und_gelieferte_strikes_stehen_getrennt(self, tmp_path: Path) -> None:
        """Dass die TWS zu einem angefragten Kontrakt nichts liefert, ist
        selbst ein Befund (ADR 0048). Er ginge verloren, stuenden nur die
        Antworten da."""
        ziel = tmp_path / "kette.json"
        kette = _mitschnitt(FakeQuelle(quotes=[_quote(210.0)]), ziel)

        _provider(kette).options(AKTIE, price=232.14, as_of=STICHTAG)
        kette.write()

        abschnitt = json.loads(ziel.read_text(encoding="utf-8"))["option_quotes"]
        assert len(abschnitt["angefragte_strikes"]) > len(abschnitt["quotes"])
        assert 210.0 in abschnitt["angefragte_strikes"]

    def test_die_aufzeichnung_aendert_am_ergebnis_nichts(self, tmp_path: Path) -> None:
        """Die Bedingung, unter der der Schalter im Tageslauf-Codepfad
        ueberhaupt zulaessig ist."""
        quotes = [_quote(210.0), _quote(220.0)]
        ohne = IbkrOptionsProvider(
            FakeQuelle(quotes=quotes),
            watchlist=[AAPL],
            parameters=OptionsParameters(),
            market_data_type=2,
            now=lambda: AUFGEZEICHNET_AM,
        ).options(AKTIE, price=232.14, as_of=STICHTAG)
        mit = _provider(_mitschnitt(FakeQuelle(quotes=quotes), tmp_path / "k.json")).options(
            AKTIE, price=232.14, as_of=STICHTAG
        )

        assert mit == ohne


class TestAbgebrochenerLauf:
    def test_ohne_zulaessigen_termin_bleibt_die_terminliste_stehen(self, tmp_path: Path) -> None:
        """Der Lauf endet nach dem ersten Abruf. Gerade dann ist die Datei
        interessant: Sie zeigt, welche Termine gelistet waren."""
        ziel = tmp_path / "kette.json"
        # Alle Termine weit ausserhalb des Laufzeitfensters.
        quelle = FakeQuelle(expirations=(date(2027, 6, 18),))
        kette = _mitschnitt(quelle, ziel)

        _provider(kette).options(AKTIE, price=232.14, as_of=STICHTAG)
        kette.write()

        datei = json.loads(ziel.read_text(encoding="utf-8"))
        assert datei["option_chain"]["expirations"] == ["2027-06-18"]
        assert "option_quotes" not in datei

    def test_ohne_gelisteten_strike_fehlt_nur_der_notierungsteil(self, tmp_path: Path) -> None:
        ziel = tmp_path / "kette.json"
        kette = _mitschnitt(FakeQuelle(gelistet=()), ziel)

        _provider(kette).options(AKTIE, price=232.14, as_of=STICHTAG)
        kette.write()

        datei = json.loads(ziel.read_text(encoding="utf-8"))
        assert datei["option_strikes"]["strikes"] == []
        assert "option_quotes" not in datei

    def test_ein_leeres_verzeichnis_entsteht_beim_schreiben(self, tmp_path: Path) -> None:
        ziel = tmp_path / "neu" / "tiefer" / "kette.json"
        kette = _mitschnitt(FakeQuelle(), ziel)

        kette.write()

        assert ziel.is_file()
