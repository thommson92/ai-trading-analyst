"""Bausteine fuer die Berichtstests.

Bewusst eigene Helfer statt der aus ``tests/unit/application``: Dort haengen
sie an Fake-Providern und Repositories, hier geht es um reine Domain-Werte.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from ai_trading_analyst.domain.analysis import Stock, StockScreeningOutcome
from ai_trading_analyst.domain.analysts import (
    AnalystRecommendations,
    AnalystRecommendationStatus,
    RecommendationPeriod,
)
from ai_trading_analyst.domain.backtesting import (
    BacktestConfidence,
    BacktestResult,
    HorizonMetrics,
)
from ai_trading_analyst.domain.earnings import EarningsFilterResult, EarningsFilterStatus
from ai_trading_analyst.domain.fundamentals import (
    FundamentalSnapshot,
    FundamentalStatus,
    Metric,
    MetricBasis,
    MetricName,
    MetricUnit,
    SourceRef,
)
from ai_trading_analyst.domain.research import (
    Citation,
    ResearchReport,
    ResearchStatus,
    SourceLicenseClass,
)
from ai_trading_analyst.domain.screening import (
    SIGNAL_RULE_VERSION,
    ScreeningResult,
    ScreeningStatus,
    SignalEvent,
    SignalType,
)
from ai_trading_analyst.domain.technical import (
    PriceZone,
    TechnicalSnapshot,
    TechnicalStatus,
    ZoneKind,
    ZoneStrength,
)

JETZT = datetime(2026, 8, 30, 21, 0, tzinfo=UTC)


def make_outcome(**overrides: object) -> StockScreeningOutcome:
    """Ein Kandidat ohne jedes Zusatzmodul -- der karge Ausgangsfall."""
    felder: dict[str, object] = {
        "analysis_run_id": uuid.uuid4(),
        "stock": Stock(id=uuid.uuid4(), symbol="AAPL", exchange="NASDAQ"),
        "result": ScreeningResult(
            status=ScreeningStatus.CANDIDATE,
            fired_signal_types=frozenset({SignalType.RSI_CROSS, SignalType.EMA5_EMA20_CROSS}),
            signal_events=(
                SignalEvent(signal_type=SignalType.RSI_CROSS, candle_index=9),
                SignalEvent(signal_type=SignalType.EMA5_EMA20_CROSS, candle_index=9),
            ),
        ),
        "decision_candle_index": 9,
        "evaluated_at": JETZT,
        "signal_rule_version": SIGNAL_RULE_VERSION,
    }
    felder.update(overrides)
    return StockScreeningOutcome(**felder)  # type: ignore[arg-type]


def make_analysts(
    status: AnalystRecommendationStatus = AnalystRecommendationStatus.COMPLETED,
    reason: str | None = None,
) -> AnalystRecommendations:
    """Zwei Monatsstaende mit **verschiedenen** Verteilungen.

    Verschieden, damit eine Vertauschung der Reihenfolge auffaellt: Bei zwei
    gleichen Zeilen bliebe jede Mutation an der Sortierung gruen.
    """
    if status is not AnalystRecommendationStatus.COMPLETED:
        return AnalystRecommendations(
            status=status,
            evaluated_at=JETZT,
            source="fake",
            source_url="https://example.com/fixture/analysts",
            reason=reason,
        )
    return AnalystRecommendations(
        status=status,
        evaluated_at=JETZT,
        periods=(
            RecommendationPeriod(
                period=date(2026, 8, 1), strong_buy=9, buy=7, hold=3, sell=1, strong_sell=0
            ),
            RecommendationPeriod(
                period=date(2026, 7, 1), strong_buy=4, buy=6, hold=8, sell=2, strong_sell=1
            ),
        ),
        source="fake",
        source_url="https://example.com/fixture/analysts",
        retrieved_at=JETZT,
    )


def make_earnings(status: EarningsFilterStatus, reason: str | None = None) -> EarningsFilterResult:
    return EarningsFilterResult(
        status=status,
        evaluated_at=JETZT,
        next_earnings_date=date(2026, 11, 1) if reason is None else None,
        candles_until_earnings=120,
        source="fake",
        reason=reason,
    )


def make_backtest(*, earnings_exclusion_applied: bool = False) -> BacktestResult:
    return BacktestResult(
        stock_id=uuid.uuid4(),
        # Alle drei: Die Iterationsreihenfolge dieses frozensets ist
        # nachweislich nicht die sortierte. Mit nur zweien faellt beides
        # zufaellig zusammen, und die Sortierzusicherung im Dokument koennte
        # nicht mehr scheitern.
        signal_types=frozenset(SignalType),
        signal_rule_version=SIGNAL_RULE_VERSION,
        evaluated_at=JETZT,
        history_start=datetime(2021, 8, 30, tzinfo=UTC),
        history_end=datetime(2026, 8, 30, tzinfo=UTC),
        horizons=(
            HorizonMetrics(
                horizon=5,
                raw_event_count=60,
                deduplicated_event_count=44,
                hit_rate=0.61,
                mean_return=0.012,
                median_return=0.009,
                max_loss=-0.08,
                drawdown=-0.11,
                held_above_entry_rate=0.41,
                confidence=BacktestConfidence.NORMAL,
            ),
        ),
        earnings_exclusion_applied=earnings_exclusion_applied,
    )


def make_technical(*, mit_zonen: bool = True) -> TechnicalSnapshot:
    zonen = (
        PriceZone(
            lower=180.0,
            upper=184.0,
            kind=ZoneKind.SUPPORT,
            strength=ZoneStrength.STRONG,
            touch_count=4,
            last_confirmed_at=datetime(2026, 8, 20, tzinfo=UTC),
            distance_pct=-3.2,
            pivot_count=4,
        ),
    )
    return TechnicalSnapshot(
        status=TechnicalStatus.COMPLETED,
        evaluated_at=JETZT,
        candle_timestamp=JETZT,
        close=190.0,
        zones=zonen if mit_zonen else (),
    )


def make_research(
    *,
    status: ResearchStatus = ResearchStatus.COMPLETED,
    positive: tuple[str, ...] = ("starke Nachfrage",),
    risiken: tuple[str, ...] = ("Lieferkette",),
    reason: str | None = None,
) -> ResearchReport:
    return ResearchReport(
        status=status,
        evaluated_at=JETZT,
        model="fake-model",
        prompt_version="fake-v1",
        summary="Zusammenfassung",
        positive_factors=positive,
        negative_factors=("Wettbewerb",),
        risks=risiken,
        confidence=0.72,
        citations=(
            Citation(
                url="https://example.test/a",
                title="Ein Beleg",
                retrieved_at=JETZT,
                cited_text="Zitat",
                license_class=SourceLicenseClass.UNKNOWN,
                transformation="zusammengefasst",
                source_age="3 days ago",
            ),
        ),
        reason=reason,
    )


def make_fundamentals(
    *,
    status: FundamentalStatus = FundamentalStatus.COMPLETED,
    company_name: str | None = "Apple Inc.",
    vollstaendig: bool = False,
) -> FundamentalSnapshot:
    def quelle(tag: str) -> SourceRef:
        """Dieselbe Einreichung, verschiedene Tags -- so liegt es in EDGAR
        tatsaechlich: Ein 10-K traegt Umsatz, Jahresueberschuss und Bilanz
        gemeinsam. Alle Kennzahlen mit demselben Tag zu versehen liesse eine
        Entdopplung ueber das Tag genauso aussehen wie eine ueber die
        Vorgangsnummer."""
        return SourceRef(
            cik=320193,
            accession="0000320193-25-000073",
            form="10-K",
            filed=date(2025, 11, 1),
            tag=tag,
        )

    namen = list(MetricName) if vollstaendig else [MetricName.REVENUE]
    metriken = {
        name: Metric(
            name=name,
            value=1.0,
            unit=MetricUnit.CURRENCY,
            basis=MetricBasis.TRAILING_TWELVE_MONTHS,
            period_start=date(2024, 10, 1),
            period_end=date(2025, 9, 30),
            currency="USD",
            sources=(quelle(f"Tag{name.value}"),),
            retrieved_at=JETZT,
        )
        for name in namen
    }
    return FundamentalSnapshot(
        symbol="AAPL",
        status=status,
        evaluated_at=JETZT,
        company_name=company_name,
        metrics=metriken if status is FundamentalStatus.COMPLETED else {},
        reason=None if status is FundamentalStatus.COMPLETED else "nichts rechenbar",
    )
