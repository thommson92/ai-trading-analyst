"""Tests des Fixture-Research-Providers -- deterministisch, unabhaengig vom Symbol."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ai_trading_analyst.domain.analysis import Stock
from ai_trading_analyst.domain.research import ResearchStatus
from ai_trading_analyst.infrastructure.fixtures.research_provider import FixtureResearchProvider

REFERENCE = datetime(2026, 8, 17, tzinfo=UTC)


def _stock(symbol: str) -> Stock:
    return Stock(id=uuid.uuid4(), symbol=symbol, exchange="SMART")


def test_liefert_immer_einen_vollstaendigen_bericht() -> None:
    provider = FixtureResearchProvider(now=lambda: REFERENCE)
    report = provider.research(_stock("AAPL"))
    assert report.status is ResearchStatus.COMPLETED
    assert report.model == "fixture"
    assert report.citations


def test_ist_unabhaengig_vom_symbol_strukturell_gleich() -> None:
    provider = FixtureResearchProvider(now=lambda: REFERENCE)
    erstes = provider.research(_stock("AAPL"))
    zweites = provider.research(_stock("MSFT"))
    assert erstes.status == zweites.status
    assert erstes.confidence == zweites.confidence


def test_zitat_verweist_auf_das_angefragte_symbol() -> None:
    provider = FixtureResearchProvider(now=lambda: REFERENCE)
    report = provider.research(_stock("AAPL"))
    assert "AAPL" in report.citations[0].url
