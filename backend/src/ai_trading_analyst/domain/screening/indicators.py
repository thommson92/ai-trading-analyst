"""Deterministische Indikatorberechnung (Gate G1, Abschnitt 1.2 und 1.3).

Bis Sprint 1B lieferte ausschliesslich der ``FixtureMarketDataProvider``
fertige Indikatorwerte. Ein produktiver Marktdatenanbieter liefert nur Kerzen
-- RSI, RSI-Moving-Average, EMA5 und EMA20 muessen daraus selbst berechnet
werden. Diese Berechnung ist eine Fachregel und gehoert deshalb in den Domain
Layer, nicht in den jeweiligen Adapter: sie gilt fuer jeden Anbieter gleich
und wird ab Sprint 3 zusaetzlich vom Backtesting genutzt.

Massgeblich ist ``docs/requirements/g1-pruefvorlage.md``:

* RSI: Laenge 14 ueber Close, Wilder/RMA-Glaettung (Abschnitt 1.2).
* RSI-MA: SMA der Laenge 14 ueber die **RSI-Werte**, nicht ueber den Preis.
* EMA5/EMA20: exponentiell ueber Close.
* Es wird ungerundet gerechnet (Abschnitt 1.4).
* Ein nicht berechenbarer Wert ist ``None`` und niemals 0.0 oder ein
  fortgeschriebener Vorwert (Abschnitt 1.5) -- die Kandidatenpruefung stuft
  eine solche Kerze als ``UNKNOWN_DATA_INCOMPLETE`` ein.

Nicht Gegenstand dieses Moduls ist die Frage, wie viele Kerzen vorliegen
muessen, bevor ein Wert als belastbar gilt: der Warm-up von 250 Kerzen
(Abschnitt 1.3) wird in der Kandidatenregel geprueft
(``CandidateRuleParameters.warmup_candles``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .values import IndicatorValues

SMOOTHING_METHODS = ("sma", "ema", "wilder")


class UnsupportedSmoothingMethodError(ValueError):
    """Eine Glaettungsmethode wurde angefordert, die es nicht gibt."""

    def __init__(self, method: str) -> None:
        self.method = method
        super().__init__(
            f"Unbekannte Glaettungsmethode '{method}'. Zulaessig: {', '.join(SMOOTHING_METHODS)}."
        )


@dataclass(frozen=True, slots=True)
class IndicatorParameters:
    """Die in Gate G1 freigegebenen Indikatorparameter.

    Bewusst ein eigenstaendiges Domain-Objekt statt einer Abhaengigkeit auf das
    Pydantic-Konfigurationsschema -- dieselbe Trennung wie bei
    ``CandidateRuleParameters``. Die Composition Root baut es aus ``AppConfig``.
    """

    rsi_length: int
    rsi_method: str
    rsi_ma_length: int
    rsi_ma_type: str
    fast_ema_length: int
    slow_ema_length: int

    def __post_init__(self) -> None:
        for name, length in (
            ("rsi_length", self.rsi_length),
            ("rsi_ma_length", self.rsi_ma_length),
            ("fast_ema_length", self.fast_ema_length),
            ("slow_ema_length", self.slow_ema_length),
        ):
            if length <= 0:
                raise ValueError(f"{name} muss groesser als 0 sein, ist aber {length}")
        for method in (self.rsi_method, self.rsi_ma_type):
            if method not in SMOOTHING_METHODS:
                raise UnsupportedSmoothingMethodError(method)


def simple_moving_average(values: Sequence[float | None], length: int) -> list[float | None]:
    """Gleitender Durchschnitt ueber genau ``length`` zusammenhaengende Werte.

    Ein Fenster, das eine Luecke (``None``) enthaelt, ergibt ``None`` -- eine
    Luecke wird nicht uebersprungen und nicht interpoliert.
    """
    result: list[float | None] = []
    for index in range(len(values)):
        window = values[index - length + 1 : index + 1]
        if index + 1 < length or any(value is None for value in window):
            result.append(None)
            continue
        result.append(sum(value for value in window if value is not None) / length)
    return result


def _recursive_average(
    values: Sequence[float | None], length: int, weight_of_new_value: float
) -> list[float | None]:
    """Gemeinsame Mechanik von EMA und Wilder/RMA.

    Beide unterscheiden sich ausschliesslich im Gewicht des neuen Wertes: EMA
    verwendet ``2 / (length + 1)``, Wilder ``1 / length``. Beide starten auf
    dem einfachen Durchschnitt der ersten ``length`` Werte (Seeding wie in
    TradingViews Pine Script) -- nach dem in Abschnitt 1.3 vorgeschriebenen
    Warm-up von 250 Kerzen ist der Einfluss dieser Startwahl auf die
    Signalentscheidung ohnehin ausgeglichen.

    Reisst die Datenreihe ab (``None``), beginnt die Glaettung danach neu mit
    einem vollstaendigen Fenster, statt ueber die Luecke hinweg fortzuschreiben.
    """
    result: list[float | None] = []
    previous: float | None = None
    for index, value in enumerate(values):
        if value is None:
            previous = None
            result.append(None)
            continue
        if previous is None:
            seed_window = values[index - length + 1 : index + 1]
            if index + 1 < length or any(item is None for item in seed_window):
                result.append(None)
                continue
            previous = sum(item for item in seed_window if item is not None) / length
        else:
            previous = weight_of_new_value * value + (1 - weight_of_new_value) * previous
        result.append(previous)
    return result


def exponential_moving_average(values: Sequence[float | None], length: int) -> list[float | None]:
    return _recursive_average(values, length, 2 / (length + 1))


def wilder_moving_average(values: Sequence[float | None], length: int) -> list[float | None]:
    """Wilders RMA -- die Glaettung, die TradingViews RSI zugrunde liegt."""
    return _recursive_average(values, length, 1 / length)


def smooth(values: Sequence[float | None], length: int, method: str) -> list[float | None]:
    if method == "sma":
        return simple_moving_average(values, length)
    if method == "ema":
        return exponential_moving_average(values, length)
    if method == "wilder":
        return wilder_moving_average(values, length)
    raise UnsupportedSmoothingMethodError(method)


def relative_strength_index(
    closes: Sequence[float], length: int, method: str = "wilder"
) -> list[float | None]:
    """RSI ueber Schlusskurse (G1-Pruefvorlage, Abschnitt 1.2).

    Die erste Kursaenderung existiert erst ab Index 1; mit der vorgeschriebenen
    Wilder-Glaettung liegt der erste RSI-Wert damit bei Index ``length``.
    """
    gains: list[float | None] = [None]
    losses: list[float | None] = [None]
    for index in range(1, len(closes)):
        change = closes[index] - closes[index - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    average_gains = smooth(gains, length, method)
    average_losses = smooth(losses, length, method)

    result: list[float | None] = []
    for average_gain, average_loss in zip(average_gains, average_losses, strict=True):
        if average_gain is None or average_loss is None:
            result.append(None)
        elif average_loss == 0.0 and average_gain == 0.0:
            # Voellig unbewegter Kurs: Der RSI ist rechnerisch nicht definiert
            # (0/0). TradingViews ta.rsi liefert hier ``na``; entsprechend
            # bleibt der Wert offen, statt 100 oder 50 zu behaupten. Die
            # Kandidatenpruefung stuft die Aktie damit als
            # UNKNOWN_DATA_INCOMPLETE ein -- das ist die ehrliche Aussage.
            result.append(None)
        elif average_loss == 0.0:
            # Kein einziger Verlust im geglaetteten Fenster: der RSI ist per
            # Definition 100, die Division waere sonst nicht definiert.
            result.append(100.0)
        else:
            result.append(100.0 - 100.0 / (1.0 + average_gain / average_loss))
    return result


def compute_indicator_values(
    closes: Sequence[float], parameters: IndicatorParameters
) -> tuple[IndicatorValues, ...]:
    """Berechnet alle vier Indikatoren fuer jede Kerze der Reihe.

    Das Ergebnis hat dieselbe Laenge und dieselbe Indizierung wie ``closes``
    und kann damit unveraendert in eine ``CandleSeries`` uebernommen werden.
    """
    rsi = relative_strength_index(closes, parameters.rsi_length, parameters.rsi_method)
    rsi_ma = smooth(rsi, parameters.rsi_ma_length, parameters.rsi_ma_type)
    ema_fast = exponential_moving_average(list(closes), parameters.fast_ema_length)
    ema_slow = exponential_moving_average(list(closes), parameters.slow_ema_length)

    return tuple(
        IndicatorValues(rsi=values[0], rsi_ma=values[1], ema5=values[2], ema20=values[3])
        for values in zip(rsi, rsi_ma, ema_fast, ema_slow, strict=True)
    )
