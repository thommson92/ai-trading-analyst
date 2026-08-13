"""Der historische Backfill.

Geprueft wird das, was den Job betriebstauglich macht: dass er nur die
Luecke anfragt, dass ein Ausfall bei einer Aktie den Lauf nicht beendet, und
dass ein zweiter Lauf nichts doppelt schreibt.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from ai_trading_analyst.application.backfill_history import (
    BackfillHistoryUseCase,
    SymbolBackfill,
    missing_days,
)
from ai_trading_analyst.domain.analysis import ContractSpec, MarketDataProviderError
from ai_trading_analyst.domain.screening import IntradayBar
from tests.unit.application.conftest import (
    FakeAnalysisRunRepository,
    FakeProcessingErrorRepository,
    FakeScreeningResultRepository,
    FakeStockRepository,
    FakeUnitOfWork,
    InMemoryIntradayBarRepository,
)

JETZT = datetime(2026, 8, 13, 22, 0, tzinfo=UTC)
WATCHLIST = (ContractSpec(symbol="AAPL"), ContractSpec(symbol="MSFT"))


def bar(start: datetime) -> IntradayBar:
    return IntradayBar(start=start, open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0)


class FakeBarSource:
    """Merkt sich, mit welchem Zeitraum gefragt wurde -- genau darum geht es."""

    def __init__(
        self,
        bars: dict[str, Sequence[IntradayBar]] | None = None,
        errors: dict[str, str] | None = None,
    ) -> None:
        self._bars = bars or {}
        self._errors = errors or {}
        self.calls: list[tuple[str, int | None]] = []

    def fetch_intraday_bars(
        self, contract: ContractSpec, days: int | None = None
    ) -> Sequence[IntradayBar]:
        self.calls.append((contract.symbol, days))
        if contract.symbol in self._errors:
            raise MarketDataProviderError(self._errors[contract.symbol])
        return self._bars.get(contract.symbol, ())

    def close(self) -> None:
        pass


def build(
    bar_source: FakeBarSource,
) -> tuple[BackfillHistoryUseCase, InMemoryIntradayBarRepository]:
    bars_repo = InMemoryIntradayBarRepository()

    def uow_factory() -> FakeUnitOfWork:
        return FakeUnitOfWork(
            FakeStockRepository(),
            bars_repo,
            FakeAnalysisRunRepository(),
            FakeScreeningResultRepository(),
            FakeProcessingErrorRepository(),
        )

    return BackfillHistoryUseCase(bar_source, uow_factory, now=lambda: JETZT), bars_repo


class TestFehlenderZeitraum:
    """Die Rechnung, die entscheidet, wie viel geholt wird."""

    def test_ohne_bestand_gilt_der_standardzeitraum(self) -> None:
        assert missing_days(None, JETZT) is None

    def test_ein_taeglicher_lauf_fragt_einen_tag_plus_ueberlappung(self) -> None:
        assert missing_days(JETZT - timedelta(days=1), JETZT) == 2

    def test_nach_einem_wochenende_wird_das_wochenende_nachgeholt(self) -> None:
        """Der Fall aus ADR 0018: Sonntagsneustart, Start am Montag."""
        assert missing_days(JETZT - timedelta(days=3), JETZT) == 4

    def test_nach_einem_laengeren_ausfall_entsprechend_mehr(self) -> None:
        assert missing_days(JETZT - timedelta(days=21), JETZT) == 22

    def test_kurz_nach_dem_letzten_bar_wird_mindestens_ein_tag_geholt(self) -> None:
        """Sonst zoege ein Lauf am selben Tag die laufende Sitzung nicht nach."""
        assert missing_days(JETZT - timedelta(hours=2), JETZT) == 1


class TestAbruf:
    def test_beim_ersten_lauf_wird_der_standardzeitraum_angefragt(self) -> None:
        quelle = FakeBarSource()
        use_case, _ = build(quelle)

        use_case.execute(WATCHLIST)

        assert quelle.calls == [("AAPL", None), ("MSFT", None)]

    def test_beim_zweiten_lauf_nur_noch_die_luecke(self) -> None:
        bars = [bar(JETZT - timedelta(days=2))]
        quelle = FakeBarSource({"AAPL": bars})
        use_case, _ = build(quelle)

        use_case.execute((ContractSpec(symbol="AAPL"),))
        use_case.execute((ContractSpec(symbol="AAPL"),))

        assert quelle.calls == [("AAPL", None), ("AAPL", 3)]

    def test_gelieferte_bars_landen_im_bestand(self) -> None:
        bars = [bar(JETZT - timedelta(days=1)), bar(JETZT - timedelta(hours=1))]
        use_case, bestand = build(FakeBarSource({"AAPL": bars}))

        bericht = use_case.execute((ContractSpec(symbol="AAPL"),))

        assert bericht.stored_bars == 2
        assert len(bestand.list_for("AAPL")) == 2

    def test_ein_zweiter_lauf_schreibt_nichts_doppelt(self) -> None:
        """Die Eigenschaft, die den Job wiederholbar macht."""
        bars = [bar(JETZT - timedelta(days=1))]
        use_case, bestand = build(FakeBarSource({"AAPL": bars}))

        use_case.execute((ContractSpec(symbol="AAPL"),))
        zweiter = use_case.execute((ContractSpec(symbol="AAPL"),))

        assert zweiter.stored_bars == 0
        assert len(bestand.list_for("AAPL")) == 1

    def test_eine_leere_antwort_ist_kein_fehler(self) -> None:
        """An einem Feiertag kommt nichts zurueck -- das ist der Normalfall."""
        use_case, _ = build(FakeBarSource({"AAPL": ()}))

        bericht = use_case.execute((ContractSpec(symbol="AAPL"),))

        assert bericht.failures == ()
        assert bericht.stored_bars == 0


class TestFehlerisolation:
    def test_ein_ausfall_beendet_den_lauf_nicht(self) -> None:
        """Bei 200 Symbolen waere ein Abbruch beim ersten die schlechteste
        aller Antworten."""
        quelle = FakeBarSource(
            bars={"MSFT": [bar(JETZT)]}, errors={"AAPL": "Keine Verbindung zur TWS"}
        )
        use_case, bestand = build(quelle)

        bericht = use_case.execute(WATCHLIST)

        assert [ergebnis.symbol for ergebnis in bericht.failures] == ["AAPL"]
        assert len(bestand.list_for("MSFT")) == 1

    def test_der_fehler_wird_im_bericht_benannt(self) -> None:
        use_case, _ = build(FakeBarSource(errors={"AAPL": "Keine Verbindung zur TWS"}))

        bericht = use_case.execute((ContractSpec(symbol="AAPL"),))

        assert bericht.failures[0].error == "Keine Verbindung zur TWS"
        assert bericht.failures[0].failed

    def test_eine_gescheiterte_aktie_bleibt_beim_naechsten_lauf_beim_standardzeitraum(
        self,
    ) -> None:
        """Sie hat nichts im Bestand -- der naechste Lauf muss wieder alles
        anfragen, nicht nur einen Tag."""
        quelle = FakeBarSource(errors={"AAPL": "Keine Verbindung zur TWS"})
        use_case, _ = build(quelle)

        use_case.execute((ContractSpec(symbol="AAPL"),))
        use_case.execute((ContractSpec(symbol="AAPL"),))

        assert quelle.calls == [("AAPL", None), ("AAPL", None)]


class TestFortschritt:
    def test_der_fortschritt_wird_je_aktie_gemeldet(self) -> None:
        """Ein Lauf ueber 200 Symbole dauert eine Stunde -- ohne Rueckmeldung
        waere nicht erkennbar, ob er haengt."""
        meldungen: list[tuple[int, int, str]] = []
        use_case, _ = build(FakeBarSource())

        use_case.execute(
            WATCHLIST,
            on_progress=lambda index, total, ergebnis: meldungen.append(
                (index, total, ergebnis.symbol)
            ),
        )

        assert meldungen == [(1, 2, "AAPL"), (2, 2, "MSFT")]


class TestBericht:
    def test_leere_watchlist_ergibt_einen_leeren_bericht(self) -> None:
        use_case, _ = build(FakeBarSource())
        bericht = use_case.execute(())
        assert bericht.results == ()
        assert bericht.stored_bars == 0


@pytest.mark.parametrize(
    ("empfangen", "gespeichert"),
    [(3, 3), (0, 0)],
)
def test_der_bericht_unterscheidet_empfangen_von_gespeichert(
    empfangen: int, gespeichert: int
) -> None:
    """Beim zweiten Lauf werden Bars empfangen, aber keine gespeichert --
    beides zu sehen macht den Unterschied zwischen 'nichts Neues' und
    'nichts bekommen'."""
    ergebnis = SymbolBackfill(
        symbol="AAPL", requested_days=2, received_bars=empfangen, stored_bars=gespeichert
    )
    assert ergebnis.received_bars == empfangen
    assert ergebnis.stored_bars == gespeichert
    assert not ergebnis.failed
