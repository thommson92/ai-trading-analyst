"""Zusammenstellung des Analyseberichts (Doc 10, Paragraph 6.12; ADR 0039).

Eine reine Funktion ueber ein ``StockScreeningOutcome``. Sie rechnet nichts
und formuliert nichts -- sie ordnet zu und traegt ein, was fehlt.
"""

from __future__ import annotations

from datetime import datetime

from ai_trading_analyst.domain.analysis.models import StockScreeningOutcome
from ai_trading_analyst.domain.analysts import AnalystRecommendationStatus
from ai_trading_analyst.domain.earnings import EarningsFilterStatus
from ai_trading_analyst.domain.fundamentals import FundamentalStatus
from ai_trading_analyst.domain.options import OptionsStatus
from ai_trading_analyst.domain.research import ResearchStatus
from ai_trading_analyst.domain.scoring import (
    Recommendation,
    ScoreKind,
    ScoreResult,
    ScoreStatus,
)
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

_SCORE_ABSCHNITT = {
    ScoreKind.SWING: ReportSection.SWING_SCORE,
    ScoreKind.LONG_TERM: ReportSection.INVESTMENT_SCORE,
}


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
    _pruefe_analystenmeinungen(outcome, luecken)
    _pruefe_risiken(outcome, luecken)
    _pruefe_fundamentaldaten(outcome, luecken)

    _pruefe_optionen(outcome, luecken)
    _pruefe_score(outcome.swing_score, ScoreKind.SWING, luecken)
    _pruefe_score(outcome.investment_score, ScoreKind.LONG_TERM, luecken)
    _pruefe_empfehlung(outcome, luecken)

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
        analysts=outcome.analysts,
        options=outcome.options,
        recommendation=outcome.recommendation,
        swing_score=outcome.swing_score,
        investment_score=outcome.investment_score,
        scoring_version=_scoring_version(outcome),
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


def _research_grund(outcome: StockScreeningOutcome) -> str | None:
    """Warum die Recherche nichts beitraegt -- oder ``None``, wenn sie es tut."""
    research = outcome.research
    if research is None:
        return "die Recherche lief nicht -- der Earnings-Filter liess sie nicht zu"
    if research.status is not ResearchStatus.COMPLETED:
        return research.reason or research.status.value
    return None


def _pruefe_research(outcome: StockScreeningOutcome, luecken: _Luecken) -> None:
    """Die Punkte, die **allein** an der Recherche haengen.

    Zwei Punkte stehen bewusst nicht dabei. Die Risiken speisen sich
    zusaetzlich aus der KI-Einordnung. Und die Analystenmeinungen standen bis
    ADR 0043 hier -- ohne Recherche galt Punkt 9 als fehlend, obwohl die
    gezaehlte Votenverteilung mit der Recherche nichts zu tun hat.
    """
    grund = _research_grund(outcome)
    if grund is not None:
        for abschnitt in (ReportSection.NACHRICHTEN, ReportSection.CHANCEN):
            luecken.fehlt(abschnitt, grund)
        return

    research = outcome.research
    assert research is not None  # ``_research_grund`` hat es bereits geprueft
    if not research.positive_factors:
        luecken.fehlt(ReportSection.CHANCEN, "die Recherche nennt keine positiven Faktoren")


def _pruefe_analystenmeinungen(outcome: StockScreeningOutcome, luecken: _Luecken) -> None:
    """Punkt 9 -- **unabhaengig von der Recherche** (ADR 0043).

    Der Punkt bleibt auch im Erfolgsfall eingeschraenkt: Doc 10 verlangt neben
    den Meinungen auch Kursziele, und die sind dauerhaft zurueckgestellt, weil
    der Endpunkt kostenpflichtig ist und keine Score-Komponente sie braucht.
    Das gehoert gesagt, nicht weggelassen.
    """
    analysts = outcome.analysts

    if analysts is None:
        luecken.fehlt(ReportSection.ANALYSTENMEINUNGEN, "die Empfehlungen wurden nicht abgerufen")
        return
    if analysts.status is AnalystRecommendationStatus.UNAVAILABLE:
        luecken.fehlt(
            ReportSection.ANALYSTENMEINUNGEN,
            f"der Anbieter war nicht erreichbar ({analysts.reason or 'ohne Angabe'})",
        )
        return
    if analysts.status is AnalystRecommendationStatus.UNKNOWN:
        # Keine Abdeckung ist nicht "keine Meinung" (ADR 0043) -- der Punkt
        # fehlt, statt eine leere Verteilung als Aussage auszugeben.
        luecken.fehlt(
            ReportSection.ANALYSTENMEINUNGEN,
            "der Anbieter fuehrt fuer dieses Symbol keine Empfehlungen",
        )
        return

    luecken.eingeschraenkt(
        ReportSection.ANALYSTENMEINUNGEN,
        "ohne Kursziele -- dauerhaft zurueckgestellt (ADR 0043)",
    )


def _pruefe_risiken(outcome: StockScreeningOutcome, luecken: _Luecken) -> None:
    """Punkt 12 speist sich aus **zwei** Quellen (Doc 10, Paragraph 6.12).

    Die Recherche nennt fachliche Risiken, die KI-Einordnung die Gruende fuer
    ein moegliches Fehlsignal. Der Punkt fehlt nur, wenn beide schweigen --
    ihn an der Recherche allein festzumachen ergab einen Abschnitt, der als
    fehlend galt und trotzdem Inhalt trug.
    """
    aus_research = tuple(outcome.research.risks) if outcome.research is not None else ()
    einordnung = outcome.technical_assessment
    aus_einordnung = tuple(einordnung.false_signal_risks) if einordnung is not None else ()

    if not aus_research and not aus_einordnung:
        luecken.fehlt(
            ReportSection.RISIKEN,
            _research_grund(outcome) or "weder Recherche noch Einordnung nennen ein Risiko",
        )
        return
    if not aus_research:
        luecken.eingeschraenkt(
            ReportSection.RISIKEN,
            "nur Fehlsignalgruende aus der Einordnung -- "
            + (_research_grund(outcome) or "die Recherche nennt keine Risiken"),
        )


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


def _pruefe_optionen(outcome: StockScreeningOutcome, luecken: _Luecken) -> None:
    """Punkt 13 (Doc 10, Paragraph 6.10; ADR 0048).

    Drei Faelle, drei verschiedene Aussagen: nicht abgerufen, abgerufen ohne
    passenden Kontrakt, oder Vorschlaege mit unvollstaendiger Nebenangabe.

    Der dritte ist **eingeschraenkt und nicht fehlend**: Der Abschnitt hat
    Inhalt -- Strike, Praemie, Rendite, Break-even stehen alle darin --, ihm
    fehlt nur der Abstand zur naechsten Unterstuetzung, weil die
    Chartauswertung keine belastbare Zone geliefert hat. Ihn deshalb als
    fehlend zu fuehren waere ein Widerspruch im Dokument, und die Kopplung
    ist ausdruecklich nicht blockierend (CLAUDE.md).
    """
    optionen = outcome.options
    if optionen is None:
        luecken.fehlt(
            ReportSection.PUT_STRATEGIEN,
            "die Optionsanalyse lief nicht -- die Quelle war nicht erreichbar",
        )
        return
    if optionen.status is not OptionsStatus.COMPLETED or not optionen.strategies:
        luecken.fehlt(
            ReportSection.PUT_STRATEGIEN,
            optionen.reason or "kein Vorschlag im Zielfenster",
        )
        return
    ohne_zone = [s for s in optionen.strategies if s.distance_to_support_pct is None]
    if ohne_zone:
        luecken.eingeschraenkt(
            ReportSection.PUT_STRATEGIEN,
            f"{len(ohne_zone)} von {len(optionen.strategies)} Vorschlaegen ohne Abstand "
            "zur naechsten Unterstuetzung -- die Chartauswertung hat keine belastbare "
            "Zone geliefert",
        )


def _pruefe_score(score: ScoreResult | None, kind: ScoreKind, luecken: _Luecken) -> None:
    """Punkt 14 beziehungsweise 15 (Doc 10, Paragraph 6.11).

    Drei Faelle, drei verschiedene Aussagen: kein Score gerechnet, kein Score
    zustande gekommen, oder ein Score auf unvollstaendiger Grundlage. Der
    dritte ist **eingeschraenkt und nicht fehlend** -- der Abschnitt hat
    Inhalt, und die umgewichteten Gewichte stehen darin. Ihn als fehlend zu
    fuehren waere ein Widerspruch im Dokument.
    """
    abschnitt = _SCORE_ABSCHNITT[kind]
    if score is None:
        luecken.fehlt(abschnitt, "der Score wurde nicht gerechnet")
        return
    if score.status is ScoreStatus.INSUFFICIENT_DATA:
        fehlend = ", ".join(name.value for name in score.missing_components)
        luecken.fehlt(
            abschnitt,
            f"Datenabdeckung {score.coverage:.0%} reicht nicht -- ohne {fehlend}",
        )
        return
    if score.missing_components:
        fehlend = ", ".join(name.value for name in score.missing_components)
        luecken.eingeschraenkt(
            abschnitt,
            f"Abdeckung {score.coverage:.0%} -- ohne {fehlend}, die uebrigen Gewichte "
            "sind darauf umgerechnet",
        )


def _pruefe_empfehlung(outcome: StockScreeningOutcome, luecken: _Luecken) -> None:
    """Punkt 16 (Doc 10, Paragraph 6.12; ADR 0046).

    Der Punkt ist **verfuegbar, sobald es eine Stufe gibt** -- auch wenn diese
    ``INSUFFICIENT_DATA`` lautet. Das ist eine der fuenf Stufen aus Doc 10 und
    keine Luecke: Sie sagt, dass die Grundlage fehlt, und nennt den Grund.

    Eingeschraenkt bleibt er trotzdem: Doc 10 verlangt eine *konkrete*
    Empfehlung, und die formulierte Zusammenfassung dazu gehoert der
    KI-Haelfte des Berichts (ADR 0039). Ein deterministisch zusammengesetzter
    Satz waere eine Formulierung ohne Verfasser.
    """
    empfehlung = outcome.recommendation
    if empfehlung is None:
        luecken.fehlt(ReportSection.EMPFEHLUNG, "die Empfehlungsstufe wurde nicht gerechnet")
        return
    if empfehlung.level is Recommendation.INSUFFICIENT_DATA:
        grund = empfehlung.reasons[0] if empfehlung.reasons else "ohne Grund"
        luecken.eingeschraenkt(ReportSection.EMPFEHLUNG, f"INSUFFICIENT_DATA -- {grund}")
        return
    luecken.eingeschraenkt(
        ReportSection.EMPFEHLUNG,
        "ohne formulierte Begruendung -- die KI-Haelfte des Berichts folgt getrennt (ADR 0039)",
    )


def _scoring_version(outcome: StockScreeningOutcome) -> str | None:
    """Die Versionen beider Scores in einem Feld (Doc 10, Paragraph 8).

    Beide, weil sie unabhaengig voneinander steigen. ``None``, wenn kein
    Score gerechnet wurde -- eine Version ohne Ergebnis waere eine Angabe
    ueber nichts.
    """
    teile = [
        f"{art.value.lower()}-{score.version}"
        for art, score in (
            (ScoreKind.SWING, outcome.swing_score),
            (ScoreKind.LONG_TERM, outcome.investment_score),
        )
        if score is not None
    ]
    return "+".join(teile) if teile else None


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
    analysts = outcome.analysts
    if (
        analysts is not None
        and analysts.status is AnalystRecommendationStatus.COMPLETED
        and analysts.source_url is not None
    ):
        # Die Adresse kommt vom Anbieter, nicht aus dieser Datei: Ein Bericht
        # aus Fixture-Zahlen darf nicht die Adresse des echten Dienstes
        # nennen. Ohne Adresse gibt es keinen Beleg -- und damit auch keine
        # Quellenzeile, statt einer mit erfundener Herkunft.
        quellen.append(
            ReportSource(
                kind=SourceKind.ANALYSTS,
                label=f"Analystenempfehlungen ({analysts.source or 'ohne Angabe'})",
                url=analysts.source_url,
                retrieved_at=analysts.retrieved_at,
            )
        )
    return tuple(quellen)
