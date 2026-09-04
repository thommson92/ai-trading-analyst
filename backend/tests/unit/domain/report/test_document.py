"""Das Dokument fuehrt immer alle achtzehn Abschnitte (ADR 0039).

Ein fehlender Punkt ist ein Abschnitt mit ``verfuegbar: false`` und einer
Begruendung -- nie ein weggelassener Schluessel. Genau das unterscheidet
"unvollstaendige Analyse" von "kuerzerer Bericht".
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from ai_trading_analyst.domain.analysts import AnalystRecommendationStatus
from ai_trading_analyst.domain.earnings import EarningsFilterStatus
from ai_trading_analyst.domain.options import (
    OPTIONS_ANALYSIS_VERSION,
    REASON_NO_HEDGE_STRIKE,
    LiquidityGrade,
    OptionsAnalysis,
    OptionsStatus,
    PutSpread,
    PutStrategy,
)
from ai_trading_analyst.domain.report import ReportSection, as_document, build_report
from ai_trading_analyst.domain.scoring import (
    ComponentName,
    Recommendation,
    RecommendationResult,
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


class TestPutStrategienImDokument:
    """Punkt 13 traegt alle Ausgabegroessen aus Doc 10, Paragraph 6.10.

    Das Dokument ist die verbindliche Fassung: Was hier nicht steht, laesst
    sich spaeter nicht mehr ergaenzen -- die Notierung von 16:30 gibt es
    morgen nicht noch einmal.
    """

    @staticmethod
    def _analyse(**overrides: object) -> OptionsAnalysis:
        vorgabe: dict = {  # type: ignore[type-arg]
            "expiration": date(2026, 10, 2),
            "days_to_expiration": 31,
            "strike": 92.0,
            "distance_to_price_pct": 0.08,
            "premium": 1.5,
            "break_even": 90.5,
            "capital_at_risk": 9200.0,
            "simple_return": 0.0163,
            "annualized_return": 0.192,
            "liquidity": LiquidityGrade.ACCEPTABLE,
            "liquidity_warnings": ("Open Interest 30",),
            "bid": 1.5,
            "ask": 1.6,
            "mid": 1.55,
            "delta": 0.26,
            "implied_volatility": 0.31,
            "open_interest": 30,
            "volume": 60,
            "distance_to_support_pct": 0.03,
            "earnings_within_term": False,
        }
        return OptionsAnalysis(
            status=OptionsStatus.COMPLETED,
            evaluated_at=ERSTELLT,
            underlying_price=100.0,
            expiration=date(2026, 10, 2),
            strategies=(PutStrategy(**{**vorgabe, **overrides}),),
        )

    def _inhalt(self, analyse: OptionsAnalysis) -> dict:  # type: ignore[type-arg]
        abschnitt = dokument(options=analyse)["abschnitte"][
            ReportSection.PUT_STRATEGIEN.value
        ]
        inhalt: dict = abschnitt["inhalt"]  # type: ignore[type-arg]
        return inhalt

    def test_kurs_verfallstermin_und_version_stehen_am_abschnitt(self) -> None:
        inhalt = self._inhalt(self._analyse())

        assert inhalt["kurs"] == pytest.approx(100.0)
        assert inhalt["verfallstermin"] == "2026-10-02"
        assert inhalt["version"] == OPTIONS_ANALYSIS_VERSION

    def test_jeder_vorschlag_traegt_seine_rohgroessen_neben_den_abgeleiteten(self) -> None:
        """Wer ``annualisierte_rendite`` nicht glaubt, soll nachrechnen
        koennen -- Praemie, Strike und Restlaufzeit stehen daneben."""
        (vorschlag,) = self._inhalt(self._analyse())["vorschlaege"]

        assert vorschlag["strike"] == pytest.approx(92.0)
        assert vorschlag["premium"] == pytest.approx(1.5)
        assert vorschlag["days_to_expiration"] == 31
        assert vorschlag["annualized_return"] == pytest.approx(0.192)
        assert vorschlag["break_even"] == pytest.approx(90.5)
        assert vorschlag["liquidity"] == "ACCEPTABLE"
        assert vorschlag["liquidity_warnings"] == ["Open Interest 30"]

    def test_fehlende_nebenangaben_stehen_als_null_und_nicht_als_zahl(self) -> None:
        """``null`` und ``0`` sind im Dokument verschiedene Aussagen: kein
        Delta geliefert gegen ein Delta von null."""
        (vorschlag,) = self._inhalt(
            self._analyse(delta=None, distance_to_support_pct=None, open_interest=None)
        )["vorschlaege"]

        assert vorschlag["delta"] is None
        assert vorschlag["distance_to_support_pct"] is None
        assert vorschlag["open_interest"] is None

    def test_ein_unbekannter_berichtstermin_ist_nicht_false(self) -> None:
        (vorschlag,) = self._inhalt(self._analyse(earnings_within_term=None))["vorschlaege"]

        assert vorschlag["earnings_within_term"] is None

    def test_der_strukturvergleich_steht_aufgeloest_im_abschnitt(self) -> None:
        """ADR 0058, Festlegung 11. Er steht **neben** den Vorschlaegen und
        ersetzt keinen -- aber wenn er da ist, gehoert er ganz da hin."""
        spread = PutSpread(
            short_strike=92.0,
            hedge_strike=85.0,
            hedge_cost=0.4,
            net_credit=1.1,
            max_loss=5.9,
            capital_at_risk=590.0,
            hedge_cost_share=0.2667,
            return_on_risk=0.1864,
            hedge_liquidity=LiquidityGrade.GOOD,
            hedge_delta=0.12,
        )

        inhalt = self._inhalt(replace(self._analyse(), spread=spread))

        assert inhalt["spread_grund"] is None
        assert inhalt["spread"]["hedge_strike"] == pytest.approx(85.0)
        assert inhalt["spread"]["max_loss"] == pytest.approx(5.9)
        # Aufgeloest, nicht als Objektname: Das Enum steht als sein Wert, und
        # die nicht gelieferten Nebenangaben als ``null`` statt als Zahl.
        assert inhalt["spread"]["hedge_liquidity"] == "GOOD"
        assert inhalt["spread"]["hedge_open_interest"] is None

    def test_ein_ausgefallener_vergleich_nennt_seinen_grund(self) -> None:
        """Ein Vergleich, der einfach fehlt, sieht aus wie einer, den es nicht
        geben kann. Der Grund steht deshalb in einem **eigenen** Feld neben
        ``grund`` -- die Optionsanalyse selbst ist vollstaendig."""
        inhalt = self._inhalt(
            replace(self._analyse(), spread_reason=REASON_NO_HEDGE_STRIKE)
        )

        assert inhalt["spread"] is None
        assert inhalt["spread_grund"] == REASON_NO_HEDGE_STRIKE
        assert inhalt["grund"] is None
        assert inhalt["vorschlaege"]


class TestEmpfehlungImDokument:
    """Punkt 16 traegt die Herleitung mit, nicht nur den Namen der Stufe.

    Doc 10, Paragraph 12 verlangt fuer jede Empfehlung nachvollziehbar, worauf
    sie beruht -- und der Bericht ist die verbindliche Fassung, aus der sich
    das spaeter nicht mehr ergaenzen laesst.
    """

    @staticmethod
    def _inhalt() -> dict:  # type: ignore[type-arg]
        empfehlung = RecommendationResult(
            level=Recommendation.WATCH,
            version="1.0",
            reasons=(
                "Swing-Score 9.0 ergibt STRONG_CANDIDATE",
                "hohes Fehlsignalrisiko der KI-Einordnung: hoechstens WATCH",
            ),
            applied_caps=("hohes Fehlsignalrisiko der KI-Einordnung: hoechstens WATCH",),
        )
        abschnitt = dokument(recommendation=empfehlung)["abschnitte"][
            ReportSection.EMPFEHLUNG.value
        ]
        inhalt: dict = abschnitt["inhalt"]  # type: ignore[type-arg]
        return inhalt

    def test_stufe_begruendung_deckelungen_und_version(self) -> None:
        inhalt = self._inhalt()

        assert inhalt["stufe"] == "WATCH"
        assert len(inhalt["begruendung"]) == 2
        assert inhalt["deckelungen"] == [
            "hohes Fehlsignalrisiko der KI-Einordnung: hoechstens WATCH"
        ]
        assert inhalt["version"] == "1.0"

    def test_die_zusammenfassung_steht_ausdruecklich_als_leer(self) -> None:
        """Ein fehlender Schluessel saehe aus wie ein vergessener."""
        assert self._inhalt()["zusammenfassung"] is None
