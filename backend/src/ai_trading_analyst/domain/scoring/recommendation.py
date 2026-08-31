"""Die Empfehlungsstufe aus beiden Scores (Berichtspunkt 16; ADR 0046).

Der Tageslauf ist ein **Swing-Screener**: Er sucht Einstiege, nicht
Unternehmen. Deshalb fuehrt der Swing-Score, und der Investment-Score
korrigiert um hoechstens eine Stufe. Die beiden werden dabei **nicht zu einer
Zahl verrechnet** -- Doc 09 schliesst das aus, und zwar nicht als
Stilfrage: Ein Titel kann als Swing-Kandidat stark und als Investment schwach
sein, und genau das sichtbar zu machen ist der Zweck der Trennung.

Rechnen, nicht zuordnen -- deshalb hier und nicht im Report Generator, der
laut ADR 0039 keine neuen Fakten erzeugt.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_trading_analyst.domain.earnings import EarningsFilterStatus
from ai_trading_analyst.domain.technical import FalseSignalRisk

from .parameters import ScoringParameters
from .values import RANGFOLGE, Recommendation, ScoreResult, ScoreStatus


@dataclass(frozen=True, slots=True)
class RecommendationResult:
    """Die Stufe samt ihrer Herleitung.

    Doc 10, Paragraph 12 verlangt fuer jede Empfehlung nachvollziehbar, worauf
    sie beruht. Die Bausteine stehen deshalb am Ergebnis und nicht nur im
    Logfile -- und sie sind **gerechnet**, nicht formuliert: kein Satz stammt
    aus einem Sprachmodell (CLAUDE.md).
    """

    level: Recommendation
    version: str
    reasons: tuple[str, ...] = ()
    """Die Schritte der Ableitung in der Reihenfolge, in der sie gewirkt
    haben -- Grundstufe, Korrektur, Deckelung."""
    applied_caps: tuple[str, ...] = ()
    """Nur die Deckelungen, die tatsaechlich gegriffen haben. Ein Risiko, das
    die Stufe nicht veraendert hat, gehoert in den Bericht, aber nicht in
    diese Liste -- sonst laese sich eine unveraenderte Stufe als gedeckelte."""


def derive_recommendation(
    *,
    swing: ScoreResult | None,
    investment: ScoreResult | None,
    false_signal_risk: FalseSignalRisk | None,
    earnings_status: EarningsFilterStatus | None,
    parameters: ScoringParameters,
) -> RecommendationResult:
    """Grundstufe, Korrektur, Deckelung -- in dieser Reihenfolge.

    Die Deckelung kommt zuletzt, damit sie in jedem Fall greift. Stuende sie
    vor der Korrektur, hoebe ein guter Investment-Score die Stufe wieder
    ueber die Grenze, die ein hohes Fehlsignalrisiko gerade gezogen hat.
    """
    regeln = parameters.recommendation

    if swing is None or swing.status is ScoreStatus.INSUFFICIENT_DATA:
        return RecommendationResult(
            level=Recommendation.INSUFFICIENT_DATA,
            version=regeln.version,
            reasons=("ohne Swing-Score gibt es keine Aussage ueber den Einstieg",),
        )

    stufe = _grundstufe(swing.value, parameters)
    begruendungen = [f"Swing-Score {swing.value:.1f} ergibt {stufe.value}"]

    stufe, korrektur = _korrigiert(stufe, investment, parameters)
    if korrektur is not None:
        begruendungen.append(korrektur)

    stufe, deckelungen = _gedeckelt(stufe, false_signal_risk, earnings_status, parameters)
    begruendungen.extend(deckelungen)

    return RecommendationResult(
        level=stufe,
        version=regeln.version,
        reasons=tuple(begruendungen),
        applied_caps=tuple(deckelungen),
    )


def _grundstufe(wert: float | None, parameters: ScoringParameters) -> Recommendation:
    """Die Stufe allein aus dem Swing-Score.

    Die Grenzen liegen auf der Skala, aus der der Score selbst gebaut ist
    (2/4/6/8/10, ADR 0045) -- sie sind damit nicht geraten, sondern aus seiner
    Konstruktion abgelesen.
    """
    regeln = parameters.recommendation
    # ``wert`` ist bei COMPLETED nie None -- ``ScoreResult`` sichert das zu.
    assert wert is not None
    if wert >= regeln.strong_candidate:
        return Recommendation.STRONG_CANDIDATE
    if wert >= regeln.candidate:
        return Recommendation.CANDIDATE
    if wert >= regeln.watch:
        return Recommendation.WATCH
    return Recommendation.AVOID_FOR_NOW


def _korrigiert(
    stufe: Recommendation, investment: ScoreResult | None, parameters: ScoringParameters
) -> tuple[Recommendation, str | None]:
    """Der Investment-Score hebt oder senkt um **hoechstens eine** Stufe.

    Ein fehlender Investment-Score korrigiert **nicht**. Ihn wie einen
    schwachen zu behandeln hiesse, fehlende Daten zu bestrafen -- und das ist
    genau die Verwechslung, die das ganze System vermeidet (CLAUDE.md).
    """
    regeln = parameters.recommendation
    if investment is None or investment.status is ScoreStatus.INSUFFICIENT_DATA:
        return stufe, None
    wert = investment.value
    assert wert is not None

    if wert >= regeln.investment_strong:
        angehoben = _verschoben(stufe, +1)
        if angehoben is stufe:
            return stufe, f"Investment-Score {wert:.1f} -- bereits die hoechste Stufe"
        return angehoben, f"Investment-Score {wert:.1f} hebt auf {angehoben.value}"
    if wert <= regeln.investment_weak:
        gesenkt = _verschoben(stufe, -1)
        if gesenkt is stufe:
            return stufe, f"Investment-Score {wert:.1f} -- bereits die niedrigste Stufe"
        return gesenkt, f"Investment-Score {wert:.1f} senkt auf {gesenkt.value}"
    return stufe, f"Investment-Score {wert:.1f} veraendert die Stufe nicht"


def _gedeckelt(
    stufe: Recommendation,
    false_signal_risk: FalseSignalRisk | None,
    earnings_status: EarningsFilterStatus | None,
    parameters: ScoringParameters,
) -> tuple[Recommendation, list[str]]:
    """Begrenzende Risiken (Doc 09) -- sie koennen nur senken, nie heben.

    **Die Konfidenz der Signalstatistik steht bewusst nicht hier.** Sie laesst
    die Komponente schon entfallen (ADR 0045) und senkt damit bereits die
    Datenabdeckung; sie zusaetzlich auf die Stufe durchschlagen zu lassen
    bestrafte dieselbe Tatsache zweimal.
    """
    regeln = parameters.recommendation
    angewandt: list[str] = []
    obergrenzen: list[tuple[Recommendation, str]] = []

    if false_signal_risk is FalseSignalRisk.HIGH:
        obergrenzen.append(
            (regeln.cap_false_signal_high, "hohes Fehlsignalrisiko der KI-Einordnung")
        )
    if earnings_status is EarningsFilterStatus.UNKNOWN:
        obergrenzen.append((regeln.cap_earnings_unknown, "Berichtstermin unbekannt"))

    for grenze, grund in obergrenzen:
        if RANGFOLGE.index(stufe) > RANGFOLGE.index(grenze):
            angewandt.append(f"{grund}: hoechstens {grenze.value}")
            stufe = grenze
    return stufe, angewandt


def _verschoben(stufe: Recommendation, schritte: int) -> Recommendation:
    """Eine Stufe hoch oder runter, ohne die Rangfolge zu verlassen."""
    position = RANGFOLGE.index(stufe) + schritte
    return RANGFOLGE[max(0, min(len(RANGFOLGE) - 1, position))]
