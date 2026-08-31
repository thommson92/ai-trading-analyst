"""SQLAlchemy-Implementierungen der Domain-Ports (``domain.analysis.ports``)."""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ai_trading_analyst.domain.analysis import (
    AnalysisRun,
    RunStatus,
    Stock,
    StockProcessingError,
    StockScreeningOutcome,
)
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
from ai_trading_analyst.domain.earnings import EarningsFilterResult, EarningsFilterStatus
from ai_trading_analyst.domain.fundamentals import (
    FigureName,
    FundamentalSnapshot,
    FundamentalStatus,
    Metric,
    MetricBasis,
    MetricName,
    MetricUnit,
    SourceRef,
    TagConflict,
)
from ai_trading_analyst.domain.report import StockReport, StoredReport, as_document
from ai_trading_analyst.domain.research import (
    Citation,
    ResearchCoverage,
    ResearchEvidence,
    ResearchReport,
    ResearchStatus,
    SourceLicenseClass,
    SourceRank,
)
from ai_trading_analyst.domain.scoring import (
    ComponentName,
    Recommendation,
    RecommendationResult,
    ScoreComponent,
    ScoreConfidence,
    ScoreKind,
    ScoreResult,
    ScoreStatus,
)
from ai_trading_analyst.domain.screening import (
    IntradayBar,
    ScreeningResult,
    ScreeningStatus,
    SignalEvent,
    SignalType,
)
from ai_trading_analyst.domain.technical import (
    BreakoutQuality,
    FalseSignalRisk,
    MomentumState,
    PriceZone,
    RiskRewardRating,
    SwingEntryPlausibility,
    TechnicalAssessment,
    TechnicalAssessmentStatus,
    TechnicalSnapshot,
    TechnicalStatus,
    TrendDirection,
    TrendStrength,
    ZoneKind,
    ZoneStrength,
)

from .orm import (
    AnalysisRunOrm,
    BacktestResultOrm,
    FundamentalMetricOrm,
    IntradayBarOrm,
    ProcessingErrorOrm,
    ResearchCitationOrm,
    ScreeningResultOrm,
    SignalEventOrm,
    StockOrm,
    StockReportOrm,
    TechnicalZoneOrm,
)


class SqlAlchemyStockRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, stock: Stock) -> None:
        """Idempotent nach Symbol -- nicht nach id: ein Marktdatenanbieter, der
        fuer ein bereits bekanntes Symbol eine neue id liefert, soll den
        bestehenden Datensatz unberuehrt lassen statt mit einer IntegrityError
        abzubrechen (die Aktie waere sonst faelschlich ein StockProcessingError
        statt regulaer gescreent zu werden)."""
        statement = (
            pg_insert(StockOrm)
            .values(id=stock.id, symbol=stock.symbol, exchange=stock.exchange)
            .on_conflict_do_nothing(index_elements=["symbol"])
        )
        self._session.execute(statement)

    def get_by_symbol(self, symbol: str) -> Stock | None:
        row = self._session.execute(
            select(StockOrm).where(StockOrm.symbol == symbol)
        ).scalar_one_or_none()
        return None if row is None else Stock(id=row.id, symbol=row.symbol, exchange=row.exchange)

    def list_all(self) -> Sequence[Stock]:
        rows = self._session.execute(select(StockOrm)).scalars().all()
        return tuple(Stock(id=row.id, symbol=row.symbol, exchange=row.exchange) for row in rows)


def _run_from_row(row: AnalysisRunOrm) -> AnalysisRun:
    return AnalysisRun(
        id=row.id,
        status=RunStatus(row.status),
        started_at=row.started_at,
        completed_at=row.completed_at,
        number_of_stocks=row.number_of_stocks,
        candidates_found=row.candidates_found,
        error_message=row.error_message,
    )


class SqlAlchemyAnalysisRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, run: AnalysisRun) -> None:
        self._session.add(
            AnalysisRunOrm(
                id=run.id,
                status=run.status,
                started_at=run.started_at,
                completed_at=run.completed_at,
                number_of_stocks=run.number_of_stocks,
                candidates_found=run.candidates_found,
                error_message=run.error_message,
            )
        )

    def get(self, run_id: uuid.UUID) -> AnalysisRun | None:
        row = self._session.get(AnalysisRunOrm, run_id)
        return None if row is None else _run_from_row(row)

    def list_all(self) -> Sequence[AnalysisRun]:
        rows = (
            self._session.execute(select(AnalysisRunOrm).order_by(AnalysisRunOrm.started_at))
            .scalars()
            .all()
        )
        return tuple(_run_from_row(row) for row in rows)

    def update(self, run: AnalysisRun) -> None:
        row = self._session.get(AnalysisRunOrm, run.id)
        if row is None:
            raise LookupError(
                f"AnalysisRun {run.id} wurde nicht gefunden und kann nicht aktualisiert werden."
            )
        row.status = run.status
        row.completed_at = run.completed_at
        row.number_of_stocks = run.number_of_stocks
        row.candidates_found = run.candidates_found
        row.error_message = run.error_message


def _require_paired_evaluated_at(
    row_id: uuid.UUID,
    evaluated_at: datetime | None,
    status_field: str,
    evaluated_at_field: str,
) -> datetime:
    """Optionale Teilergebnisse (Earnings-Filter, Research) werden immer als
    Paar aus Status- und Zeitstempel-Spalte geschrieben (siehe
    ``SqlAlchemyScreeningResultRepository.add``) -- eine Zeile mit Status,
    aber ohne Zeitstempel, ist ein inkonsistenter Datensatz. Gibt den
    Zeitstempel zurueck (statt nur zu pruefen), damit mypy ihn am Aufrufort
    als nicht-optional erkennt."""
    if evaluated_at is None:
        raise ValueError(
            f"Screening-Ergebnis {row_id}: {evaluated_at_field} fehlt trotz gesetztem "
            f"{status_field} -- beide Spalten werden immer gemeinsam geschrieben."
        )
    return evaluated_at


def _technical_from_row(row: ScreeningResultOrm) -> TechnicalSnapshot | None:
    """Liest die Chartauswertung zurueck, sofern eine gespeichert wurde.

    Die Zonen kommen ueber die nach ``position`` sortierte Beziehung -- die
    Sortierung nach Abstand zum Kurs ist Teil der Aussage und darf beim
    Wiedereinlesen nicht der Datenbank ueberlassen bleiben.
    """
    if row.technical_status is None:
        return None
    evaluated_at = _require_paired_evaluated_at(
        row.id, row.technical_evaluated_at, "technical_status", "technical_evaluated_at"
    )
    if row.technical_analysis_version is None:
        raise ValueError(
            f"Screening-Ergebnis {row.id}: technical_analysis_version fehlt trotz gesetztem "
            "technical_status -- ohne die Verfahrensversion ist nicht mehr feststellbar, "
            "nach welchem Verfahren gerechnet wurde."
        )
    return TechnicalSnapshot(
        status=TechnicalStatus(row.technical_status),
        evaluated_at=evaluated_at,
        analysis_version=row.technical_analysis_version,
        parameters=row.technical_parameters,
        reason=row.technical_reason,
        candle_timestamp=row.technical_candle_timestamp,
        close=row.technical_close,
        trend=None if row.technical_trend is None else TrendDirection(row.technical_trend),
        rsi=row.technical_rsi,
        ema5=row.technical_ema5,
        ema20=row.technical_ema20,
        distance_to_ema5_pct=row.technical_distance_to_ema5_pct,
        distance_to_ema20_pct=row.technical_distance_to_ema20_pct,
        atr=row.technical_atr,
        atr_pct=row.technical_atr_pct,
        recent_high=row.technical_recent_high,
        recent_high_at=row.technical_recent_high_at,
        recent_low=row.technical_recent_low,
        recent_low_at=row.technical_recent_low_at,
        zones=tuple(
            PriceZone(
                lower=zone.lower,
                upper=zone.upper,
                kind=ZoneKind(zone.kind),
                strength=ZoneStrength(zone.strength),
                touch_count=zone.touch_count,
                last_confirmed_at=zone.last_confirmed_at,
                distance_pct=zone.distance_pct,
                pivot_count=zone.pivot_count,
            )
            for zone in row.technical_zones
        ),
        downside_to_support_pct=row.technical_downside_to_support_pct,
        upside_to_resistance_pct=row.technical_upside_to_resistance_pct,
        chance_risk_ratio=row.technical_chance_risk_ratio,
    )


_TECHNICAL_FIELDS = (
    "status",
    "evaluated_at",
    "analysis_version",
    "parameters",
    "reason",
    "candle_timestamp",
    "close",
    "trend",
    "rsi",
    "ema5",
    "ema20",
    "distance_to_ema5_pct",
    "distance_to_ema20_pct",
    "atr",
    "atr_pct",
    "recent_high",
    "recent_high_at",
    "recent_low",
    "recent_low_at",
    "downside_to_support_pct",
    "upside_to_resistance_pct",
    "chance_risk_ratio",
)


_RESEARCH_EVIDENCE_FIELDS = (
    "distinct_sources",
    "successful_fetches",
    "rejected_tool_calls",
    "dropped_citations",
)
"""Feldname von ``ResearchEvidence`` = Spaltenname ohne Praefix (Muster
``_TECHNICAL_FIELDS``). Einmal geschrieben, damit die beiden Zweige des
Mappers nicht auseinanderlaufen koennen."""


def _research_evidence_columns(evidence: ResearchEvidence | None) -> dict[str, Any]:
    """Die Zahlen hinter der Abdeckung (ADR 0029) als Spaltensatz.

    Ohne Bericht bleiben alle vier leer statt auf null zu stehen: Null
    abgelehnte Werkzeugaufrufe waere eine Aussage ueber einen Lauf, den es
    nicht gab.
    """
    return {
        f"research_{name}": getattr(evidence, name) if evidence is not None else None
        for name in _RESEARCH_EVIDENCE_FIELDS
    }


def _research_evidence(row: ScreeningResultOrm) -> ResearchEvidence | None:
    """Gegenstueck zu ``_research_evidence_columns``.

    Vor ADR 0029 geschriebene Zeilen haben die Spalten nicht. Sie bekommen
    ``None`` statt Nullen -- ein alter Bericht weiss nichts ueber seine
    Abdeckung und soll das auch nicht behaupten.
    """
    if (
        row.research_distinct_sources is None
        or row.research_successful_fetches is None
        or row.research_rejected_tool_calls is None
        or row.research_dropped_citations is None
    ):
        # Alle vier werden als Satz geschrieben, also auch als Satz gelesen.
        # Ein ``or 0`` je Feld haette aus einer fehlenden Messung eine Null
        # gemacht -- eine Aussage ueber einen Lauf, den es nie gab.
        return None
    return ResearchEvidence(
        distinct_sources=row.research_distinct_sources,
        successful_fetches=row.research_successful_fetches,
        rejected_tool_calls=row.research_rejected_tool_calls,
        dropped_citations=row.research_dropped_citations,
    )


_FUNDAMENTALS_FIELDS = (
    "status",
    "analysis_version",
    "evaluated_at",
    "company_name",
    "reason",
    "price_used",
    "fiscal_years",
    "tag_conflicts",
)


def _quelle_als_json(quelle: SourceRef) -> dict[str, Any]:
    """Die Quellenbindung aus CLAUDE.md, vollstaendig und flach.

    Alle fuenf Angaben, die ein Leser braucht, um den Wert in EDGAR
    wiederzufinden -- die URL laesst sich aus CIK und Einreichung jederzeit
    bilden und wird deshalb nicht mitgeschrieben.
    """
    return {
        "cik": quelle.cik,
        "accession": quelle.accession,
        "form": quelle.form,
        "filed": quelle.filed.isoformat(),
        "tag": quelle.tag,
    }


def _quelle_aus_json(eintrag: dict[str, Any]) -> SourceRef:
    return SourceRef(
        cik=int(eintrag["cik"]),
        accession=str(eintrag["accession"]),
        form=str(eintrag["form"]),
        filed=date.fromisoformat(str(eintrag["filed"])),
        tag=str(eintrag["tag"]),
    )


def _score_columns(prefix: str, score: ScoreResult | None) -> dict[str, Any]:
    """Vier Spalten je Score: Wert, Status, Version und der Rest als JSONB.

    ``prefix`` ist ``swing`` oder ``long_term`` -- ein Mapper fuer beide,
    damit die Abbildung nicht an zwei Stellen auseinanderlaufen kann.
    """
    if score is None:
        return {
            f"{prefix}_score": None,
            f"{prefix}_status": None,
            f"{prefix}_version": None,
            f"{prefix}_detail": None,
        }
    return {
        f"{prefix}_score": score.value,
        f"{prefix}_status": score.status,
        f"{prefix}_version": score.version,
        f"{prefix}_detail": {
            "abdeckung": score.coverage,
            "konfidenz": score.confidence.value,
            "komponenten": [
                {
                    "name": komponente.name.value,
                    "gewicht": komponente.weight,
                    "wirksames_gewicht": komponente.effective_weight,
                    "teilwert": komponente.value,
                    "begruendung": komponente.reason,
                }
                for komponente in score.components
            ],
            "positive_faktoren": list(score.positive_factors),
            "negative_faktoren": list(score.negative_factors),
            "begrenzende_risiken": list(score.limiting_risks),
        },
    }


def _recommendation_columns(empfehlung: RecommendationResult | None) -> dict[str, Any]:
    if empfehlung is None:
        return {"recommendation": None, "recommendation_detail": None}
    return {
        "recommendation": empfehlung.level,
        "recommendation_detail": {
            "version": empfehlung.version,
            "begruendung": list(empfehlung.reasons),
            "deckelungen": list(empfehlung.applied_caps),
        },
    }


def _recommendation_from_row(row: ScreeningResultOrm) -> RecommendationResult | None:
    """Die Stufe samt Herleitung -- **streng gelesen**, wie die Scores daneben.

    Kein ``.get`` mit Ersatzwert: Geschrieben wird das Detail immer zusammen
    mit der Stufe. Eine fehlende Version stillschweigend zu einer leeren
    Zeichenkette zu machen ergaebe ein Ergebnis ohne Versionsangabe -- und
    die verlangt CLAUDE.md an jedem.
    """
    if row.recommendation is None:
        return None
    detail = row.recommendation_detail
    if detail is None:
        raise ValueError(
            f"Screening-Ergebnis {row.id}: Empfehlungsstufe {row.recommendation} ohne "
            "Herleitung -- die Zeile ist beschaedigt"
        )
    return RecommendationResult(
        level=Recommendation(row.recommendation),
        version=str(detail["version"]),
        reasons=tuple(detail["begruendung"]),
        applied_caps=tuple(detail["deckelungen"]),
    )


def _score_from_row(row: ScreeningResultOrm, prefix: str, kind: ScoreKind) -> ScoreResult | None:
    """Der Score aus seinen vier Spalten -- **durchgehend streng gelesen**.

    Kein ``.get`` mit Ersatzwert: Geschrieben wird das Detail immer im
    Ganzen und immer zusammen mit dem Status. Eine halb nachsichtige
    Fassung -- die einen Schluessel mit Vorgabe, der naechste mit
    ``KeyError`` -- verdeckt einen fehlenden Teil des Details als
    Abdeckung 0,0 und laesst den naechsten trotzdem den ganzen Lauf
    scheitern. Wenn hier etwas fehlt, ist die Zeile kaputt, und das soll
    man sehen.
    """
    status = getattr(row, f"{prefix}_status")
    if status is None:
        return None
    detail: dict[str, Any] = getattr(row, f"{prefix}_detail")
    return ScoreResult(
        kind=kind,
        status=ScoreStatus(status),
        version=getattr(row, f"{prefix}_version") or "",
        value=getattr(row, f"{prefix}_score"),
        components=tuple(
            ScoreComponent(
                name=ComponentName(eintrag["name"]),
                weight=float(eintrag["gewicht"]),
                value=(None if eintrag["teilwert"] is None else float(eintrag["teilwert"])),
                effective_weight=float(eintrag["wirksames_gewicht"]),
                reason=eintrag["begruendung"],
            )
            for eintrag in detail["komponenten"]
        ),
        coverage=float(detail["abdeckung"]),
        confidence=ScoreConfidence(detail["konfidenz"]),
        positive_factors=tuple(detail["positive_faktoren"]),
        negative_factors=tuple(detail["negative_faktoren"]),
        limiting_risks=tuple(detail["begrenzende_risiken"]),
    )


def _fundamentals_columns(snapshot: FundamentalSnapshot | None) -> dict[str, Any]:
    """Kopfspalten der Fundamentalanalyse, ``fundamentals_``-praefigiert.

    Wie bei ``_technical_columns`` werden ohne Auswertung alle Spalten
    ausdruecklich auf ``None`` gesetzt.
    """
    if snapshot is None:
        return {f"fundamentals_{name}": None for name in _FUNDAMENTALS_FIELDS}
    return {
        "fundamentals_status": snapshot.status,
        "fundamentals_analysis_version": snapshot.analysis_version,
        "fundamentals_evaluated_at": snapshot.evaluated_at,
        "fundamentals_company_name": snapshot.company_name,
        "fundamentals_reason": snapshot.reason,
        "fundamentals_price_used": snapshot.price_used,
        "fundamentals_fiscal_years": list(snapshot.fiscal_years),
        "fundamentals_tag_conflicts": [
            {
                "figure": konflikt.figure.value,
                "period_end": konflikt.period_end.isoformat(),
                "chosen_tag": konflikt.chosen_tag,
                "chosen_value": konflikt.chosen_value,
                "other_tag": konflikt.other_tag,
                "other_value": konflikt.other_value,
            }
            for konflikt in snapshot.tag_conflicts
        ],
    }


_ANALYST_FIELDS = (
    "status",
    "analysis_version",
    "evaluated_at",
    "source",
    "source_url",
    "retrieved_at",
    "reason",
    "periods",
)
"""Die ``analyst_``-Spalten ohne Praefix (Muster ``_FUNDAMENTALS_FIELDS``).
Einmal geschrieben, damit die beiden Zweige des Mappers nicht auseinander
laufen koennen."""


def _analyst_columns(recommendations: AnalystRecommendations | None) -> dict[str, Any]:
    """Spalten der Analystenempfehlungen, ``analyst_``-praefigiert (ADR 0043)."""
    if recommendations is None:
        return {f"analyst_{name}": None for name in _ANALYST_FIELDS}
    return {
        "analyst_status": recommendations.status,
        "analyst_analysis_version": recommendations.analysis_version,
        "analyst_evaluated_at": recommendations.evaluated_at,
        "analyst_source": recommendations.source,
        "analyst_source_url": recommendations.source_url,
        "analyst_retrieved_at": recommendations.retrieved_at,
        "analyst_reason": recommendations.reason,
        "analyst_periods": [
            {
                "period": zeitraum.period.isoformat(),
                "strong_buy": zeitraum.strong_buy,
                "buy": zeitraum.buy,
                "hold": zeitraum.hold,
                "sell": zeitraum.sell,
                "strong_sell": zeitraum.strong_sell,
            }
            for zeitraum in recommendations.periods
        ],
    }


def _analyst_from_row(row: ScreeningResultOrm) -> AnalystRecommendations | None:
    if row.analyst_status is None or row.analyst_evaluated_at is None:
        return None
    return AnalystRecommendations(
        status=AnalystRecommendationStatus(row.analyst_status),
        evaluated_at=row.analyst_evaluated_at,
        periods=tuple(
            RecommendationPeriod(
                period=date.fromisoformat(str(eintrag["period"])),
                strong_buy=int(eintrag["strong_buy"]),
                buy=int(eintrag["buy"]),
                hold=int(eintrag["hold"]),
                sell=int(eintrag["sell"]),
                strong_sell=int(eintrag["strong_sell"]),
            )
            for eintrag in row.analyst_periods or ()
        ),
        source=row.analyst_source,
        source_url=row.analyst_source_url,
        retrieved_at=row.analyst_retrieved_at,
        reason=row.analyst_reason,
        analysis_version=row.analyst_analysis_version or "",
    )


def _fundamentals_from_row(row: ScreeningResultOrm) -> FundamentalSnapshot | None:
    if row.fundamentals_status is None or row.fundamentals_evaluated_at is None:
        return None
    return FundamentalSnapshot(
        symbol=row.stock.symbol,
        status=FundamentalStatus(row.fundamentals_status),
        evaluated_at=row.fundamentals_evaluated_at,
        analysis_version=row.fundamentals_analysis_version or "",
        company_name=row.fundamentals_company_name,
        metrics={
            MetricName(metrik.name): Metric(
                name=MetricName(metrik.name),
                value=metrik.value,
                unit=MetricUnit(metrik.unit),
                basis=MetricBasis(metrik.basis),
                period_start=metrik.period_start,
                period_end=metrik.period_end,
                currency=metrik.currency,
                sources=tuple(_quelle_aus_json(eintrag) for eintrag in metrik.sources),
                retrieved_at=metrik.retrieved_at,
            )
            for metrik in row.fundamental_metrics
        },
        fiscal_years=tuple(row.fundamentals_fiscal_years or ()),
        price_used=row.fundamentals_price_used,
        tag_conflicts=tuple(
            TagConflict(
                figure=FigureName(eintrag["figure"]),
                period_end=date.fromisoformat(str(eintrag["period_end"])),
                chosen_tag=str(eintrag["chosen_tag"]),
                chosen_value=float(eintrag["chosen_value"]),
                other_tag=str(eintrag["other_tag"]),
                other_value=float(eintrag["other_value"]),
            )
            for eintrag in row.fundamentals_tag_conflicts or ()
        ),
        reason=row.fundamentals_reason,
    )


def _technical_columns(technical: TechnicalSnapshot | None) -> dict[str, Any]:
    """Spaltenwerte der Chartauswertung, ``technical_``-praefigiert.

    Ohne Auswertung werden alle Spalten ausdruecklich auf ``None`` gesetzt,
    statt sie wegzulassen: Beim Wiederverwenden einer Zeile haenge sonst am
    Spalten-Default, ob ein alter Wert stehen bleibt.
    """
    if technical is None:
        return {f"technical_{name}": None for name in _TECHNICAL_FIELDS}
    return {
        "technical_status": technical.status,
        "technical_evaluated_at": technical.evaluated_at,
        "technical_analysis_version": technical.analysis_version,
        # ``dict(...)``, weil die Domain eine ``Mapping`` fuehrt und
        # SQLAlchemy einen serialisierbaren Wert braucht.
        "technical_parameters": (
            None if technical.parameters is None else dict(technical.parameters)
        ),
        "technical_reason": technical.reason,
        "technical_candle_timestamp": technical.candle_timestamp,
        "technical_close": technical.close,
        "technical_trend": technical.trend,
        "technical_rsi": technical.rsi,
        "technical_ema5": technical.ema5,
        "technical_ema20": technical.ema20,
        "technical_distance_to_ema5_pct": technical.distance_to_ema5_pct,
        "technical_distance_to_ema20_pct": technical.distance_to_ema20_pct,
        "technical_atr": technical.atr,
        "technical_atr_pct": technical.atr_pct,
        "technical_recent_high": technical.recent_high,
        "technical_recent_high_at": technical.recent_high_at,
        "technical_recent_low": technical.recent_low,
        "technical_recent_low_at": technical.recent_low_at,
        "technical_downside_to_support_pct": technical.downside_to_support_pct,
        "technical_upside_to_resistance_pct": technical.upside_to_resistance_pct,
        "technical_chance_risk_ratio": technical.chance_risk_ratio,
    }


_TECHNICAL_AI_FIELDS = (
    "status",
    "evaluated_at",
    "model",
    "prompt_version",
    "interpreted_analysis_version",
    "summary",
    "trend_strength",
    "breakout_quality",
    "momentum_state",
    "false_signal_risk",
    "risk_reward_rating",
    "swing_entry_plausibility",
    "false_signal_risks",
    "confidence",
    "reason",
)


def _technical_ai_columns(assessment: TechnicalAssessment | None) -> dict[str, Any]:
    """Spaltenwerte der KI-Einordnung, ``technical_ai_``-praefigiert.

    Wie ``_technical_columns``: ohne Einordnung werden alle Spalten
    ausdruecklich auf ``None`` gesetzt statt weggelassen. Beide Zweige muessen
    dieselbe Schluesselmenge liefern -- ein Test sichert das zu.

    Beruehrt keine einzige ``technical_``-Spalte: Doc 10, Paragraph 6.8
    verlangt die getrennte Speicherung von Berechnung und Interpretation.
    """
    if assessment is None:
        return {f"technical_ai_{name}": None for name in _TECHNICAL_AI_FIELDS}
    return {
        "technical_ai_status": assessment.status,
        "technical_ai_evaluated_at": assessment.evaluated_at,
        "technical_ai_model": assessment.model,
        "technical_ai_prompt_version": assessment.prompt_version,
        "technical_ai_interpreted_analysis_version": assessment.interpreted_analysis_version,
        "technical_ai_summary": assessment.summary,
        "technical_ai_trend_strength": assessment.trend_strength,
        "technical_ai_breakout_quality": assessment.breakout_quality,
        "technical_ai_momentum_state": assessment.momentum_state,
        "technical_ai_false_signal_risk": assessment.false_signal_risk,
        "technical_ai_risk_reward_rating": assessment.risk_reward_rating,
        "technical_ai_swing_entry_plausibility": assessment.swing_entry_plausibility,
        "technical_ai_false_signal_risks": list(assessment.false_signal_risks),
        "technical_ai_confidence": assessment.confidence,
        "technical_ai_reason": assessment.reason,
    }


def _technical_ai_from_row(row: ScreeningResultOrm) -> TechnicalAssessment | None:
    """Liest die KI-Einordnung zurueck, sofern eine gespeichert wurde."""
    if row.technical_ai_status is None:
        return None
    evaluated_at = _require_paired_evaluated_at(
        row.id, row.technical_ai_evaluated_at, "technical_ai_status", "technical_ai_evaluated_at"
    )
    return TechnicalAssessment(
        status=TechnicalAssessmentStatus(row.technical_ai_status),
        evaluated_at=evaluated_at,
        model=row.technical_ai_model,
        prompt_version=row.technical_ai_prompt_version,
        interpreted_analysis_version=row.technical_ai_interpreted_analysis_version,
        summary=row.technical_ai_summary,
        trend_strength=(
            None
            if row.technical_ai_trend_strength is None
            else TrendStrength(row.technical_ai_trend_strength)
        ),
        breakout_quality=(
            None
            if row.technical_ai_breakout_quality is None
            else BreakoutQuality(row.technical_ai_breakout_quality)
        ),
        momentum_state=(
            None
            if row.technical_ai_momentum_state is None
            else MomentumState(row.technical_ai_momentum_state)
        ),
        false_signal_risk=(
            None
            if row.technical_ai_false_signal_risk is None
            else FalseSignalRisk(row.technical_ai_false_signal_risk)
        ),
        risk_reward_rating=(
            None
            if row.technical_ai_risk_reward_rating is None
            else RiskRewardRating(row.technical_ai_risk_reward_rating)
        ),
        swing_entry_plausibility=(
            None
            if row.technical_ai_swing_entry_plausibility is None
            else SwingEntryPlausibility(row.technical_ai_swing_entry_plausibility)
        ),
        false_signal_risks=tuple(row.technical_ai_false_signal_risks or ()),
        confidence=row.technical_ai_confidence,
        reason=row.technical_ai_reason,
    )


def _outcome_from_row(row: ScreeningResultOrm) -> StockScreeningOutcome:
    stock = Stock(id=row.stock.id, symbol=row.stock.symbol, exchange=row.stock.exchange)
    events = tuple(
        SignalEvent(signal_type=SignalType(event.signal_type), candle_index=event.candle_index)
        for event in row.signal_events
    )
    result = ScreeningResult(
        status=ScreeningStatus(row.status),
        fired_signal_types=frozenset(event.signal_type for event in events),
        signal_events=events,
        reason=row.reason,
        affected_index=row.affected_index,
    )
    earnings: EarningsFilterResult | None = None
    if row.earnings_status is not None:
        earnings_evaluated_at = _require_paired_evaluated_at(
            row.id, row.earnings_evaluated_at, "earnings_status", "earnings_evaluated_at"
        )
        earnings = EarningsFilterResult(
            status=EarningsFilterStatus(row.earnings_status),
            evaluated_at=earnings_evaluated_at,
            next_earnings_date=row.earnings_next_date,
            candles_until_earnings=row.earnings_candles_until,
            source=row.earnings_source,
            reason=row.earnings_reason,
        )
    research: ResearchReport | None = None
    if row.research_status is not None:
        research_evaluated_at = _require_paired_evaluated_at(
            row.id, row.research_evaluated_at, "research_status", "research_evaluated_at"
        )
        research = ResearchReport(
            status=ResearchStatus(row.research_status),
            evaluated_at=research_evaluated_at,
            model=row.research_model,
            prompt_version=row.research_prompt_version,
            analysis_version=row.research_analysis_version,
            summary=row.research_summary,
            positive_factors=tuple(row.research_positive_factors or ()),
            negative_factors=tuple(row.research_negative_factors or ()),
            risks=tuple(row.research_risks or ()),
            confidence=row.research_confidence,
            citations=tuple(
                Citation(
                    url=citation.url,
                    title=citation.title,
                    retrieved_at=citation.retrieved_at,
                    cited_text=citation.cited_text,
                    license_class=SourceLicenseClass(citation.license_class),
                    transformation=citation.transformation,
                    # Vor ADR 0029 geschriebene Zeilen tragen keinen Rang. Sie
                    # bekommen UNRANKED -- "wir wissen es nicht" -- statt einer
                    # nachtraeglich erfundenen Einstufung.
                    source_rank=(
                        SourceRank(citation.source_rank)
                        if citation.source_rank is not None
                        else SourceRank.UNRANKED
                    ),
                    source_age=citation.source_age,
                )
                for citation in row.research_citations
            ),
            coverage=(
                ResearchCoverage(row.research_coverage)
                if row.research_coverage is not None
                else None
            ),
            evidence=_research_evidence(row),
            reason=row.research_reason,
        )
    return StockScreeningOutcome(
        analysis_run_id=row.analysis_run_id,
        stock=stock,
        result=result,
        decision_candle_index=row.decision_candle_index,
        evaluated_at=row.evaluated_at,
        signal_rule_version=row.signal_rule_version,
        technical=_technical_from_row(row),
        technical_assessment=_technical_ai_from_row(row),
        earnings=earnings,
        research=research,
        fundamentals=_fundamentals_from_row(row),
        analysts=_analyst_from_row(row),
        swing_score=_score_from_row(row, "swing", ScoreKind.SWING),
        investment_score=_score_from_row(row, "long_term", ScoreKind.LONG_TERM),
        recommendation=_recommendation_from_row(row),
    )


class SqlAlchemyScreeningResultRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, outcome: StockScreeningOutcome) -> None:
        earnings = outcome.earnings
        research = outcome.research
        row = ScreeningResultOrm(
            id=uuid.uuid4(),
            analysis_run_id=outcome.analysis_run_id,
            stock_id=outcome.stock.id,
            status=outcome.result.status,
            reason=outcome.result.reason,
            affected_index=outcome.result.affected_index,
            decision_candle_index=outcome.decision_candle_index,
            evaluated_at=outcome.evaluated_at,
            signal_rule_version=outcome.signal_rule_version,
            earnings_status=earnings.status if earnings is not None else None,
            earnings_evaluated_at=earnings.evaluated_at if earnings is not None else None,
            earnings_next_date=earnings.next_earnings_date if earnings is not None else None,
            earnings_candles_until=(
                earnings.candles_until_earnings if earnings is not None else None
            ),
            earnings_source=earnings.source if earnings is not None else None,
            earnings_reason=earnings.reason if earnings is not None else None,
            research_status=research.status if research is not None else None,
            research_evaluated_at=research.evaluated_at if research is not None else None,
            research_model=research.model if research is not None else None,
            research_prompt_version=research.prompt_version if research is not None else None,
            research_analysis_version=(
                research.analysis_version if research is not None else None
            ),
            research_summary=research.summary if research is not None else None,
            research_positive_factors=(
                list(research.positive_factors) if research is not None else None
            ),
            research_negative_factors=(
                list(research.negative_factors) if research is not None else None
            ),
            research_risks=list(research.risks) if research is not None else None,
            research_confidence=research.confidence if research is not None else None,
            research_reason=research.reason if research is not None else None,
            research_coverage=research.coverage if research is not None else None,
            **_research_evidence_columns(research.evidence if research is not None else None),
            **_technical_columns(outcome.technical),
            **_technical_ai_columns(outcome.technical_assessment),
            **_fundamentals_columns(outcome.fundamentals),
            **_analyst_columns(outcome.analysts),
            **_score_columns("swing", outcome.swing_score),
            **_score_columns("long_term", outcome.investment_score),
            **_recommendation_columns(outcome.recommendation),
        )
        row.signal_events = [
            SignalEventOrm(
                id=uuid.uuid4(), signal_type=event.signal_type, candle_index=event.candle_index
            )
            for event in outcome.result.signal_events
        ]
        row.research_citations = [
            ResearchCitationOrm(
                id=uuid.uuid4(),
                position=position,
                url=citation.url,
                title=citation.title,
                retrieved_at=citation.retrieved_at,
                cited_text=citation.cited_text,
                license_class=citation.license_class,
                transformation=citation.transformation,
                source_rank=citation.source_rank,
                source_age=citation.source_age,
            )
            for position, citation in enumerate(
                research.citations if research is not None else ()
            )
        ]
        technical = outcome.technical
        row.technical_zones = [
            TechnicalZoneOrm(
                id=uuid.uuid4(),
                position=position,
                lower=zone.lower,
                upper=zone.upper,
                kind=zone.kind,
                strength=zone.strength,
                touch_count=zone.touch_count,
                last_confirmed_at=zone.last_confirmed_at,
                distance_pct=zone.distance_pct,
                pivot_count=zone.pivot_count,
            )
            for position, zone in enumerate(technical.zones if technical is not None else ())
        ]
        fundamentals = outcome.fundamentals
        row.fundamental_metrics = [
            FundamentalMetricOrm(
                id=uuid.uuid4(),
                position=position,
                name=metric.name,
                value=metric.value,
                unit=metric.unit,
                currency=metric.currency,
                basis=metric.basis,
                period_start=metric.period_start,
                period_end=metric.period_end,
                retrieved_at=metric.retrieved_at,
                sources=[_quelle_als_json(quelle) for quelle in metric.sources],
            )
            for position, metric in enumerate(
                fundamentals.metrics.values() if fundamentals is not None else ()
            )
        ]
        self._session.add(row)

    def list_for_run(self, run_id: uuid.UUID) -> Sequence[StockScreeningOutcome]:
        rows = (
            self._session.execute(
                select(ScreeningResultOrm).where(ScreeningResultOrm.analysis_run_id == run_id)
            )
            .scalars()
            .all()
        )
        return tuple(_outcome_from_row(row) for row in rows)


class SqlAlchemyProcessingErrorRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, error: StockProcessingError) -> None:
        self._session.add(
            ProcessingErrorOrm(
                id=uuid.uuid4(),
                analysis_run_id=error.analysis_run_id,
                stock_symbol=error.stock_symbol,
                message=error.message,
                occurred_at=error.occurred_at,
            )
        )

    def list_for_run(self, run_id: uuid.UUID) -> Sequence[StockProcessingError]:
        rows = (
            self._session.execute(
                select(ProcessingErrorOrm).where(ProcessingErrorOrm.analysis_run_id == run_id)
            )
            .scalars()
            .all()
        )
        return tuple(
            StockProcessingError(
                analysis_run_id=row.analysis_run_id,
                stock_symbol=row.stock_symbol,
                message=row.message,
                occurred_at=row.occurred_at,
            )
            for row in rows
        )


BARS_JE_INSERT = 1_000
"""Zeilen je Einfuegevorgang.

PostgreSQL nimmt hoechstens 65.535 Parameter je Anweisung entgegen. Bei
sieben Spalten je Bar reisst ein einzelnes Insert deshalb ab 9.363 Zeilen ab
-- nachgestellt und belegt. Der Standardzuschnitt (15-Minuten-Bars, ein Jahr
Historie) liegt mit rund 6.550 Bars knapp darunter und liefe heute noch
durch; fuenf Minuten Barbreite oder der in ADR 0014 (E3) vorgesehene
Fuenf-Jahres-Batch scheiterten sofort.

Tausend Zeilen belegen 7.000 Parameter -- reichlich Abstand, ohne die Zahl
der Anweisungen unnoetig hochzutreiben. Alle Bloecke laufen in derselben
Transaktion; ein Abbruch dazwischen laesst nichts halb Geschriebenes zurueck.
"""


class SqlAlchemyIntradayBarRepository:
    """Bar-Speicher fuer den Backfill.

    Alle Schreibvorgaenge sind ueber den Schluessel ``(symbol, start)``
    idempotent. Das ist keine Bequemlichkeit, sondern die Eigenschaft, die den
    Backfill wiederholbar macht: Ein abgebrochener Lauf wird schlicht erneut
    gestartet, und ueberlappende Zeitraeume kosten nichts.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def latest_start(self, symbol: str) -> datetime | None:
        return self._session.execute(
            select(func.max(IntradayBarOrm.start)).where(IntradayBarOrm.symbol == symbol)
        ).scalar_one_or_none()

    def latest_start_overall(self) -> datetime | None:
        return self._session.execute(select(func.max(IntradayBarOrm.start))).scalar_one_or_none()

    def earliest_start(self, symbol: str) -> datetime | None:
        return self._session.execute(
            select(func.min(IntradayBarOrm.start)).where(IntradayBarOrm.symbol == symbol)
        ).scalar_one_or_none()

    def add_all(self, symbol: str, bars: Sequence[IntradayBar]) -> int:
        if not bars:
            return 0
        self._reject_naive(symbol, bars)
        neu = 0
        for block in range(0, len(bars), BARS_JE_INSERT):
            neu += self._insert(symbol, bars[block : block + BARS_JE_INSERT])
        return neu

    @staticmethod
    def _reject_naive(symbol: str, bars: Sequence[IntradayBar]) -> None:
        """Naive Zeitstempel kommen hier nicht durch.

        Doc 10 untersagt sie, und ``ruff`` setzt das im eigenen Code ueber die
        ``DTZ``-Regeln durch. Eine Systemgrenze erreicht das nicht: PostgreSQL
        nimmt einen naiven Zeitstempel fuer eine ``timestamptz``-Spalte an und
        legt ihn in der Zeitzone der Datenbanksitzung aus -- serverabhaengig
        und damit nicht vorhersagbar. Zurueck kaeme ein zeitzonenbehafteter
        Wert, an dem nichts mehr auf den Fehler hinweist.

        Aus 09:30 New Yorker Zeit wuerde so 09:30 UTC. Der Bar laege
        ausserhalb des Sitzungsfensters, die Kerzenbildung verwuerfe ihn, und
        der Handelstag saehe aus wie einer ohne jede Lieferung -- der einzige
        Fall, den die Lueckenpruefung nicht erkennen kann.
        """
        naive = [bar.start for bar in bars if bar.start.tzinfo is None]
        if naive:
            raise ValueError(
                f"'{symbol}': {len(naive)} Bars ohne Zeitzone, erster {naive[0].isoformat()}. "
                "Zeitstempel muessen zeitzonenbehaftet sein (Doc 10)."
            )

    def _insert(self, symbol: str, bars: Sequence[IntradayBar]) -> int:
        statement = (
            pg_insert(IntradayBarOrm)
            .values(
                [
                    {
                        "symbol": symbol,
                        "start": bar.start,
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                    }
                    for bar in bars
                ]
            )
            .on_conflict_do_nothing(index_elements=["symbol", "start"])
            # Nicht ueber rowcount zaehlen: Bei einem Insert mit mehreren
            # Zeilen liefert der Treiber dafuer -1. RETURNING gibt bei
            # ON CONFLICT DO NOTHING ausschliesslich die tatsaechlich
            # geschriebenen Zeilen zurueck.
            .returning(IntradayBarOrm.start)
        )
        return len(self._session.execute(statement).all())

    def list_for(self, symbol: str) -> Sequence[IntradayBar]:
        rows = (
            self._session.execute(
                select(IntradayBarOrm)
                .where(IntradayBarOrm.symbol == symbol)
                .order_by(IntradayBarOrm.start)
            )
            .scalars()
            .all()
        )
        return tuple(
            IntradayBar(
                start=row.start,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
            )
            for row in rows
        )


def _gesamtwert(score: ScoreResult | None) -> float | None:
    """Die Zahl eines Scores -- ``None`` auch dann, wenn es einen Score gibt,
    er aber ``INSUFFICIENT_DATA`` ist. Eine Spalte, die nur zum Sortieren da
    ist, darf keinen Wert fuehren, den es nicht gibt."""
    return score.value if score is not None else None


def _horizon_metrics_from_row(row: BacktestResultOrm) -> HorizonMetrics:
    return HorizonMetrics(
        horizon=row.horizon,
        raw_event_count=row.raw_event_count,
        deduplicated_event_count=row.deduplicated_event_count,
        hit_rate=row.hit_rate,
        mean_return=row.mean_return,
        median_return=row.median_return,
        max_loss=row.max_loss,
        drawdown=row.drawdown,
        held_above_entry_rate=row.held_above_entry_rate,
        confidence=BacktestConfidence(row.confidence),
    )


def _group_rows_into_results(rows: Sequence[BacktestResultOrm]) -> tuple[BacktestResult, ...]:
    """Fasst Zeilen (eine je Horizont) wieder zu einem ``BacktestResult`` je
    Aktie, Signalkombination und Berechnungszeitpunkt zusammen."""
    grouped: dict[tuple[uuid.UUID, frozenset[SignalType], datetime], list[BacktestResultOrm]] = (
        defaultdict(list)
    )
    for row in rows:
        signal_types = frozenset(SignalType(value) for value in row.signal_types)
        grouped[(row.stock_id, signal_types, row.evaluated_at)].append(row)

    results = []
    for (stock_id, signal_types, evaluated_at), group_rows in grouped.items():
        first = group_rows[0]
        horizons = tuple(
            _horizon_metrics_from_row(row) for row in sorted(group_rows, key=lambda r: r.horizon)
        )
        results.append(
            BacktestResult(
                stock_id=stock_id,
                signal_types=signal_types,
                signal_rule_version=first.signal_rule_version,
                evaluated_at=evaluated_at,
                history_start=first.history_start,
                history_end=first.history_end,
                horizons=horizons,
                earnings_exclusion_applied=first.earnings_exclusion_applied,
            )
        )
    return tuple(results)


class SqlAlchemyStockReportRepository:
    """Berichte schreiben und je Lauf wieder lesen (ADR 0039).

    Kein Update-Pfad. Das Dokument geht als JSONB hinein und kommt unveraendert
    heraus -- es ist die verbindliche Fassung, nicht eine Ableitung, die man
    beim Lesen neu bauen duerfte.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, report: StockReport) -> None:
        self._session.add(
            StockReportOrm(
                id=uuid.uuid4(),
                analysis_run_id=report.analysis_run_id,
                stock_id=report.stock_id,
                created_at=report.created_at,
                report_schema_version=report.report_schema_version,
                app_version=report.app_version,
                scoring_version=report.scoring_version,
                # Nur die Stufe: Die Spalte beantwortet die Frage, fuer die
                # man das Dokument nicht oeffnen muss. Begruendung und
                # Deckelungen stehen vollstaendig in ``document`` und in
                # ``screening_results.recommendation_detail``.
                recommendation=(
                    report.recommendation.level if report.recommendation is not None else None
                ),
                # Nur die Zahl: Die Spalten daneben beantworten die Frage,
                # fuer die man das Dokument nicht oeffnen muss. Der
                # vollstaendige Score mit Teilwerten, Gewichten und
                # Begruendung steht in ``document`` -- und in
                # ``screening_results``.
                swing_score=_gesamtwert(report.swing_score),
                investment_score=_gesamtwert(report.investment_score),
                summary=report.summary,
                document=as_document(report),
            )
        )

    def list_for_run(self, analysis_run_id: uuid.UUID) -> Sequence[StoredReport]:
        rows = (
            self._session.execute(
                select(StockReportOrm)
                .where(StockReportOrm.analysis_run_id == analysis_run_id)
                .order_by(StockReportOrm.created_at)
            )
            .scalars()
            .all()
        )
        return [
            StoredReport(
                symbol=row.stock.symbol,
                created_at=row.created_at,
                report_schema_version=row.report_schema_version,
                app_version=row.app_version,
                document=row.document,
            )
            for row in rows
        ]


class SqlAlchemyBacktestResultRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, result: BacktestResult, analysis_run_id: uuid.UUID | None = None) -> None:
        sorted_signal_types = sorted(signal_type.value for signal_type in result.signal_types)
        rows = [
            BacktestResultOrm(
                id=uuid.uuid4(),
                stock_id=result.stock_id,
                analysis_run_id=analysis_run_id,
                signal_types=sorted_signal_types,
                signal_rule_version=result.signal_rule_version,
                evaluated_at=result.evaluated_at,
                history_start=result.history_start,
                history_end=result.history_end,
                horizon=horizon.horizon,
                raw_event_count=horizon.raw_event_count,
                deduplicated_event_count=horizon.deduplicated_event_count,
                hit_rate=horizon.hit_rate,
                mean_return=horizon.mean_return,
                median_return=horizon.median_return,
                max_loss=horizon.max_loss,
                drawdown=horizon.drawdown,
                held_above_entry_rate=horizon.held_above_entry_rate,
                confidence=horizon.confidence,
                earnings_exclusion_applied=result.earnings_exclusion_applied,
            )
            for horizon in result.horizons
        ]
        self._session.add_all(rows)

    def list_for_stock(self, stock_id: uuid.UUID) -> Sequence[BacktestResult]:
        rows = (
            self._session.execute(
                select(BacktestResultOrm).where(BacktestResultOrm.stock_id == stock_id)
            )
            .scalars()
            .all()
        )
        return _group_rows_into_results(rows)

