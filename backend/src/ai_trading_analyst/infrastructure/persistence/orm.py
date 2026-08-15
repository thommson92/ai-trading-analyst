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

from sqlalchemy import Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from ai_trading_analyst.domain.analysis import RunStatus
from ai_trading_analyst.domain.screening import ScreeningStatus, SignalType


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

    stock: Mapped[StockOrm] = relationship()
    signal_events: Mapped[list[SignalEventOrm]] = relationship(
        back_populates="screening_result", cascade="all, delete-orphan"
    )


class SignalEventOrm(Base):
    __tablename__ = "signal_events"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    screening_result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("screening_results.id"))
    signal_type: Mapped[SignalType] = mapped_column(_enum_column(SignalType))
    candle_index: Mapped[int]

    screening_result: Mapped[ScreeningResultOrm] = relationship(back_populates="signal_events")


class ProcessingErrorOrm(Base):
    """Modulfehler/Verarbeitungsstatus je isolierter Aktie (Fehlerisolation)."""

    __tablename__ = "analysis_run_errors"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id"))
    stock_symbol: Mapped[str]
    message: Mapped[str]
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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
