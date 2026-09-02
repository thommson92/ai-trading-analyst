"""Die Kurzfassung sagt, ob sich der Blick lohnt -- mehr nicht (ADR 0040,
ADR 0047, ADR 0055).

Die entscheidenden Zusicherungen sind die **negativen**: Was nicht in der
Meldung stehen darf, steht dort auch nicht. Sie verlaesst das eigene Netz.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from ai_trading_analyst.domain.analysis import (
    AnalysisRun,
    AnalysisRunSummary,
    RunStatus,
    Stock,
    StockScreeningOutcome,
)
from ai_trading_analyst.domain.earnings import EarningsFilterStatus
from ai_trading_analyst.domain.options import OptionsAnalysis, OptionsStatus
from ai_trading_analyst.domain.report import render_notification
from ai_trading_analyst.domain.scoring import (
    ComponentName,
    MetricThresholds,
    Recommendation,
    RecommendationParameters,
    ScoreComponent,
    ScoreConfidence,
    ScoreKind,
    ScoreResult,
    ScoreStatus,
    ScoringParameters,
    derive_recommendation,
)
from ai_trading_analyst.domain.screening import (
    ScreeningResult,
    ScreeningStatus,
    SignalType,
)
from ai_trading_analyst.domain.technical import (
    FalseSignalRisk,
    TechnicalAssessment,
    TechnicalAssessmentStatus,
)
from tests.unit.domain.report.conftest import (
    JETZT,
    make_earnings,
    make_fundamentals,
    make_options,
    make_outcome,
    make_put_strategy,
    make_research,
    make_technical,
)

_NY = "America/New_York"

REGELN = ScoringParameters(
    swing_weights={},
    long_term_weights={},
    thresholds={},
    analyst_buy_share=MetricThresholds(boundaries=(0.4, 0.6, 0.7, 0.8), higher_is_better=True),
    analyst_max_age_days=62,
    minimum_coverage=0.6,
    normal_confidence_coverage=0.8,
    recommendation=RecommendationParameters(
        strong_candidate=8.0,
        candidate=6.0,
        watch=4.0,
        investment_strong=8.0,
        investment_weak=4.0,
        cap_false_signal_high=Recommendation.WATCH,
        cap_earnings_unknown=Recommendation.CANDIDATE,
        version="1.0",
    ),
    swing_version="1.0",
    long_term_version="1.0",
)
"""Nur die Empfehlungsregeln zaehlen hier -- die Meldung rechnet keinen Score,
sie zeigt ihn."""


def zusammenfassung(
    *outcomes: StockScreeningOutcome, aktien: int = 4
) -> AnalysisRunSummary:
    kandidaten = sum(
        outcome.result.status is ScreeningStatus.CANDIDATE for outcome in outcomes
    )
    run = AnalysisRun(
        id=uuid.UUID("11111111-2222-3333-4444-555555555555"),
        status=RunStatus.COMPLETED,
        started_at=datetime(2026, 8, 30, 21, 15, tzinfo=UTC),
        number_of_stocks=aktien,
        candidates_found=kandidaten,
    )
    return AnalysisRunSummary(run=run, outcomes=tuple(outcomes), errors=())


def punktzahl(wert: float | None, kind: ScoreKind) -> ScoreResult:
    vollstaendig = wert is not None
    return ScoreResult(
        kind=kind,
        status=ScoreStatus.COMPLETED if vollstaendig else ScoreStatus.INSUFFICIENT_DATA,
        version="1.0",
        components=(
            ScoreComponent(
                name=ComponentName.TECHNICAL_SIGNALS,
                weight=1.0,
                value=wert,
                effective_weight=1.0 if vollstaendig else 0.0,
            ),
        ),
        coverage=1.0 if vollstaendig else 0.0,
        confidence=ScoreConfidence.NORMAL if vollstaendig else ScoreConfidence.INSUFFICIENT_DATA,
        value=wert,
    )


def kandidat(
    symbol: str,
    *,
    swing: float | None,
    investment: float | None,
    voll: bool = False,
    options: OptionsAnalysis | None = None,
) -> StockScreeningOutcome:
    """Ein Kandidat mit Scores und der Stufe, die sich daraus ergibt.

    ``voll`` erzeugt die **laengstmoegliche** Zeile: drei Signale, das
    Fehlsignalrisiko und der Earnings-Hinweis. Nur damit laesst sich die
    Kuerzungsgrenze belegen -- an einer kurzen Zeile gemessen waere sie zu
    optimistisch.
    """
    swing_score = punktzahl(swing, ScoreKind.SWING)
    investment_score = punktzahl(investment, ScoreKind.LONG_TERM)
    zusatz: dict[str, object] = {}
    if voll:
        zusatz = {
            "result": ScreeningResult(
                status=ScreeningStatus.CANDIDATE, fired_signal_types=frozenset(SignalType)
            ),
            "technical_assessment": einordnung(FalseSignalRisk.MEDIUM),
            "earnings": make_earnings(EarningsFilterStatus.UNKNOWN),
            # Der laengstmoegliche Block traegt seit ADR 0055 auch die
            # Put-Zeile -- ohne sie waere die Kuerzungsmessung zu optimistisch.
            "options": make_options(),
        }
    if options is not None:
        zusatz["options"] = options
    return make_outcome(
        stock=Stock(id=uuid.uuid5(uuid.NAMESPACE_DNS, symbol), symbol=symbol, exchange="NASDAQ"),
        swing_score=swing_score,
        investment_score=investment_score,
        recommendation=derive_recommendation(
            swing=swing_score,
            investment=investment_score,
            false_signal_risk=None,
            earnings_status=None,
            parameters=REGELN,
        ),
        **zusatz,
    )


def einordnung(risiko: FalseSignalRisk) -> TechnicalAssessment:
    return TechnicalAssessment(
        status=TechnicalAssessmentStatus.COMPLETED,
        evaluated_at=JETZT,
        model="fake",
        prompt_version="fake-v1",
        interpreted_analysis_version="technical-v3",
        summary="Einordnung",
        false_signal_risk=risiko,
        false_signal_risks=("Ein Freitext-Risiko, das nirgends auftauchen darf",),
        confidence=0.6,
    )


class TestWasDrinSteht:
    def test_betreff_nennt_tag_und_anzahl(self) -> None:
        betreff, _ = render_notification(zusammenfassung(make_outcome()), timezone=_NY)
        assert betreff == "Analyse-Lauf 2026-08-30: 1 Kandidat(en)"

    def test_jeder_block_nennt_symbol_und_signalzahl_statt_signalnamen(self) -> None:
        """ADR 0055: gezaehlt statt aufgezaehlt -- die Gesamtzahl kommt aus
        der Regelmenge, nicht als fest verdrahtete Drei."""
        _, text = render_notification(zusammenfassung(make_outcome()), timezone=_NY)
        assert f"AAPL -- 2/{len(SignalType)} Signale" in text
        assert "EMA5_EMA20_CROSS" not in text
        assert "RSI_CROSS" not in text

    def test_das_fehlsignalrisiko_erscheint_als_stufe(self) -> None:
        _, text = render_notification(
            zusammenfassung(make_outcome(technical_assessment=einordnung(FalseSignalRisk.HIGH))),
            timezone=_NY,
        )
        assert "Risiko HIGH" in text

    def test_bloecke_sind_durch_leerzeilen_getrennt(self) -> None:
        """ADR 0055: ein Block je Aktie, dazwischen eine Leerzeile -- auch
        vor der Legende."""
        _, text = render_notification(
            zusammenfassung(
                kandidat("AAA", swing=7.0, investment=5.0),
                kandidat("BBB", swing=6.0, investment=5.0),
            ),
            timezone=_NY,
        )
        bloecke = text.split("\n\n")
        assert len(bloecke) == 3  # zwei Kandidaten + Legende
        assert bloecke[0].startswith("AAA -- ")
        assert bloecke[1].startswith("BBB -- ")
        assert "cli report" in bloecke[2]

    def test_ein_unbekannter_earnings_termin_wird_genannt(self) -> None:
        """Doc 10, Paragraph 6.5: ein Datenrisiko, das ausdruecklich
        gekennzeichnet wird."""
        _, text = render_notification(
            zusammenfassung(
                make_outcome(earnings=make_earnings(EarningsFilterStatus.UNKNOWN, "x"))
            ),
            timezone=_NY,
        )
        assert "Earnings-Termin unbekannt" in text

    def test_der_verweis_auf_den_vollen_bericht_nennt_die_lauf_id(self) -> None:
        _, text = render_notification(zusammenfassung(make_outcome()), timezone=_NY)
        assert "cli report --run 11111111-2222-3333-4444-555555555555" in text


class TestHandelstag:
    def test_der_betreff_nennt_den_boersentag_nicht_den_utc_tag(self) -> None:
        """CLAUDE.md: gerechnet wird in ``America/New_York``. Ein verspaeteter
        Lauf um 21:30 New Yorker Zeit liegt in UTC schon am Folgetag -- der
        Betreff nennt trotzdem den Handelstag, an dem gescreent wurde."""
        summary = zusammenfassung(make_outcome())
        spaet = AnalysisRunSummary(
            run=AnalysisRun(
                id=summary.run.id,
                status=RunStatus.COMPLETED,
                # 2026-08-31 01:30 UTC = 2026-08-30 21:30 in New York
                started_at=datetime(2026, 8, 31, 1, 30, tzinfo=UTC),
                number_of_stocks=4,
                candidates_found=1,
            ),
            outcomes=summary.outcomes,
            errors=(),
        )

        betreff, _ = render_notification(spaet, timezone=_NY)

        assert betreff.startswith("Analyse-Lauf 2026-08-30:")


class TestWasDraussenBleibt:
    """Die Zusicherung, die ADR 0047 **nicht** gelockert hat.

    Scores und Stufe gehen jetzt hinaus (ADR 0047). Kurse, Kennzahlen und
    jeder Freitext bleiben draussen -- die Grenze verschiebt sich von "keine
    Zahlen" zu "keine Rohdaten und keine Formulierung".
    """

    def test_kein_kurs_und_keine_kennzahl(self) -> None:
        _, text = render_notification(
            zusammenfassung(
                make_outcome(
                    technical=make_technical(),
                    fundamentals=make_fundamentals(vollstaendig=True),
                )
            ),
            timezone=_NY,
        )
        assert "190.0" not in text, "der Schlusskurs steht in der Meldung"
        assert "REVENUE" not in text
        assert "Apple Inc." not in text

    def test_kein_freitext_aus_recherche_oder_einordnung(self) -> None:
        _, text = render_notification(
            zusammenfassung(
                make_outcome(
                    research=make_research(),
                    technical_assessment=einordnung(FalseSignalRisk.LOW),
                )
            ),
            timezone=_NY,
        )
        assert "Zusammenfassung" not in text
        assert "Lieferkette" not in text
        assert "Freitext-Risiko" not in text


class TestOhneKandidaten:
    def test_ein_leerer_lauf_meldet_die_zahl_der_geprueften_aktien(self) -> None:
        nicht_kandidat = make_outcome(result=ScreeningResult(status=ScreeningStatus.NOT_CANDIDATE))
        betreff, text = render_notification(
            zusammenfassung(nicht_kandidat, aktien=192), timezone=_NY
        )

        assert betreff == "Analyse-Lauf 2026-08-30: 0 Kandidat(en)"
        assert "192 Aktien" in text
        assert "AAPL" not in text


class TestScoresUndStufe:
    """ADR 0047 -- der Punkt, in dem die Meldung ADR 0040  abloest."""

    def test_beide_scores_und_die_stufe_stehen_in_der_zeile(self) -> None:
        _, text = render_notification(
            zusammenfassung(kandidat("AAPL", swing=8.6, investment=5.5)), timezone=_NY
        )

        assert "8.6" in text
        assert "5.5" in text
        assert "STRONG_CANDIDATE" in text

    def test_ein_fehlender_score_steht_als_strich_und_nicht_als_null(self) -> None:
        """Null hiesse geprueft und schlecht (Doc 09) -- in einer Meldung, die
        auf ein Smartphone geht, ist der Unterschied besonders teuer."""
        _, text = render_notification(
            zusammenfassung(kandidat("AAPL", swing=7.0, investment=None)), timezone=_NY
        )

        assert "I --" in text
        assert "I 0.0" not in text

    def test_die_legende_erklaert_die_beiden_buchstaben(self) -> None:
        _, text = render_notification(
            zusammenfassung(kandidat("AAPL", swing=7.0, investment=5.0)), timezone=_NY
        )
        assert "S = Swing" in text
        assert "I = Investment" in text

    def test_der_beste_kandidat_steht_oben(self) -> None:
        """Die Kuerzung greift am Ende des Textes. Alphabetisch sortiert
        verloere man ausgerechnet die Kandidaten, wegen derer die Meldung
        ueberhaupt geschrieben wird."""
        _, text = render_notification(
            zusammenfassung(
                kandidat("AAA", swing=4.0, investment=5.0),
                kandidat("ZZZ", swing=9.0, investment=5.0),
                kandidat("MMM", swing=6.5, investment=5.0),
            ),
            timezone=_NY,
        )

        bloecke = text.split("\n\n")[:3]
        assert [block.split(" -- ")[0] for block in bloecke] == ["ZZZ", "MMM", "AAA"]

    def test_kandidaten_ohne_score_stehen_hinten(self) -> None:
        """Nicht, weil sie schlecht waeren, sondern weil ueber sie nichts zu
        sagen ist."""
        _, text = render_notification(
            zusammenfassung(
                kandidat("OHNE", swing=None, investment=None),
                kandidat("MIT", swing=4.0, investment=5.0),
            ),
            timezone=_NY,
        )

        bloecke = text.split("\n\n")[:2]
        assert [block.split(" -- ")[0] for block in bloecke] == ["MIT", "OHNE"]

    def test_die_legende_nennt_die_kontraktpraemie(self) -> None:
        _, text = render_notification(
            zusammenfassung(kandidat("AAPL", swing=7.0, investment=5.0)), timezone=_NY
        )
        assert "Praemie je Kontrakt (Mid)" in text

    def test_bei_gleichstand_entscheidet_das_symbol(self) -> None:
        """Ohne zweiten Schluessel haengt die Reihenfolge an der Aktienliste,
        und zwei Laeufe derselben Lage ergaeben verschiedene Meldungen."""
        _, text = render_notification(
            zusammenfassung(
                kandidat("ZZZ", swing=7.0, investment=5.0),
                kandidat("AAA", swing=7.0, investment=5.0),
            ),
            timezone=_NY,
        )

        bloecke = text.split("\n\n")[:2]
        assert [block.split(" -- ")[0] for block in bloecke] == ["AAA", "ZZZ"]


class TestPutZeile:
    """ADR 0055 -- der Punkt, in dem die Meldung ADR 0047 abloest: Fuer
    empfohlene Kandidaten steht der beste Put-Vorschlag in der Meldung."""

    def test_der_beste_vorschlag_steht_mit_strike_verfall_und_kontraktpraemie(self) -> None:
        """``premium`` ist der Mid je Aktie -- 1.50 muss als ~150 $ je
        Kontrakt erscheinen, sonst stimmt die Umrechnung nicht."""
        _, text = render_notification(
            zusammenfassung(
                kandidat(
                    "AAPL",
                    swing=8.6,
                    investment=5.5,
                    options=make_options(
                        strategies=(
                            make_put_strategy(
                                strike=320.0, premium=1.50, expiration=date(2026, 10, 16)
                            ),
                        )
                    ),
                )
            ),
            timezone=_NY,
        )
        assert "Put-Verkauf: Strike 320 $, Verfall 16.10.2026, Praemie ~150 $" in text

    def test_die_erste_und_damit_beste_strategie_wird_genommen(self) -> None:
        """``strategies`` ist absteigend nach annualisierter Rendite sortiert
        -- die Meldung nimmt die erste, nicht irgendeine."""
        _, text = render_notification(
            zusammenfassung(
                kandidat(
                    "AAPL",
                    swing=7.0,
                    investment=5.0,
                    options=make_options(
                        strategies=(
                            make_put_strategy(strike=310.0, annualized_return=0.30),
                            make_put_strategy(strike=300.0, annualized_return=0.20),
                        )
                    ),
                )
            ),
            timezone=_NY,
        )
        assert "Strike 310 $" in text
        assert "Strike 300" not in text

    def test_der_strike_bleibt_eine_klare_dezimalzahl(self) -> None:
        """Kein ``:g``: Das rundete ab sieben signifikanten Stellen und
        zeigte Strikes ab einer Million wissenschaftlich notiert."""
        _, gross = render_notification(
            zusammenfassung(
                kandidat(
                    "TEUER",
                    swing=8.6,
                    investment=5.5,
                    options=make_options(
                        strategies=(make_put_strategy(strike=1050000.0, premium=2.0),)
                    ),
                )
            ),
            timezone=_NY,
        )
        _, halb = render_notification(
            zusammenfassung(
                kandidat(
                    "AAPL",
                    swing=8.6,
                    investment=5.5,
                    options=make_options(strategies=(make_put_strategy(strike=112.5),)),
                )
            ),
            timezone=_NY,
        )
        assert "Strike 1050000 $" in gross
        assert "Strike 112.5 $" in halb

    def test_kandidat_ohne_optionsdaten_sagt_das_ausdruecklich(self) -> None:
        """Fehlende Daten bleiben sichtbar fehlend -- kein Ersatzwert, keine
        stille Auslassung."""
        _, text = render_notification(
            zusammenfassung(kandidat("AAPL", swing=7.0, investment=5.0)), timezone=_NY
        )
        assert "Put-Verkauf: keine Optionsdaten" in text

    def test_insufficient_data_und_leere_strategien_sagen_dasselbe(self) -> None:
        _, ohne_daten = render_notification(
            zusammenfassung(
                kandidat(
                    "AAPL",
                    swing=7.0,
                    investment=5.0,
                    options=make_options(
                        status=OptionsStatus.INSUFFICIENT_DATA,
                        strategies=(),
                        reason="kein Verfall im Fenster",
                    ),
                )
            ),
            timezone=_NY,
        )
        _, leer = render_notification(
            zusammenfassung(
                kandidat("AAPL", swing=7.0, investment=5.0, options=make_options(strategies=()))
            ),
            timezone=_NY,
        )
        assert "Put-Verkauf: keine Optionsdaten" in ohne_daten
        assert "Put-Verkauf: keine Optionsdaten" in leer
        # Der Grund ist Freitext des Adapters und bleibt draussen.
        assert "kein Verfall im Fenster" not in ohne_daten

    def test_watch_traegt_weder_put_zeile_noch_hinweis(self) -> None:
        _, text = render_notification(
            zusammenfassung(
                kandidat("AAPL", swing=5.0, investment=5.0, options=make_options())
            ),
            timezone=_NY,
        )
        assert "WATCH" in text
        assert "Put-Verkauf" not in text
