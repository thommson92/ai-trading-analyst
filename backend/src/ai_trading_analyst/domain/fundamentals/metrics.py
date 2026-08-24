"""Die Kennzahlenrechnung selbst (Doc 10, Paragraph 6.9; ADR 0032).

Bekommt bereits aufgeloeste Jahreswerte -- welches XBRL-Tag sie geliefert
hat und welche Einreichung gewonnen hat, ist zu diesem Zeitpunkt entschieden
(``infrastructure.edgar``). Hier passiert nur noch Arithmetik, und zwar
ohne Netz, ohne Datenbank und ohne Sprachmodell.

Zwei Regeln durchziehen das ganze Modul:

**Kein Ersatzwert.** Fehlt eine Rohgroesse, fehlt die Kennzahl. Es gibt
keinen Rueckfall auf ein aehnliches Jahr, keinen Branchendurchschnitt und
keine Null (CLAUDE.md: fehlende Werte bleiben fehlend).

**Keine Kennzahl aus zwei Jahren.** Eine Marge aus dem Gewinn des einen und
dem Umsatz des anderen Geschaeftsjahres saehe plausibel aus und waere falsch.
Beide Rohgroessen muessen denselben Stichtag tragen.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from .values import (
    FUNDAMENTAL_ANALYSIS_VERSION,
    FigureName,
    FundamentalSnapshot,
    FundamentalStatus,
    Metric,
    MetricName,
    MetricUnit,
    ReportedFigure,
    TagConflict,
)


@dataclass(frozen=True, slots=True)
class FundamentalParameters:
    """Parameter der Kennzahlenrechnung (ADR 0032)."""

    growth_years: int = 3
    """Spanne der Wachstumsraten in Geschaeftsjahren.

    Die Spanne wird **vollstaendig verlangt**, nicht auf das gekuerzt, was
    vorliegt. Eine Wachstumsrate ueber zwei Jahre neben einer ueber drei
    saehe wie dieselbe Kennzahl aus und waere keine -- bei einem jungen
    Unternehmen fehlt sie deshalb lieber ganz."""

    def __post_init__(self) -> None:
        if self.growth_years < 1:
            raise ValueError(f"growth_years muss mindestens 1 sein, war {self.growth_years}")


def compound_annual_growth(start_value: float, end_value: float, years: int) -> float | None:
    """Jaehrliche Wachstumsrate als Bruchteil, oder ``None``.

    ``None`` bei einem Ausgangswert von null oder darunter. Das ist keine
    Vorsicht, sondern Arithmetik: Aus einem Verlust in einen Gewinn gibt es
    keine sinnvolle Wachstumsrate -- die Formel liefert dort je nach
    Vorzeichen eine komplexe Zahl oder eine, die das Gegenteil dessen
    aussagt, was passiert ist. Ein Verlust, der sich halbiert, saehe als
    "minus 50 Prozent Wachstum" aus wie eine Verschlechterung.
    """
    if start_value <= 0 or years < 1:
        return None
    if end_value <= 0:
        # Aus Gewinn wurde Verlust. Der Verlauf ist eine Aussage, aber keine
        # Rate -- eine negative Wurzel gaebe es hier ohnehin nicht.
        return None
    rate: float = (end_value / start_value) ** (1 / years) - 1
    return rate


def _nach_geschaeftsjahr(
    figures: Mapping[FigureName, Sequence[ReportedFigure]], name: FigureName
) -> dict[date, ReportedFigure]:
    """Rohgroesse nach Stichtag, damit sich Jahre paaren lassen."""
    return {figure.period_end: figure for figure in figures.get(name, ())}


class _Rechner:
    """Sammelt die Kennzahlen eines Laufs.

    Eine Klasse und keine Funktionsfolge, weil jede Kennzahl dieselben drei
    Dinge braucht -- Stichtag, Abrufzeitpunkt und die Quellen der beteiligten
    Rohgroessen -- und diese Wiederholung sonst in jeder einzelnen Rechnung
    stuende.
    """

    def __init__(
        self,
        figures: Mapping[FigureName, Sequence[ReportedFigure]],
        *,
        retrieved_at: datetime,
        currency: str,
    ) -> None:
        self._nach_name = {name: _nach_geschaeftsjahr(figures, name) for name in FigureName}
        self._retrieved_at = retrieved_at
        self._currency = currency
        self.metrics: dict[MetricName, Metric] = {}

    def wert(self, name: FigureName, stichtag: date) -> ReportedFigure | None:
        return self._nach_name[name].get(stichtag)

    def stichtage(self, name: FigureName) -> list[date]:
        return sorted(self._nach_name[name])

    def add(
        self,
        name: MetricName,
        value: float | None,
        *,
        unit: MetricUnit,
        period_end: date,
        quellen: Sequence[ReportedFigure],
        period_start: date | None = None,
    ) -> None:
        """Traegt eine Kennzahl ein -- oder eben nicht.

        ``None`` fuehrt zu keinem Eintrag und zu keinem Platzhalter. Was
        fehlt, taucht ueber ``missing_metrics`` auf, nicht als Null.
        """
        if value is None:
            return
        self.metrics[name] = Metric(
            name=name,
            value=value,
            unit=unit,
            period_start=period_start,
            period_end=period_end,
            currency=self._currency if unit is MetricUnit.CURRENCY else None,
            sources=tuple(figure.source for figure in quellen),
            retrieved_at=self._retrieved_at,
        )

    def betrag(self, name: MetricName, figure: ReportedFigure | None) -> None:
        """Eine Rohgroesse unveraendert als Kennzahl."""
        if figure is None:
            return
        self.add(
            name,
            figure.value,
            unit=MetricUnit.CURRENCY,
            period_start=figure.period_start,
            period_end=figure.period_end,
            quellen=[figure],
        )

    def verhaeltnis(
        self,
        name: MetricName,
        zaehler: ReportedFigure | None,
        nenner: ReportedFigure | None,
        *,
        unit: MetricUnit,
        stichtag: date,
        nur_positiver_nenner: bool = True,
    ) -> None:
        """Zwei Rohgroessen desselben Stichtags ins Verhaeltnis gesetzt.

        ``nur_positiver_nenner`` ist der Regelfall: Ein negatives
        Eigenkapital oder ein negativer Umsatz macht das Verhaeltnis nicht
        klein, sondern bedeutungslos -- eine Eigenkapitalrendite bei
        negativem Eigenkapital dreht das Vorzeichen und behauptet damit das
        Gegenteil der Lage.
        """
        if zaehler is None or nenner is None:
            return
        if nenner.value == 0 or (nur_positiver_nenner and nenner.value < 0):
            return
        self.add(
            name,
            zaehler.value / nenner.value,
            unit=unit,
            period_end=stichtag,
            quellen=[zaehler, nenner],
        )


def _jahresspanne(
    rechner: _Rechner, name: FigureName, jahre: int
) -> tuple[ReportedFigure, ReportedFigure] | None:
    """Aeltester und juengster Wert einer Spanne von genau ``jahre`` Jahren.

    Gesucht wird der Stichtag, der ``jahre`` Geschaeftsjahre vor dem
    juengsten liegt -- nicht schlicht der aelteste vorhandene. Fehlt ein Jahr
    dazwischen, waere die Rate sonst ueber eine andere Spanne gerechnet, als
    sie behauptet.
    """
    stichtage = rechner.stichtage(name)
    if len(stichtage) <= jahre:
        return None
    juengster = stichtage[-1]
    aeltester = stichtage[-1 - jahre]
    if juengster.year - aeltester.year != jahre:
        return None
    frueh = rechner.wert(name, aeltester)
    spaet = rechner.wert(name, juengster)
    if frueh is None or spaet is None:
        return None
    return frueh, spaet


def _wachstum(rechner: _Rechner, metric: MetricName, figure: FigureName, jahre: int) -> None:
    spanne = _jahresspanne(rechner, figure, jahre)
    if spanne is None:
        return
    frueh, spaet = spanne
    rechner.add(
        metric,
        compound_annual_growth(frueh.value, spaet.value, jahre),
        unit=MetricUnit.FRACTION,
        period_start=frueh.period_start or frueh.period_end,
        period_end=spaet.period_end,
        quellen=[frueh, spaet],
    )


def compute_fundamental_snapshot(
    *,
    symbol: str,
    figures: Mapping[FigureName, Sequence[ReportedFigure]],
    retrieved_at: datetime,
    evaluated_at: datetime,
    shares_outstanding: ReportedFigure | None = None,
    price: float | None = None,
    currency: str = "USD",
    parameters: FundamentalParameters | None = None,
    tag_conflicts: Sequence[TagConflict] = (),
) -> FundamentalSnapshot:
    """Rechnet alle Kennzahlen, die die vorliegenden Jahreswerte hergeben.

    ``price`` ist die **optionale, nicht blockierende** Eingabe aus ADR 0032:
    Fehlt er, entstehen die vier bewertungsabhaengigen Kennzahlen nicht, alle
    uebrigen vollstaendig. Das Modul beschafft selbst keinen Kurs.
    """
    params = parameters or FundamentalParameters()
    umsatzstichtage = sorted({figure.period_end for figure in figures.get(FigureName.REVENUE, ())})
    if not umsatzstichtage:
        return FundamentalSnapshot(
            symbol=symbol,
            status=FundamentalStatus.INSUFFICIENT_DATA,
            evaluated_at=evaluated_at,
            analysis_version=FUNDAMENTAL_ANALYSIS_VERSION,
            reason="keine Jahresumsaetze in den Einreichungen",
            tag_conflicts=tuple(tag_conflicts),
        )

    rechner = _Rechner(figures, retrieved_at=retrieved_at, currency=currency)
    stichtag = umsatzstichtage[-1]

    umsatz = rechner.wert(FigureName.REVENUE, stichtag)
    gewinn = rechner.wert(FigureName.NET_INCOME, stichtag)
    eigenkapital = rechner.wert(FigureName.EQUITY, stichtag)

    rechner.betrag(MetricName.REVENUE, umsatz)
    rechner.betrag(MetricName.NET_INCOME, gewinn)

    freier_cashflow = _freier_cashflow(rechner, stichtag)
    if freier_cashflow is not None:
        rechner.add(
            MetricName.FREE_CASH_FLOW,
            freier_cashflow.value,
            unit=MetricUnit.CURRENCY,
            period_start=freier_cashflow.period_start,
            period_end=stichtag,
            quellen=freier_cashflow.quellen,
        )

    rechner.verhaeltnis(
        MetricName.GROSS_MARGIN,
        rechner.wert(FigureName.GROSS_PROFIT, stichtag),
        umsatz,
        unit=MetricUnit.FRACTION,
        stichtag=stichtag,
    )
    rechner.verhaeltnis(
        MetricName.OPERATING_MARGIN,
        rechner.wert(FigureName.OPERATING_INCOME, stichtag),
        umsatz,
        unit=MetricUnit.FRACTION,
        stichtag=stichtag,
    )
    rechner.verhaeltnis(
        MetricName.NET_MARGIN, gewinn, umsatz, unit=MetricUnit.FRACTION, stichtag=stichtag
    )
    if freier_cashflow is not None and umsatz is not None and umsatz.value > 0:
        rechner.add(
            MetricName.FREE_CASH_FLOW_MARGIN,
            freier_cashflow.value / umsatz.value,
            unit=MetricUnit.FRACTION,
            period_end=stichtag,
            quellen=[*freier_cashflow.quellen, umsatz],
        )

    rechner.verhaeltnis(
        MetricName.RETURN_ON_EQUITY,
        gewinn,
        eigenkapital,
        unit=MetricUnit.FRACTION,
        stichtag=stichtag,
    )
    rechner.verhaeltnis(
        MetricName.RETURN_ON_ASSETS,
        gewinn,
        rechner.wert(FigureName.ASSETS, stichtag),
        unit=MetricUnit.FRACTION,
        stichtag=stichtag,
    )
    rechner.verhaeltnis(
        MetricName.DEBT_TO_EQUITY,
        rechner.wert(FigureName.LIABILITIES, stichtag),
        eigenkapital,
        unit=MetricUnit.RATIO,
        stichtag=stichtag,
    )
    rechner.verhaeltnis(
        MetricName.CURRENT_RATIO,
        rechner.wert(FigureName.CURRENT_ASSETS, stichtag),
        rechner.wert(FigureName.CURRENT_LIABILITIES, stichtag),
        unit=MetricUnit.RATIO,
        stichtag=stichtag,
    )

    _wachstum(rechner, MetricName.REVENUE_GROWTH, FigureName.REVENUE, params.growth_years)
    _wachstum(rechner, MetricName.NET_INCOME_GROWTH, FigureName.NET_INCOME, params.growth_years)
    _wachstum(
        rechner, MetricName.SHARE_COUNT_GROWTH, FigureName.DILUTED_SHARES, params.growth_years
    )

    _bewertung(
        rechner,
        stichtag=stichtag,
        price=price,
        shares_outstanding=shares_outstanding,
        umsatz=umsatz,
        gewinn=gewinn,
        freier_cashflow=freier_cashflow,
    )

    return FundamentalSnapshot(
        symbol=symbol,
        status=FundamentalStatus.COMPLETED,
        evaluated_at=evaluated_at,
        analysis_version=FUNDAMENTAL_ANALYSIS_VERSION,
        metrics=rechner.metrics,
        fiscal_years=tuple(tag.year for tag in umsatzstichtage),
        price_used=price,
        tag_conflicts=tuple(tag_conflicts),
    )


@dataclass(frozen=True, slots=True)
class _FreierCashflow:
    value: float
    period_start: date | None
    quellen: tuple[ReportedFigure, ...]


def _freier_cashflow(rechner: _Rechner, stichtag: date) -> _FreierCashflow | None:
    """Operativer Cashflow abzueglich Investitionen ins Anlagevermoegen.

    Die Investitionen stehen in XBRL als **Auszahlung**, also positiv. Sie
    werden abgezogen, nicht addiert -- ein Vorzeichenfehler hier verdoppelte
    den freien Cashflow, statt ihn zu halbieren, und faellt an einer
    plausiblen Zahl niemandem auf.
    """
    operativ = rechner.wert(FigureName.OPERATING_CASH_FLOW, stichtag)
    investitionen = rechner.wert(FigureName.CAPITAL_EXPENDITURE, stichtag)
    if operativ is None or investitionen is None:
        return None
    return _FreierCashflow(
        value=operativ.value - abs(investitionen.value),
        period_start=operativ.period_start,
        quellen=(operativ, investitionen),
    )


def _bewertung(
    rechner: _Rechner,
    *,
    stichtag: date,
    price: float | None,
    shares_outstanding: ReportedFigure | None,
    umsatz: ReportedFigure | None,
    gewinn: ReportedFigure | None,
    freier_cashflow: _FreierCashflow | None,
) -> None:
    """Die vier kursabhaengigen Kennzahlen (ADR 0032, Entscheidung 4).

    Faellt vollstaendig aus, wenn Kurs oder Aktienzahl fehlen -- ohne
    Ersatzwert und ohne dass die uebrigen Kennzahlen davon beruehrt waeren.
    """
    if price is None or shares_outstanding is None or price <= 0:
        return
    marktkapitalisierung = price * shares_outstanding.value
    if marktkapitalisierung <= 0:
        return
    rechner.add(
        MetricName.MARKET_CAPITALIZATION,
        marktkapitalisierung,
        unit=MetricUnit.CURRENCY,
        period_end=shares_outstanding.period_end,
        quellen=[shares_outstanding],
    )

    def teile_durch(name: MetricName, nenner: float, quellen: Sequence[ReportedFigure]) -> None:
        if nenner <= 0:
            # Ein KGV bei Verlust ist negativ und wird mit wachsendem Verlust
            # groesser -- es saehe aus wie eine guenstige Bewertung.
            return
        rechner.add(
            name,
            marktkapitalisierung / nenner,
            unit=MetricUnit.RATIO,
            period_end=stichtag,
            quellen=[shares_outstanding, *quellen],
        )

    if gewinn is not None:
        teile_durch(MetricName.PRICE_EARNINGS_RATIO, gewinn.value, [gewinn])
    if umsatz is not None:
        teile_durch(MetricName.PRICE_SALES_RATIO, umsatz.value, [umsatz])
    if freier_cashflow is not None:
        teile_durch(
            MetricName.PRICE_FREE_CASH_FLOW_RATIO,
            freier_cashflow.value,
            freier_cashflow.quellen,
        )


__all__ = [
    "FundamentalParameters",
    "compound_annual_growth",
    "compute_fundamental_snapshot",
]