"""Tests des Fixture-Earnings-Providers -- Offset-zu-Datum-Rueckrechnung."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from ai_trading_analyst.domain.analysis import EarningsProviderError, Stock
from ai_trading_analyst.infrastructure.fixtures.earnings_provider import FixtureEarningsProvider

REFERENCE = date(2026, 8, 17)  # Montag


def _stock(symbol: str) -> Stock:
    return Stock(id=uuid.uuid4(), symbol=symbol, exchange="SMART")


def test_ausgeschlossenes_symbol_liegt_nah_am_referenzdatum() -> None:
    provider = FixtureEarningsProvider(reference_date=lambda: REFERENCE)
    termin = provider.next_earnings_date(_stock("EARNEXCLUDED"))
    assert termin is not None
    assert termin.date > REFERENCE
    assert termin.source == "fixture"


def test_freies_symbol_liegt_weit_in_der_zukunft() -> None:
    provider = FixtureEarningsProvider(reference_date=lambda: REFERENCE)
    ausgeschlossen = provider.next_earnings_date(_stock("EARNEXCLUDED"))
    frei = provider.next_earnings_date(_stock("EARNCLEAR"))
    assert ausgeschlossen is not None
    assert frei is not None
    assert frei.date > ausgeschlossen.date


def test_unbekanntes_symbol_hat_keine_abdeckung() -> None:
    provider = FixtureEarningsProvider(reference_date=lambda: REFERENCE)
    assert provider.next_earnings_date(_stock("NICHT_IN_DER_FIXTURE")) is None


def test_fehlersymbol_wirft_earnings_provider_error() -> None:
    provider = FixtureEarningsProvider(reference_date=lambda: REFERENCE)
    with pytest.raises(EarningsProviderError, match="Simulierter Providerfehler"):
        provider.next_earnings_date(_stock("EARNERROR"))


def test_ergebnis_ist_deterministisch_fuer_dasselbe_referenzdatum() -> None:
    provider = FixtureEarningsProvider(reference_date=lambda: REFERENCE)
    erster = provider.next_earnings_date(_stock("EARNEXCLUDED"))
    zweiter = provider.next_earnings_date(_stock("EARNEXCLUDED"))
    assert erster is not None
    assert zweiter is not None
    assert erster.date == zweiter.date


def test_termin_faellt_nie_auf_ein_wochenende() -> None:
    provider = FixtureEarningsProvider(reference_date=lambda: REFERENCE)
    for symbol in ("EARNEXCLUDED", "EARNCLEAR"):
        termin = provider.next_earnings_date(_stock(symbol))
        assert termin is not None
        assert termin.date.weekday() < 5
