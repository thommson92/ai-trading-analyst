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
    quoted_mid: float | None
    """Der notierte Mittelwert, oder ``None``, wenn Geld- **oder** Briefkurs
    fehlte -- nach Boersenschluss und bei duenn gehandelten Kontrakten der
    Regelfall (``OptionQuote.mid``). Kein Ersatzwert: Eine Null waere von
    einer notierten Null nicht mehr zu unterscheiden."""
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
    # ``method="inclusive"`` und nicht die Vorgabe: Die Vorgabe (``exclusive``)
    # extrapoliert ueber die Reihe hinaus und liefert bei zwei Werten Quartile
    # **ausserhalb** der Spanne -- aus ``[0, 10]`` wird ``-2,5`` und ``12,5``.
    # Ein negatives Quartil neben einem Aufschlag, der nur positiv sein kann,
    # waere sichtbar falsch. Und die duenne Anfangslage ist genau der Fall,
    # den ADR 0058 als Risiko benennt.
    unteres, _, oberes = statistics.quantiles(sortiert, n=4, method="inclusive")
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
    hier gemessen statt gesetzt.

    **Je Kette, nicht je Notierung** -- und das ist keine Feinheit, sondern
    der Unterschied zwischen einer Messung und einem Mischwert. Eine Kette
    liefert bis zu zwoelf Strikes mit je eigener, skew-behafteter impliziter
    Volatilitaet, aber nur **eine** realisierte. Ein Median ueber alle
    Einzelverhaeltnisse maesse Aufschlag und Skew in einer Zahl: Bei einem
    wahren Aufschlag von 1,25 und einer Skew-Steigung von -0,5 kaeme 1,49
    heraus, bei -1,0 sogar 1,74 -- systematisch zu hoch, und abhaengig davon,
    welche Strikes der Tageslauf gerade notiert hat.

    Genommen wird deshalb die **auf das Geld extrapolierte** implizite
    Volatilitaet der Kette: der Achsenabschnitt derselben Ausgleichsgeraden,
    aus der auch ``skew_steigung`` kommt, bei ``ln(K/S) = 0``. Das ist eine
    kurze Extrapolation -- die notierten Strikes liegen zwischen 80 und 99
    Prozent des Kurses, der naechste also bei ``ln(K/S) ~ -0,01``.

    Eine Kette, fuer die sich keine Gerade schaetzen laesst, traegt hier
    nichts bei. Aus einem oder zwei Punkten liesse sich Niveau und Steigung
    nicht trennen, und ein Ersatz waere erfunden."""
    skew_steigung: Verteilung | None
    """Aenderung der impliziten Volatilitaet je Einheit ``ln(strike / kurs)``,
    je Kette geschaetzt. **Negativ** ist der uebliche Befund bei
    Aktienoptionen: Weiter aus dem Geld liegende Puts -- kleineres ``ln(K/S)``
    -- tragen die hoehere implizite Volatilitaet."""
    ohne_implizite_volatilitaet: int
    ohne_realisierte_volatilitaet: int
    ohne_mittelwert: int
    """Notierungen ohne Geld- oder Briefkurs. Sie zaehlen in ``notierungen``
    mit und in der Formeltreue nicht -- ohne diese Zahl bliebe die Luecke
    zwischen beiden unerklaerlich, und die Abdeckung ist genau die Frage,
    fuer die dieser Messlauf gebaut ist."""
    ketten: int
    """Wieviele Ketten (Symbol, Abrufzeitpunkt, Verfall) der Bestand ueberhaupt
    enthaelt."""
    ketten_mit_gerade: int
    """Wieviele davon mindestens drei Notierungen mit implizierter
    Volatilitaet auf **drei verschiedenen** Strikes hatten. Nur sie tragen zu
    Aufschlag und Skew bei; darunter laesst sich keine Gerade schaetzen."""


def summarize_calibration(
    observations: Iterable[Observation], *, risk_free_rate: float
) -> CalibrationSummary:
    """Die drei Messgroessen aus einer Menge Beobachtungen."""
    beobachtungen = list(observations)

    abweichungen: list[float] = []
    ohne_iv = 0
    ohne_rv = 0
    ohne_mid = 0
    kurven: dict[tuple[str, datetime, date], list[tuple[float, float]]] = {}
    # Je Kette **eine** realisierte Volatilitaet: Alle ihre Notierungen teilen
    # Symbol und Abrufzeitpunkt, stehen also auf derselben Kurshistorie.
    kette_rv: dict[tuple[str, datetime, date], float] = {}
    alle_ketten: set[tuple[str, datetime, date]] = set()

    for beobachtung in beobachtungen:
        alle_ketten.add(beobachtung.chain_key)
        iv = beobachtung.quoted_implied_volatility
        mid = beobachtung.quoted_mid
        if mid is None or mid <= 0.0:
            ohne_mid += 1
        rv = beobachtung.realized_volatility
        if rv is None or rv <= 0.0:
            ohne_rv += 1
        else:
            kette_rv[beobachtung.chain_key] = rv

        if iv is None or iv <= 0.0:
            ohne_iv += 1
            continue

        if mid is not None and mid > 0.0:
            modelliert = price_put(
                spot=beobachtung.underlying_price,
                strike=beobachtung.strike,
                years_to_expiration=beobachtung.years_to_expiration,
                volatility=iv,
                risk_free_rate=risk_free_rate,
            ).premium
            abweichungen.append((modelliert - mid) / mid)

        kurven.setdefault(beobachtung.chain_key, []).append(
            (math.log(beobachtung.strike / beobachtung.underlying_price), iv)
        )

    steigungen: list[float] = []
    aufschlaege: list[float] = []
    for schluessel, punkte in kurven.items():
        gerade = _gerade(punkte)
        if gerade is None:
            continue
        steigung, am_geld = gerade
        steigungen.append(steigung)
        rv_der_kette = kette_rv.get(schluessel)
        # Der Achsenabschnitt ist die auf ``ln(K/S) = 0`` extrapolierte
        # implizite Volatilitaet -- das Niveau der Kette, ohne den Skew.
        # Eine negative Extrapolation gibt es rechnerisch, als Volatilitaet
        # nicht; sie traegt deshalb nichts bei.
        if rv_der_kette is not None and am_geld > 0.0:
            aufschlaege.append(am_geld / rv_der_kette)

    return CalibrationSummary(
        notierungen=len(beobachtungen),
        formeltreue=verteilung(abweichungen),
        volatilitaetsaufschlag=verteilung(aufschlaege),
        skew_steigung=verteilung(steigungen),
        ohne_implizite_volatilitaet=ohne_iv,
        ohne_realisierte_volatilitaet=ohne_rv,
        ohne_mittelwert=ohne_mid,
        ketten=len(alle_ketten),
        ketten_mit_gerade=len(steigungen),
    )


_MINDESTSTRIKES_JE_KETTE = 3
"""Zwei Stuetzstellen legen immer eine Gerade -- und sagen damit nichts
darueber, ob es eine gibt. Gezaehlt werden **verschiedene** ``x``, nicht
Punkte: Drei Notierungen auf den Strikes 95/95/90 stuenden auf zwei
Stuetzstellen und waeren wieder die Tautologie, gegen die diese Schranke
gesetzt ist."""


def _gerade(punkte: Sequence[tuple[float, float]]) -> tuple[float, float] | None:
    """Steigung und Achsenabschnitt der Ausgleichsgeraden durch ``(x, y)``.

    Der Achsenabschnitt ist der Wert bei ``x = 0`` -- fuer die Skew-Kurve also
    die auf das Geld extrapolierte implizite Volatilitaet.

    ``None``, wenn weniger als drei **verschiedene** ``x`` vorliegen. Dann ist
    die Gerade nicht bestimmt, und Zahlen an dieser Stelle waeren erfunden.
    Der Vergleich laeuft dabei auf den Werten selbst und nicht auf ihrer
    Streuung: Bei lauter gleichen ``x`` ist die Streuung rechnerisch null, in
    Gleitkomma aber nicht -- ``fmean`` summiert und teilt, das Ergebnis weicht
    im letzten Bit ab, die Streuung landet bei ~1e-34 und die Kovarianz bei
    ~1e-18. Der Quotient waere eine Steigung aus reinem Rundungsrauschen.
    """
    xs = [x for x, _ in punkte]
    if len(set(xs)) < _MINDESTSTRIKES_JE_KETTE:
        return None
    ys = [y for _, y in punkte]
    x_mittel = statistics.fmean(xs)
    y_mittel = statistics.fmean(ys)
    streuung = sum((x - x_mittel) ** 2 for x in xs)
    kovarianz = sum(
        (x - x_mittel) * (y - y_mittel) for x, y in zip(xs, ys, strict=True)
    )
    steigung = kovarianz / streuung
    return steigung, y_mittel - steigung * x_mittel
