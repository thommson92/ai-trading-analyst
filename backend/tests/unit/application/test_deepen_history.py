"""Der Tiefen-Backfill (ADR 0028).

Geprueft wird, was den stundenlangen Lauf betriebstauglich macht: dass er
beim aeltesten gespeicherten Bar ansetzt, dass ein zweiter Lauf nichts mehr
holt, dass ein Ausfall den Lauf nicht beendet -- und vor allem, dass eine
Aktie, die das Ziel nicht erreicht, auch nicht so aussieht.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from ai_trading_analyst.application.deepen_history import (
    DeepenHistoryUseCase,
    DeepenOutcome,
    erforderliche_fenster,
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

JETZT = datetime(2026, 8, 23, 20, 0, tzinfo=UTC)
AAPL = ContractSpec(symbol="AAPL")
MSFT = ContractSpec(symbol="MSFT")


def bar(start: datetime) -> IntradayBar:
    return IntradayBar(start=start, open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0)


class FensterQuelle:
    """Ein Anbieter mit einer Historie fester Tiefe.

    Ein Fenster von ``days`` Handelstagen deckt hier bewusst mehr
    Kalendertage ab -- genau der gemessene Befund aus ADR 0028. Waere das
    Doppel naiv in Kalendertagen gerechnet, uebersaehe der Test die Stelle,
    an der sich der Zielabgleich entscheidet.
    """

    KALENDERTAGE_JE_HANDELSTAG = 1.45

    def __init__(self, depth_days: int, now: datetime = JETZT) -> None:
        self._earliest = now - timedelta(days=depth_days)
        self._now = now
        self.calls: list[tuple[str, datetime | None, int]] = []

    def fetch_window(
        self, contract: ContractSpec, end: datetime | None, days: int
    ) -> Sequence[IntradayBar]:
        self.calls.append((contract.symbol, end, days))
        oberer_rand = end if end is not None else self._now
        spanne = timedelta(days=days * self.KALENDERTAGE_JE_HANDELSTAG)
        unterer_rand = max(oberer_rand - spanne, self._earliest)
        if unterer_rand >= oberer_rand:
            return ()
        return (bar(unterer_rand), bar(oberer_rand - timedelta(minutes=15)))

    def close(self) -> None:
        pass


@pytest.fixture
def uow_factory() -> tuple[object, InMemoryIntradayBarRepository]:
    bars = InMemoryIntradayBarRepository()

    def factory() -> FakeUnitOfWork:
        return FakeUnitOfWork(
            stocks=FakeStockRepository(),
            analysis_runs=FakeAnalysisRunRepository(),
            screening_results=FakeScreeningResultRepository(),
            processing_errors=FakeProcessingErrorRepository(),
            intraday_bars=bars,
        )

    return factory, bars


class TestFensterzahl:
    """Wieviele Anfragen eine Aktie kostet -- in Handelstagen gerechnet."""

    def test_fuenf_jahre_brauchen_fuenf_fenster(self) -> None:
        """5 * 252 = 1260 Handelstage, / 365 = 3,45 -> aufgerundet 4.

        Dazu das Sicherheitsfenster: Feiertage und der Rundungsrest zwischen
        Kalender- und Handelstagen gingen sonst zu Lasten des fuenften
        Jahres.
        """
        assert erforderliche_fenster(5) == 5

    def test_ein_jahr_braucht_zwei(self) -> None:
        assert erforderliche_fenster(1) == 2

    def test_in_kalendertagen_gerechnet_waere_es_zu_wenig(self) -> None:
        """Die Probe auf den Befund aus ADR 0028.

        Wer 5 * 365 Kalendertage durch eine Fenstergroesse von 365 teilt,
        kaeme auf fuenf Fenster und haette scheinbar dasselbe Ergebnis --
        aber aus dem falschen Grund. Bei einer anderen Fenstergroesse faellt
        der Unterschied auseinander.
        """
        assert erforderliche_fenster(5, window_trading_days=100) == 14
        # In Kalendertagen waeren es (5*365)/100 = 19 Fenster gewesen.

    def test_null_jahre_sind_kein_ziel(self) -> None:
        with pytest.raises(ValueError, match="mindestens 1"):
            erforderliche_fenster(0)


class TestTiefenBackfill:
    def _use_case(
        self, quelle: object, factory: object, jahre: int = 5, **kwargs: int
    ) -> DeepenHistoryUseCase:
        return DeepenHistoryUseCase(
            quelle,  # type: ignore[arg-type]
            factory,  # type: ignore[arg-type]
            target_years=jahre,
            now=lambda: JETZT,
            **kwargs,
        )

    def test_ein_leerer_bestand_wird_bis_zum_ziel_gefuellt(
        self, uow_factory: tuple[object, InMemoryIntradayBarRepository]
    ) -> None:
        factory, bars = uow_factory
        quelle = FensterQuelle(depth_days=6360)  # 17,4 Jahre wie gemessen

        bericht = self._use_case(quelle, factory).execute((AAPL,))

        (ergebnis,) = bericht.results
        assert ergebnis.outcome is DeepenOutcome.TARGET_REACHED
        assert ergebnis.earliest_after is not None
        assert ergebnis.earliest_after <= JETZT - timedelta(days=5 * 365)
        assert ergebnis.stored_bars > 0
        assert len(bars.list_for("AAPL")) == ergebnis.stored_bars

    def test_der_erste_abruf_beginnt_bei_jetzt(
        self, uow_factory: tuple[object, InMemoryIntradayBarRepository]
    ) -> None:
        """Ohne Bestand gibt es keinen Ansatzpunkt in der Vergangenheit."""
        factory, _ = uow_factory
        quelle = FensterQuelle(depth_days=6360)

        self._use_case(quelle, factory).execute((AAPL,))

        assert quelle.calls[0][1] is None

    def test_ein_vorhandener_bestand_wird_nicht_erneut_geholt(
        self, uow_factory: tuple[object, InMemoryIntradayBarRepository]
    ) -> None:
        """Angesetzt wird am **aeltesten** Bar, nicht am juengsten.

        Sonst holte der Lauf die schon vorhandenen Jahre ein zweites Mal --
        bei 190 Symbolen Stunden fuer nichts.
        """
        factory, bars = uow_factory
        vorhanden = JETZT - timedelta(days=300)
        bars.add_all("AAPL", [bar(vorhanden), bar(JETZT - timedelta(days=1))])
        quelle = FensterQuelle(depth_days=6360)

        ergebnis = self._use_case(quelle, factory).execute((AAPL,)).results[0]

        assert ergebnis.earliest_before == vorhanden
        assert quelle.calls[0][1] == vorhanden

    def test_ein_tiefer_bestand_kostet_keine_einzige_anfrage(
        self, uow_factory: tuple[object, InMemoryIntradayBarRepository]
    ) -> None:
        """Der Fall beim zweiten Lauf -- der Grund, warum Wiederholen nichts kostet."""
        factory, bars = uow_factory
        bars.add_all("AAPL", [bar(JETZT - timedelta(days=6 * 365))])
        quelle = FensterQuelle(depth_days=6360)

        ergebnis = self._use_case(quelle, factory).execute((AAPL,)).results[0]

        assert ergebnis.outcome is DeepenOutcome.ALREADY_DEEP_ENOUGH
        assert quelle.calls == []
        assert ergebnis.short_of_target is False

    def test_jedes_fenster_wird_sofort_abgelegt(
        self, uow_factory: tuple[object, InMemoryIntradayBarRepository]
    ) -> None:
        """Sonst waere ein Abbruch nach vier Stunden ein Totalverlust."""
        factory, bars = uow_factory
        gesehen: list[int] = []

        class ZaehlendeQuelle(FensterQuelle):
            def fetch_window(
                self, contract: ContractSpec, end: datetime | None, days: int
            ) -> Sequence[IntradayBar]:
                gesehen.append(len(bars.list_for("AAPL")))
                return super().fetch_window(contract, end, days)

        self._use_case(ZaehlendeQuelle(depth_days=6360), factory).execute((AAPL,))

        # Vor dem zweiten Abruf liegt bereits etwas im Bestand.
        assert gesehen[0] == 0
        assert gesehen[1] > 0

    def test_eine_kurze_boersenhistorie_ist_kein_fehler(
        self, uow_factory: tuple[object, InMemoryIntradayBarRepository]
    ) -> None:
        """Eine Neuemission hat keine fuenf Jahre -- das ist kein Ausfall,
        aber auch kein erreichtes Ziel."""
        factory, _ = uow_factory
        quelle = FensterQuelle(depth_days=400)

        ergebnis = self._use_case(quelle, factory).execute((AAPL,)).results[0]

        assert ergebnis.outcome is DeepenOutcome.PROVIDER_EXHAUSTED
        assert ergebnis.failed is False
        assert ergebnis.short_of_target is True

    def test_die_reissleine_gilt_je_aktie(
        self, uow_factory: tuple[object, InMemoryIntradayBarRepository]
    ) -> None:
        factory, _ = uow_factory

        class Endlos:
            def fetch_window(
                self, contract: ContractSpec, end: datetime | None, days: int
            ) -> Sequence[IntradayBar]:
                rand = end if end is not None else JETZT
                return (bar(rand - timedelta(days=1)), bar(rand))

            def close(self) -> None:
                pass

        ergebnis = (
            self._use_case(Endlos(), factory, maximum_windows=3).execute((AAPL,)).results[0]
        )

        assert ergebnis.outcome is DeepenOutcome.WINDOW_LIMIT
        assert ergebnis.windows == 3
        assert ergebnis.short_of_target is True

    def test_ein_ausfall_beendet_den_lauf_nicht(
        self, uow_factory: tuple[object, InMemoryIntradayBarRepository]
    ) -> None:
        factory, _ = uow_factory

        class NurAaplFaellt(FensterQuelle):
            def fetch_window(
                self, contract: ContractSpec, end: datetime | None, days: int
            ) -> Sequence[IntradayBar]:
                if contract.symbol == "AAPL":
                    raise MarketDataProviderError("TWS weg")
                return super().fetch_window(contract, end, days)

        bericht = self._use_case(NurAaplFaellt(depth_days=6360), factory).execute((AAPL, MSFT))

        gescheitert, durchgelaufen = bericht.results
        assert gescheitert.outcome is DeepenOutcome.ERROR
        assert gescheitert.error is not None and "TWS weg" in gescheitert.error
        assert durchgelaufen.outcome is DeepenOutcome.TARGET_REACHED
        assert bericht.failures == (gescheitert,)

    def test_auch_ein_fehler_beim_speichern_isoliert(
        self, uow_factory: tuple[object, InMemoryIntradayBarRepository]
    ) -> None:
        """Nicht nur die TWS ist eine Systemgrenze."""

        class KaputteAblage(FakeUnitOfWork):
            def commit(self) -> None:
                raise RuntimeError("Verbindung zur Datenbank abgerissen")

        def factory() -> KaputteAblage:
            return KaputteAblage(
                stocks=FakeStockRepository(),
                analysis_runs=FakeAnalysisRunRepository(),
                screening_results=FakeScreeningResultRepository(),
                processing_errors=FakeProcessingErrorRepository(),
                intraday_bars=InMemoryIntradayBarRepository(),
            )

        bericht = self._use_case(FensterQuelle(depth_days=6360), factory).execute((AAPL,))

        assert bericht.results[0].outcome is DeepenOutcome.ERROR
        assert len(bericht.failures) == 1

    def test_der_bericht_trennt_erreicht_von_zu_kurz(
        self, uow_factory: tuple[object, InMemoryIntradayBarRepository]
    ) -> None:
        factory, _ = uow_factory

        class ZweiTiefen(FensterQuelle):
            def fetch_window(
                self, contract: ContractSpec, end: datetime | None, days: int
            ) -> Sequence[IntradayBar]:
                tiefe = 6360 if contract.symbol == "AAPL" else 400
                return FensterQuelle(depth_days=tiefe).fetch_window(contract, end, days)

        bericht = self._use_case(ZweiTiefen(depth_days=0), factory).execute((AAPL, MSFT))

        assert [item.symbol for item in bericht.short_of_target] == ["MSFT"]
        assert bericht.target_years == 5
