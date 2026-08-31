"""Der Swing Trade Score (Doc 09; ADR 0041, ADR 0045).

Sechs Komponenten, davon zwei heute noch nicht berechenbar: Die News- und
Ereignislage folgt mit ADR 0046, die Optionsattraktivitaet mit ADR 0048. Sie
stehen trotzdem in der Liste -- als ausgewiesene Luecke, nicht als Null. Sie
mit 0 zu bewerten hiesse zu behaupten, sie seien geprueft und schlecht
(Doc 09).

**Alle Abbildungen dieses Moduls sind Setzungen**, keine Messung: Es gibt
bislang keinen produktiven Tageslauf, aus dem sich eine Verteilung ergaebe
(ADR 0045, Abschnitt 4). Sie stehen deshalb hier im Code und nicht in der
Konfiguration -- eine Zahl, die man nicht gemessen hat, gewinnt nichts
dadurch, dass man sie verstellbar macht.
"""

from __future__ import annotations

from collections.abc import Sequence

from ai_trading_analyst.domain.analysts import (
    AnalystRecommendations,
    AnalystRecommendationStatus,
)
from ai_trading_analyst.domain.backtesting import BacktestConfidence, BacktestResult
from ai_trading_analyst.domain.screening import ScreeningResult
from ai_trading_analyst.domain.technical import (
    BreakoutQuality,
    RiskRewardRating,
    SwingEntryPlausibility,
    TechnicalAssessment,
    TechnicalAssessmentStatus,
    TrendStrength,
)

from .aggregate import aggregate
from .parameters import ScoringParameters
from .values import ComponentName, ScoreComponent, ScoreKind, ScoreResult

SIGNAL_TEILWERTE = {3: 10.0, 2: 6.0}
"""Drei von drei Signalen sind 10, zwei von drei sind 6 (ADR 0045).

Eine Abbildung nur dieser beiden Faelle: Unter zwei Signalen ist eine Aktie
gar kein Kandidat, und ueber einen Fall, den es nicht gibt, wird hier nichts
behauptet."""

TREND_TEILWERTE = {
    TrendStrength.STRONG: 10.0,
    TrendStrength.MODERATE: 7.0,
    TrendStrength.WEAK: 4.0,
    TrendStrength.ABSENT: 1.0,
}

AUSBRUCH_TEILWERTE = {
    BreakoutQuality.CONFIRMED: 10.0,
    BreakoutQuality.TENTATIVE: 6.0,
    BreakoutQuality.NO_BREAKOUT: 4.0,
    BreakoutQuality.FAILED: 1.0,
}
"""``NO_BREAKOUT`` bekommt 4 und nicht 1: "Es gibt keinen Ausbruch" ist ein
anderer Befund als "der Ausbruch ist gescheitert" -- der Docstring des Enums
sagt das ausdruecklich, und die Abbildung soll ihn nicht wieder einebnen."""

EINSTIEG_TEILWERTE = {
    SwingEntryPlausibility.PLAUSIBLE: 10.0,
    SwingEntryPlausibility.QUESTIONABLE: 5.0,
    SwingEntryPlausibility.IMPLAUSIBLE: 1.0,
}

CHANCE_RISIKO_TEILWERTE = {
    RiskRewardRating.FAVOURABLE: 10.0,
    RiskRewardRating.BALANCED: 6.0,
    RiskRewardRating.UNFAVOURABLE: 2.0,
}
"""``NOT_ASSESSABLE`` fehlt hier absichtlich: Es heisst, dass das Verhaeltnis
gar nicht berechnet werden konnte (ADR 0026). Die Komponente ist dann nicht
verfuegbar und wird umgewichtet."""

ANALYST_BUY_SHARE_LABEL = "ANALYST_BUY_SHARE"
"""Der Name, unter dem der Kauf-Anteil in der Mess-CSV und in der
Konfiguration steht.

Eine Konstante und keine zwei Zeichenketten: Der Name verbindet den Messlauf
(``cli ratings --watchlist --output``) mit der Auswertung
(``cli calibrate-scores``) und mit dem Konfigurationsschluessel der
Schwellen. Drei Stellen, an denen ein Tippfehler erst am Ergebnis auffiele.
"""


def analyst_buy_share(
    recommendations: AnalystRecommendations | None, *, max_age_days: int
) -> float | None:
    """Der Anteil der Kauf-Voten am juengsten Monatsstand -- oder ``None``.

    **Ein gezaehlter Anteil, keine Konsenszahl.** ADR 0043 lehnt eine
    Konsenszahl ab, weil deren Gewichte frei gewaehlt waeren; ein Anteil hat
    keine. Dasselbe ADR sagt zugleich, dass die Uebersetzung in einen
    Teilwert der Scoring-Engine zusteht -- hier ist sie.

    **Die bekannte Schwaeche gehoert dazu:** Der Anteil unterscheidet nicht
    zwischen "hold" und "sell". Zwei Titel mit je der Haelfte Kauf-Voten
    bekommen denselben Wert, auch wenn beim einen der Rest haelt und beim
    anderen verkauft. Eine Unterscheidung braeuchte Gewichte, und damit waere
    es die Konsenszahl, die ADR 0043 ausschliesst.

    ``None`` heisst hier durchgehend "keine Grundlage": kein Abruf, keine
    Abdeckung, ein Monatsstand ohne ein einziges Votum -- oder ein Stand, der
    aelter ist als ``max_age_days``. Der Teilwert entfaellt dann, statt als
    Null zu gelten.

    **Die Aktualitaetsschranke ist noetig, weil der Endpunkt keine hat.** Er
    liefert den juengsten Stand, den er kennt; verliert ein Titel seine
    Abdeckung, ist das ein Stand von vor zwei Jahren. Ohne Schranke ginge er
    als heutige "News- und Ereignislage" mit vollem Gewicht ein -- ein
    veralteter Wert ist kein fehlender, aber er behauptet Aktualitaet.
    Dasselbe Muster wie bei den Fundamentaldaten (ADR 0034).

    Gemessen wird gegen ``evaluated_at`` des Ergebnisses und nicht gegen die
    Uhr: Die Domain kennt keine (CLAUDE.md), und ein gespeichertes Ergebnis
    soll sich Jahre spaeter genauso nachrechnen lassen.

    Diese Funktion ist **die** Stelle, an der der Anteil entsteht: Die
    Kalibrierung ueber die Watchliste (``cli ratings --watchlist --output``)
    ruft dieselbe Funktion. Zwei Formeln haetten Schwellen ergeben, die zu
    den gemessenen Werten nicht passen.
    """
    if (
        recommendations is None
        or recommendations.status is not AnalystRecommendationStatus.COMPLETED
    ):
        return None
    stand = recommendations.latest
    if stand is None or stand.total == 0:
        return None
    if (recommendations.evaluated_at.date() - stand.period).days > max_age_days:
        return None
    return (stand.strong_buy + stand.buy) / stand.total


LOW_SAMPLE_OBERGRENZE = 6.0
"""Die Trefferquote einer duennen Stichprobe wird gedeckelt (ADR 0045,
Abschnitt 4). Die erste der begrenzenden Regeln aus ADR 0041, Abschnitt 4."""


def compute_swing_score(
    result: ScreeningResult,
    *,
    backtest: Sequence[BacktestResult],
    assessment: TechnicalAssessment | None,
    analysts: AnalystRecommendations | None,
    parameters: ScoringParameters,
) -> ScoreResult:
    """Der Swing-Score einer bereits qualifizierten Aktie."""
    begrenzungen: list[str] = []
    komponenten = [
        _signale(result, parameters),
        _signalstatistik(result, backtest, parameters, begrenzungen),
        _chart_setup(assessment, parameters),
        _chance_risiko(assessment, parameters),
        _news_und_ereignisse(analysts, parameters),
        ScoreComponent(
            name=ComponentName.OPTIONS_ATTRACTIVENESS,
            weight=parameters.swing_weights[ComponentName.OPTIONS_ATTRACTIVENESS],
            reason="die Optionsanalyse ist noch nicht gebaut (ADR 0048)",
        ),
    ]
    return aggregate(
        kind=ScoreKind.SWING,
        version=parameters.swing_version,
        components=komponenten,
        minimum_coverage=parameters.minimum_coverage,
        normal_confidence_coverage=parameters.normal_confidence_coverage,
        limiting_risks=begrenzungen,
    )


def _news_und_ereignisse(
    analysts: AnalystRecommendations | None, parameters: ScoringParameters
) -> ScoreComponent:
    """Die News- und Ereignislage aus der Analystenverteilung (ADR 0046).

    **Allein aus den gezaehlten Voten, nicht aus der Recherche.** ADR 0041
    nennt beide Quellen; die Faktoren des ``ResearchReport`` sind aber
    Freitext, und aus Freitext entsteht nie ein Teilwert (CLAUDE.md). Das ist
    eine Verengung der Komponente, kein Austausch -- und sie ist im ADR als
    solche ausgewiesen.
    """
    gewicht = parameters.swing_weights[ComponentName.NEWS_AND_EVENTS]
    anteil = analyst_buy_share(analysts, max_age_days=parameters.analyst_max_age_days)
    stand = analysts.latest if analysts is not None else None
    if anteil is None:
        return ScoreComponent(
            name=ComponentName.NEWS_AND_EVENTS,
            weight=gewicht,
            value=None,
            reason=_ohne_analystengrundlage(analysts, parameters),
        )
    assert stand is not None  # ``analyst_buy_share`` hat ihn bereits geprueft
    return ScoreComponent(
        name=ComponentName.NEWS_AND_EVENTS,
        weight=gewicht,
        value=parameters.analyst_buy_share.score(anteil),
        # Votenzahl **und** Monatsstand: Ein Anteil von 100 Prozent aus drei
        # Voten ist etwas anderes als einer aus vierzig, und einer von vor
        # einem halben Jahr etwas anderes als der von gestern.
        reason=f"Kauf-Anteil {anteil:.0%} aus {stand.total} Voten ({stand.period.isoformat()})",
    )


def _ohne_analystengrundlage(
    analysts: AnalystRecommendations | None, parameters: ScoringParameters
) -> str:
    """Warum es keinen Kauf-Anteil gibt -- die vier Faelle auseinandergehalten.

    Ein gemeinsamer Satz fuer alle vier stuende im Bericht und sagte nichts:
    "kein Abruf", "keine Abdeckung", "keine Voten" und "zu alt" sind vier
    verschiedene Befunde mit vier verschiedenen Folgen.
    """
    if analysts is None:
        return "die Analystenempfehlungen wurden nicht abgerufen"
    if analysts.status is not AnalystRecommendationStatus.COMPLETED:
        return f"keine Analystenempfehlungen ({analysts.reason or analysts.status.value})"
    stand = analysts.latest
    if stand is None or stand.total == 0:
        return "der juengste Monatsstand fuehrt kein einziges Votum"
    alter = (analysts.evaluated_at.date() - stand.period).days
    return (
        f"der juengste Monatsstand ist vom {stand.period.isoformat()} und damit "
        f"{alter} Tage alt (hoechstens {parameters.analyst_max_age_days})"
    )


def _signale(result: ScreeningResult, parameters: ScoringParameters) -> ScoreComponent:
    anzahl = len(result.fired_signal_types)
    teilwert = SIGNAL_TEILWERTE.get(anzahl)
    return ScoreComponent(
        name=ComponentName.TECHNICAL_SIGNALS,
        weight=parameters.swing_weights[ComponentName.TECHNICAL_SIGNALS],
        value=teilwert,
        reason=(
            f"{anzahl} von 3 Signalen"
            if teilwert is not None
            else f"{anzahl} Signale -- dafuer gibt es keine Abbildung (ADR 0045)"
        ),
    )


def _signalstatistik(
    result: ScreeningResult,
    backtest: Sequence[BacktestResult],
    parameters: ScoringParameters,
    begrenzungen: list[str],
) -> ScoreComponent:
    """Die Trefferquote des kuerzesten Horizonts, gedeckelt von ihrer Konfidenz.

    Massgeblich ist die Statistik **genau der Signalkombination**, die heute
    ausgeloest hat -- nicht die beste oder die erste. Eine Trefferquote einer
    anderen Kombination waere die Statistik eines anderen Ereignisses.
    """
    gewicht = parameters.swing_weights[ComponentName.SIGNAL_STATISTICS]

    def fehlt(grund: str) -> ScoreComponent:
        return ScoreComponent(
            name=ComponentName.SIGNAL_STATISTICS, weight=gewicht, value=None, reason=grund
        )

    passend = [e for e in backtest if e.signal_types == result.fired_signal_types]
    if not passend:
        return fehlt("keine historische Statistik zu dieser Signalkombination")
    horizonte = passend[0].horizons
    if not horizonte:
        return fehlt("die Statistik fuehrt keinen Horizont")

    kuerzester = min(horizonte, key=lambda h: h.horizon)
    if kuerzester.confidence is BacktestConfidence.INSUFFICIENT_DATA:
        # Eine Trefferquote aus drei Ereignissen ist keine Trefferquote
        # (ADR 0045, Abschnitt 4).
        begrenzungen.append(
            f"Signalstatistik ohne belastbare Stichprobe "
            f"({kuerzester.deduplicated_event_count} Ereignisse) -- Komponente entfaellt"
        )
        return fehlt(
            f"Stichprobe zu klein ({kuerzester.deduplicated_event_count} entdoppelte Ereignisse)"
        )
    if kuerzester.hit_rate is None:
        return fehlt(f"keine Trefferquote fuer Horizont {kuerzester.horizon}")

    teilwert = kuerzester.hit_rate * 10.0
    begruendung = (
        f"Trefferquote {kuerzester.hit_rate:.0%} ueber {kuerzester.horizon} Kerzen "
        f"({kuerzester.deduplicated_event_count} Ereignisse)"
    )
    if kuerzester.confidence is BacktestConfidence.LOW_SAMPLE and teilwert > LOW_SAMPLE_OBERGRENZE:
        begrenzungen.append(
            f"Signalstatistik auf duenner Stichprobe "
            f"({kuerzester.deduplicated_event_count} Ereignisse) -- Teilwert auf "
            f"{LOW_SAMPLE_OBERGRENZE:.0f} gedeckelt"
        )
        return ScoreComponent(
            name=ComponentName.SIGNAL_STATISTICS,
            weight=gewicht,
            value=LOW_SAMPLE_OBERGRENZE,
            reason=f"{begruendung}, gedeckelt wegen duenner Stichprobe",
        )
    return ScoreComponent(
        name=ComponentName.SIGNAL_STATISTICS,
        weight=gewicht,
        value=round(teilwert, 1),
        reason=begruendung,
    )


def _chart_setup(
    assessment: TechnicalAssessment | None, parameters: ScoringParameters
) -> ScoreComponent:
    gewicht = parameters.swing_weights[ComponentName.CHART_SETUP]
    if assessment is None or assessment.status is not TechnicalAssessmentStatus.COMPLETED:
        grund = (
            "die KI-Einordnung lief nicht"
            if assessment is None
            else (assessment.reason or assessment.status.value)
        )
        return ScoreComponent(
            name=ComponentName.CHART_SETUP, weight=gewicht, value=None, reason=grund
        )

    teilwerte: list[tuple[str, float]] = []
    if assessment.trend_strength is not None:
        teilwerte.append(("Trendstaerke", TREND_TEILWERTE[assessment.trend_strength]))
    if assessment.breakout_quality is not None:
        teilwerte.append(("Ausbruch", AUSBRUCH_TEILWERTE[assessment.breakout_quality]))
    if assessment.swing_entry_plausibility is not None:
        teilwerte.append(("Einstieg", EINSTIEG_TEILWERTE[assessment.swing_entry_plausibility]))

    if not teilwerte:
        return ScoreComponent(
            name=ComponentName.CHART_SETUP,
            weight=gewicht,
            value=None,
            reason="die Einordnung nennt keine der drei Einstufungen",
        )
    wert = sum(teilwert for _, teilwert in teilwerte) / len(teilwerte)
    return ScoreComponent(
        name=ComponentName.CHART_SETUP,
        weight=gewicht,
        value=round(wert, 1),
        reason=", ".join(f"{bezeichnung} {teilwert:.0f}" for bezeichnung, teilwert in teilwerte),
    )


def _chance_risiko(
    assessment: TechnicalAssessment | None, parameters: ScoringParameters
) -> ScoreComponent:
    gewicht = parameters.swing_weights[ComponentName.CHANCE_RISK]
    # Dieselbe Statuspruefung wie im Chart-Setup: Eine Einstufung an einer
    # Einordnung, die gar nicht durchlief, waere ein Wert ohne Herkunft.
    # Heute setzt der Adapter bei einem Ausfall keine Einstufungen -- aber
    # zwei Funktionen, die zwanzig Zeilen auseinanderliegen und verschieden
    # streng sind, laufen beim naechsten Umbau auseinander.
    ausgewertet = (
        assessment is not None and assessment.status is TechnicalAssessmentStatus.COMPLETED
    )
    einstufung = assessment.risk_reward_rating if ausgewertet and assessment else None
    teilwert = CHANCE_RISIKO_TEILWERTE.get(einstufung) if einstufung is not None else None
    if einstufung is None or teilwert is None:
        return ScoreComponent(
            name=ComponentName.CHANCE_RISK,
            weight=gewicht,
            value=None,
            reason=(
                "das Chance-Risiko-Verhaeltnis liess sich nicht berechnen"
                if einstufung is RiskRewardRating.NOT_ASSESSABLE
                else "keine Einstufung des Chance-Risiko-Verhaeltnisses"
            ),
        )
    return ScoreComponent(
        name=ComponentName.CHANCE_RISK,
        weight=gewicht,
        value=teilwert,
        reason=f"Einstufung {einstufung.value}",
    )
