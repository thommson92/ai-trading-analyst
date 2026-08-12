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
from enum import StrEnum
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


class IncompleteReason(StrEnum):
    """Warum ein Zeitfenster keine vollstaendige Kerze ergeben hat.

    Von aussen sehen die drei Faelle gleich aus -- es fehlen Bars --, fachlich
    sind sie gegensaetzlich: zwei davon sind unbedenklich, der dritte macht die
    ganze Reihe unbrauchbar.
    """

    SESSION_ENDED = "session_ended"
    """Die Sitzung endete in diesem Fenster. Entweder ein **verkuerzter
    Handelstag** (der 28.11.2025 nach Thanksgiving schloss um 13:00 statt
    16:00, die zweite Kerze bekam genau einen Bar) oder die **laufende Kerze**
    am Ende der Reihe. Es fehlt nichts, es hat nur nicht mehr Handel
    gegeben."""

    SESSION_STARTED_LATE = "session_started_late"
    """Der Handel begann an diesem Tag erst mitten im Fenster und lief dann bis
    zum Fensterende durch. Typisch am **ersten Handelstag nach einem
    Boersengang** (die Eroeffnungsauktion findet Stunden nach 09:30 statt) und
    nach einer **Eroeffnungsunterbrechung**. Auch hier fehlt nichts: Vorher gab
    es diesen Kurs nicht."""

    DATA_GAP = "data_gap"
    """Innerhalb eines gehandelten Zeitraums fehlen Bars. Eine echte
    Datenluecke."""


@dataclass(frozen=True, slots=True)
class IncompleteCandle:
    """Ein Zeitfenster, in dem nicht alle erwarteten Bars vorlagen.

    Unterschieden wird ohne Boersenkalender, allein an der Lage der
    vorhandenen Bars im Fenster: Sie muessen luecklos aufeinanderfolgen und
    entweder am Fensteranfang beginnen (dann endete die Sitzung dort) oder am
    Fensterende schliessen (dann begann der Handel spaeter). Alles andere ist
    eine Luecke.

    Was diese Pruefung nicht erkennen kann, ist ein **vollstaendig fehlender
    Handelstag** -- dafuer braeuchte es einen Kalender.
    """

    timestamp: datetime
    daily_candle_index: int
    received_bars: int
    expected_bars: int
    reason: IncompleteReason
    first_missing_bar: datetime
    """Beginn des ersten fehlenden nativen Bars -- ohne diese Angabe laesst
    sich aus einem Protokoll nicht erkennen, ob der Handel spaet begann oder
    ob mitten im Fenster etwas fehlt."""


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


def _expected_bar_starts(
    candle_start: datetime, native_bar_minutes: int, expected_bars: int
) -> list[datetime]:
    return [
        candle_start + timedelta(minutes=native_bar_minutes * offset)
        for offset in range(expected_bars)
    ]


def _classify(
    buckets: dict[tuple[datetime, int], list[IntradayBar]],
    session_start: datetime,
    bucket_index: int,
    bucket_bars: list[IntradayBar],
    expected_starts: list[datetime],
    native_bar_minutes: int,
) -> IncompleteReason:
    """Fehlte hier Handel oder fehlen hier Daten?

    Grundbedingung fuer beide unbedenklichen Faelle ist, dass die vorhandenen
    Bars **luecklos aufeinanderfolgen**: Ein Loch zwischen zwei vorhandenen
    Bars laesst sich durch keinen Sitzungsverlauf erklaeren. Dazu muss der
    Block an einem der beiden Fensterraender anliegen, und auf der anderen
    Seite darf es an diesem Tag keinen Handel gegeben haben.
    """
    lueckenlos = all(
        bar.start == bucket_bars[0].start + timedelta(minutes=native_bar_minutes * offset)
        for offset, bar in enumerate(bucket_bars)
    )
    if not lueckenlos:
        return IncompleteReason.DATA_GAP

    indizes_des_tages = [index for start, index in buckets if start == session_start]
    if bucket_bars[0].start == expected_starts[0] and not any(
        index > bucket_index for index in indizes_des_tages
    ):
        return IncompleteReason.SESSION_ENDED
    if bucket_bars[-1].start == expected_starts[-1] and not any(
        index < bucket_index for index in indizes_des_tages
    ):
        return IncompleteReason.SESSION_STARTED_LATE
    return IncompleteReason.DATA_GAP


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
        bucket_bars.sort(key=lambda bar: bar.start)
        if len(bucket_bars) != expected_bars:
            expected_starts = _expected_bar_starts(
                timestamp, native_bar_minutes, expected_bars
            )
            vorhanden = {bar.start for bar in bucket_bars}
            incomplete.append(
                IncompleteCandle(
                    timestamp=timestamp,
                    daily_candle_index=bucket_index + 1,
                    received_bars=len(bucket_bars),
                    expected_bars=expected_bars,
                    reason=_classify(
                        buckets,
                        session_start,
                        bucket_index,
                        bucket_bars,
                        expected_starts,
                        native_bar_minutes,
                    ),
                    # Es liegen weniger Bars vor als Plaetze im Fenster, also
                    # bleibt mindestens einer davon unbesetzt.
                    first_missing_bar=next(
                        start for start in expected_starts if start not in vorhanden
                    ),
                )
            )
            continue
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
