"""Der Investment-Score aus den Fundamentalkennzahlen (ADR 0041, ADR 0045).

Gerechnet wird gegen die **ausgelieferten** Schwellen aus
``config/default.yaml``. Erfundene Testschwellen prueften eine Abbildung,
die es nicht gibt -- und sie wuerden nicht merken, wenn in der echten Datei
eine Kennzahl ohne Schwelle bliebe.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime

import pytest

from ai_trading_analyst.domain.fundamentals import (
    FundamentalSnapshot,
    FundamentalStatus,
    Metric,
    MetricBasis,
    MetricName,
    MetricUnit,
    SourceRef,
)
from ai_trading_analyst.domain.scoring import (
    KENNZAHLEN_JE_KOMPONENTE,
    SCORED_METRICS,
    ComponentName,
    ScoreKind,
    ScoreStatus,
    ScoringParameters,
    compute_long_term_score,
)
from ai_trading_analyst.domain.scoring.long_term import mindestbesetzung

JETZT = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
QUELLE = SourceRef(
    cik=320193, accession="0000320193-25-000073", form="10-K", filed=date(2025, 11, 1), tag="Tag"
)


def snapshot(
    werte: Mapping[MetricName, float],
    *,
    status: FundamentalStatus = FundamentalStatus.COMPLETED,
) -> FundamentalSnapshot:
    return FundamentalSnapshot(
        symbol="AAPL",
        status=status,
        evaluated_at=JETZT,
        metrics={
            name: Metric(
                name=name,
                value=wert,
                unit=MetricUnit.RATIO,
                basis=MetricBasis.POINT_IN_TIME,
                period_end=date(2025, 9, 30),
                sources=(QUELLE,),
                retrieved_at=JETZT,
            )
            for name, wert in werte.items()
        },
        reason=None if status is FundamentalStatus.COMPLETED else "nichts rechenbar",
    )


SPITZENWERTE: dict[MetricName, float] = {
    MetricName.GROSS_MARGIN: 0.80,
    MetricName.OPERATING_MARGIN: 0.40,
    MetricName.NET_MARGIN: 0.35,
    MetricName.FREE_CASH_FLOW_MARGIN: 0.35,
    MetricName.RETURN_ON_EQUITY: 0.50,
    MetricName.RETURN_ON_ASSETS: 0.20,
    MetricName.REVENUE_GROWTH: 0.20,
    MetricName.NET_INCOME_GROWTH: 0.40,
    MetricName.PRICE_EARNINGS_RATIO: 10.0,
    MetricName.PRICE_SALES_RATIO: 1.0,
    MetricName.PRICE_FREE_CASH_FLOW_RATIO: 10.0,
    MetricName.DEBT_TO_EQUITY: 0.3,
    MetricName.CURRENT_RATIO: 3.0,
    MetricName.SHARE_COUNT_GROWTH: -0.05,
}
"""Ein Titel im obersten Fuenftel jeder einzelnen Kennzahl."""


class TestVollstaendigeGrundlage:
    def test_der_beste_titel_bekommt_zehn(self, scoring_params: ScoringParameters) -> None:
        ergebnis = compute_long_term_score(snapshot(SPITZENWERTE), parameters=scoring_params)
        assert ergebnis.kind is ScoreKind.LONG_TERM
        assert ergebnis.status is ScoreStatus.COMPLETED
        assert ergebnis.value == 10.0
        assert ergebnis.coverage == 1.0

    def test_die_richtung_gilt_je_kennzahl(self, scoring_params: ScoringParameters) -> None:
        """Ein sehr teurer Titel bekommt in der Bewertung das unterste
        Fuenftel -- **obwohl** die Zahl gross ist. Ohne die Umkehrung waere
        ein KGV von 200 die beste Bewertung der Liste."""
        teuer = dict(SPITZENWERTE)
        teuer[MetricName.PRICE_EARNINGS_RATIO] = 200.0
        teuer[MetricName.PRICE_SALES_RATIO] = 30.0
        teuer[MetricName.PRICE_FREE_CASH_FLOW_RATIO] = 200.0

        ergebnis = compute_long_term_score(snapshot(teuer), parameters=scoring_params)

        (bewertung,) = [k for k in ergebnis.components if k.name is ComponentName.VALUATION]
        assert bewertung.value == 2.0

    def test_die_niveaugroessen_tragen_keinen_teilwert(
        self, scoring_params: ScoringParameters
    ) -> None:
        """Umsatz, Jahresueberschuss, freier Cashflow und
        Marktkapitalisierung sind Kontext (Doc 09): Ohne Vergleichsgruppe ist
        "zehn Milliarden Umsatz" weder gut noch schlecht."""
        nur_niveau = {
            MetricName.REVENUE: 1e11,
            MetricName.NET_INCOME: 1e10,
            MetricName.FREE_CASH_FLOW: 1e10,
            MetricName.MARKET_CAPITALIZATION: 1e12,
        }
        ergebnis = compute_long_term_score(snapshot(nur_niveau), parameters=scoring_params)
        assert ergebnis.status is ScoreStatus.INSUFFICIENT_DATA
        assert ergebnis.coverage == 0.0


class TestMindestbesetzung:
    def test_die_haelfte_aufgerundet(self) -> None:
        assert mindestbesetzung(KENNZAHLEN_JE_KOMPONENTE[ComponentName.PROFITABILITY]) == 3
        assert mindestbesetzung(KENNZAHLEN_JE_KOMPONENTE[ComponentName.GROWTH]) == 1
        assert mindestbesetzung(KENNZAHLEN_JE_KOMPONENTE[ComponentName.VALUATION]) == 2
        assert mindestbesetzung(KENNZAHLEN_JE_KOMPONENTE[ComponentName.BALANCE_SHEET_QUALITY]) == 2

    def test_drei_von_sechs_margen_reichen_fuer_die_profitabilitaet(
        self, scoring_params: ScoringParameters
    ) -> None:
        """Der Fall aus ADR 0045: Banken, Versicherer und Versorger haben
        keine Bruttomarge."""
        werte = {
            MetricName.NET_MARGIN: 0.35,
            MetricName.RETURN_ON_EQUITY: 0.50,
            MetricName.RETURN_ON_ASSETS: 0.20,
        }
        ergebnis = compute_long_term_score(snapshot(werte), parameters=scoring_params)
        (profitabilitaet,) = [
            k for k in ergebnis.components if k.name is ComponentName.PROFITABILITY
        ]
        assert profitabilitaet.value == 10.0
        assert "3 von 6" in (profitabilitaet.reason or "")

    def test_zwei_von_sechs_reichen_nicht(self, scoring_params: ScoringParameters) -> None:
        werte = {MetricName.NET_MARGIN: 0.35, MetricName.RETURN_ON_EQUITY: 0.50}
        ergebnis = compute_long_term_score(snapshot(werte), parameters=scoring_params)
        (profitabilitaet,) = [
            k for k in ergebnis.components if k.name is ComponentName.PROFITABILITY
        ]
        assert profitabilitaet.value is None
        assert "noetig sind 3" in (profitabilitaet.reason or "")

    def test_gemittelt_wird_ueber_die_vorhandenen(
        self, scoring_params: ScoringParameters
    ) -> None:
        """Eine fehlende Kennzahl senkt den Teilwert nicht -- sie wird
        uebersprungen (ADR 0045, Entscheidung 3)."""
        werte = {
            MetricName.NET_MARGIN: 0.35,  # 10
            MetricName.RETURN_ON_EQUITY: 0.50,  # 10
            MetricName.RETURN_ON_ASSETS: 0.001,  # 2
        }
        ergebnis = compute_long_term_score(snapshot(werte), parameters=scoring_params)
        (profitabilitaet,) = [
            k for k in ergebnis.components if k.name is ComponentName.PROFITABILITY
        ]
        assert profitabilitaet.value == pytest.approx(7.3)


class TestOhneGrundlage:
    def test_ohne_snapshot_entsteht_kein_score(self, scoring_params: ScoringParameters) -> None:
        """Ein ausgefallenes EDGAR ist ein normaler Betriebszustand (ADR
        0035) und kein Programmfehler."""
        ergebnis = compute_long_term_score(None, parameters=scoring_params)
        assert ergebnis.status is ScoreStatus.INSUFFICIENT_DATA
        assert ergebnis.value is None
        assert len(ergebnis.missing_components) == 4

    def test_der_grund_des_snapshots_steht_an_den_komponenten(
        self, scoring_params: ScoringParameters
    ) -> None:
        ergebnis = compute_long_term_score(
            snapshot({}, status=FundamentalStatus.INSUFFICIENT_DATA), parameters=scoring_params
        )
        assert all("nichts rechenbar" in (k.reason or "") for k in ergebnis.components)


class TestZuordnung:
    def test_jede_bewertete_kennzahl_gehoert_zu_genau_einer_komponente(self) -> None:
        gezaehlt = [
            name for kennzahlen in KENNZAHLEN_JE_KOMPONENTE.values() for name in kennzahlen
        ]
        assert len(gezaehlt) == len(set(gezaehlt)) == len(SCORED_METRICS) == 14

    def test_die_ausgelieferte_konfiguration_fuehrt_jede_davon(
        self, scoring_params: ScoringParameters
    ) -> None:
        assert SCORED_METRICS <= scoring_params.thresholds.keys()
