"""Aus ``companyfacts`` werden Jahreswerte (ADR 0032).

Reine Textarbeit, getrennt von der Abfrage -- dasselbe Muster wie beim
IBKR-Kalender: Was hier passiert, laesst sich ohne Netz pruefen, und genau
die Sonderfaelle (Tag-Wechsel, Neuausweis, Aenderungsbericht) treten selten
genug auf, dass man sie nicht abwarten will.

Drei gemessene Befunde aus ADR 0032 bestimmen den Aufbau:

1. **Kein Tag traegt fuer alle Emittenten dieselbe Groesse.** Apple hat
   ``Revenues`` nach 2018 aufgegeben, NVIDIA fuehrt es bis heute. Deshalb
   eine geordnete Liste je Rohgroesse statt eines festen Tags.
2. **Ueberlappende Tags koennen sich widersprechen.** Bei Honeywell liegen
   ``SalesRevenueNet`` und ``SalesRevenueGoodsNet`` fuer dasselbe Jahr 22
   Prozent auseinander, weil das zweite die Dienstleistungen auslaesst.
   Deshalb stehen in einer Liste nur Tags **gleicher Bedeutung** -- und ein
   Widerspruch zwischen zweien wird gemeldet statt verschwiegen.
3. **Derselbe Tag traegt fuer denselben Zeitraum verschiedene Werte.** 426
   solcher Zeitraeume allein bei Apple, durch Neuausweise und
   Aenderungsberichte. Deshalb gewinnt die zuletzt eingereichte Angabe.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from ai_trading_analyst.domain.fundamentals import (
    FigureName,
    ReportedFigure,
    SourceRef,
    TagConflict,
)

ANNUAL_FORMS = frozenset({"10-K", "10-K/A"})
"""Nur Jahresabschluesse und ihre Aenderungsberichte (ADR 0032,
Entscheidung 3). ``10-K/A`` gehoert ausdruecklich dazu: In Apples Daten
traegt ein Aenderungsbericht die berichtigte Zahl, und ohne ihn stuende der
zurueckgenommene Wert in der Kennzahl."""

MIN_ANNUAL_DAYS = 300
MAX_ANNUAL_DAYS = 400
"""Ein Geschaeftsjahr dauert 52 oder 53 Wochen, ein Kalenderjahr 365 Tage.

Die Grenzen sind noetig, weil ein 10-K **auch Quartalszahlen enthaelt** --
ohne sie liefe eine Jahresumsatzreihe still mit einzelnen Quartalswerten
darin. Weit genug fuer Rumpfgeschaeftsjahre bei einer Umstellung, eng genug,
um ein Halbjahr auszuschliessen."""

USD = "USD"
SHARES = "shares"

FIGURE_TAGS: Mapping[FigureName, tuple[str, ...]] = {
    FigureName.REVENUE: (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ),
    FigureName.NET_INCOME: ("NetIncomeLoss", "ProfitLoss"),
    FigureName.GROSS_PROFIT: ("GrossProfit",),
    FigureName.OPERATING_INCOME: ("OperatingIncomeLoss",),
    FigureName.ASSETS: ("Assets",),
    FigureName.LIABILITIES: ("Liabilities",),
    FigureName.EQUITY: (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    FigureName.CURRENT_ASSETS: ("AssetsCurrent",),
    FigureName.CURRENT_LIABILITIES: ("LiabilitiesCurrent",),
    FigureName.OPERATING_CASH_FLOW: (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    FigureName.CAPITAL_EXPENDITURE: (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ),
    FigureName.DILUTED_SHARES: ("WeightedAverageNumberOfDilutedSharesOutstanding",),
}
"""Die geordneten Tag-Listen (ADR 0032, Entscheidung 2).

**Was hier bewusst fehlt:** ``SalesRevenueGoodsNet``. Es ist der Warenumsatz
ohne Dienstleistungen und damit eine andere Groesse, nicht eine andere
Schreibweise derselben -- der Befund, an dem ADR 0032 die ganze Regel
festmacht.

Zur Reihenfolge beim Umsatz: ``ExcludingAssessedTax`` steht vor
``IncludingAssessedTax``, weil die eingesammelte Umsatzsteuer kein Erloes des
Unternehmens ist. Emittenten verwenden praktisch immer nur eines von beiden;
die Reihenfolge entscheidet also selten, muss aber festliegen."""

FIGURE_UNITS: Mapping[FigureName, str] = {
    name: (SHARES if name is FigureName.DILUTED_SHARES else USD) for name in FigureName
}

INSTANT_FIGURES = frozenset(
    {
        FigureName.ASSETS,
        FigureName.LIABILITIES,
        FigureName.EQUITY,
        FigureName.CURRENT_ASSETS,
        FigureName.CURRENT_LIABILITIES,
    }
)
"""Bestandsgroessen: Sie gelten zu einem Stichtag, nicht ueber einen Zeitraum.

XBRL fuehrt sie ohne ``start``. Wuerde man sie wie Zeitraumgroessen
behandeln, fielen sie durch die Dauerpruefung heraus und alle Bilanz-
kennzahlen fehlten -- ohne dass ein Fehler auftraete."""

SHARES_OUTSTANDING_TAG = "EntityCommonStockSharesOutstanding"
"""Deckblattwert der juengsten Einreichung, aus der ``dei``-Taxonomie.

Nicht ``WeightedAverageNumberOfDilutedSharesOutstanding``: Fuer die
Marktkapitalisierung zaehlt die Zahl der heute ausstehenden Aktien, nicht
der Jahresdurchschnitt."""

CONFLICT_TOLERANCE = 0.005
"""Ab welcher relativen Abweichung zwei Tags als widerspruechlich gelten.

Nicht null: Gerundete Angaben in Tausend gegen solche in Millionen weichen
um Kleinstbetraege ab, ohne dass jemand etwas anderes meint. Bei den 22
Prozent aus ADR 0032 spielt die Schwelle keine Rolle."""


class CompanyFactsError(ValueError):
    """Die Antwort war nicht als ``companyfacts`` lesbar."""


@dataclass(frozen=True, slots=True)
class _RawFact:
    value: float
    start: date | None
    end: date
    accession: str
    form: str
    filed: date

    @property
    def is_annual_duration(self) -> bool:
        if self.start is None:
            return False
        dauer = (self.end - self.start).days
        return MIN_ANNUAL_DAYS <= dauer <= MAX_ANNUAL_DAYS


@dataclass(frozen=True, slots=True)
class ResolvedFacts:
    """Das Ergebnis der Aufloesung: Jahreswerte je Rohgroesse."""

    cik: int
    entity_name: str
    figures: Mapping[FigureName, tuple[ReportedFigure, ...]]
    shares_outstanding: ReportedFigure | None
    conflicts: tuple[TagConflict, ...]


def resolve_company_facts(payload: Any) -> ResolvedFacts:
    """Uebersetzt eine ``companyfacts``-Antwort in Jahreswerte.

    Wirft ``CompanyFactsError``, wenn die Antwort strukturell nicht passt --
    ein leeres Ergebnis waere nicht zu unterscheiden von einem Unternehmen
    ohne Einreichungen.
    """
    if not isinstance(payload, dict):
        raise CompanyFactsError("companyfacts-Antwort ist kein Objekt")
    try:
        cik = int(payload["cik"])
        entity_name = str(payload["entityName"])
        facts = payload["facts"]
    except (KeyError, TypeError, ValueError) as error:
        raise CompanyFactsError(f"companyfacts-Antwort unvollstaendig: {error}") from error
    if not isinstance(facts, dict):
        raise CompanyFactsError("Feld 'facts' ist kein Objekt")

    us_gaap = facts.get("us-gaap")
    if not isinstance(us_gaap, dict):
        raise CompanyFactsError("Taxonomie 'us-gaap' fehlt -- kein US-GAAP-Bericht (ADR 0032 L3)")

    figures: dict[FigureName, tuple[ReportedFigure, ...]] = {}
    conflicts: list[TagConflict] = []
    for name, tags in FIGURE_TAGS.items():
        aufgeloest, widersprueche = _resolve_figure(cik, us_gaap, name, tags)
        if aufgeloest:
            figures[name] = aufgeloest
        conflicts.extend(widersprueche)

    return ResolvedFacts(
        cik=cik,
        entity_name=entity_name,
        figures=figures,
        shares_outstanding=_resolve_shares_outstanding(cik, facts.get("dei")),
        conflicts=tuple(conflicts),
    )


def _resolve_figure(
    cik: int, us_gaap: Mapping[str, Any], name: FigureName, tags: Sequence[str]
) -> tuple[tuple[ReportedFigure, ...], list[TagConflict]]:
    """Ein Jahreswert je Stichtag, nach der Reihenfolge der Tag-Liste."""
    einheit = FIGURE_UNITS[name]
    instant = name in INSTANT_FIGURES
    je_tag = {tag: _annual_facts(us_gaap.get(tag), einheit, instant) for tag in tags}

    gewaehlt: dict[date, tuple[str, _RawFact]] = {}
    for tag in tags:
        for stichtag, fakt in je_tag[tag].items():
            if stichtag not in gewaehlt:
                gewaehlt[stichtag] = (tag, fakt)

    conflicts = [
        TagConflict(
            figure=name,
            period_end=stichtag,
            chosen_tag=tag,
            chosen_value=fakt.value,
            other_tag=anderer_tag,
            other_value=je_tag[anderer_tag][stichtag].value,
        )
        for stichtag, (tag, fakt) in gewaehlt.items()
        for anderer_tag in tags
        if anderer_tag != tag
        and stichtag in je_tag[anderer_tag]
        and _weicht_ab(fakt.value, je_tag[anderer_tag][stichtag].value)
    ]

    aufgeloest = tuple(
        ReportedFigure(
            value=fakt.value,
            period_start=fakt.start,
            period_end=stichtag,
            unit=einheit,
            source=SourceRef(
                cik=cik, accession=fakt.accession, form=fakt.form, filed=fakt.filed, tag=tag
            ),
        )
        for stichtag, (tag, fakt) in sorted(gewaehlt.items())
    )
    return aufgeloest, conflicts


def _weicht_ab(gewaehlt: float, anderer: float) -> bool:
    if gewaehlt == anderer:
        return False
    if gewaehlt == 0:
        return True
    return abs(anderer - gewaehlt) / abs(gewaehlt) > CONFLICT_TOLERANCE


def _annual_facts(tag_inhalt: Any, einheit: str, instant: bool) -> dict[date, _RawFact]:
    """Jahresfakten eines Tags, je Stichtag der zuletzt eingereichte Wert."""
    if not isinstance(tag_inhalt, dict):
        return {}
    units = tag_inhalt.get("units")
    if not isinstance(units, dict):
        return {}
    je_stichtag: dict[date, _RawFact] = {}
    for eintrag in units.get(einheit, ()):
        fakt = _parse_fact(eintrag)
        if fakt is None or fakt.form not in ANNUAL_FORMS:
            continue
        if instant:
            if fakt.start is not None:
                continue
        elif not fakt.is_annual_duration:
            continue
        vorheriger = je_stichtag.get(fakt.end)
        if vorheriger is None or fakt.filed > vorheriger.filed:
            je_stichtag[fakt.end] = fakt
    return je_stichtag


def _parse_fact(eintrag: Any) -> _RawFact | None:
    """Ein einzelner Fakt, oder ``None``, wenn er unbrauchbar ist.

    Ein unlesbarer Einzelfakt bricht den Lauf **nicht** ab: ``companyfacts``
    fuehrt hunderte Tags, von denen uns eine Handvoll interessiert. Ein
    Formatfehler in einem davon darf nicht die ganze Aktie kosten. Fehlt
    dadurch ein Jahr, fehlt anschliessend die Kennzahl -- sichtbar, statt
    falsch.
    """
    if not isinstance(eintrag, dict):
        return None
    try:
        return _RawFact(
            value=float(eintrag["val"]),
            start=date.fromisoformat(eintrag["start"]) if eintrag.get("start") else None,
            end=date.fromisoformat(eintrag["end"]),
            accession=str(eintrag["accn"]),
            form=str(eintrag["form"]),
            filed=date.fromisoformat(eintrag["filed"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _resolve_shares_outstanding(cik: int, dei: Any) -> ReportedFigure | None:
    """Die juengste Aktienzahl vom Deckblatt.

    Massgeblich ist der spaeteste Stichtag, nicht die spaeteste Einreichung:
    Ein Aenderungsbericht kann heute eingereicht werden und einen alten
    Stichtag tragen.
    """
    if not isinstance(dei, dict):
        return None
    inhalt = dei.get(SHARES_OUTSTANDING_TAG)
    if not isinstance(inhalt, dict):
        return None
    units = inhalt.get("units")
    if not isinstance(units, dict):
        return None
    kandidaten = [fakt for eintrag in units.get(SHARES, ()) if (fakt := _parse_fact(eintrag))]
    if not kandidaten:
        return None
    juengster = max(kandidaten, key=lambda fakt: (fakt.end, fakt.filed))
    return ReportedFigure(
        value=juengster.value,
        period_start=None,
        period_end=juengster.end,
        unit=SHARES,
        source=SourceRef(
            cik=cik,
            accession=juengster.accession,
            form=juengster.form,
            filed=juengster.filed,
            tag=SHARES_OUTSTANDING_TAG,
        ),
    )
