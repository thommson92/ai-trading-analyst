"""Der Swing-Score (ADR 0041, ADR 0045 Abschnitt 4).

Alle Abbildungen hier sind **Setzungen**: Es gibt bislang keinen produktiven
Tageslauf, aus dem sich eine Verteilung ergaebe. Die Tests halten deshalb
nicht fest, dass die Zahlen richtig *gemessen* sind -- sondern dass sie die
Setzung aus dem ADR treffen und dass die begrenzende Regel greift.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

import pytest

from ai_trading_analyst.domain.analysts import (
    AnalystRecommendations,
    AnalystRecommendationStatus,
    RecommendationPeriod,
)
from ai_trading_analyst.domain.backtesting import (
    BacktestConfidence,
    BacktestResult,
    HorizonMetrics,
)
from ai_trading_analyst.domain.scoring import (
    ComponentName,
    ScoreKind,
    ScoreResult,
    ScoreStatus,
    ScoringParameters,
    compute_swing_score,
)
from ai_trading_analyst.domain.screening import (
    ScreeningResult,
    ScreeningStatus,
    SignalEvent,
    SignalType,
)
from ai_trading_analyst.domain.technical import (
    BreakoutQuality,
    RiskRewardRating,
    SwingEntryPlausibility,
    TechnicalAssessment,
    TechnicalAssessmentStatus,
    TrendStrength,
)

JETZT = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
ALLE_DREI = frozenset(SignalType)
ZWEI = frozenset({SignalType.RSI_CROSS, SignalType.EMA5_EMA20_CROSS})


def ergebnis(signale: frozenset[SignalType] = ALLE_DREI) -> ScreeningResult:
    return ScreeningResult(
        status=ScreeningStatus.CANDIDATE,
        fired_signal_types=signale,
        signal_events=tuple(
            SignalEvent(signal_type=typ, candle_index=10) for typ in sorted(signale)
        ),
    )


def statistik(
    *,
    signale: frozenset[SignalType] = ALLE_DREI,
    hit_rate: float | None = 0.7,
    confidence: BacktestConfidence = BacktestConfidence.NORMAL,
    events: int = 42,
    horizonte: tuple[int, ...] = (5, 20),
) -> BacktestResult:
    return BacktestResult(
        stock_id=uuid4(),
        signal_types=signale,
        signal_rule_version="g1",
        evaluated_at=JETZT,
        history_start=JETZT,
        history_end=JETZT,
        horizons=tuple(
            HorizonMetrics(
                horizon=h,
                raw_event_count=events,
                deduplicated_event_count=events,
                # Der laengere Horizont traegt bewusst eine andere
                # Trefferquote: So faellt auf, wenn nicht der kuerzeste
                # gewaehlt wird.
                hit_rate=hit_rate if h == min(horizonte) else 0.1,
                mean_return=0.0,
                median_return=0.0,
                max_loss=0.0,
                drawdown=0.0,
                held_above_entry_rate=0.0,
                confidence=confidence,
            )
            for h in horizonte
        ),
    )


def voten(anteil: float, *, gesamt: int = 30) -> AnalystRecommendations:
    """Eine Verteilung mit dem gewuenschten Kauf-Anteil.

    ``strong_buy`` und ``buy`` zaehlen zusammen, der Rest liegt auf ``hold``
    -- die Abbildung unterscheidet beides nicht, und das steht so im ADR.
    """
    kaufe = round(anteil * gesamt)
    return AnalystRecommendations(
        status=AnalystRecommendationStatus.COMPLETED,
        evaluated_at=JETZT,
        periods=(
            RecommendationPeriod(
                period=date(2026, 8, 1),
                strong_buy=kaufe,
                buy=0,
                hold=gesamt - kaufe,
                sell=0,
                strong_sell=0,
            ),
        ),
        source="fixture",
    )


def einordnung(
    *,
    status: TechnicalAssessmentStatus = TechnicalAssessmentStatus.COMPLETED,
    trend: TrendStrength | None = TrendStrength.STRONG,
    ausbruch: BreakoutQuality | None = BreakoutQuality.CONFIRMED,
    einstieg: SwingEntryPlausibility | None = SwingEntryPlausibility.PLAUSIBLE,
    chance_risiko: RiskRewardRating | None = RiskRewardRating.FAVOURABLE,
) -> TechnicalAssessment:
    return TechnicalAssessment(
        status=status,
        evaluated_at=JETZT,
        model="modell",
        prompt_version="p1",
        trend_strength=trend,
        breakout_quality=ausbruch,
        swing_entry_plausibility=einstieg,
        risk_reward_rating=chance_risiko,
        reason=None if status is TechnicalAssessmentStatus.COMPLETED else "provider_error",
    )


_STANDARD: Any = object()
"""Unterscheidet "nicht angegeben" von ``None``: ``assessment=None`` heisst
hier ausdruecklich "es gab keine Einordnung" und ist ein eigener Testfall."""


def rechne(
    params: ScoringParameters,
    *,
    result: ScreeningResult = _STANDARD,
    backtest: Sequence[BacktestResult] = _STANDARD,
    assessment: TechnicalAssessment | None = _STANDARD,
    analysts: AnalystRecommendations | None = _STANDARD,
) -> ScoreResult:
    return compute_swing_score(
        ergebnis() if result is _STANDARD else result,
        backtest=(statistik(),) if backtest is _STANDARD else backtest,
        assessment=einordnung() if assessment is _STANDARD else assessment,
        analysts=voten(0.9) if analysts is _STANDARD else analysts,
        parameters=params,
    )


def teilwert(score: ScoreResult, name: ComponentName) -> float | None:
    (komponente,) = [k for k in score.components if k.name is name]
    return komponente.value


def teilwert_zwingend(score: ScoreResult, name: ComponentName) -> float:
    """Fuer Vergleiche zweier Teilwerte: Ohne die Pruefung verglichen zwei
    ``None`` gegeneinander und der Test saehe gruen aus."""
    wert = teilwert(score, name)
    assert wert is not None
    return wert


class TestTechnischeSignale:
    def test_drei_von_drei_sind_zehn(self, scoring_params: ScoringParameters) -> None:
        score = rechne(scoring_params)
        assert teilwert(score, ComponentName.TECHNICAL_SIGNALS) == 10.0

    def test_zwei_von_drei_sind_sechs(self, scoring_params: ScoringParameters) -> None:
        score = rechne(
            scoring_params, result=ergebnis(ZWEI), backtest=(statistik(signale=ZWEI),)
        )
        assert teilwert(score, ComponentName.TECHNICAL_SIGNALS) == 6.0


class TestSignalstatistik:
    def test_die_trefferquote_des_kuerzesten_horizonts_zaehlt(
        self, scoring_params: ScoringParameters
    ) -> None:
        score = rechne(scoring_params)
        assert teilwert(score, ComponentName.SIGNAL_STATISTICS) == 7.0

    def test_massgeblich_ist_die_heute_ausgeloeste_kombination(
        self, scoring_params: ScoringParameters
    ) -> None:
        """Eine Statistik zu einer anderen Kombination waere die Statistik
        eines anderen Ereignisses."""
        score = rechne(
            scoring_params, result=ergebnis(ALLE_DREI), backtest=(statistik(signale=ZWEI),)
        )
        assert teilwert(score, ComponentName.SIGNAL_STATISTICS) is None

    def test_die_passende_wird_aus_mehreren_herausgesucht(
        self, scoring_params: ScoringParameters
    ) -> None:
        score = rechne(
            scoring_params,
            backtest=(statistik(signale=ZWEI, hit_rate=0.1), statistik(hit_rate=0.9)),
        )
        assert teilwert(score, ComponentName.SIGNAL_STATISTICS) == 9.0

    def test_ohne_statistik_fehlt_die_komponente(
        self, scoring_params: ScoringParameters
    ) -> None:
        score = rechne(scoring_params, backtest=())
        assert teilwert(score, ComponentName.SIGNAL_STATISTICS) is None

    def test_ohne_trefferquote_fehlt_sie_ebenfalls(
        self, scoring_params: ScoringParameters
    ) -> None:
        score = rechne(scoring_params, backtest=(statistik(hit_rate=None),))
        assert teilwert(score, ComponentName.SIGNAL_STATISTICS) is None


class TestKonfidenzDeckelt:
    def test_eine_duenne_stichprobe_deckelt_den_teilwert_auf_sechs(
        self, scoring_params: ScoringParameters
    ) -> None:
        """Die erste der begrenzenden Regeln aus ADR 0041, Abschnitt 4."""
        score = rechne(
            scoring_params,
            backtest=(
                statistik(hit_rate=0.9, confidence=BacktestConfidence.LOW_SAMPLE, events=12),
            ),
        )
        assert teilwert(score, ComponentName.SIGNAL_STATISTICS) == 6.0
        assert any("gedeckelt" in risiko for risiko in score.limiting_risks)

    def test_unter_der_obergrenze_deckelt_sie_nicht(
        self, scoring_params: ScoringParameters
    ) -> None:
        """Ein Deckel, der auch nach unten wirkte, machte aus 4,0 eine 6,0 --
        er soll begrenzen, nicht anheben."""
        score = rechne(
            scoring_params,
            backtest=(
                statistik(hit_rate=0.4, confidence=BacktestConfidence.LOW_SAMPLE, events=12),
            ),
        )
        assert teilwert(score, ComponentName.SIGNAL_STATISTICS) == 4.0
        assert score.limiting_risks == ()

    def test_eine_untragbare_stichprobe_laesst_die_komponente_entfallen(
        self, scoring_params: ScoringParameters
    ) -> None:
        """Eine Trefferquote aus drei Ereignissen ist keine Trefferquote."""
        score = rechne(
            scoring_params,
            backtest=(
                statistik(
                    hit_rate=1.0, confidence=BacktestConfidence.INSUFFICIENT_DATA, events=3
                ),
            ),
        )
        assert teilwert(score, ComponentName.SIGNAL_STATISTICS) is None
        assert any("Komponente entfaellt" in risiko for risiko in score.limiting_risks)


class TestChartSetup:
    def test_das_mittel_der_drei_einstufungen(self, scoring_params: ScoringParameters) -> None:
        score = rechne(
            scoring_params,
            assessment=einordnung(
                trend=TrendStrength.MODERATE,  # 7
                ausbruch=BreakoutQuality.NO_BREAKOUT,  # 4
                einstieg=SwingEntryPlausibility.QUESTIONABLE,  # 5
            ),
        )
        assert teilwert(score, ComponentName.CHART_SETUP) == pytest.approx(5.3)

    def test_kein_ausbruch_ist_besser_als_ein_gescheiterter(
        self, scoring_params: ScoringParameters
    ) -> None:
        """"Es gibt keinen Ausbruch" ist ein anderer Befund als "der Ausbruch
        ist gescheitert" -- der Docstring des Enums sagt das, und die
        Abbildung soll ihn nicht wieder einebnen (ADR 0045)."""
        ohne = rechne(scoring_params, assessment=einordnung(ausbruch=BreakoutQuality.NO_BREAKOUT))
        gescheitert = rechne(
            scoring_params, assessment=einordnung(ausbruch=BreakoutQuality.FAILED)
        )
        assert teilwert_zwingend(ohne, ComponentName.CHART_SETUP) > teilwert_zwingend(
            gescheitert, ComponentName.CHART_SETUP
        )

    def test_gemittelt_wird_ueber_die_vorhandenen_einstufungen(
        self, scoring_params: ScoringParameters
    ) -> None:
        score = rechne(scoring_params, assessment=einordnung(ausbruch=None, einstieg=None))
        assert teilwert(score, ComponentName.CHART_SETUP) == 10.0

    def test_ohne_einordnung_fehlt_die_komponente(
        self, scoring_params: ScoringParameters
    ) -> None:
        score = rechne(scoring_params, assessment=None)
        assert teilwert(score, ComponentName.CHART_SETUP) is None

    def test_eine_ausgefallene_einordnung_ebenfalls(
        self, scoring_params: ScoringParameters
    ) -> None:
        score = rechne(
            scoring_params,
            assessment=einordnung(status=TechnicalAssessmentStatus.UNAVAILABLE),
        )
        assert teilwert(score, ComponentName.CHART_SETUP) is None

    def test_eine_einordnung_ganz_ohne_einstufungen_ebenfalls(
        self, scoring_params: ScoringParameters
    ) -> None:
        score = rechne(
            scoring_params, assessment=einordnung(trend=None, ausbruch=None, einstieg=None)
        )
        assert teilwert(score, ComponentName.CHART_SETUP) is None


class TestChanceRisiko:
    @pytest.mark.parametrize(
        ("einstufung", "erwartet"),
        [
            (RiskRewardRating.FAVOURABLE, 10.0),
            (RiskRewardRating.BALANCED, 6.0),
            (RiskRewardRating.UNFAVOURABLE, 2.0),
        ],
    )
    def test_die_drei_einstufungen(
        self,
        scoring_params: ScoringParameters,
        einstufung: RiskRewardRating,
        erwartet: float,
    ) -> None:
        score = rechne(scoring_params, assessment=einordnung(chance_risiko=einstufung))
        assert teilwert(score, ComponentName.CHANCE_RISK) == erwartet

    def test_nicht_beurteilbar_ist_kein_teilwert(
        self, scoring_params: ScoringParameters
    ) -> None:
        """``NOT_ASSESSABLE`` heisst, dass das Verhaeltnis gar nicht
        berechnet werden konnte (ADR 0026) -- nicht, dass es schlecht ist."""
        score = rechne(
            scoring_params, assessment=einordnung(chance_risiko=RiskRewardRating.NOT_ASSESSABLE)
        )
        assert teilwert(score, ComponentName.CHANCE_RISK) is None


class TestNewsUndEreignislage:
    """Die Komponente steht auf der gezaehlten Analystenverteilung (ADR 0046).

    Nicht auf der Recherche: Deren Faktoren sind Freitext, und aus Freitext
    entsteht nie ein Teilwert. Eine Verengung der Komponente, kein Austausch.
    """

    def test_ein_hoher_kauf_anteil_ergibt_den_hoechsten_teilwert(
        self, scoring_params: ScoringParameters
    ) -> None:
        score = rechne(scoring_params, analysts=voten(0.95))
        assert teilwert(score, ComponentName.NEWS_AND_EVENTS) == 10.0

    def test_ein_niedriger_den_niedrigsten(self, scoring_params: ScoringParameters) -> None:
        score = rechne(scoring_params, analysts=voten(0.05))
        assert teilwert(score, ComponentName.NEWS_AND_EVENTS) == 2.0

    def test_starke_und_einfache_kaufempfehlungen_zaehlen_beide(
        self, scoring_params: ScoringParameters
    ) -> None:
        """Der Anteil ist ``(strong_buy + buy) / total``.

        Die uebrigen Tests legen alle Kauf-Voten auf ``strong_buy`` -- eine
        Formel, die nur den starken Kauf zaehlt, kaeme dort mit demselben
        Ergebnis durch. Hier liegt die Mehrheit ausdruecklich auf ``buy``.
        """
        gemischt = AnalystRecommendations(
            status=AnalystRecommendationStatus.COMPLETED,
            evaluated_at=JETZT,
            periods=(
                RecommendationPeriod(
                    period=date(2026, 8, 1),
                    strong_buy=4,
                    buy=20,
                    hold=6,
                    sell=0,
                    strong_sell=0,
                ),
            ),
            source="fixture",
        )

        score = rechne(scoring_params, analysts=gemischt)

        # 24 von 30 sind 80 Prozent -- das vierte Fuenftel. Nur der starke
        # Kauf waeren 13 Prozent und damit das unterste.
        (komponente,) = [
            k for k in score.components if k.name is ComponentName.NEWS_AND_EVENTS
        ]
        assert komponente.value == 8.0
        assert "80%" in (komponente.reason or "")

    def test_verkaufsempfehlungen_senken_den_anteil(
        self, scoring_params: ScoringParameters
    ) -> None:
        """Sie zaehlen im Nenner mit. Ein Zaehler ueber den Kauf-Voten allein
        und ein Nenner ohne die Verkaeufe waere kein Anteil."""
        ueberwiegend_verkauf = AnalystRecommendations(
            status=AnalystRecommendationStatus.COMPLETED,
            evaluated_at=JETZT,
            periods=(
                RecommendationPeriod(
                    period=date(2026, 8, 1),
                    strong_buy=3,
                    buy=3,
                    hold=4,
                    sell=10,
                    strong_sell=10,
                ),
            ),
            source="fixture",
        )

        score = rechne(scoring_params, analysts=ueberwiegend_verkauf)

        assert teilwert(score, ComponentName.NEWS_AND_EVENTS) == 2.0

    def test_die_zahl_der_voten_steht_in_der_begruendung(
        self, scoring_params: ScoringParameters
    ) -> None:
        """Ein Anteil von 100 Prozent aus drei Voten ist etwas anderes als
        einer aus vierzig."""
        score = rechne(scoring_params, analysts=voten(0.9, gesamt=7))
        (komponente,) = [
            k for k in score.components if k.name is ComponentName.NEWS_AND_EVENTS
        ]
        assert "7 Voten" in (komponente.reason or "")

    def test_ohne_abruf_fehlt_die_komponente(self, scoring_params: ScoringParameters) -> None:
        score = rechne(scoring_params, analysts=None)
        assert teilwert(score, ComponentName.NEWS_AND_EVENTS) is None

    @pytest.mark.parametrize(
        "status", [AnalystRecommendationStatus.UNKNOWN, AnalystRecommendationStatus.UNAVAILABLE]
    )
    def test_ohne_abdeckung_und_bei_ausfall_ebenfalls(
        self, scoring_params: ScoringParameters, status: AnalystRecommendationStatus
    ) -> None:
        """"Der Anbieter fuehrt das Symbol nicht" ist keine Meinung, und ein
        Ausfall erst recht keine (ADR 0043)."""
        ohne = AnalystRecommendations(
            status=status, evaluated_at=JETZT, reason="no_coverage", source="fixture"
        )
        score = rechne(scoring_params, analysts=ohne)
        assert teilwert(score, ComponentName.NEWS_AND_EVENTS) is None

    def test_ein_monatsstand_ohne_voten_ergibt_keinen_anteil(
        self, scoring_params: ScoringParameters
    ) -> None:
        """Sonst waere es eine Division durch null -- und ein Anteil ohne
        Nenner ist keiner."""
        leer = AnalystRecommendations(
            status=AnalystRecommendationStatus.COMPLETED,
            evaluated_at=JETZT,
            periods=(
                RecommendationPeriod(
                    period=date(2026, 8, 1),
                    strong_buy=0,
                    buy=0,
                    hold=0,
                    sell=0,
                    strong_sell=0,
                ),
            ),
            source="fixture",
        )
        score = rechne(scoring_params, analysts=leer)
        assert teilwert(score, ComponentName.NEWS_AND_EVENTS) is None


class TestNochNichtGebauteKomponenten:
    def test_die_optionsattraktivitaet_steht_als_luecke_in_der_liste(
        self, scoring_params: ScoringParameters
    ) -> None:
        """Sie mit 0 zu bewerten hiesse zu behaupten, sie sei geprueft und
        schlecht (Doc 09). Sie wegzulassen verschwiege, dass sie fehlt."""
        score = rechne(scoring_params)
        assert score.missing_components == (ComponentName.OPTIONS_ATTRACTIVENESS,)
        assert score.coverage == pytest.approx(0.9)

    def test_der_beste_kandidat_bekommt_trotzdem_einen_score(
        self, scoring_params: ScoringParameters
    ) -> None:
        score = rechne(scoring_params, backtest=(statistik(hit_rate=1.0),))
        assert score.kind is ScoreKind.SWING
        assert score.status is ScoreStatus.COMPLETED
        assert score.value == 10.0


class TestZuWenigGrundlage:
    def test_ohne_statistik_und_ohne_einordnung_entsteht_kein_score(
        self, scoring_params: ScoringParameters
    ) -> None:
        """Uebrig blieben allein die technischen Signale mit 25 Prozent --
        unter der Untergrenze von 60."""
        score = rechne(scoring_params, backtest=(), assessment=None)
        assert score.status is ScoreStatus.INSUFFICIENT_DATA
        assert score.value is None

    def test_ein_ausfall_der_ki_einordnung_kostet_den_score_nicht_mehr(
        self, scoring_params: ScoringParameters
    ) -> None:
        """Der Befund aus Stufe 1, erledigt (ADR 0046).

        Chart-Setup und Chance-Risiko haengen beide an derselben Einordnung;
        faellt sie aus, gehen 30 Prozentpunkte zugleich verloren. Solange die
        News-Komponente fehlte, blieben 50 Prozent -- unter der Untergrenze,
        und der Score entfiel, obwohl die beiden nachrechenbaren Komponenten
        vorlagen. Mit der News-Komponente sind es 60, also genau die Leiter,
        die ADR 0041 vorgesehen hatte.
        """
        score = rechne(scoring_params, assessment=None)

        assert score.coverage == pytest.approx(0.6)
        assert score.status is ScoreStatus.COMPLETED
        assert teilwert(score, ComponentName.SIGNAL_STATISTICS) == 7.0

    def test_faellt_zusaetzlich_der_analystenabruf_aus_entsteht_kein_score(
        self, scoring_params: ScoringParameters
    ) -> None:
        """Bei 50 Prozent ist Schluss -- richtig so, und jetzt
        ausgeschrieben statt ueberraschend."""
        score = rechne(scoring_params, assessment=None, analysts=None)

        assert score.coverage == pytest.approx(0.5)
        assert score.status is ScoreStatus.INSUFFICIENT_DATA
