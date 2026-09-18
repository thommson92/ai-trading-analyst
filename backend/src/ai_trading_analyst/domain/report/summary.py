"""Die Kurzfassung eines gespeicherten Berichts (ADR 0062).

Was eine Liste ueber einen Kandidaten sagt, ohne das Dokument zu oeffnen --
und **aus dem Dokument** gelesen, nicht aus den Analysezeilen daneben: Das
Dokument ist der eingefrorene Stand des Laufs (ADR 0039), und eine Liste,
die etwas anderes zeigte als die Einzelsicht, waere eine zweite Wahrheit.

Gelesen wird **defensiv**: Ein Abschnitt, der ``verfuegbar: false`` traegt
oder in einer aelteren Schemafassung anders heisst, ergibt ``None`` -- kein
Fehler, kein Ersatzwert. Die Kenntnis des Dokumentaufbaus gehoert hierher,
in die Domain, nicht in die Persistenz und nicht in die API.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ai_trading_analyst.domain.backtesting.options_metrics import kombinationskuerzel
from ai_trading_analyst.domain.screening import SignalType

from .values import ReportSection


@dataclass(frozen=True, slots=True)
class PutSummary:
    """Der beste Put-Vorschlag, wie ihn die Meldung nennt (ADR 0055)."""

    strike: float
    expiration: str
    days_to_expiration: int
    premium: float
    """Je Aktie, nicht je Kontrakt -- so steht sie im Bericht."""
    annualized_return: float | None
    distance_to_price_pct: float | None
    liquidity: str | None
    earnings_within_term: bool | None


@dataclass(frozen=True, slots=True)
class ReportSummaryFields:
    """Was eine Kandidatenkarte zeigt. Jedes Feld ``None``, wenn der
    Bericht dazu nichts sagt."""

    company_name: str | None = None
    close: float | None = None
    decision_candle_at: str | None = None
    signal_letters: str | None = None
    false_signal_risk: str | None = None
    earnings_status: str | None = None
    earnings_next_date: str | None = None
    earnings_candles_until: int | None = None
    options_status: str | None = None
    options_reason: str | None = None
    put_suggestion: PutSummary | None = None


def extract_summary_fields(document: Mapping[str, Any]) -> ReportSummaryFields:
    """Liest die Kurzfassung aus einem gespeicherten Dokument."""
    unternehmen = _abschnitt(document, ReportSection.SYMBOL_UND_UNTERNEHMEN)
    signale = _abschnitt(document, ReportSection.TECHNISCHE_SIGNALE)
    earnings = _abschnitt(document, ReportSection.EARNINGS_STATUS)
    lage = _abschnitt(document, ReportSection.TECHNISCHE_LAGE)
    puts = _abschnitt(document, ReportSection.PUT_STRATEGIEN)

    deterministisch = _objekt(lage, "deterministisch")
    einordnung = _objekt(lage, "einordnung")
    vorschlaege = _liste(puts, "vorschlaege")
    erster = _als_objekt(vorschlaege[0]) if vorschlaege else None

    return ReportSummaryFields(
        company_name=_text(unternehmen, "unternehmen"),
        close=_zahl(deterministisch, "close"),
        decision_candle_at=_text(deterministisch, "candle_timestamp"),
        signal_letters=_buchstaben(signale),
        false_signal_risk=_text(einordnung, "false_signal_risk"),
        earnings_status=_text(earnings, "status"),
        earnings_next_date=_text(earnings, "next_earnings_date"),
        earnings_candles_until=_ganzzahl(earnings, "candles_until_earnings"),
        options_status=_text(puts, "status"),
        options_reason=_text(puts, "grund"),
        put_suggestion=_put(erster),
    )


def _put(vorschlag: Mapping[str, Any] | None) -> PutSummary | None:
    if vorschlag is None:
        return None
    strike = _zahl(vorschlag, "strike")
    expiration = _text(vorschlag, "expiration")
    tage = _ganzzahl(vorschlag, "days_to_expiration")
    praemie = _zahl(vorschlag, "premium")
    if strike is None or expiration is None or tage is None or praemie is None:
        # Ein Vorschlag ohne seine vier Kerngroessen ist keiner -- lieber
        # keine Karte als eine mit Strich an der Stelle, um die es geht.
        return None
    return PutSummary(
        strike=strike,
        expiration=expiration,
        days_to_expiration=tage,
        premium=praemie,
        annualized_return=_zahl(vorschlag, "annualized_return"),
        distance_to_price_pct=_zahl(vorschlag, "distance_to_price_pct"),
        liquidity=_text(vorschlag, "liquidity"),
        earnings_within_term=_wahrheit(vorschlag, "earnings_within_term"),
    )


def _buchstaben(signale: Any) -> str | None:
    """Die Signalbuchstaben aus den gespeicherten Ereignissen -- dieselbe
    Zuordnung wie im Backtest (``SIGNAL_BUCHSTABEN``)."""
    if not isinstance(signale, Sequence) or isinstance(signale, str):
        return None
    typen: set[SignalType] = set()
    for eintrag in signale:
        wert = _text(_als_objekt(eintrag), "signal_type")
        if wert is None:
            continue
        try:
            typen.add(SignalType(wert))
        except ValueError:
            continue  # ein Typ aus einer spaeteren Regelfassung: nicht raten
    return kombinationskuerzel(frozenset(typen)) if typen else None


def _abschnitt(document: Mapping[str, Any], section: ReportSection) -> Any:
    """Der Inhalt eines Abschnitts -- ``None``, wenn er fehlt.

    Bewusst **nicht** an ``verfuegbar`` gebunden: Ein Optionsergebnis ohne
    Vorschlag gilt im Dokument als nicht verfuegbar, traegt aber Status und
    Grund -- und genau die soll eine Karte nennen, statt zu schweigen."""
    abschnitte = _als_objekt(document.get("abschnitte"))
    eintrag = _als_objekt(abschnitte.get(section.value)) if abschnitte is not None else None
    return eintrag.get("inhalt") if eintrag is not None else None


def _als_objekt(wert: Any) -> Mapping[str, Any] | None:
    return wert if isinstance(wert, Mapping) else None


def _objekt(wert: Any, schluessel: str) -> Mapping[str, Any] | None:
    objekt = _als_objekt(wert)
    return _als_objekt(objekt.get(schluessel)) if objekt is not None else None


def _liste(wert: Any, schluessel: str) -> list[Any]:
    objekt = _als_objekt(wert)
    inhalt = objekt.get(schluessel) if objekt is not None else None
    return list(inhalt) if isinstance(inhalt, Sequence) and not isinstance(inhalt, str) else []


def _text(wert: Any, schluessel: str) -> str | None:
    objekt = _als_objekt(wert)
    inhalt = objekt.get(schluessel) if objekt is not None else None
    return inhalt if isinstance(inhalt, str) else None


def _zahl(wert: Any, schluessel: str) -> float | None:
    objekt = _als_objekt(wert)
    inhalt = objekt.get(schluessel) if objekt is not None else None
    return (
        float(inhalt) if isinstance(inhalt, int | float) and not isinstance(inhalt, bool) else None
    )


def _ganzzahl(wert: Any, schluessel: str) -> int | None:
    objekt = _als_objekt(wert)
    inhalt = objekt.get(schluessel) if objekt is not None else None
    return inhalt if isinstance(inhalt, int) and not isinstance(inhalt, bool) else None


def _wahrheit(wert: Any, schluessel: str) -> bool | None:
    objekt = _als_objekt(wert)
    inhalt = objekt.get(schluessel) if objekt is not None else None
    return inhalt if isinstance(inhalt, bool) else None
