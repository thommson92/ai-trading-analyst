"""Repository- und UnitOfWork-Tests gegen echtes PostgreSQL."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.exc import IntegrityError

from ai_trading_analyst.domain.analysis import (
    RunStatus,
    Stock,
    StockProcessingError,
    StockScreeningOutcome,
)
from ai_trading_analyst.domain.screening import (
    SIGNAL_RULE_VERSION,
    IntradayBar,
    ScreeningResult,
    ScreeningStatus,
    SignalEvent,
    SignalType,
)
from ai_trading_analyst.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from tests.integration.conftest import make_outcome, make_run, make_stock

UowFactory = Callable[[], SqlAlchemyUnitOfWork]


class TestStockRepository:
    def test_add_is_idempotent_fuer_dasselbe_symbol(self, uow_factory: UowFactory) -> None:
        stock = make_stock("IDEMP")
        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.stocks.add(stock)
            uow.commit()

        with uow_factory() as uow:
            assert len(uow.stocks.list_all()) == 1
            assert uow.stocks.get_by_symbol("IDEMP") == stock

    def test_unbekanntes_symbol_liefert_none(self, uow_factory: UowFactory) -> None:
        with uow_factory() as uow:
            assert uow.stocks.get_by_symbol("NICHT_VORHANDEN") is None

    def test_add_ist_idempotent_auch_bei_abweichender_id_fuer_dasselbe_symbol(
        self, uow_factory: UowFactory
    ) -> None:
        """Ein Marktdatenanbieter, der fuer ein bereits bekanntes Symbol eine
        neue id liefert, darf den bestehenden Datensatz nicht per
        IntegrityError zum Absturz bringen -- Idempotenz gilt nach Symbol,
        nicht nach id (siehe SqlAlchemyStockRepository.add)."""
        original = make_stock("SAMESYMBOL")
        with_different_id = Stock(
            id=make_stock("EIN_ANDERES_SYMBOL").id, symbol="SAMESYMBOL", exchange="NYSE"
        )

        with uow_factory() as uow:
            uow.stocks.add(original)
            uow.commit()

        with uow_factory() as uow:
            uow.stocks.add(with_different_id)
            uow.commit()

        with uow_factory() as uow:
            assert len(uow.stocks.list_all()) == 1
            assert uow.stocks.get_by_symbol("SAMESYMBOL") == original


class TestAnalysisRunRepository:
    def test_roundtrip_add_get_update(self, uow_factory: UowFactory) -> None:
        run = make_run(status=RunStatus.RUNNING)
        with uow_factory() as uow:
            uow.analysis_runs.add(run)
            uow.commit()

        with uow_factory() as uow:
            fetched = uow.analysis_runs.get(run.id)
        assert fetched == run

        run.status = RunStatus.COMPLETED
        run.candidates_found = 3
        with uow_factory() as uow:
            uow.analysis_runs.update(run)
            uow.commit()

        with uow_factory() as uow:
            updated = uow.analysis_runs.get(run.id)
        assert updated is not None
        assert updated.status == RunStatus.COMPLETED
        assert updated.candidates_found == 3

    def test_erneute_abfrage_eines_abgeschlossenen_laufs_liefert_konsistente_daten(
        self, uow_factory: UowFactory
    ) -> None:
        run = make_run(status=RunStatus.COMPLETED)
        with uow_factory() as uow:
            uow.analysis_runs.add(run)
            uow.commit()

        with uow_factory() as uow:
            first = uow.analysis_runs.get(run.id)
        with uow_factory() as uow:
            second = uow.analysis_runs.get(run.id)

        assert first == second == run

    def test_update_eines_unbekannten_laufs_schlaegt_eindeutig_fehl(
        self, uow_factory: UowFactory
    ) -> None:
        run = make_run()
        with pytest.raises(LookupError):
            with uow_factory() as uow:
                uow.analysis_runs.update(run)
                uow.commit()


class TestScreeningResultRepository:
    @pytest.mark.parametrize(
        "status",
        [
            ScreeningStatus.CANDIDATE,
            ScreeningStatus.NOT_CANDIDATE,
            ScreeningStatus.UNKNOWN_DATA_INCOMPLETE,
        ],
    )
    def test_alle_drei_screening_status_koennen_gespeichert_und_gelesen_werden(
        self, uow_factory: UowFactory, status: ScreeningStatus
    ) -> None:
        stock = make_stock(f"STATUS-{status.value}")
        run = make_run()
        outcome = make_outcome(stock, status, analysis_run_id=run.id)

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()

        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)
        assert persisted.result.status == status
        assert persisted.stock == stock

    def test_signal_events_werden_mitgespeichert(self, uow_factory: UowFactory) -> None:
        stock = make_stock("WITHEVENTS")
        run = make_run()
        events = (
            SignalEvent(signal_type=SignalType.RSI_CROSS, candle_index=254),
            SignalEvent(signal_type=SignalType.PRICE_EMA20_BREAKOUT, candle_index=257),
        )
        outcome = StockScreeningOutcome(
            analysis_run_id=run.id,
            stock=stock,
            result=ScreeningResult(
                status=ScreeningStatus.CANDIDATE,
                fired_signal_types=frozenset({event.signal_type for event in events}),
                signal_events=events,
            ),
            decision_candle_index=258,
            evaluated_at=datetime.now(UTC),
            signal_rule_version=SIGNAL_RULE_VERSION,
        )

        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(outcome)
            uow.commit()

        with uow_factory() as uow:
            (persisted,) = uow.screening_results.list_for_run(run.id)
        assert persisted.result.signal_events == events
        assert persisted.result.fired_signal_types == frozenset(
            {SignalType.RSI_CROSS, SignalType.PRICE_EMA20_BREAKOUT}
        )

    def test_zweites_ergebnis_fuer_dieselbe_aktie_im_selben_lauf_wird_abgelehnt(
        self, uow_factory: UowFactory
    ) -> None:
        """Abgeschlossene Screening-Ergebnisse werden nicht stillschweigend
        ueberschrieben -- die Datenbank erzwingt das zusaetzlich zur Anwendungslogik."""
        stock = make_stock("NOOVERWRITE")
        run = make_run()
        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.analysis_runs.add(run)
            uow.screening_results.add(
                make_outcome(stock, ScreeningStatus.NOT_CANDIDATE, analysis_run_id=run.id)
            )
            uow.commit()

        with pytest.raises(IntegrityError):
            with uow_factory() as uow:
                uow.screening_results.add(
                    make_outcome(stock, ScreeningStatus.CANDIDATE, analysis_run_id=run.id)
                )
                uow.commit()


class TestProcessingErrorRepository:
    def test_fehlerisolation_zwischen_zwei_aktien_bleibt_unabhaengig_nachvollziehbar(
        self, uow_factory: UowFactory
    ) -> None:
        run = make_run()
        stock_ok = make_stock("OK1")
        with uow_factory() as uow:
            uow.analysis_runs.add(run)
            uow.stocks.add(stock_ok)
            uow.screening_results.add(
                make_outcome(stock_ok, ScreeningStatus.NOT_CANDIDATE, analysis_run_id=run.id)
            )
            uow.processing_errors.add(
                StockProcessingError(
                    analysis_run_id=run.id,
                    stock_symbol="BROKEN1",
                    message="Simulierter Fehler",
                    occurred_at=datetime.now(UTC),
                )
            )
            uow.commit()

        with uow_factory() as uow:
            outcomes = uow.screening_results.list_for_run(run.id)
            errors = uow.processing_errors.list_for_run(run.id)

        assert len(outcomes) == 1
        assert outcomes[0].stock.symbol == "OK1"
        assert len(errors) == 1
        assert errors[0].stock_symbol == "BROKEN1"


class TestTransaktionsverhalten:
    def test_nicht_committete_aenderungen_werden_beim_normalen_verlassen_verworfen(
        self, uow_factory: UowFactory
    ) -> None:
        stock = make_stock("NOCOMMIT")
        with uow_factory() as uow:
            uow.stocks.add(stock)
            # kein uow.commit()

        with uow_factory() as uow:
            assert uow.stocks.get_by_symbol("NOCOMMIT") is None

    def test_eine_exception_rollt_alle_ausstehenden_aenderungen_zurueck(
        self, uow_factory: UowFactory
    ) -> None:
        stock = make_stock("ROLLBACK")

        class _SimulatedFailureError(Exception):
            pass

        with pytest.raises(_SimulatedFailureError):
            with uow_factory() as uow:
                uow.stocks.add(stock)
                raise _SimulatedFailureError("simulierter Fehler mitten in der Transaktion")

        with uow_factory() as uow:
            assert uow.stocks.get_by_symbol("ROLLBACK") is None

    def test_explizites_rollback_verwirft_aenderungen_ohne_exception(
        self, uow_factory: UowFactory
    ) -> None:
        stock = make_stock("EXPLICITROLLBACK")
        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.rollback()

        with uow_factory() as uow:
            assert uow.stocks.get_by_symbol("EXPLICITROLLBACK") is None


def make_bar(start: datetime, close: float = 100.0) -> IntradayBar:
    return IntradayBar(
        start=start, open=close, high=close + 1, low=close - 1, close=close, volume=1_000.0
    )


class TestIntradayBarRepository:
    """Der Speicher, von dem der Backfill lebt. Entscheidend ist nicht das
    Schreiben, sondern dass ein wiederholter Lauf nichts kaputt macht."""

    NEW_YORK = ZoneInfo("America/New_York")

    def _bars(self, anzahl: int, ab: datetime | None = None) -> list[IntradayBar]:
        beginn = ab or datetime(2026, 3, 10, 9, 30, tzinfo=self.NEW_YORK)
        return [make_bar(beginn + timedelta(minutes=15 * index)) for index in range(anzahl)]

    def test_ohne_daten_gibt_es_keinen_letzten_stand(self, uow_factory: UowFactory) -> None:
        """Der Fall des allerersten Laufs -- er entscheidet, ob ein ganzes Jahr
        oder nur ein Tag geholt wird."""
        with uow_factory() as uow:
            assert uow.intraday_bars.latest_start("LEER") is None

    def test_der_letzte_stand_ist_der_juengste_bar(self, uow_factory: UowFactory) -> None:
        bars = self._bars(5)
        with uow_factory() as uow:
            uow.intraday_bars.add_all("AAPL", bars)
            uow.commit()

        with uow_factory() as uow:
            assert uow.intraday_bars.latest_start("AAPL") == bars[-1].start

    def test_derselbe_lauf_zweimal_schreibt_nichts_doppelt(self, uow_factory: UowFactory) -> None:
        """Die Eigenschaft, die den Backfill wiederholbar macht: Ein
        abgebrochener Lauf wird schlicht erneut gestartet."""
        bars = self._bars(5)
        with uow_factory() as uow:
            assert uow.intraday_bars.add_all("AAPL", bars) == 5
            uow.commit()

        with uow_factory() as uow:
            assert uow.intraday_bars.add_all("AAPL", bars) == 0
            uow.commit()

        with uow_factory() as uow:
            assert len(uow.intraday_bars.list_for("AAPL")) == 5

    def test_ueberlappende_zeitraeume_zaehlen_nur_das_neue(
        self, uow_factory: UowFactory
    ) -> None:
        """Zwei Laeufe ueberlappen sich zwangslaeufig -- der zweite beginnt am
        letzten bekannten Bar, damit keine Luecke entsteht."""
        with uow_factory() as uow:
            uow.intraday_bars.add_all("AAPL", self._bars(5))
            uow.commit()

        with uow_factory() as uow:
            assert uow.intraday_bars.add_all("AAPL", self._bars(8)) == 3
            uow.commit()

        with uow_factory() as uow:
            assert len(uow.intraday_bars.list_for("AAPL")) == 8

    def test_bars_kommen_zeitlich_aufsteigend_zurueck(self, uow_factory: UowFactory) -> None:
        """Die Aggregation verlaesst sich nicht darauf, aber eine falsche
        Reihenfolge waere ein stiller Fehler."""
        bars = self._bars(6)
        with uow_factory() as uow:
            uow.intraday_bars.add_all("AAPL", list(reversed(bars)))
            uow.commit()

        with uow_factory() as uow:
            gelesen = uow.intraday_bars.list_for("AAPL")
            assert [bar.start for bar in gelesen] == [bar.start for bar in bars]

    def test_zwei_aktien_teilen_sich_keinen_bestand(self, uow_factory: UowFactory) -> None:
        with uow_factory() as uow:
            uow.intraday_bars.add_all("AAPL", self._bars(5))
            uow.intraday_bars.add_all("MSFT", self._bars(2))
            uow.commit()

        with uow_factory() as uow:
            assert len(uow.intraday_bars.list_for("AAPL")) == 5
            assert len(uow.intraday_bars.list_for("MSFT")) == 2

    def test_der_zeitpunkt_ueberlebt_die_datenbank(self, uow_factory: UowFactory) -> None:
        """Naive Zeitstempel sind untersagt (Doc 10). Was hineingeht, muss
        denselben Zeitpunkt bezeichnen, wenn es herauskommt."""
        bar = make_bar(datetime(2026, 3, 10, 9, 30, tzinfo=self.NEW_YORK))
        with uow_factory() as uow:
            uow.intraday_bars.add_all("AAPL", [bar])
            uow.commit()

        with uow_factory() as uow:
            gelesen = uow.intraday_bars.list_for("AAPL")[0]
            assert gelesen.start.tzinfo is not None
            assert gelesen.start == bar.start

    def test_eine_leere_lieferung_ist_kein_fehler(self, uow_factory: UowFactory) -> None:
        """Kommt an einem Feiertag nichts zurueck, ist das der Normalfall."""
        with uow_factory() as uow:
            assert uow.intraday_bars.add_all("AAPL", []) == 0
            uow.commit()


    def test_mehr_bars_als_postgres_parameter_erlaubt(self, uow_factory: UowFactory) -> None:
        """PostgreSQL nimmt hoechstens 65.535 Parameter je Anweisung.

        Bei sieben Spalten je Bar reisst ein einzelnes Insert ab 9.363 Zeilen
        ab. Ein Jahr Fuenf-Minuten-Bars liegt darueber, ebenso der in ADR 0014
        vorgesehene Fuenf-Jahres-Batch -- der Fall ist also nicht konstruiert,
        sondern der naechste Ausbauschritt.
        """
        bars = self._bars(12_000)

        with uow_factory() as uow:
            assert uow.intraday_bars.add_all("VIELE", bars) == 12_000
            uow.commit()

        with uow_factory() as uow:
            assert len(uow.intraday_bars.list_for("VIELE")) == 12_000

    def test_auch_ueber_die_grenze_hinweg_bleibt_es_idempotent(
        self, uow_factory: UowFactory
    ) -> None:
        """Die Stueckelung darf die Eigenschaft nicht aufweichen, auf der die
        Wiederholbarkeit beruht."""
        bars = self._bars(12_000)
        with uow_factory() as uow:
            uow.intraday_bars.add_all("VIELE", bars)
            uow.commit()

        with uow_factory() as uow:
            assert uow.intraday_bars.add_all("VIELE", bars) == 0
            uow.commit()

        with uow_factory() as uow:
            assert len(uow.intraday_bars.list_for("VIELE")) == 12_000

    def test_werte_bleiben_unveraendert(self, uow_factory: UowFactory) -> None:
        bar = make_bar(datetime(2026, 3, 10, 9, 30, tzinfo=self.NEW_YORK), close=123.45)
        with uow_factory() as uow:
            uow.intraday_bars.add_all("AAPL", [bar])
            uow.commit()

        with uow_factory() as uow:
            assert uow.intraday_bars.list_for("AAPL")[0] == bar
