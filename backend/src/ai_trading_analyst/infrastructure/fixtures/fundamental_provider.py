"""Dauerhaft nutzbarer Testprovider fuer die Fundamentalanalyse (ADR 0032).

Muster ``FixtureTechnicalInterpreter``: symbolunabhaengig dieselben
Einreichungen. Damit laufen Start und Tests ohne Netzzugriff auf EDGAR, und
``fundamentals.provider`` bleibt ausgeliefert auf ``fixture``.

Die Zahlen sind erfunden und bewusst rund. Sie sollen die Verdrahtung
pruefbar machen, kein Unternehmen nachahmen -- **erfundene Zahlen duerfen
nirgends wie gemessene aussehen** (CLAUDE.md). Der Quellenverweis zeigt
deshalb auf eine offensichtlich unechte Vorgangsnummer.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime

from ai_trading_analyst.domain.analysis import FundamentalDataProvider, Stock
from ai_trading_analyst.domain.fundamentals import (
    FigureName,
    FundamentalSnapshot,
    ReportedFigure,
    SourceRef,
    compute_fundamental_snapshot,
)
from ai_trading_analyst.infrastructure.edgar.companyfacts import INSTANT_FIGURES

_CIK = 0
_ACCESSION = "0000000000-00-000000"
"""Offensichtlich unecht. Eine plausibel aussehende Vorgangsnummer koennte in
einem Bericht fuer eine echte Einreichung gehalten werden."""

_JAHRESENDEN = (date(2022, 12, 31), date(2023, 12, 31), date(2024, 12, 31), date(2025, 12, 31))

_REIHEN: dict[FigureName, tuple[float, ...]] = {
    FigureName.REVENUE: (1_000e6, 1_100e6, 1_210e6, 1_331e6),
    FigureName.NET_INCOME: (100e6, 112e6, 126e6, 140e6),
    FigureName.GROSS_PROFIT: (400e6, 440e6, 484e6, 532e6),
    FigureName.OPERATING_INCOME: (150e6, 165e6, 180e6, 200e6),
    FigureName.ASSETS: (2_000e6, 2_100e6, 2_200e6, 2_300e6),
    FigureName.LIABILITIES: (1_200e6, 1_240e6, 1_280e6, 1_300e6),
    FigureName.EQUITY: (800e6, 860e6, 920e6, 1_000e6),
    FigureName.CURRENT_ASSETS: (600e6, 640e6, 680e6, 720e6),
    FigureName.CURRENT_LIABILITIES: (400e6, 410e6, 420e6, 430e6),
    FigureName.OPERATING_CASH_FLOW: (180e6, 198e6, 218e6, 240e6),
    FigureName.CAPITAL_EXPENDITURE: (50e6, 55e6, 60e6, 66e6),
    FigureName.DILUTED_SHARES: (100e6, 99e6, 98e6, 97e6),
}

def _figure(name: FigureName, wert: float, ende: date) -> ReportedFigure:
    return ReportedFigure(
        value=wert,
        period_start=None if name in INSTANT_FIGURES else date(ende.year, 1, 1),
        period_end=ende,
        unit="shares" if name is FigureName.DILUTED_SHARES else "USD",
        source=SourceRef(
            cik=_CIK, accession=_ACCESSION, form="10-K", filed=ende, tag=f"fixture:{name.value}"
        ),
    )


class FixtureFundamentalDataProvider(FundamentalDataProvider):
    """Implementiert ``FundamentalDataProvider`` ohne Anbieteranfrage."""

    def __init__(self, now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._now = now

    def fundamentals(self, stock: Stock, price: float | None = None) -> FundamentalSnapshot:
        jetzt = self._now()
        figures = {
            name: tuple(
                _figure(name, wert, ende) for wert, ende in zip(reihe, _JAHRESENDEN, strict=True)
            )
            for name, reihe in _REIHEN.items()
        }
        return compute_fundamental_snapshot(
            symbol=stock.symbol,
            figures=figures,
            shares_outstanding=_figure(
                FigureName.DILUTED_SHARES, 97e6, _JAHRESENDEN[-1]
            ),
            price=price,
            retrieved_at=jetzt,
            evaluated_at=jetzt,
        )
