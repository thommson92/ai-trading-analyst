"""SQLAlchemy-Modelle. Nur diese Datei kennt die Tabellenstruktur.

Rohdaten und fachliche Ergebnisse bleiben unterscheidbar: Sprint 1B
persistiert ausschliesslich das fachliche Ergebnis (``screening_results`` /
``signal_events``) -- Rohkerzendaten kommen im Walking Skeleton je Lauf frisch
vom ``FixtureMarketDataProvider`` und werden nicht gespeichert. Eine eigene
Kerzentabelle folgt erst, wenn ab Sprint 2 echte Kursdaten dauerhaft vorliegen
muessen.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import ARRAY, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from ai_trading_analyst.domain.analysis import RunStatus
from ai_trading_analyst.domain.backtesting import BacktestConfidence
from ai_trading_analyst.domain.earnings import EarningsFilterStatus
from ai_trading_analyst.domain.research import ResearchStatus, SourceLicenseClass
from ai_trading_analyst.domain.screening import ScreeningStatus, SignalType
from ai_trading_analyst.domain.technical import (
    TechnicalStatus,
    TrendDirection,
    ZoneKind,
    ZoneStrength,
)


class Base(DeclarativeBase):
    pass


def _enum_column(enum_type: type) -> SqlEnum:
    return SqlEnum(enum_type, values_callable=lambda e: [member.value for member in e])


class IntradayBarOrm(Base):
    """Native Bars des Anbieters, so wie er sie geliefert hat.

    Gespeichert werden **Rohbars, keine fertigen 195-Minuten-Kerzen.** Der
    Grund ist Erfahrung: Die Aggregationsregeln haben sich binnen einer Woche
    dreimal geaendert -- verkuerzte Handelstage, spaeter Handelsbeginn,
    stille Kuerzung der Antwort. Laegen nur Kerzen vor, haette jede dieser
    Korrekturen einen erneuten Abruf ueber ein Jahr und 192 Symbole verlangt:
    eine Stunde Laufzeit und die Anfragegrenzen von IBKR. Mit Rohbars ist eine
    Regelaenderung ein erneuter Lauf ueber lokale Daten.

    Der Schluessel ist ``(symbol, start)``, nicht die Aktien-ID: Bars werden
    vom Backfill geholt, unter Umstaenden bevor ueberhaupt ein
    ``stocks``-Eintrag existiert, und das Symbol ist die Kennung, die der
    Anbieter liefert. Derselbe Schluessel macht den Job **wiederholbar** --
    ein erneuter Abruf desselben Zeitraums schreibt keine Dubletten.
    """

    __tablename__ = "intraday_bars"

    symbol: Mapped[str] = mapped_column(primary_key=True)
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    open: Mapped[float]
    high: Mapped[float]
    low: Mapped[float]
    close: Mapped[float]
    volume: Mapped[float]


class StockOrm(Base):
    __tablename__ = "stocks"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    symbol: Mapped[str] = mapped_column(unique=True, index=True)
    exchange: Mapped[str]


class AnalysisRunOrm(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    status: Mapped[RunStatus] = mapped_column(_enum_column(RunStatus))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    number_of_stocks: Mapped[int] = mapped_column(default=0)
    candidates_found: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None] = mapped_column(nullable=True)


class ScreeningResultOrm(Base):
    """Ein abgeschlossenes Screening-Ergebnis wird nie per UPDATE veraendert
    -- die Unique Constraint verhindert zusaetzlich ein zweites, stillschweigend
    ueberschreibendes Insert fuer dieselbe Aktie im selben Lauf."""

    __tablename__ = "screening_results"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "stock_id", name="uq_screening_result_run_stock"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id"))
    stock_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stocks.id"))
    status: Mapped[ScreeningStatus] = mapped_column(_enum_column(ScreeningStatus))
    reason: Mapped[str | None] = mapped_column(nullable=True)
    affected_index: Mapped[int | None] = mapped_column(nullable=True)
    decision_candle_index: Mapped[int]
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    signal_rule_version: Mapped[str]

    # Earnings-Filter (Doc 10, Paragraph 6.5; ADR 0020) -- nur bei CANDIDATE
    # gesetzt, sonst durchgehend NULL. Eigene Spalten statt einer eigenen
    # Tabelle: die Entscheidung wird einmal je Lauf und Aktie berechnet, nie
    # unabhaengig vom Screening-Ergebnis abgefragt (wie reason/affected_index
    # oben).
    earnings_status: Mapped[EarningsFilterStatus | None] = mapped_column(
        _enum_column(EarningsFilterStatus), nullable=True
    )
    earnings_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    earnings_next_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    earnings_candles_until: Mapped[int | None] = mapped_column(nullable=True)
    earnings_source: Mapped[str | None] = mapped_column(nullable=True)
    earnings_reason: Mapped[str | None] = mapped_column(nullable=True)

    # Deterministische Chartauswertung (Doc 10, Paragraph 6.8; ADR 0025) --
    # wie bei den earnings_*-Spalten nur bei CANDIDATE gesetzt. Getrennt von
    # jeder KI-Interpretation gespeichert, wie Doc 10, Paragraph 6.8
    # ausdruecklich verlangt: Der Technical Agent schreibt spaeter in eigene
    # Spalten und veraendert keine einzige der folgenden.
    technical_status: Mapped[TechnicalStatus | None] = mapped_column(
        _enum_column(TechnicalStatus), nullable=True
    )
    technical_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    technical_analysis_version: Mapped[str | None] = mapped_column(nullable=True)
    technical_reason: Mapped[str | None] = mapped_column(nullable=True)
    technical_candle_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    technical_close: Mapped[float | None] = mapped_column(nullable=True)
    technical_trend: Mapped[TrendDirection | None] = mapped_column(
        _enum_column(TrendDirection), nullable=True
    )
    technical_rsi: Mapped[float | None] = mapped_column(nullable=True)
    technical_ema5: Mapped[float | None] = mapped_column(nullable=True)
    technical_ema20: Mapped[float | None] = mapped_column(nullable=True)
    technical_distance_to_ema5_pct: Mapped[float | None] = mapped_column(nullable=True)
    technical_distance_to_ema20_pct: Mapped[float | None] = mapped_column(nullable=True)
    technical_atr: Mapped[float | None] = mapped_column(nullable=True)
    technical_atr_pct: Mapped[float | None] = mapped_column(nullable=True)
    technical_recent_high: Mapped[float | None] = mapped_column(nullable=True)
    technical_recent_high_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    technical_recent_low: Mapped[float | None] = mapped_column(nullable=True)
    technical_recent_low_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Research Agent (Doc 10, Paragraph 6.7 und 10; ADR 0021, ADR 0023) --
    # wie bei den earnings_*-Spalten: einmal je Lauf und Aktie berechnet,
    # nie unabhaengig vom Screening-Ergebnis abgefragt. Nur gesetzt, wenn
    # zusaetzlich earnings_status == EARNINGS_CLEAR war.
    research_status: Mapped[ResearchStatus | None] = mapped_column(
        _enum_column(ResearchStatus), nullable=True
    )
    research_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    research_model: Mapped[str | None] = mapped_column(nullable=True)
    research_prompt_version: Mapped[str | None] = mapped_column(nullable=True)
    research_summary: Mapped[str | None] = mapped_column(nullable=True)
    research_positive_factors: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    research_negative_factors: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    research_risks: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    research_confidence: Mapped[float | None] = mapped_column(nullable=True)
    research_reason: Mapped[str | None] = mapped_column(nullable=True)

    stock: Mapped[StockOrm] = relationship()
    signal_events: Mapped[list[SignalEventOrm]] = relationship(
        back_populates="screening_result", cascade="all, delete-orphan"
    )
    research_citations: Mapped[list[ResearchCitationOrm]] = relationship(
        back_populates="screening_result", cascade="all, delete-orphan"
    )
    technical_zones: Mapped[list[TechnicalZoneOrm]] = relationship(
        back_populates="screening_result",
        cascade="all, delete-orphan",
        order_by="TechnicalZoneOrm.position",
    )


class SignalEventOrm(Base):
    __tablename__ = "signal_events"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    screening_result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("screening_results.id"))
    signal_type: Mapped[SignalType] = mapped_column(_enum_column(SignalType))
    candle_index: Mapped[int]

    screening_result: Mapped[ScreeningResultOrm] = relationship(back_populates="signal_events")


class TechnicalZoneOrm(Base):
    """Eine Unterstuetzungs- oder Widerstandszone eines Screening-Ergebnisses.

    Eigene Tabelle statt Spalten: Anders als beim Earnings-Filter ist die Zahl
    der Zonen nicht fest, und jede einzelne traegt die sieben Angaben, die
    Doc 10, Paragraph 6.8 verlangt.
    """

    __tablename__ = "technical_zones"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    screening_result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("screening_results.id"))
    position: Mapped[int]
    """Rang in der nach Abstand zum Kurs sortierten Ausgabe. Ohne ihn gaebe
    die Datenbank die Zonen in unbestimmter Reihenfolge zurueck, und die
    Naehe zum Kurs -- die eigentliche Aussage der Sortierung -- ginge beim
    Wiedereinlesen verloren."""
    lower: Mapped[float]
    upper: Mapped[float]
    kind: Mapped[ZoneKind] = mapped_column(_enum_column(ZoneKind))
    strength: Mapped[ZoneStrength] = mapped_column(_enum_column(ZoneStrength))
    touch_count: Mapped[int]
    last_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    distance_pct: Mapped[float]
    pivot_count: Mapped[int]

    screening_result: Mapped[ScreeningResultOrm] = relationship(back_populates="technical_zones")


class ResearchCitationOrm(Base):
    """Ein einzelner Beleg eines Research-Berichts (ADR 0023, Zitier-
    architektur) -- eigene Tabelle statt einer flachen Spalte, weil jedes
    Zitat mehrere Felder hat (Muster ``SignalEventOrm``)."""

    __tablename__ = "research_citations"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    screening_result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("screening_results.id"))
    url: Mapped[str]
    title: Mapped[str]
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cited_text: Mapped[str | None] = mapped_column(nullable=True)
    license_class: Mapped[SourceLicenseClass] = mapped_column(_enum_column(SourceLicenseClass))
    transformation: Mapped[str]

    screening_result: Mapped[ScreeningResultOrm] = relationship(
        back_populates="research_citations"
    )


class ProcessingErrorOrm(Base):
    """Modulfehler/Verarbeitungsstatus je isolierter Aktie (Fehlerisolation)."""

    __tablename__ = "analysis_run_errors"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id"))
    stock_symbol: Mapped[str]
    message: Mapped[str]
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BacktestResultOrm(Base):
    """Ein Zeile je Aktie, Signalkombination und Horizont (Doc 07; G1-Pruefvorlage
    Abschnitt 4).

    Keine Unique Constraint, kein Update-Pfad -- jede Neuberechnung ist ein
    neues, zeitgestempeltes Insert (Projektregel: abgeschlossene Analysen
    werden nicht ueberschrieben).
    """

    __tablename__ = "backtest_results"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    stock_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stocks.id"))
    signal_types: Mapped[list[str]] = mapped_column(ARRAY(String))
    """Sortierte Werte von ``SignalType`` -- die Domain rekonstruiert daraus
    ein ``frozenset`` (Menge, nicht Liste, G1-Pruefvorlage Abschnitt 4.3)."""
    signal_rule_version: Mapped[str]
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    history_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    history_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    horizon: Mapped[int] = mapped_column(Integer)
    raw_event_count: Mapped[int]
    deduplicated_event_count: Mapped[int]
    hit_rate: Mapped[float | None]
    mean_return: Mapped[float | None]
    median_return: Mapped[float | None]
    max_loss: Mapped[float | None]
    drawdown: Mapped[float | None]
    held_above_entry_rate: Mapped[float | None]
    confidence: Mapped[BacktestConfidence] = mapped_column(_enum_column(BacktestConfidence))

    stock: Mapped[StockOrm] = relationship()


class DispatcherRunOrm(Base):
    """Zustand des taeglichen Dispatchers (ADR 0019).

    Der Schluessel ist bewusst ``(session_date, candle_close)`` und nicht der
    Handelstag allein: Wird spaeter auch nach der zweiten Tageskerze
    gerechnet, sind das zwei getrennte Laeufe desselben Tages.

    Die Tabelle liegt in derselben Datenbank wie die Analyseergebnisse. Zwei
    Orte fuer zusammengehoerigen Zustand waeren eine Quelle fuer Widersprueche
    nach einem Absturz zwischen beiden Schreibvorgaengen.
    """

    __tablename__ = "dispatcher_runs"

    session_date: Mapped[date] = mapped_column(Date, primary_key=True)
    candle_close: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    status: Mapped[str]
    """``running``, ``succeeded`` oder ``failed``.

    Nur ``succeeded`` haelt den naechsten Start ab. Ein gescheiterter Versuch
    darf den Lauf nicht blockieren -- eine nicht angemeldete TWS ist der
    haeufigste Grund, und der naechste Start soll es erneut versuchen.
    """
    attempts: Mapped[int]
    first_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_error: Mapped[str | None] = mapped_column(default=None)
    alert_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    """Ohne diesen Vermerk meldete sich der Dispatcher nach Fristablauf alle
    15 Minuten erneut."""
