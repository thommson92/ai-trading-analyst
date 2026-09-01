"""API-Integrationstests: FastAPI-App vollstaendig verdrahtet
(``ai_trading_analyst.bootstrap.build_app``) gegen echtes PostgreSQL.

Die Daten entstehen hier ueber die UnitOfWork und nicht mehr ueber einen
Startknopf: Die API ist lesend (ADR 0053).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from ai_trading_analyst.bootstrap import build_app
from ai_trading_analyst.domain.analysis import (
    AnalysisRun,
    RunStatus,
    Stock,
    StockProcessingError,
    StockScreeningOutcome,
)
from ai_trading_analyst.domain.earnings import EarningsFilterResult, EarningsFilterStatus
from ai_trading_analyst.domain.report import build_report
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
    SIGNAL_RULE_VERSION,
    ScreeningResult,
    ScreeningStatus,
)
from ai_trading_analyst.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork

from .conftest import make_run, make_stock

UowFactory = Callable[[], SqlAlchemyUnitOfWork]


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, database_url: str, engine: Engine) -> TestClient:
    monkeypatch.setenv("ATA_DATABASE_URL", database_url)
    monkeypatch.setenv("ATA_SESSION_SECRET", "test-secret")
    app = build_app()
    return TestClient(app)


def _score(kind: ScoreKind, value: float) -> ScoreResult:
    return ScoreResult(
        kind=kind,
        status=ScoreStatus.COMPLETED,
        version="1.0",
        components=(
            ScoreComponent(
                name=ComponentName.TECHNICAL_SIGNALS,
                weight=1.0,
                value=value,
                effective_weight=1.0,
                reason="Testwert",
            ),
        ),
        coverage=1.0,
        confidence=ScoreConfidence.NORMAL,
        value=value,
    )


def _outcome(
    stock: Stock,
    run: AnalysisRun,
    *,
    status: ScreeningStatus = ScreeningStatus.CANDIDATE,
    earnings: EarningsFilterStatus | None = None,
    mit_scores: bool = False,
    swing: float = 7.4,
) -> StockScreeningOutcome:
    return StockScreeningOutcome(
        analysis_run_id=run.id,
        stock=stock,
        result=ScreeningResult(status=status),
        decision_candle_index=258,
        evaluated_at=datetime.now(UTC),
        signal_rule_version=SIGNAL_RULE_VERSION,
        earnings=(
            None
            if earnings is None
            else EarningsFilterResult(status=earnings, evaluated_at=datetime.now(UTC))
        ),
        swing_score=_score(ScoreKind.SWING, swing) if mit_scores else None,
        investment_score=_score(ScoreKind.LONG_TERM, 5.1) if mit_scores else None,
        recommendation=(
            RecommendationResult(
                level=Recommendation.CANDIDATE,
                version="1.0",
                reasons=("Testbegruendung",),
            )
            if mit_scores
            else None
        ),
    )


def _speichere(
    uow_factory: UowFactory,
    *,
    stock: Stock,
    run: AnalysisRun,
    outcomes: tuple[StockScreeningOutcome, ...] = (),
    mit_bericht: bool = False,
    mit_scores: bool = True,
    swing: float = 7.4,
    fehler: int = 0,
    bericht_erstellt_am: datetime | None = None,
) -> None:
    with uow_factory() as uow:
        uow.stocks.add(stock)
        uow.analysis_runs.add(run)
        for outcome in outcomes:
            uow.screening_results.add(outcome)
        if mit_bericht:
            uow.stock_reports.add(
                build_report(
                    _outcome(stock, run, mit_scores=mit_scores, swing=swing),
                    created_at=bericht_erstellt_am or datetime.now(UTC),
                    app_version="0.1.0",
                )
            )
        for nummer in range(fehler):
            uow.processing_errors.add(
                StockProcessingError(
                    analysis_run_id=run.id,
                    stock_symbol=f"ERR{nummer}",
                    message="Simulierter Modulfehler",
                    occurred_at=datetime.now(UTC),
                )
            )
        uow.commit()


def test_health_reports_ok(client: TestClient) -> None:
    response = client.get("/api/v1/system/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_ready_when_database_is_reachable(client: TestClient) -> None:
    response = client.get("/api/v1/system/readiness")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_analyselauf_laesst_sich_nicht_ueber_http_starten(client: TestClient) -> None:
    """ADR 0053: Der Endpunkt ist weg und kommt nicht versehentlich zurueck.

    Er baute den Analyse-Use-Case mit den Anbietern aus der Konfiguration --
    auf dem Server die Fixtures. Ein Aufruf schriebe dort einen Lauf aus
    erfundenen Werten in die Produktivdatenbank.
    """
    assert client.post("/api/v1/analysis-runs").status_code == 405


class TestLaufliste:
    def test_neueste_zuerst_und_seitenweise(
        self, client: TestClient, uow_factory: UowFactory
    ) -> None:
        jetzt = datetime.now(UTC)
        with uow_factory() as uow:
            for stunden in range(3):
                run = make_run(status=RunStatus.COMPLETED)
                uow.analysis_runs.add(
                    AnalysisRun(
                        id=run.id,
                        status=run.status,
                        started_at=jetzt - timedelta(hours=stunden),
                    )
                )
            uow.commit()

        antwort = client.get("/api/v1/analysis-runs", params={"limit": 2})

        assert antwort.status_code == 200
        seite = antwort.json()
        assert seite["total"] == 3
        assert seite["limit"] == 2 and seite["offset"] == 0
        gestartet = [eintrag["started_at"] for eintrag in seite["items"]]
        assert len(gestartet) == 2
        assert gestartet == sorted(gestartet, reverse=True)

    def test_filtert_nach_status(self, client: TestClient, uow_factory: UowFactory) -> None:
        with uow_factory() as uow:
            uow.analysis_runs.add(make_run(status=RunStatus.COMPLETED))
            uow.analysis_runs.add(make_run(status=RunStatus.FAILED))
            uow.commit()

        seite = client.get("/api/v1/analysis-runs", params={"status": "FAILED"}).json()

        assert seite["total"] == 1
        assert [eintrag["status"] for eintrag in seite["items"]] == ["FAILED"]

    def test_mehrere_status_gehen_gemeinsam(
        self, client: TestClient, uow_factory: UowFactory
    ) -> None:
        """"Der letzte erfolgreiche Lauf" ist COMPLETED **oder**
        PARTIALLY_COMPLETED: Ein Lauf, bei dem eine von zweihundert Aktien an
        einem isolierten Modulfehler haengen blieb, ist abgeschlossen
        (Doc 10, Paragraph 11). Mit nur einem Wert je Abfrage stuende in der
        Tagesuebersicht nach einem einzigen Anbieterfehler dauerhaft
        "noch keiner"."""
        with uow_factory() as uow:
            uow.analysis_runs.add(make_run(status=RunStatus.COMPLETED))
            uow.analysis_runs.add(make_run(status=RunStatus.PARTIALLY_COMPLETED))
            uow.analysis_runs.add(make_run(status=RunStatus.FAILED))
            uow.commit()

        seite = client.get(
            "/api/v1/analysis-runs",
            params=[("status", "COMPLETED"), ("status", "PARTIALLY_COMPLETED")],
        ).json()

        assert seite["total"] == 2
        assert {eintrag["status"] for eintrag in seite["items"]} == {
            "COMPLETED",
            "PARTIALLY_COMPLETED",
        }

    def test_offset_blaettert_weiter(self, client: TestClient, uow_factory: UowFactory) -> None:
        """Gegen echtes SQL: ``.limit().offset()`` mit fester Reihenfolge."""
        jetzt = datetime.now(UTC)
        with uow_factory() as uow:
            for stunden in range(3):
                run = make_run(status=RunStatus.COMPLETED)
                uow.analysis_runs.add(
                    AnalysisRun(
                        id=run.id,
                        status=run.status,
                        started_at=jetzt - timedelta(hours=stunden),
                    )
                )
            uow.commit()

        erste = client.get("/api/v1/analysis-runs", params={"limit": 2}).json()
        zweite = client.get("/api/v1/analysis-runs", params={"limit": 2, "offset": 2}).json()

        assert len(erste["items"]) == 2
        assert len(zweite["items"]) == 1
        assert zweite["total"] == 3 and zweite["offset"] == 2
        # Keine Ueberschneidung: Was auf Seite eins stand, steht nicht auf zwei.
        assert {e["id"] for e in erste["items"]}.isdisjoint({e["id"] for e in zweite["items"]})

    def test_limit_ueber_der_obergrenze_wird_abgewiesen(self, client: TestClient) -> None:
        assert client.get("/api/v1/analysis-runs", params={"limit": 500}).status_code == 422


class TestLaufdetail:
    def test_zaehlt_earnings_ausschluesse_und_modulfehler(
        self, client: TestClient, uow_factory: UowFactory
    ) -> None:
        run = make_run(status=RunStatus.COMPLETED)
        stock = make_stock("DET")
        weitere = (make_stock("DET2"), make_stock("DET3"), make_stock("DET4"))
        with uow_factory() as uow:
            uow.stocks.add(stock)
            for aktie in weitere:
                uow.stocks.add(aktie)
            uow.analysis_runs.add(run)
            uow.screening_results.add(
                _outcome(stock, run, earnings=EarningsFilterStatus.EARNINGS_EXCLUDED)
            )
            uow.screening_results.add(
                _outcome(weitere[0], run, earnings=EarningsFilterStatus.UNKNOWN)
            )
            uow.screening_results.add(
                _outcome(weitere[1], run, earnings=EarningsFilterStatus.EARNINGS_CLEAR)
            )
            # Keine Kandidatin, also nie gefragt: Die Earnings-Spalte bleibt
            # NULL. Sie mitzuzaehlen hiesse, eine nicht gestellte Frage als
            # Status zu lesen -- die Zaehlung muss sie auslassen.
            uow.screening_results.add(
                _outcome(weitere[2], run, status=ScreeningStatus.NOT_CANDIDATE)
            )
            uow.processing_errors.add(
                StockProcessingError(
                    analysis_run_id=run.id,
                    stock_symbol="BOOM",
                    message="Simulierter Modulfehler",
                    occurred_at=datetime.now(UTC),
                )
            )
            uow.commit()

        detail = client.get(f"/api/v1/analysis-runs/{run.id}").json()

        assert detail["earnings_excluded"] == 1
        # Getrennt gezaehlt: "unbekannt" ist kein belegter Nichttermin (ADR 0020).
        assert detail["earnings_unknown"] == 1
        assert detail["module_errors"] == 1

    def test_unbekannter_lauf_liefert_404(self, client: TestClient) -> None:
        antwort = client.get(f"/api/v1/analysis-runs/{uuid.uuid4()}")
        assert antwort.status_code == 404


class TestBerichte:
    def test_kurzliste_traegt_empfehlung_und_beide_scores(
        self, client: TestClient, uow_factory: UowFactory
    ) -> None:
        run = make_run(status=RunStatus.COMPLETED)
        stock = make_stock("RPT")
        _speichere(uow_factory, stock=stock, run=run, mit_bericht=True)

        (eintrag,) = client.get(f"/api/v1/analysis-runs/{run.id}/reports").json()

        assert eintrag["symbol"] == "RPT"
        assert eintrag["recommendation"] == "CANDIDATE"
        assert eintrag["swing_score"] == 7.4
        assert eintrag["investment_score"] == 5.1

    def test_kurzliste_folgt_der_rangfolge_der_meldung(
        self, client: TestClient, uow_factory: UowFactory
    ) -> None:
        """Bester Swing-Score zuerst, fehlender zuletzt, bei Gleichstand nach
        Symbol -- dieselbe Rangfolge wie in der Telegram-Meldung. Sortiert
        die API nicht, sondern jede Anzeige fuer sich, steht dieselbe Liste
        an zwei Stellen verschieden."""
        run = make_run(status=RunStatus.COMPLETED)
        _speichere(uow_factory, stock=make_stock("MITTE"), run=run, mit_bericht=True, swing=7.4)
        for symbol, swing, scores in (
            ("BESTE", 9.1, True),
            ("GLEICH", 7.4, True),
            ("OHNE", 0.0, False),
        ):
            with uow_factory() as uow:
                aktie = make_stock(symbol)
                uow.stocks.add(aktie)
                uow.stock_reports.add(
                    build_report(
                        _outcome(aktie, run, mit_scores=scores, swing=swing),
                        created_at=datetime.now(UTC),
                        app_version="0.1.0",
                    )
                )
                uow.commit()

        eintraege = client.get(f"/api/v1/analysis-runs/{run.id}/reports").json()

        assert [eintrag["symbol"] for eintrag in eintraege] == [
            "BESTE",
            "GLEICH",
            "MITTE",
            "OHNE",
        ]

    def test_berichte_eines_unbekannten_laufs_liefern_404(self, client: TestClient) -> None:
        assert client.get(f"/api/v1/analysis-runs/{uuid.uuid4()}/reports").status_code == 404

    def test_dokument_kommt_unveraendert_zurueck(
        self, client: TestClient, uow_factory: UowFactory
    ) -> None:
        run = make_run(status=RunStatus.COMPLETED)
        stock = make_stock("DOC")
        _speichere(uow_factory, stock=stock, run=run, mit_bericht=True)
        (eintrag,) = client.get(f"/api/v1/analysis-runs/{run.id}/reports").json()

        dokument = client.get(f"/api/v1/reports/{eintrag['report_id']}").json()

        # Die deutschen Schluessel und alle achtzehn Punkte, so wie gespeichert
        # -- die API uebersetzt das Dokument nicht (ADR 0053).
        assert len(dokument["abschnitte"]) == 18
        abschnitt = dokument["abschnitte"]["SYMBOL_UND_UNTERNEHMEN"]
        assert abschnitt["verfuegbar"] is True
        assert abschnitt["inhalt"]["symbol"] == "DOC"
        assert dokument["berichtsschema_version"]

    def test_unbekannter_bericht_liefert_404(self, client: TestClient) -> None:
        assert client.get(f"/api/v1/reports/{uuid.uuid4()}").status_code == 404


class TestHistorieJeAktie:
    def test_neueste_zuerst(self, client: TestClient, uow_factory: UowFactory) -> None:
        stock = make_stock("HIST")
        jetzt = datetime.now(UTC)
        for tage in range(2):
            _speichere(
                uow_factory,
                stock=stock,
                run=make_run(status=RunStatus.COMPLETED),
                mit_bericht=True,
                bericht_erstellt_am=jetzt - timedelta(days=tage),
            )

        seite = client.get("/api/v1/stocks/HIST/reports").json()

        assert seite["total"] == 2
        erstellt = [eintrag["created_at"] for eintrag in seite["items"]]
        assert erstellt == sorted(erstellt, reverse=True)

    def test_symbol_wird_wie_in_der_kommandozeile_normalisiert(
        self, client: TestClient, uow_factory: UowFactory
    ) -> None:
        stock = make_stock("CASE")
        _speichere(uow_factory, stock=stock, run=make_run(), mit_bericht=True)

        assert client.get("/api/v1/stocks/case/reports").json()["total"] == 1

    def test_bekannte_aktie_ohne_bericht_liefert_leere_seite(
        self, client: TestClient, uow_factory: UowFactory
    ) -> None:
        stock = make_stock("LEER")
        with uow_factory() as uow:
            uow.stocks.add(stock)
            uow.commit()

        seite = client.get("/api/v1/stocks/LEER/reports").json()

        assert seite["total"] == 0
        assert seite["items"] == []

    def test_offset_und_obergrenze_gelten_auch_hier(
        self, client: TestClient, uow_factory: UowFactory
    ) -> None:
        stock = make_stock("BLAETTER")
        jetzt = datetime.now(UTC)
        for tage in range(3):
            _speichere(
                uow_factory,
                stock=stock,
                run=make_run(status=RunStatus.COMPLETED),
                mit_bericht=True,
                bericht_erstellt_am=jetzt - timedelta(days=tage),
            )

        zweite = client.get(
            "/api/v1/stocks/BLAETTER/reports", params={"limit": 2, "offset": 2}
        ).json()

        assert zweite["total"] == 3
        assert len(zweite["items"]) == 1
        assert (
            client.get(
                "/api/v1/stocks/BLAETTER/reports", params={"limit": 500}
            ).status_code
            == 422
        )

    def test_unbekannte_aktie_liefert_404(self, client: TestClient) -> None:
        assert client.get("/api/v1/stocks/GIBTESNICHT/reports").status_code == 404
