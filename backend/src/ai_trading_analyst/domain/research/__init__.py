"""Research Agent: Wertobjekte und deterministische Ableitungen

(Doc 06; Doc 10, Paragraph 6.7 und 10; ADR 0021, ADR 0023, ADR 0029)."""

from .sources import (
    BEGRENZTE_MINDESTQUELLEN,
    BREITE_MINDESTQUELLEN,
    RAENGE_MIT_SUBSTANZ,
    RESEARCH_ANALYSIS_VERSION,
    classify_source_rank,
    derive_coverage,
    host_of,
    rank_and_cap,
)
from .values import (
    RANGFOLGE,
    Citation,
    ResearchCoverage,
    ResearchEvidence,
    ResearchReport,
    ResearchStatus,
    SourceLicenseClass,
    SourceRank,
    rangindex,
)

__all__ = [
    "BEGRENZTE_MINDESTQUELLEN",
    "BREITE_MINDESTQUELLEN",
    "RAENGE_MIT_SUBSTANZ",
    "RANGFOLGE",
    "RESEARCH_ANALYSIS_VERSION",
    "Citation",
    "ResearchCoverage",
    "ResearchEvidence",
    "ResearchReport",
    "ResearchStatus",
    "SourceLicenseClass",
    "SourceRank",
    "classify_source_rank",
    "derive_coverage",
    "host_of",
    "rangindex",
    "rank_and_cap",
]
