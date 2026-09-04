"""Bewertung eines europaeischen Puts und die Volatilitaet dazu (ADR 0058).

Reine Rechnung: keine Uhr, kein Netz, keine Konfiguration, keine
Kerzenfolge. Was hereinkommt, sind Zahlen; was herausgeht, sind Zahlen.

**Ohne neue Abhaengigkeit.** Die Normalverteilung steht mit ``math.erf`` in
der Standardbibliothek; scipy dafuer einzufuehren waere eine Abhaengigkeit
fuer eine Zeile (``CLAUDE.md``: keine unnoetigen Abhaengigkeiten).

Zwei Aufrufer, dieselben Funktionen -- dasselbe Muster wie bei
``strategies.py``: Der Messlauf, der das Modell gegen echte Notierungen
haelt, und der spaetere historische Backtest rechnen mit **einer** Formel.
Zwei waeren zwei Ergebnisse, von denen niemand sagen koennte, welches gilt.

Drei bekannte Vereinfachungen, alle mit **bekannter Richtung** (ADR 0058,
"Was bewusst nicht gebaut wird"):

1. **Europaeisch, nicht amerikanisch.** Ein amerikanischer Put ist wegen des
   vorzeitigen Ausuebungsrechts etwas mehr wert. Bei aus dem Geld liegenden
   Puts mit 21 bis 60 Tagen ist der Unterschied klein; die Formel
   **unterschaetzt** die Praemie also leicht.
2. **Keine Dividenden.** Eine Dividende erhoeht den Wert eines Puts. Auch
   hier wird die Praemie **unterschaetzt**.
3. **Ein Zinssatz, kein Zinsstrukturverlauf.** Bei den betrachteten
   Laufzeiten faellt das kaum ins Gewicht.

Alle drei zeigen in dieselbe Richtung. Das ist der Grund, warum der Messlauf
den Fehler **gegen echte Notierungen** ausweist statt ihn zu schaetzen: Eine
gemessene Abweichung enthaelt sie mit, eine behauptete nicht.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

PRICING_MODEL_VERSION = "black-scholes-europaeisch-v1"
"""Version des Bewertungsverfahrens, an jedem gerechneten Ergebnis zu
speichern (``CLAUDE.md``: Versionierung).

Aendert sich eine der drei Vereinfachungen oben -- kommt etwa die
amerikanische Bewertung dazu --, steigt diese Nummer. Eine Praemie aus einem
Binomialbaum ist eine **andere Zahl** als eine aus dieser Formel, und man
muss einem gespeicherten Ergebnis ansehen koennen, welche von beiden es ist.
"""

TRADING_DAYS_PER_YEAR = 252
"""Handelstage im Jahr -- der uebliche Annualisierungsfaktor fuer eine aus
Tagesschlusskursen gerechnete Volatilitaet.

Handelstage und nicht Kalendertage: Zwischen Freitag- und Montagsschluss
liegt **ein** Renditeschritt, nicht drei. Die Restlaufzeit einer Option
rechnet dagegen in Kalendertagen (``strategies.TAGE_JE_JAHR``) -- dort ist
Kapital ueber ein Wochenende genauso gebunden wie an einem Dienstag. Beide
Faktoren sind richtig, jeder fuer seine Groesse.
"""


@dataclass(frozen=True, slots=True)
class PutPrice:
    """Praemie und Delta eines Puts aus **einer** Rechnung.

    Zusammen und nicht in zwei Funktionen: Beide stehen auf denselben ``d1``
    und ``d2``. Getrennt gerechnet koennten sie auf verschiedenen Eingaben
    stehen, und ein Delta, das nicht zu seiner Praemie passt, waere schlimmer
    als keines -- die Strike-Wahl des Backtests haengt daran (ADR 0058,
    Festlegung 5).
    """

    premium: float
    delta: float
    """Vorzeichenbehaftet wie beim Anbieter: fuer einen Put zwischen ``-1``
    und ``0``."""


def normal_cdf(x: float) -> float:
    """Verteilungsfunktion der Standardnormalverteilung."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def price_put(
    *,
    spot: float,
    strike: float,
    years_to_expiration: float,
    volatility: float,
    risk_free_rate: float,
) -> PutPrice:
    """Black-Scholes fuer einen europaeischen Put.

    ``volatility`` und ``risk_free_rate`` sind annualisiert; ``spot`` und
    ``strike`` in derselben Waehrung; ``years_to_expiration`` in Jahren.

    **Die Grenzfaelle sind exakt, keine Ersatzwerte.** Laeuft keine Zeit mehr
    (``years_to_expiration <= 0``) oder bewegt sich nichts
    (``volatility <= 0``), gibt es keine Unsicherheit mehr zu bewerten: Der
    Put ist dann genau den abgezinsten Betrag wert, um den der Terminkurs
    unter dem Strike liegt, und das Delta ist ``-1`` oder ``0``. Das ist die
    richtige Antwort und nicht ein Ausweichen vor einer Division durch null.

    Ein Kurs oder Strike von null oder darunter ist dagegen kein Grenzfall,
    sondern ein Programmierfehler -- aus echten Kerzen und echten
    Optionsketten kann er nicht kommen.
    """
    if spot <= 0.0:
        raise ValueError(f"Kurs muss positiv sein, war {spot}.")
    if strike <= 0.0:
        raise ValueError(f"Strike muss positiv sein, war {strike}.")

    diskontierter_strike = strike * math.exp(-risk_free_rate * max(years_to_expiration, 0.0))
    streuung = volatility * math.sqrt(max(years_to_expiration, 0.0))
    if streuung <= 0.0:
        im_geld = spot < diskontierter_strike
        return PutPrice(
            premium=max(diskontierter_strike - spot, 0.0),
            delta=-1.0 if im_geld else 0.0,
        )

    d1 = (
        math.log(spot / strike)
        + (risk_free_rate + 0.5 * volatility**2) * years_to_expiration
    ) / streuung
    d2 = d1 - streuung
    return PutPrice(
        premium=diskontierter_strike * normal_cdf(-d2) - spot * normal_cdf(-d1),
        delta=normal_cdf(d1) - 1.0,
    )


def realized_volatility(
    closes: Sequence[float], *, periods_per_year: int = TRADING_DAYS_PER_YEAR
) -> float | None:
    """Annualisierte Standardabweichung der logarithmischen Renditen.

    ``None``, wenn sie sich nicht rechnen laesst: weniger als drei
    Schlusskurse -- zwei Renditen sind das Wenigste, woraus eine
    Stichprobenstreuung entsteht -- oder ein Kurs von null oder darunter.
    Kein Ersatzwert (``CLAUDE.md``: fehlt eine Kennzahl, bleibt sie fehlend).

    **Stichprobenstreuung, kein Nullmittel.** In der Praxis wird die
    Volatilitaet oft mit unterstelltem Mittelwert null gerechnet
    (``sqrt(sum(r^2)/n)``); das ergibt einen etwas hoeheren Wert, weil die
    Drift nicht abgezogen wird. Hier steht die Lehrbuchdefinition, weil sie
    keine Annahme ueber die Drift trifft. Der Unterschied ist klein und
    systematisch -- und er verschwindet ohnehin in dem Aufschlag, den ADR
    0058 (Festlegung 2) an echten Notierungen **misst**, statt ihn zu setzen.

    Der Aufrufer entscheidet, welche Schlusskurse er hereinreicht, und muss
    dabei das Look-ahead-Verbot beachten (Doc 10, Paragraph 6.6): Fuer eine
    Entscheidung an ``t`` zaehlen ausschliesslich Kerzen vor ``t``.
    """
    if len(closes) < 3:
        return None
    if any(close <= 0.0 for close in closes):
        return None
    renditen = [math.log(spaeter / frueher) for frueher, spaeter in pairwise(closes)]
    return statistics.stdev(renditen) * math.sqrt(periods_per_year)
