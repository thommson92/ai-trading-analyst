"""Die Barquelle, die aus dem eigenen Bestand liest.

Sie ist der Grund, warum der Screener nach dem Backfill ohne TWS auskommt --
und warum zwei Laeufe desselben Tages dasselbe Ergebnis liefern.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import OperationalError

from ai_trading_analyst.domain.analysis import (
    ContractSpec,
    IntradayBarRepository,
    MarketDataProviderError,
)
from ai_trading_analyst.domain.screening import IntradayBar
from ai_trading_analyst.infrastructure.persistence.stored_bar_source import StoredBarSource
from tests.unit.application.conftest import (
    FakeAnalysisRunRepository,
    FakeProcessingErrorRepository,
    FakeScreeningResultRepository,
    FakeStockRepository,
    FakeUnitOfWork,
    InMemoryIntradayBarRepository,
)

BEGINN = datetime(2026, 3, 10, 9, 30, tzinfo=UTC)


def bar(offset_minutes: int) -> IntradayBar:
    return IntradayBar(
        start=BEGINN + timedelta(minutes=offset_minutes),
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
        volume=1.0,
    )


def quelle_ueber(bestand: IntradayBarRepository) -> StoredBarSource:
    """Je Abruf eine eigene Arbeitseinheit -- wie im Betrieb."""

    def uow_factory() -> FakeUnitOfWork:
        return FakeUnitOfWork(
            FakeStockRepository(),
            bestand,
            FakeAnalysisRunRepository(),
            FakeScreeningResultRepository(),
            FakeProcessingErrorRepository(),
        )

    return StoredBarSource(uow_factory)


def quelle_mit(*bars: IntradayBar) -> StoredBarSource:
    bestand = InMemoryIntradayBarRepository()
    bestand.add_all("AAPL", list(bars))
    return quelle_ueber(bestand)


class TestLesen:
    def test_gespeicherte_bars_kommen_zurueck(self) -> None:
        quelle = quelle_mit(bar(0), bar(15))
        assert len(quelle.fetch_intraday_bars(ContractSpec(symbol="AAPL"))) == 2

    def test_der_zeitraum_wird_bewusst_ignoriert(self) -> None:
        """Der Bestand ist der Bestand. Ihn hier zu beschneiden waere eine
        zweite, stille Stelle, an der ueber den Betrachtungszeitraum
        entschieden wird."""
        quelle = quelle_mit(bar(0), bar(15), bar(30))
        assert len(quelle.fetch_intraday_bars(ContractSpec(symbol="AAPL"), days=1)) == 3

    def test_eine_andere_aktie_bekommt_nichts(self) -> None:
        quelle = quelle_mit(bar(0))
        with pytest.raises(MarketDataProviderError):
            quelle.fetch_intraday_bars(ContractSpec(symbol="MSFT"))


class TestLeererBestand:
    def test_ohne_bars_verweist_die_meldung_auf_den_backfill(self) -> None:
        """Sonst lautete die Meldung 'keine abgeschlossene Kerze' -- richtig,
        aber irrefuehrend: Es fehlt nicht die Kerze, es fehlt der Backfill."""
        quelle = quelle_ueber(InMemoryIntradayBarRepository())
        with pytest.raises(MarketDataProviderError, match="Backfill"):
            quelle.fetch_intraday_bars(ContractSpec(symbol="AAPL"))


class TestDatenbankfehler:
    """Ein Datenbankproblem ist ein Problem *dieser* Aktie, nicht des Laufs.

    Ohne die Uebersetzung liefe ein ``SQLAlchemyError`` durch die
    Fehlerbehandlung des Screenings hindurch -- sie faengt
    ``MarketDataProviderError`` -- und riss den gesamten Lauf mitsamt aller
    bis dahin geprueften Aktien ab. Der Live-Pfad hat dieses Loch nicht.
    """

    class AbgerisseneVerbindung:
        def latest_start(self, symbol: str) -> datetime | None:
            return None

        def latest_start_overall(self) -> datetime | None:
            return None

        def add_all(self, symbol: str, bars: object) -> int:
            return 0

        def list_for(self, symbol: str) -> list[IntradayBar]:
            raise OperationalError("SELECT intraday_bars", {}, Exception("server closed"))

    def test_ein_datenbankfehler_kommt_als_anbieterfehler_an(self) -> None:
        quelle = quelle_ueber(self.AbgerisseneVerbindung())

        with pytest.raises(MarketDataProviderError, match="nicht lesbar"):
            quelle.fetch_intraday_bars(ContractSpec(symbol="AAPL"))

    def test_die_meldung_nennt_die_betroffene_aktie(self) -> None:
        quelle = quelle_ueber(self.AbgerisseneVerbindung())

        with pytest.raises(MarketDataProviderError, match="AAPL"):
            quelle.fetch_intraday_bars(ContractSpec(symbol="AAPL"))


class TestVerbindungsfreigabe:
    def test_close_ist_folgenlos_und_mehrfach_aufrufbar(self) -> None:
        quelle = quelle_ueber(InMemoryIntradayBarRepository())
        quelle.close()
        quelle.close()
