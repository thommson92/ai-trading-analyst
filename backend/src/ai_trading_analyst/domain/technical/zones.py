"""Unterstuetzungs- und Widerstandszonen aus Swing-Punkten (ADR 0025).

Verfahren in drei Schritten, jeder einzeln nachpruefbar -- Doc 10, Paragraph
6.8 verlangt ausdruecklich, dass die Berechnung nachvollziehbar ist:

1. **Swing-Punkte** -- lokale Hoch- und Tiefpunkte, die von ``pivot_reach``
   Kerzen auf beiden Seiten nicht uebertroffen werden.
2. **Zusammenfassen** -- benachbarte Swing-Punkte werden zu einer Preiszone
   gebuendelt, solange sie nahe genug an deren Mittelwert liegen.
3. **Beruehrungen zaehlen** -- wie oft der Kurs die entstandene Zone
   spaeter getestet hat.

Hoch- und Tiefpunkte werden dabei **gemeinsam** gebuendelt und nicht getrennt.
Eine Preisregion, die erst als Widerstand gedient hat und nach dem Durchbruch
als Unterstuetzung traegt, ist dieselbe Region -- getrennte Buendelung wuerde
sie in zwei halb belegte Zonen zerlegen und gerade den Fall verschlechtern,
der am aussagekraeftigsten ist.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from ai_trading_analyst.domain.screening import Candle

from .values import (
    PriceZone,
    SwingPoint,
    TechnicalAnalysisParameters,
    ZoneKind,
    ZoneStrength,
)


def find_swing_points(
    candles: Sequence[Candle], start: int, end: int, pivot_reach: int
) -> tuple[SwingPoint, ...]:
    """Bestaetigte lokale Wendepunkte in ``candles[start:end]``.

    ``end`` ist ausschliesslich. Die Indizes der Rueckgabe beziehen sich auf
    ``candles`` als Ganzes, nicht auf den Ausschnitt.

    Ein Wendepunkt braucht ``pivot_reach`` Kerzen auf **beiden** Seiten. Die
    juengsten ``pivot_reach`` Kerzen des Ausschnitts koennen deshalb keinen
    bilden: Ob das gestrige Hoch ein Wendepunkt war, entscheidet sich erst,
    wenn der Kurs sich davon entfernt hat. Ein Verfahren, das den letzten
    Balken schon als Hochpunkt fuehrt, meldet auf jedem neuen Hoch eine neue
    Widerstandszone.

    Bei mehreren gleich hohen Kerzen nebeneinander (einem Plateau) wird
    ausschliesslich die **aelteste** zum Wendepunkt: Nach links wird echt
    groesser verlangt, nach rechts groesser oder gleich. Ohne diese
    Unterscheidung ergaebe jedes Plateau so viele Wendepunkte, wie es Kerzen
    breit ist, und wuerde die Zone allein dadurch staerker erscheinen lassen.
    """
    points: list[SwingPoint] = []
    for index in range(max(start + pivot_reach, pivot_reach), min(end, len(candles)) - pivot_reach):
        candle = candles[index]
        left = candles[index - pivot_reach : index]
        right = candles[index + 1 : index + 1 + pivot_reach]

        if all(candle.high > other.high for other in left) and all(
            candle.high >= other.high for other in right
        ):
            points.append(
                SwingPoint(
                    index=index, timestamp=candle.timestamp, price=candle.high, is_high=True
                )
            )
        if all(candle.low < other.low for other in left) and all(
            candle.low <= other.low for other in right
        ):
            points.append(
                SwingPoint(
                    index=index, timestamp=candle.timestamp, price=candle.low, is_high=False
                )
            )
    return tuple(points)


def _cluster_by_price(
    points: Sequence[SwingPoint], tolerance_pct: float
) -> list[list[SwingPoint]]:
    """Buendelt nach Preisnaehe: aufsteigend sortiert, dann fortlaufend gefuellt.

    Ein Punkt kommt zum laufenden Buendel, solange er nicht weiter als
    ``tolerance_pct`` vom bisherigen Mittelwert des Buendels entfernt ist --
    bewusst vom Mittelwert und nicht vom jeweiligen Vorgaenger: Sonst reiht
    eine dichte Folge knapp benachbarter Punkte sich unbegrenzt aneinander
    und ergibt eine Zone ueber die halbe Kursspanne.
    """
    if not points:
        return []

    ordered = sorted(points, key=lambda point: (point.price, point.timestamp, point.is_high))
    clusters: list[list[SwingPoint]] = [[ordered[0]]]
    running_sum = ordered[0].price

    for point in ordered[1:]:
        mean = running_sum / len(clusters[-1])
        if abs(point.price - mean) <= mean * tolerance_pct:
            clusters[-1].append(point)
            running_sum += point.price
        else:
            clusters.append([point])
            running_sum = point.price
    return clusters


def _zone_bounds(cluster: Sequence[SwingPoint], tolerance_pct: float) -> tuple[float, float]:
    """Grenzen einer Zone: das Toleranzband um den Mittelwert des Buendels.

    Nicht die Spanne der Punkte selbst: Ein Buendel aus einem einzigen Punkt
    haette dann die Breite null, und die Zahl seiner Beruehrungen waere nicht
    mit der einer breiteren Zone vergleichbar -- die Staerke haenge dann an
    der Bandbreite statt am Verhalten des Kurses.

    Der Vergleich mit den tatsaechlichen Punkten bleibt trotzdem stehen: Weil
    das Buendel nach dem Mittelwert *waehrend* des Fuellens gebildet wurde,
    kann ein frueh aufgenommener Punkt am Ende knapp ausserhalb des Bandes um
    den *endgueltigen* Mittelwert liegen. Eine Zone, die einen ihrer eigenen
    Punkte nicht enthaelt, waere nicht erklaerbar.
    """
    mean = sum(point.price for point in cluster) / len(cluster)
    lower = min(mean * (1 - tolerance_pct), min(point.price for point in cluster))
    upper = max(mean * (1 + tolerance_pct), max(point.price for point in cluster))
    return lower, upper


def _count_touches(
    candles: Sequence[Candle], start: int, end: int, lower: float, upper: float
) -> tuple[int, datetime | None]:
    """Getrennte Beruehrungen der Zone und Zeitpunkt der juengsten.

    Eine Kerze beruehrt die Zone, wenn ihre Spanne sie schneidet.
    Aufeinanderfolgende Kerzen innerhalb der Zone zaehlen zusammen als
    **eine** Beruehrung -- sonst waere eine mehrwoechige Seitwaertsphase in
    der Zone ein Dutzend Tests, und die Staerke einer Zone haenge daran, wie
    lange der Kurs in ihr feststeckte, statt daran, wie oft er an ihr
    abgeprallt ist.
    """
    touches = 0
    inside_before = False
    last_inside: datetime | None = None

    for index in range(start, min(end, len(candles))):
        candle = candles[index]
        inside = candle.low <= upper and candle.high >= lower
        if inside:
            if not inside_before:
                touches += 1
            last_inside = candle.timestamp
        inside_before = inside
    return touches, last_inside


def _classify(lower: float, upper: float, close: float) -> tuple[ZoneKind, float]:
    if upper < close:
        return ZoneKind.SUPPORT, (close - upper) / close
    if lower > close:
        return ZoneKind.RESISTANCE, (lower - close) / close
    return ZoneKind.PRICE_INSIDE, 0.0


def _strength(touch_count: int, params: TechnicalAnalysisParameters) -> ZoneStrength:
    if touch_count >= params.strong_touch_count:
        return ZoneStrength.STRONG
    if touch_count >= params.moderate_touch_count:
        return ZoneStrength.MODERATE
    return ZoneStrength.WEAK


def _select(zones: Sequence[PriceZone], max_per_side: int) -> tuple[PriceZone, ...]:
    """Behaelt je Seite die ``max_per_side`` naechstgelegenen Zonen.

    Zonen, in denen der Kurs gerade liegt, bleiben immer erhalten: Es gibt
    hoechstens sehr wenige davon, und sie sind fuer die Einstiegsfrage die
    unmittelbar wichtigsten.
    """
    by_distance = sorted(zones, key=lambda zone: (zone.distance_pct, zone.lower))
    kept: list[PriceZone] = []
    per_side = {ZoneKind.SUPPORT: 0, ZoneKind.RESISTANCE: 0}

    for zone in by_distance:
        if zone.kind is ZoneKind.PRICE_INSIDE:
            kept.append(zone)
            continue
        if per_side[zone.kind] < max_per_side:
            per_side[zone.kind] += 1
            kept.append(zone)
    return tuple(kept)


def build_zones(
    candles: Sequence[Candle],
    start: int,
    end: int,
    close: float,
    params: TechnicalAnalysisParameters,
) -> tuple[PriceZone, ...]:
    """Zonen aus ``candles[start:end]``, bezogen auf den Kurs ``close``.

    Ergebnis nach Abstand zum Kurs aufsteigend. Eine leere Rueckgabe ist ein
    zulaessiges Ergebnis und kein Fehler: Nicht jede Aktie hat im betrachteten
    Fenster mehrfach getestete Preisregionen.
    """
    points = find_swing_points(candles, start, end, params.pivot_reach)

    zones: list[PriceZone] = []
    for cluster in _cluster_by_price(points, params.zone_tolerance_pct):
        lower, upper = _zone_bounds(cluster, params.zone_tolerance_pct)
        touch_count, last_confirmed_at = _count_touches(candles, start, end, lower, upper)
        if touch_count < params.min_touches or last_confirmed_at is None:
            continue
        kind, distance_pct = _classify(lower, upper, close)
        zones.append(
            PriceZone(
                lower=lower,
                upper=upper,
                kind=kind,
                strength=_strength(touch_count, params),
                touch_count=touch_count,
                last_confirmed_at=last_confirmed_at,
                distance_pct=distance_pct,
                pivot_count=len(cluster),
            )
        )
    return _select(zones, params.max_zones_per_side)
