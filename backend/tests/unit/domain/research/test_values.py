"""Tests der Wertobjekte des Research Agent."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_trading_analyst.config.settings import ResearchConfig
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
    rank_and_cap,
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
            # Die Hauptdomain fuer sich ist kein Unternehmensauftritt -- erst
            # der Newsroom-Pfad macht sie zu einem (eigener Fall unten).
            ("https://apple.com/iphone", SourceRank.UNRANKED),
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

    def test_abrufe_veraendern_die_stufe_nicht(self) -> None:
        """Seit ``research-analysis-v2`` (ADR 0029, zweiter Nachtrag).

        Ein realer Lauf hat null Abrufe, weil ``fetch_allowed_domains`` keine
        Domain abdeckt, die in Suchtreffern auftaucht -- die Bedingung machte
        BROAD unerreichbar. Die Zahl wird weiter erhoben, geht aber nicht mehr
        in die Einstufung ein.
        """
        belege = [
            self._beleg("https://sec.gov/a", SourceRank.REGULATORY),
            self._beleg("https://www.reuters.com/b", SourceRank.GENERAL_MEDIA),
            self._beleg("https://www.bloomberg.com/c", SourceRank.FINANCIAL_MEDIA),
        ]
        ohne = ResearchEvidence(3, 0, 0, 0)
        mit = ResearchEvidence(3, 3, 0, 0)
        assert derive_coverage(ohne, belege) is ResearchCoverage.BROAD
        assert derive_coverage(ohne, belege) is derive_coverage(mit, belege)

    def test_ohne_substanzquelle_bleibt_es_begrenzt(self) -> None:
        """Die verbliebene Huerde vor BROAD. Faellt sie auch noch, ist die
        Stufe nur noch eine Quellenzaehlung."""
        belege = [
            self._beleg("https://finance.yahoo.com/a", SourceRank.AGGREGATOR),
            self._beleg("https://www.reuters.com/b", SourceRank.GENERAL_MEDIA),
            self._beleg("https://www.bloomberg.com/c", SourceRank.FINANCIAL_MEDIA),
        ]
        assert derive_coverage(ResearchEvidence(3, 0, 0, 0), belege) is ResearchCoverage.LIMITED


class TestEchterQuellensatz:
    """Gegen die Quellen eines tatsaechlichen Laufs, nicht gegen erdachte.

    Die Liste stammt aus dem AAPL-Lauf vom 2026-08-24 auf dem Server (38
    Zitate, 19 verschiedene Quellen). Sie steht hier, weil die erdachten
    Faelle eine Luecke nicht gezeigt haben: ``www.apple.com/newsroom/...``
    -- fuer einen CEO-Wechsel die verlaesslichste denkbare Quelle -- fiel
    auf ``UNRANKED`` durch, und damit war ``BROAD`` fuer einen typischen
    Nachrichtenbericht unerreichbar.
    """

    ECHTE_QUELLEN = (
        # (URL, erwarteter Rang, Zahl der Zitate im Lauf)
        ("https://www.apple.com/newsroom/2026/04/tim-cook-x/", SourceRank.COMPANY, 2),
        ("https://www.apple.com/newsroom/2026/08/eu-app-store/", SourceRank.COMPANY, 1),
        ("https://www.bloomberg.com/news/articles/2026-08-18/x", SourceRank.FINANCIAL_MEDIA, 2),
        ("https://www.cnbc.com/quotes/AAPL", SourceRank.FINANCIAL_MEDIA, 1),
        ("https://www.cnn.com/markets/stocks/AAPL", SourceRank.GENERAL_MEDIA, 2),
        ("https://finance.yahoo.com/news/x", SourceRank.AGGREGATOR, 1),
        # Die grosse Mehrheit des Laufs: Portale und Analyseseiten, die wir
        # nicht einordnen koennen. UNRANKED ist hier die richtige Antwort,
        # nicht ein Mangel der Einstufung -- es macht sichtbar, worauf sich
        # die Recherche tatsaechlich stuetzt.
        ("https://247wallst.com/investing/2026/08/03/x", SourceRank.UNRANKED, 7),
        ("https://247wallst.com/investing/2026/08/18/x", SourceRank.UNRANKED, 3),
        ("https://www.ad-hoc-news.de/boerse/news/x", SourceRank.UNRANKED, 3),
        ("https://ts2.tech/en/x", SourceRank.UNRANKED, 3),
        ("https://appleinsider.com/articles/26/08/18/x", SourceRank.UNRANKED, 2),
        ("https://9to5mac.com/2026/08/17/x", SourceRank.UNRANKED, 2),
        ("https://stockanalysis.com/stocks/aapl/forecast/", SourceRank.UNRANKED, 2),
        ("https://clearank.com/stock/apple-aapl/", SourceRank.UNRANKED, 2),
        ("https://robinhood.com/us/en/stocks/AAPL/", SourceRank.UNRANKED, 1),
        ("https://simplywall.st/stocks/us/tech/nasdaq-aapl/apple/future", SourceRank.UNRANKED, 1),
        ("https://techcrunch.com/2026/08/18/x", SourceRank.UNRANKED, 1),
        ("https://tickernerd.com/stock/aapl-forecast/", SourceRank.UNRANKED, 1),
        ("https://lawfold.com/apple-antitrust-lawsuit/", SourceRank.UNRANKED, 1),
    )
    """19 Quellen, 38 Zitate -- der vollstaendige Lauf."""

    @staticmethod
    def _beleg(url: str, nummer: int = 0) -> Citation:
        return Citation(
            url=url,
            title="Titel",
            retrieved_at=datetime(2026, 8, 24, tzinfo=UTC),
            cited_text=f"{url}#{nummer}",
            license_class=SourceLicenseClass.UNKNOWN,
            transformation="zusammengefasst",
            source_rank=classify_source_rank(url),
        )

    @pytest.mark.parametrize(
        ("url", "erwartet"), [(url, rang) for url, rang, _ in ECHTE_QUELLEN]
    )
    def test_die_quellen_eines_echten_laufs(self, url: str, erwartet: SourceRank) -> None:
        assert classify_source_rank(url) is erwartet

    def test_ein_typischer_nachrichtenbericht_erreicht_broad(self) -> None:
        """Eine Stufe, die nie vergeben wird, ist keine Stufe.

        Zwei Huerden standen dem nacheinander im Weg, beide erst an echten
        Laeufen sichtbar geworden. Ohne den Newsroom-Pfad war ``hat_substanz``
        bei einem Lauf ohne SEC-Filing immer falsch. Und ``successful_fetches``
        ist bei einem typischen Lauf **null** -- deshalb steht hier die Null
        und nicht die Eins des ersten Entwurfs.
        """
        belege = [self._beleg(url) for url, _, _ in self.ECHTE_QUELLEN]
        evidence = ResearchEvidence(
            distinct_sources=len(belege),
            successful_fetches=0,
            rejected_tool_calls=0,
            dropped_citations=13,
        )
        assert derive_coverage(evidence, belege) is ResearchCoverage.BROAD

    def test_der_newsroom_pfad_hebt_keine_nachrichtenseite(self) -> None:
        """Er wird **nach** den Medienlisten geprueft. Sonst machte ein
        ``/press-releases``-Bereich einer Nachrichtenseite sie zur
        Unternehmensmeldung -- und COMPANY zaehlt zur Substanz."""
        assert (
            classify_source_rank("https://www.bloomberg.com/press-releases/x")
            is SourceRank.FINANCIAL_MEDIA
        )
        assert (
            classify_source_rank("https://irgendeine-ag.example/press-release/zahlen")
            is SourceRank.COMPANY
        )

    def test_die_obergrenze_laesst_keine_quelle_des_echten_laufs_fallen(self) -> None:
        """Bei 15 gingen vier der 19 Quellen verloren, obwohl die Deckelung
        gerade die Vielfalt schuetzen soll -- deshalb steht der Standard auf
        25. Der Test haelt beides fest: dass 25 reicht und dass 15 es nicht
        tat."""
        belege = [
            self._beleg(url, nummer)
            for url, _, anzahl in self.ECHTE_QUELLEN
            for nummer in range(anzahl)
        ]
        assert len(belege) == 38

        behalten, verworfen = rank_and_cap(belege, ResearchConfig().max_citations)
        assert len({beleg.url for beleg in behalten}) == len(self.ECHTE_QUELLEN)
        assert verworfen == len(belege) - ResearchConfig().max_citations

        zu_knapp, _ = rank_and_cap(belege, 15)
        assert len({beleg.url for beleg in zu_knapp}) < len(self.ECHTE_QUELLEN)
