"""Die Zusicherungen der Wertobjekte selbst.

Klein, aber nicht beilaeufig: ``ScoreResult`` haelt die Regel, dass ein Score
ohne Zahl ``INSUFFICIENT_DATA`` heisst -- genau die Invariante, die ein
Rundlauf durch die Datenbank verletzen koennte.
"""

from __future__ import annotations

import pytest

from ai_trading_analyst.domain.scoring import (
    ComponentName,
    MetricThresholds,
    Recommendation,
    RecommendationParameters,
    ScoreComponent,
    ScoreConfidence,
    ScoreKind,
    ScoreResult,
    ScoreStatus,
    ScoringParameters,
)

KOMPONENTE = ScoreComponent(name=ComponentName.GROWTH, weight=1.0, value=5.0)
EMPFEHLUNGSREGELN = RecommendationParameters(
    strong_candidate=8.0,
    candidate=6.0,
    watch=4.0,
    investment_strong=8.0,
    investment_weak=4.0,
    cap_false_signal_high=Recommendation.WATCH,
    cap_earnings_unknown=Recommendation.CANDIDATE,
    version="1.0",
)


def ergebnis(*, status: ScoreStatus, value: float | None) -> ScoreResult:
    return ScoreResult(
        kind=ScoreKind.LONG_TERM,
        status=status,
        version="1.0",
        components=(KOMPONENTE,),
        coverage=1.0,
        confidence=ScoreConfidence.NORMAL,
        value=value,
    )


class TestStatusUndZahlPassenZusammen:
    def test_ein_score_ohne_zahl_muss_insufficient_data_sein(self) -> None:
        with pytest.raises(ValueError, match="passen nicht zusammen"):
            ergebnis(status=ScoreStatus.COMPLETED, value=None)

    def test_und_umgekehrt(self) -> None:
        """Der gefaehrlichere der beiden Faelle: eine Zahl neben
        ``INSUFFICIENT_DATA`` laese sich als Score."""
        with pytest.raises(ValueError, match="passen nicht zusammen"):
            ergebnis(status=ScoreStatus.INSUFFICIENT_DATA, value=7.0)

    @pytest.mark.parametrize(
        ("status", "value"),
        [(ScoreStatus.COMPLETED, 7.0), (ScoreStatus.INSUFFICIENT_DATA, None)],
    )
    def test_die_beiden_zulaessigen_kombinationen(
        self, status: ScoreStatus, value: float | None
    ) -> None:
        assert ergebnis(status=status, value=value).value == value


class TestParameter:
    def test_eine_normalgrenze_unter_der_untergrenze_ist_ein_fehler(self) -> None:
        """Dieselbe Regel wie in ``ScoringConfig`` -- und hier ebenfalls
        gehalten: Die Domain bekommt ihre Parameter nicht nur aus der
        YAML-Datei, sondern in Tests und kuenftig auch anderswoher."""
        with pytest.raises(ValueError, match="normal_confidence_coverage"):
            ScoringParameters(
                swing_weights={},
                long_term_weights={},
                thresholds={},
                minimum_coverage=0.9,
                normal_confidence_coverage=0.5,
                recommendation=EMPFEHLUNGSREGELN,
                swing_version="1.0",
                long_term_version="1.0",
            )

    def test_unsortierte_grenzen_sind_auch_in_der_domain_ein_fehler(self) -> None:
        with pytest.raises(ValueError, match="aufsteigen"):
            MetricThresholds(boundaries=(4.0, 3.0, 2.0, 1.0), higher_is_better=True)
