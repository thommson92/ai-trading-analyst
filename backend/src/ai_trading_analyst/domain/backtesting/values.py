"""Wertobjekte der historischen Signalprüfung (Doc 07; G1-Prüfvorlage
Abschnitt 4; CLAUDE.md "Backtesting").

Reines Python -- keine Infrastruktur, kein Anbieter. Baut auf
``domain.screening`` auf (``evaluate_candidate`` gilt laut dessen eigenem
Modul-Docstring gleichermassen fuer die Live-Pruefung wie fuer jeden
Entscheidungspunkt im Backtesting).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from ai_trading_analyst.domain.screening import SignalType

SignalCombination = frozenset[SignalType]
"""Menge der aufgetretenen Signaltypen, nicht Reihenfolge oder Position
(G1-Pruefvorlage Abschnitt 4.3: massgeblich fuer die Gruppierung ist
ausschliesslich die Menge)."""


class BacktestConfidence(StrEnum):
    """Verlaesslichkeit einer Kennzahl anhand der Stichprobengroesse
    (CLAUDE.md "Backtesting"; ``BacktestingConfig.minimum_sample_size`` /
    ``normal_confidence_sample_size``)."""

    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    LOW_SAMPLE = "LOW_SAMPLE"
    NORMAL = "NORMAL"


@dataclass(frozen=True, slots=True)
class HorizonMetrics:
    """Kennzahlen einer Signalkombination fuer einen Bewertungshorizont
    (Doc 07 "Kennzahlen").

    Alle ``float``-Felder sind ``None``, wenn ``deduplicated_event_count``
    null ist -- kein Ersatzwert, kein stillschweigender Nullwert.
    """

    horizon: int
    raw_event_count: int
    deduplicated_event_count: int
    hit_rate: float | None
    mean_return: float | None
    median_return: float | None
    max_loss: float | None
    drawdown: float | None
    held_above_entry_rate: float | None
    confidence: BacktestConfidence


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Historische Kennzahlen einer Aktie fuer eine Signalkombination, ueber
    alle konfigurierten Horizonte."""

    stock_id: UUID
    signal_types: SignalCombination
    signal_rule_version: str
    evaluated_at: datetime
    history_start: datetime
    history_end: datetime
    horizons: tuple[HorizonMetrics, ...]
    earnings_exclusion_applied: bool = False
    """Wurden Ereignisse nahe einem Berichtstermin aus dem Replay
    ausgeschlossen? (ADR 0038, Entscheidung 3.)

    Heute durchgehend ``False``: Historische Berichtstermine gibt es nicht,
    ADR 0017 haelt das als Einschraenkung L9 fest. Der Backtest zaehlt damit
    Ereignisse, die der Live-Filter ausgeschlossen haette -- die Kennzahlen
    messen eine leicht andere Strategie als die gehandelte (Risiko R6).

    Ein Feld, das immer ``False`` ist, sieht nach Vorratshaltung aus. Es ist
    das Gegenteil: Sobald der EDGAR-Adapter fuer ``8-K``-Termine da ist (E3),
    sagen die alten Zeilen weiterhin die Wahrheit ueber sich selbst, statt
    rueckwirkend so auszusehen, als waeren sie gefiltert worden.
    """


@dataclass(frozen=True, slots=True)
class BacktestParameters:
    """Aus ``BacktestingConfig`` gebaut (bootstrap.py) -- Domain bleibt
    config-frei."""

    horizons: tuple[int, ...]
    cooldown_candles: int
    minimum_sample_size: int
    normal_confidence_sample_size: int
    history_years: int
    """Wie viele Jahre vor ``evaluated_at`` repliziert werden -- aeltere
    gespeicherte Kerzen bleiben unberuecksichtigt (Doc 10, Paragraph 6.6)."""
