"""Der Bericht ordnet zu und benennt, was fehlt (Doc 10, Paragraph 6.12; ADR 0039).

Geprueft wird beides: dass ein vorhandenes Teilergebnis im richtigen Abschnitt
landet, **und** dass ein fehlendes eine begruendete Luecke ergibt. Das zweite
ist die eigentliche Zusicherung -- eine stille Auslassung waere der Fehler,
den CLAUDE.md verbietet.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_trading_analyst.domain.analysts import AnalystRecommendationStatus
from ai_trading_analyst.domain.earnings import EarningsFilterStatus
from ai_trading_analyst.domain.fundamentals import FundamentalStatus
from ai_trading_analyst.domain.report import (
    REPORT_SCHEMA_VERSION,
    GapKind,
    ReportSection,
    SourceKind,
    build_report,
)
from ai_trading_analyst.domain.research import ResearchStatus
from ai_trading_analyst.domain.scoring import (
    ComponentName,
    ScoreComponent,
    ScoreConfidence,
    ScoreKind,
    ScoreResult,
    ScoreStatus,
)
from tests.unit.domain.report.conftest import (
    JETZT,
    make_analysts,
    make_backtest,
    make_earnings,
    make_fundamentals,
    make_outcome,
    make_research,
    make_technical,
)

ERSTELLT = datetime(2026, 8, 30, 21, 5, tzinfo=UTC)


def bericht(**overrides: object):  # type: ignore[no-untyped-def]
    return build_report(make_outcome(**overrides), created_at=ERSTELLT, app_version="0.1.0")


def luecken_zu(report, section: ReportSection):  # type: ignore[no-untyped-def]
    return [luecke for luecke in report.gaps if luecke.section is section]


class TestVollstaendigkeit:
    def test_jede_luecke_nennt_einen_grund(self) -> None:
        for luecke in bericht().gaps:
            assert luecke.reason.strip(), f"{luecke.section} ohne Begruendung"

    def test_die_versionen_stehen_am_bericht(self) -> None:
        """Doc 10, Paragraph 8: Berichtsschema- und Anwendungsversion an jedem
        Ergebnis. Die Scoring-Version bleibt leer statt erfunden."""
        report = bericht()
        assert report.report_schema_version == REPORT_SCHEMA_VERSION
        assert report.app_version == "0.1.0"
        assert report.scoring_version is None

    def test_die_zusammenfassung_bleibt_leer(self) -> None:
        """Ohne Sprachmodell keine Formulierung (ADR 0039, Entscheidung 2)."""
        assert bericht().summary is None


class TestSprintFuenf:
    @pytest.mark.parametrize(
        "section",
        [
            ReportSection.PUT_STRATEGIEN,
            ReportSection.SWING_SCORE,
            ReportSection.INVESTMENT_SCORE,
            ReportSection.EMPFEHLUNG,
        ],
    )
    def test_die_vier_sprint_5_punkte_fehlen_ausdruecklich(self, section: ReportSection) -> None:
        """Sie fehlen immer -- und zwar benannt, nicht weggelassen. Das ist die
        Entscheidung aus ADR 0039, Entscheidung 1."""
        report = bericht(
            earnings=make_earnings(EarningsFilterStatus.EARNINGS_CLEAR),
            backtest=(make_backtest(),),
            technical=make_technical(),
            research=make_research(),
            fundamentals=make_fundamentals(vollstaendig=True),
        )
        (luecke,) = luecken_zu(report, section)
        assert luecke.kind is GapKind.FEHLT
        assert section in report.missing_sections

    def test_ohne_score_gibt_es_keine_empfehlung(self) -> None:
        report = bericht()
        assert report.recommendation is None
        assert report.swing_score is None
        assert report.investment_score is None


class TestEarnings:
    def test_ohne_earnings_filter_fehlt_der_punkt(self) -> None:
        (luecke,) = luecken_zu(bericht(), ReportSection.EARNINGS_STATUS)
        assert luecke.kind is GapKind.FEHLT

    def test_ein_klarer_termin_ergibt_keine_luecke(self) -> None:
        report = bericht(earnings=make_earnings(EarningsFilterStatus.EARNINGS_CLEAR))
        assert luecken_zu(report, ReportSection.EARNINGS_STATUS) == []
        assert ReportSection.EARNINGS_STATUS not in report.missing_sections

    def test_ein_unbekannter_termin_ist_ein_datenrisiko(self) -> None:
        """Doc 10, Paragraph 6.5: UNKNOWN wird ausdruecklich als Datenrisiko
        gekennzeichnet -- nicht stillschweigend als unbedenklich behandelt."""
        report = bericht(
            earnings=make_earnings(EarningsFilterStatus.UNKNOWN, reason="keine Abdeckung")
        )
        (luecke,) = luecken_zu(report, ReportSection.EARNINGS_STATUS)
        assert luecke.kind is GapKind.EINGESCHRAENKT
        assert "keine Abdeckung" in luecke.reason
        # Eingeschraenkt heisst: vorhanden, aber mit Vorbehalt.
        assert ReportSection.EARNINGS_STATUS not in report.missing_sections


class TestSignalstatistik:
    def test_ohne_backtest_fehlt_punkt_fuenf(self) -> None:
        (luecke,) = luecken_zu(bericht(), ReportSection.SIGNALSTATISTIK)
        assert luecke.kind is GapKind.FEHLT

    def test_ein_ungefilterter_backtest_gilt_nur_eingeschraenkt(self) -> None:
        """ADR 0038, Entscheidung 3: Der Replay schliesst keine Ereignisse nahe
        Berichtsterminen aus. Die Kennzahl fehlt nicht -- sie misst eine leicht
        andere Strategie als die gehandelte, und das gehoert in den Bericht."""
        report = bericht(backtest=(make_backtest(earnings_exclusion_applied=False),))
        (luecke,) = luecken_zu(report, ReportSection.SIGNALSTATISTIK)
        assert luecke.kind is GapKind.EINGESCHRAENKT
        assert "ADR 0017 L9" in luecke.reason
        assert ReportSection.SIGNALSTATISTIK not in report.missing_sections

    def test_ein_gefilterter_backtest_stuende_ohne_vorbehalt(self) -> None:
        """Die Gegenprobe zu E3: Sobald historische Termine vorliegen, faellt
        der Vorbehalt von selbst weg."""
        report = bericht(backtest=(make_backtest(earnings_exclusion_applied=True),))
        assert luecken_zu(report, ReportSection.SIGNALSTATISTIK) == []


class TestTechnik:
    def test_ohne_chartauswertung_fehlen_lage_und_zonen(self) -> None:
        report = bericht()
        assert luecken_zu(report, ReportSection.TECHNISCHE_LAGE)[0].kind is GapKind.FEHLT
        assert luecken_zu(report, ReportSection.ZONEN)[0].kind is GapKind.FEHLT

    def test_mit_zonen_fehlt_nichts(self) -> None:
        report = bericht(technical=make_technical())
        assert luecken_zu(report, ReportSection.TECHNISCHE_LAGE) == []
        assert luecken_zu(report, ReportSection.ZONEN) == []

    def test_ohne_belastbare_zone_fehlt_nur_punkt_sieben(self) -> None:
        report = bericht(technical=make_technical(mit_zonen=False))
        assert luecken_zu(report, ReportSection.TECHNISCHE_LAGE) == []
        assert luecken_zu(report, ReportSection.ZONEN)[0].kind is GapKind.FEHLT


class TestResearch:
    def test_ohne_recherche_fehlen_vier_punkte(self) -> None:
        report = bericht()
        for section in (
            ReportSection.NACHRICHTEN,
            ReportSection.ANALYSTENMEINUNGEN,
            ReportSection.CHANCEN,
            ReportSection.RISIKEN,
        ):
            assert luecken_zu(report, section)[0].kind is GapKind.FEHLT, section

    def test_ein_ausfall_der_quelle_wird_begruendet(self) -> None:
        report = bericht(
            research=make_research(status=ResearchStatus.UNAVAILABLE, reason="Anbieter down")
        )
        assert "Anbieter down" in luecken_zu(report, ReportSection.NACHRICHTEN)[0].reason

    def test_ohne_recherche_haengt_punkt_neun_nicht_mehr_daran(self) -> None:
        """Bis ADR 0043 galt Punkt 9 als fehlend, sobald die Recherche
        ausfiel -- obwohl die gezaehlte Votenverteilung damit nichts zu tun
        hat. Genau der Fehler, den die letzte Review bei den Risiken fand."""
        report = bericht(
            research=make_research(status=ResearchStatus.UNAVAILABLE, reason="Anbieter down"),
            analysts=make_analysts(),
        )
        (luecke,) = luecken_zu(report, ReportSection.ANALYSTENMEINUNGEN)
        assert luecke.kind is GapKind.EINGESCHRAENKT
        assert ReportSection.ANALYSTENMEINUNGEN not in report.missing_sections

    def test_eine_recherche_ohne_risiken_laesst_punkt_zwoelf_fehlen(self) -> None:
        report = bericht(research=make_research(risiken=()))
        assert luecken_zu(report, ReportSection.RISIKEN)[0].kind is GapKind.FEHLT


class TestAnalystenmeinungen:
    """Punkt 9 (ADR 0043)."""

    def test_kursziele_bleiben_ein_ausdruecklicher_vorbehalt(self) -> None:
        """Doc 10 verlangt sie, es wird sie nicht geben. Das gehoert gesagt."""
        (luecke,) = luecken_zu(bericht(analysts=make_analysts()), ReportSection.ANALYSTENMEINUNGEN)
        assert luecke.kind is GapKind.EINGESCHRAENKT
        assert "Kursziele" in luecke.reason

    def test_ohne_abruf_fehlt_der_punkt(self) -> None:
        (luecke,) = luecken_zu(bericht(), ReportSection.ANALYSTENMEINUNGEN)
        assert luecke.kind is GapKind.FEHLT

    def test_ein_ausfall_des_anbieters_wird_begruendet(self) -> None:
        report = bericht(
            analysts=make_analysts(
                status=AnalystRecommendationStatus.UNAVAILABLE, reason="provider_error"
            )
        )
        (luecke,) = luecken_zu(report, ReportSection.ANALYSTENMEINUNGEN)
        assert luecke.kind is GapKind.FEHLT
        assert "provider_error" in luecke.reason

    def test_fehlende_abdeckung_ist_nicht_keine_meinung(self) -> None:
        """Ein Anbieter, der das Symbol nicht fuehrt, hat nichts gesagt --
        der Punkt fehlt, statt eine leere Verteilung auszugeben (ADR 0043)."""
        report = bericht(
            analysts=make_analysts(
                status=AnalystRecommendationStatus.UNKNOWN, reason="no_coverage"
            )
        )
        (luecke,) = luecken_zu(report, ReportSection.ANALYSTENMEINUNGEN)
        assert luecke.kind is GapKind.FEHLT
        assert "keine Empfehlungen" in luecke.reason

    def test_die_empfehlungen_stehen_als_eigene_quellenart_in_punkt_achtzehn(self) -> None:
        quellen = bericht(analysts=make_analysts()).sources
        arten = {quelle.kind for quelle in quellen}
        assert SourceKind.ANALYSTS in arten

    def test_ohne_abdeckung_gibt_es_auch_keine_quelle(self) -> None:
        """Ein Beleg fuer eine Angabe, die es nicht gibt, waere keiner."""
        quellen = bericht(
            analysts=make_analysts(status=AnalystRecommendationStatus.UNKNOWN)
        ).sources
        assert all(quelle.kind is not SourceKind.ANALYSTS for quelle in quellen)


class TestFundamentaldaten:
    def test_ohne_fundamentaldaten_fehlt_die_bewertung_und_der_name_ist_offen(self) -> None:
        """Punkt 10 fehlt ganz, Punkt 1 nur halb: Symbol und Boerse stehen
        auch ohne Fundamentaldaten."""
        report = bericht()
        assert luecken_zu(report, ReportSection.FUNDAMENTALE_BEWERTUNG)[0].kind is GapKind.FEHLT
        name_luecke = luecken_zu(report, ReportSection.SYMBOL_UND_UNTERNEHMEN)[0]
        assert name_luecke.kind is GapKind.EINGESCHRAENKT
        assert ReportSection.SYMBOL_UND_UNTERNEHMEN not in report.missing_sections

    def test_der_unternehmensname_kommt_aus_den_fundamentaldaten(self) -> None:
        """Berichtspunkt 1 verlangt "Symbol und Unternehmen"; die einzige
        Quelle ist das SEC-Symbolverzeichnis (ADR 0039, Entscheidung 5)."""
        report = bericht(fundamentals=make_fundamentals(vollstaendig=True))
        assert report.company_name == "Apple Inc."
        assert luecken_zu(report, ReportSection.SYMBOL_UND_UNTERNEHMEN) == []

    def test_ohne_eintrag_im_verzeichnis_bleibt_der_name_leer(self) -> None:
        report = bericht(fundamentals=make_fundamentals(company_name=None, vollstaendig=True))
        assert report.company_name is None
        luecke = luecken_zu(report, ReportSection.SYMBOL_UND_UNTERNEHMEN)[0]
        assert luecke.kind is GapKind.EINGESCHRAENKT
        assert "Symbolverzeichnis" in luecke.reason

    def test_eine_teilweise_abdeckung_nennt_die_fehlenden_kennzahlen(self) -> None:
        report = bericht(fundamentals=make_fundamentals())
        (luecke,) = luecken_zu(report, ReportSection.FUNDAMENTALE_BEWERTUNG)
        assert luecke.kind is GapKind.EINGESCHRAENKT
        assert "NET_INCOME" in luecke.reason

    def test_insufficient_data_laesst_den_punkt_fehlen(self) -> None:
        report = bericht(
            fundamentals=make_fundamentals(status=FundamentalStatus.INSUFFICIENT_DATA)
        )
        assert luecken_zu(report, ReportSection.FUNDAMENTALE_BEWERTUNG)[0].kind is GapKind.FEHLT


class TestQuellen:
    def test_ohne_jede_quelle_fehlt_punkt_achtzehn(self) -> None:
        assert luecken_zu(bericht(), ReportSection.QUELLEN)[0].kind is GapKind.FEHLT

    def test_beide_quellenarten_landen_in_einer_liste(self) -> None:
        report = bericht(
            research=make_research(), fundamentals=make_fundamentals(vollstaendig=True)
        )
        arten = {quelle.kind for quelle in report.sources}
        assert arten == {SourceKind.RESEARCH, SourceKind.FUNDAMENTALS}
        assert luecken_zu(report, ReportSection.QUELLEN) == []

    def test_dieselbe_einreichung_erscheint_nur_einmal(self) -> None:
        """Neunzehn Kennzahlen stammen aus demselben Dokument. Neunzehn
        gleiche Zeilen waeren keine Quellenangabe, sondern Rauschen."""
        report = bericht(fundamentals=make_fundamentals(vollstaendig=True))
        sec = [q for q in report.sources if q.kind is SourceKind.FUNDAMENTALS]
        assert len(sec) == 1
        assert sec[0].url.startswith("https://www.sec.gov/Archives/")
        assert sec[0].filed is not None

    def test_das_quellenalter_bleibt_roh(self) -> None:
        """ADR 0029: Die Angabe des Anbieters ist relativ ("3 days ago") und
        wird nie in ein Datum gerechnet."""
        quellen = bericht(research=make_research()).sources
        (quelle,) = [q for q in quellen if q.kind is SourceKind.RESEARCH]
        assert quelle.source_age == "3 days ago"
        assert quelle.filed is None


class TestKonfidenz:
    def test_die_konfidenzen_bleiben_getrennt(self) -> None:
        """ADR 0039: keine Gesamtkonfidenz -- die Zahlen messen Verschiedenes."""
        report = bericht(
            research=make_research(), fundamentals=make_fundamentals(vollstaendig=True)
        )
        assert report.confidences == {
            "research": 0.72,
            "fundamentals_coverage": 1.0,
        }

    def test_ohne_zulieferer_gibt_es_keine_konfidenz(self) -> None:
        assert bericht().confidences == {}


class TestUebernahme:
    def test_die_stammdaten_kommen_unveraendert_an(self) -> None:
        outcome = make_outcome()
        report = build_report(outcome, created_at=ERSTELLT, app_version="0.1.0")
        assert report.symbol == outcome.stock.symbol
        assert report.exchange == outcome.stock.exchange
        assert report.stock_id == outcome.stock.id
        assert report.analysis_run_id == outcome.analysis_run_id
        assert report.evaluated_at == JETZT
        assert report.created_at == ERSTELLT
        assert report.signals == outcome.result.signal_events


class TestScores:
    """Punkte 14 und 15 (Doc 10, Paragraph 6.11).

    Drei Faelle mit drei verschiedenen Aussagen: nicht gerechnet, nicht
    zustande gekommen, auf unvollstaendiger Grundlage. Der dritte ist
    **eingeschraenkt und nicht fehlend** -- der Abschnitt hat Inhalt.
    """

    @staticmethod
    def _score(
        *,
        kind: ScoreKind = ScoreKind.SWING,
        status: ScoreStatus = ScoreStatus.COMPLETED,
        value: float | None = 7.4,
        fehlend: bool = False,
    ) -> ScoreResult:
        komponenten = [
            ScoreComponent(
                name=ComponentName.TECHNICAL_SIGNALS,
                weight=0.25,
                value=10.0,
                effective_weight=1.0,
                reason="3 von 3 Signalen",
            )
        ]
        if fehlend:
            komponenten.append(
                ScoreComponent(
                    name=ComponentName.OPTIONS_ATTRACTIVENESS, weight=0.10, reason="nicht gebaut"
                )
            )
        return ScoreResult(
            kind=kind,
            status=status,
            version="1.0",
            value=value,
            components=tuple(komponenten),
            coverage=0.7 if fehlend else 1.0,
            confidence=ScoreConfidence.NORMAL,
        )

    def test_ohne_score_fehlt_der_punkt(self) -> None:
        report = build_report(make_outcome(), created_at=ERSTELLT, app_version="0.1.0")
        assert ReportSection.SWING_SCORE in report.missing_sections
        assert ReportSection.INVESTMENT_SCORE in report.missing_sections

    def test_ein_vollstaendiger_score_fuellt_den_punkt(self) -> None:
        report = build_report(
            make_outcome(swing_score=self._score(), investment_score=self._score(
                kind=ScoreKind.LONG_TERM
            )),
            created_at=ERSTELLT,
            app_version="0.1.0",
        )
        assert ReportSection.SWING_SCORE not in report.missing_sections
        assert ReportSection.INVESTMENT_SCORE not in report.missing_sections
        assert report.swing_score is not None
        assert report.swing_score.value == 7.4

    def test_eine_fehlende_komponente_macht_den_punkt_eingeschraenkt_und_nicht_fehlend(
        self,
    ) -> None:
        report = build_report(
            make_outcome(swing_score=self._score(fehlend=True)),
            created_at=ERSTELLT,
            app_version="0.1.0",
        )
        assert ReportSection.SWING_SCORE not in report.missing_sections
        (vorbehalt,) = [
            luecke
            for luecke in report.gaps
            if luecke.section is ReportSection.SWING_SCORE
        ]
        assert vorbehalt.kind is GapKind.EINGESCHRAENKT
        assert "OPTIONS_ATTRACTIVENESS" in vorbehalt.reason

    def test_ein_score_ohne_zahl_fehlt(self) -> None:
        report = build_report(
            make_outcome(
                swing_score=self._score(
                    status=ScoreStatus.INSUFFICIENT_DATA, value=None, fehlend=True
                )
            ),
            created_at=ERSTELLT,
            app_version="0.1.0",
        )
        assert ReportSection.SWING_SCORE in report.missing_sections

    def test_die_versionen_beider_scores_stehen_am_bericht(self) -> None:
        report = build_report(
            make_outcome(
                swing_score=self._score(),
                investment_score=self._score(kind=ScoreKind.LONG_TERM),
            ),
            created_at=ERSTELLT,
            app_version="0.1.0",
        )
        assert report.scoring_version == "swing-1.0+long_term-1.0"

    def test_ohne_score_bleibt_die_scoring_version_leer(self) -> None:
        """Eine Version ohne Ergebnis waere eine Angabe ueber nichts."""
        report = build_report(make_outcome(), created_at=ERSTELLT, app_version="0.1.0")
        assert report.scoring_version is None

    def test_ohne_empfehlung_fehlt_punkt_sechzehn(self) -> None:
        report = build_report(make_outcome(), created_at=ERSTELLT, app_version="0.1.0")
        assert ReportSection.EMPFEHLUNG in report.missing_sections
