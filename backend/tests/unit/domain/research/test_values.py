"""Tests der Wertobjekte des Research Agent."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_trading_analyst.domain.research import (
    RANGFOLGE,
    Citation,
    ResearchCoverage,
    ResearchEvidence,
    ResearchReport,
    ResearchStatus,
    SourceLicenseClass,
    SourceRank,
    classify_source_rank,
    derive_coverage,
    rangindex,
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


class TestRangfolge:
    """``RANGFOLGE`` traegt die Sortierung der Zitate (ADR 0029).

    Ihre eigene Begruendung ist, dass eine spaeter eingefuegte Stufe die
    Sortierung nicht still verschieben soll -- das braucht genau den Test,
    der hier steht. Ohne ihn haette ein vergessener Eintrag den naechtlichen
    Lauf zur Laufzeit abgebrochen (``rangindex`` wirft ``ValueError``), statt
    die Suite rot zu faerben.
    """

    def test_jede_stufe_ist_genau_einmal_eingeordnet(self) -> None:
        assert set(RANGFOLGE) == set(SourceRank)
        assert len(RANGFOLGE) == len(SourceRank)

    def test_die_belastbarste_stufe_steht_vorn(self) -> None:
        assert RANGFOLGE[0] is SourceRank.REGULATORY
        assert RANGFOLGE[-1] is SourceRank.UNRANKED

    def test_rangindex_ordnet_streng_aufsteigend(self) -> None:
        indizes = [rangindex(rank) for rank in RANGFOLGE]
        assert indizes == sorted(indizes)
        assert len(set(indizes)) == len(indizes)


class TestQuellenrangZuordnung:
    @pytest.mark.parametrize(
        ("url", "erwartet"),
        [
            ("https://www.sec.gov/Archives/edgar/data/1/10-q.htm", SourceRank.REGULATORY),
            # Port und Zugangsdaten duerfen die Zuordnung nicht kippen.
            ("https://www.sec.gov:443/Archives/edgar/data/1/10-q.htm", SourceRank.REGULATORY),
            ("https://investor.apple.com/news", SourceRank.COMPANY),
            ("https://ir.microsoft.com/mitteilung", SourceRank.COMPANY),
            ("https://www.businesswire.com/news/1", SourceRank.COMPANY),
            ("https://www.bloomberg.com/news/a", SourceRank.FINANCIAL_MEDIA),
            # Investor's Business Daily ist Fachpresse, kein Unternehmensauftritt --
            # und zwar mit wie ohne "www.".
            ("https://investors.com/news/a", SourceRank.FINANCIAL_MEDIA),
            ("https://www.investors.com/news/a", SourceRank.FINANCIAL_MEDIA),
            ("https://www.reuters.com/markets/a", SourceRank.GENERAL_MEDIA),
            ("https://seekingalpha.com/article/1", SourceRank.AGGREGATOR),
            # nasdaq.com veroeffentlicht ueberwiegend Fremdinhalte weiter.
            ("https://www.nasdaq.com/articles/eine-meinung", SourceRank.AGGREGATOR),
            ("https://finance.yahoo.com/news/a", SourceRank.AGGREGATOR),
            ("https://irgendein-blog.example/beitrag", SourceRank.UNRANKED),
            ("https://apple.com/newsroom", SourceRank.UNRANKED),
        ],
    )
    def test_rang_kommt_aus_der_domain(self, url: str, erwartet: SourceRank) -> None:
        assert classify_source_rank(url) is erwartet

    def test_ein_fremder_host_der_zufaellig_so_beginnt_ist_kein_unternehmen(self) -> None:
        """Verglichen wird das erste Host-Label, nicht ein Zeichenpraefix."""
        assert classify_source_rank("https://investorenblatt.example/x") is SourceRank.UNRANKED

    def test_eine_eigenstaendige_domain_ist_kein_investor_relations_auftritt(self) -> None:
        """Ein IR-Auftritt ist eine Unterdomain. ``ir.example.com`` ja,
        ``ir.example`` nein -- letzteres ist eine Domain fuer sich."""
        assert classify_source_rank("https://ir.beispiel.example/x") is SourceRank.COMPANY
        assert classify_source_rank("https://ir.example/x") is SourceRank.UNRANKED


class TestAbdeckungsregel:
    @staticmethod
    def _beleg(url: str, rank: SourceRank) -> Citation:
        return Citation(
            url=url,
            title="Titel",
            retrieved_at=datetime(2026, 8, 23, tzinfo=UTC),
            cited_text=None,
            license_class=SourceLicenseClass.UNKNOWN,
            transformation="zusammengefasst",
            source_rank=rank,
        )

    def test_abgelehnte_werkzeugaufrufe_veraendern_die_stufe_nicht(self) -> None:
        """Sie tragen die Diagnose, nicht die Einstufung -- was sie an Belegen
        gekostet haben, steht bereits in den Zahlen, die eingehen."""
        belege = [
            self._beleg("https://sec.gov/a", SourceRank.REGULATORY),
            self._beleg("https://www.reuters.com/b", SourceRank.GENERAL_MEDIA),
            self._beleg("https://www.bloomberg.com/c", SourceRank.FINANCIAL_MEDIA),
        ]
        ohne = ResearchEvidence(3, 1, 0, 0)
        mit = ResearchEvidence(3, 1, 99, 0)
        assert derive_coverage(ohne, belege) is derive_coverage(mit, belege)

    def test_eine_quelle_ist_keine_recherche(self) -> None:
        belege = [self._beleg("https://sec.gov/a", SourceRank.REGULATORY)]
        assert derive_coverage(ResearchEvidence(1, 1, 0, 0), belege) is ResearchCoverage.THIN
