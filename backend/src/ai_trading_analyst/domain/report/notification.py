"""Die kompakte Zusammenfassung fuer den Benachrichtigungskanal (ADR 0040).

Eine der drei Berichtsvarianten aus Doc 10, Paragraph 6.12. Sie steht hier und
nicht in der Presentation-Schicht, weil **was** in die Meldung darf eine
fachliche Festlegung ist und keine Darstellungsfrage: Die Nachricht verlaesst
das eigene Netz, und ADR 0040 zieht die Grenze bei Symbolen und Signaltypen --
keine Kurse, keine Kennzahlen, kein Modell-Freitext.
"""

from __future__ import annotations

from ai_trading_analyst.domain.analysis.models import AnalysisRunSummary, StockScreeningOutcome
from ai_trading_analyst.domain.earnings import EarningsFilterStatus
from ai_trading_analyst.domain.screening import ScreeningStatus


def render_notification(summary: AnalysisRunSummary) -> tuple[str, str]:
    """Die kompakte Zusammenfassung fuer den Benachrichtigungskanal (ADR 0040).

    Betreff und Text. Enthaelt Symbole, Signaltypen, das Fehlsignalrisiko als
    Stufe und den Hinweis auf einen unbekannten Berichtstermin -- **keine
    Kurse, keine Kennzahlen, keinen Freitext**. Die Meldung verlaesst das
    eigene Netz; sie soll sagen, ob sich der Blick in den Bericht lohnt, und
    nicht der Bericht sein.
    """
    kandidaten = [
        outcome
        for outcome in summary.outcomes
        if outcome.result.status is ScreeningStatus.CANDIDATE
    ]
    tag = summary.run.started_at.date().isoformat()
    betreff = f"Analyse-Lauf {tag}: {len(kandidaten)} Kandidat(en)"
    if not kandidaten:
        return betreff, (
            f"Der Lauf ueber {summary.run.number_of_stocks} Aktien fand keinen Kandidaten."
        )

    zeilen = [_kandidatenzeile(outcome) for outcome in kandidaten]
    zeilen.append("")
    zeilen.append("Keine Kurse und keine Kennzahlen in dieser Meldung (ADR 0040) --")
    zeilen.append(f"der vollstaendige Bericht: cli report --run {summary.run.id}")
    return betreff, "\n".join(zeilen)


def _kandidatenzeile(outcome: StockScreeningOutcome) -> str:
    signale = " + ".join(sorted(typ.value for typ in outcome.result.fired_signal_types))
    zeile = f"{outcome.stock.symbol}  {signale}"

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
