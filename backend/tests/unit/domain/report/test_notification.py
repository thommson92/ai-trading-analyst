"""Die Kurzfassung sagt, ob sich der Blick lohnt -- mehr nicht (ADR 0040).

Die entscheidenden Zusicherungen sind die **negativen**: Was nicht in der
Meldung stehen darf, steht dort auch nicht. Sie verlaesst das eigene Netz.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ai_trading_analyst.domain.analysis import (
    AnalysisRun,
    AnalysisRunSummary,
    RunStatus,
    StockScreeningOutcome,
)
from ai_trading_analyst.domain.earnings import EarningsFilterStatus
from ai_trading_analyst.domain.report import render_notification
from ai_trading_analyst.domain.screening import ScreeningResult, ScreeningStatus
from ai_trading_analyst.domain.technical import (
    FalseSignalRisk,
    TechnicalAssessment,
    TechnicalAssessmentStatus,
)
from tests.unit.domain.report.conftest import (
    JETZT,
    make_earnings,
    make_fundamentals,
    make_outcome,
    make_research,
    make_technical,
)


def zusammenfassung(
    *outcomes: StockScreeningOutcome, aktien: int = 4
) -> AnalysisRunSummary:
    kandidaten = sum(
        outcome.result.status is ScreeningStatus.CANDIDATE for outcome in outcomes
    )
    run = AnalysisRun(
        id=uuid.UUID("11111111-2222-3333-4444-555555555555"),
        status=RunStatus.COMPLETED,
        started_at=datetime(2026, 8, 30, 21, 15, tzinfo=UTC),
        number_of_stocks=aktien,
        candidates_found=kandidaten,
    )
    return AnalysisRunSummary(run=run, outcomes=tuple(outcomes), errors=())


def einordnung(risiko: FalseSignalRisk) -> TechnicalAssessment:
    return TechnicalAssessment(
        status=TechnicalAssessmentStatus.COMPLETED,
        evaluated_at=JETZT,
        model="fake",
        prompt_version="fake-v1",
        interpreted_analysis_version="technical-v3",
        summary="Einordnung",
        false_signal_risk=risiko,
        false_signal_risks=("Ein Freitext-Risiko, das nirgends auftauchen darf",),
        confidence=0.6,
    )


class TestWasDrinSteht:
    def test_betreff_nennt_tag_und_anzahl(self) -> None:
        betreff, _ = render_notification(zusammenfassung(make_outcome()))
        assert betreff == "Analyse-Lauf 2026-08-30: 1 Kandidat(en)"

    def test_jede_zeile_nennt_symbol_und_signaltypen(self) -> None:
        _, text = render_notification(zusammenfassung(make_outcome()))
        assert "AAPL  EMA5_EMA20_CROSS + RSI_CROSS" in text

    def test_das_fehlsignalrisiko_erscheint_als_stufe(self) -> None:
        _, text = render_notification(
            zusammenfassung(make_outcome(technical_assessment=einordnung(FalseSignalRisk.HIGH)))
        )
        assert "Fehlsignalrisiko HIGH" in text

    def test_ein_unbekannter_earnings_termin_wird_genannt(self) -> None:
        """Doc 10, Paragraph 6.5: ein Datenrisiko, das ausdruecklich
        gekennzeichnet wird."""
        _, text = render_notification(
            zusammenfassung(make_outcome(earnings=make_earnings(EarningsFilterStatus.UNKNOWN, "x")))
        )
        assert "Earnings-Termin unbekannt" in text

    def test_der_verweis_auf_den_vollen_bericht_nennt_die_lauf_id(self) -> None:
        _, text = render_notification(zusammenfassung(make_outcome()))
        assert "cli report --run 11111111-2222-3333-4444-555555555555" in text


class TestWasDraussenBleibt:
    """Die eigentliche Zusicherung von ADR 0040."""

    def test_kein_kurs_und_keine_kennzahl(self) -> None:
        _, text = render_notification(
            zusammenfassung(
                make_outcome(
                    technical=make_technical(),
                    fundamentals=make_fundamentals(vollstaendig=True),
                )
            )
        )
        assert "190.0" not in text, "der Schlusskurs steht in der Meldung"
        assert "REVENUE" not in text
        assert "Apple Inc." not in text

    def test_kein_freitext_aus_recherche_oder_einordnung(self) -> None:
        _, text = render_notification(
            zusammenfassung(
                make_outcome(
                    research=make_research(),
                    technical_assessment=einordnung(FalseSignalRisk.LOW),
                )
            )
        )
        assert "Zusammenfassung" not in text
        assert "Lieferkette" not in text
        assert "Freitext-Risiko" not in text


class TestOhneKandidaten:
    def test_ein_leerer_lauf_meldet_die_zahl_der_geprueften_aktien(self) -> None:
        nicht_kandidat = make_outcome(result=ScreeningResult(status=ScreeningStatus.NOT_CANDIDATE))
        betreff, text = render_notification(zusammenfassung(nicht_kandidat, aktien=192))

        assert betreff == "Analyse-Lauf 2026-08-30: 0 Kandidat(en)"
        assert "192 Aktien" in text
        assert "AAPL" not in text
