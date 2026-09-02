"""Die kompakte Zusammenfassung fuer den Benachrichtigungskanal (ADR 0040,
ADR 0047, ADR 0055).

Eine der drei Berichtsvarianten aus Doc 10, Paragraph 6.12. Sie steht hier und
nicht in der Presentation-Schicht, weil **was** in die Meldung darf eine
fachliche Festlegung ist und keine Darstellungsfrage: Die Nachricht verlaesst
das eigene Netz.

ADR 0040 zog die Grenze bei Symbolen und Signaltypen und schloss Zahlen aus --
mit dem ausdruecklichen Vorbehalt, das neu zu entscheiden, sobald es Scores
gibt. ADR 0047 hat das getan: Beide Scores und die Empfehlungsstufe gehoeren
hinein. **ADR 0055 formt daraus Bloecke:** Signale werden gezaehlt statt
aufgezaehlt, und fuer empfohlene Kandidaten steht der beste Put-Vorschlag mit
Strike, Verfall und Praemie dabei -- er ist der Zweck der Meldung, nicht
Beiwerk. Weiterhin draussen bleibt Freitext -- aus der Recherche wie aus der
KI-Einordnung.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

from ai_trading_analyst.domain.analysis.models import AnalysisRunSummary, StockScreeningOutcome
from ai_trading_analyst.domain.earnings import EarningsFilterStatus
from ai_trading_analyst.domain.options import KONTRAKTGROESSE, OptionsStatus
from ai_trading_analyst.domain.scoring import Recommendation, ScoreResult
from ai_trading_analyst.domain.screening import ScreeningStatus, SignalType

_EMPFOHLENE_STUFEN = frozenset({Recommendation.STRONG_CANDIDATE, Recommendation.CANDIDATE})
"""Nur diese Stufen tragen die Put-Zeile (ADR 0055): Fuer sie ist der
Vorschlag der Zweck der Meldung; bei WATCH und darunter waere er eine
Handlungsaufforderung, die die Stufe gerade nicht ausspricht."""


def render_notification(summary: AnalysisRunSummary, *, timezone: str) -> tuple[str, str]:
    """Die kompakte Zusammenfassung fuer den Benachrichtigungskanal (ADR 0055).

    ``timezone`` ist die Boersenzeitzone; sie bestimmt, welchen Handelstag der
    Betreff nennt.

    Betreff und Text. Je Kandidat ein Block aus zwei Zeilen -- Symbol, Stufe,
    Signalzahl, Fehlsignalrisiko, beide Scores, Earnings-Hinweis -- und fuer
    STRONG_CANDIDATE/CANDIDATE eine dritte Zeile mit dem besten
    Put-Vorschlag. **Kein Freitext.** Die Meldung verlaesst das eigene Netz;
    sie soll sagen, ob sich der Blick in den Bericht lohnt, und nicht der
    Bericht sein.

    **Sortiert nach Swing-Score, absteigend.** Die Kuerzung des Kanals greift
    am Ende des Textes; alphabetisch sortiert verloere man damit ausgerechnet
    die Kandidaten, wegen derer die Meldung geschrieben wird. Kandidaten ohne
    Score stehen hinten -- nicht, weil sie schlecht waeren, sondern weil ueber
    sie nichts zu sagen ist.
    """
    kandidaten = [
        outcome
        for outcome in summary.outcomes
        if outcome.result.status is ScreeningStatus.CANDIDATE
    ]
    # Der Handelstag ist der an der Boerse, nicht der in UTC (CLAUDE.md: der
    # Scheduler rechnet in America/New_York). Ein Lauf nach 20:00 New Yorker
    # Zeit -- etwa ein verspaeteter innerhalb der Nachholfrist -- liegt in UTC
    # bereits am Folgetag und truege sonst das falsche Datum im Betreff.
    tag = summary.run.started_at.astimezone(ZoneInfo(timezone)).date().isoformat()
    betreff = f"Analyse-Lauf {tag}: {len(kandidaten)} Kandidat(en)"
    if not kandidaten:
        return betreff, (
            f"Der Lauf ueber {summary.run.number_of_stocks} Aktien fand keinen Kandidaten."
        )

    bloecke = [_kandidatenblock(outcome) for outcome in sorted(kandidaten, key=_rangfolge)]
    legende = "\n".join(
        (
            "S = Swing, I = Investment, je bis 10. Praemie je Kontrakt (Mid).",
            "Kein Freitext in dieser Meldung (ADR 0055) -- der vollstaendige Bericht:",
            f"cli report --run {summary.run.id}",
        )
    )
    return betreff, "\n\n".join([*bloecke, legende])


def _rangfolge(outcome: StockScreeningOutcome) -> tuple[float, str]:
    """Bester Swing-Score zuerst, bei Gleichstand alphabetisch.

    Der zweite Schluessel ist keine Kosmetik: Ohne ihn haengt die Reihenfolge
    zweier gleich bewerteter Kandidaten an der Reihenfolge der Aktienliste,
    und zwei Laeufe derselben Lage ergaeben verschiedene Meldungen.
    """
    score = outcome.swing_score
    wert = score.value if score is not None and score.value is not None else -1.0
    return (-wert, outcome.stock.symbol)


def _kandidatenblock(outcome: StockScreeningOutcome) -> str:
    """Zwei Infozeilen je Aktie, dazu fuer empfohlene Stufen die Put-Zeile
    (ADR 0055). Die Bloecke trennt ``render_notification`` per Leerzeile."""
    kopf = [outcome.stock.symbol]

    empfehlung = outcome.recommendation
    if empfehlung is not None:
        kopf.append(empfehlung.level.value)

    # Gezaehlt statt aufgezaehlt (ADR 0055): Die Namen unterscheiden in einer
    # Schwellenregel nichts, die Anzahl schon. Die Gesamtzahl kommt aus der
    # Regelmenge selbst -- sie ist mit ADR 0056 von drei auf fuenf gewachsen,
    # ohne dass diese Zeile sich aendern musste.
    kopf.append(f"{len(outcome.result.fired_signal_types)}/{len(SignalType)} Signale")

    einordnung = outcome.technical_assessment
    if einordnung is not None and einordnung.false_signal_risk is not None:
        # Eine Stufe aus einer gegen ein Schema validierten Antwort (ADR 0026),
        # kein Freitext des Modells.
        kopf.append(f"Risiko {einordnung.false_signal_risk.value}")

    # Ein fehlender Score steht als Strich und nicht als Null: Null hiesse
    # geprueft und schlecht (Doc 09).
    detail = f"S {_zahl(outcome.swing_score)} | I {_zahl(outcome.investment_score)}"
    if outcome.earnings is not None and outcome.earnings.status is EarningsFilterStatus.UNKNOWN:
        # Doc 10, Paragraph 6.5: ein unbekannter Termin ist ein Datenrisiko
        # und wird ausdruecklich gekennzeichnet.
        detail += " -- Earnings-Termin unbekannt"

    zeilen = [" -- ".join(kopf), detail]
    put = _put_angabe(outcome)
    if put is not None:
        zeilen.append(put)
    return "\n".join(zeilen)


def _put_angabe(outcome: StockScreeningOutcome) -> str | None:
    """Der beste Put-Vorschlag -- nur fuer STRONG_CANDIDATE und CANDIDATE.

    Fehlende Optionsdaten bleiben sichtbar fehlend (ADR 0055): Bei einer
    empfohlenen Stufe ohne verwertbare Daten steht das ausdruecklich da,
    statt still zu fehlen. WATCH und darunter tragen keine Zeile -- auch
    keinen Hinweis.

    Die Praemie ist der Mid **je Kontrakt** (``premium`` ist je Aktie,
    ``KONTRAKTGROESSE`` die Kontraktgroesse aus der Optionsdomaene); das
    ``~`` kennzeichnet die Mid-Annahme, ein Mid ist kein handelbarer Kurs
    (ADR 0048).
    """
    empfehlung = outcome.recommendation
    if empfehlung is None or empfehlung.level not in _EMPFOHLENE_STUFEN:
        return None

    optionen = outcome.options
    if (
        optionen is None
        or optionen.status is not OptionsStatus.COMPLETED
        or not optionen.strategies
    ):
        return "Put-Verkauf: keine Optionsdaten"

    # Die beste Strategie: ``strategies`` ist absteigend nach annualisierter
    # Rendite sortiert -- das ist Zusage des Datentyps, keine Annahme.
    beste = optionen.strategies[0]
    verfall = beste.expiration.strftime("%d.%m.%Y")
    return (
        f"Put-Verkauf: Strike {_strike(beste.strike)} $, Verfall {verfall}, "
        f"Praemie ~{beste.premium * KONTRAKTGROESSE:.0f} $"
    )


def _strike(wert: float) -> str:
    """Der Strike mit hoechstens zwei Nachkommastellen, ohne Nullenrest.

    Kein ``:g``: Das rundete ab sieben signifikanten Stellen und kippte ab
    einer Million in wissenschaftliche Notation -- in der einen Zeile, auf
    der gehandelt wird.
    """
    return f"{wert:.2f}".rstrip("0").rstrip(".")


def _zahl(score: ScoreResult | None) -> str:
    """Der Gesamtwert oder ein Strich -- nie eine Null fuer einen fehlenden."""
    if score is None or score.value is None:
        return "--"
    return f"{score.value:.1f}"
