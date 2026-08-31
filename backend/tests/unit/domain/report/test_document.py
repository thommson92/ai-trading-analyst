"""Das Dokument fuehrt immer alle achtzehn Abschnitte (ADR 0039).

Ein fehlender Punkt ist ein Abschnitt mit ``verfuegbar: false`` und einer
Begruendung -- nie ein weggelassener Schluessel. Genau das unterscheidet
"unvollstaendige Analyse" von "kuerzerer Bericht".
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from ai_trading_analyst.domain.analysts import AnalystRecommendationStatus
from ai_trading_analyst.domain.earnings import EarningsFilterStatus
from ai_trading_analyst.domain.report import ReportSection, as_document, build_report
from ai_trading_analyst.domain.scoring import (
    ComponentName,
    ScoreComponent,
    ScoreConfidence,
    ScoreKind,
    ScoreResult,
    ScoreStatus,
)
from ai_trading_analyst.domain.technical import TechnicalAssessment, TechnicalAssessmentStatus
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


def dokument(**overrides: object) -> dict:  # type: ignore[type-arg]
    report = build_report(
        make_outcome(**overrides), created_at=ERSTELLT, app_version="0.1.0"
    )
    return as_document(report)


def vollstaendig() -> dict:  # type: ignore[type-arg]
    return dokument(
        earnings=make_earnings(EarningsFilterStatus.EARNINGS_CLEAR),
        backtest=(make_backtest(),),
        technical=make_technical(),
        research=make_research(),
        fundamentals=make_fundamentals(vollstaendig=True),
        analysts=make_analysts(),
    )


def nur_einordnung() -> dict:  # type: ignore[type-arg]
    """Recherche ohne Risiken, aber eine Einordnung mit Fehlsignalgruenden --
    genau der Fall, in dem Punkt 12 als fehlend galt und trotzdem Inhalt trug."""
    return dokument(
        research=make_research(risiken=()),
        technical_assessment=einordnung_mit_risiken(),
    )


def einordnung_ohne_recherche() -> dict:  # type: ignore[type-arg]
    return dokument(technical_assessment=einordnung_mit_risiken())


def empfehlungen_ausgefallen() -> dict:  # type: ignore[type-arg]
    """Vollstaendig bis auf Punkt 9, dessen Anbieter ausfiel.

    Ein eigener Fall in ``_FAELLE``, damit die beiden Invarianten ihn
    mitpruefen: Ein ausgefallener Abschnitt muss ``verfuegbar: false`` **und**
    ``inhalt: null`` haben. Genau hier entstuende sonst ein Abschnitt, der
    als fehlend gilt und trotzdem eine leere Verteilung traegt."""
    return dokument(
        earnings=make_earnings(EarningsFilterStatus.EARNINGS_CLEAR),
        technical=make_technical(),
        research=make_research(),
        analysts=make_analysts(
            status=AnalystRecommendationStatus.UNAVAILABLE, reason="provider_error"
        ),
    )


def ohne_zonen() -> dict:  # type: ignore[type-arg]
    return dokument(technical=make_technical(mit_zonen=False), research=make_research())


_FAELLE: dict[str, Callable[[], dict]] = {  # type: ignore[type-arg]
    "karg": dokument,
    "vollstaendig": vollstaendig,
    "nur_einordnung": nur_einordnung,
    "einordnung_ohne_recherche": einordnung_ohne_recherche,
    "ohne_zonen": ohne_zonen,
    "empfehlungen_ausgefallen": empfehlungen_ausgefallen,
}


def einordnung_mit_risiken() -> TechnicalAssessment:
    return TechnicalAssessment(
        status=TechnicalAssessmentStatus.COMPLETED,
        evaluated_at=JETZT,
        model="fake",
        prompt_version="fake-v1",
        interpreted_analysis_version="technical-v3",
        summary="Einordnung",
        false_signal_risks=("Volumen duenn",),
        confidence=0.6,
    )


class TestAchtzehnAbschnitte:
    def test_der_karge_fall_fuehrt_trotzdem_alle_achtzehn(self) -> None:
        abschnitte = dokument()["abschnitte"]
        assert set(abschnitte) == {section.value for section in ReportSection}

    def test_der_vollstaendige_fall_fuehrt_dieselben_achtzehn(self) -> None:
        assert set(vollstaendig()["abschnitte"]) == {section.value for section in ReportSection}

    def test_die_nummern_folgen_doc_10(self) -> None:
        abschnitte = dokument()["abschnitte"]
        assert abschnitte[ReportSection.SYMBOL_UND_UNTERNEHMEN.value]["nummer"] == 1
        assert abschnitte[ReportSection.SIGNALSTATISTIK.value]["nummer"] == 5
        assert abschnitte[ReportSection.EMPFEHLUNG.value]["nummer"] == 16
        assert abschnitte[ReportSection.QUELLEN.value]["nummer"] == 18
        assert sorted(a["nummer"] for a in abschnitte.values()) == list(range(1, 19))

    @pytest.mark.parametrize("fall", sorted(_FAELLE))
    def test_jeder_nicht_verfuegbare_abschnitt_nennt_einen_grund(self, fall: str) -> None:
        """Die zentrale Invariante -- und sie braucht **mehr als den kargen
        Fall**.

        In der ersten Fassung lief dieser Test nur auf einem Bericht ohne jedes
        Zusatzmodul. Er hat deshalb nicht bemerkt, dass Punkt 12 als fehlend
        gefuehrt wurde, waehrend die KI-Einordnung Fehlsignalgruende
        beisteuerte: Regel und Inhalt standen auf verschiedenen Quellen.
        """
        for name, abschnitt in _FAELLE[fall]()["abschnitte"].items():
            if not abschnitt["verfuegbar"]:
                assert abschnitt["vorbehalte"], f"{name} ohne Begruendung"
                assert abschnitt["inhalt"] is None, f"{name} hat Inhalt trotz Luecke"

    @pytest.mark.parametrize("fall", sorted(_FAELLE))
    def test_ein_verfuegbarer_abschnitt_hat_immer_inhalt(self, fall: str) -> None:
        """Die Gegenrichtung: ``verfuegbar`` ohne Inhalt waere genauso falsch."""
        for name, abschnitt in _FAELLE[fall]()["abschnitte"].items():
            if abschnitt["verfuegbar"]:
                assert abschnitt["inhalt"] is not None, f"{name} verfuegbar, aber leer"


class TestSerialisierbarkeit:
    def test_das_dokument_ist_json(self) -> None:
        """Die verbindliche Fassung geht als JSONB in die Datenbank. Ein Wert,
        der sich nicht schreiben laesst, faellt hier auf und nicht erst im
        Tageslauf."""
        json.dumps(vollstaendig())

    def test_zeitpunkte_werden_zu_iso_zeichenketten(self) -> None:
        dok = vollstaendig()
        assert dok["erstellt_am"] == ERSTELLT.isoformat()
        lage = dok["abschnitte"][ReportSection.TECHNISCHE_LAGE.value]["inhalt"]
        assert isinstance(lage["deterministisch"]["evaluated_at"], str)

    def test_mengen_werden_sortiert(self) -> None:
        """Sonst haengt das Dokument an der Hash-Reihenfolge, und zwei Laeufe
        mit demselben Inhalt ergaeben verschiedene Berichte."""
        statistik = vollstaendig()["abschnitte"][ReportSection.SIGNALSTATISTIK.value]["inhalt"]
        typen = statistik[0]["signal_types"]
        assert typen == sorted(typen)


class TestInhalte:
    def test_die_versionen_stehen_im_kopf(self) -> None:
        dok = dokument()
        assert dok["berichtsschema_version"] == "report-v2"
        assert dok["anwendungsversion"] == "0.1.0"
        assert dok["scoring_version"] is None

    def test_punkt_siebzehn_zaehlt_die_luecken_auf(self) -> None:
        inhalt = dokument()["abschnitte"][ReportSection.KONFIDENZ_UND_DATENLUECKEN.value]["inhalt"]
        abschnitte = {luecke["abschnitt"] for luecke in inhalt["luecken"]}
        assert ReportSection.SWING_SCORE.value in abschnitte
        assert ReportSection.PUT_STRATEGIEN.value in inhalt["fehlende_abschnitte"]

    def test_punkt_siebzehn_ist_selbst_nie_eine_luecke(self) -> None:
        """Der Abschnitt, der die Luecken aufzaehlt, hat immer Inhalt -- auch
        wenn alles andere fehlt."""
        abschnitt = dokument()["abschnitte"][ReportSection.KONFIDENZ_UND_DATENLUECKEN.value]
        assert abschnitt["verfuegbar"]
        assert abschnitt["inhalt"]["luecken"]

    def test_die_analystenmeinungen_fuehren_kursziele_als_leer(self) -> None:
        """Punkt 9 verlangt sie ausdruecklich. Es wird sie nicht geben -- und
        der Schluessel steht trotzdem da, damit niemand ihn fuer vergessen
        haelt (ADR 0043)."""
        inhalt = vollstaendig()["abschnitte"][ReportSection.ANALYSTENMEINUNGEN.value]["inhalt"]
        assert inhalt["kursziele"] is None

    def test_die_votenverteilung_steht_vollstaendig_und_neuester_stand_zuerst(self) -> None:
        inhalt = vollstaendig()["abschnitte"][ReportSection.ANALYSTENMEINUNGEN.value]["inhalt"]
        staende = inhalt["empfehlungen"]["periods"]
        assert [stand["period"] for stand in staende] == ["2026-08-01", "2026-07-01"]
        assert staende[0]["strong_buy"] == 9
        assert staende[1]["hold"] == 8

    def test_punkt_neun_steht_auch_ohne_recherche(self) -> None:
        """ADR 0043: Die Verteilung ist gezaehlt, nicht recherchiert."""
        abschnitt = dokument(analysts=make_analysts())["abschnitte"][
            ReportSection.ANALYSTENMEINUNGEN.value
        ]
        assert abschnitt["verfuegbar"]
        assert abschnitt["inhalt"]["empfehlungen"]["periods"]

    def test_risiken_kommen_aus_beiden_modulen(self) -> None:
        inhalt = vollstaendig()["abschnitte"][ReportSection.RISIKEN.value]["inhalt"]
        assert "Lieferkette" in inhalt

    def test_die_fundamentalkennzahlen_stehen_vollstaendig_im_dokument(self) -> None:
        inhalt = vollstaendig()["abschnitte"][ReportSection.FUNDAMENTALE_BEWERTUNG.value]["inhalt"]
        assert inhalt["company_name"] == "Apple Inc."
        assert inhalt["metrics"]["REVENUE"]["sources"][0]["accession"]


class TestScoreImDokument:
    """Punkt 14 traegt den ganzen Score, nicht nur seine Zahl.

    Doc 10, Paragraph 6.11 verlangt neun Angaben. Eine blosse Zahl im
    Dokument waere genau die Scheingenauigkeit, die derselbe Absatz
    ausschliesst -- und der Bericht ist die verbindliche Fassung, aus der
    sich das spaeter nicht mehr ergaenzen laesst.
    """

    @staticmethod
    def _score() -> ScoreResult:
        return ScoreResult(
            kind=ScoreKind.SWING,
            status=ScoreStatus.COMPLETED,
            version="1.0",
            value=8.6,
            components=(
                ScoreComponent(
                    name=ComponentName.TECHNICAL_SIGNALS,
                    weight=0.25,
                    value=10.0,
                    effective_weight=0.3125,
                    reason="3 von 3 Signalen",
                ),
                ScoreComponent(
                    name=ComponentName.OPTIONS_ATTRACTIVENESS,
                    weight=0.10,
                    reason="die Optionsanalyse ist noch nicht gebaut (ADR 0048)",
                ),
            ),
            coverage=0.9,
            confidence=ScoreConfidence.NORMAL,
            positive_factors=("Technische Signale: 10.0",),
            limiting_risks=("Signalstatistik auf duenner Stichprobe",),
        )

    def test_der_abschnitt_traegt_teilwerte_gewichte_und_begruendung(self) -> None:
        inhalt = dokument(swing_score=self._score())["abschnitte"][
            ReportSection.SWING_SCORE.value
        ]["inhalt"]

        assert inhalt["value"] == 8.6
        assert inhalt["coverage"] == 0.9
        assert inhalt["confidence"] == "NORMAL"
        assert inhalt["version"] == "1.0"
        assert inhalt["positive_factors"] == ["Technische Signale: 10.0"]
        assert inhalt["limiting_risks"] == ["Signalstatistik auf duenner Stichprobe"]
        erste = inhalt["components"][0]
        assert erste["name"] == "TECHNICAL_SIGNALS"
        assert erste["weight"] == 0.25
        assert erste["effective_weight"] == 0.3125
        assert erste["reason"] == "3 von 3 Signalen"

    def test_eine_fehlende_komponente_steht_als_luecke_und_nicht_als_null(self) -> None:
        inhalt = dokument(swing_score=self._score())["abschnitte"][
            ReportSection.SWING_SCORE.value
        ]["inhalt"]

        (fehlend,) = [
            k for k in inhalt["components"] if k["name"] == "OPTIONS_ATTRACTIVENESS"
        ]
        assert fehlend["value"] is None
        assert fehlend["effective_weight"] == 0.0
        assert fehlend["weight"] == 0.10, "das verlorene Gewicht bleibt sichtbar"

    def test_das_dokument_bleibt_json(self) -> None:
        json.dumps(dokument(swing_score=self._score()))
