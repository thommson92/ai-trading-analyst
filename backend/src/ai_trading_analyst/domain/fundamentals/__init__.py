"""Deterministische Fundamentalanalyse (Doc 10, Paragraph 6.9; ADR 0032).

Die gerechnete Haelfte des Fundamental Analysis Module. Sie bekommt bereits
aufgeloeste Jahreswerte und rechnet daraus Kennzahlen -- ohne Netz, ohne
Datenbank, ohne Sprachmodell.

Welches XBRL-Tag einen Rohwert geliefert hat, entscheidet die Infrastruktur
(``infrastructure.edgar``). Diese Trennung ist nicht kosmetisch: ADR 0032
zeigt an Honeywell, dass die Tag-Wahl den Umsatz um 22 Prozent verschiebt.
Sie gehoert damit an eine Stelle, die man pruefen kann, und nicht in die
Kennzahlenformel.
"""

from .metrics import (
    FundamentalParameters,
    compound_annual_growth,
    compute_fundamental_snapshot,
)
from .values import (
    FUNDAMENTAL_ANALYSIS_VERSION,
    FigureName,
    FundamentalSnapshot,
    FundamentalStatus,
    Metric,
    MetricName,
    MetricUnit,
    ReportedFigure,
    SourceRef,
    TagConflict,
)

__all__ = [
    "FUNDAMENTAL_ANALYSIS_VERSION",
    "FigureName",
    "FundamentalParameters",
    "FundamentalSnapshot",
    "FundamentalStatus",
    "Metric",
    "MetricName",
    "MetricUnit",
    "ReportedFigure",
    "SourceRef",
    "TagConflict",
    "compound_annual_growth",
    "compute_fundamental_snapshot",
]
