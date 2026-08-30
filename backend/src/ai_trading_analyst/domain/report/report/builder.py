"""Zusammenstellung des Analyseberichts (Doc 10, Paragraph 6.12; ADR 0039).

Eine reine Funktion ueber ein ``StockScreeningOutcome``. Sie rechnet nichts
und formuliert nichts -- sie ordnet zu und traegt ein, was fehlt.
"""

from __future__ import annotations

from datetime import datetime

from ai_trading_analyst.domain.analysis.models import StockScreeningOutcome
from ai_trading_analyst.domain.earnings import EarningsFilterStatus
from ai_trading_analyst.domain.fundamentals import FundamentalStatus
from ai_trading_analyst.domain.research import ResearchStatus
from ai_trading_analyst.domain.technical import TechnicalAssessmentStatus, TechnicalStatus

from .values import (
    REPORT_SCHEMA_VERSION,
    GapKind,
    ReportGap,
    ReportSection,
    ReportSource,
    SourceKind,
    StockReport,
)

_SPRINT_5 = "Optionsanalyse und Scoring gehoeren zu Sprint 5 und sind nicht gebaut"


class _Luecken:
    """Sammelt die Befunde zu Punkt 17 waehrend des Zusammenstellens."""

    def __init__(self) -> None:
        self._eintraege: list[ReportGap] = []

    def fehlt(self, section: ReportSection, grund: str) -> None:
        self._eintraege.append(ReportGap(section=section, kind=GapKind.FEHLT, reason=grund))

    def eingeschraenkt(self, section: ReportSection, grund: str) -> None:
        self._eintraege.append(
            ReportGap(section=section, kind=GapKind.EINGESCHRAENKT, reason=grund)
        )

    @property
    def alle(self) -> tuple[ReportGap, ...]:
        return tuple(self._eintraege)

    @property
    def fehlende_abschnitte(self) -> frozenset[ReportSection]:
        return frozenset(e.section for e in self._eintraege if e.kind is GapKind.FEHLT)


def build_report(
    outcome: StockScreeningOutcome, *, created_at: datetime, app_version: str
) -> StockReport:
    """Der Bericht zu einem Screening-Ergebnis.

    ``created_at`` und ``app_version`` kommen von aussen: Der Zeitpunkt, weil
    eine Domain-Funktion keine Uhr kennt, und die Anwendungsversion, weil sie
    aus den Paketmetadaten stammt und damit Infrastruktur ist.
    """
    luecken = _Luecken()

    company_name = outcome.fundamentals.company_name if outcome.fundamentals else None
    if company_name is None:
        # Eingeschraenkt und nicht fehlend: Symbol und Boerse stehen, nur die
        # zweite Haelfte von Punkt 1 nicht. Den ganzen Abschnitt als fehlend
        # zu fuehren, waehrend er Inhalt hat, waere ein Widerspruch im
        # Dokument.
        luecken.eingeschraenkt(
            ReportSection.SYMBOL_UND_UNTERNEHMEN,
            "kein Unternehmensname -- das SEC-Symbolverzeichnis fuehrt das Symbol nicht",
        )

    if not outcome.result.signal_events:
        luecken.fehlt(ReportSection.TECHNISCHE_SIGNALE, "keine Signalereignisse aufgezeichnet")

    _pruefe_earnings(outcome, luecken)
    _pruefe_signalstatistik(outcome, luecken)
    _pruefe_technik(outcome, luecken)
    _pruefe_research(outcome, luecken)
    _pruefe_fundamentaldaten(outcome, luecken)

    luecken.fehlt(ReportSection.PUT_STRATEGIEN, _SPRINT_5)
    luecken.fehlt(ReportSection.SWING_SCORE, _SPRINT_5)
    luecken.fehlt(ReportSection.INVESTMENT_SCORE, _SPRINT_5)
    luecken.fehlt(
        ReportSection.EMPFEHLUNG,
        "ohne Swing- und Investment-Score gibt es keine Grundlage fuer eine Empfehlung",
    )

    quellen = _quellen(outcome)
    if not quellen:
        luecken.fehlt(ReportSection.QUELLEN, "weder Recherche- noch Einreichungsquellen vorhanden")

    return StockReport(
        analysis_run_id=outcome.analysis_run_id,
        stock_id=outcome.stock.id,
        symbol=outcome.stock.symbol,
        exchange=outcome.stock.exchange,
        created_at=created_at,
        evaluated_at=outcome.evaluated_at,
        screening_status=outcome.result.status,
        signal_rule_version=outcome.signal_rule_version,
        company_name=company_name,
        signals=outcome.result.signal_events,
        earnings=outcome.earnings,
        backtest=outcome.backtest,
        technical=outcome.technical,
        technical_assessment=outcome.technical_assessment,
        research=outcome.research,
        fundamentals=outcome.fundamentals,
        gaps=luecken.alle,
        sources=quellen,
        report_schema_version=REPORT_SCHEMA_VERSION,
        app_version=app_version,
        missing_sections=luecken.fehlende_abschnitte,
    )


def _pruefe_earnings(outcome: StockScreeningOutcome, luecken: _Luecken) -> None:
    earnings = outcome.earnings
    if earnings is None:
        luecken.fehlt(ReportSection.EARNINGS_STATUS, "der Earnings-Filter lief nicht")
        return
    if earnings.status is EarningsFilterStatus.UNKNOWN:
        # Doc 10, Paragraph 6.5: ein Kandidat mit UNKNOWN wird im Bericht
        # ausdruecklich als Datenrisiko gekennzeichnet -- nicht stillschweigend
        # als unbedenklich behandelt.
        luecken.eingeschraenkt(
            ReportSection.EARNINGS_STATUS,
            f"Termin unbekannt ({earnings.reason or 'ohne Angabe'}) -- Datenrisiko",
        )


def _pruefe_signalstatistik(outcome: StockScreeningOutcome, luecken: _Luecken) -> None:
    if not outcome.backtest:
        luecken.fehlt(
            ReportSection.SIGNALSTATISTIK,
            "keine historische Signalstatistik -- die Historie im Betrachtungsfenster "
            "reichte nicht",
        )
        return
    if any(not ergebnis.earnings_exclusion_applied for ergebnis in outcome.backtest):
        # ADR 0038, Entscheidung 3 -- die Abweichung steht am Ergebnis und
        # gehoert damit in den Bericht.
        luecken.eingeschraenkt(
            ReportSection.SIGNALSTATISTIK,
            "der Replay schliesst keine Ereignisse nahe Berichtsterminen aus -- historische "
            "Termine liegen nicht vor (ADR 0017 L9); die Kennzahlen messen eine leicht andere "
            "Strategie als die gehandelte",
        )


def _pruefe_technik(outcome: StockScreeningOutcome, luecken: _Luecken) -> None:
    snapshot = outcome.technical
    if snapshot is None or snapshot.status is not TechnicalStatus.COMPLETED:
        grund = snapshot.reason if snapshot is not None else "die Chartauswertung lief nicht"
        luecken.fehlt(ReportSection.TECHNISCHE_LAGE, grund or "Chartauswertung nicht auswertbar")
        luecken.fehlt(ReportSection.ZONEN, "ohne Chartauswertung gibt es keine Zonen")
    elif not snapshot.zones:
        luecken.fehlt(
            ReportSection.ZONEN, "keine belastbare Unterstuetzung oder Widerstand gefunden"
        )

    einordnung = outcome.technical_assessment
    if einordnung is not None and einordnung.status is not TechnicalAssessmentStatus.COMPLETED:
        luecken.eingeschraenkt(
            ReportSection.TECHNISCHE_LAGE,
            f"ohne KI-Einordnung ({einordnung.reason or einordnung.status.value})",
        )


def _pruefe_research(outcome: StockScreeningOutcome, luecken: _Luecken) -> None:
    research = outcome.research
    betroffen = (
        ReportSection.NACHRICHTEN,
        ReportSection.ANALYSTENMEINUNGEN,
        ReportSection.CHANCEN,
        ReportSection.RISIKEN,
    )
    if research is None or research.status is not ResearchStatus.COMPLETED:
        grund = (
            (research.reason or research.status.value)
            if research is not None
            else "die Recherche lief nicht -- der Earnings-Filter liess sie nicht zu"
        )
        for abschnitt in betroffen:
            luecken.fehlt(abschnitt, grund)
        return

    # Kursziele sind bewusst nicht gebaut (ADR 0017): Der Finnhub-Endpunkt ist
    # kostenpflichtig. Punkt 9 verlangt sie ausdruecklich -- das gehoert
    # gesagt, nicht weggelassen.
    luecken.eingeschraenkt(
        ReportSection.ANALYSTENMEINUNGEN,
        "ohne Kursziele -- der Anbieter fuehrt sie nur kostenpflichtig (ADR 0017)",
    )
    if not research.positive_factors:
        luecken.fehlt(ReportSection.CHANCEN, "die Recherche nennt keine positiven Faktoren")
    if not research.risks:
        luecken.fehlt(ReportSection.RISIKEN, "die Recherche nennt keine Risiken")


def _pruefe_fundamentaldaten(outcome: StockScreeningOutcome, luecken: _Luecken) -> None:
    fundamentals = outcome.fundamentals
    if fundamentals is None:
        luecken.fehlt(
            ReportSection.FUNDAMENTALE_BEWERTUNG,
            "die Fundamentalanalyse lief nicht -- die Quelle war nicht erreichbar",
        )
        return
    if fundamentals.status is not FundamentalStatus.COMPLETED:
        luecken.fehlt(
            ReportSection.FUNDAMENTALE_BEWERTUNG,
            fundamentals.reason or "keine Kennzahl auswertbar",
        )
        return
    if fundamentals.missing_metrics:
        fehlende = ", ".join(name.value for name in fundamentals.missing_metrics)
        luecken.eingeschraenkt(
            ReportSection.FUNDAMENTALE_BEWERTUNG,
            f"Abdeckung {fundamentals.coverage:.0%} -- ohne {fehlende}",
        )


def _quellen(outcome: StockScreeningOutcome) -> tuple[ReportSource, ...]:
    """Punkt 18, aus beiden Quellenarten in einer Liste.

    Die Einreichungen werden ueber ihre Vorgangsnummer entdoppelt: Zwoelf
    Kennzahlen stammen regelmaessig aus demselben Dokument, und zwoelf
    identische Zeilen waeren keine Quellenangabe, sondern Rauschen.
    """
    quellen: list[ReportSource] = []
    if outcome.research is not None:
        quellen.extend(
            ReportSource(
                kind=SourceKind.RESEARCH,
                label=zitat.title,
                url=zitat.url,
                retrieved_at=zitat.retrieved_at,
                source_age=zitat.source_age,
            )
            for zitat in outcome.research.citations
        )
    if outcome.fundamentals is not None:
        gesehen: dict[str, ReportSource] = {}
        for metrik in outcome.fundamentals.metrics.values():
            for quelle in metrik.sources:
                gesehen.setdefault(
                    quelle.accession,
                    ReportSource(
                        kind=SourceKind.FUNDAMENTALS,
                        label=f"SEC {quelle.form}",
                        url=quelle.url,
                        retrieved_at=metrik.retrieved_at,
                        filed=quelle.filed,
                    ),
                )
        quellen.extend(gesehen.values())
    return tuple(quellen)
