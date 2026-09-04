"""Verfallskalender und Strike-Wahl fuer den Rueckblick (ADR 0058).

Was der Live-Betrieb **abruft**, muss der historische Lauf **konstruieren**:
Welche Kontrakte damals notiert waren, laesst sich nicht mehr erfragen. Beides
hier sind deshalb Regeln, keine Abrufe -- und beide sind Annahmen, die am
Ergebnis vermerkt werden.

Reine Rechnung: keine Uhr, kein Netz, keine Kerzenfolge.
"""

from __future__ import annotations

import calendar
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .pricing import price_put


def daily_closes(
    samples: Sequence[tuple[datetime, float]], *, timezone: ZoneInfo
) -> list[tuple[date, float]]:
    """Je Handelstag der Schluss des **letzten** Eintrags, aufsteigend.

    Nimmt Zeitstempel-Kurs-Paare und nicht eine bestimmte Kerzen- oder
    Barklasse: Gebraucht wird dieselbe Ableitung an zwei Stellen -- der
    Messlauf rechnet auf den nativen Bars des Anbieters, der historische
    Backtest auf den gebildeten Kerzen. Zwei Fassungen waeren zwei
    Definitionen von "Tagesschluss".

    **Der Handelstag wird umgerechnet, nicht angenommen.** Ein Zeitstempel
    kann in jeder Zone ankommen -- aus der Datenbank in der Zone der Sitzung,
    aus der Kerzenbildung in der der Boerse. ``.date()`` darauf ergaebe
    unterschiedliche Tage fuer dieselbe Kerze.
    """
    je_tag: dict[date, float] = {}
    for zeitpunkt, close in samples:
        je_tag[zeitpunkt.astimezone(timezone).date()] = close
    return sorted(je_tag.items())

HISTORICAL_CALENDAR = "monatsverfaelle-dritter-freitag"
"""Welche Verfallstermine der Rueckblick unterstellt -- am Ergebnis zu
speichern (ADR 0058, Festlegung 4).

Der Live-Betrieb sieht bei vielen Titeln auch Wochenoptionen und nutzt sie
regelmaessig. Der Rueckblick nimmt sie **nicht** an: Ob ein bestimmter Titel
2022 Wochenoptionen hatte, ist nicht belegbar, der dritte Freitag dagegen
galt fuer jeden optionsfaehigen US-Titel ueber den ganzen Zeitraum. Die
Kennzahlen messen damit eine etwas andere Strategie als die gehandelte, und
wer sie liest, muss das sehen koennen.
"""

_DRITTER_FREITAG_FRUEHESTENS = 15
"""Der dritte Freitag eines Monats kann nicht vor dem 15. liegen: Faellt der
Erste auf einen Freitag, ist der dritte der 15.; spaeter kann er bis zum 21.
wandern."""


def third_friday(jahr: int, monat: int) -> date:
    """Der dritte Freitag eines Monats -- der Standard-Verfallstag."""
    erster_freitag = _DRITTER_FREITAG_FRUEHESTENS - 14
    wochentag_des_ersten, _ = calendar.monthrange(jahr, monat)
    versatz = (calendar.FRIDAY - wochentag_des_ersten) % 7
    return date(jahr, monat, erster_freitag + versatz + 14)


def monthly_expirations(*, von: date, bis: date) -> tuple[date, ...]:
    """Alle Monatsverfaelle im Zeitraum, aufsteigend, Grenzen eingeschlossen.

    **Ohne Feiertagsverschiebung.** Faellt der dritte Freitag auf einen
    Feiertag, verschiebt die Boerse den Verfall auf den Donnerstag davor. Der
    Handelskalender reicht nicht weit genug zurueck, um das nachzubilden --
    dieselbe Wochentagsnaeherung wie in ADR 0030 und aus demselben Grund. Der
    Fehler betraegt hoechstens einen Tag Restlaufzeit und ist am Ergebnis
    ueber ``HISTORICAL_CALENDAR`` vermerkt.
    """
    termine: list[date] = []
    jahr, monat = von.year, von.month
    while (jahr, monat) <= (bis.year, bis.month):
        termin = third_friday(jahr, monat)
        if von <= termin <= bis:
            termine.append(termin)
        jahr, monat = (jahr + 1, 1) if monat == 12 else (jahr, monat + 1)
    return tuple(termine)


def select_historical_expiration(
    *,
    as_of: date,
    min_days: int,
    max_days: int,
    target_days: int,
) -> date | None:
    """Der Monatsverfall im Laufzeitfenster, der der bevorzugten Restlaufzeit
    am naechsten liegt -- oder ``None``, wenn keiner darin liegt.

    Dieselbe Regel wie live (``select_expiration``): Das Fenster sagt, was
    zulaessig ist, ``target_days`` sagt, was bevorzugt wird. Bei Gleichstand
    gewinnt der **fruehere** Termin, kuerzer gebundenes Kapital bei gleichem
    Abstand.

    Ein Berichtstermin wirkt hier **nicht**. Historische Berichtstermine gibt
    es nicht ([ADR 0042](../../../docs/adr/0042-kein-historischer-earnings-filter.md)),
    und ein Filter auf das realisierte Einreichungsdatum tauschte eine
    beschriebene Verzerrung gegen eine unbeschriebene. Der Rueckblick misst
    damit Vorschlaege, die der Live-Filter teilweise verworfen haette.
    """
    zulaessig = monthly_expirations(
        von=as_of + timedelta(days=min_days), bis=as_of + timedelta(days=max_days)
    )
    if not zulaessig:
        return None
    return min(zulaessig, key=lambda termin: abs((termin - as_of).days - target_days))


DEFAULT_STRIKE_GRID: tuple[tuple[float, float], ...] = (
    (25.0, 1.0),
    (200.0, 2.5),
)
"""Strike-Abstaende nach Kursniveau: bis 25 Dollar ein Dollar, bis 200 zwei
Komma fuenf, darueber fuenf.

Eine **Annahme**, keine Messung -- die tatsaechlich gelisteten Abstaende
haengen am Titel und an der Zeit, und viele liquide Werte tragen durchgehend
Dollarabstaende. Ihre Wirkung ist gering: Gewaehlt wird nach Delta, und die
Rundung auf den naechsten Rasterpunkt verschiebt es nur wenig. Am Ergebnis
wird sie trotzdem vermerkt, wie der Kalender.
"""


def strike_step(price: float, grid: Sequence[tuple[float, float]] = DEFAULT_STRIKE_GRID) -> float:
    """Der Strike-Abstand fuer dieses Kursniveau."""
    for grenze, schritt in grid:
        if price < grenze:
            return schritt
    return 5.0


def snap_to_strike_grid(
    strike: float, *, price: float, grid: Sequence[tuple[float, float]] = DEFAULT_STRIKE_GRID
) -> float:
    """Der naechstgelegene Rasterpunkt."""
    schritt = strike_step(price, grid)
    return round(strike / schritt) * schritt


def select_historical_strike(
    *,
    spot: float,
    years_to_expiration: float,
    volatility: float,
    risk_free_rate: float,
    target_delta: float,
    grid: Sequence[tuple[float, float]] = DEFAULT_STRIKE_GRID,
) -> float | None:
    """Der Strike auf dem Raster, dessen **modelliertes** Delta dem Ziel am
    naechsten liegt (ADR 0058, Festlegung 5).

    Nach Delta und nicht nach Moneyness, weil die produktive Regel es so tut
    (``min_delta``/``max_delta``). Eine Auswahl nach reiner Moneyness braeuchte
    kein Modell, wuerde aber eine **andere Strategie messen als die
    gehandelte**.

    Gesucht wird abwaerts vom Geld: Ein Put-Verkauf steht unter dem Kurs, und
    das Delta faellt dort monoton, je weiter der Strike vom Geld weg liegt.
    Die Suche endet, sobald sie unter dem Ziel liegt -- weiter unten wird der
    Abstand nur groesser.

    ``None``, wenn kein Rasterpunkt unter dem Kurs ein Delta ueber null
    traegt: bei verschwindender Volatilitaet oder Restlaufzeit. Dann gibt es
    keinen Vorschlag, und ein erfundener waere schlimmer als keiner.
    """
    if spot <= 0.0 or volatility <= 0.0 or years_to_expiration <= 0.0:
        return None
    schritt = strike_step(spot, grid)
    ziel = abs(target_delta)
    bester: float | None = None
    bester_abstand = float("inf")
    kandidat = snap_to_strike_grid(spot, price=spot, grid=grid)
    while kandidat > 0.0:
        delta = abs(
            price_put(
                spot=spot,
                strike=kandidat,
                years_to_expiration=years_to_expiration,
                volatility=volatility,
                risk_free_rate=risk_free_rate,
            ).delta
        )
        abstand = abs(delta - ziel)
        if abstand < bester_abstand:
            bester, bester_abstand = kandidat, abstand
        if delta < ziel:
            # Ab hier faellt das Delta weiter -- der Abstand kann nur wachsen.
            break
        kandidat -= schritt
    return bester
