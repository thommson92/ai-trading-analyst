"""Der Analysebericht (Doc 10, Paragraph 6.12; ADR 0039).

Fuehrt die Ergebnisse der fuenf Analysemodule zu den achtzehn Pflichtpunkten
zusammen. **Erzeugt keine neuen Fakten** -- was fehlt, wird als Luecke
ausgewiesen, nicht ersetzt.
"""

from .builder import build_report
from .document import as_document
from .values import (
    REPORT_SCHEMA_VERSION,
    GapKind,
    Recommendation,
    ReportGap,
    ReportSection,
    ReportSource,
    SourceKind,
    StockReport,
)

__all__ = [
    "REPORT_SCHEMA_VERSION",
    "GapKind",
    "Recommendation",
    "ReportGap",
    "ReportSection",
    "ReportSource",
    "SourceKind",
    "StockReport",
    "as_document",
    "build_report",
]
