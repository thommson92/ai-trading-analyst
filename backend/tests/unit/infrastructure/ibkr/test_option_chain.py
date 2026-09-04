"""Die Optionsanbindung an die TWS (ADR 0048).

Gegen ein Doppel des ``IB``-Objekts, ohne laufende TWS und ohne Netz --
dasselbe Vorgehen wie bei den Bars. Geprueft wird, was der Adapter an die
Bibliothek uebergibt und was er aus ihrer Antwort macht; die Fachregel
dahinter hat ihre eigenen Tests in ``tests/unit/domain/options``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from ai_trading_analyst.domain.analysis import (
    ContractSpec,
    OptionsDataProviderError,
    Stock,
)
from ai_trading_analyst.domain.options import (
    REASON_HEDGE_CROSSED,
    OptionQuote,
    OptionsParameters,
    OptionsStatus,
)
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


class _Details:
    """Was ``reqContractDetails`` je Kontrakt zurueckgibt."""

    def __init__(self, contract: FakeKontrakt) -> None:
        self.contract = contract


class FakeIb:
    """Nur die Aufrufe, die die Optionsanbindung an ``ib_async`` richtet."""

    def __init__(
        self,
        ketten: list[FakeKette] | None = None,
        tickers: list[FakeTicker] | None = None,
        gelistet: list[float] | None = None,
    ) -> None:
        self._ketten = ketten if ketten is not None else []
        self._tickers = tickers if tickers is not None else []
        self._gelistet = gelistet if gelistet is not None else []
        self.market_data_types: list[int] = []
        self.qualifiziert: list[Any] = []
        self.ticker_fehler: Exception | None = None

    def reqSecDefOptParams(self, *args: object) -> list[FakeKette]:  # noqa: N802
        return self._ketten

    def reqContractDetails(self, kontrakt: Any) -> list[Any]:  # noqa: N802
        return [_Details(FakeKontrakt(strike)) for strike in self._gelistet]

    def reqMarketDataType(self, art: int) -> None:  # noqa: N802
        self.market_data_types.append(art)

    def qualifyContracts(self, *kontrakte: Any) -> list[Any]:  # noqa: N802
        self.qualifiziert = list(kontrakte)
        return list(kontrakte)

    def reqTickers(self, *kontrakte: object) -> list[FakeTicker]:  # noqa: N802
        if self.ticker_fehler is not None:
            raise self.ticker_fehler
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
        assert struktur.expirations == (date(2026, 10, 2), date(2026, 10, 16))

    def test_unter_mehreren_smart_klassen_gewinnt_die_reichste(self) -> None:
        """Ein Basiswert kann mehrere Handelsklassen haben -- neben der
        regulaeren etwa eine nach einem Split angepasste, die nur noch wenige
        Termine fuehrt. Die zu erwischen, weil sie zufaellig zuerst kommt,
        saehe aus wie "dieser Titel hat keine Wochenoptionen"."""
        angepasst = FakeKette("SMART", ["20261016"], [100.0])
        angepasst.tradingClass = "NFLX1"
        regulaer = FakeKette("SMART", ["20260925", "20261002", "20261016"], [100.0])
        ib = FakeIb(ketten=[angepasst, regulaer])

        struktur = quelle(ib).option_chain(AAPL)

        assert struktur.trading_class == "AAPL"
        assert len(struktur.expirations) == 3

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
    def test_der_marktdatenmodus_wird_gesetzt_und_zurueckgestellt(self) -> None:
        """Ohne ihn kaeme nach Boersenschluss nichts zurueck (ADR 0048).

        Zurueckgestellt wird, weil der Modus fuer die **ganze** Verbindung
        gilt und dieselbe den Kerzenabruf bedient: Bei
        ``market_data.source: live`` verschraenken sich beide je Aktie, und
        ein stehen gebliebenes "verzoegert" wirkte auf Anfragen, die mit
        Optionen nichts zu tun haben.
        """
        ib = FakeIb(tickers=[FakeTicker(90.0)])
        quelle(ib).option_quotes(AAPL, date(2026, 10, 2), [90.0], 2, "AAPL")
        assert ib.market_data_types == [2, 1]

    def test_zurueckgestellt_wird_auch_nach_einem_fehler(self) -> None:
        """Sonst bliebe der Modus gerade dann stehen, wenn der Lauf
        weiterlaeuft -- der Ausfall einer Kette kostet nur diese Aktie."""
        ib = FakeIb(tickers=[FakeTicker(90.0)])
        ib.ticker_fehler = RuntimeError("TWS weg")

        with pytest.raises(IbkrBarSourceError):
            quelle(ib).option_quotes(AAPL, date(2026, 10, 2), [90.0], 2, "AAPL")

        assert ib.market_data_types == [2, 1]

    def test_ohne_strikes_wird_gar_nicht_erst_gefragt(self) -> None:
        ib = FakeIb(tickers=[FakeTicker(90.0)])
        assert quelle(ib).option_quotes(AAPL, date(2026, 10, 2), [], 2, "AAPL") == ()
        assert ib.market_data_types == []

    def test_die_greeks_werden_uebernommen(self) -> None:
        ib = FakeIb(tickers=[FakeTicker(90.0, delta=-0.27)])
        (quote,) = quelle(ib).option_quotes(AAPL, date(2026, 10, 2), [90.0], 2, "AAPL")
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
        (quote,) = quelle(ib).option_quotes(AAPL, date(2026, 10, 2), [90.0], 2, "AAPL")
        assert quote.delta is None
        assert quote.bid == pytest.approx(2.0)

    def test_ein_nan_delta_ist_kein_delta(self) -> None:
        ib = FakeIb(tickers=[FakeTicker(90.0, delta=None)])
        (quote,) = quelle(ib).option_quotes(AAPL, date(2026, 10, 2), [90.0], 2, "AAPL")
        assert quote.delta is None

    @pytest.mark.parametrize("kurs", [-1.0, 0.0])
    def test_ibkrs_minus_eins_ist_kein_kurs(self, kurs: float) -> None:
        """``-1`` heisst bei IBKR "es liegt keine Notierung vor".

        Als Zahl weitergereicht ergaebe es eine negative Praemie und einen
        unsinnigen Mittelwert.
        """
        ib = FakeIb(tickers=[FakeTicker(90.0, bid=kurs, ask=kurs)])
        (quote,) = quelle(ib).option_quotes(AAPL, date(2026, 10, 2), [90.0], 2, "AAPL")
        assert quote.bid is None
        assert quote.ask is None
        assert quote.mid is None

    def test_ein_fehlendes_open_interest_bleibt_leer(self) -> None:
        ib = FakeIb(tickers=[FakeTicker(90.0)])
        (quote,) = quelle(ib).option_quotes(AAPL, date(2026, 10, 2), [90.0], 2, "AAPL")
        assert quote.open_interest is None
        assert quote.volume == 60


class FakeQuelle:
    """Ein Doppel des ``OptionChainSource``-Protokolls."""

    def __init__(
        self,
        struktur: OptionChainStructure,
        tickers: list[Any] | None = None,
        gelistet: tuple[float, ...] = (80.0, 90.0, 95.0, 99.0, 105.0),
    ) -> None:
        self._struktur = struktur
        self._quotes = tickers if tickers is not None else []
        self._gelistet = gelistet
        self.angefragte_strikes: list[float] = []
        self.handelsklassen: list[str] = []
        self.fehler: Exception | None = None

    def option_chain(self, contract: ContractSpec) -> OptionChainStructure:
        if self.fehler is not None:
            raise self.fehler
        return self._struktur

    def option_strikes(
        self, contract: ContractSpec, expiration: date, trading_class: str
    ) -> tuple[float, ...]:
        self.handelsklassen.append(trading_class)
        return self._gelistet

    def option_quotes(
        self,
        contract: ContractSpec,
        expiration: date,
        strikes: Any,
        market_data_type: int,
        trading_class: str,
    ) -> Any:
        self.angefragte_strikes = list(strikes)
        self.handelsklassen.append(trading_class)
        return self._quotes


def struktur(
    expirations: tuple[date, ...] = (date(2026, 10, 2),),
    trading_class: str = "AAPL",
) -> OptionChainStructure:
    return OptionChainStructure(
        expirations=expirations, trading_class=trading_class, exchange="SMART"
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
        quelle = FakeQuelle(struktur(), gelistet=(500.0, 600.0))
        analyse = provider(quelle).options(AKTIE, price=100.0, as_of=STICHTAG)
        assert analyse.status is OptionsStatus.INSUFFICIENT_DATA
        assert "kein Strike" in (analyse.reason or "")
        assert quelle.angefragte_strikes == []

    def test_die_handelsklasse_der_kette_gilt_fuer_beide_folgeabrufe(self) -> None:
        """Sonst waere die Wahl in ``_bevorzugte_kette`` folgenlos.

        Genau das Szenario, gegen das sie geschrieben wurde, traete eine
        Stufe spaeter wieder ein: Ohne Handelsklasse saehen
        ``reqContractDetails`` und ``qualifyContracts`` alle Klassen des
        Basiswerts -- die Strike-Liste mischte zwei Raster, und mehrdeutige
        Kontrakte liesse ``qualifyContracts`` stillschweigend weg.
        """
        quelle = FakeQuelle(struktur(trading_class="NFLX1"))

        provider(quelle).options(AKTIE, price=100.0, as_of=STICHTAG)

        assert quelle.handelsklassen == ["NFLX1", "NFLX1"]

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


class TestGelisteteStrikes:
    """Der Befund vom 2026-08-31, gegen den dieser Schritt gebaut ist.

    ``reqSecDefOptParams`` liefert die **Vereinigung** aller Strikes ueber
    alle Verfallstermine. Bei AAPL hatten die Wochenoptionen 2,50er
    Abstaende, der Monatstermin aber 5,00er -- sechs von zwoelf angefragten
    Kontrakten existierten nicht (``Error 200``), und die Auswahl halbierte
    sich still.
    """

    def test_die_terminliste_kommt_aus_den_kontraktdetails(self) -> None:
        ib = FakeIb(gelistet=[295.0, 300.0, 305.0])
        assert quelle(ib).option_strikes(AAPL, date(2026, 9, 25), "AAPL") == (
            295.0,
            300.0,
            305.0,
        )

    def test_notiert_wird_nur_was_zu_diesem_termin_gelistet_ist(self) -> None:
        """Die Kette kennt 2,50er Schritte, der Termin nur 5,00er."""
        quelle = FakeQuelle(struktur(), gelistet=(295.0, 300.0, 305.0))

        provider(quelle).options(AKTIE, price=309.42, as_of=STICHTAG)

        assert quelle.angefragte_strikes == [305.0, 300.0, 295.0]

    def test_ohne_gelisteten_put_wird_nicht_notiert(self) -> None:
        quelle = FakeQuelle(struktur(), gelistet=())

        analyse = provider(quelle).options(AKTIE, price=100.0, as_of=STICHTAG)

        assert analyse.status is OptionsStatus.INSUFFICIENT_DATA
        assert "kein einziger Put gelistet" in (analyse.reason or "")
        assert quelle.angefragte_strikes == []


class TestGrundOhneVerfallstermin:
    """Der Grund muss zwei Ursachen unterscheiden koennen (Messlauf 2026-08-31).

    Eine Kette, die nur Monatsverfaelle fuehrt, und eine, bei der der Adapter
    die falsche Klasse erwischt hat, ergaben dieselbe Sammelmeldung -- und
    damit war nicht zu entscheiden, ob eine Fensteranpassung oder ein
    Codefehler die Antwort ist.
    """

    # Der Tag des Messlaufs. Von ihm aus liegt der Septemberverfall
    # 18 Tage und der Oktoberverfall 46 Tage entfernt -- das Fenster 21-45
    # trifft keinen von beiden.
    MESSLAUF = date(2026, 8, 31)

    def _grund(self, expirations: tuple[date, ...], *, as_of: date = MESSLAUF) -> str:
        quelle = FakeQuelle(struktur(expirations=expirations))
        analyse = provider(quelle).options(AKTIE, price=100.0, as_of=as_of)
        assert analyse.status is OptionsStatus.INSUFFICIENT_DATA
        return analyse.reason or ""

    def test_die_naechsten_termine_auf_beiden_seiten_stehen_drin(self) -> None:
        """Eine Kette, die das Fenster 21-60 ueberspringt.

        Die Lage vom 2026-08-31 (18 und 46 Tage) faellt seit der
        Verbreiterung **nicht** mehr durch -- 46 liegt jetzt drin. Uebrig
        bleibt der Fall einer Kette mit einer echten Luecke, und auch der
        soll seinen Grund benennen koennen.
        """
        grund = self._grund((date(2026, 9, 18), date(2026, 11, 20)))

        assert "naechste 18 und 81 Tage" in grund

    def test_eine_fehlende_seite_wird_als_fehlend_gezeigt(self) -> None:
        grund = self._grund((date(2026, 11, 20),))

        assert "naechste -- und 81 Tage" in grund

    def test_handelsklasse_und_boerse_stehen_dabei(self) -> None:
        """Ohne sie liesse sich eine angepasste Klasse nicht erkennen."""
        grund = self._grund((date(2026, 11, 20),))

        assert "Klasse 'AAPL' ueber SMART" in grund

    def test_die_termine_werden_aufgezaehlt_aber_gekuerzt(self) -> None:
        viele = tuple(date(2026, 11, 20) + timedelta(days=30 * i) for i in range(9))

        grund = self._grund(viele)

        assert grund.count("2026-") + grund.count("2027-") == 6
        assert grund.endswith("...)")


class TestBerichtsterminBeiDerTerminwahl:
    """Der Rueckfall auf den frueheren Verfall (ADR 0048, Festlegung 7).

    Er greift im Adapter, weil dort der Berichtstermin ankommt -- und weil
    ein Kontrakt, der ohnehin ausschiede, so gar nicht erst notiert wird.
    """

    MESSLAUF = date(2026, 8, 31)

    def test_ein_frueherer_verfall_wird_genommen_statt_gar_keiner(self) -> None:
        quelle = FakeQuelle(
            struktur(expirations=(date(2026, 10, 2), date(2026, 10, 9)))
        )

        analyse = provider(quelle).options(
            AKTIE,
            price=100.0,
            as_of=self.MESSLAUF,
            next_earnings_date=date(2026, 10, 6),
        )

        assert analyse.expiration == date(2026, 10, 2)

    def test_ohne_zulaessigen_termin_nennt_der_grund_den_berichtstermin(self) -> None:
        """Nicht dieselbe Meldung wie bei einem zu schmalen Fenster: Das eine
        heisst "die Kette gibt nichts her", das andere "dieser Titel steht zu
        nah an seinen Zahlen"."""
        quelle = FakeQuelle(
            struktur(expirations=(date(2026, 10, 2), date(2026, 10, 9)))
        )

        analyse = provider(quelle).options(
            AKTIE,
            price=100.0,
            as_of=self.MESSLAUF,
            next_earnings_date=date(2026, 9, 15),
        )

        assert analyse.status is OptionsStatus.INSUFFICIENT_DATA
        assert "nach dem Berichtstermin am 2026-09-15" in (analyse.reason or "")
        assert quelle.angefragte_strikes == []


class SpreadQuelle:
    """Eine Quelle, die **jede** Notierungsanfrage einzeln beantwortet.

    ``FakeQuelle`` gibt auf jede Frage dieselbe Liste zurueck und merkt sich
    nur die letzte -- fuer den zweiten, gezielten Abruf des
    Absicherungs-Strikes (ADR 0058, Festlegung 11) ist beides unbrauchbar.
    """

    def __init__(
        self,
        *,
        notiert: dict[float, OptionQuote],
        nachschlag: Sequence[OptionQuote] | Exception = (),
        gelistet: tuple[float, ...] = (80.0, 90.0, 95.0, 99.0, 105.0),
    ) -> None:
        self._notiert = notiert
        self._nachschlag = nachschlag
        self._gelistet = gelistet
        self.abfragen: list[tuple[float, ...]] = []

    def option_chain(self, contract: ContractSpec) -> OptionChainStructure:
        return struktur()

    def option_strikes(
        self, contract: ContractSpec, expiration: date, trading_class: str
    ) -> tuple[float, ...]:
        return self._gelistet

    def option_quotes(
        self,
        contract: ContractSpec,
        expiration: date,
        strikes: Any,
        market_data_type: int,
        trading_class: str,
    ) -> Sequence[OptionQuote]:
        self.abfragen.append(tuple(strikes))
        if len(self.abfragen) == 1:
            return tuple(self._notiert[s] for s in strikes if s in self._notiert)
        if isinstance(self._nachschlag, Exception):
            raise self._nachschlag
        return self._nachschlag


def notierung(
    strike: float, *, bid: float = 2.0, ask: float = 2.1, delta: float | None = -0.25
) -> OptionQuote:
    return OptionQuote(
        expiration=date(2026, 10, 2),
        strike=strike,
        bid=bid,
        ask=ask,
        delta=delta,
        implied_volatility=0.31,
        open_interest=None,
        volume=60,
    )


def spread_analyse(quelle: SpreadQuelle) -> Any:
    """Ein enges Moneyness-Band, damit der Absicherungs-Strike herausfaellt.

    Notiert werden dann nur 99 und 95; die Zielbreite von 6,5 Prozent fuehrt
    von 99 auf 92,5 und damit auf den gelisteten, aber **nicht** notierten
    90er. Genau dann tritt der Rueckfall ein.
    """
    return IbkrOptionsProvider(
        quelle,
        watchlist=[AAPL],
        parameters=OptionsParameters(min_moneyness=0.92),
        market_data_type=2,
        now=lambda: BEWERTET_AM,
    ).options(AKTIE, price=100.0, as_of=STICHTAG)


class TestStrukturvergleichAmAdapter:
    """Die Zweige des zweiten Abrufs. Sie liegen alle im Adapter, nicht in der
    Domaene -- die Rechnung selbst hat ihre Tests in
    ``tests/unit/domain/options/test_spread.py``."""

    def _quelle(self, **kwargs: Any) -> SpreadQuelle:
        return SpreadQuelle(
            notiert={99.0: notierung(99.0), 95.0: notierung(95.0)}, **kwargs
        )

    def test_der_nachgefragte_kontrakt_wird_gespeichert_und_gerechnet(self) -> None:
        quelle = self._quelle(nachschlag=(notierung(90.0, bid=0.8, ask=0.9),))

        analyse = spread_analyse(quelle)

        assert quelle.abfragen[1] == (90.0,)
        assert analyse.spread is not None
        assert analyse.spread.hedge_strike == 90.0
        # Angehaengt, und genau einmal: Die Kalibrierung mittelt ueber die
        # Zeilen in ``option_quotes`` (ADR 0058, Festlegung 1).
        assert [q.strike for q in analyse.quotes] == [99.0, 95.0, 90.0]

    def test_ein_anderer_strike_als_angefragt_wird_nicht_geglaubt(self) -> None:
        """Der Anbieter antwortet gelegentlich mit einem anderen Kontrakt.
        Liegt er unter dem Verkauf, ergaebe er einen rechnerisch richtigen
        Spread ganz anderer Breite -- und stuende womoeglich ein zweites Mal
        in ``option_quotes``, weil ueber den **angefragten** Strike nachgesehen
        wurde."""
        quelle = self._quelle(nachschlag=(notierung(95.0, bid=0.8, ask=0.9),))

        analyse = spread_analyse(quelle)

        assert analyse.spread is None
        assert "95.00" in (analyse.spread_reason or "")
        assert "90.00" in (analyse.spread_reason or "")

    def test_ein_ausfall_der_tws_entwertet_die_optionsanalyse_nicht(self) -> None:
        quelle = self._quelle(nachschlag=IbkrBarSourceError("Zeitueberschreitung"))

        analyse = spread_analyse(quelle)

        assert analyse.status is OptionsStatus.COMPLETED
        assert analyse.strategies
        assert analyse.spread is None
        assert "Zeitueberschreitung" in (analyse.spread_reason or "")

    def test_eine_leere_antwort_nennt_den_strike(self) -> None:
        quelle = self._quelle(nachschlag=())

        analyse = spread_analyse(quelle)

        assert analyse.spread is None
        assert "90.00" in (analyse.spread_reason or "")

    def test_eine_abgerufene_notierung_bleibt_auch_ohne_spread_erhalten(self) -> None:
        """Die Anfrage ist bezahlt, und gerade Notierungen ausserhalb des
        Bandes sagen als einzige etwas ueber die Form der Volatilitaetskurve
        (ADR 0058, Festlegung 1). Hier ist der Markt gekreuzt -- kein Spread,
        aber sehr wohl eine Beobachtung."""
        quelle = self._quelle(nachschlag=(notierung(90.0, bid=0.9, ask=0.8),))

        analyse = spread_analyse(quelle)

        assert analyse.spread is None
        assert analyse.spread_reason == REASON_HEDGE_CROSSED
        assert 90.0 in [q.strike for q in analyse.quotes]
