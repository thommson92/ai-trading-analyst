"""API-Integrationstests: FastAPI-App vollstaendig verdrahtet
(``ai_trading_analyst.bootstrap.build_app``) gegen echtes PostgreSQL."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from ai_trading_analyst.bootstrap import build_app


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, database_url: str, engine: Engine) -> TestClient:
    monkeypatch.setenv("ATA_DATABASE_URL", database_url)
    monkeypatch.setenv("ATA_SESSION_SECRET", "test-secret")
    app = build_app()
    return TestClient(app)


def test_health_reports_ok(client: TestClient) -> None:
    response = client.get("/api/v1/system/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_ready_when_database_is_reachable(client: TestClient) -> None:
    response = client.get("/api/v1/system/readiness")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_post_analysis_run_startet_einen_fixture_basierten_lauf(client: TestClient) -> None:
    response = client.post("/api/v1/analysis-runs")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PARTIALLY_COMPLETED"
    assert body["number_of_stocks"] == 4
    assert body["candidates_found"] == 1


def test_get_analysis_run_liefert_den_gestarteten_lauf(client: TestClient) -> None:
    created = client.post("/api/v1/analysis-runs").json()

    response = client.get(f"/api/v1/analysis-runs/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_unbekannter_lauf_liefert_404(client: TestClient) -> None:
    response = client.get("/api/v1/analysis-runs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_list_analysis_runs_enthaelt_gestartete_laeufe(client: TestClient) -> None:
    created = client.post("/api/v1/analysis-runs").json()

    response = client.get("/api/v1/analysis-runs")

    assert response.status_code == 200
    assert any(run["id"] == created["id"] for run in response.json())
