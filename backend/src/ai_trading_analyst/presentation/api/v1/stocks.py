"""``/api/v1/stocks`` -- die Analysehistorie einer Aktie (US-010).

Der Zusammenbau steht in ``..views`` -- derselbe Code, aus dem der
Exportschritt seinen Datenbaum schreibt (ADR 0060).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ai_trading_analyst.domain.analysis import (
    MarketDataProvider,
    MarketDataProviderError,
    MarketDataUnavailableError,
    UnitOfWork,
)
from ai_trading_analyst.domain.backtesting import BacktestParameters
from ai_trading_analyst.domain.screening import CandidateRuleParameters
from ai_trading_analyst.presentation.validation_chart import build_chart_payload

from .. import views
from ..dependencies import (
    get_backtest_parameters,
    get_candidate_rule_parameters,
    get_chart_market_data,
    get_unit_of_work_factory,
)
from ..schemas import Page, ReportSummaryResponse, StockBacktestResponse, StockIndexResponse

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/stocks", tags=["stocks"])


def _als_404(fehler: views.NotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(fehler))


@router.get("", response_model=list[StockIndexResponse])
def list_stocks(
    uow_factory: Callable[[], UnitOfWork] = Depends(get_unit_of_work_factory),
) -> list[StockIndexResponse]:
    """Alle Aktien mit ihrem letzten Stand (ADR 0062) -- alphabetisch, ohne
    Seitengrenze: Die Watchlist hat zweihundert Titel, nicht zwanzigtausend."""
    with uow_factory() as uow:
        return views.stock_index(uow)


@router.get("/{symbol}/reports", response_model=Page[ReportSummaryResponse])
def list_reports_of_stock(
    symbol: str,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    uow_factory: Callable[[], UnitOfWork] = Depends(get_unit_of_work_factory),
) -> Page[ReportSummaryResponse]:
    """Die Berichte einer Aktie ueber alle Laeufe, neueste zuerst.

    Das Symbol wird wie an jeder anderen Eingabegrenze normalisiert
    (``strip().upper()``, wie in der Kommandozeile).

    Eine unbekannte Aktie ist ein 404; eine bekannte ohne Bericht liefert eine
    leere Seite -- sie war nie Kandidat, und das ist eine Auskunft.
    """
    with uow_factory() as uow:
        try:
            return views.reports_of_stock(uow, symbol, limit=limit, offset=offset)
        except views.NotFoundError as fehler:
            raise _als_404(fehler) from fehler


@router.get("/{symbol}/backtest", response_model=StockBacktestResponse)
def get_stock_backtest(
    symbol: str,
    measurement_id: UUID | None = Query(default=None),
    uow_factory: Callable[[], UnitOfWork] = Depends(get_unit_of_work_factory),
    backtest_params: BacktestParameters = Depends(get_backtest_parameters),
) -> StockBacktestResponse:
    """Beide Backtests einer Aktie -- und ausdruecklich **getrennt**.

    Der Signal-Backtest sagt, ob das Signal traegt; der Optionsbacktest, ob
    sich damit Geld verdienen liesse. Sie zu einer Zahl zu verrechnen waere
    derselbe Fehler wie eine gemeinsame Erfolgsquote aus Trefferquote und
    Halten oberhalb des Einstiegs (``CLAUDE.md``).

    Ohne ``measurement_id`` gilt die juengste Messung. Lief noch keine, bleibt
    die Optionsseite leer -- der Signal-Backtest steht trotzdem, denn er
    entsteht im Tageslauf und haengt am Messlauf nicht.
    """
    with uow_factory() as uow:
        try:
            return views.stock_backtest(
                uow,
                symbol,
                measurement_id=measurement_id,
                backtest_params=backtest_params,
            )
        except views.NotFoundError as fehler:
            raise _als_404(fehler) from fehler


@router.get("/{symbol}/chart")
def get_stock_chart(
    symbol: str,
    uow_factory: Callable[[], UnitOfWork] = Depends(get_unit_of_work_factory),
    market_data: MarketDataProvider = Depends(get_chart_market_data),
    rule: CandidateRuleParameters = Depends(get_candidate_rule_parameters),
) -> dict[str, Any]:
    """Der Validierungschart als reine Daten.

    Derselbe Aufbau wie ``cli chart``, und zwar buchstaeblich dieselbe
    Funktion: ``build_chart_payload`` rechnet ausschliesslich mit
    Domain-Funktionen. Eine zweite Rechnung im Frontend zeigte, was diese
    zweite Rechnung daraus macht -- nicht, was der Screener sieht.

    Die Kerzen kommen **aus dem Bestand**, nie von der TWS. Geliefert wird die
    ganze Reihe: Fuenf Jahre sind rund 2.500 Kerzen, und ein Fenster
    verschoebe die Frage, welches das richtige ist, in die Oberflaeche.
    """
    gesucht = views.normalisiertes_symbol(symbol)
    with uow_factory() as uow:
        try:
            aktie = views.aktie(uow, gesucht)
        except views.NotFoundError as fehler:
            raise _als_404(fehler) from fehler
    try:
        series = market_data.get_candle_series(aktie)
    except MarketDataUnavailableError as fehler:
        # **Zuerst der Ausfall.** Ein Datenbankabriss als 404 zu melden hiesse,
        # ein Betriebsproblem als Befund auszugeben -- unsichtbar fuer jede
        # Ueberwachung. Und der Wortlaut bleibt drinnen: Eine
        # SQLAlchemy-Meldung nennt Anweisung, Tabelle und Spalten.
        _logger.error("Chart fuer %s nicht lesbar: %s", gesucht, fehler)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Der Kursbestand ist gerade nicht lesbar.",
        ) from fehler
    except MarketDataProviderError as fehler:
        # Kein 500: Dass fuer diese Aktie keine Kerzen im Bestand liegen, ist
        # eine Auskunft ueber die Datenlage und kein Fehler des Dienstes.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(fehler)
        ) from fehler
    return build_chart_payload(gesucht, series, rule)
