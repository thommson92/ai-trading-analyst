"""FastAPI-Anwendung: nur Routen-Registrierung, keine Verdrahtung konkreter
Infrastruktur (siehe ``ai_trading_analyst.bootstrap`` fuer den Composition Root)."""

from __future__ import annotations

from fastapi import FastAPI

from .v1 import analysis_runs, system


def create_app() -> FastAPI:
    app = FastAPI(title="AI Trading Analyst", version="0.1.0")
    app.include_router(analysis_runs.router)
    app.include_router(system.router)
    return app
