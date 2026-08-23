"""Dauerhaft nutzbarer Testprovider fuer den Technical Agent (ADR 0026).

Muster ``FixtureResearchProvider``: symbolunabhaengig dieselbe
deterministische Einordnung. Damit laufen Start und Tests ohne
``ATA_LLM_API_KEY``, und ``technical_agent.provider`` bleibt ausgeliefert auf
``fixture``.

Die Einordnung ist bewusst nichtssagend und immer gleich -- sie soll die
Verdrahtung pruefbar machen, nicht ein Modell nachahmen. Nur die Regel, die
den Agenten von einem freien Textgenerator unterscheidet, gilt auch hier: Bei
einem Snapshot ohne ``COMPLETED`` gibt es nichts einzuordnen.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from ai_trading_analyst.domain.analysis import Stock, TechnicalInterpreter
from ai_trading_analyst.domain.technical import (
    BreakoutQuality,
    FalseSignalRisk,
    MomentumState,
    RiskRewardRating,
    SwingEntryPlausibility,
    TechnicalAssessment,
    TechnicalAssessmentStatus,
    TechnicalSnapshot,
    TechnicalStatus,
    TrendStrength,
)

_MODEL = "fixture"
_PROMPT_VERSION = "fixture-v1"


class FixtureTechnicalInterpreter(TechnicalInterpreter):
    """Implementiert ``TechnicalInterpreter`` ohne Anbieteranfrage."""

    def __init__(self, now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._now = now

    def interpret(self, stock: Stock, snapshot: TechnicalSnapshot) -> TechnicalAssessment:
        evaluated_at = self._now()
        if snapshot.status is not TechnicalStatus.COMPLETED:
            return TechnicalAssessment(
                status=TechnicalAssessmentStatus.INSUFFICIENT_DATA,
                evaluated_at=evaluated_at,
                model=None,
                prompt_version=None,
                interpreted_analysis_version=snapshot.analysis_version,
                reason="snapshot_insufficient",
            )
        return TechnicalAssessment(
            status=TechnicalAssessmentStatus.COMPLETED,
            evaluated_at=evaluated_at,
            model=_MODEL,
            prompt_version=_PROMPT_VERSION,
            interpreted_analysis_version=snapshot.analysis_version,
            summary=(f"Fixture-Einordnung fuer {stock.symbol} -- keine echte Modellanfrage."),
            trend_strength=TrendStrength.MODERATE,
            breakout_quality=BreakoutQuality.NO_BREAKOUT,
            momentum_state=MomentumState.NEUTRAL,
            false_signal_risk=FalseSignalRisk.MEDIUM,
            # Auch der Fixture-Anbieter haelt sich an die Regel, dass ohne
            # berechnetes Verhaeltnis keine Einstufung moeglich ist -- sonst
            # liefe ein Test gegen ihn gruen, den der echte Adapter nicht
            # bestuende.
            risk_reward_rating=(
                RiskRewardRating.NOT_ASSESSABLE
                if snapshot.chance_risk_ratio is None
                else RiskRewardRating.BALANCED
            ),
            swing_entry_plausibility=SwingEntryPlausibility.QUESTIONABLE,
            false_signal_risks=("Beispielhaftes Fehlsignalrisiko",),
            confidence=0.5,
        )
