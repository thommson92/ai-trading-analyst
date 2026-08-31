"""Die Empfehlungsstufe (Berichtspunkt 16; ADR 0046).

Drei Schritte in fester Reihenfolge: Grundstufe aus dem Swing-Score,
Korrektur durch den Investment-Score, dann die Deckelung. Die Reihenfolge ist
die eigentliche Zusicherung -- stuende die Deckelung vor der Korrektur, hoebe
ein guter Investment-Score die Stufe wieder ueber die Grenze, die ein hohes
Fehlsignalrisiko gerade gezogen hat.
"""

from __future__ import annotations

import pytest

from ai_trading_analyst.domain.earnings import EarningsFilterStatus
from ai_trading_analyst.domain.scoring import (
    ComponentName,
    Recommendation,
    ScoreComponent,
    ScoreConfidence,
    ScoreKind,
    ScoreResult,
    ScoreStatus,
    ScoringParameters,
    derive_recommendation,
)
from ai_trading_analyst.domain.technical import FalseSignalRisk


def score(wert: float | None, *, kind: ScoreKind = ScoreKind.SWING) -> ScoreResult:
    vollstaendig = wert is not None
    return ScoreResult(
        kind=kind,
        status=ScoreStatus.COMPLETED if vollstaendig else ScoreStatus.INSUFFICIENT_DATA,
        version="1.0",
        components=(
            ScoreComponent(
                name=ComponentName.TECHNICAL_SIGNALS,
                weight=1.0,
                value=wert,
                effective_weight=1.0 if vollstaendig else 0.0,
            ),
        ),
        coverage=1.0 if vollstaendig else 0.0,
        confidence=ScoreConfidence.NORMAL if vollstaendig else ScoreConfidence.INSUFFICIENT_DATA,
        value=wert,
    )


def stufe(
    params: ScoringParameters,
    swing: float | None = 7.0,
    investment: float | None = 6.0,
    *,
    swing_fehlt: bool = False,
    investment_fehlt: bool = False,
    risiko: FalseSignalRisk | None = None,
    earnings: EarningsFilterStatus | None = EarningsFilterStatus.EARNINGS_CLEAR,
) -> Recommendation:
    ergebnis = derive_recommendation(
        swing=None if swing_fehlt else score(swing),
        investment=None if investment_fehlt else score(investment, kind=ScoreKind.LONG_TERM),
        false_signal_risk=risiko,
        earnings_status=earnings,
        parameters=params,
    )
    return ergebnis.level


class TestGrundstufe:
    @pytest.mark.parametrize(
        ("swing", "erwartet"),
        [
            (9.0, Recommendation.STRONG_CANDIDATE),
            (8.0, Recommendation.STRONG_CANDIDATE),
            (7.0, Recommendation.CANDIDATE),
            (6.0, Recommendation.CANDIDATE),
            (5.0, Recommendation.WATCH),
            (4.0, Recommendation.WATCH),
            (3.0, Recommendation.AVOID_FOR_NOW),
        ],
    )
    def test_jede_stufe_wird_erreicht(
        self, scoring_params: ScoringParameters, swing: float, erwartet: Recommendation
    ) -> None:
        """Die Grenzen liegen auf der Skala, aus der der Score gebaut ist --
        ein Wert **auf** der Grenze gehoert in die hoehere Stufe."""
        assert stufe(scoring_params, swing=swing) is erwartet


class TestOhneSwingScore:
    def test_ohne_swing_score_gibt_es_keine_stufe(
        self, scoring_params: ScoringParameters
    ) -> None:
        assert stufe(scoring_params, swing_fehlt=True) is Recommendation.INSUFFICIENT_DATA

    def test_ein_swing_score_mit_insufficient_data_ebenfalls(
        self, scoring_params: ScoringParameters
    ) -> None:
        assert stufe(scoring_params, swing=None) is Recommendation.INSUFFICIENT_DATA

    def test_insufficient_data_schlaegt_einen_starken_investment_score(
        self, scoring_params: ScoringParameters
    ) -> None:
        """Absorbierend: Ohne Aussage ueber den Einstieg hilft das beste
        Unternehmen nichts -- der Lauf sucht Einstiege."""
        assert stufe(scoring_params, swing=None, investment=10.0) is (
            Recommendation.INSUFFICIENT_DATA
        )

    def test_der_grund_steht_am_ergebnis(self, scoring_params: ScoringParameters) -> None:
        ergebnis = derive_recommendation(
            swing=None,
            investment=score(9.0, kind=ScoreKind.LONG_TERM),
            false_signal_risk=None,
            earnings_status=None,
            parameters=scoring_params,
        )
        assert ergebnis.reasons
        assert "Swing-Score" in ergebnis.reasons[0]


class TestKorrekturDurchDenInvestmentScore:
    def test_ein_starker_investment_score_hebt_um_eine_stufe(
        self, scoring_params: ScoringParameters
    ) -> None:
        assert stufe(scoring_params, swing=7.0, investment=6.0) is Recommendation.CANDIDATE
        assert stufe(scoring_params, swing=7.0, investment=9.0) is (
            Recommendation.STRONG_CANDIDATE
        )

    def test_ein_schwacher_senkt_um_eine_stufe(self, scoring_params: ScoringParameters) -> None:
        assert stufe(scoring_params, swing=7.0, investment=3.0) is Recommendation.WATCH

    def test_er_hebt_nur_um_eine_und_nicht_weiter(
        self, scoring_params: ScoringParameters
    ) -> None:
        """Sonst waere er die fuehrende Groesse und nicht die korrigierende."""
        assert stufe(scoring_params, swing=5.0, investment=10.0) is Recommendation.CANDIDATE

    def test_ueber_der_hoechsten_stufe_geht_es_nicht_weiter(
        self, scoring_params: ScoringParameters
    ) -> None:
        assert stufe(scoring_params, swing=9.0, investment=10.0) is (
            Recommendation.STRONG_CANDIDATE
        )

    def test_unter_der_niedrigsten_ebenfalls(self, scoring_params: ScoringParameters) -> None:
        assert stufe(scoring_params, swing=1.0, investment=1.0) is Recommendation.AVOID_FOR_NOW

    def test_ein_fehlender_investment_score_senkt_nicht(
        self, scoring_params: ScoringParameters
    ) -> None:
        """Fehlende Daten bestrafen nicht (CLAUDE.md). Ein Titel ohne
        SEC-Zahlen ist kein schlechter Titel."""
        assert stufe(scoring_params, swing=7.0, investment_fehlt=True) is (
            Recommendation.CANDIDATE
        )
        assert stufe(scoring_params, swing=7.0, investment=None) is Recommendation.CANDIDATE

    def test_ein_mittlerer_investment_score_veraendert_nichts(
        self, scoring_params: ScoringParameters
    ) -> None:
        assert stufe(scoring_params, swing=7.0, investment=6.0) is Recommendation.CANDIDATE


class TestBegrenzendeRisiken:
    def test_hohes_fehlsignalrisiko_deckelt_auf_watch(
        self, scoring_params: ScoringParameters
    ) -> None:
        """Der ganze Lauf steht auf dem Signal. Haelt die Einordnung es fuer
        unzuverlaessig, ist mehr als Beobachten nicht zu rechtfertigen."""
        assert stufe(scoring_params, swing=9.0, risiko=FalseSignalRisk.HIGH) is (
            Recommendation.WATCH
        )

    def test_mittleres_risiko_deckelt_nicht(self, scoring_params: ScoringParameters) -> None:
        assert stufe(scoring_params, swing=9.0, risiko=FalseSignalRisk.MEDIUM) is (
            Recommendation.STRONG_CANDIDATE
        )

    def test_ein_unbekannter_berichtstermin_schliesst_die_hoechste_stufe_aus(
        self, scoring_params: ScoringParameters
    ) -> None:
        assert stufe(scoring_params, swing=9.0, earnings=EarningsFilterStatus.UNKNOWN) is (
            Recommendation.CANDIDATE
        )

    def test_die_deckelung_kommt_nach_der_korrektur(
        self, scoring_params: ScoringParameters
    ) -> None:
        """Der eigentliche Befund: Ein starker Investment-Score darf die
        Deckelung nicht wieder aufheben."""
        assert stufe(
            scoring_params, swing=7.0, investment=10.0, risiko=FalseSignalRisk.HIGH
        ) is Recommendation.WATCH

    def test_eine_deckelung_hebt_nie_an(self, scoring_params: ScoringParameters) -> None:
        """``AVOID_FOR_NOW`` bleibt, wo es ist -- die Obergrenze ``WATCH``
        ist eine Obergrenze und keine Zuweisung."""
        assert stufe(scoring_params, swing=1.0, risiko=FalseSignalRisk.HIGH) is (
            Recommendation.AVOID_FOR_NOW
        )

    def test_beide_deckelungen_zusammen_ergeben_die_niedrigere(
        self, scoring_params: ScoringParameters
    ) -> None:
        assert stufe(
            scoring_params,
            swing=9.0,
            risiko=FalseSignalRisk.HIGH,
            earnings=EarningsFilterStatus.UNKNOWN,
        ) is Recommendation.WATCH

    def test_nur_wirksame_deckelungen_werden_ausgewiesen(
        self, scoring_params: ScoringParameters
    ) -> None:
        """Ein Risiko, das die Stufe nicht veraendert hat, laese eine
        unveraenderte Stufe wie eine gedeckelte aussehen."""
        ergebnis = derive_recommendation(
            swing=score(3.0),
            investment=score(5.0, kind=ScoreKind.LONG_TERM),
            false_signal_risk=FalseSignalRisk.HIGH,
            earnings_status=EarningsFilterStatus.EARNINGS_CLEAR,
            parameters=scoring_params,
        )
        assert ergebnis.level is Recommendation.AVOID_FOR_NOW
        assert ergebnis.applied_caps == ()


class TestHerleitung:
    def test_jeder_schritt_steht_am_ergebnis(self, scoring_params: ScoringParameters) -> None:
        """Doc 10, Paragraph 12: Fuer jede Empfehlung muss nachvollziehbar
        sein, worauf sie beruht."""
        ergebnis = derive_recommendation(
            swing=score(9.0),
            investment=score(2.0, kind=ScoreKind.LONG_TERM),
            false_signal_risk=FalseSignalRisk.HIGH,
            earnings_status=EarningsFilterStatus.EARNINGS_CLEAR,
            parameters=scoring_params,
        )
        gesamt = " | ".join(ergebnis.reasons)
        assert "Swing-Score 9.0" in gesamt
        assert "Investment-Score 2.0" in gesamt
        assert "Fehlsignalrisiko" in gesamt
        assert ergebnis.level is Recommendation.WATCH

    def test_die_version_kommt_aus_den_parametern(
        self, scoring_params: ScoringParameters
    ) -> None:
        ergebnis = derive_recommendation(
            swing=score(7.0),
            investment=None,
            false_signal_risk=None,
            earnings_status=None,
            parameters=scoring_params,
        )
        assert ergebnis.version == scoring_params.recommendation.version
