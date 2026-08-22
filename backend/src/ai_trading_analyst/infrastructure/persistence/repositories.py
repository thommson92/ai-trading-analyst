"""SQLAlchemy-Implementierungen der Domain-Ports (``domain.analysis.ports``)."""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
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
from ai_trading_analyst.domain.backtesting import (
    BacktestConfidence,
    BacktestResult,
    HorizonMetrics,
)
from ai_trading_analyst.domain.earnings import EarningsFilterResult, EarningsFilterStatus
from ai_trading_analyst.domain.research import (
    Citation,
    ResearchReport,
    ResearchStatus,
    SourceLicenseClass,
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
    IntradayBarOrm,
    ProcessingErrorOrm,
    ResearchCitationOrm,
    ScreeningResultOrm,
    SignalEventOrm,
    StockOrm,
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
                )
                for citation in row.research_citations
            ),
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
            **_technical_columns(outcome.technical),
            **_technical_ai_columns(outcome.technical_assessment),
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
                url=citation.url,
                title=citation.title,
                retrieved_at=citation.retrieved_at,
                cited_text=citation.cited_text,
                license_class=citation.license_class,
                transformation=citation.transformation,
            )
            for citation in (research.citations if research is not None else ())
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
            )
        )
    return tuple(results)


class SqlAlchemyBacktestResultRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, result: BacktestResult) -> None:
        sorted_signal_types = sorted(signal_type.value for signal_type in result.signal_types)
        rows = [
            BacktestResultOrm(
                id=uuid.uuid4(),
                stock_id=result.stock_id,
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
