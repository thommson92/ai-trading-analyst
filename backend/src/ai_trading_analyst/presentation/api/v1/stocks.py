"""``/api/v1/stocks`` -- die Analysehistorie einer Aktie (US-010)."""

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
    Stock,
    UnitOfWork,
)
from ai_trading_analyst.domain.backtesting import (
    BacktestParameters,
    pool_trades,
    thresholds_of,
)
from ai_trading_analyst.domain.screening import CandidateRuleParameters
from ai_trading_analyst.presentation.validation_chart import build_chart_payload

from ..dependencies import (
    get_backtest_parameters,
    get_candidate_rule_parameters,
    get_chart_market_data,
    get_unit_of_work_factory,
)
from ..schemas import (
    OptionsCombinationResponse,
    OptionsMeasurementResponse,
    OptionsStockRowResponse,
    OptionsTradeResponse,
    Page,
    ReportSummaryResponse,
    SignalBacktestResponse,
    StockBacktestResponse,
)

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/stocks", tags=["stocks"])


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
    gesucht = symbol.strip().upper()
    with uow_factory() as uow:
        if uow.stocks.get_by_symbol(gesucht) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Aktie nicht gefunden."
            )
        reports = uow.stock_reports.list_for_symbol(gesucht, limit=limit, offset=offset)
        total = uow.stock_reports.count_for_symbol(gesucht)
    return Page(
        items=[ReportSummaryResponse.from_domain(report) for report in reports],
        total=total,
        limit=limit,
        offset=offset,
    )


def _aktie_oder_404(uow: UnitOfWork, symbol: str) -> Stock:
    aktie = uow.stocks.get_by_symbol(symbol)
    if aktie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Aktie nicht gefunden."
        )
    return aktie


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
    gesucht = symbol.strip().upper()
    with uow_factory() as uow:
        aktie = _aktie_oder_404(uow, gesucht)
        signal_backtests = [
            SignalBacktestResponse.from_domain(ergebnis)
            for ergebnis in uow.backtest_results.list_for_stock(aktie.id)
        ]
        messung_id = (
            measurement_id
            if measurement_id is not None
            else uow.options_backtest_results.latest_measurement_id()
        )
        if messung_id is None:
            return StockBacktestResponse(
                symbol=gesucht,
                signal_backtests=signal_backtests,
                measurement=None,
                combinations=[],
                pooled=None,
                trades=[],
            )
        kombinationen = uow.options_backtest_results.list_for_stock(messung_id, aktie.id)
        trades = uow.options_backtest_results.list_trades_for_stock(messung_id, aktie.id)
        kopf = uow.options_backtest_results.get_measurement(messung_id)
        if kopf is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Messung nicht gefunden."
            )
        # Mit den Schwellen dieser Messung, nicht denen von heute.
        schwellen = thresholds_of(kopf[1], backtest_params)
        gepoolt = pool_trades([trade for _, trade in trades], schwellen)
        return StockBacktestResponse(
            symbol=gesucht,
            signal_backtests=signal_backtests,
            measurement=OptionsMeasurementResponse.from_domain(kopf[0], kopf[1]),
            combinations=[
                OptionsCombinationResponse.from_domain(ergebnis)
                for ergebnis in kombinationen
                if ergebnis.episodes
            ],
            # Auch ohne einen einzigen Trade: Die Zeile sagt dann
            # ``INSUFFICIENT_DATA`` statt zu fehlen, und das ist eine Auskunft.
            pooled=OptionsStockRowResponse.from_domain(aktie.id, gesucht, gepoolt),
            trades=[
                OptionsTradeResponse.from_domain(kombination, trade)
                for kombination, trade in trades
            ],
        )


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
    gesucht = symbol.strip().upper()
    with uow_factory() as uow:
        aktie = _aktie_oder_404(uow, gesucht)
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
