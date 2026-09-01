"""FastAPI-Anwendung: nur Routen-Registrierung, keine Verdrahtung konkreter
Infrastruktur (siehe ``ai_trading_analyst.bootstrap`` fuer den Composition Root)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .v1 import analysis_runs, reports, stocks, system


def create_app(dashboard_directory: Path | None = None) -> FastAPI:
    """Die Anwendung, wahlweise mit dem Dashboard.

    ``dashboard_directory`` ist der statische Export des Frontends. Er wird
    **zuletzt** und unter ``/`` eingehaengt: Die API-Routen sind vorher
    registriert und gewinnen damit, alles Uebrige ist eine Datei (ADR 0052).

    Ohne den Ordner laeuft die Anwendung weiter. Der Batchbetrieb haengt
    nicht daran, ob jemand ``npm run build`` ausgefuehrt hat.
    """
    app = FastAPI(title="AI Trading Analyst", version="0.1.0")
    app.include_router(analysis_runs.router)
    app.include_router(reports.router)
    app.include_router(stocks.router)
    app.include_router(system.router)
    if dashboard_directory is not None and dashboard_directory.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=dashboard_directory, html=True),
            name="dashboard",
        )
    return app
