"""Die Antworten der lesenden Endpunkte -- einmal gebaut, zweimal genutzt.

Die Router in ``v1/`` uebersetzen HTTP: Sie nehmen Pfad und Abfrage
entgegen und machen aus einem fehlenden Datensatz einen 404. Was
*dazwischen* liegt -- aus welchen Repositories sich eine Antwort
zusammensetzt, mit welchen Schwellen sie eingestuft und in welcher
Reihenfolge sie sortiert wird -- steht hier.

**Warum getrennt:** Seit ADR 0060 (das Dashboard laeuft ausserhalb des
Servers) schreibt der Exportschritt dieselben Antworten als Dateien in einen
Datenbaum. Stuende der Zusammenbau in den Routern, muesste der Export ihn
nachbauen -- und haette damit eine zweite Wahrheit ueber dieselben Zahlen.
Genau das verbietet der Spike-Bericht (Abschnitt 8.2: "keine zweite
Rechnung, kein zweiter Zuschnitt").

Kein FastAPI in diesem Modul: Ein fehlender Datensatz ist hier ein
``NotFoundError``, kein ``HTTPException``. Der Router macht daraus einen
404, der Export laesst die Datei weg.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from ai_trading_analyst.domain.analysis import RunStatus, Stock, UnitOfWork
from ai_trading_analyst.domain.backtesting import (
    BacktestEpisode,
    BacktestParameters,
    pool_trades,
    thresholds_of,
)

from .schemas import (
    AnalysisRunResponse,
    BacktestEpisodeResponse,
    EpisodeEvaluationResponse,
    OptionsCombinationResponse,
    OptionsMeasurementDetailResponse,
    OptionsMeasurementResponse,
    OptionsStockRowResponse,
    OptionsTradeResponse,
    Page,
    ReportSummaryResponse,
    SignalBacktestResponse,
    StockBacktestResponse,
)


class NotFoundError(Exception):
    """Das Angefragte gibt es nicht.

    Traegt den Wortlaut mit, den der Router als ``detail`` ausgibt -- sonst
    muesste jede Aufrufstelle ihn erneut formulieren, und zwei Endpunkte
    wuerden fuer dieselbe Lage verschiedene Saetze melden.
    """


def normalisiertes_symbol(symbol: str) -> str:
    """``strip().upper()`` -- wie an jeder anderen Eingabegrenze."""
    return symbol.strip().upper()


def analysis_run_page(
    uow: UnitOfWork,
    *,
    limit: int,
    offset: int,
    status: list[RunStatus] | None = None,
) -> Page[AnalysisRunResponse]:
    """Laeufe, neueste zuerst, seitenweise."""
    runs = uow.analysis_runs.list_recent(limit=limit, offset=offset, status=status)
    total = uow.analysis_runs.count(status=status)
    return Page(
        items=[AnalysisRunResponse.from_domain(run) for run in runs],
        total=total,
        limit=limit,
        offset=offset,
    )


def reports_of_run(uow: UnitOfWork, run_id: UUID) -> list[ReportSummaryResponse]:
    """Die Berichte eines Laufs als Kurzliste.

    Ein unbekannter Lauf ist ein ``NotFoundError`` und keine leere Liste --
    sonst saehe ein Tippfehler in der Kennung aus wie ein Tag ohne
    Kandidaten.
    """
    if uow.analysis_runs.get(run_id) is None:
        raise NotFoundError("AnalysisRun nicht gefunden.")
    berichte = uow.stock_reports.list_for_run(run_id)
    return [ReportSummaryResponse.from_domain(bericht) for bericht in berichte]


def aktie(uow: UnitOfWork, symbol: str) -> Stock:
    """Die Aktie zu einem Symbol -- normalisiert nachgeschlagen.

    Oeffentlich, weil der Chart-Endpunkt sie ebenfalls braucht: Er holt seine
    Kerzen danach beim Marktdatenanbieter und passt deshalb in keine der
    Antwortfunktionen. Ein zweites Nachschlagen dort haette denselben
    404-Wortlaut ein zweites Mal aufgeschrieben.
    """
    gefunden = uow.stocks.get_by_symbol(normalisiertes_symbol(symbol))
    if gefunden is None:
        raise NotFoundError("Aktie nicht gefunden.")
    return gefunden


def reports_of_stock(
    uow: UnitOfWork, symbol: str, *, limit: int, offset: int
) -> Page[ReportSummaryResponse]:
    """Die Berichte einer Aktie ueber alle Laeufe, neueste zuerst.

    Eine unbekannte Aktie ist ein ``NotFoundError``; eine bekannte ohne
    Bericht liefert eine leere Seite -- sie war nie Kandidat, und das ist
    eine Auskunft.
    """
    gesucht = normalisiertes_symbol(symbol)
    aktie(uow, gesucht)
    reports = uow.stock_reports.list_for_symbol(gesucht, limit=limit, offset=offset)
    return Page(
        items=[ReportSummaryResponse.from_domain(report) for report in reports],
        total=uow.stock_reports.count_for_symbol(gesucht),
        limit=limit,
        offset=offset,
    )


def _episoden_je_auswertung(
    episoden: Sequence[BacktestEpisode],
) -> list[EpisodeEvaluationResponse]:
    """Gruppiert nach Auswertungszeitpunkt, in der Reihenfolge des
    Repositories (juengste zuerst, Einstiege aufsteigend)."""
    gruppen: dict[datetime, list[BacktestEpisode]] = {}
    for episode in episoden:
        gruppen.setdefault(episode.evaluated_at, []).append(episode)
    return [
        EpisodeEvaluationResponse(
            evaluated_at=evaluated_at,
            signal_rule_version=eintraege[0].signal_rule_version,
            episodes=[BacktestEpisodeResponse.from_domain(e) for e in eintraege],
        )
        for evaluated_at, eintraege in gruppen.items()
    ]


def stock_backtest(
    uow: UnitOfWork,
    symbol: str,
    *,
    measurement_id: UUID | None,
    backtest_params: BacktestParameters,
) -> StockBacktestResponse:
    """Beide Backtests einer Aktie -- und ausdruecklich **getrennt**.

    Ohne ``measurement_id`` gilt die juengste Messung. Lief noch keine,
    bleibt die Optionsseite leer -- der Signal-Backtest steht trotzdem, denn
    er entsteht im Tageslauf und haengt am Messlauf nicht.
    """
    gesucht = normalisiertes_symbol(symbol)
    gefundene_aktie = aktie(uow, gesucht)
    signal_backtests = [
        SignalBacktestResponse.from_domain(ergebnis)
        for ergebnis in uow.backtest_results.list_for_stock(gefundene_aktie.id)
    ]
    episode_evaluations = _episoden_je_auswertung(
        uow.backtest_results.list_episodes_for_stock(gefundene_aktie.id)
    )
    messung_id = (
        measurement_id
        if measurement_id is not None
        else uow.options_backtest_results.latest_measurement_id()
    )
    if messung_id is None:
        return StockBacktestResponse(
            symbol=gesucht,
            signal_backtests=signal_backtests,
            episode_evaluations=episode_evaluations,
            measurement=None,
            combinations=[],
            pooled=None,
            trades=[],
        )
    kombinationen = uow.options_backtest_results.list_for_stock(messung_id, gefundene_aktie.id)
    trades = uow.options_backtest_results.list_trades_for_stock(messung_id, gefundene_aktie.id)
    kopf = uow.options_backtest_results.get_measurement(messung_id)
    if kopf is None:
        raise NotFoundError("Messung nicht gefunden.")
    # Mit den Schwellen dieser Messung, nicht denen von heute.
    schwellen = thresholds_of(kopf[1], backtest_params)
    gepoolt = pool_trades([trade for _, trade in trades], schwellen)
    return StockBacktestResponse(
        symbol=gesucht,
        signal_backtests=signal_backtests,
        episode_evaluations=episode_evaluations,
        measurement=OptionsMeasurementResponse.from_domain(kopf[0], kopf[1]),
        combinations=[
            OptionsCombinationResponse.from_domain(ergebnis)
            for ergebnis in kombinationen
            if ergebnis.episodes
        ],
        # Auch ohne einen einzigen Trade: Die Zeile sagt dann
        # ``INSUFFICIENT_DATA`` statt zu fehlen, und das ist eine Auskunft.
        pooled=OptionsStockRowResponse.from_domain(gefundene_aktie.id, gesucht, gepoolt),
        trades=[
            OptionsTradeResponse.from_domain(kombination, trade)
            for kombination, trade in trades
        ],
    )


def measurements(uow: UnitOfWork) -> list[OptionsMeasurementResponse]:
    """Alle Messungen, juengste zuerst.

    Eine leere Liste heisst: Es lief noch kein Messlauf. Das ist eine
    Auskunft und kein Fehler.
    """
    return [
        OptionsMeasurementResponse.from_domain(bereich, annahmen)
        for bereich, annahmen in uow.options_backtest_results.list_measurements()
    ]


def measurement_detail(
    uow: UnitOfWork, measurement_id: UUID, *, backtest_params: BacktestParameters
) -> OptionsMeasurementDetailResponse:
    """Eine Messung: die Kombinationen ueber alle Aktien und die Aktienzeilen.

    Die Aktienzeilen entstehen **aus den Einzeltrades** und nicht als Mittel
    der Kombinationszeilen -- ein Mittel von Mitteln gewichtete eine Aktie mit
    drei Trades so schwer wie eine mit dreissig.
    """
    zeilen = uow.options_backtest_results.list_for_measurement(measurement_id)
    if not zeilen:
        raise NotFoundError("Messung nicht gefunden.")
    gesamt = [(bereich, ergebnis) for bereich, ergebnis in zeilen if bereich.stock_id is None]
    if not gesamt:
        # Kann der Messlauf nicht erzeugen; eine Messung ohne Gesamtzeile
        # waere ein halb geschriebener Lauf, und den zu deuten hiesse raten.
        raise NotFoundError("Messung ohne Gesamtzeile -- unvollstaendig gespeichert.")
    kopf, kopfergebnis = gesamt[0]
    # Mit den Schwellen **dieser** Messung, nicht denen von heute: Sonst
    # stuenden Kombinationszeilen, die beim Schreiben als belastbar galten,
    # neben Aktienzeilen, die beim Lesen durchfallen -- fuer dieselben Trades.
    schwellen = thresholds_of(kopfergebnis.assumptions, backtest_params)
    trades_je_aktie = uow.options_backtest_results.list_trades_for_measurement(measurement_id)
    # **Alle Aktien der Messung, nicht nur die mit Trades.** Eine Aktie, deren
    # Episoden zu keinem vollstaendigen Trade fuehrten -- kein Verfall im
    # Fenster, zu wenig Historie --, hat Ergebniszeilen, aber keine
    # Tradezeilen. Sie einfach wegzulassen hiesse, dass der Kopf vierzig
    # Aktien nennt und die Liste siebenunddreissig zeigt, ohne dass jemand
    # erfaehrt, welche fehlen.
    bekannte = {bereich.stock_id for bereich, _ in zeilen if bereich.stock_id is not None}
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
        measurement=OptionsMeasurementResponse.from_domain(kopf, kopfergebnis.assumptions),
        overall=[
            OptionsCombinationResponse.from_domain(ergebnis)
            for _, ergebnis in gesamt
            if ergebnis.episodes
        ],
        # Nach Rendite der gemanagten Variante, und Aktien ohne belastbare
        # Stichprobe ans Ende: Eine Rangliste, die eine Aktie mit vier Trades
        # anfuehren laesst, ist eine Einladung zum Fehlschluss.
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
