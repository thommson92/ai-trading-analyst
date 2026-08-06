"""ASGI-Einstiegspunkt: ``uvicorn ai_trading_analyst.main:app``."""

from __future__ import annotations

from ai_trading_analyst.bootstrap import build_app

app = build_app()
