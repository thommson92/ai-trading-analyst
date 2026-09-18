"""Die Laufuebersicht -- mit dem rekonstruierten Sperrstatus (ADR 0062)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from ai_trading_analyst.application.read_run_overview import ReadRunOverviewUseCase
from ai_trading_analyst.domain.analysis import (
    AnalysisRun,
    RepeatSuppressionParameters,
    RunStatus,
    Stock,
    StockScreeningOutcome,
)
from ai_trading_analyst.domain.screening import (
    SIGNAL_RULE_VERSION,
    ScreeningResult,
    ScreeningStatus,
)
from tests.unit.application.conftest import (
    FakeAnalysisRunRepository,
    FakeProcessingErrorRepository,
    FakeScreeningResultRepository,
    FakeStockRepository,
    FakeUnitOfWork,
    InMemoryIntradayBarRepository,
)

START = datetime(2026, 9, 18, 17, 50, tzinfo=UTC)  # 13:50 New York


def lauf(started_at: datetime) -> AnalysisRun:
    return AnalysisRun(
        id=uuid.uuid4(), status=RunStatus.COMPLETED, started_at=started_at, number_of_stocks=3
    )


def ergebnis(
    run: AnalysisRun, symbol: str, status: ScreeningStatus, evaluated_at: datetime
) -> StockScreeningOutcome:
    return StockScreeningOutcome(
        analysis_run_id=run.id,
        stock=Stock(id=uuid.uuid4(), symbol=symbol, exchange="NASDAQ"),
        result=ScreeningResult(status=status),
        decision_candle_index=9,
        evaluated_at=evaluated_at,
        signal_rule_version=SIGNAL_RULE_VERSION,
    )


def aufbau() -> tuple[FakeAnalysisRunRepository, FakeScreeningResultRepository, FakeUnitOfWork]:
    runs = FakeAnalysisRunRepository()
    results = FakeScreeningResultRepository()
    uow = FakeUnitOfWork(
        FakeStockRepository(),
        InMemoryIntradayBarRepository(),
        runs,
        results,
        FakeProcessingErrorRepository(),
    )
    return runs, results, uow


class TestSperrstatus:
    def test_ein_kuerzlich_voll_analysiertes_symbol_gilt_als_gesperrt(self) -> None:
        runs, results, uow = aufbau()
        frueher = lauf(START - timedelta(days=2))
        heute = lauf(START)
        runs.add(frueher)
        runs.add(heute)
        results.add(ergebnis(frueher, "NVDA", ScreeningStatus.CANDIDATE, frueher.started_at))
        results.add(ergebnis(heute, "AAPL", ScreeningStatus.NOT_CANDIDATE, heute.started_at))

        uebersicht = ReadRunOverviewUseCase(
            lambda: uow, repeat_suppression=RepeatSuppressionParameters(window_days=7)
        ).execute(heute.id)

        assert uebersicht is not None
        assert [s.symbol for s in uebersicht.suppressed] == ["NVDA"]
        assert uebersicht.suppressed[0].blocking_run_id == frueher.id
        assert uebersicht.suppression_window_days == 7

    def test_ein_im_lauf_bewertetes_symbol_gilt_nicht_als_gesperrt(self) -> None:
        """Wer im Lauf eine Zeile hat, wurde bewertet -- auch wenn er im
        Fenster Kandidat war (z. B. Sperre damals aus)."""
        runs, results, uow = aufbau()
        frueher = lauf(START - timedelta(days=2))
        heute = lauf(START)
        runs.add(frueher)
        runs.add(heute)
        results.add(ergebnis(frueher, "NVDA", ScreeningStatus.CANDIDATE, frueher.started_at))
        results.add(ergebnis(heute, "NVDA", ScreeningStatus.CANDIDATE, heute.started_at))

        uebersicht = ReadRunOverviewUseCase(
            lambda: uow, repeat_suppression=RepeatSuppressionParameters(window_days=7)
        ).execute(heute.id)

        assert uebersicht is not None
        assert uebersicht.suppressed == ()

    def test_der_laufende_tag_sperrt_nicht(self) -> None:
        runs, results, uow = aufbau()
        vorhin = lauf(START - timedelta(hours=1))
        heute = lauf(START)
        runs.add(vorhin)
        runs.add(heute)
        results.add(ergebnis(vorhin, "NVDA", ScreeningStatus.CANDIDATE, vorhin.started_at))

        uebersicht = ReadRunOverviewUseCase(
            lambda: uow, repeat_suppression=RepeatSuppressionParameters(window_days=7)
        ).execute(heute.id)

        assert uebersicht is not None
        assert uebersicht.suppressed == ()

    def test_ohne_parameter_wird_nicht_gerechnet(self) -> None:
        """Leer, weil nicht gerechnet -- und das Fensterfeld sagt es."""
        runs, _, uow = aufbau()
        heute = lauf(START)
        runs.add(heute)

        uebersicht = ReadRunOverviewUseCase(lambda: uow).execute(heute.id)

        assert uebersicht is not None
        assert uebersicht.suppressed == ()
        assert uebersicht.suppression_window_days is None

    def test_ein_unbekannter_lauf_ist_none(self) -> None:
        _, _, uow = aufbau()
        assert ReadRunOverviewUseCase(lambda: uow).execute(uuid.uuid4()) is None
