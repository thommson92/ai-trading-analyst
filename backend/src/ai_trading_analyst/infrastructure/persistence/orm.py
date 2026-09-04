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
from typing import Any

from sqlalchemy import (
    ARRAY,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from ai_trading_analyst.domain.analysis import RunStatus
from ai_trading_analyst.domain.analysts import AnalystRecommendationStatus
from ai_trading_analyst.domain.backtesting import BacktestConfidence
from ai_trading_analyst.domain.earnings import EarningsFilterStatus
from ai_trading_analyst.domain.fundamentals import (
    FundamentalStatus,
    MetricBasis,
    MetricName,
    MetricUnit,
)
from ai_trading_analyst.domain.options import OptionsStatus
from ai_trading_analyst.domain.research import (
    ResearchCoverage,
    ResearchStatus,
    SourceLicenseClass,
    SourceRank,
)
from ai_trading_analyst.domain.scoring import Recommendation, ScoreStatus
from ai_trading_analyst.domain.screening import ScreeningStatus, SignalType
from ai_trading_analyst.domain.technical import (
    BreakoutQuality,
    FalseSignalRisk,
    MomentumState,
    RiskRewardRating,
    SwingEntryPlausibility,
    TechnicalAssessmentStatus,
    TechnicalStatus,
    TrendDirection,
    TrendStrength,
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
    technical_parameters: Mapped[dict[str, float] | None] = mapped_column(JSONB, nullable=True)
    """Die Parameter, mit denen gerechnet wurde. Zusammen mit
    ``technical_analysis_version`` die vollstaendige Auskunft darueber, wie
    dieses Ergebnis zustande kam -- Doc 14 fordert ausdruecklich dazu auf,
    Zonenbreite und Schwellen zwischen Laeufen nachzuziehen.

    JSONB und keine elf einzelnen Spalten: Sie werden nur geschrieben und
    gelesen, nie gefiltert oder sortiert. Ein neuer Parameter braucht so
    keine Migration, und ein alter bleibt in alten Zeilen lesbar."""
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
    # Weg bis zur naechsten Unterstuetzung, Weg bis zum naechsten Widerstand
    # und ihr Verhaeltnis (ADR 0026) -- gespeichert und nicht beim Lesen
    # abgeleitet, damit eine spaetere Aenderung der Herleitung die Zahlen
    # abgeschlossener Analysen nicht rueckwirkend verschiebt.
    technical_downside_to_support_pct: Mapped[float | None] = mapped_column(nullable=True)
    technical_upside_to_resistance_pct: Mapped[float | None] = mapped_column(nullable=True)
    technical_chance_risk_ratio: Mapped[float | None] = mapped_column(nullable=True)

    # Technical Agent: die KI-Einordnung der Chartauswertung (Doc 10,
    # Paragraph 6.8 "Qualitative Interpretation"; ADR 0026). Ein eigener
    # Spaltensatz -- keine der technical_*-Spalten darueber wird davon
    # beruehrt, wie Doc 10 die getrennte Speicherung verlangt.
    #
    # Gesetzt, sobald technical_status gesetzt ist, und zwar unabhaengig vom
    # Earnings-Filter: anders als research_*, das EARNINGS_CLEAR voraussetzt.
    technical_ai_status: Mapped[TechnicalAssessmentStatus | None] = mapped_column(
        _enum_column(TechnicalAssessmentStatus), nullable=True
    )
    technical_ai_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    technical_ai_model: Mapped[str | None] = mapped_column(nullable=True)
    technical_ai_prompt_version: Mapped[str | None] = mapped_column(nullable=True)
    technical_ai_interpreted_analysis_version: Mapped[str | None] = mapped_column(nullable=True)
    technical_ai_summary: Mapped[str | None] = mapped_column(nullable=True)
    technical_ai_trend_strength: Mapped[TrendStrength | None] = mapped_column(
        _enum_column(TrendStrength), nullable=True
    )
    technical_ai_breakout_quality: Mapped[BreakoutQuality | None] = mapped_column(
        _enum_column(BreakoutQuality), nullable=True
    )
    technical_ai_momentum_state: Mapped[MomentumState | None] = mapped_column(
        _enum_column(MomentumState), nullable=True
    )
    technical_ai_false_signal_risk: Mapped[FalseSignalRisk | None] = mapped_column(
        _enum_column(FalseSignalRisk), nullable=True
    )
    technical_ai_risk_reward_rating: Mapped[RiskRewardRating | None] = mapped_column(
        _enum_column(RiskRewardRating), nullable=True
    )
    technical_ai_swing_entry_plausibility: Mapped[SwingEntryPlausibility | None] = mapped_column(
        _enum_column(SwingEntryPlausibility), nullable=True
    )
    technical_ai_false_signal_risks: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    technical_ai_confidence: Mapped[float | None] = mapped_column(nullable=True)
    technical_ai_reason: Mapped[str | None] = mapped_column(nullable=True)

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
    research_analysis_version: Mapped[str | None] = mapped_column(nullable=True)
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
    # Abdeckung neben dem Status, nicht darin (ADR 0029): research_status sagt,
    # dass der Lauf durchlief -- diese Spalten, worauf er steht.
    research_coverage: Mapped[ResearchCoverage | None] = mapped_column(
        _enum_column(ResearchCoverage), nullable=True
    )
    research_distinct_sources: Mapped[int | None] = mapped_column(nullable=True)
    research_successful_fetches: Mapped[int | None] = mapped_column(nullable=True)
    research_rejected_tool_calls: Mapped[int | None] = mapped_column(nullable=True)
    research_dropped_citations: Mapped[int | None] = mapped_column(nullable=True)

    # Deterministische Fundamentalanalyse (Doc 10, Paragraph 6.9; ADR 0035)
    # -- wie die technical_*-Spalten nur bei CANDIDATE gesetzt. Die
    # Kennzahlen selbst stehen in ``fundamental_metrics``: Ihre Zahl ist
    # nicht fest, weil fehlende gar nicht erst entstehen, und jede traegt
    # ihren eigenen Zeitbezug (ADR 0033 L2).
    fundamentals_status: Mapped[FundamentalStatus | None] = mapped_column(
        _enum_column(FundamentalStatus), nullable=True
    )
    fundamentals_analysis_version: Mapped[str | None] = mapped_column(nullable=True)
    fundamentals_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fundamentals_company_name: Mapped[str | None] = mapped_column(nullable=True)
    """Der amtliche Name des Registranten aus dem SEC-Symbolverzeichnis --
    die einzige Quelle, die das System fuer Berichtspunkt 1 hat (Doc 10,
    Paragraph 6.12). Fehlt der Eintrag, bleibt die Spalte leer."""
    fundamentals_reason: Mapped[str | None] = mapped_column(nullable=True)
    fundamentals_price_used: Mapped[float | None] = mapped_column(nullable=True)
    """Der Kurs, mit dem die vier bewertungsabhaengigen Kennzahlen gerechnet
    wurden -- der Schluss der letzten abgeschlossenen Kerze (ADR 0035,
    Entscheidung 2). Ohne ihn liesse sich ein Kurs-Gewinn-Verhaeltnis spaeter
    nicht nachrechnen, und die Kennzahl waere eine Behauptung statt eines
    Belegs."""
    fundamentals_fiscal_years: Mapped[list[int] | None] = mapped_column(JSONB, nullable=True)
    fundamentals_tag_conflicts: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )
    """Die gemeldeten Tag-Widersprueche (ADR 0032, Entscheidung 2).

    JSONB und keine Kindtabelle: Sie werden geschrieben und im Ganzen
    gelesen, nie gefiltert oder sortiert -- dasselbe Argument wie bei
    ``technical_parameters``. Dazu ein zweites: Es sind im Mittel zehn je
    Aktie und bei einzelnen ueber vierzig; als Zeilen waeren das mehr als
    fuer alle uebrigen Analysemodule zusammen, fuer eine rein diagnostische
    Angabe (ADR 0035, Entscheidung 6)."""

    # Analystenempfehlungen (Doc 10, Paragraph 6.12 Punkt 9; ADR 0043) --
    # wie die uebrigen Analysespalten nur bei CANDIDATE gesetzt.
    analyst_status: Mapped[AnalystRecommendationStatus | None] = mapped_column(
        _enum_column(AnalystRecommendationStatus), nullable=True
    )
    analyst_analysis_version: Mapped[str | None] = mapped_column(nullable=True)
    analyst_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    analyst_source: Mapped[str | None] = mapped_column(nullable=True)
    analyst_source_url: Mapped[str | None] = mapped_column(nullable=True)
    """Die Adresse, unter der die Verteilung herkam -- vom Anbieter
    gesetzt, damit ein Fixture-Lauf nicht die Adresse des echten
    Dienstes traegt (ADR 0043)."""
    analyst_retrieved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    analyst_reason: Mapped[str | None] = mapped_column(nullable=True)
    analyst_periods: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    """Die Votenverteilung je Monatsstand, neuester zuerst.

    JSONB und keine Kindtabelle: Sie wird im Ganzen geschrieben und im Ganzen
    gelesen, nie gefiltert oder sortiert -- dasselbe Argument wie bei
    ``fundamentals_tag_conflicts``. Es sind hoechstens vier Eintraege je
    Aktie und Lauf (``analyst_ratings.months``); als Zeilen waere das eine
    Tabelle fuer eine Angabe, die nur am Stueck etwas bedeutet."""

    # Die beiden Scores (Doc 10, Paragraph 6.11; ADR 0041, ADR 0045) -- wie
    # die uebrigen Analysespalten nur bei CANDIDATE gesetzt.
    #
    # Vier Spalten je Score und nicht vierzehn: Sortiert und gefiltert wird
    # ausschliesslich nach dem Gesamtwert, alles Uebrige wird im Ganzen
    # geschrieben und im Ganzen gelesen -- dasselbe Argument wie bei
    # ``technical_parameters`` und ``fundamentals_tag_conflicts``. Eine neue
    # Komponente braucht so keine Migration, und eine alte bleibt in alten
    # Zeilen lesbar.
    swing_score: Mapped[float | None] = mapped_column(
        Numeric(4, 1, asdecimal=False), nullable=True
    )
    """Der Gesamtwert zwischen 0 und 10, oder NULL bei
    ``INSUFFICIENT_DATA``. ``NUMERIC(4,1)`` und kein ``float``: Ein Score
    traegt genau eine Nachkommastelle, und die Spalte soll das festhalten
    statt es der Binaerrundung zu ueberlassen. ``asdecimal=False``, damit
    beim Lesen ein ``float`` zurueckkommt und nicht ein ``Decimal``, das die
    Typangabe Luegen straft."""
    swing_status: Mapped[ScoreStatus | None] = mapped_column(
        _enum_column(ScoreStatus), nullable=True
    )
    swing_version: Mapped[str | None] = mapped_column(nullable=True)
    swing_detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    """Teilwerte, Gewichte, Abdeckung, Konfidenz, Faktoren und begrenzende
    Risiken -- die uebrigen acht der neun Angaben aus Doc 10, Paragraph
    6.11."""
    long_term_score: Mapped[float | None] = mapped_column(
        Numeric(4, 1, asdecimal=False), nullable=True
    )
    long_term_status: Mapped[ScoreStatus | None] = mapped_column(
        _enum_column(ScoreStatus), nullable=True
    )
    long_term_version: Mapped[str | None] = mapped_column(nullable=True)
    long_term_detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Die Optionsanalyse (Doc 10, Paragraph 6.12 Punkt 13; ADR 0048) -- wie
    # die fundamentals_*-Spalten nur bei CANDIDATE gesetzt.
    options_status: Mapped[OptionsStatus | None] = mapped_column(
        _enum_column(OptionsStatus), nullable=True
    )
    options_analysis_version: Mapped[str | None] = mapped_column(nullable=True)
    options_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    options_reason: Mapped[str | None] = mapped_column(nullable=True)
    options_underlying_price: Mapped[float | None] = mapped_column(nullable=True)
    """Der Kurs, auf dem die Strike-Auswahl stand -- der Schluss der letzten
    abgeschlossenen Kerze. Ohne ihn liesse sich der Abstand eines Strikes zum
    Kurs spaeter nicht nachrechnen."""
    options_expiration: Mapped[date | None] = mapped_column(Date, nullable=True)
    options_spread: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    """Der Put-Spread zum bestbewerteten Vorschlag (ADR 0058, Festlegung 11).

    JSONB wie ``options_strategies`` und aus demselben Grund: im Ganzen
    geschrieben, im Ganzen gelesen, nie gefiltert oder sortiert. Anders als
    die Rohnotierungen -- die gehoeren in eine eigene Tabelle, weil ueber sie
    aggregiert wird."""
    options_spread_reason: Mapped[str | None] = mapped_column(nullable=True)
    """Warum kein Spread entstand -- im Klartext, nie stillschweigend.

    Eigene Spalte neben ``options_reason``: Die Optionsanalyse kann
    vollstaendig sein und der Strukturvergleich trotzdem fehlen. Beide Gruende
    in eine Spalte zu legen hiesse, zwei verschiedene Ausfaelle zu
    verwechseln."""
    options_strategies: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )
    """Die bewerteten Put-Vorschlaege, hoechstens drei je Kandidat.

    JSONB und keine Kindtabelle: im Ganzen geschrieben, im Ganzen gelesen,
    nie gefiltert oder sortiert -- dasselbe Argument wie bei ``swing_detail``
    und ``fundamentals_tag_conflicts``. Neunzehn Felder je Vorschlag als
    Spalten waeren mehr als fuer alle uebrigen Analysemodule zusammen."""

    # Die Empfehlungsstufe (Doc 10, Paragraph 6.12 Punkt 16; ADR 0046) --
    # wie die Scores nur bei CANDIDATE gesetzt.
    recommendation: Mapped[Recommendation | None] = mapped_column(
        _enum_column(Recommendation), nullable=True
    )
    """Die Stufe selbst -- die einzige Groesse, nach der je gefiltert wird."""
    recommendation_detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    """Begruendungsbausteine, angewandte Deckelungen und die Version.

    JSONB und keine drei Spalten: im Ganzen geschrieben, im Ganzen gelesen --
    dasselbe Argument wie bei ``swing_detail``. Ohne diese Angaben stuende im
    Bericht eine Empfehlung ohne Grund, und Doc 10, Paragraph 12 verlangt das
    Gegenteil."""

    stock: Mapped[StockOrm] = relationship()
    signal_events: Mapped[list[SignalEventOrm]] = relationship(
        back_populates="screening_result", cascade="all, delete-orphan"
    )
    research_citations: Mapped[list[ResearchCitationOrm]] = relationship(
        back_populates="screening_result",
        cascade="all, delete-orphan",
        order_by="ResearchCitationOrm.position",
    )
    technical_zones: Mapped[list[TechnicalZoneOrm]] = relationship(
        back_populates="screening_result",
        cascade="all, delete-orphan",
        order_by="TechnicalZoneOrm.position",
    )
    fundamental_metrics: Mapped[list[FundamentalMetricOrm]] = relationship(
        back_populates="screening_result",
        cascade="all, delete-orphan",
        order_by="FundamentalMetricOrm.position",
    )
    option_quotes: Mapped[list[OptionQuoteOrm]] = relationship(
        back_populates="screening_result",
        cascade="all, delete-orphan",
        order_by="OptionQuoteOrm.position",
    )


class SignalEventOrm(Base):
    __tablename__ = "signal_events"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    screening_result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("screening_results.id"))
    signal_type: Mapped[SignalType] = mapped_column(_enum_column(SignalType))
    candle_index: Mapped[int]

    screening_result: Mapped[ScreeningResultOrm] = relationship(back_populates="signal_events")


class OptionQuoteOrm(Base):
    """Eine einzelne abgerufene Put-Notierung (ADR 0058, Festlegung 1).

    **Eigene Tabelle und nicht JSONB wie ``options_strategies``** -- und zwar
    nach dem Kriterium, das dort selbst genannt ist: Die Vorschlaege werden
    "im Ganzen geschrieben, im Ganzen gelesen, nie gefiltert oder sortiert".
    Bei den Rohnotierungen ist genau das Gegenteil der Zweck. Sie existieren,
    um spaeter nach Moneyness gruppiert, ueber Zeitraeume aggregiert und gegen
    die modellierte Praemie gehalten zu werden; als JSONB muesste jede dieser
    Abfragen die Menge erst entpacken.

    Keine Spalten fuer Zeitpunkt und Aktienkurs: Beide stehen mit
    ``options_evaluated_at`` und ``options_underlying_price`` an der
    Elternzeile und gelten fuer jede Notierung desselben Abrufs gleich.
    """

    __tablename__ = "option_quotes"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    screening_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("screening_results.id"), index=True
    )
    """``index=True`` gehoert an das Modell und nicht nur in die Migration --
    sonst erzeugte das naechste ``alembic revision --autogenerate`` ein
    ``drop_index``, weil ``env.py`` gegen ``Base.metadata`` vergleicht."""
    position: Mapped[int]
    """Reihenfolge des Abrufs -- die Strikes kommen absteigend, die
    naechstliegenden zuerst (``select_strikes``). Muster
    ``TechnicalZoneOrm.position``: Eine Relationship ohne ``order_by``
    liefert die Kinder in einer Reihenfolge, die die Datenbank bestimmt."""
    expiration: Mapped[date] = mapped_column(Date)
    strike: Mapped[float]
    bid: Mapped[float | None] = mapped_column(nullable=True)
    ask: Mapped[float | None] = mapped_column(nullable=True)
    delta: Mapped[float | None] = mapped_column(nullable=True)
    """Vorzeichenbehaftet, wie der Anbieter ihn liefert -- fuer einen Put also
    negativ. Bewusst **nicht** als Betrag gespeichert wie am Vorschlag: Hier
    steht, was ankam, nicht, was daraus gemacht wurde."""
    implied_volatility: Mapped[float | None] = mapped_column(nullable=True)
    open_interest: Mapped[int | None] = mapped_column(nullable=True)
    volume: Mapped[int | None] = mapped_column(nullable=True)

    screening_result: Mapped[ScreeningResultOrm] = relationship(back_populates="option_quotes")


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


class FundamentalMetricOrm(Base):
    """Eine gerechnete Fundamentalkennzahl (ADR 0035, Entscheidung 5).

    Eigene Tabelle statt achtzehn mal sechs Spalten: Die Zahl der Kennzahlen
    ist nicht fest -- was sich nicht rechnen liess, entsteht gar nicht --,
    und jede traegt Einheit, Basis und Zeitraum einzeln. Zwei Kennzahlen
    desselben Berichts koennen verschiedene Zeitbezuege haben (ADR 0033 L2),
    weshalb Basis und Zeitraum an der Kennzahl stehen und nicht am Ergebnis.
    """

    __tablename__ = "fundamental_metrics"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    screening_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("screening_results.id"), index=True
    )
    """``index=True`` gehoert hierher und nicht nur in die Migration: Ohne ihn
    am Modell erzeugte das naechste ``alembic revision --autogenerate`` ein
    ``drop_index``, weil ``env.py`` gegen ``Base.metadata`` vergleicht.

    Genau das war bis 2026-09-04 der Fall -- der Docstring stand hier, die
    Angabe fehlte. Die Migration ``b7e3d9a5c210`` legt den Index an, er
    existiert also produktiv; er fehlte allein am Modell. Keine
    Schemaaenderung, nur der Gleichstand, der den destruktiven Vorschlag
    verhindert."""
    position: Mapped[int]
    """Reihenfolge der Ausgabe. Muster ``TechnicalZoneOrm.position``: Eine
    Relationship ohne ``order_by`` liefert die Kinder in einer Reihenfolge,
    die die Datenbank bestimmt."""
    name: Mapped[MetricName] = mapped_column(_enum_column(MetricName))
    value: Mapped[float]
    unit: Mapped[MetricUnit] = mapped_column(_enum_column(MetricUnit))
    currency: Mapped[str | None] = mapped_column(nullable=True)
    basis: Mapped[MetricBasis] = mapped_column(_enum_column(MetricBasis))
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date] = mapped_column(Date)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    """Herkunft je Kennzahl -- bis zu drei Eintraege, weil eine Marge auf
    zwei Tags und der freie Cashflow auf zwei weiteren steht. JSONB aus
    demselben Grund wie ``technical_parameters``: geschrieben und im Ganzen
    gelesen, nie gefiltert. Die Quellenbindung aus CLAUDE.md verlangt CIK,
    Einreichung, Formular, Tag und Einreichungsdatum -- alle fuenf stehen
    darin."""

    screening_result: Mapped[ScreeningResultOrm] = relationship(
        back_populates="fundamental_metrics"
    )


class ResearchCitationOrm(Base):
    """Ein einzelner Beleg eines Research-Berichts (ADR 0023, Zitier-
    architektur) -- eigene Tabelle statt einer flachen Spalte, weil jedes
    Zitat mehrere Felder hat (Muster ``SignalEventOrm``)."""

    __tablename__ = "research_citations"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    screening_result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("screening_results.id"))
    position: Mapped[int]
    """Rangreihenfolge aus ``rank_and_cap`` (ADR 0029).

    Ohne eigene Spalte waere sie nach dem ersten Neuladen verloren: Eine
    Relationship ohne ``order_by`` liefert die Kinder in einer Reihenfolge,
    die die Datenbank bestimmt. Muster ``TechnicalZoneOrm.position``."""
    url: Mapped[str]
    title: Mapped[str]
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cited_text: Mapped[str | None] = mapped_column(nullable=True)
    license_class: Mapped[SourceLicenseClass] = mapped_column(_enum_column(SourceLicenseClass))
    transformation: Mapped[str]
    # Getrennt von der Lizenzklasse (ADR 0029): jene beantwortet die
    # Rechtsfrage, dieser die Belastbarkeit.
    source_rank: Mapped[SourceRank | None] = mapped_column(
        _enum_column(SourceRank), nullable=True
    )
    source_age: Mapped[str | None] = mapped_column(nullable=True)
    """Rohwert des Anbieters, nie geparst -- siehe ``Citation.source_age``."""

    screening_result: Mapped[ScreeningResultOrm] = relationship(back_populates="research_citations")


class StockReportOrm(Base):
    """Der Analysebericht einer Aktie fuer einen Lauf (Doc 10, Paragraph 6.12;
    ADR 0039).

    Ein Datensatz je Lauf und Aktie, nie per UPDATE veraendert -- die Unique
    Constraint verhindert zusaetzlich ein zweites, stillschweigend
    ueberschreibendes Insert (Muster ``uq_screening_result_run_stock``).

    Der Name weicht von Doc 05 (``StockAnalysis``) ab: „Analysis" ist im
    Schema bereits mit ``analysis_runs`` belegt. Gemeint ist dieselbe Entitaet.

    Das vollstaendige Dokument steht als JSONB in ``document``. Es verdoppelt
    Daten, die auch in ``screening_results`` liegen, und genau das ist die
    Zusicherung: Doc 10, Paragraph 8 verlangt, dass ein abgeschlossener
    Bericht sich nicht mehr aendert. Einer, der bei jedem Abruf neu entsteht,
    aenderte sich still mit jeder Codeaenderung.

    Die Spalten daneben sind die, nach denen gefragt wird, ohne das Dokument
    zu oeffnen -- Versionen und, sobald es ein Scoring gibt, Empfehlung und
    Punktzahlen.
    """

    __tablename__ = "stock_reports"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "stock_id", name="uq_stock_report_run_stock"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_runs.id"), index=True
    )
    stock_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stocks.id"), index=True)
    """Eigener Index, obwohl die Spalte im Eindeutigkeits-Constraint steht:
    Dort ist sie die zweite und damit nicht fuehrend -- die Historie einer
    Aktie filtert aber genau auf sie."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    report_schema_version: Mapped[str]
    app_version: Mapped[str]
    scoring_version: Mapped[str | None] = mapped_column(nullable=True)
    """Die Versionen beider Scores in einem Feld (Doc 10, Paragraph 8) --
    etwa ``swing-1.0+long_term-1.0``. Leer, wenn kein Score entstanden ist."""

    recommendation: Mapped[Recommendation | None] = mapped_column(
        _enum_column(Recommendation), nullable=True
    )
    swing_score: Mapped[float | None] = mapped_column(
        Numeric(4, 1, asdecimal=False), nullable=True
    )
    """Nur der Gesamtwert -- die Spalte beantwortet die Frage, fuer die man
    das Dokument nicht oeffnen muss. Teilwerte, Gewichte, Abdeckung und
    Begruendung stehen vollstaendig in ``document`` und in
    ``screening_results.swing_detail``. Leer, wenn der Score
    ``INSUFFICIENT_DATA`` ist."""
    investment_score: Mapped[float | None] = mapped_column(
        Numeric(4, 1, asdecimal=False), nullable=True
    )
    summary: Mapped[str | None] = mapped_column(nullable=True)
    """Die zusammenfassende Formulierung -- Aufgabe der KI-Haelfte, bis dahin
    leer (ADR 0039, Entscheidung 2)."""

    document: Mapped[dict[str, Any]] = mapped_column(JSONB)

    stock: Mapped[StockOrm] = relationship()


class ProcessingErrorOrm(Base):
    """Modulfehler/Verarbeitungsstatus je isolierter Aktie (Fehlerisolation)."""

    __tablename__ = "analysis_run_errors"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_runs.id"), index=True
    )
    """Indiziert: Die Laufdetailansicht zaehlt bei jedem Aufruf die Fehler
    eines Laufs, und die Tabelle waechst mit jedem Handelstag."""
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
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analysis_runs.id"), nullable=True, index=True
    )
    """Der Lauf, in dem das Ergebnis entstand (ADR 0038). NULL bei Laeufen
    ueber ``cli backtest``, die zu keinem Tageslauf gehoeren."""
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
    earnings_exclusion_applied: Mapped[bool] = mapped_column(default=False)
    """Heute durchgehend False -- historische Berichtstermine gibt es nicht
    (ADR 0017 L9, ADR 0038 Entscheidung 3). Die Spalte steht mit, damit alte
    Zeilen die Wahrheit ueber sich selbst sagen, sobald E3 entschieden ist."""

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
    alert_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    """Ohne diesen Vermerk meldete sich der Dispatcher nach Fristablauf alle
    15 Minuten erneut."""
