"""Kerzenzaehlung bis zu einem kuenftigen Earnings-Termin (ADR 0020).

Wochentagsnaeherung: Montag bis Freitag gelten als vollstaendige
Handelstage mit ``candles_per_day`` Kerzen, US-Boersenfeiertage und
verkuerzte Handelstage bleiben unberuecksichtigt (ADR 0020, Einschraenkung
L2). Kein Kalenderzugriff, keine Abhaengigkeit von IBKR oder dem
Trading-Day-Dispatcher.
"""

from __future__ import annotations

from datetime import date, timedelta


def count_future_trading_candles(
    as_of: date, earnings_date: date, candles_per_day: int
) -> int:
    """Zaehlt kuenftige Kerzen streng nach ``as_of`` bis einschliesslich
    ``earnings_date``.

    ``as_of`` selbst zaehlt nicht mit -- er ist der Handelstag, an dem die
    Entscheidungskerze liegt, nicht Teil der "Zukunft". Ein Termin an
    ``as_of`` liefert deshalb 0 Kerzen, was bei jeder sinnvollen
    Fensterschwelle (>= 1) ohnehin ``EARNINGS_EXCLUDED`` ergibt.

    Raises:
        ValueError: wenn ``earnings_date`` vor ``as_of`` liegt oder
            ``candles_per_day`` kleiner als 1 ist.
    """
    if candles_per_day < 1:
        raise ValueError(f"candles_per_day ({candles_per_day}) muss mindestens 1 sein")
    if earnings_date < as_of:
        raise ValueError(
            f"earnings_date ({earnings_date}) liegt vor as_of ({as_of})"
        )

    trading_days = 0
    current = as_of + timedelta(days=1)
    while current <= earnings_date:
        if current.weekday() < 5:
            trading_days += 1
        current += timedelta(days=1)

    return trading_days * candles_per_day
