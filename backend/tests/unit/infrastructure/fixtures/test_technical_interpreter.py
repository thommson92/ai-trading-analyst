"""Fixture-Anbieter des Technical Agent (ADR 0026)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ai_trading_analyst.domain.analysis import Stock
from ai_trading_analyst.domain.technical import (
    RiskRewardRating,
    TechnicalAssessmentStatus,
    TechnicalSnapshot,
    TechnicalStatus,
)
from ai_trading_analyst.infrastructure.fixtures.technical_interpreter import (
    FixtureTechnicalInterpreter,
)

EVALUATED_AT = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
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


def _interpreter() -> FixtureTechnicalInterpreter:
    return FixtureTechnicalInterpreter(now=lambda: EVALUATED_AT)


def test_liefert_eine_vollstaendige_einordnung() -> None:
    assessment = _interpreter().interpret(STOCK, _snapshot())

    assert assessment.status is TechnicalAssessmentStatus.COMPLETED
    assert assessment.model == "fixture"
    assert assessment.prompt_version == "fixture-v1"
    assert "AAPL" in (assessment.summary or "")
    assert assessment.trend_strength is not None
    assert assessment.swing_entry_plausibility is not None


def test_unvollstaendiger_snapshot_wird_nicht_eingeordnet() -> None:
    """Es gaebe nichts einzuordnen -- und der echte Adapter darf dafuer erst
    recht keinen kostenpflichtigen Aufruf ausloesen."""
    assessment = _interpreter().interpret(
        STOCK, _snapshot(status=TechnicalStatus.INSUFFICIENT_DATA, close=None)
    )

    assert assessment.status is TechnicalAssessmentStatus.INSUFFICIENT_DATA
    assert assessment.reason == "snapshot_insufficient"
    assert assessment.model is None
    assert assessment.trend_strength is None


def test_ohne_berechnetes_verhaeltnis_gibt_es_keine_einstufung() -> None:
    """Dieselbe Regel wie im echten Adapter: Was nicht berechnet wurde, wird
    nicht eingestuft (CLAUDE.md)."""
    assessment = _interpreter().interpret(STOCK, _snapshot(chance_risk_ratio=None))

    assert assessment.risk_reward_rating is RiskRewardRating.NOT_ASSESSABLE


def test_die_eingeordnete_verfahrensversion_wird_uebernommen() -> None:
    assessment = _interpreter().interpret(STOCK, _snapshot())

    assert assessment.interpreted_analysis_version == _snapshot().analysis_version
