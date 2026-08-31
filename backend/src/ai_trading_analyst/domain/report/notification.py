"""Die kompakte Zusammenfassung fuer den Benachrichtigungskanal (ADR 0040,
ADR 0047).

Eine der drei Berichtsvarianten aus Doc 10, Paragraph 6.12. Sie steht hier und
nicht in der Presentation-Schicht, weil **was** in die Meldung darf eine
fachliche Festlegung ist und keine Darstellungsfrage: Die Nachricht verlaesst
das eigene Netz.

ADR 0040 zog die Grenze bei Symbolen und Signaltypen und schloss Zahlen aus --
mit dem ausdruecklichen Vorbehalt, das neu zu entscheiden, sobald es Scores
gibt. **ADR 0047 hat das getan:** Beide Scores und die Empfehlungsstufe
gehoeren hinein, weil Doc 10, Paragraph 6.13 sie verlangt und ohne sie die
Meldung nicht sagt, ob sich der Blick lohnt. Weiterhin draussen bleibt
Freitext -- aus der Recherche wie aus der KI-Einordnung.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

from ai_trading_analyst.domain.analysis.models import AnalysisRunSummary, StockScreeningOutcome
from ai_trading_analyst.domain.earnings import EarningsFilterStatus
from ai_trading_analyst.domain.scoring import ScoreResult
from ai_trading_analyst.domain.screening import ScreeningStatus


def render_notification(summary: AnalysisRunSummary, *, timezone: str) -> tuple[str, str]:
    """Die kompakte Zusammenfassung fuer den Benachrichtigungskanal (ADR 0040).

    ``timezone`` ist die Boersenzeitzone; sie bestimmt, welchen Handelstag der
    Betreff nennt.

    Betreff und Text. Enthaelt je Kandidat Symbol, Signaltypen, beide Scores,
    die Empfehlungsstufe, das Fehlsignalrisiko als Stufe und den Hinweis auf
    einen unbekannten Berichtstermin -- **keinen Freitext**. Die Meldung
    verlaesst das eigene Netz; sie soll sagen, ob sich der Blick in den
    Bericht lohnt, und nicht der Bericht sein.

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

    zeilen = [_kandidatenzeile(outcome) for outcome in sorted(kandidaten, key=_rangfolge)]
    zeilen.append("")
    zeilen.append("S = Swing, I = Investment, je bis 10. Kein Freitext in dieser")
    zeilen.append("Meldung (ADR 0047) -- der vollstaendige Bericht:")
    zeilen.append(f"cli report --run {summary.run.id}")
    return betreff, "\n".join(zeilen)


def _rangfolge(outcome: StockScreeningOutcome) -> tuple[float, str]:
    """Bester Swing-Score zuerst, bei Gleichstand alphabetisch.

    Der zweite Schluessel ist keine Kosmetik: Ohne ihn haengt die Reihenfolge
    zweier gleich bewerteter Kandidaten an der Reihenfolge der Aktienliste,
    und zwei Laeufe derselben Lage ergaeben verschiedene Meldungen.
    """
    score = outcome.swing_score
    wert = score.value if score is not None and score.value is not None else -1.0
    return (-wert, outcome.stock.symbol)


def _kandidatenzeile(outcome: StockScreeningOutcome) -> str:
    signale = " + ".join(sorted(typ.value for typ in outcome.result.fired_signal_types))
    zeile = f"{outcome.stock.symbol}  {signale}"

    empfehlung = outcome.recommendation
    if empfehlung is not None:
        zeile += f"  -- {empfehlung.level.value}"
    # Ein fehlender Score steht als Strich und nicht als Null: Null hiesse
    # geprueft und schlecht (Doc 09).
    zeile += f"  [S {_zahl(outcome.swing_score)} | I {_zahl(outcome.investment_score)}]"

    einordnung = outcome.technical_assessment
    if einordnung is not None and einordnung.false_signal_risk is not None:
        # Eine Stufe aus einer gegen ein Schema validierten Antwort (ADR 0026),
        # kein Freitext des Modells.
        zeile += f"  -- Fehlsignalrisiko {einordnung.false_signal_risk.value}"

    if outcome.earnings is not None and outcome.earnings.status is EarningsFilterStatus.UNKNOWN:
        # Doc 10, Paragraph 6.5: ein unbekannter Termin ist ein Datenrisiko
        # und wird ausdruecklich gekennzeichnet.
        zeile += "  -- Earnings-Termin unbekannt"
    return zeile


def _zahl(score: ScoreResult | None) -> str:
    """Der Gesamtwert oder ein Strich -- nie eine Null fuer einen fehlenden."""
    if score is None or score.value is None:
        return "--"
    return f"{score.value:.1f}"
