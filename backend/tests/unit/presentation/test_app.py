"""Die Anwendung liefert das Dashboard mit aus -- oder laeuft ohne (ADR 0052)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ai_trading_analyst.presentation.api.app import create_app


def _client(dashboard: Path | None) -> TestClient:
    app = create_app(dashboard)
    app.state.check_database_ready = lambda: True
    return TestClient(app)


def test_ohne_export_laeuft_die_api_weiter(tmp_path: Path) -> None:
    """Der Batchbetrieb darf nicht daran haengen, ob jemand gebaut hat."""
    antwort = _client(tmp_path / "gibtesnicht").get("/api/v1/system/health")

    assert antwort.status_code == 200


def test_der_export_wird_unter_der_wurzel_ausgeliefert(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<h1>Tagesuebersicht</h1>", encoding="utf-8")

    antwort = _client(tmp_path).get("/")

    assert antwort.status_code == 200
    assert "Tagesuebersicht" in antwort.text


def test_die_api_gewinnt_gegen_den_export(tmp_path: Path) -> None:
    """Eine Datei darf keinen Endpunkt verdecken.

    Der Export wird zuletzt eingehaengt; wer das umdreht, liefert unter
    ``/api/v1/system/health`` eine 404-Seite aus.
    """
    verzeichnis = tmp_path / "api" / "v1" / "system"
    verzeichnis.mkdir(parents=True)
    (verzeichnis / "health").write_text("falsch", encoding="utf-8")

    antwort = _client(tmp_path).get("/api/v1/system/health")

    assert antwort.json() == {"status": "ok"}
