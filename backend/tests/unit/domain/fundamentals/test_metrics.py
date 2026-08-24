"""Die Kennzahlenrechnung (ADR 0032).

Geprueft wird vor allem, was **nicht** entsteht: Die Regeln dieses Moduls
sind fast alle Verbote -- kein Ersatzwert, keine Kennzahl aus zwei Jahren,
keine Wachstumsrate ohne positiven Ausgangswert.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from ai_trading_analyst.domain.fundamentals import (
    FigureName,
    FundamentalParameters,
    FundamentalSnapshot,
    FundamentalStatus,
    Metric,
    MetricName,
    MetricUnit,
    ReportedFigure,
    SourceRef,
    compound_annual_growth,
    compute_fundamental_snapshot,
)

JETZT = datetime(2026, 8, 24, tzinfo=UTC)


def _quelle(jahr: int, *, accession: str = "0000000000-00-000000", tag: str = "T") -> SourceRef:
    return SourceRef(
        cik=1, accession=accession, form="10-K", filed=date(jahr + 1, 2, 1), tag=tag
    )


def _figure(
    wert: float,
    jahr: int,
    *,
    instant: bool = False,
    accession: str = "0000000000-00-000000",
    unit: str = "USD",
) -> ReportedFigure:
    return ReportedFigure(
        value=wert,
        period_start=None if instant else date(jahr, 1, 1),
        period_end=date(jahr, 12, 31),
        unit=unit,
        source=_quelle(jahr, accession=accession),
    )


def _reihe(werte: dict[int, float], **kwargs: object) -> tuple[ReportedFigure, ...]:
    return tuple(_figure(wert, jahr, **kwargs) for jahr, wert in sorted(werte.items()))  # type: ignore[arg-type]


def _snapshot(
    figures: dict[FigureName, tuple[ReportedFigure, ...]], **kwargs: object
) -> FundamentalSnapshot:
    return compute_fundamental_snapshot(
        symbol="TEST",
        figures=figures,
        retrieved_at=JETZT,
        evaluated_at=JETZT,
        **kwargs,  # type: ignore[arg-type]
    )


class TestWachstumsrate:
    def test_eine_verdopplung_in_drei_jahren(self) -> None:
        assert compound_annual_growth(100.0, 200.0, 3) == pytest.approx(0.259921, abs=1e-6)

    def test_ohne_positiven_ausgangswert_gibt_es_keine_rate(self) -> None:
        """Ein Verlust, der sich halbiert, waere als 'minus 50 Prozent
        Wachstum' das Gegenteil dessen, was passiert ist."""
        assert compound_annual_growth(-100.0, -50.0, 3) is None
        assert compound_annual_growth(0.0, 50.0, 3) is None

    def test_aus_gewinn_wurde_verlust(self) -> None:
        assert compound_annual_growth(100.0, -20.0, 3) is None


class TestFehlendeGroessen:
    def test_ohne_umsatz_gibt_es_nichts_zu_rechnen(self) -> None:
        snapshot = _snapshot({FigureName.NET_INCOME: _reihe({2025: 10.0})})
        assert snapshot.status is FundamentalStatus.INSUFFICIENT_DATA
        assert snapshot.reason is not None
        assert not snapshot.metrics

    def test_eine_fehlende_rohgroesse_laesst_die_kennzahl_fehlen(self) -> None:
        """Kein Ersatzwert und keine Null -- die Kennzahl taucht in
        ``missing_metrics`` auf, nicht mit dem Wert 0 in der Liste."""
        snapshot = _snapshot({FigureName.REVENUE: _reihe({2025: 1000.0})})
        assert MetricName.GROSS_MARGIN not in snapshot.metrics
        assert MetricName.GROSS_MARGIN in snapshot.missing_metrics

    def test_eine_kennzahl_entsteht_nie_aus_zwei_geschaeftsjahren(self) -> None:
        """Der Gewinn stammt aus 2024, der Umsatz aus 2025. Eine Marge
        daraus saehe plausibel aus und waere falsch."""
        snapshot = _snapshot(
            {
                FigureName.REVENUE: _reihe({2025: 1000.0}),
                FigureName.NET_INCOME: _reihe({2024: 100.0}),
            }
        )
        assert MetricName.NET_MARGIN not in snapshot.metrics


class TestVerhaeltnisse:
    def test_die_marge_wird_aus_demselben_jahr_gebildet(self) -> None:
        snapshot = _snapshot(
            {
                FigureName.REVENUE: _reihe({2025: 1000.0}),
                FigureName.NET_INCOME: _reihe({2025: 250.0}),
            }
        )
        assert snapshot.metrics[MetricName.NET_MARGIN].value == pytest.approx(0.25)
        assert snapshot.metrics[MetricName.NET_MARGIN].unit is MetricUnit.FRACTION

    def test_bei_negativem_eigenkapital_gibt_es_keine_eigenkapitalrendite(self) -> None:
        """Sie drehte das Vorzeichen und behauptete damit das Gegenteil der
        Lage: ein Gewinn bei negativem Eigenkapital saehe aus wie ein
        Verlust."""
        snapshot = _snapshot(
            {
                FigureName.REVENUE: _reihe({2025: 1000.0}),
                FigureName.NET_INCOME: _reihe({2025: 100.0}),
                FigureName.EQUITY: _reihe({2025: -500.0}, instant=True),
            }
        )
        assert MetricName.RETURN_ON_EQUITY not in snapshot.metrics

    def test_der_freie_cashflow_zieht_die_investitionen_ab(self) -> None:
        """Sie stehen in XBRL als Auszahlung, also positiv. Ein
        Vorzeichenfehler verdoppelte den Wert, statt ihn zu halbieren."""
        snapshot = _snapshot(
            {
                FigureName.REVENUE: _reihe({2025: 1000.0}),
                FigureName.OPERATING_CASH_FLOW: _reihe({2025: 300.0}),
                FigureName.CAPITAL_EXPENDITURE: _reihe({2025: 100.0}),
            }
        )
        assert snapshot.metrics[MetricName.FREE_CASH_FLOW].value == pytest.approx(200.0)


class TestWachstumUeberDieVolleSpanne:
    def test_die_spanne_wird_vollstaendig_verlangt(self) -> None:
        """Zwei Jahre Historie ergeben keine Dreijahresrate -- lieber keine
        Kennzahl als eine, die eine andere Spanne meint, als sie behauptet."""
        snapshot = _snapshot({FigureName.REVENUE: _reihe({2024: 900.0, 2025: 1000.0})})
        assert MetricName.REVENUE_GROWTH not in snapshot.metrics

    def test_eine_luecke_in_der_mitte_verhindert_die_rate(self) -> None:
        """Vier Werte liegen vor, aber 2023 fehlt: Der viertletzte Stichtag
        ist 2021, die Spanne waere vier Jahre statt drei."""
        snapshot = _snapshot(
            {FigureName.REVENUE: _reihe({2021: 800.0, 2022: 900.0, 2024: 950.0, 2025: 1000.0})}
        )
        assert MetricName.REVENUE_GROWTH not in snapshot.metrics

    def test_die_volle_spanne_ergibt_die_rate(self) -> None:
        snapshot = _snapshot(
            {FigureName.REVENUE: _reihe({2022: 1000.0, 2023: 1.0, 2024: 1.0, 2025: 2000.0})},
            parameters=FundamentalParameters(growth_years=3),
        )
        assert snapshot.metrics[MetricName.REVENUE_GROWTH].value == pytest.approx(
            0.259921, abs=1e-6
        )


class TestVerwaesserung:
    """Die Aktienzahl wird nur innerhalb einer Einreichung verglichen.

    Der Grund ist gemessen: Netflix' 10-K von 2011 nennt 63 Millionen
    Aktien, das von 2017 nennt 431 Millionen. Dazwischen liegen Splits.
    """

    def test_zahlen_aus_verschiedenen_einreichungen_werden_nicht_verglichen(self) -> None:
        figures = {
            FigureName.REVENUE: _reihe({2025: 1000.0}),
            FigureName.DILUTED_SHARES: (
                _figure(10e6, 2022, accession="alt", unit="shares"),
                _figure(100e6, 2025, accession="neu", unit="shares"),
            ),
        }
        snapshot = _snapshot(figures)
        assert MetricName.SHARE_COUNT_GROWTH not in snapshot.metrics

    def test_innerhalb_einer_einreichung_wird_verglichen(self) -> None:
        figures = {
            FigureName.REVENUE: _reihe({2025: 1000.0}),
            FigureName.DILUTED_SHARES: (
                _figure(100e6, 2023, accession="eins", unit="shares"),
                _figure(98e6, 2024, accession="eins", unit="shares"),
                _figure(96e6, 2025, accession="eins", unit="shares"),
            ),
        }
        metric = _snapshot(figures).metrics[MetricName.SHARE_COUNT_GROWTH]
        assert metric.value < 0
        assert metric.period_end == date(2025, 12, 31)

    def test_die_juengste_einreichung_gewinnt(self) -> None:
        figures = {
            FigureName.REVENUE: _reihe({2025: 1000.0}),
            FigureName.DILUTED_SHARES: (
                _figure(50e6, 2020, accession="alt", unit="shares"),
                _figure(49e6, 2021, accession="alt", unit="shares"),
                _figure(100e6, 2024, accession="neu", unit="shares"),
                _figure(99e6, 2025, accession="neu", unit="shares"),
            ),
        }
        metric = _snapshot(figures).metrics[MetricName.SHARE_COUNT_GROWTH]
        assert metric.period_end == date(2025, 12, 31)
        assert metric.sources[0].accession == "neu"


class TestKursAlsOptionaleEingabe:
    """ADR 0032, Entscheidung 4 -- die zweite gerichtete Kopplung."""

    def _basis(self) -> dict[FigureName, tuple[ReportedFigure, ...]]:
        return {
            FigureName.REVENUE: _reihe({2025: 1000.0}),
            FigureName.NET_INCOME: _reihe({2025: 100.0}),
        }

    def test_ohne_kurs_fehlen_genau_die_vier_bewertungskennzahlen(self) -> None:
        snapshot = _snapshot(self._basis())
        assert snapshot.price_used is None
        assert MetricName.PRICE_EARNINGS_RATIO in snapshot.missing_metrics
        assert MetricName.NET_MARGIN in snapshot.metrics

    def test_ohne_aktienzahl_gibt_es_keine_bewertung(self) -> None:
        snapshot = _snapshot(self._basis(), price=50.0)
        assert MetricName.MARKET_CAPITALIZATION not in snapshot.metrics

    def test_mit_kurs_und_aktienzahl_entsteht_das_kgv(self) -> None:
        snapshot = _snapshot(
            self._basis(),
            price=50.0,
            shares_outstanding=_figure(10.0, 2025, instant=True, unit="shares"),
        )
        assert snapshot.metrics[MetricName.MARKET_CAPITALIZATION].value == pytest.approx(500.0)
        assert snapshot.metrics[MetricName.PRICE_EARNINGS_RATIO].value == pytest.approx(5.0)
        assert snapshot.price_used == 50.0

    def test_bei_verlust_gibt_es_kein_kgv(self) -> None:
        """Es waere negativ und wuechse mit dem Verlust -- es saehe aus wie
        eine guenstige Bewertung."""
        figures = self._basis() | {FigureName.NET_INCOME: _reihe({2025: -100.0})}
        snapshot = _snapshot(
            figures, price=50.0, shares_outstanding=_figure(10.0, 2025, instant=True, unit="shares")
        )
        assert MetricName.PRICE_EARNINGS_RATIO not in snapshot.metrics
        assert MetricName.PRICE_SALES_RATIO in snapshot.metrics


class TestHerkunftIstPflicht:
    def test_eine_kennzahl_ohne_quelle_laesst_sich_nicht_bilden(self) -> None:
        """Doc 10, Paragraph 6.9 verlangt die Quelle an jeder Kennzahl."""
        with pytest.raises(ValueError, match="ohne Quelle"):
            Metric(
                name=MetricName.REVENUE,
                value=1.0,
                unit=MetricUnit.CURRENCY,
                period_end=date(2025, 12, 31),
                sources=(),
                retrieved_at=JETZT,
                currency="USD",
            )

    def test_waehrung_und_einheit_muessen_zusammenpassen(self) -> None:
        with pytest.raises(ValueError, match="passen nicht zusammen"):
            Metric(
                name=MetricName.NET_MARGIN,
                value=0.1,
                unit=MetricUnit.FRACTION,
                period_end=date(2025, 12, 31),
                sources=(_quelle(2025),),
                retrieved_at=JETZT,
                currency="USD",
            )

    def test_jede_kennzahl_traegt_abrufzeitpunkt_und_quelle(self) -> None:
        snapshot = _snapshot({FigureName.REVENUE: _reihe({2025: 1000.0})})
        metric = snapshot.metrics[MetricName.REVENUE]
        assert metric.retrieved_at == JETZT
        assert metric.sources
        assert metric.sources[0].url.startswith("https://www.sec.gov/Archives/edgar/data/")
