"""Abstrakte Schnittstellen (Ports) fuer Marktdaten und Persistenz.

Konkrete Implementierungen (Fixture-Provider, SQLAlchemy-Repositories) leben
in der Infrastructure-Schicht und referenzieren diese Protocols -- nie
umgekehrt. Der Domain Layer kennt keinen konkreten Datenanbieter (Doc 10,
Paragraph 9).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from types import TracebackType
from typing import Protocol
from uuid import UUID

from ai_trading_analyst.domain.analysts import AnalystRecommendations
from ai_trading_analyst.domain.backtesting import BacktestResult
from ai_trading_analyst.domain.earnings import NextEarningsDate
from ai_trading_analyst.domain.fundamentals import FundamentalSnapshot

# Bewusst aus dem Wertemodul und nicht aus dem Paket: ``domain.report``
# zieht ueber ``build_report`` seinerseits ``domain.analysis`` herein. Der
# Zuschnitt ist richtig -- der Bericht liest ein Screening-Ergebnis, und die
# Unit of Work speichert ihn --, aber als Paketimport waere es ein Kreis.
# ``report.values`` haengt an keinem anderen Domain-Paket ausser den
# Teilergebnissen.
from ai_trading_analyst.domain.report.values import StockReport, StoredReport
from ai_trading_analyst.domain.research import ResearchReport
from ai_trading_analyst.domain.screening import CandleSeries, IntradayBar
from ai_trading_analyst.domain.technical import TechnicalAssessment, TechnicalSnapshot

from .models import (
    AnalysisRun,
    ContractSpec,
    Stock,
    StockProcessingError,
    StockScreeningOutcome,
)


class MarketDataProviderError(Exception):
    """Ein Marktdatenanbieter konnte fuer eine Aktie keine Daten liefern.

    Wird vom Application-Layer pro Aktie isoliert (Fehlerisolation) -- ein
    Fehler bei einer Aktie darf den Lauf nicht insgesamt scheitern lassen.
    """


class HistoricalBarSource(Protocol):
    """Liefert native Intraday-Bars einer Aktie, aeltester Bar zuerst.

    Bewusst getrennt von ``MarketDataProvider``: Der Provider liefert fertige
    Kerzen samt Indikatoren, diese Quelle nur Rohbars. Der Backfill braucht
    genau die Rohbars, und der Screener liest sie spaeter aus dem eigenen
    Bestand -- dieselbe Schnittstelle, einmal gegen die TWS, einmal gegen die
    Datenbank.
    """

    def fetch_intraday_bars(
        self, contract: ContractSpec, days: int | None = None
    ) -> Sequence[IntradayBar]:
        """Holt Bars der letzten ``days`` Tage.

        ``None`` bedeutet den konfigurierten Standardzeitraum -- den Fall des
        allerersten Abrufs, wenn noch nichts gespeichert ist. Danach fragt der
        Backfill nur noch die Luecke seit dem letzten bekannten Bar an.

        Raises:
            MarketDataProviderError: wenn die Bars nicht beschafft werden
                konnten.
        """
        ...

    def close(self) -> None:
        """Gibt eine gehaltene Verbindung frei. Muss mehrfach aufrufbar sein."""
        ...


class HistoricalBarWindowSource(Protocol):
    """Liefert Bars eines **frei waehlbaren** Fensters der Vergangenheit.

    Bewusst getrennt von ``HistoricalBarSource``: Die holt immer das Fenster,
    das jetzt endet -- genau das, was der taegliche Backfill braucht. Wer
    wissen will, wie weit die Historie einer Aktie ueberhaupt zurueckreicht,
    muss dagegen an einem beliebigen Punkt der Vergangenheit ansetzen und sich
    Fenster fuer Fenster zurueckarbeiten.

    Ein eigener Port statt eines weiteren Parameters am bestehenden: Der
    Bestand als Quelle (``StoredBarSource``) kann das nicht sinnvoll
    beantworten -- er weiss nur, was schon geholt wurde, nicht, was es beim
    Anbieter gaebe. Diese Frage stellt sich ausschliesslich an den Anbieter.
    """

    def fetch_window(
        self, contract: ContractSpec, end: datetime | None, days: int
    ) -> Sequence[IntradayBar]:
        """Holt die Bars der ``days`` Tage **vor** ``end``.

        ``end`` ist der ausschliessende obere Rand des Fensters; ``None``
        steht fuer den aktuellen Zeitpunkt. Zurueck kommt, was der Anbieter
        tatsaechlich hergibt -- eine leere Folge heisst, dass er fuer dieses
        Fenster nichts (mehr) hat.

        Raises:
            MarketDataProviderError: wenn das Fenster nicht abgerufen werden
                konnte.
        """
        ...

    def close(self) -> None:
        """Gibt eine gehaltene Verbindung frei. Muss mehrfach aufrufbar sein."""
        ...


class MarketDataProvider(Protocol):
    """Liefert die fuer die Kandidatenpruefung benoetigten Aktien und Kerzen."""

    def list_stocks(self) -> Sequence[Stock]: ...

    def get_candle_series(self, stock: Stock) -> CandleSeries:
        """Liefert die vollstaendige Kerzenserie einer Aktie.

        Raises:
            MarketDataProviderError: wenn fuer diese Aktie keine Daten
                beschafft werden konnten.
        """
        ...


class EarningsProviderError(Exception):
    """Ein Earnings-Anbieter konnte fuer eine Aktie keinen Termin liefern.

    Wird vom Application-Layer pro Aktie isoliert -- ein Ausfall der Quelle
    ist ein normaler Betriebszustand (ADR 0017), kein Laufabbruch. Die
    technische Analyse laeuft unabhaengig weiter (Doc 10: Analysemodule sind
    entkoppelt).
    """


class EarningsProvider(Protocol):
    """Liefert den naechsten bekannten Earnings-Termin einer Aktie."""

    def next_earnings_date(self, stock: Stock) -> NextEarningsDate | None:
        """Naechster kuenftiger Earnings-Termin, oder ``None`` bei fehlender
        Abdeckung (ADR 0017 L3) -- niemals stillschweigend als unbedenklich
        zu werten.

        Raises:
            EarningsProviderError: wenn die Quelle nicht erreichbar war.
        """
        ...


class AnalystRecommendationsProviderError(Exception):
    """Ein Anbieter konnte fuer eine Aktie keine Empfehlungen liefern.

    Wird vom Application-Layer pro Aktie isoliert (Muster
    ``EarningsProviderError``) -- ein Ausfall der Quelle ist ein normaler
    Betriebszustand (ADR 0017), kein Laufabbruch.
    """


class AnalystRecommendationsFormatError(AnalystRecommendationsProviderError):
    """Der Anbieter war erreichbar, seine Antwort aber nicht auswertbar.

    Getrennt von der Basisklasse, weil der Unterschied im Bericht steht:
    "nicht erreicht" und "erreicht, aber unlesbar" sind verschiedene
    Aussagen ueber die Datenlage. Der Earnings-Filter macht dieselbe
    Unterscheidung (ADR 0017, Gruende ``provider_error`` und
    ``invalid_data``).
    """


class AnalystRecommendationsProvider(Protocol):
    """Liefert die Votenverteilung der Analysten je Monatsstand."""

    def recommendations(self, stock: Stock) -> AnalystRecommendations:
        """Empfehlungen der letzten Monate, neuester Stand zuerst (ADR 0043).

        Fuehrt der Anbieter das Symbol nicht, ist das ``UNKNOWN`` mit Grund
        ``"no_coverage"`` -- **nicht** eine leere Verteilung und nicht "keine
        Meinung". Kursziele liefert dieser Port nicht und wird es nicht: Sie
        sind dauerhaft zurueckgestellt (ADR 0043).

        Raises:
            AnalystRecommendationsProviderError: wenn die Quelle nicht
                erreichbar war oder eine Antwort lieferte, die nicht
                auswertbar ist.
        """
        ...


class ResearchProviderError(Exception):
    """Ein Research-Anbieter konnte fuer eine Aktie keinen Bericht liefern.

    Wird vom Application-Layer pro Aktie isoliert -- ein Ausfall der Quelle
    ist ein normaler Betriebszustand, kein Laufabbruch (Muster
    ``EarningsProviderError``). Die deterministische Chartanalyse und das
    Backtesting laufen unabhaengig von Research weiter (CLAUDE.md, Doc 10:
    Analysemodule sind entkoppelt).
    """


class ResearchProvider(Protocol):
    """Liefert einen strukturierten Recherche-Bericht zu einer Aktie."""

    def research(self, stock: Stock) -> ResearchReport:
        """Bericht mit Belegen, oder ``status=INSUFFICIENT_DATA`` bei zu
        duenner Grundlage -- niemals ein erfundener Bericht (Doc 10,
        Paragraph 10, Halluzinationsschutz).

        Raises:
            ResearchProviderError: wenn die Quelle nicht erreichbar war.
        """
        ...


class FundamentalDataProviderError(Exception):
    """Die Fundamentaldatenquelle war fuer eine Aktie nicht verwertbar.

    Wird vom Application-Layer pro Aktie isoliert (Muster
    ``EarningsProviderError``) -- ein Ausfall von EDGAR ist ein normaler
    Betriebszustand, kein Laufabbruch. Screening, technische Analyse und
    Backtesting laufen unabhaengig davon weiter (CLAUDE.md: Analysemodule
    sind entkoppelt).
    """


class FundamentalDataProvider(Protocol):
    """Liefert die deterministisch gerechneten Fundamentalkennzahlen."""

    def fundamentals(self, stock: Stock, price: float | None = None) -> FundamentalSnapshot:
        """Kennzahlen aus den Einreichungen der Aktie (ADR 0032).

        ``price`` ist eine **optionale, nicht blockierende** Eingabe: Fehlt
        er, entstehen die bewertungsabhaengigen Kennzahlen nicht, alle
        uebrigen vollstaendig. Die Umsetzung beschafft selbst keinen Kurs und
        leitet keinen ab (CLAUDE.md, zweite gerichtete Kopplung).

        Raises:
            FundamentalDataProviderError: wenn die Quelle nicht erreichbar war
                oder eine Antwort lieferte, die nicht auswertbar ist.
        """
        ...


class TechnicalInterpreterError(Exception):
    """Der Technical Agent konnte fuer eine Aktie keine Einordnung liefern.

    Wird vom Application-Layer pro Aktie isoliert (Muster
    ``ResearchProviderError``) -- ein Ausfall des Sprachmodells ist ein
    normaler Betriebszustand, kein Laufabbruch. Die deterministische
    Chartauswertung ist zu diesem Zeitpunkt bereits fertig gerechnet und
    bleibt vollstaendig erhalten (CLAUDE.md: Analysemodule sind entkoppelt).
    """


class TechnicalInterpreter(Protocol):
    """Ordnet eine fertig gerechnete Chartauswertung qualitativ ein."""

    def interpret(self, stock: Stock, snapshot: TechnicalSnapshot) -> TechnicalAssessment:
        """Einordnung der sechs Punkte aus Doc 10, Paragraph 6.8.

        Die Umsetzung veraendert **keinen** Wert des Snapshots und leitet
        keinen neuen ab (CLAUDE.md, zentrale Regel). Ist der Snapshot nicht
        ``COMPLETED``, liefert sie ``INSUFFICIENT_DATA`` **ohne** Aufruf des
        Anbieters -- es gaebe nichts einzuordnen, und der Aufruf kostete nur.

        Raises:
            TechnicalInterpreterError: wenn der Anbieter nicht erreichbar war
                oder eine Antwort lieferte, die nicht zum Schema passt.
        """
        ...


class BacktestResultRepository(Protocol):
    def add(self, result: BacktestResult, analysis_run_id: UUID | None = None) -> None:
        """``analysis_run_id`` bindet das Ergebnis an den Tageslauf, in dem es
        entstand (ADR 0038). Ohne Angabe -- so bei ``cli backtest`` -- bleibt
        die Bindung leer; das Ergebnis gehoert dann zu keinem Lauf."""
        ...

    def list_for_stock(self, stock_id: UUID) -> Sequence[BacktestResult]: ...


class IntradayBarRepository(Protocol):
    """Speicher fuer die nativen Bars des Anbieters.

    Er beantwortet die eine Frage, von der der Backfill lebt: **Bis wann
    liegen fuer diese Aktie schon Daten vor?** Daraus ergibt sich, was noch
    zu holen ist -- ein Tag nach einem gewoehnlichen Lauf, drei Wochen nach
    einem laengeren Ausfall, ein ganzes Jahr beim ersten Mal. Ein fester
    Zeitraum je Lauf wuerde entweder zu viel holen oder zu wenig.
    """

    def latest_start(self, symbol: str) -> datetime | None:
        """Beginn des juengsten gespeicherten Bars, oder ``None``."""
        ...

    def latest_start_overall(self) -> datetime | None:
        """Beginn des juengsten Bars ueber **alle** Aktien.

        Die Frage des Dispatchers: Sind die Daten des Handelstages ueberhaupt
        angekommen? Ueber alle Aktien und nicht ueber eine bestimmte, damit
        ein einzelner ausgesetzter Titel den Lauf nicht verhindert. Ob eine
        *einzelne* Aktie vollstaendig ist, entscheidet ohnehin erst die
        Kerzenbildung, und zwar je Aktie.
        """
        ...

    def earliest_start(self, symbol: str) -> datetime | None:
        """Beginn des **aeltesten** gespeicherten Bars, oder ``None``.

        Der Gegenpart zu ``latest_start`` und die Frage, von der der
        Tiefen-Backfill lebt: Er fuellt nicht vorwaerts bis heute, sondern
        rueckwaerts in die Vergangenheit. Sein Ansatzpunkt ist deshalb der
        aelteste bekannte Bar -- und weil der mit jedem geschriebenen Fenster
        weiter zurueckwandert, setzt ein abgebrochener Lauf ohne Zutun genau
        dort wieder an.
        """
        ...

    def add_all(self, symbol: str, bars: Sequence[IntradayBar]) -> int:
        """Speichert Bars und liefert die Zahl der **neu** hinzugekommenen.

        Wiederholt gelieferte Bars werden uebergangen, nicht als Fehler
        behandelt: Die Zeitraeume zweier Laeufe ueberlappen sich zwangslaeufig,
        und ein abgebrochener Lauf muss ohne Aufraeumen wiederholbar sein.
        """
        ...

    def list_for(self, symbol: str) -> Sequence[IntradayBar]:
        """Alle gespeicherten Bars einer Aktie, nach Zeit aufsteigend."""
        ...


class StockRepository(Protocol):
    def add(self, stock: Stock) -> None: ...
    def get_by_symbol(self, symbol: str) -> Stock | None: ...
    def list_all(self) -> Sequence[Stock]: ...


class AnalysisRunRepository(Protocol):
    def add(self, run: AnalysisRun) -> None: ...
    def get(self, run_id: UUID) -> AnalysisRun | None: ...
    def list_all(self) -> Sequence[AnalysisRun]: ...
    def update(self, run: AnalysisRun) -> None: ...


class ScreeningResultRepository(Protocol):
    def add(self, outcome: StockScreeningOutcome) -> None: ...
    def list_for_run(self, run_id: UUID) -> Sequence[StockScreeningOutcome]: ...


class ProcessingErrorRepository(Protocol):
    def add(self, error: StockProcessingError) -> None: ...
    def list_for_run(self, run_id: UUID) -> Sequence[StockProcessingError]: ...


class StockReportRepository(Protocol):
    """Speicher fuer die Analyseberichte (Doc 10, Paragraph 6.12; ADR 0039).

    Kein Update-Pfad: Ein abgeschlossener Bericht wird nicht ueberschrieben
    (Doc 10, Paragraph 8).
    """

    def add(self, report: StockReport) -> None: ...

    def list_for_run(self, analysis_run_id: UUID) -> Sequence[StoredReport]:
        """Die Berichte eines Laufs, **so wie sie geschrieben wurden**.

        Kein ``StockReport``: Das gespeicherte Dokument ist die verbindliche
        Fassung, und es beim Lesen erneut zu erzeugen hiesse, einen
        abgeschlossenen Bericht durch heutigen Code zu schicken.
        """
        ...


class UnitOfWork(Protocol):
    """Transaktionsgrenze ueber alle Repositories eines Analyse-Laufs.

    Jeder Verwendungsblock committet oder rollt vollstaendig zurueck -- kein
    teilweise geschriebener Zustand innerhalb einer einzelnen Transaktion.
    """

    stocks: StockRepository
    intraday_bars: IntradayBarRepository
    analysis_runs: AnalysisRunRepository
    screening_results: ScreeningResultRepository
    processing_errors: ProcessingErrorRepository
    backtest_results: BacktestResultRepository
    stock_reports: StockReportRepository

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
