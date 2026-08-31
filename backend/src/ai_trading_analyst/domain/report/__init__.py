"""Der Analysebericht (Doc 10, Paragraph 6.12; ADR 0039).

Fuehrt die Ergebnisse der fuenf Analysemodule zu den achtzehn Pflichtpunkten
zusammen. **Erzeugt keine neuen Fakten** -- was fehlt, wird als Luecke
ausgewiesen, nicht ersetzt.
"""

from .builder import build_report
from .document import as_document
from .notification import render_notification
from .values import (
    REPORT_SCHEMA_VERSION,
    GapKind,
    ReportGap,
    ReportSection,
    ReportSource,
    SourceKind,
    StockReport,
    StoredReport,
)

__all__ = [
    "REPORT_SCHEMA_VERSION",
    "GapKind",
    "ReportGap",
    "ReportSection",
    "ReportSource",
    "SourceKind",
    "StockReport",
    "StoredReport",
    "as_document",
    "build_report",
    "render_notification",
]
