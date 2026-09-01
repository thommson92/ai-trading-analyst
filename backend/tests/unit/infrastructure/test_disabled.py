"""Bewusst abgeschaltete Agenten (``provider: none``).

Der Unterschied zur Fixture ist der Pruefgegenstand: Die Fixture simuliert
einen funktionierenden Anbieter mit vollstaendig aussehenden Ergebnissen --
``none`` liefert die ehrliche Luecke (``UNAVAILABLE``, Grund
``provider_disabled``), die Score, Bericht und Meldung bereits richtig
behandeln.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ai_trading_analyst.domain.analysis import Stock
from ai_trading_analyst.domain.research import ResearchStatus
from ai_trading_analyst.domain.technical import (
    TechnicalAssessmentStatus,
    TechnicalSnapshot,
    TechnicalStatus,
)
from ai_trading_analyst.infrastructure.disabled import (
    REASON_DISABLED,
    DisabledResearchProvider,
    DisabledTechnicalInterpreter,
)

EVALUATED_AT = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
STOCK = Stock(id=uuid.uuid4(), symbol="AAPL", exchange="NASDAQ")


def _snapshot(**overrides: object) -> TechnicalSnapshot:
    felder: dict[str, object] = {
        "status": TechnicalStatus.COMPLETED,
        "evaluated_at": EVALUATED_AT,
        "close": 100.0,
        "chance_risk_ratio": 2.0,
    }
    felder.update(overrides)
    return TechnicalSnapshot(**felder)  # type: ignore[arg-type]


class TestDisabledResearchProvider:
    def test_liefert_unavailable_mit_grund_und_ohne_inhalte(self) -> None:
        report = DisabledResearchProvider(now=lambda: EVALUATED_AT).research(STOCK)

        assert report.status is ResearchStatus.UNAVAILABLE
        assert report.reason == REASON_DISABLED
        assert report.evaluated_at == EVALUATED_AT
        assert report.model is None
        assert report.prompt_version is None
        assert report.summary is None
        assert report.positive_factors == ()
        assert report.citations == ()
        assert report.coverage is None
        assert report.evidence is None


class TestDisabledTechnicalInterpreter:
    def test_liefert_unavailable_mit_grund_und_snapshot_version(self) -> None:
        assessment = DisabledTechnicalInterpreter(now=lambda: EVALUATED_AT).interpret(
            STOCK, _snapshot()
        )

        assert assessment.status is TechnicalAssessmentStatus.UNAVAILABLE
        assert assessment.reason == REASON_DISABLED
        assert assessment.evaluated_at == EVALUATED_AT
        assert assessment.model is None
        assert assessment.prompt_version is None
        assert assessment.interpreted_analysis_version == _snapshot().analysis_version
        assert assessment.trend_strength is None
        assert assessment.risk_reward_rating is None

    def test_auch_ein_unvollstaendiger_snapshot_ergibt_unavailable(self) -> None:
        """Bewusst KEIN ``snapshot_insufficient`` (anders als Fixture und
        echter Adapter): Die Luecke kommt vom Betreiber, nicht von den Daten
        -- die Port-Regel verhindert nur den vergeblichen Anbieteraufruf, den
        es hier nicht gibt."""
        assessment = DisabledTechnicalInterpreter(now=lambda: EVALUATED_AT).interpret(
            STOCK, _snapshot(status=TechnicalStatus.INSUFFICIENT_DATA, close=None)
        )

        assert assessment.status is TechnicalAssessmentStatus.UNAVAILABLE
        assert assessment.reason == REASON_DISABLED
