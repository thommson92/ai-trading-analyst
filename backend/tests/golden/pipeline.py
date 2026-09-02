"""Die deterministische Kette, die der Golden Master einfriert.

Nachgebildet wird genau der Weg, den ein Lauf gegen den Bestand nimmt --
ohne Datenbank, ohne TWS, ohne Netz:

    native Bars
      -> aggregate_intraday_bars   (Kerzenbildung, Doc 10 Paragraph 6.2)
      -> compute_indicator_values  (RSI, RSI-MA, EMA5, EMA20 -- Gate G1)
      -> evaluate_candidate        (3-aus-5-Regel, Screener)
      -> compute_backtest_results  (Replay, Cooldown, Kennzahlen)

Was hier **nicht** nachgebildet wird, ist die Infrastruktur um die Kette
herum: Repositories, Anbieteradapter, Fehlerisolation. Die haben eigene
Tests. Der Golden Master bewacht das Verfahren, nicht die Verdrahtung.

Die Parameter stammen absichtlich nicht aus ``config/default.yaml``, sondern
stehen hier fest. Eine Konfigurationsaenderung soll den Golden Master
**nicht** brechen -- sonst schluege er bei jeder Parameterprobe an und
verloere seinen Wert. Anschlagen soll er, wenn sich die *Rechnung* aendert.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any
from uuid import UUID

from ai_trading_analyst.domain.backtesting import (
    BacktestParameters,
    BacktestResult,
    compute_backtest_results,
)
from ai_trading_analyst.domain.screening import (
    SIGNAL_RULE_VERSION,
    CandidateRuleParameters,
    CandleSeries,
    IndicatorParameters,
    IntradayBar,
    ScreeningResult,
    ScreeningStatus,
    SessionParameters,
    aggregate_intraday_bars,
    compute_indicator_values,
    evaluate_candidate,
)

DATA_DIR = Path(__file__).parent / "data"

NATIVE_BAR_MINUTES = 15

SESSION = SessionParameters(
    timezone="America/New_York",
    session_open=time(9, 30),
    session_minutes=390,
    timeframe_minutes=195,
    early_close=time(13, 0),
)

INDICATORS = IndicatorParameters(
    rsi_length=14,
    rsi_method="wilder",
    rsi_ma_length=14,
    rsi_ma_type="sma",
    fast_ema_length=5,
    slow_ema_length=20,
)

CANDIDATE_RULE = CandidateRuleParameters(
    required_signal_count=3,
    signal_lookback_previous_candles=5,
    warmup_candles=250,
)

BACKTEST = BacktestParameters(
    horizons=(5, 10, 20),
    cooldown_candles=5,
    minimum_sample_size=10,
    normal_confidence_sample_size=30,
    history_years=5,
)

STOCK_ID = UUID("9e1c0d54-0000-4000-8000-000000000001")
"""Feste Kennung -- eine zufaellige wanderte in jede aufgezeichnete Datei."""

EVALUATED_AT = datetime(2026, 8, 23, 20, 0, tzinfo=UTC)
"""Fester Auswertungszeitpunkt.

``compute_backtest_results`` schneidet die Historie auf
``history_years`` vor diesem Zeitpunkt zu. Mit der Uhr des Testlaufs waere
das Ergebnis vom Tag des Laufs abhaengig -- ein Golden Master, der von selbst
bricht, sobald die eingefrorenen Daten alt genug sind.
"""


@dataclass(frozen=True, slots=True)
class GoldenCase:
    """Ein eingefrorener Datensatz und die Dateien, die zu ihm gehoeren."""

    name: str

    @property
    def bars_path(self) -> Path:
        return DATA_DIR / f"{self.name}.bars.csv"

    @property
    def expected_path(self) -> Path:
        return DATA_DIR / f"{self.name}.expected.json"


def available_cases() -> tuple[GoldenCase, ...]:
    """Jede Bar-Datei im Datenverzeichnis ist ein Fall.

    Bewusst ueber das Verzeichnis und nicht ueber eine Liste im Code: Ein
    echter Datenausschnitt vom Server (``cli export-bars``) wird damit zu
    einem Testfall, sobald er abgelegt und einmal aufgezeichnet ist -- ohne
    Codeaenderung.
    """
    return tuple(
        GoldenCase(name=path.name.removesuffix(".bars.csv"))
        for path in sorted(DATA_DIR.glob("*.bars.csv"))
    )


def read_bars(path: Path) -> tuple[IntradayBar, ...]:
    """Liest die eingefrorenen Bars.

    Format: ``start,open,high,low,close,volume`` mit ISO-8601-Zeitstempel
    samt Zeitzone -- dasselbe, was ``cli export-bars`` schreibt. CSV, damit
    ein Unterschied im Diff sichtbar bleibt und die Datei sich mit
    gewoehnlichen Werkzeugen ansehen laesst.
    """
    zeilen = path.read_text(encoding="utf-8").splitlines()
    if not zeilen or zeilen[0] != "start,open,high,low,close,volume":
        raise ValueError(f"{path.name} hat keine erkennbare Kopfzeile")
    bars = []
    for zeile in zeilen[1:]:
        if not zeile.strip():
            continue
        start, *werte = zeile.split(",")
        zeitpunkt = datetime.fromisoformat(start)
        if zeitpunkt.tzinfo is None:
            raise ValueError(f"{path.name}: naiver Zeitstempel {start!r}")
        offen, hoch, tief, schluss, volumen = (float(wert) for wert in werte)
        bars.append(
            IntradayBar(
                start=zeitpunkt,
                open=offen,
                high=hoch,
                low=tief,
                close=schluss,
                volume=volumen,
            )
        )
    return tuple(bars)


def write_bars(path: Path, bars: Sequence[IntradayBar]) -> None:
    zeilen = ["start,open,high,low,close,volume"]
    zeilen.extend(
        f"{bar.start.isoformat()},{bar.open:.4f},{bar.high:.4f},"
        f"{bar.low:.4f},{bar.close:.4f},{bar.volume:.0f}"
        for bar in bars
    )
    path.write_text("\n".join(zeilen) + "\n", encoding="utf-8")


def build_series(bars: Sequence[IntradayBar]) -> CandleSeries:
    aggregiert = aggregate_intraday_bars(bars, NATIVE_BAR_MINUTES, SESSION)
    indikatoren = compute_indicator_values(
        [kerze.close for kerze in aggregiert.candles], INDICATORS
    )
    return CandleSeries(candles=aggregiert.candles, indicators=indikatoren)


def _round(wert: float | None) -> float | None:
    """Auf acht Stellen -- genau genug, um eine Verfahrensaenderung zu sehen.

    Ohne Rundung braechen die aufgezeichneten Zahlen an der letzten
    Binaerstelle, sobald sich die Reihenfolge einer Summe aendert, ohne dass
    sich das Verfahren geaendert haette. Acht Stellen liegen weit unter jeder
    fachlich bedeutsamen Abweichung und weit ueber dem Rauschen.
    """
    return None if wert is None else round(wert, 8)


def _screening_snapshot(series: CandleSeries) -> dict[str, Any]:
    """Der Screener an **jedem** auswertbaren Entscheidungspunkt.

    Nicht nur an der letzten Kerze: Eine Verfahrensaenderung, die nur
    aeltere Fenster trifft, bliebe sonst unsichtbar. Aufgezeichnet wird die
    Zusammenfassung ueber alle Punkte plus jeder einzelne Kandidat -- das
    haelt die Datei lesbar und faengt trotzdem jede Verschiebung.
    """
    nach_status: dict[str, int] = {}
    kandidaten: list[dict[str, Any]] = []
    for t in range(len(series)):
        ergebnis: ScreeningResult = evaluate_candidate(series, t, CANDIDATE_RULE)
        nach_status[ergebnis.status.value] = nach_status.get(ergebnis.status.value, 0) + 1
        if ergebnis.status is not ScreeningStatus.CANDIDATE:
            continue
        kandidaten.append(
            {
                "candle_index": t,
                "timestamp": series.candle(t).timestamp.isoformat(),
                "fired_signal_types": sorted(
                    signal.value for signal in ergebnis.fired_signal_types
                ),
                # Listen, keine Tupel: Die Aufzeichnung geht durch JSON, und
                # ein Tupel kaeme daraus als Liste zurueck -- der Vergleich
                # schluege bei jedem Lauf fehl, ohne dass sich etwas
                # geaendert haette.
                "signal_events": sorted(
                    [ereignis.signal_type.value, ereignis.candle_index]
                    for ereignis in ergebnis.signal_events
                ),
            }
        )
    return {"status_counts": nach_status, "candidates": kandidaten}


def _horizon_snapshot(metrics: Any) -> dict[str, Any]:
    return {
        "horizon": metrics.horizon,
        "raw_event_count": metrics.raw_event_count,
        "deduplicated_event_count": metrics.deduplicated_event_count,
        "hit_rate": _round(metrics.hit_rate),
        "mean_return": _round(metrics.mean_return),
        "median_return": _round(metrics.median_return),
        "max_loss": _round(metrics.max_loss),
        "drawdown": _round(metrics.drawdown),
        "held_above_entry_rate": _round(metrics.held_above_entry_rate),
        "confidence": metrics.confidence.value,
    }


def _backtest_snapshot(results: Sequence[BacktestResult]) -> list[dict[str, Any]]:
    return [
        {
            "signal_types": sorted(signal.value for signal in ergebnis.signal_types),
            "history_start": ergebnis.history_start.isoformat(),
            "history_end": ergebnis.history_end.isoformat(),
            "horizons": [_horizon_snapshot(horizont) for horizont in ergebnis.horizons],
        }
        for ergebnis in results
    ]


def compute_snapshot(bars: Sequence[IntradayBar]) -> dict[str, Any]:
    """Das vollstaendige Ergebnis der Kette, als vergleichbare Struktur."""
    series = build_series(bars)
    ergebnisse = compute_backtest_results(
        series,
        stock_id=STOCK_ID,
        candidate_params=CANDIDATE_RULE,
        backtest_params=BACKTEST,
        signal_rule_version=SIGNAL_RULE_VERSION,
        evaluated_at=EVALUATED_AT,
    )
    return {
        "signal_rule_version": SIGNAL_RULE_VERSION,
        "bars": len(bars),
        "candles": len(series),
        "first_candle": series.candle(0).timestamp.isoformat(),
        "last_candle": series.candle(len(series) - 1).timestamp.isoformat(),
        "indicators_at_last_candle": {
            "rsi": _round(series.indicator(len(series) - 1).rsi),
            "rsi_ma": _round(series.indicator(len(series) - 1).rsi_ma),
            "ema5": _round(series.indicator(len(series) - 1).ema5),
            "ema20": _round(series.indicator(len(series) - 1).ema20),
        },
        "screening": _screening_snapshot(series),
        "backtest": _backtest_snapshot(ergebnisse),
    }


def read_expected(path: Path) -> dict[str, Any]:
    geladen: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return geladen


def write_expected(path: Path, snapshot: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
