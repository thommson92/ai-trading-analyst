"""Wertobjekte und Enums des deterministischen Signalkerns (Gate G1).

Fachliche Grundlage ist ausschliesslich ``docs/requirements/g1-pruefvorlage.md``
-- bei Widersprueche mit aelteren Dokumenten hat diese Datei Vorrang (siehe
dort, Abschnitt "Herkunft").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

SIGNAL_RULE_VERSION = "g1-pruefvorlage-2026-09-02"
"""Version der fachlichen Regeln, gegen die dieser Signalkern implementiert
wurde (Datum der finalen Bestaetigung in g1-pruefvorlage.md). Wird an jedem
persistierten Ergebnis gespeichert (Doc 10, Paragraph 8), damit spaetere
Aenderungen an den Signalregeln in bestehenden Daten sichtbar bleiben.

``2026-09-02`` gegenueber ``2026-08-06``: fuenf Kriterien statt drei, Schwelle
drei statt zwei, Signal B ohne Gap-up-Klausel (ADR 0056)."""


class SignalType(StrEnum):
    """Die drei fachlich freigegebenen Signaltypen (Doc 05, G1-Pruefvorlage Abschnitt 2)."""

    RSI_CROSS = "RSI_CROSS"
    PRICE_EMA20_BREAKOUT = "PRICE_EMA20_BREAKOUT"
    EMA5_EMA20_CROSS = "EMA5_EMA20_CROSS"


class ScreeningStatus(StrEnum):
    """Ergebnisstatus einer Kandidatenpruefung (G1-Pruefvorlage Abschnitt 1.5, 3.4)."""

    CANDIDATE = "CANDIDATE"
    NOT_CANDIDATE = "NOT_CANDIDATE"
    UNKNOWN_DATA_INCOMPLETE = "UNKNOWN_DATA_INCOMPLETE"


@dataclass(frozen=True, slots=True)
class Candle:
    """Eine vollstaendig abgeschlossene 195-Minuten-Kerze der regulaeren Sitzung.

    ``daily_candle_index`` unterscheidet die erste (1) von der zweiten (2)
    Kerze eines Handelstages -- massgeblich fuer die Beschraenkung der
    Backtesting-Entscheidungszeitpunkte auf die erste Tageskerze
    (G1-Pruefvorlage Abschnitt 4.1).
    """

    timestamp: datetime
    daily_candle_index: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class IndicatorValues:
    """Auf Kerzenschluss berechnete Indikatorwerte (G1-Pruefvorlage Abschnitt 1.2).

    ``None`` bedeutet: Wert fuer diese Kerze nicht verfuegbar -- niemals
    stillschweigend als "Signal nicht erfuellt" zu werten (Abschnitt 1.5).
    """

    rsi: float | None
    rsi_ma: float | None
    ema5: float | None
    ema20: float | None


@dataclass(frozen=True, slots=True)
class SignalEvent:
    """Erstes Auftreten eines Signaltyps innerhalb eines ausgewerteten Fensters.

    Wird zusaetzlich zur Mitgliedschaft in ``fired_signal_types`` gespeichert,
    fuer Audit und Bericht -- nicht als Kriterium fuer "identische
    Signalkombination" (G1-Pruefvorlage Abschnitt 4.3).
    """

    signal_type: SignalType
    candle_index: int


@dataclass(frozen=True, slots=True)
class ScreeningResult:
    """Ergebnis einer Kandidatenpruefung fuer eine Kerze ``t`` (Abschnitt 3.4)."""

    status: ScreeningStatus
    fired_signal_types: frozenset[SignalType] = frozenset()
    signal_events: tuple[SignalEvent, ...] = ()
    reason: str | None = None
    affected_index: int | None = None


class DataIncompleteError(Exception):
    """Eine Signalformel konnte nicht ausgewertet werden -- Daten fehlen.

    Wird von den Signalfunktionen (``signals.py``) als zweite Verteidigungslinie
    ausgeloest, falls trotz vorgelagerter Vollstaendigkeitspruefung ein
    benoetigter Wert fehlt. Niemals als "Signal nicht erfuellt" zu behandeln.
    """

    def __init__(self, candle_index: int, required: tuple[str, ...]) -> None:
        self.candle_index = candle_index
        self.required = required
        super().__init__(
            f"Fehlende Daten fuer Kerzenindex {candle_index}: benoetigt {', '.join(required)}"
        )


@dataclass(frozen=True, slots=True)
class CandleSeries:
    """Chronologisch aufsteigende, indexstabile Folge von Kerzen und Indikatoren.

    Index 0 ist die aelteste bekannte Kerze. ``candles`` und ``indicators``
    muessen exakt gleich lang sein und sich auf dieselbe Kerze am selben Index
    beziehen.
    """

    candles: tuple[Candle, ...]
    indicators: tuple[IndicatorValues, ...]

    def __post_init__(self) -> None:
        if len(self.candles) != len(self.indicators):
            raise ValueError(
                "candles und indicators muessen gleich lang sein: "
                f"{len(self.candles)} != {len(self.indicators)}"
            )

    def __len__(self) -> int:
        return len(self.candles)

    def has_index(self, index: int) -> bool:
        return 0 <= index < len(self.candles)

    def candle(self, index: int) -> Candle:
        return self.candles[index]

    def indicator(self, index: int) -> IndicatorValues:
        return self.indicators[index]
