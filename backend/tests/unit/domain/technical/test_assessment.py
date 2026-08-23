"""Wertobjekte der KI-Einordnung (ADR 0026)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from ai_trading_analyst.domain.technical import (
    BreakoutQuality,
    FalseSignalRisk,
    MomentumState,
    RiskRewardRating,
    SwingEntryPlausibility,
    TechnicalAssessment,
    TechnicalAssessmentStatus,
    TrendStrength,
)

EVALUATED_AT = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


class TestEnumWerte:
    """Die Zeichenketten sind zugesichert, nicht beliebig.

    Sie stehen so in der Datenbank *und* im Werkzeugschema des Adapters. Eine
    stille Umbenennung macht gespeicherte Zeilen unlesbar und laesst das
    Modell einen Wert liefern, den die Domain nicht kennt -- der Test ist
    deshalb keine Tautologie, sondern ein Vertrag.
    """

    def test_trendstaerke(self) -> None:
        assert [m.value for m in TrendStrength] == ["STRONG", "MODERATE", "WEAK", "ABSENT"]

    def test_breakout_qualitaet(self) -> None:
        assert [m.value for m in BreakoutQuality] == [
            "CONFIRMED",
            "TENTATIVE",
            "FAILED",
            "NO_BREAKOUT",
        ]

    def test_momentum(self) -> None:
        assert [m.value for m in MomentumState] == ["OVERBOUGHT", "NEUTRAL", "OVERSOLD"]

    def test_fehlsignalrisiko(self) -> None:
        assert [m.value for m in FalseSignalRisk] == ["LOW", "MEDIUM", "HIGH"]

    def test_chance_risiko_einstufung(self) -> None:
        assert [m.value for m in RiskRewardRating] == [
            "FAVOURABLE",
            "BALANCED",
            "UNFAVOURABLE",
            "NOT_ASSESSABLE",
        ]

    def test_einstiegsplausibilitaet(self) -> None:
        assert [m.value for m in SwingEntryPlausibility] == [
            "PLAUSIBLE",
            "QUESTIONABLE",
            "IMPLAUSIBLE",
        ]

    def test_status(self) -> None:
        assert [m.value for m in TechnicalAssessmentStatus] == [
            "COMPLETED",
            "INSUFFICIENT_DATA",
            "UNAVAILABLE",
        ]


class TestTechnicalAssessment:
    def test_ohne_einordnung_bleiben_alle_inhaltsfelder_leer(self) -> None:
        """Ein Ausfall erzeugt keinen Ersatztext, der sich im Bericht wie
        eine Einschaetzung liest (CLAUDE.md)."""
        assessment = TechnicalAssessment(
            status=TechnicalAssessmentStatus.UNAVAILABLE,
            evaluated_at=EVALUATED_AT,
            model=None,
            prompt_version=None,
            reason="provider_error",
        )

        assert assessment.summary is None
        assert assessment.trend_strength is None
        assert assessment.breakout_quality is None
        assert assessment.momentum_state is None
        assert assessment.false_signal_risk is None
        assert assessment.risk_reward_rating is None
        assert assessment.swing_entry_plausibility is None
        assert assessment.false_signal_risks == ()
        assert assessment.confidence is None

    def test_die_eingeordnete_verfahrensversion_gehoert_ans_ergebnis(self) -> None:
        """Doc 10, Paragraph 12: nachvollziehbar, welche Daten verwendet
        wurden. Steigt das deterministische Verfahren, bleibt erkennbar, dass
        diese Einordnung die aeltere Fassung gesehen hat."""
        assessment = TechnicalAssessment(
            status=TechnicalAssessmentStatus.COMPLETED,
            evaluated_at=EVALUATED_AT,
            model="claude-haiku-4-5-20251001",
            prompt_version="technical-agent-v1",
            interpreted_analysis_version="technical-v3",
        )

        assert assessment.interpreted_analysis_version == "technical-v3"

    def test_ist_unveraenderlich(self) -> None:
        """Abgeschlossene Analysen werden nicht ueberschrieben (CLAUDE.md) --
        das faengt beim Wertobjekt an."""
        assessment = TechnicalAssessment(
            status=TechnicalAssessmentStatus.COMPLETED,
            evaluated_at=EVALUATED_AT,
            model="fixture",
            prompt_version="fixture-v1",
        )

        with pytest.raises(FrozenInstanceError):
            assessment.summary = "nachtraeglich geaendert"  # type: ignore[misc]
