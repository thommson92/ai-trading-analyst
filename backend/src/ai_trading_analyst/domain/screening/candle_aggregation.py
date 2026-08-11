"""Aufbau der 195-Minuten-Kerzen aus nativen Intraday-Bars.

Kein Anbieter liefert 195-Minuten-Kerzen fertig. Sie entstehen aus kleineren
nativen Bars (bei IBKR: 15 Minuten) und muessen deshalb selbst gebildet
werden. Die Regeln dafuer sind fachlich, nicht anbieterspezifisch, und liegen
darum im Domain Layer:

* Nur die **regulaere US-Sitzung** (Doc 10; G1-Pruefvorlage Abschnitt 1.1).
  Extended Hours fliessen nie ein.
* 390 Sitzungsminuten ergeben genau zwei Kerzen: 09:30--12:45 und
  12:45--16:00 Ortszeit der Boerse.
* **Nur vollstaendig abgeschlossene Kerzen.** Eine Kerze gilt genau dann als
  abgeschlossen, wenn alle erwarteten nativen Bars vorliegen. Eine laufende
  Kerze fliesst nie in ein Signal ein (Doc 10). Dieselbe Regel greift an einem
  verkuerzten Handelstag: die zweite Kerze bleibt dort unvollstaendig.
* **Unvollstaendige Kerzen werden gemeldet, nicht verschwiegen.** Sie stehen
  nicht in ``candles``, aber in ``incomplete`` -- denn die beiden Faelle sind
  fachlich verschieden: Am Ende der Reihe ist eine unvollstaendige Kerze der
  Normalfall (die laufende Kerze), mitten in der Reihe ist sie eine
  Datenluecke. Wuerde sie stillschweigend entfallen, waeren die verbleibenden
  Kerzen nicht mehr zusammenhaengend und jede darauf berechnete
  Indikatorreihe waere falsch, ohne dass es irgendwo auffiele
  (G1-Pruefvorlage, Abschnitt 1.5: eine Luecke wird nie stillschweigend
  behandelt). Ueber den Umgang damit entscheidet der Aufrufer.

Zeitstempel-Konvention: sowohl die eingehenden Bars als auch die erzeugten
Kerzen sind mit ihrem **Beginn** datiert (die 09:30-Kerze traegt 09:30, nicht
12:45). Das entspricht der Konvention der IBKR-Historiendaten und damit dem
Datenstand, aus dem aggregiert wird.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .values import Candle


class CandleAggregationError(ValueError):
    """Die Kerzenbildung ist mit den uebergebenen Daten nicht durchfuehrbar."""


@dataclass(frozen=True, slots=True)
class IntradayBar:
    """Ein nativer Bar des Anbieters, datiert auf seinen Beginn."""

    start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class IncompleteCandle:
    """Ein Zeitfenster, in dem nicht alle erwarteten Bars vorlagen."""

    timestamp: datetime
    daily_candle_index: int
    received_bars: int
    expected_bars: int


@dataclass(frozen=True, slots=True)
class AggregationResult:
    """Abgeschlossene Kerzen und die dabei uebergangenen Zeitfenster."""

    candles: tuple[Candle, ...]
    incomplete: tuple[IncompleteCandle, ...]


@dataclass(frozen=True, slots=True)
class SessionParameters:
    """Zuschnitt der Handelssitzung -- aus ``MarketConfig`` aufgebaut."""

    timezone: str
    session_open: time
    session_minutes: int
    timeframe_minutes: int

    def __post_init__(self) -> None:
        if self.session_minutes % self.timeframe_minutes != 0:
            raise CandleAggregationError(
                f"session_minutes ({self.session_minutes}) muss ein Vielfaches von "
                f"timeframe_minutes ({self.timeframe_minutes}) sein"
            )


def aggregate_intraday_bars(
    bars: Sequence[IntradayBar], native_bar_minutes: int, parameters: SessionParameters
) -> AggregationResult:
    """Bildet aus nativen Bars die Kerzen der regulaeren Sitzung.

    Bars ausserhalb der regulaeren Sitzung werden verworfen -- auch dann, wenn
    der Anbieter sie trotz angeforderter Beschraenkung mitliefert.

    Zeitfenster, in denen Bars fehlen, erscheinen nicht in ``candles``, aber
    vollstaendig in ``incomplete``.

    Raises:
        CandleAggregationError: bei einer nicht teilbaren Bar-Groesse, einem
            naiven Zeitstempel oder einem doppelt gelieferten Bar. Alle drei
            wuerden sonst still zu falschen Kerzen fuehren.
    """
    if native_bar_minutes <= 0:
        raise CandleAggregationError(
            f"native_bar_minutes muss groesser als 0 sein, ist aber {native_bar_minutes}"
        )
    if parameters.timeframe_minutes % native_bar_minutes != 0:
        raise CandleAggregationError(
            f"{parameters.timeframe_minutes} Minuten sind nicht ohne Rest durch "
            f"{native_bar_minutes} Minuten teilbar -- aus dieser Bar-Groesse laesst sich "
            "keine saubere Kerze bilden"
        )

    exchange_timezone = ZoneInfo(parameters.timezone)
    expected_bars = parameters.timeframe_minutes // native_bar_minutes

    buckets: dict[tuple[datetime, int], list[IntradayBar]] = {}
    seen: set[datetime] = set()

    for bar in bars:
        if bar.start.tzinfo is None:
            raise CandleAggregationError(
                f"Bar-Zeitstempel {bar.start!r} hat keine Zeitzone -- naive Zeitstempel "
                "sind unzulaessig (Doc 10)"
            )
        if bar.start in seen:
            raise CandleAggregationError(
                f"Der Bar mit Zeitstempel {bar.start.isoformat()} wurde doppelt geliefert"
            )
        seen.add(bar.start)

        local_start = bar.start.astimezone(exchange_timezone)
        session_start = datetime.combine(
            local_start.date(), parameters.session_open, tzinfo=exchange_timezone
        )
        minutes_into_session = (local_start - session_start).total_seconds() / 60
        if not 0 <= minutes_into_session < parameters.session_minutes:
            continue

        bucket_index = int(minutes_into_session // parameters.timeframe_minutes)
        buckets.setdefault((session_start, bucket_index), []).append(bar)

    candles: list[Candle] = []
    incomplete: list[IncompleteCandle] = []
    for (session_start, bucket_index), bucket_bars in sorted(buckets.items()):
        timestamp = session_start + timedelta(
            minutes=bucket_index * parameters.timeframe_minutes
        )
        if len(bucket_bars) != expected_bars:
            incomplete.append(
                IncompleteCandle(
                    timestamp=timestamp,
                    daily_candle_index=bucket_index + 1,
                    received_bars=len(bucket_bars),
                    expected_bars=expected_bars,
                )
            )
            continue
        bucket_bars.sort(key=lambda bar: bar.start)
        candles.append(
            Candle(
                timestamp=timestamp,
                daily_candle_index=bucket_index + 1,
                open=bucket_bars[0].open,
                high=max(bar.high for bar in bucket_bars),
                low=min(bar.low for bar in bucket_bars),
                close=bucket_bars[-1].close,
                volume=sum(bar.volume for bar in bucket_bars),
            )
        )

    return AggregationResult(candles=tuple(candles), incomplete=tuple(incomplete))
