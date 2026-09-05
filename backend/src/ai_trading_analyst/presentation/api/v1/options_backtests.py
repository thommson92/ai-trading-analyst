"""``/api/v1/options-backtests`` -- die Messungen des Optionsbacktests.

Nur lesend. Ein Messlauf entsteht ueber ``cli options-backtest`` und nicht auf
Zuruf durch das Web: Er rechnet ueber die ganze Watchliste und ueber fuenf
Jahre, und ein Webdienst, der das auf Knopfdruck anstoesst, waere derselbe
Fehler wie ein Webdienst, der die TWS-Client-ID belegt (ADR 0052).

**Jede Zahl hier ist eine Modellzahl.** Die Praemie ist gerechnet, der
Verfallskalender konstruiert, das Strike-Raster angenommen. Die Annahmen
stehen deshalb an jeder Messung und nicht im Kleingedruckten.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ai_trading_analyst.domain.analysis import UnitOfWork
from ai_trading_analyst.domain.backtesting import (
    BacktestParameters,
    pool_trades,
    thresholds_of,
)

from ..dependencies import get_backtest_parameters, get_unit_of_work_factory
from ..schemas import (
    OptionsCombinationResponse,
    OptionsMeasurementDetailResponse,
    OptionsMeasurementResponse,
    OptionsStockRowResponse,
)

router = APIRouter(prefix="/api/v1/options-backtests", tags=["options-backtests"])


@router.get("", response_model=list[OptionsMeasurementResponse])
def list_measurements(
    uow_factory: Callable[[], UnitOfWork] = Depends(get_unit_of_work_factory),
) -> list[OptionsMeasurementResponse]:
    """Alle Messungen, juengste zuerst.

    Eine leere Liste heisst: Es lief noch kein Messlauf. Das ist eine
    Auskunft und kein Fehler -- der Optionsbacktest ist ein Handlauf und
    haengt nicht am Tageslauf.
    """
    with uow_factory() as uow:
        return [
            OptionsMeasurementResponse.from_domain(bereich, annahmen)
            for bereich, annahmen in uow.options_backtest_results.list_measurements()
        ]


@router.get("/{measurement_id}", response_model=OptionsMeasurementDetailResponse)
def get_measurement(
    measurement_id: UUID,
    uow_factory: Callable[[], UnitOfWork] = Depends(get_unit_of_work_factory),
    backtest_params: BacktestParameters = Depends(get_backtest_parameters),
) -> OptionsMeasurementDetailResponse:
    """Eine Messung: die Kombinationen ueber alle Aktien und die Aktienzeilen.

    Die Aktienzeilen entstehen **aus den Einzeltrades** und nicht als Mittel
    der Kombinationszeilen -- ein Mittel von Mitteln gewichtete eine Aktie mit
    drei Trades so schwer wie eine mit dreissig.
    """
    with uow_factory() as uow:
        zeilen = uow.options_backtest_results.list_for_measurement(measurement_id)
        if not zeilen:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Messung nicht gefunden."
            )
        gesamt = [
            (bereich, ergebnis) for bereich, ergebnis in zeilen if bereich.stock_id is None
        ]
        if not gesamt:
            # Kann der Messlauf nicht erzeugen; eine Messung ohne Gesamtzeile
            # waere ein halb geschriebener Lauf, und den zu deuten hiesse raten.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Messung ohne Gesamtzeile -- unvollstaendig gespeichert.",
            )
        kopf, kopfergebnis = gesamt[0]
        # Mit den Schwellen **dieser** Messung, nicht denen von heute: Sonst
        # stuenden Kombinationszeilen, die beim Schreiben als belastbar
        # galten, neben Aktienzeilen, die beim Lesen durchfallen -- fuer
        # dieselben Trades.
        schwellen = thresholds_of(kopfergebnis.assumptions, backtest_params)
        trades_je_aktie = uow.options_backtest_results.list_trades_for_measurement(
            measurement_id
        )
        # **Alle Aktien der Messung, nicht nur die mit Trades.** Eine Aktie,
        # deren Episoden zu keinem vollstaendigen Trade fuehrten -- kein
        # Verfall im Fenster, zu wenig Historie --, hat Ergebniszeilen, aber
        # keine Tradezeilen. Sie einfach wegzulassen hiesse, dass der Kopf
        # vierzig Aktien nennt und die Liste siebenunddreissig zeigt, ohne
        # dass jemand erfaehrt, welche fehlen.
        bekannte = {
            bereich.stock_id
            for bereich, _ in zeilen
            if bereich.stock_id is not None
        }
        symbole = {stock.id: stock.symbol for stock in uow.stocks.list_all()}
        aktien = [
            OptionsStockRowResponse.from_domain(
                stock_id,
                symbole.get(stock_id, "?"),
                pool_trades(list(trades_je_aktie.get(stock_id, ())), schwellen),
            )
            for stock_id in bekannte
        ]
        return OptionsMeasurementDetailResponse(
            measurement=OptionsMeasurementResponse.from_domain(
                kopf, kopfergebnis.assumptions
            ),
            overall=[
                OptionsCombinationResponse.from_domain(ergebnis)
                for _, ergebnis in gesamt
                if ergebnis.episodes
            ],
            # Nach Rendite der gemanagten Variante, und Aktien ohne belastbare
            # Stichprobe ans Ende: Eine Rangliste, die eine Aktie mit vier
            # Trades anfuehren laesst, ist eine Einladung zum Fehlschluss.
            stocks=sorted(aktien, key=_rangfolge),
        )


def _rangfolge(zeile: OptionsStockRowResponse) -> tuple[int, float, str]:
    """Rendite absteigend, ohne belastbare Stichprobe ans Ende.

    Das Symbol als letztes Merkmal: Ohne es haengt die Reihenfolge zweier
    gleich guter Aktien -- und die des ganzen Endes -- an der Reihenfolge, in
    der die Datenbank ihre Zeilen liefert. Zwei Aufrufe ergaeben dann
    verschiedene Listen fuer dieselbe Messung.
    """
    if zeile.managed is None or zeile.managed.mean_return_on_capital is None:
        return (1, 0.0, zeile.symbol)
    return (0, -zeile.managed.mean_return_on_capital, zeile.symbol)

