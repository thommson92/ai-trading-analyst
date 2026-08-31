"""Auswahl und Bewertung von Cash Secured Puts (ADR 0048).

Reine Funktionen: keine Uhr, kein Netz, keine Konfiguration. Der Anbieter
ruft sie -- so, wie der EDGAR-Adapter ``compute_fundamental_snapshot`` ruft
--, und der Messlauf ueber die Watchliste ruft **dieselben**. Das ist keine
Bequemlichkeit, sondern die Lehre aus ADR 0046: Zwei Formeln haetten
Schwellen ergeben, die zu den gemessenen Werten nicht passen.

Die Auswahl laeuft in zwei Stufen, und die Reihenfolge ist der Grund, warum
sie getrennt sind:

1. ``select_expiration`` und ``select_strikes`` entscheiden **vor** dem
   Abruf, welche Kontrakte ueberhaupt notiert werden sollen. Sie kennen nur
   Kalender und Kurs.
2. ``build_options_analysis`` bewertet **nach** dem Abruf. Erst hier ist das
   Delta bekannt -- vorher gaebe es nur ein geschaetztes, und ein
   geschaetztes Delta waere ein erfundener Wert (CLAUDE.md).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime

from ai_trading_analyst.domain.technical import PriceZone, ZoneKind

from .values import (
    LiquidityGrade,
    OptionQuote,
    OptionsAnalysis,
    OptionsParameters,
    OptionsStatus,
    PutStrategy,
)

KONTRAKTGROESSE = 100
"""Aktien je Optionskontrakt an den US-Boersen. Bestimmt die Kapitalbindung
eines Cash Secured Puts und sonst nichts -- alle Renditen sind Verhaeltnisse
und von ihr unabhaengig."""

TAGE_JE_JAHR = 365
"""Die annualisierte Rendite rechnet auf Kalendertagen, nicht auf
Handelstagen: Kapital ist ueber ein Wochenende genauso gebunden wie an einem
Dienstag."""


def select_expiration(
    expirations: Iterable[date], *, as_of: date, parameters: OptionsParameters
) -> date | None:
    """Der Verfallstermin im Zielfenster, der der bevorzugten Laufzeit am
    naechsten liegt (ADR 0048, Festlegung 4).

    Zwei getrennte Groessen, und die Trennung ist ein Messbefund: Das Fenster
    sagt, was **zulaessig** ist, ``target_days_to_expiration`` sagt, was
    **bevorzugt** wird. Haengt die Wahl an der Fenstermitte, verschiebt jede
    Verbreiterung zugleich die uebliche Laufzeit -- und das Fenster musste
    verbreitert werden, damit Titel mit reinen Monatsverfaellen ueberhaupt
    einen Termin bekommen.

    Eine Regel, nicht zwei: Der Monatsverfall ist in der Regel liquider als
    eine Wochenoption, aber ihn ueber eine zweite Kalenderregel zu bevorzugen
    waere Komplexitaet ohne Beleg -- und die Liquiditaetsbewertung macht eine
    duenne Kette ohnehin sichtbar.

    Bei Gleichstand gewinnt der **fruehere** Termin: kuerzer gebundenes
    Kapital bei gleichem Abstand zur bevorzugten Laufzeit.

    ``None``, wenn das Zielfenster leer ist -- die Kette enthaelt dann keinen
    Termin zwischen ``min_days_to_expiration`` und ``max_days_to_expiration``.
    """
    mitte = parameters.target_days_to_expiration
    im_fenster = [
        termin
        for termin in expirations
        if parameters.min_days_to_expiration
        <= (termin - as_of).days
        <= parameters.max_days_to_expiration
    ]
    if not im_fenster:
        return None
    return min(im_fenster, key=lambda termin: (abs((termin - as_of).days - mitte), termin))


def select_strikes(
    strikes: Iterable[float], *, price: float, parameters: OptionsParameters
) -> tuple[float, ...]:
    """Die Strikes im Moneyness-Band, die naechsten am Kurs zuerst.

    Absteigend sortiert, damit die Obergrenze ``max_strikes`` die **weit** aus
    dem Geld liegenden Kontrakte abschneidet und nicht die naheliegenden. Wer
    ein Delta von 0,40 sucht, findet es dicht unter dem Kurs; wer bei 0,10
    landet, hat ohnehin die kleinste Praemie.
    """
    im_band = [
        strike
        for strike in strikes
        if price * parameters.min_moneyness <= strike <= price * parameters.max_moneyness
    ]
    return tuple(sorted(im_band, reverse=True)[: parameters.max_strikes])


def build_options_analysis(
    quotes: Sequence[OptionQuote],
    *,
    price: float,
    expiration: date,
    as_of: date,
    evaluated_at: datetime,
    parameters: OptionsParameters,
    zones: Sequence[PriceZone] = (),
    next_earnings_date: date | None = None,
) -> OptionsAnalysis:
    """Bewertet die abgerufenen Notierungen und waehlt die besten Vorschlaege.

    ``zones`` und ``next_earnings_date`` sind **optionale, nicht blockierende**
    Eingaben (CLAUDE.md, erste und dritte gerichtete Kopplung). "Nicht
    blockierend" heisst: Ein **fehlender** Wert haelt nichts auf. Ein
    vorhandener darf sehr wohl wirken -- ein bekannter Berichtstermin vor dem
    Verfall verwirft den Vorschlag (ADR 0048, Festlegung 7).
    """
    verworfen: list[str] = []
    strategien: list[PutStrategy] = []
    for quote in quotes:
        strategie = _bewerte(
            quote,
            price=price,
            as_of=as_of,
            parameters=parameters,
            zones=zones,
            next_earnings_date=next_earnings_date,
            verworfen=verworfen,
        )
        if strategie is not None:
            strategien.append(strategie)

    if not strategien:
        return unzureichend(
            _verwerfungsgrund(len(quotes), verworfen, parameters),
            evaluated_at=evaluated_at,
            parameters=parameters,
            underlying_price=price,
            expiration=expiration,
        )

    strategien.sort(
        key=lambda s: (s.liquidity is LiquidityGrade.POOR, -s.annualized_return, -s.strike)
    )
    return OptionsAnalysis(
        status=OptionsStatus.COMPLETED,
        evaluated_at=evaluated_at,
        underlying_price=price,
        expiration=expiration,
        strategies=tuple(strategien[: parameters.max_suggestions]),
        parameters=parameters.as_mapping(),
    )


def unzureichend(
    reason: str,
    *,
    evaluated_at: datetime,
    parameters: OptionsParameters,
    underlying_price: float | None = None,
    expiration: date | None = None,
) -> OptionsAnalysis:
    """Ein Ergebnis ohne Vorschlaege -- mit Grund, nie stillschweigend.

    Auch von den Aufrufern gebraucht, die schon vor dem Abruf abbrechen: kein
    Verfallstermin im Zielfenster, kein Strike im Moneyness-Band. Der
    Aktienkurs bleibt erhalten, weil er auch dann belegt, worauf gerechnet
    wurde.
    """
    return OptionsAnalysis(
        status=OptionsStatus.INSUFFICIENT_DATA,
        evaluated_at=evaluated_at,
        underlying_price=underlying_price,
        expiration=expiration,
        reason=reason,
        parameters=parameters.as_mapping(),
    )


_OHNE_DELTA = "ohne_delta"
_DELTA_AUSSERHALB = "delta_ausserhalb"
_OHNE_MITTELWERT = "ohne_mittelwert"
_ABGELAUFEN = "abgelaufen"
_EARNINGS_IM_FENSTER = "earnings_im_fenster"


def _bewerte(
    quote: OptionQuote,
    *,
    price: float,
    as_of: date,
    parameters: OptionsParameters,
    zones: Sequence[PriceZone],
    next_earnings_date: date | None,
    verworfen: list[str],
) -> PutStrategy | None:
    """Ein einzelner Kontrakt, oder ``None`` mit vermerktem Grund."""
    restlaufzeit = (quote.expiration - as_of).days
    if restlaufzeit <= 0:
        verworfen.append(_ABGELAUFEN)
        return None
    if quote.delta is None:
        verworfen.append(_OHNE_DELTA)
        return None
    delta = abs(quote.delta)
    if not parameters.min_delta <= delta <= parameters.max_delta:
        verworfen.append(_DELTA_AUSSERHALB)
        return None
    # Der Mittelwert **ist** die Praemie (ADR 0048, Festlegung 6). Er setzt
    # Geld- **und** Briefkurs voraus; fehlt einer, gibt es keinen Mittelwert
    # und damit keine Rendite zu rechnen.
    praemie = quote.mid
    if praemie is None:
        verworfen.append(_OHNE_MITTELWERT)
        return None
    # Quartalszahlen vor dem Verfall schliessen den Vorschlag aus
    # (Entscheidung des Projektinhabers, 2026-08-31; ADR 0048, Festlegung 7).
    #
    # Der Grund steht in den Messdaten: Die drei hoechsten
    # Praemienrenditen der Watchliste am 2026-08-31 -- ORCL 71 %, STX 72 %,
    # MU 64 % -- gehoerten alle Titeln, die innerhalb der Laufzeit
    # berichteten. Das ist keine Gelegenheit, sondern die Verguetung fuer
    # genau das Risiko, das ein Put-Verkaeufer traegt. Ohne diese Regel
    # fuehrten sie die Rangliste an und trieben zugleich den Teilwert der
    # Optionsattraktivitaet nach oben.
    im_laufzeitfenster = _earnings_im_laufzeitfenster(
        next_earnings_date, as_of=as_of, expiration=quote.expiration
    )
    if im_laufzeitfenster:
        verworfen.append(_EARNINGS_IM_FENSTER)
        return None
    einfache_rendite = praemie / quote.strike
    warnungen = _liquiditaetswarnungen(quote, parameters)
    return PutStrategy(
        expiration=quote.expiration,
        days_to_expiration=restlaufzeit,
        strike=quote.strike,
        distance_to_price_pct=(price - quote.strike) / price,
        premium=praemie,
        break_even=quote.strike - praemie,
        capital_at_risk=quote.strike * KONTRAKTGROESSE,
        simple_return=einfache_rendite,
        annualized_return=einfache_rendite * TAGE_JE_JAHR / restlaufzeit,
        liquidity=_liquiditaetsstufe(warnungen),
        liquidity_warnings=warnungen,
        bid=quote.bid,
        ask=quote.ask,
        mid=quote.mid,
        delta=delta,
        implied_volatility=quote.implied_volatility,
        open_interest=quote.open_interest,
        volume=quote.volume,
        distance_to_support_pct=_abstand_zur_unterstuetzung(quote.strike, zones),
        earnings_within_term=im_laufzeitfenster,
    )


def _liquiditaetswarnungen(
    quote: OptionQuote, parameters: OptionsParameters
) -> tuple[str, ...]:
    """Die verletzten Bedingungen im Klartext.

    Nicht geliefert heisst nicht verletzt: Ein fehlendes Open Interest
    erzeugt keine Warnung (CLAUDE.md -- fehlende Werte bestrafen nicht). Es
    fehlt dafuer sichtbar am Vorschlag.
    """
    warnungen: list[str] = []
    mitte = quote.mid
    if mitte is not None and mitte > 0 and quote.ask is not None and quote.bid is not None:
        spanne = (quote.ask - quote.bid) / mitte
        if spanne > parameters.max_relative_spread:
            warnungen.append(f"Geld-Brief-Spanne {spanne:.1%}")
    if quote.open_interest is not None and quote.open_interest < parameters.min_open_interest:
        warnungen.append(f"Open Interest {quote.open_interest}")
    if quote.volume is not None and quote.volume < parameters.min_volume:
        warnungen.append(f"Tagesvolumen {quote.volume}")
    return tuple(warnungen)


def _liquiditaetsstufe(warnungen: Sequence[str]) -> LiquidityGrade:
    if not warnungen:
        return LiquidityGrade.GOOD
    if len(warnungen) == 1:
        return LiquidityGrade.ACCEPTABLE
    return LiquidityGrade.POOR


def _abstand_zur_unterstuetzung(
    strike: float, zones: Sequence[PriceZone]
) -> float | None:
    """Vorzeichenbehafteter Abstand zur naechstgelegenen Unterstuetzungszone.

    Betrachtet werden ausschliesslich Zonen der Art ``SUPPORT`` -- die
    einzigen, die fuer einen Strike unterhalb des Kurses ein Halt sein
    koennen. Positiv heisst: Der Strike liegt **ueber** der Zone, sie muesste
    also erst erreicht werden, nachdem angedient wurde. Negativ heisst: Der
    Strike liegt darunter, die Zone muesste vorher brechen.
    """
    stuetzen = [zone for zone in zones if zone.kind is ZoneKind.SUPPORT]
    if not stuetzen:
        return None
    naechste = min(stuetzen, key=lambda zone: abs(_zonenabstand(strike, zone)))
    return _zonenabstand(strike, naechste)


def _zonenabstand(strike: float, zone: PriceZone) -> float:
    """``0.0`` innerhalb der Zone -- dieselbe Lesart wie ``PriceZone.distance_pct``."""
    if strike > zone.upper:
        return (strike - zone.upper) / strike
    if strike < zone.lower:
        return (strike - zone.lower) / strike
    return 0.0


def _earnings_im_laufzeitfenster(
    next_earnings_date: date | None, *, as_of: date, expiration: date
) -> bool | None:
    """``None`` heisst "kein Termin bekannt" und nicht "kein Termin".

    Der Unterschied ist hier folgenreich: ``True`` verwirft den Vorschlag,
    ``False`` und ``None`` lassen ihn stehen. Ein unbekannter Termin darf
    nicht wie ein belegter Nichttermin wirken -- aber er darf auch nicht
    ausschliessen, denn dann bliebe von der Optionsanalyse bei jedem Symbol
    ohne Earnings-Abdeckung nichts uebrig.
    """
    if next_earnings_date is None:
        return None
    return as_of <= next_earnings_date <= expiration


def _verwerfungsgrund(
    anzahl: int, verworfen: Sequence[str], parameters: OptionsParameters
) -> str:
    """Warum kein Vorschlag uebrig blieb -- benannt, nicht pauschal.

    Der Unterschied zaehlt: "keine Notierung lieferte ein Delta" ist ein
    Befund ueber die Marktdatenberechtigung oder die Tageszeit, "keine lag im
    Delta-Band" ist ein Befund ueber die Kette.
    """
    if anzahl == 0:
        return "der Anbieter lieferte zu den angefragten Strikes keine einzige Notierung"
    gruende = {
        _OHNE_DELTA: "lieferte ein Delta",
        _DELTA_AUSSERHALB: (
            f"lag im Delta-Band {parameters.min_delta:.2f} bis {parameters.max_delta:.2f}"
        ),
        _OHNE_MITTELWERT: "hatte Geld- und Briefkurs",
        _ABGELAUFEN: "war noch nicht verfallen",
        _EARNINGS_IM_FENSTER: "lag vor dem naechsten Berichtstermin",
    }
    # Bei Gleichstand entscheidet die Reihenfolge in ``gruende`` und nicht die
    # Laune der Mengeniteration -- derselbe Lauf soll denselben Satz ergeben.
    haeufigster = max(gruende, key=lambda grund: verworfen.count(grund))
    return f"keine der {anzahl} Notierungen {gruende[haeufigster]}"
