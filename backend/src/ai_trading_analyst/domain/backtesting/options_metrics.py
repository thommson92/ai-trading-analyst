"""Kennzahlen der simulierten Put-Verkaeufe (ADR 0058, Stufe 1).

Reine Rechnung auf fertigen Trades -- Replay und Simulation liegen in
``replay.py`` und ``options_trade.py``.

**Absoluter Ertrag und Rendite auf gebundenes Kapital stehen nebeneinander,
und keine ersetzt die andere** (ADR 0058, Festlegung 6). Der Cash Secured Put
bringt fuer dieselbe Markterwartung mehr Dollar als ein Spread und bindet
dafuer ein Vielfaches an Kapital; wer nur eine der beiden Zahlen ausweist,
entscheidet den Vergleich, statt ihn zu zeigen. Eine Zinsannahme braucht es
dafuer nicht: Habenzinsen auf Barbestand sind eine Eigenschaft des Kontos,
nicht des Trades.

**Grundlinie und gemanagte Variante bleiben getrennt.** Sie zu einer Zahl zu
verrechnen waere derselbe Fehler wie eine gemeinsame "Erfolgsquote" aus
Trefferquote und Halten oberhalb des Einstiegs (``CLAUDE.md``): Der
Unterschied zwischen ihnen **ist** die Aussage.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from ai_trading_analyst.domain.options import DEFAULT_STRIKE_GRID, HISTORICAL_CALENDAR
from ai_trading_analyst.domain.screening import SignalType

from .options_trade import (
    OPTIONS_BACKTEST_VERSION,
    OptionsBacktestParameters,
    OptionTrade,
    TradeOutcome,
)
from .values import (
    BacktestConfidence,
    BacktestParameters,
    SignalCombination,
    qualifying_combinations,
)


@dataclass(frozen=True, slots=True)
class VariantMetrics:
    """Kennzahlen einer Ausstiegsvariante.

    Alle Geldbetraege je Kontrakt. ``None`` heisst: keine Grundlage, nicht
    null.
    """

    trades: int
    win_rate: float | None
    """Anteil der Trades mit einem Ergebnis ueber null."""
    mean_profit: float | None
    median_profit: float | None
    total_profit: float | None
    worst_profit: float | None
    """Der schlechteste einzelne Trade -- die Zahl, die eine gute
    Trefferquote nicht zeigt."""
    mean_return_on_capital: float | None
    """Ertrag im Verhaeltnis zum gebundenen Kapital, je Trade gerechnet und
    dann gemittelt. Bei einem Cash Secured Put ist das ``strike * 100`` und
    damit **immer positiv** -- eine Absicherung gegen null waere eine gegen
    einen Fall, den es nicht gibt (``CLAUDE.md``), und sie mittelte
    stillschweigend ueber weniger Trades, als daneben stehen."""
    expired_worthless: int
    assigned: int
    take_profits: int
    stops: int


@dataclass(frozen=True, slots=True)
class OptionsBacktestResult:
    """Das Ergebnis einer Signalkombination.

    ``assumptions`` ist kein Beiwerk: Verfallskalender, Strike-Raster,
    Volatilitaetsaufschlag und Ausfuehrungsabschlag machen aus demselben
    Kurspfad andere Zahlen. Ohne sie waere die Zeile nicht deutbar.
    """

    signal_types: SignalCombination
    episodes: int
    """Gezaehlte Episoden nach ADR 0057 -- die Grundgesamtheit."""
    trades: int
    without_trade: int
    """Episoden ohne vollstaendigen Trade. Kein Fehler: kein Verfall im
    Fenster, zu wenig Historie, oder die Reihe endet vor dem Verfall."""
    held: VariantMetrics | None
    managed: VariantMetrics | None
    confidence: BacktestConfidence
    assumptions: Mapping[str, str]


def summarize_variant(
    profits: Sequence[float],
    capitals: Sequence[float],
    outcomes: Sequence[TradeOutcome],
) -> VariantMetrics | None:
    """Kennzahlen aus den Einzelergebnissen, oder ``None`` ohne Trades."""
    if not profits:
        return None
    return VariantMetrics(
        trades=len(profits),
        win_rate=sum(1 for gewinn in profits if gewinn > 0.0) / len(profits),
        mean_profit=statistics.fmean(profits),
        median_profit=statistics.median(profits),
        total_profit=sum(profits),
        worst_profit=min(profits),
        mean_return_on_capital=statistics.fmean(
            gewinn / kapital
            for gewinn, kapital in zip(profits, capitals, strict=True)
        ),
        expired_worthless=sum(1 for o in outcomes if o is TradeOutcome.EXPIRED_WORTHLESS),
        assigned=sum(1 for o in outcomes if o is TradeOutcome.ASSIGNED),
        take_profits=sum(1 for o in outcomes if o is TradeOutcome.TAKE_PROFIT),
        stops=sum(1 for o in outcomes if o is TradeOutcome.STOPPED_OUT),
    )


def assumptions_of(params: OptionsBacktestParameters) -> Mapping[str, str]:
    """Was aus demselben Kurspfad eine andere Zahl macht.

    Oeffentlich, weil die Ausgabe sie auch dann braucht, wenn keine einzige
    Episode entstand -- ein leeres Ergebnis ohne die Annahmen, unter denen es
    entstand, ist nicht deutbar.
    """
    return MappingProxyType(
        {
            "version": OPTIONS_BACKTEST_VERSION,
            "kalender": HISTORICAL_CALENDAR,
            "strike_raster": ", ".join(
                f"<{grenze:g}: {schritt:g}" for grenze, schritt in DEFAULT_STRIKE_GRID
            )
            + ", sonst 5",
            "volatilitaetsfenster": f"{params.volatility_window} Handelstage",
            "volatilitaetsaufschlag": f"{params.volatility_uplift:.2f}",
            "zinssatz": f"{params.risk_free_rate:.4f}",
            "ausfuehrungsabschlag": f"{params.execution_haircut:.4f}",
            "gewinnmitnahme": f"{params.take_profit_fraction:.2f}",
            "rueckkauf": f"{params.stop_multiple:.1f}x",
            "ziel_delta": f"{params.target_delta:.2f}",
        }
    )


SIGNAL_BUCHSTABEN: Mapping[str, SignalType] = MappingProxyType(
    {
        "A": SignalType.RSI_CROSS,
        "B": SignalType.PRICE_EMA20_BREAKOUT,
        "C": SignalType.EMA5_EMA20_CROSS,
        "D": SignalType.RSI_OVERSOLD,
        "E": SignalType.NO_RECENT_EMA_DOWNCROSS,
    }
)
"""Die Kriterienbuchstaben der G1-Pruefvorlage (Abschnitte 2.1 bis 2.5).

Ausgeschrieben ist die laengste Kombination 84 Zeichen lang -- in einer
Tabelle mit acht weiteren Spalten muesste sie abgeschnitten werden, und zwei
verschiedene Kombinationen saehen dann gleich aus. Die Buchstaben sind
ohnehin die Sprache, in der die Pruefvorlage ueber die Kriterien redet.

**Explizit und nicht ueber die Enum-Reihenfolge**, obwohl sie heute
uebereinstimmen: Ein neuer Signaltyp bekaeme sonst stillschweigend keinen
Buchstaben und verschwaende aus jeder Kombination. Ein Test haelt die
Abdeckung fest.
"""


def kombinationskuerzel(kombination: SignalCombination) -> str:
    """Eine Signalkombination als Kriterienbuchstaben, etwa ``ABE``."""
    return "".join(
        buchstabe
        for buchstabe, signal in SIGNAL_BUCHSTABEN.items()
        if signal in kombination
    )


def compute_options_backtest_results(
    trades_by_combination: Mapping[SignalCombination, Sequence[OptionTrade | None]],
    *,
    options_params: OptionsBacktestParameters,
    backtest_params: BacktestParameters,
    required_crossing_signals: int,
) -> tuple[OptionsBacktestResult, ...]:
    """Kennzahlen je Signalkombination.

    ``trades_by_combination`` enthaelt je Episode einen Eintrag -- ``None``,
    wo kein Trade zustande kam. Die Zahl bleibt sichtbar: Eine Kombination
    mit zwanzig Episoden und drei Trades ist etwas anderes als eine mit drei
    Episoden und drei Trades, und beide haetten sonst dieselbe Zeile.

    Geliefert werden **alle** moeglichen Kombinationen, auch leere -- kein
    stillschweigendes Weglassen (Projektkonvention aus ``metrics.py``).
    """
    annahmen = assumptions_of(options_params)
    ergebnisse: list[OptionsBacktestResult] = []
    for kombination in qualifying_combinations(required_crossing_signals):
        eintraege = trades_by_combination.get(kombination, ())
        trades = [trade for trade in eintraege if trade is not None]
        kapitale = [trade.capital_at_risk for trade in trades]
        konfidenz = _classify(len(trades), backtest_params)
        belastbar = konfidenz is not BacktestConfidence.INSUFFICIENT_DATA
        ergebnisse.append(
            OptionsBacktestResult(
                signal_types=kombination,
                episodes=len(eintraege),
                trades=len(trades),
                without_trade=len(eintraege) - len(trades),
                held=(
                    summarize_variant(
                        [t.held_profit for t in trades],
                        kapitale,
                        [t.held_outcome for t in trades],
                    )
                    if belastbar
                    else None
                ),
                managed=(
                    summarize_variant(
                        [t.managed_profit for t in trades],
                        kapitale,
                        [t.managed_outcome for t in trades],
                    )
                    if belastbar
                    else None
                ),
                confidence=konfidenz,
                assumptions=annahmen,
            )
        )
    return tuple(ergebnisse)


def _classify(trades: int, params: BacktestParameters) -> BacktestConfidence:
    """Dieselben Schwellen wie die Aktienseite (``metrics._classify_confidence``).

    Unterhalb von ``minimum_sample_size`` bleiben die Kennzahlen ``None`` und
    nicht nur niedrig eingestuft -- eine Trefferquote aus vier Trades ist
    keine Trefferquote.
    """
    if trades < params.minimum_sample_size:
        return BacktestConfidence.INSUFFICIENT_DATA
    if trades < params.normal_confidence_sample_size:
        return BacktestConfidence.LOW_SAMPLE
    return BacktestConfidence.NORMAL
