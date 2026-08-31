"""Der Bericht als maschinenlesbares Dokument (Doc 10, Paragraph 6.12).

Die verbindliche Fassung: Genau sie wird gespeichert, und aus ihr entstehen
die lesbare Konsolenausgabe und die Kurzfassung. Sie fuehrt **immer alle
achtzehn Abschnitte** -- ein fehlender Punkt ist ein Abschnitt mit
``verfuegbar: false`` und einer Begruendung, nie ein weggelassener Schluessel.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

from ai_trading_analyst.domain.analysts import AnalystRecommendationStatus

from .values import ReportSection, StockReport

_ABSCHNITTSNUMMER = {section: nummer for nummer, section in enumerate(ReportSection, start=1)}
"""Die Nummer aus Doc 10, Paragraph 6.12 -- aus der Reihenfolge des Enums
abgeleitet, damit sie nicht zweimal gepflegt werden muss."""


def as_document(report: StockReport) -> dict[str, Any]:
    """Der vollstaendige Bericht als reine Daten."""
    inhalte = _inhalte(report)
    vorbehalte: dict[str, list[dict[str, str]]] = {}
    for luecke in report.gaps:
        vorbehalte.setdefault(luecke.section.value, []).append(
            {"art": luecke.kind.value, "grund": luecke.reason}
        )

    abschnitte: dict[str, Any] = {}
    for section in ReportSection:
        eigene = vorbehalte.get(section.value, [])
        abschnitte[section.value] = {
            "nummer": _ABSCHNITTSNUMMER[section],
            "verfuegbar": section not in report.missing_sections,
            "inhalt": inhalte.get(section),
            "vorbehalte": eigene,
        }

    return {
        "berichtsschema_version": report.report_schema_version,
        "anwendungsversion": report.app_version,
        "scoring_version": report.scoring_version,
        "signalregel_version": report.signal_rule_version,
        "lauf_id": str(report.analysis_run_id),
        "aktie_id": str(report.stock_id),
        "erstellt_am": report.created_at.isoformat(),
        "abschnitte": abschnitte,
    }


def _inhalte(report: StockReport) -> dict[ReportSection, Any]:
    """Was in jedem der achtzehn Abschnitte steht.

    Fehlt der Inhalt, steht hier nichts -- ``as_document`` setzt dann ``null``
    und die Begruendung daneben. Kein Ersatzwert, kein leeres Objekt, das wie
    ein Ergebnis aussieht.
    """
    fundamentals = report.fundamentals
    technical = report.technical
    research = report.research
    einordnung = report.technical_assessment

    inhalte: dict[ReportSection, Any] = {
        ReportSection.SYMBOL_UND_UNTERNEHMEN: {
            "symbol": report.symbol,
            "boerse": report.exchange,
            "unternehmen": report.company_name,
        },
        ReportSection.ANALYSEZEITPUNKT: {
            "ausgewertet_am": report.evaluated_at.isoformat(),
            "screening_status": report.screening_status.value,
        },
        ReportSection.KONFIDENZ_UND_DATENLUECKEN: {
            "konfidenzen": report.confidences,
            "luecken": [
                {
                    "abschnitt": luecke.section.value,
                    "nummer": _ABSCHNITTSNUMMER[luecke.section],
                    "art": luecke.kind.value,
                    "grund": luecke.reason,
                }
                for luecke in report.gaps
            ],
            "fehlende_abschnitte": sorted(s.value for s in report.missing_sections),
        },
    }
    if report.sources:
        # Nur bei tatsaechlichen Quellen. Eine leere Liste neben der
        # Begruendung "keine Quellen" waere ein Inhalt, der keiner ist.
        inhalte[ReportSection.QUELLEN] = _rein(report.sources)

    if report.signals:
        inhalte[ReportSection.TECHNISCHE_SIGNALE] = _rein(report.signals)
    if report.earnings is not None:
        inhalte[ReportSection.EARNINGS_STATUS] = _rein(report.earnings)
    if report.backtest:
        inhalte[ReportSection.SIGNALSTATISTIK] = _rein(report.backtest)
    if technical is not None:
        inhalte[ReportSection.TECHNISCHE_LAGE] = {
            "deterministisch": _rein(technical),
            "einordnung": _rein(einordnung) if einordnung is not None else None,
        }
        if technical.zones:
            inhalte[ReportSection.ZONEN] = _rein(technical.zones)
    if research is not None:
        inhalte[ReportSection.NACHRICHTEN] = {
            "zusammenfassung": research.summary,
            "abdeckung": _rein(research.coverage),
            "belege": _rein(research.evidence),
        }
        if research.positive_factors:
            inhalte[ReportSection.CHANCEN] = list(research.positive_factors)
    # Punkt 12 aus beiden Quellen und **ausserhalb** des Research-Zweiges: Die
    # Einordnung nennt Fehlsignalgruende auch dann, wenn die Recherche gar
    # nicht lief. Stuende das hier drinnen, gaebe es Risiken, die der Bericht
    # kennt und nicht zeigt (Muster: ``_pruefe_risiken`` im Builder).
    risiken = list(research.risks) if research is not None else []
    if einordnung is not None:
        risiken += list(einordnung.false_signal_risks)
    if risiken:
        inhalte[ReportSection.RISIKEN] = risiken

    if fundamentals is not None:
        inhalte[ReportSection.FUNDAMENTALE_BEWERTUNG] = _rein(fundamentals)

    # Punkt 9 **ausserhalb** des Research-Zweiges (ADR 0043): Die gezaehlte
    # Votenverteilung hat mit der Recherche nichts zu tun und steht auch dann,
    # wenn diese ausgefallen ist. Bis ADR 0043 fuellten hier die positiven und
    # negativen Faktoren der Recherche den Platz -- sie stehen ohnehin in den
    # Punkten 11 und 12, und eine Analystenmeinung waren sie nie.
    analysts = report.analysts
    if analysts is not None and analysts.status is AnalystRecommendationStatus.COMPLETED:
        inhalte[ReportSection.ANALYSTENMEINUNGEN] = {
            "empfehlungen": _rein(analysts),
            # Ausdruecklich null und nicht weggelassen: Doc 10 verlangt
            # Kursziele, und es wird sie nicht geben (ADR 0043). Ein fehlender
            # Schluessel saehe aus wie ein vergessener.
            "kursziele": None,
        }

    # Punkte 13 bis 16 haben keinen Inhalt: Optionsanalyse und Scoring
    # gehoeren zu Sprint 5. Die Felder stehen trotzdem am Bericht, damit
    # Sprint 5 sie fuellen kann, ohne das Schema zu heben.
    if report.swing_score is not None:
        inhalte[ReportSection.SWING_SCORE] = report.swing_score
    if report.investment_score is not None:
        inhalte[ReportSection.INVESTMENT_SCORE] = report.investment_score
    if report.recommendation is not None:
        inhalte[ReportSection.EMPFEHLUNG] = {
            "stufe": report.recommendation.value,
            "zusammenfassung": report.summary,
        }
    return inhalte


def _rein(wert: Any) -> Any:
    """Wandelt Domain-Objekte in reine Daten.

    Bewusst allgemein statt Feld fuer Feld: Der Bericht ist der vollstaendige
    Nachweis eines Laufs, und eine handgeschriebene Feldliste je Teilergebnis
    veraltete beim naechsten neuen Feld still -- ein Wert waere dann im
    System, aber nicht im Bericht.
    """
    if wert is None or isinstance(wert, str | bool | int | float):
        return wert
    if isinstance(wert, Enum):
        return wert.value
    if isinstance(wert, datetime | date):
        return wert.isoformat()
    if isinstance(wert, uuid.UUID):
        return str(wert)
    if is_dataclass(wert) and not isinstance(wert, type):
        return {feld.name: _rein(getattr(wert, feld.name)) for feld in fields(wert)}
    if isinstance(wert, Mapping):
        return {_schluessel(k): _rein(v) for k, v in wert.items()}
    if isinstance(wert, frozenset | set):
        # Sortiert, damit zwei Laeufe mit demselben Inhalt dasselbe Dokument
        # ergeben -- sonst waere ein Vergleich zweier Berichte Zufall.
        return sorted(_rein(eintrag) for eintrag in wert)
    if isinstance(wert, Sequence):
        return [_rein(eintrag) for eintrag in wert]
    raise TypeError(f"Kein Weg, {type(wert).__name__} als Bericht zu schreiben")


def _schluessel(wert: Any) -> str:
    return wert.value if isinstance(wert, Enum) else str(wert)
