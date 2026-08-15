"""Vom Backfill bis zur fertigen Kerzenreihe -- gegen echtes PostgreSQL.

Die Einzelteile sind je fuer sich geprueft. Hier geht es um die Naht: Was der
Backfill ablegt, muss der Screener lesen und zu denselben Kerzen verrechnen
koennen, die ein direkter Abruf ergeben haette. Nur die TWS ist ersetzt --
alles danach ist echt, einschliesslich Datenbank und Migrationen.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ai_trading_analyst.application.backfill_history import BackfillHistoryUseCase
from ai_trading_analyst.domain.analysis import ContractSpec, MarketDataProviderError
from ai_trading_analyst.domain.screening import (
    IndicatorParameters,
    IntradayBar,
    SessionParameters,
)
from ai_trading_analyst.infrastructure.ibkr.market_data_provider import IbkrMarketDataProvider
from ai_trading_analyst.infrastructure.persistence.stored_bar_source import StoredBarSource
from ai_trading_analyst.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork

NEW_YORK = ZoneInfo("America/New_York")
AAPL = ContractSpec(symbol="AAPL", primary_exchange="NASDAQ")
SESSION = SessionParameters(
    timezone="America/New_York",
    session_open=time(9, 30),
    session_minutes=390,
    timeframe_minutes=195,
    early_close=time(13, 0),
)
INDICATORS = IndicatorParameters(
    rsi_length=14,
    rsi_method="wilder",
    rsi_ma_length=14,
    rsi_ma_type="sma",
    fast_ema_length=5,
    slow_ema_length=20,
)

UowFactory = Callable[[], SqlAlchemyUnitOfWork]


def trading_days(count: int, first_day: date = date(2026, 3, 2)) -> list[IntradayBar]:
    """Vollstaendige Handelstage zu je zwei Kerzen."""
    bars: list[IntradayBar] = []
    price = 100.0
    for day_offset in range(count):
        session_start = datetime.combine(
            first_day + timedelta(days=day_offset), time(9, 30), tzinfo=NEW_YORK
        )
        for index in range(26):
            price += 0.5
            bars.append(
                IntradayBar(
                    start=session_start + timedelta(minutes=15 * index),
                    open=price,
                    high=price + 0.25,
                    low=price - 0.25,
                    close=price,
                    volume=1_000.0,
                )
            )
    return bars


class FakeTws:
    """Nur die TWS ist ersetzt -- alles dahinter ist echt."""

    def __init__(self, bars: Sequence[IntradayBar]) -> None:
        self._bars = bars
        self.calls: list[int | None] = []

    def fetch_intraday_bars(
        self, contract: ContractSpec, days: int | None = None
    ) -> Sequence[IntradayBar]:
        self.calls.append(days)
        return self._bars

    def close(self) -> None:
        pass


def build_provider(uow_factory: UowFactory) -> IbkrMarketDataProvider:
    return IbkrMarketDataProvider(
        bar_source=StoredBarSource(uow_factory),
        watchlist=(AAPL,),
        session_parameters=SESSION,
        indicator_parameters=INDICATORS,
        native_bar_minutes=15,
    )


class TestBackfillUndScreening:
    def test_was_abgelegt_wurde_ergibt_dieselben_kerzen(
        self, uow_factory: UowFactory
    ) -> None:
        """Der Kern der Sache: Der Umweg ueber die Datenbank aendert nichts am
        Ergebnis."""
        bars = trading_days(20)
        use_case = BackfillHistoryUseCase(FakeTws(bars), uow_factory)

        bericht = use_case.execute((AAPL,))

        assert bericht.stored_bars == len(bars)
        provider = build_provider(uow_factory)
        series = provider.get_candle_series(provider.list_stocks()[0])
        assert len(series) == 40  # 20 Handelstage zu je zwei Kerzen
        letzte = series.indicator(len(series) - 1)
        assert letzte.rsi is not None
        assert letzte.ema20 is not None

    def test_ein_zweiter_backfill_aendert_den_bestand_nicht(
        self, uow_factory: UowFactory
    ) -> None:
        """Wiederholbarkeit, gegen die echte Datenbank statt gegen ein
        In-Memory-Doppel."""
        bars = trading_days(20)
        use_case = BackfillHistoryUseCase(FakeTws(bars), uow_factory)

        use_case.execute((AAPL,))
        zweiter = use_case.execute((AAPL,))

        assert zweiter.stored_bars == 0
        provider = build_provider(uow_factory)
        assert len(provider.get_candle_series(provider.list_stocks()[0])) == 40

    def test_der_zweite_lauf_fragt_nur_noch_die_luecke(self, uow_factory: UowFactory) -> None:
        quelle = FakeTws(trading_days(20))
        use_case = BackfillHistoryUseCase(quelle, uow_factory)

        use_case.execute((AAPL,))
        use_case.execute((AAPL,))

        assert quelle.calls[0] is None  # erster Lauf: Standardzeitraum
        assert quelle.calls[1] is not None  # zweiter: nur die Luecke
        assert quelle.calls[1] > 0

    def test_zwei_laeufe_nacheinander_ergeben_dieselbe_reihe(
        self, uow_factory: UowFactory
    ) -> None:
        """Der eigentliche Gewinn gegenueber dem Abruf je Lauf: IBKRs
        Ein-Jahres-Fenster wandert mit der Uhr, der Bestand nicht."""
        use_case = BackfillHistoryUseCase(FakeTws(trading_days(20)), uow_factory)
        use_case.execute((AAPL,))

        erste = build_provider(uow_factory).get_candle_series(
            build_provider(uow_factory).list_stocks()[0]
        )
        zweite = build_provider(uow_factory).get_candle_series(
            build_provider(uow_factory).list_stocks()[0]
        )

        assert [candle.timestamp for candle in erste.candles] == [
            candle.timestamp for candle in zweite.candles
        ]

    def test_ein_teilweise_gefuellter_bestand_liefert_die_vorhandenen_kerzen(
        self, uow_factory: UowFactory
    ) -> None:
        """Nach einem abgebrochenen Backfill ist der Bestand unvollstaendig,
        aber in sich stimmig -- er soll nutzbar bleiben."""
        BackfillHistoryUseCase(FakeTws(trading_days(5)), uow_factory).execute((AAPL,))

        provider = build_provider(uow_factory)
        assert len(provider.get_candle_series(provider.list_stocks()[0])) == 10


class TestLeererBestand:
    def test_ohne_backfill_verweist_die_meldung_darauf(
        self, uow_factory: UowFactory
    ) -> None:
        """Sonst lautete die Meldung 'keine abgeschlossene Kerze' -- richtig,
        aber am eigentlichen Problem vorbei."""
        provider = build_provider(uow_factory)
        try:
            provider.get_candle_series(provider.list_stocks()[0])
        except MarketDataProviderError as error:
            assert "Backfill" in str(error)
        else:
            raise AssertionError("erwartet wurde ein MarketDataProviderError")


class TestLueckeImBestand:
    def test_eine_echte_luecke_wird_auch_aus_dem_bestand_erkannt(
        self, uow_factory: UowFactory
    ) -> None:
        """Die Kerzenbildung prueft unabhaengig davon, woher die Bars kommen.
        Eine Luecke darf der Umweg ueber die Datenbank nicht verstecken."""
        bars = trading_days(20)
        del bars[3]  # ein Bar mitten in der ersten Kerze
        BackfillHistoryUseCase(FakeTws(bars), uow_factory).execute((AAPL,))

        provider = build_provider(uow_factory)
        try:
            provider.get_candle_series(provider.list_stocks()[0])
        except MarketDataProviderError as error:
            assert "lueckenhafte Historie" in str(error)
        else:
            raise AssertionError("erwartet wurde ein MarketDataProviderError")


class TestZeitzonen:
    def test_die_boersenzeit_ueberlebt_den_umweg_ueber_die_datenbank(
        self, uow_factory: UowFactory
    ) -> None:
        """PostgreSQL speichert in UTC. Die Kerzen muessen trotzdem an den
        Sitzungsgrenzen der Boerse liegen -- 09:30 und 12:45 Ortszeit."""
        BackfillHistoryUseCase(FakeTws(trading_days(2)), uow_factory).execute((AAPL,))

        provider = build_provider(uow_factory)
        series = provider.get_candle_series(provider.list_stocks()[0])

        ortszeiten = {candle.timestamp.astimezone(NEW_YORK).time() for candle in series.candles}
        assert ortszeiten == {time(9, 30), time(12, 45)}


class TestFehlerisolation:
    def test_ein_ausfall_hinterlaesst_keinen_halben_bestand(
        self, uow_factory: UowFactory
    ) -> None:
        """Scheitert der Abruf, darf nichts geschrieben worden sein -- sonst
        haelt der naechste Lauf die Luecke faelschlich fuer gefuellt."""

        class ScheiterndeTws:
            def fetch_intraday_bars(
                self, contract: ContractSpec, days: int | None = None
            ) -> Sequence[IntradayBar]:
                raise MarketDataProviderError("Keine Verbindung zur TWS")

            def close(self) -> None:
                pass

        bericht = BackfillHistoryUseCase(ScheiterndeTws(), uow_factory).execute((AAPL,))

        assert len(bericht.failures) == 1
        with uow_factory() as uow:
            assert uow.intraday_bars.latest_start("AAPL") is None


def test_der_bestand_kennt_seinen_letzten_stand(uow_factory: UowFactory) -> None:
    """Die Angabe, aus der sich der naechste Abrufzeitraum ergibt."""
    bars = trading_days(3)
    BackfillHistoryUseCase(FakeTws(bars), uow_factory).execute((AAPL,))

    with uow_factory() as uow:
        letzter = uow.intraday_bars.latest_start("AAPL")

    assert letzter == bars[-1].start
    assert letzter is not None
    assert letzter.tzinfo is not None
    assert letzter < datetime.now(UTC)
