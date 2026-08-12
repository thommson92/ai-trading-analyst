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
from dataclasses import dataclass, replace
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
    Handelstag** -- der Handel endete dann genau zur konfigurierten
    Schlusszeit verkuerzter Tage (US-Aktienmaerkte: 13:00 Ortszeit, so am
    28.11.2025 nach Thanksgiving) -- oder die **laufende Kerze** am letzten Tag
    der Reihe. Es fehlt nichts, es hat nur nicht mehr Handel gegeben."""

    SESSION_STARTED_LATE = "session_started_late"
    """Der Handel begann an diesem Tag erst spaeter und lief dann bis zum
    regulaeren Schluss durch. Typisch am **ersten Handelstag nach einem
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
    vorhandenen Bars im Tagesverlauf -- siehe ``_classify``.

    Was diese Pruefung nicht erkennen kann, ist ein **vollstaendig fehlender
    Handelstag**: Liefert der Anbieter zu einem Datum gar keinen Bar, gibt es
    nichts, woran sich der fehlende Tag festmachen liesse. Dafuer braeuchte es
    einen Boersenkalender. Innerhalb eines Tages, zu dem ueberhaupt Daten
    vorliegen, bleibt dagegen kein fehlendes Fenster unbemerkt.
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
    early_close: time
    """Schlusszeit an verkuerzten Handelstagen (US-Aktienmaerkte: 13:00)."""

    def __post_init__(self) -> None:
        if self.session_minutes % self.timeframe_minutes != 0:
            raise CandleAggregationError(
                f"session_minutes ({self.session_minutes}) muss ein Vielfaches von "
                f"timeframe_minutes ({self.timeframe_minutes}) sein"
            )

    @property
    def candles_per_day(self) -> int:
        return self.session_minutes // self.timeframe_minutes


def _expected_bar_starts(
    candle_start: datetime, native_bar_minutes: int, expected_bars: int
) -> list[datetime]:
    return [
        candle_start + timedelta(minutes=native_bar_minutes * offset)
        for offset in range(expected_bars)
    ]


@dataclass(frozen=True, slots=True)
class _TradingDay:
    """Was an einem Handelstag tatsaechlich geliefert wurde.

    Alle Zeitstempel in der Zeitzone der Boerse -- die Schlusszeit verkuerzter
    Tage ist eine Ortszeit und nur dort vergleichbar.
    """

    erster_bar: datetime
    letzter_bar_ende: datetime
    hat_vollstaendige_kerze: bool
    ist_letzter_tag_der_reihe: bool


def _trading_days(
    buckets: dict[tuple[datetime, int], list[IntradayBar]],
    expected_bars: int,
    native_bar_minutes: int,
) -> dict[datetime, _TradingDay]:
    """Fasst je Handelstag zusammen, was der Anbieter geliefert hat."""
    tage: dict[datetime, list[list[IntradayBar]]] = {}
    for (session_start, _), bucket_bars in buckets.items():
        tage.setdefault(session_start, []).append(bucket_bars)

    letzter_tag = max(tage)
    ergebnis: dict[datetime, _TradingDay] = {}
    for session_start, tagesfenster in tage.items():
        alle_bars = [bar for fenster in tagesfenster for bar in fenster]
        ergebnis[session_start] = _TradingDay(
            erster_bar=min(bar.start for bar in alle_bars),
            letzter_bar_ende=max(bar.start for bar in alle_bars)
            + timedelta(minutes=native_bar_minutes),
            hat_vollstaendige_kerze=any(
                len(fenster) == expected_bars for fenster in tagesfenster
            ),
            ist_letzter_tag_der_reihe=session_start == letzter_tag,
        )
    return ergebnis


def _classify(
    bucket_bars: list[IntradayBar],
    expected_starts: list[datetime],
    native_bar_minutes: int,
    tag: _TradingDay,
    parameters: SessionParameters,
) -> IncompleteReason:
    """Fehlte hier Handel oder fehlen hier Daten?

    Beide sehen im Datenstrom gleich aus, deshalb entscheidet der
    **Tagesverlauf**, nicht das einzelne Fenster:

    1. Die vorhandenen Bars muessen luecklos aufeinanderfolgen und auf dem
       Zeitraster liegen. Ein Loch zwischen zwei vorhandenen Bars laesst sich
       durch keinen Sitzungsverlauf erklaeren.
    2. Liegt das Fenster am **Ende** der Tagesdaten, ist es nur dann
       unbedenklich, wenn der Handel zur Schlusszeit verkuerzter Tage endete
       (US-Maerkte: 13:00) oder es der letzte Tag der Reihe ist -- dann ist es
       die laufende Kerze. Ein Feed, der um 10:45 abreisst, sieht genauso aus,
       endet aber zu keiner boerslichen Schlusszeit.
    3. Liegt das Fenster am **Anfang** der Tagesdaten, ist es nur dann
       unbedenklich, wenn der Tag danach mindestens eine vollstaendige Kerze
       hergibt. Ein Tag, der ueberhaupt keine vollstaendige Kerze liefert, ist
       kein spaeter Handelsbeginn, sondern ein Datenausfall.

    Alles andere ist eine Luecke.
    """
    vorhanden = [bar.start for bar in bucket_bars]
    lueckenlos = all(
        start == vorhanden[0] + timedelta(minutes=native_bar_minutes * offset)
        for offset, start in enumerate(vorhanden)
    )
    if not lueckenlos:
        return IncompleteReason.DATA_GAP

    fensterende = expected_starts[-1] + timedelta(minutes=native_bar_minutes)
    # Das Fenster schliesst die Tagesdaten ab: Es ist von seinem Beginn an
    # gefuellt (oder leer) und danach kam an diesem Tag nichts mehr.
    schliesst_den_tag_ab = tag.letzter_bar_ende <= fensterende and (
        not vorhanden or vorhanden[0] == expected_starts[0]
    )
    # Das Fenster eroeffnet die Tagesdaten: Es ist bis zu seinem Ende gefuellt
    # (oder leer) und davor gab es an diesem Tag nichts.
    eroeffnet_den_tag = tag.erster_bar >= expected_starts[0] and (
        not vorhanden or vorhanden[-1] == expected_starts[-1]
    )

    if schliesst_den_tag_ab and (
        tag.ist_letzter_tag_der_reihe
        or tag.letzter_bar_ende.time() == parameters.early_close
    ):
        return IncompleteReason.SESSION_ENDED
    if eroeffnet_den_tag and tag.hat_vollstaendige_kerze:
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
        if minutes_into_session % native_bar_minutes != 0:
            # Ein Bar zwischen den Rasterplaetzen gehoert in kein Fenster. Er
            # wuerde die Anzahl stimmen lassen und trotzdem eine Kerze mit
            # falschem Eroeffnungskurs ergeben.
            raise CandleAggregationError(
                f"Der Bar um {local_start.isoformat()} liegt nicht auf dem "
                f"{native_bar_minutes}-Minuten-Raster der Sitzung"
            )

        bucket_index = int(minutes_into_session // parameters.timeframe_minutes)
        # Ab hier in Boersenzeit rechnen: Die Schlusszeit verkuerzter Tage ist
        # eine Ortszeit, und der Anbieter darf seine Bars in jeder Zeitzone
        # liefern.
        buckets.setdefault((session_start, bucket_index), []).append(
            replace(bar, start=local_start)
        )

    # Fenster ohne einen einzigen Bar sollen ebenfalls auffallen. Sie entstehen
    # nicht beim Einsortieren -- und blieben sonst als einzige Luecke
    # unsichtbar, obwohl fuer den Tag Daten vorliegen.
    for session_start in {tag for tag, _ in buckets}:
        for bucket_index in range(parameters.candles_per_day):
            buckets.setdefault((session_start, bucket_index), [])

    tage = _trading_days(buckets, expected_bars, native_bar_minutes)

    candles: list[Candle] = []
    incomplete: list[IncompleteCandle] = []
    for (session_start, bucket_index), bucket_bars in sorted(buckets.items()):
        timestamp = session_start + timedelta(
            minutes=bucket_index * parameters.timeframe_minutes
        )
        bucket_bars.sort(key=lambda bar: bar.start)
        expected_starts = _expected_bar_starts(timestamp, native_bar_minutes, expected_bars)
        vorhanden = {bar.start for bar in bucket_bars}
        if vorhanden != set(expected_starts):
            incomplete.append(
                IncompleteCandle(
                    timestamp=timestamp,
                    daily_candle_index=bucket_index + 1,
                    # Nur die Bars, die auf einem Rasterplatz sitzen -- ein
                    # Bar um 09:37 fuellt keinen davon.
                    received_bars=len(vorhanden & set(expected_starts)),
                    expected_bars=expected_bars,
                    reason=_classify(
                        bucket_bars,
                        expected_starts,
                        native_bar_minutes,
                        tage[session_start],
                        parameters,
                    ),
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
