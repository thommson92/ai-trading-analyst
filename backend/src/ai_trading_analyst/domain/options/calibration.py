"""Das Preismodell gegen echte Notierungen halten (ADR 0058, Stufe 0).

Reine Rechnung auf fertig aufbereiteten Beobachtungen -- kein Netz, keine
Datenbank, keine Kerzenfolge. Wer die Beobachtungen beschafft, entscheidet
der Aufrufer.

**Warum das vor dem Backtest kommt.** Jede Praemie des historischen Laufs ist
eine Modellzahl; es gibt keine Notierungen aus der Vergangenheit, an denen
sie sich pruefen liesse. Was es gibt, sind die Ketten, die der Tageslauf seit
dem 2026-09-01 mitschreibt. An ihnen laesst sich messen, wie weit das Modell
danebenliegt -- und wenn der Fehler gross ist, weiss man es, **bevor** der
historische Lauf gebaut wird.

Gemessen werden drei Groessen, und ihre Trennung ist der eigentliche Gehalt:

1. **Formeltreue.** Die Praemie, mit der *notierten* impliziten Volatilitaet
   gerechnet, gegen den notierten Mittelwert. Hier steckt keine Annahme ueber
   die Volatilitaet mehr drin -- was uebrig bleibt, ist der Fehler der Formel
   selbst samt ihrer drei Vereinfachungen (europaeisch, ohne Dividende, ein
   Zinssatz).
2. **Volatilitaetsaufschlag.** Die notierte implizite gegen die aus Kerzen
   gerechnete realisierte Volatilitaet. Das ist der Faktor, den ADR 0058
   (Festlegung 2) zunaechst setzt und hier messen laesst.
3. **Skew.** Wie die implizite Volatilitaet mit der Moneyness faellt oder
   steigt. Ohne ihn ist der Vergleich von Put-Verkauf und Put-Spread eine
   Aussage ueber die Annahme (Festlegung 3) -- er entscheidet, wann Stufe 2
   ueberhaupt sinnvoll wird.

Die drei sind **getrennt**, weil sie verschiedene Dinge diagnostizieren. Ein
grosser Fehler in (1) heisst: Die Formel passt nicht. Ein grosser Fehler in
(2) heisst: Die Formel passt, aber die unterstellte Volatilitaet nicht. Eine
zusammengefasste Zahl liesse beide Faelle gleich aussehen.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from .pricing import price_put
from .values import OptionQuote


@dataclass(frozen=True, slots=True)
class StoredQuote:
    """Eine gespeicherte Notierung samt dem, was an ihrer Elternzeile stand.

    Der Kurs und der Zeitpunkt gehoeren zum Abruf, nicht zum Kontrakt --
    deshalb stehen sie hier und nicht in ``OptionQuote``.
    """

    symbol: str
    observed_at: datetime
    underlying_price: float
    quote: OptionQuote


@dataclass(frozen=True, slots=True)
class Observation:
    """Eine Notierung, aufbereitet zum Vergleich.

    ``realized_volatility`` ist ``None``, wenn sie sich aus dem Bestand nicht
    rechnen liess -- die Beobachtung zaehlt dann fuer die Formeltreue mit und
    fuer den Aufschlag nicht. Kein Ersatzwert (``CLAUDE.md``).
    """

    symbol: str
    underlying_price: float
    strike: float
    years_to_expiration: float
    quoted_mid: float
    quoted_implied_volatility: float | None
    realized_volatility: float | None
    chain_key: tuple[str, datetime, date]
    """Was eine Kette ausmacht: Symbol, Abrufzeitpunkt, Verfallstermin. Die
    Skew-Schaetzung rechnet **je Kette** und nicht ueber alle Notierungen --
    sonst vermengte sie die Form der Kurve mit dem Niveauunterschied zwischen
    Titeln und Tagen."""


@dataclass(frozen=True, slots=True)
class Verteilung:
    """Was eine Messreihe ueber sich sagt, ohne sie auf einen Wert zu
    verkuerzen.

    Median und Quartile statt Mittelwert und Streuung: Ein einzelner
    Ausreisser -- eine Notierung aus einem gekreuzten Markt etwa -- verschoebe
    den Mittelwert und liesse die Reihe schlechter aussehen, als sie ist.
    """

    anzahl: int
    median: float
    unteres_quartil: float
    oberes_quartil: float
    kleinster: float
    groesster: float


def verteilung(werte: Sequence[float]) -> Verteilung | None:
    """``None`` bei leerer Reihe -- eine Verteilung ohne Werte gibt es nicht."""
    if not werte:
        return None
    sortiert = sorted(werte)
    if len(sortiert) == 1:
        einziger = sortiert[0]
        return Verteilung(1, einziger, einziger, einziger, einziger, einziger)
    unteres, _, oberes = statistics.quantiles(sortiert, n=4)
    return Verteilung(
        anzahl=len(sortiert),
        median=statistics.median(sortiert),
        unteres_quartil=unteres,
        oberes_quartil=oberes,
        kleinster=sortiert[0],
        groesster=sortiert[-1],
    )


@dataclass(frozen=True, slots=True)
class CalibrationSummary:
    """Das Messergebnis von Stufe 0.

    Jede der drei Groessen kann ``None`` sein -- dann fehlte die Grundlage,
    und das ist eine Aussage fuer sich. Wieviel wovon fehlte, sagen die
    Abdeckungszahlen.
    """

    notierungen: int
    formeltreue: Verteilung | None
    """Relative Abweichung ``(modelliert - notiert) / notiert`` der Praemie,
    gerechnet mit der **notierten** impliziten Volatilitaet. Ein Median nahe
    null heisst: Die Formel trifft den Markt. Ein systematisch negativer
    Median waere der erwartete Befund -- alle drei Vereinfachungen
    unterschaetzen die Praemie."""
    volatilitaetsaufschlag: Verteilung | None
    """Verhaeltnis ``implizit / realisiert``. Der Faktor aus Festlegung 2,
    hier gemessen statt gesetzt."""
    skew_steigung: Verteilung | None
    """Aenderung der impliziten Volatilitaet je Einheit ``ln(strike / kurs)``,
    je Kette geschaetzt. **Negativ** ist der uebliche Befund bei
    Aktienoptionen: Weiter aus dem Geld liegende Puts -- kleineres ``ln(K/S)``
    -- tragen die hoehere implizite Volatilitaet."""
    ohne_implizite_volatilitaet: int
    ohne_realisierte_volatilitaet: int
    ketten_fuer_skew: int
    """Wieviele Ketten mindestens drei Notierungen mit implizierter
    Volatilitaet und **verschiedenen** Strikes hatten. Darunter laesst sich
    keine Steigung schaetzen."""


def summarize_calibration(
    observations: Iterable[Observation], *, risk_free_rate: float
) -> CalibrationSummary:
    """Die drei Messgroessen aus einer Menge Beobachtungen."""
    beobachtungen = list(observations)

    abweichungen: list[float] = []
    aufschlaege: list[float] = []
    ohne_iv = 0
    ohne_rv = 0
    ketten: dict[tuple[str, datetime, date], list[tuple[float, float]]] = {}

    for beobachtung in beobachtungen:
        iv = beobachtung.quoted_implied_volatility
        if iv is None or iv <= 0.0:
            ohne_iv += 1
        else:
            modelliert = price_put(
                spot=beobachtung.underlying_price,
                strike=beobachtung.strike,
                years_to_expiration=beobachtung.years_to_expiration,
                volatility=iv,
                risk_free_rate=risk_free_rate,
            ).premium
            if beobachtung.quoted_mid > 0.0:
                abweichungen.append(
                    (modelliert - beobachtung.quoted_mid) / beobachtung.quoted_mid
                )
            ketten.setdefault(beobachtung.chain_key, []).append(
                (
                    math.log(beobachtung.strike / beobachtung.underlying_price),
                    iv,
                )
            )

        rv = beobachtung.realized_volatility
        if rv is None or rv <= 0.0:
            ohne_rv += 1
        elif iv is not None and iv > 0.0:
            aufschlaege.append(iv / rv)

    steigungen = [
        steigung
        for punkte in ketten.values()
        if (steigung := _steigung(punkte)) is not None
    ]

    return CalibrationSummary(
        notierungen=len(beobachtungen),
        formeltreue=verteilung(abweichungen),
        volatilitaetsaufschlag=verteilung(aufschlaege),
        skew_steigung=verteilung(steigungen),
        ohne_implizite_volatilitaet=ohne_iv,
        ohne_realisierte_volatilitaet=ohne_rv,
        ketten_fuer_skew=len(steigungen),
    )


_MINDESTPUNKTE_JE_KETTE = 3
"""Zwei Punkte legen immer eine Gerade -- und sagen damit nichts darueber, ob
es eine gibt. Ab drei ist die Steigung eine Schaetzung und keine
Tautologie."""


def _steigung(punkte: Sequence[tuple[float, float]]) -> float | None:
    """Steigung der Ausgleichsgeraden durch ``(x, y)``, oder ``None``.

    ``None``, wenn zu wenige Punkte vorliegen oder alle auf demselben ``x``
    stehen -- dann ist die Steigung nicht bestimmt, und eine Zahl an dieser
    Stelle waere erfunden.
    """
    if len(punkte) < _MINDESTPUNKTE_JE_KETTE:
        return None
    xs = [x for x, _ in punkte]
    ys = [y for _, y in punkte]
    # **Der Vergleich laeuft auf den Werten selbst, nicht auf ihrer Streuung.**
    # Bei lauter gleichen ``x`` ist die Streuung rechnerisch null, in
    # Gleitkomma aber nicht: ``fmean`` summiert und teilt, und das Ergebnis
    # weicht im letzten Bit ab. Die Streuung landet dann bei ~1e-34, die
    # Kovarianz bei ~1e-18, und der Quotient ist eine Steigung aus reinem
    # Rundungsrauschen -- gemessen -2,67, wo es keine gibt.
    if min(xs) == max(xs):
        return None
    x_mittel = statistics.fmean(xs)
    y_mittel = statistics.fmean(ys)
    streuung = sum((x - x_mittel) ** 2 for x in xs)
    kovarianz = sum(
        (x - x_mittel) * (y - y_mittel) for x, y in zip(xs, ys, strict=True)
    )
    return kovarianz / streuung
