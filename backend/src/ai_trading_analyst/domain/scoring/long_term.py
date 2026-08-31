"""Der Long-Term Investment Score (Doc 09; ADR 0041, ADR 0045).

Vier Komponenten, alle vollstaendig auf Kennzahlen aus SEC-Einreichungen.
**Geschaeftsqualitaet, Wettbewerbsvorteile, Marktposition und Management
tragen keinen Teilwert** -- sie bleiben Text im Bericht, solange dafuer keine
deterministische Grundlage existiert (Doc 09 "Was nicht bewertet wird").
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import ceil

from ai_trading_analyst.domain.fundamentals import (
    FundamentalSnapshot,
    FundamentalStatus,
    MetricName,
)

from .aggregate import aggregate
from .parameters import ScoringParameters
from .values import ComponentName, ScoreComponent, ScoreKind, ScoreResult

KENNZAHLEN_JE_KOMPONENTE: Mapping[ComponentName, tuple[MetricName, ...]] = {
    ComponentName.PROFITABILITY: (
        MetricName.GROSS_MARGIN,
        MetricName.OPERATING_MARGIN,
        MetricName.NET_MARGIN,
        MetricName.FREE_CASH_FLOW_MARGIN,
        MetricName.RETURN_ON_EQUITY,
        MetricName.RETURN_ON_ASSETS,
    ),
    ComponentName.GROWTH: (
        MetricName.REVENUE_GROWTH,
        MetricName.NET_INCOME_GROWTH,
    ),
    ComponentName.VALUATION: (
        MetricName.PRICE_EARNINGS_RATIO,
        MetricName.PRICE_SALES_RATIO,
        MetricName.PRICE_FREE_CASH_FLOW_RATIO,
    ),
    ComponentName.BALANCE_SHEET_QUALITY: (
        MetricName.DEBT_TO_EQUITY,
        MetricName.CURRENT_RATIO,
        MetricName.SHARE_COUNT_GROWTH,
    ),
}
"""Welche Kennzahl zu welcher Komponente gehoert (ADR 0041).

Die **Niveaugroessen** -- Umsatz, Jahresueberschuss, freier Cashflow,
Marktkapitalisierung -- stehen in keiner Komponente. Ohne Vergleichsgruppe
und ohne Verlauf ist eine absolute Zahl nicht bewertbar; "zehn Milliarden
Umsatz" ist fuer sich weder gut noch schlecht (Doc 09).
"""

SCORED_METRICS: frozenset[MetricName] = frozenset(
    name for kennzahlen in KENNZAHLEN_JE_KOMPONENTE.values() for name in kennzahlen
)
"""Die Kennzahlen, fuer die es Schwellen geben muss. ``bootstrap`` prueft die
Konfiguration dagegen, damit eine vergessene Schwelle beim Start auffaellt
und nicht als stillschweigend uebersprungene Kennzahl im Ergebnis."""


def mindestbesetzung(kennzahlen: Sequence[MetricName]) -> int:
    """Die Haelfte, aufgerundet (ADR 0045, Entscheidung 3).

    Profitabilitaet 3 von 6, Wachstum 1 von 2, Bewertung 2 von 3,
    Bilanzqualitaet 2 von 3. Das praezisiert ADR 0041, das nur sagt: "Eine
    Komponente ist verfuegbar, wenn ihre Kennzahlen vorliegen."
    """
    return ceil(len(kennzahlen) / 2)


def compute_long_term_score(
    snapshot: FundamentalSnapshot | None, *, parameters: ScoringParameters
) -> ScoreResult:
    """Der Investment-Score aus den Fundamentalkennzahlen.

    ``None`` oder ein Snapshot ohne auswertbare Kennzahlen ergibt keinen
    Fehler, sondern vier fehlende Komponenten und damit
    ``INSUFFICIENT_DATA``. Ein ausgefallenes EDGAR ist ein normaler
    Betriebszustand (ADR 0035) und kein Programmfehler.
    """
    if snapshot is None:
        grund = "die Fundamentalanalyse lief nicht"
        metrics: Mapping[MetricName, float] = {}
    elif snapshot.status is not FundamentalStatus.COMPLETED:
        grund = snapshot.reason or "keine Kennzahl auswertbar"
        metrics = {}
    else:
        grund = ""
        metrics = {name: metrik.value for name, metrik in snapshot.metrics.items()}

    komponenten = [
        _komponente(name, kennzahlen, metrics, parameters, grund)
        for name, kennzahlen in KENNZAHLEN_JE_KOMPONENTE.items()
    ]
    return aggregate(
        kind=ScoreKind.LONG_TERM,
        version=parameters.long_term_version,
        components=komponenten,
        minimum_coverage=parameters.minimum_coverage,
        normal_confidence_coverage=parameters.normal_confidence_coverage,
    )


def _komponente(
    name: ComponentName,
    kennzahlen: tuple[MetricName, ...],
    metrics: Mapping[MetricName, float],
    parameters: ScoringParameters,
    grund_ohne_daten: str,
) -> ScoreComponent:
    gewicht = parameters.long_term_weights[name]
    teilwerte = {
        kennzahl: parameters.thresholds[kennzahl].score(metrics[kennzahl])
        for kennzahl in kennzahlen
        if kennzahl in metrics and kennzahl in parameters.thresholds
    }
    noetig = mindestbesetzung(kennzahlen)
    if len(teilwerte) < noetig:
        fehlend = grund_ohne_daten or (
            f"nur {len(teilwerte)} von {len(kennzahlen)} Kennzahlen vorhanden, "
            f"noetig sind {noetig}"
        )
        return ScoreComponent(name=name, weight=gewicht, value=None, reason=fehlend)

    # Gleich gewichtet ueber die vorhandenen Kennzahlen (ADR 0045,
    # Entscheidung 3) -- dieselbe Regel, die ADR 0041 fuer die Komponenten
    # setzt, eine Ebene tiefer.
    wert = sum(teilwerte.values()) / len(teilwerte)
    benannt = ", ".join(
        f"{kennzahl.value} {teilwert:.0f}" for kennzahl, teilwert in teilwerte.items()
    )
    return ScoreComponent(
        name=name,
        weight=gewicht,
        value=round(wert, 1),
        reason=f"{len(teilwerte)} von {len(kennzahlen)} Kennzahlen: {benannt}",
    )
