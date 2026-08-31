"""Die Optionsanbindung an die TWS (ADR 0048).

Gegen ein Doppel des ``IB``-Objekts, ohne laufende TWS und ohne Netz --
dasselbe Vorgehen wie bei den Bars. Geprueft wird, was der Adapter an die
Bibliothek uebergibt und was er aus ihrer Antwort macht; die Fachregel
dahinter hat ihre eigenen Tests in ``tests/unit/domain/options``.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

import pytest

from ai_trading_analyst.domain.analysis import (
    ContractSpec,
    OptionsDataProviderError,
    Stock,
)
from ai_trading_analyst.domain.options import OptionsParameters, OptionsStatus
from ai_trading_analyst.infrastructure.ibkr import (
    IbAsyncBarSource,
    IbkrBarSourceError,
    IbkrConnectionSettings,
    IbkrOptionsProvider,
    OptionChainStructure,
)

AAPL = ContractSpec(symbol="AAPL", exchange="SMART", currency="USD", primary_exchange="NASDAQ")
UNBESETZTER_PORT = IbkrConnectionSettings(
    host="127.0.0.1", port=1, client_id=1, connect_timeout_seconds=0.1
)
STICHTAG = date(2026, 9, 1)
BEWERTET_AM = datetime(2026, 9, 1, 20, 30, tzinfo=UTC)


class FakeKette:
    def __init__(self, exchange: str, expirations: list[str], strikes: list[float]) -> None:
        self.exchange = exchange
        self.expirations = expirations
        self.strikes = strikes
        self.tradingClass = "AAPL"


class FakeKontrakt:
    def __init__(self, strike: float, expiration: str = "20261002") -> None:
        self.strike = strike
        self.lastTradeDateOrContractMonth = expiration
        self.symbol = "AAPL"
        self.secType = "STK"
        self.conId = 265598


class FakeGreeks:
    def __init__(self, delta: float | None, implied_vol: float | None) -> None:
        self.delta = math.nan if delta is None else delta
        self.impliedVol = math.nan if implied_vol is None else implied_vol


class FakeTicker:
    def __init__(
        self,
        strike: float,
        *,
        bid: float = 2.0,
        ask: float = 2.1,
        delta: float | None = -0.25,
        volume: float = 60.0,
        greeks: bool = True,
    ) -> None:
        self.contract = FakeKontrakt(strike)
        self.bid = bid
        self.ask = ask
        self.volume = volume
        self.putOpenInterest = math.nan
        self.modelGreeks = FakeGreeks(delta, 0.31) if greeks else None


class FakeIb:
    """Nur die Aufrufe, die die Optionsanbindung an ``ib_async`` richtet."""

    def __init__(
        self,
        ketten: list[FakeKette] | None = None,
        tickers: list[FakeTicker] | None = None,
    ) -> None:
        self._ketten = ketten if ketten is not None else []
        self._tickers = tickers if tickers is not None else []
        self.market_data_types: list[int] = []
        self.qualifiziert: list[Any] = []

    def reqSecDefOptParams(self, *args: object) -> list[FakeKette]:  # noqa: N802
        return self._ketten

    def reqMarketDataType(self, art: int) -> None:  # noqa: N802
        self.market_data_types.append(art)

    def qualifyContracts(self, *kontrakte: Any) -> list[Any]:  # noqa: N802
        self.qualifiziert = list(kontrakte)
        return list(kontrakte)

    def reqTickers(self, *kontrakte: object) -> list[FakeTicker]:  # noqa: N802
        return self._tickers


def quelle(ib: FakeIb) -> IbAsyncBarSource:
    gebaut = IbAsyncBarSource(UNBESETZTER_PORT, native_bar_minutes=15, duration="1 Y")
    gebaut._connection = lambda: ib  # type: ignore[method-assign]
    gebaut._qualified = lambda ib, contract: FakeKontrakt(0.0)  # type: ignore[method-assign]
    return gebaut


class TestKettenabruf:
    def test_die_smart_kette_wird_bevorzugt(self) -> None:
        """Abgefragt wird ueber SMART -- die Kette dieser Boerse ist die passende."""
        ib = FakeIb(
            ketten=[
                FakeKette("CBOE", ["20261002"], [100.0]),
                FakeKette("SMART", ["20261002", "20261016"], [90.0, 100.0]),
            ]
        )
        struktur = quelle(ib).option_chain(AAPL)
        assert struktur.exchange == "SMART"
        assert struktur.strikes == (90.0, 100.0)

    def test_ohne_smart_gewinnt_die_reichste_kette(self) -> None:
        ib = FakeIb(
            ketten=[
                FakeKette("CBOE", ["20261002"], [100.0]),
                FakeKette("AMEX", ["20261002", "20261016", "20261120"], [100.0]),
            ]
        )
        assert quelle(ib).option_chain(AAPL).exchange == "AMEX"

    def test_verfallstermine_werden_uebersetzt_und_sortiert(self) -> None:
        ib = FakeIb(ketten=[FakeKette("SMART", ["20261016", "20261002"], [100.0])])
        assert quelle(ib).option_chain(AAPL).expirations == (
            date(2026, 10, 2),
            date(2026, 10, 16),
        )

    def test_ein_termin_ohne_tagesangabe_wird_verworfen_nicht_geraten(self) -> None:
        """IBKR liefert fuer manche Basiswerte Monatsangaben.

        Ein daraus ergaenzter Tag waere ein erfundener Verfallstermin -- und
        er faende sich spaeter als Vertragsdatum in einem Bericht wieder.
        """
        ib = FakeIb(ketten=[FakeKette("SMART", ["202610", "20261002"], [100.0])])
        assert quelle(ib).option_chain(AAPL).expirations == (date(2026, 10, 2),)

    def test_ein_basiswert_ohne_optionen_meldet_sich_deutlich(self) -> None:
        with pytest.raises(IbkrBarSourceError, match="keine Optionskette"):
            quelle(FakeIb(ketten=[])).option_chain(AAPL)


class TestNotierungen:
    def test_der_marktdatenmodus_wird_gesetzt(self) -> None:
        """Ohne ihn kaeme nach Boersenschluss nichts zurueck (ADR 0048)."""
        ib = FakeIb(tickers=[FakeTicker(90.0)])
        quelle(ib).option_quotes(AAPL, date(2026, 10, 2), [90.0], 2)
        assert ib.market_data_types == [2]

    def test_ohne_strikes_wird_gar_nicht_erst_gefragt(self) -> None:
        ib = FakeIb(tickers=[FakeTicker(90.0)])
        assert quelle(ib).option_quotes(AAPL, date(2026, 10, 2), [], 2) == ()
        assert ib.market_data_types == []

    def test_die_greeks_werden_uebernommen(self) -> None:
        ib = FakeIb(tickers=[FakeTicker(90.0, delta=-0.27)])
        (quote,) = quelle(ib).option_quotes(AAPL, date(2026, 10, 2), [90.0], 2)
        assert quote.delta == pytest.approx(-0.27)
        assert quote.implied_volatility == pytest.approx(0.31)
        assert quote.strike == pytest.approx(90.0)
        assert quote.expiration == date(2026, 10, 2)

    def test_ohne_greeks_bleibt_das_delta_leer(self) -> None:
        """Der Fall ohne Optionsmarktdaten-Abo (Spike: ``Error 10091``).

        Kein Ersatzwert: Die Domain verwirft den Kontrakt danach mit
        benanntem Grund.
        """
        ib = FakeIb(tickers=[FakeTicker(90.0, greeks=False)])
        (quote,) = quelle(ib).option_quotes(AAPL, date(2026, 10, 2), [90.0], 2)
        assert quote.delta is None
        assert quote.bid == pytest.approx(2.0)

    def test_ein_nan_delta_ist_kein_delta(self) -> None:
        ib = FakeIb(tickers=[FakeTicker(90.0, delta=None)])
        (quote,) = quelle(ib).option_quotes(AAPL, date(2026, 10, 2), [90.0], 2)
        assert quote.delta is None

    @pytest.mark.parametrize("kurs", [-1.0, 0.0])
    def test_ibkrs_minus_eins_ist_kein_kurs(self, kurs: float) -> None:
        """``-1`` heisst bei IBKR "es liegt keine Notierung vor".

        Als Zahl weitergereicht ergaebe es eine negative Praemie und einen
        unsinnigen Mittelwert.
        """
        ib = FakeIb(tickers=[FakeTicker(90.0, bid=kurs, ask=kurs)])
        (quote,) = quelle(ib).option_quotes(AAPL, date(2026, 10, 2), [90.0], 2)
        assert quote.bid is None
        assert quote.ask is None
        assert quote.mid is None

    def test_ein_fehlendes_open_interest_bleibt_leer(self) -> None:
        ib = FakeIb(tickers=[FakeTicker(90.0)])
        (quote,) = quelle(ib).option_quotes(AAPL, date(2026, 10, 2), [90.0], 2)
        assert quote.open_interest is None
        assert quote.volume == 60


class FakeQuelle:
    """Ein Doppel des ``OptionChainSource``-Protokolls."""

    def __init__(
        self, struktur: OptionChainStructure, tickers: list[Any] | None = None
    ) -> None:
        self._struktur = struktur
        self._quotes = tickers if tickers is not None else []
        self.angefragte_strikes: list[float] = []
        self.fehler: Exception | None = None

    def option_chain(self, contract: ContractSpec) -> OptionChainStructure:
        if self.fehler is not None:
            raise self.fehler
        return self._struktur

    def option_quotes(
        self,
        contract: ContractSpec,
        expiration: date,
        strikes: Any,
        market_data_type: int,
    ) -> Any:
        self.angefragte_strikes = list(strikes)
        return self._quotes


def struktur(
    expirations: tuple[date, ...] = (date(2026, 10, 2),),
    strikes: tuple[float, ...] = (80.0, 90.0, 95.0, 99.0, 105.0),
) -> OptionChainStructure:
    return OptionChainStructure(
        expirations=expirations, strikes=strikes, trading_class="AAPL", exchange="SMART"
    )


def provider(quelle: FakeQuelle) -> IbkrOptionsProvider:
    return IbkrOptionsProvider(
        quelle,
        watchlist=[AAPL],
        parameters=OptionsParameters(),
        market_data_type=2,
        now=lambda: BEWERTET_AM,
    )


AKTIE = Stock(id=uuid4(), symbol="AAPL", exchange="NASDAQ")


class TestAnbieter:
    def test_nur_die_ausgewaehlten_strikes_werden_notiert(self) -> None:
        """Jede Notierung kostet eine Marktdatenanfrage (ADR 0048)."""
        quelle = FakeQuelle(struktur())
        provider(quelle).options(AKTIE, price=100.0, as_of=STICHTAG)
        assert quelle.angefragte_strikes == [99.0, 95.0, 90.0, 80.0]

    def test_ohne_termin_im_zielfenster_wird_nicht_notiert(self) -> None:
        quelle = FakeQuelle(struktur(expirations=(date(2026, 9, 4),)))
        analyse = provider(quelle).options(AKTIE, price=100.0, as_of=STICHTAG)
        assert analyse.status is OptionsStatus.INSUFFICIENT_DATA
        assert "kein Verfallstermin" in (analyse.reason or "")
        assert quelle.angefragte_strikes == []

    def test_ohne_strike_im_band_wird_nicht_notiert(self) -> None:
        quelle = FakeQuelle(struktur(strikes=(500.0, 600.0)))
        analyse = provider(quelle).options(AKTIE, price=100.0, as_of=STICHTAG)
        assert analyse.status is OptionsStatus.INSUFFICIENT_DATA
        assert "kein Strike" in (analyse.reason or "")
        assert quelle.angefragte_strikes == []

    def test_ein_symbol_ausserhalb_der_watchliste_faellt_auf(self) -> None:
        fremd = Stock(id=uuid4(), symbol="MSFT", exchange="NASDAQ")
        with pytest.raises(OptionsDataProviderError, match="Watchlist"):
            provider(FakeQuelle(struktur())).options(fremd, price=100.0, as_of=STICHTAG)

    def test_ein_ausfall_der_tws_wird_zum_anbieterfehler(self) -> None:
        """Der Application-Layer isoliert ihn je Aktie -- er muss ihn erkennen."""
        quelle = FakeQuelle(struktur())
        quelle.fehler = IbkrBarSourceError("TWS nicht angemeldet")
        with pytest.raises(OptionsDataProviderError, match="TWS nicht angemeldet"):
            provider(quelle).options(AKTIE, price=100.0, as_of=STICHTAG)
