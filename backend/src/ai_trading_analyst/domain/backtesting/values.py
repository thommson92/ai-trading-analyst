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
from itertools import combinations
from uuid import UUID

from ai_trading_analyst.domain.screening import SignalType, qualifies

SignalCombination = frozenset[SignalType]
"""Menge der aufgetretenen Signaltypen, nicht Reihenfolge oder Position
(G1-Pruefvorlage Abschnitt 4.3: massgeblich fuer die Gruppierung ist
ausschliesslich die Menge)."""


def qualifying_combinations(required_crossing_signals: int) -> tuple[SignalCombination, ...]:
    """Alle Signalkombinationen, die die Qualifikationsregel erfuellen koennen
    (G1-Pruefvorlage Abschnitt 4.3).

    Aufgezaehlt werden alle Teilmengen von ``SignalType``, die ``qualifies``
    durchlaesst -- die Regel steht also genau einmal im Code und wird hier
    nicht zweitgeschrieben. Bei ``required_crossing_signals=2`` sind das vier
    Kaufsignal-Kombinationen mal drei Zusatz-Kombinationen, zusammen zwoelf.

    Hier und nicht in ``metrics.py``: Die Kennzahlen der Aktienseite und die
    der Optionsseite brauchen dieselbe Aufzaehlung, und zwei Fassungen
    koennten auseinanderlaufen, ohne dass ein Test es merkt.
    """
    alle = tuple(SignalType)
    return tuple(
        frozenset(kombination)
        for groesse in range(1, len(alle) + 1)
        for kombination in combinations(alle, groesse)
        if qualifies(frozenset(kombination), required_crossing_signals)
    )


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

    ``deduplicated_event_count`` zaehlt seit ADR 0057 die **Episoden** --
    Entscheidungspunkte, die dieselbe Bewegung auswerten, sind ein Ereignis.
    Der Feldname blieb: Was eine Zeile bedeutet, sagt ihre Signalregel-Version,
    und ein neuer Name haette alte Zeilen nicht wahrer gemacht.

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
class EpisodeHorizonOutcome:
    """Was der Kurs nach **einem** gezaehlten Ereignis bis zu einem Horizont
    tat (ADR 0061).

    Alle Werte sind ``None``, wenn die Historie den Horizont nicht mehr
    erreicht -- das Ereignis liegt zu nah am Ende. Der Horizont steht dann
    trotzdem in der Liste: Ein fehlender Eintrag saehe aus wie ein nie
    gerechneter.
    """

    horizon: int
    return_pct: float | None
    max_loss: float | None
    drawdown: float | None
    held_above_entry: bool | None

    @property
    def reached(self) -> bool:
        """Hat die Historie den Horizont erreicht? Der eine Begriff dafuer --
        wer einzelne Felder auf ``None`` prueft, prueft eine Zeile zu viel."""
        return self.return_pct is not None


@dataclass(frozen=True, slots=True)
class BacktestEpisode:
    """Ein gezaehltes Ereignis des Signal-Backtests (ADR 0057, ADR 0061).

    Der Einstieg ist der erste Trigger der Episode; ``entry_at`` ist der
    **Zeitstempel** dieser Kerze und kein Index -- der Tiefen-Backfill fuegt
    aeltere Bars vorn an und verschoebe jeden Index (``signal_events.
    candle_index`` ist die Warnung dafuer). ``entry_close`` ist der
    Einstiegskurs (CLAUDE.md "Backtesting").

    Aus genau diesen Episoden entstehen die Kennzahlen je Horizont in
    ``HorizonMetrics``; beide rechnen ueber dieselbe Funktion.
    """

    stock_id: UUID
    signal_types: SignalCombination
    signal_rule_version: str
    evaluated_at: datetime
    entry_at: datetime
    entry_close: float
    trigger_count: int
    last_trigger_at: datetime
    horizons: tuple[EpisodeHorizonOutcome, ...]


@dataclass(frozen=True, slots=True)
class BacktestComputation:
    """Aggregate und Einzelepisoden einer Aktie aus **einer** Rechnung."""

    results: tuple[BacktestResult, ...]
    episodes: tuple[BacktestEpisode, ...]


@dataclass(frozen=True, slots=True)
class BacktestParameters:
    """Aus ``BacktestingConfig`` gebaut (bootstrap.py) -- Domain bleibt
    config-frei."""

    horizons: tuple[int, ...]
    minimum_sample_size: int
    normal_confidence_sample_size: int
    history_years: int
    """Wie viele Jahre vor ``evaluated_at`` repliziert werden -- aeltere
    gespeicherte Kerzen bleiben unberuecksichtigt (Doc 10, Paragraph 6.6)."""
