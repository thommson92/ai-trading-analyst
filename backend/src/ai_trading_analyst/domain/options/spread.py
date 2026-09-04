"""Der Put-Spread neben dem ungesicherten Verkauf (ADR 0058, Festlegung 11).

Reine Rechnung. Was hier entsteht, sind **Zahlen zum Vergleich**, keine
Empfehlung: Welche Struktur die richtige ist, entscheidet Festlegung 10 an
Kriterien, die zum Teil erst nach dem Scoring feststehen. Dieses Modul
liefert die drei Groessen, die dafuer aus der Kette kommen -- was die
Absicherung kostet, was sie an Risiko wegnimmt, und ob ihre Seite ueberhaupt
handelbar ist.

**Der Absicherungs-Strike wird gezielt nachgefragt, nicht mitbestellt.**
Das Moneyness-Band des Verkaufs nach unten zu verbreitern haette fuer
**jeden** Kandidaten mehr Kontrakte notiert; der zweite Abruf faellt nur an,
wo ueberhaupt ein Verkaufs-Strike gefunden wurde.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .strategies import KONTRAKTGROESSE
from .values import LiquidityGrade, OptionQuote, PutStrategy


def select_hedge_strike(
    listed: Sequence[float], *, short_strike: float, price: float, width_pct: float
) -> float | None:
    """Der gelistete Strike, der der Zielbreite unter dem Verkauf am naechsten
    liegt.

    Die Breite ist ein Anteil des **Aktienkurses** und nicht des Strikes: Sie
    soll ueber Titel hinweg dasselbe bedeuten, und der Kurs ist die Groesse,
    an der sich ein Kursrutsch misst.

    Nur Strikes **echt unterhalb** des Verkaufs kommen in Frage -- ein
    gekaufter Put auf gleicher Hoehe nimmt kein Risiko weg und kostet die
    ganze Praemie.

    ``None``, wenn kein solcher Strike gelistet ist. Dann gibt es keinen
    Spread zu vergleichen, und ein erfundener waere schlimmer als keiner.
    """
    ziel = short_strike - price * width_pct
    darunter = [strike for strike in listed if strike < short_strike]
    if not darunter:
        return None
    # Bei Gleichstand der **tiefere**: Er nimmt mehr Risiko weg, und die
    # sortierte Reihenfolge macht die Wahl reproduzierbar.
    return min(sorted(darunter), key=lambda strike: abs(strike - ziel))


@dataclass(frozen=True, slots=True)
class PutSpread:
    """Der Verkauf mit gekauftem Put als Absicherung, gerechnet.

    Alle Geldbetraege je Aktie, wie bei ``PutStrategy``; ``capital_at_risk``
    je Kontrakt, wie dort.
    """

    short_strike: float
    hedge_strike: float
    hedge_cost: float
    """Der Mittelwert des gekauften Puts -- was die Absicherung kostet."""
    net_credit: float
    """Vereinnahmte Praemie abzueglich Absicherungskosten."""
    max_loss: float
    """``(short_strike - hedge_strike) - net_credit``, je Aktie. Der Betrag
    steht bei Eintritt fest -- das ist der ganze Unterschied zum
    ungesicherten Verkauf."""
    capital_at_risk: float
    """``max_loss * 100``. Beim Cash Secured Put ist es ``strike * 100``; der
    Unterschied zwischen beiden Zahlen ist die eigentliche Aussage
    (ADR 0058, Festlegung 6)."""
    hedge_cost_share: float
    """Anteil der Praemie, den die Absicherung frisst -- Kriterium 3 der
    Strukturwahl. Bei steilem Skew treibt er auf die Haelfte und mehr."""
    return_on_risk: float
    """Netto-Gutschrift im Verhaeltnis zum tatsaechlich riskierten Kapital --
    Kriterium 2. Die eine Zahl, die beide Strukturen vergleichbar macht."""
    hedge_liquidity: LiquidityGrade
    """Kriterium 4. Ist die zweite Seite duenn, ist der Spread eine Rechnung
    und kein Handel -- er ueberquert ausserdem doppelt so viele
    Geld-Brief-Spannen."""
    hedge_delta: float | None = None
    hedge_open_interest: int | None = None
    hedge_volume: int | None = None


REASON_NO_HEDGE_STRIKE = "kein Strike unter dem Verkauf gelistet"
REASON_HEDGE_WITHOUT_MID = "der Absicherungs-Strike lieferte keinen Mittelwert"
REASON_HEDGE_NOT_CHEAPER = "die Absicherung kostet mindestens die ganze Praemie"
REASON_CREDIT_EXCEEDS_WIDTH = "die Gutschrift uebersteigt die Spannweite"
"""Ein Spread, der mehr einbringt als er hoechstens verlieren kann, waere ein
risikoloser Gewinn -- den stellt kein Markt. Er entsteht aus zwei Notierungen,
die nicht zueinander passen: eine veraltete, eine gekreuzte, eine aus duennem
Handel. Genau dafuer ist Fehlerbehandlung da (``CLAUDE.md``: an den
Systemgrenzen), und die Zahlen daraus waeren sonst frei erfunden."""


def evaluate_spread(
    short: PutStrategy,
    hedge: OptionQuote,
    *,
    liquidity: LiquidityGrade,
) -> PutSpread | str:
    """Rechnet den Spread, oder nennt den Grund, warum keiner entsteht.

    Ein Wortlaut statt ``None``: Warum kein Spread vorliegt, gehoert an das
    Ergebnis -- sonst stuende dort eine Luecke, die niemand erklaeren kann
    (Muster ``unzureichend`` in ``strategies.py``).

    Kostet die Absicherung mindestens die ganze Praemie, entsteht keiner:
    Eine Gutschrift von null oder darunter ist kein Verkauf mehr. Das kommt
    bei sehr steilem Skew und schmalen Spannweiten tatsaechlich vor.
    """
    kosten = hedge.mid
    if kosten is None:
        return REASON_HEDGE_WITHOUT_MID
    if kosten >= short.premium:
        return REASON_HEDGE_NOT_CHEAPER

    gutschrift = short.premium - kosten
    spannweite = short.strike - hedge.strike
    max_verlust = spannweite - gutschrift
    if max_verlust <= 0.0:
        return REASON_CREDIT_EXCEEDS_WIDTH
    return PutSpread(
        short_strike=short.strike,
        hedge_strike=hedge.strike,
        hedge_cost=kosten,
        net_credit=gutschrift,
        max_loss=max_verlust,
        capital_at_risk=max_verlust * KONTRAKTGROESSE,
        hedge_cost_share=kosten / short.premium,
        return_on_risk=gutschrift / max_verlust,
        hedge_liquidity=liquidity,
        hedge_delta=abs(hedge.delta) if hedge.delta is not None else None,
        hedge_open_interest=hedge.open_interest,
        hedge_volume=hedge.volume,
    )
