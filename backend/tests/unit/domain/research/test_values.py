"""Tests der Wertobjekte des Research Agent."""

from __future__ import annotations

from datetime import UTC, datetime

from ai_trading_analyst.domain.research import (
    Citation,
    ResearchReport,
    ResearchStatus,
    SourceLicenseClass,
)


def test_citation_ist_unveraenderlich() -> None:
    citation = Citation(
        url="https://sec.gov/example",
        title="Beispiel-Filing",
        retrieved_at=datetime.now(UTC),
        cited_text="ein zitierter Ausschnitt",
        license_class=SourceLicenseClass.PRIMARY_SOURCE,
        transformation="zusammengefasst",
    )
    assert citation.url == "https://sec.gov/example"
    assert citation.license_class == SourceLicenseClass.PRIMARY_SOURCE


def test_research_report_ohne_ergebnis_hat_keine_faktoren() -> None:
    report = ResearchReport(
        status=ResearchStatus.UNAVAILABLE,
        evaluated_at=datetime.now(UTC),
        model=None,
        prompt_version=None,
        reason="provider_error",
    )
    assert report.positive_factors == ()
    assert report.negative_factors == ()
    assert report.risks == ()
    assert report.citations == ()
    assert report.summary is None


def test_research_report_mit_zitaten() -> None:
    citation = Citation(
        url="https://example.com",
        title="Titel",
        retrieved_at=datetime.now(UTC),
        cited_text=None,
        license_class=SourceLicenseClass.UNKNOWN,
        transformation="zusammengefasst",
    )
    report = ResearchReport(
        status=ResearchStatus.COMPLETED,
        evaluated_at=datetime.now(UTC),
        model="claude-sonnet-5",
        prompt_version="research-v1",
        summary="Zusammenfassung",
        positive_factors=("Faktor A",),
        confidence=0.7,
        citations=(citation,),
    )
    assert report.citations == (citation,)
    assert report.confidence == 0.7
