from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

EXCHANGE_TZ = ZoneInfo("America/New_York")
SESSION_OPEN = time(9, 30)
BUCKET_MINUTES = 195


class TimeframeError(ValueError):
    pass


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class AggregatedCandle:
    session_date: date
    bucket_index: int
    start: datetime
    end: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    bar_count: int
    is_complete: bool


@dataclass(frozen=True)
class AggregationResult:
    candles: list[AggregatedCandle]
    bars_outside_session: list[Bar]


def aggregate_to_195_minutes(bars: list[Bar], native_bar_minutes: int) -> AggregationResult:
    if native_bar_minutes <= 0:
        raise TimeframeError("native_bar_minutes muss positiv sein")
    if BUCKET_MINUTES % native_bar_minutes != 0:
        raise TimeframeError(
            f"195 Minuten sind nicht ohne Rest durch {native_bar_minutes} Minuten teilbar -- "
            "diese native Bar-Groesse eignet sich nicht fuer eine saubere Aggregation."
        )
    expected_bars_per_candle = BUCKET_MINUTES // native_bar_minutes

    buckets: dict[tuple[date, int], list[Bar]] = {}
    outside: list[Bar] = []

    for bar in sorted(bars, key=lambda b: b.timestamp):
        if bar.timestamp.tzinfo is None:
            raise TimeframeError(
                f"Bar-Zeitstempel {bar.timestamp!r} ist naiv (ohne Zeitzone) -- nicht erlaubt."
            )
        local_time = bar.timestamp.astimezone(EXCHANGE_TZ)
        session_start = datetime.combine(local_time.date(), SESSION_OPEN, tzinfo=EXCHANGE_TZ)
        minutes_since_open = (local_time - session_start).total_seconds() / 60
        if minutes_since_open < 0:
            outside.append(bar)
            continue
        bucket_index = int(minutes_since_open // BUCKET_MINUTES)
        buckets.setdefault((local_time.date(), bucket_index), []).append(bar)

    candles: list[AggregatedCandle] = []
    for (session_date, bucket_index), bucket_bars in sorted(buckets.items()):
        bucket_bars.sort(key=lambda b: b.timestamp)
        bucket_start = datetime.combine(session_date, SESSION_OPEN, tzinfo=EXCHANGE_TZ)
        candle_start = bucket_start + timedelta(minutes=bucket_index * BUCKET_MINUTES)
        candles.append(
            AggregatedCandle(
                session_date=session_date,
                bucket_index=bucket_index,
                start=candle_start,
                end=candle_start + timedelta(minutes=BUCKET_MINUTES),
                open=bucket_bars[0].open,
                high=max(b.high for b in bucket_bars),
                low=min(b.low for b in bucket_bars),
                close=bucket_bars[-1].close,
                volume=sum(b.volume for b in bucket_bars),
                bar_count=len(bucket_bars),
                is_complete=len(bucket_bars) == expected_bars_per_candle,
            )
        )

    return AggregationResult(candles=candles, bars_outside_session=outside)
