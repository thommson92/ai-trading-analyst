"""Wertobjekte der Analystenempfehlungen (ADR 0043).

Reine Domain-Werte -- kein Anbieter, keine Datenbank.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from ai_trading_analyst.domain.analysts import (
    ANALYST_ANALYSIS_VERSION,
    AnalystRecommendations,
    AnalystRecommendationStatus,
    RecommendationPeriod,
)

JETZT = datetime(2026, 8, 30, 21, 0, tzinfo=UTC)


def _stand(period: date = date(2026, 8, 1), **votes: int) -> RecommendationPeriod:
    werte = {"strong_buy": 9, "buy": 7, "hold": 3, "sell": 1, "strong_sell": 0}
    werte.update(votes)
    return RecommendationPeriod(period=period, **werte)


class TestVotensumme:
    def test_alle_fuenf_klassen_zaehlen_mit(self) -> None:
        assert _stand().total == 20

    def test_ein_stand_ohne_voten_ergibt_null(self) -> None:
        """Kommt vor: Ein Anbieter kann einen Monat fuehren, in dem niemand
        votierte. Das ist eine Aussage, keine fehlende Angabe."""
        leer = _stand(strong_buy=0, buy=0, hold=0, sell=0, strong_sell=0)
        assert leer.total == 0


class TestInvariante:
    """``COMPLETED`` und Monatsstaende gehoeren zusammen -- in beide Richtungen."""

    def test_completed_ohne_monatsstaende_wird_abgewiesen(self) -> None:
        """Es waere ein Abschnitt, der im Bericht als verfuegbar gilt und eine
        leere Verteilung traegt -- "keine Meinung" statt "keine Abdeckung"."""
        with pytest.raises(ValueError, match="mindestens einen"):
            AnalystRecommendations(
                status=AnalystRecommendationStatus.COMPLETED, evaluated_at=JETZT
            )

    @pytest.mark.parametrize(
        "status",
        [AnalystRecommendationStatus.UNKNOWN, AnalystRecommendationStatus.UNAVAILABLE],
    )
    def test_monatsstaende_ohne_completed_werden_abgewiesen(
        self, status: AnalystRecommendationStatus
    ) -> None:
        """Die Gegenrichtung: Ein Ausfall mit Daten waere ein Ergebnis, das
        sich selbst widerspricht."""
        with pytest.raises(ValueError, match="darf keine"):
            AnalystRecommendations(status=status, evaluated_at=JETZT, periods=(_stand(),))

    def test_die_beiden_gueltigen_faelle_gehen_durch(self) -> None:
        vollstaendig = AnalystRecommendations(
            status=AnalystRecommendationStatus.COMPLETED,
            evaluated_at=JETZT,
            periods=(_stand(),),
        )
        ohne = AnalystRecommendations(
            status=AnalystRecommendationStatus.UNKNOWN,
            evaluated_at=JETZT,
            reason="no_coverage",
        )
        assert vollstaendig.latest is not None
        assert ohne.latest is None


class TestVoreinstellungen:
    def test_die_verfahrensversion_steht_am_ergebnis(self) -> None:
        """Doc 10, Paragraph 8: Versionierung an jedem Ergebnis."""
        ergebnis = AnalystRecommendations(
            status=AnalystRecommendationStatus.UNKNOWN, evaluated_at=JETZT
        )
        assert ergebnis.analysis_version == ANALYST_ANALYSIS_VERSION
