"""EDGAR-Adapter fuer die deterministische Fundamentalanalyse (ADR 0032)."""

from .companyfacts import (
    FIGURE_TAGS,
    CompanyFactsError,
    ResolvedFacts,
    resolve_company_facts,
)
from .provider import EdgarConnectionSettings, EdgarFundamentalDataProvider

__all__ = [
    "FIGURE_TAGS",
    "CompanyFactsError",
    "EdgarConnectionSettings",
    "EdgarFundamentalDataProvider",
    "ResolvedFacts",
    "resolve_company_facts",
]
