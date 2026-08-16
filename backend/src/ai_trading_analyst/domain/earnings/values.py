"""Wertobjekte des Earnings-Filters (Doc 10, Paragraph 6.5; ADR 0020).

Reines Python -- keine Infrastruktur, kein Anbieter. Der Domain Layer kennt
Finnhub nicht (Doc 10, Paragraph 9), nur ``EarningsProvider`` als Port
(``domain.analysis.ports``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class EarningsFilterStatus(StrEnum):
    """Ergebnisstatus der Earnings-Pruefung (ADR 0020: reduziert auf drei
    Werte, da der Anbieter keine bestaetigt/geschaetzt-Unterscheidung liefert)."""

    EARNINGS_CLEAR = "EARNINGS_CLEAR"
    EARNINGS_EXCLUDED = "EARNINGS_EXCLUDED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class NextEarningsDate:
    """Ein von einem Anbieter gelieferter kuenftiger Earnings-Termin."""

    date: date
    source: str
    retrieved_at: datetime


@dataclass(frozen=True, slots=True)
class EarningsFilterResult:
    """Persistierbare Entscheidung samt Beleg.

    Deckt die Doc-10-Anforderungen "Quelle speichern" und "Datenqualitaet
    kennzeichnen" ab: ``source`` und ``next_earnings_date`` belegen die
    Entscheidung, ``reason`` erklaert ein ``UNKNOWN``.
    """

    status: EarningsFilterStatus
    evaluated_at: datetime
    next_earnings_date: date | None = None
    candles_until_earnings: int | None = None
    source: str | None = None
    reason: str | None = None
    """Nur bei ``UNKNOWN`` gesetzt: ``"no_coverage"`` (Anbieter kennt keinen
    Termin fuer dieses Symbol, ADR 0017 L3), ``"provider_error"`` (Anbieter
    war nicht erreichbar, ADR 0017: normaler Betriebszustand) oder
    ``"invalid_data"`` (Anbieter war erreichbar, seine Antwort aber nicht
    plausibel auswertbar, z. B. ein Termin vor der Entscheidungskerze)."""


@dataclass(frozen=True, slots=True)
class EarningsFilterParameters:
    """Aus ``AppConfig`` gebaut (bootstrap.py) -- Domain bleibt config-frei."""

    configured_exclusion_candles: int
    candles_per_day: int
