"""Tests der Wochentagsnaeherung fuer die Kerzenzaehlung (ADR 0020)."""

from __future__ import annotations

from datetime import date

import pytest

from ai_trading_analyst.domain.earnings import count_future_trading_candles

CANDLES_PER_DAY = 2


def test_termin_am_selben_tag_zaehlt_null_kerzen() -> None:
    montag = date(2026, 8, 17)
    assert count_future_trading_candles(montag, montag, CANDLES_PER_DAY) == 0


def test_termin_am_naechsten_tag_zaehlt_einen_handelstag() -> None:
    montag = date(2026, 8, 17)
    dienstag = date(2026, 8, 18)
    assert count_future_trading_candles(montag, dienstag, CANDLES_PER_DAY) == 2


def test_wochenende_wird_uebersprungen() -> None:
    freitag = date(2026, 8, 21)
    montag_danach = date(2026, 8, 24)
    # Nur der Montag zaehlt als Handelstag, Samstag/Sonntag nicht.
    assert count_future_trading_candles(freitag, montag_danach, CANDLES_PER_DAY) == 2


def test_volle_handelswoche_ergibt_fuenf_handelstage() -> None:
    montag = date(2026, 8, 17)
    montag_naechste_woche = date(2026, 8, 24)
    assert count_future_trading_candles(montag, montag_naechste_woche, CANDLES_PER_DAY) == 10


def test_earnings_date_vor_as_of_wirft_fehler() -> None:
    with pytest.raises(ValueError, match="liegt vor"):
        count_future_trading_candles(date(2026, 8, 18), date(2026, 8, 17), CANDLES_PER_DAY)


def test_candles_per_day_unter_eins_wirft_fehler() -> None:
    with pytest.raises(ValueError, match="mindestens 1"):
        count_future_trading_candles(date(2026, 8, 17), date(2026, 8, 18), 0)
