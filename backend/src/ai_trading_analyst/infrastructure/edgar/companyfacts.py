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

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
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
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
    ),
    FigureName.NET_INCOME: ("NetIncomeLoss",),
    FigureName.GROSS_PROFIT: ("GrossProfit",),
    FigureName.OPERATING_INCOME: ("OperatingIncomeLoss",),
    FigureName.ASSETS: ("Assets",),
    FigureName.LIABILITIES: ("Liabilities",),
    FigureName.EQUITY: ("StockholdersEquity",),
    FigureName.CURRENT_ASSETS: ("AssetsCurrent",),
    FigureName.CURRENT_LIABILITIES: ("LiabilitiesCurrent",),
    FigureName.OPERATING_CASH_FLOW: ("NetCashProvidedByUsedInOperatingActivities",),
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

Zur Reihenfolge beim Umsatz: ``Revenues`` steht **vorn**, und das ist
gemessen. Bei Berkshire Hathaway traegt ``RevenueFromContractWithCustomer...``
nur den Umsatz aus Kundenvertraegen -- Praemien und Kapitalertraege des
Versicherungsgeschaefts fehlen darin. Ueber sieben Geschaeftsjahre liegt es
zwischen 41 und 47 Prozent unter ``Revenues``. Wer die Vertragsumsaetze
zuerst nimmt, bekommt fuer jeden Versicherer und jedes Finanzunternehmen eine
um fast die Haelfte zu niedrige Umsatzreihe.

``Revenues`` ist die Gesamtzeile; die uebrigen sind Bestandteile, die bei
Unternehmen ohne nennenswerte vertragsfremde Erloese mit ihr zusammenfallen
-- bei Apple und NVIDIA auf den Cent. Dass beide Tags nebeneinander stehen,
bleibt trotzdem gemeldet: Ein Widerspruch heisst hier, dass der Emittent
nennenswerte Erloese ausserhalb von Kundenvertraegen hat.

``ExcludingAssessedTax`` steht vor ``IncludingAssessedTax``, weil die
eingesammelte Umsatzsteuer kein Erloes des Unternehmens ist.

**Vier Tags sind nach dem ersten Lauf gegen echte Filings wieder
herausgeflogen**, weil sie eben nicht dasselbe bedeuten -- gemessen, nicht
vermutet:

===============================================  ===================================
``ProfitLoss``                                   schliesst Minderheitenanteile ein,
                                                 ``NetIncomeLoss`` nicht. Bei
                                                 Honeywell 14 Jahre lang
                                                 abweichend, bis 2,8 Prozent.
``StockholdersEquity...NoncontrollingInterest``  dasselbe auf der Bilanzseite. Bei
                                                 Honeywell 2025 8,1 Prozent
                                                 Unterschied.
``NetCash...ContinuingOperations``               laesst aufgegebene
                                                 Geschaeftsbereiche weg. Bei
                                                 Honeywell 2023 und 2024 rund
                                                 16 Prozent Unterschied.
===============================================  ===================================

``PaymentsToAcquireProductiveAssets`` stand zunaechst mit auf dieser Liste und
ist nach der Messung **geblieben**: Ueber sechs Emittenten hinweg gibt es
keinen einzigen Zeitraum, in dem beide Capex-Tags verschiedene Werte tragen
(bei Apple zwei ueberlappende Jahre, identisch), und PepsiCo fuehrt 19 Jahre
lang ausschliesslich das zweite. Es ist eine Bezeichnungsvariante, kein
anderer Umfang -- gemessen, nicht vermutet.

Der Preis der Strenge ist Abdeckung: Ein Emittent, der nur ``ProfitLoss``
fuehrt, liefert kein Nettoergebnis. Das ist die richtige Richtung -- fehlend
statt falsch (ADR 0032 L1).

**Nicht abgeleitet wird der Rohertrag.** Honeywell und Netflix weisen fuer ihr
juengstes Geschaeftsjahr kein ``GrossProfit`` aus, und aus Umsatz minus
Herstellungskosten liesse er sich rechnen. Honeywell teilt die Kosten aber auf
``CostOfGoodsAndServicesSold`` und ``CostOfServices`` auf -- nur den ersten
abzuziehen ergaebe eine zu hohe Bruttomarge, die plausibel aussieht. Das ist
derselbe Fehler wie bei ``SalesRevenueGoodsNet``, nur eine Rechenstufe
spaeter. Die Bruttomarge fehlt dort lieber."""

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

TEILSTUECK_TOLERANZ_TAGE = 5
"""Wie weit das Vorjahresteilstueck vom laufenden abweichen darf.

Ein Geschaeftsjahr mit 52 oder 53 Wochen verschiebt die Quartalsenden um
einige Tage. Ohne Toleranz faende die Formel das Gegenstueck bei jedem
Emittenten mit Wochenkalender nicht -- mit einer grossen verrechnete sie
Zeitraeume verschiedener Laenge."""

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


TRAILING_FIGURES = frozenset(FigureName) - INSTANT_FIGURES - {FigureName.DILUTED_SHARES}
"""Rohgroessen, fuer die ein Zwoelfmonatswert gebildet wird.

Bestandsgroessen nicht -- sie gelten zu einem Stichtag und werden ohnehin
aus der juengsten Einreichung genommen. Die Aktienzahl ebenfalls nicht: Der
gewichtete Jahresdurchschnitt laesst sich nicht sinnvoll ueber drei
Einreichungen verrechnen, und die Verwaesserung wird ohnehin nur innerhalb
einer Einreichung gemessen (ADR 0032, Korrektur 3)."""


@dataclass(frozen=True, slots=True)
class ResolvedFacts:
    """Das Ergebnis der Aufloesung."""

    cik: int
    entity_name: str
    figures: Mapping[FigureName, tuple[ReportedFigure, ...]]
    """Jahresreihe je Rohgroesse -- Grundlage der Wachstumsraten."""
    shares_outstanding: ReportedFigure | None
    conflicts: tuple[TagConflict, ...]
    trailing: Mapping[FigureName, ReportedFigure] = field(default_factory=dict)
    """Zwoelfmonatswerte, wo sie sich bilden liessen (ADR 0033)."""


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
    trailing: dict[FigureName, ReportedFigure] = {}
    conflicts: list[TagConflict] = []
    for name, tags in FIGURE_TAGS.items():
        aufgeloest, widersprueche = _resolve_figure(cik, us_gaap, name, tags)
        if aufgeloest:
            figures[name] = aufgeloest
        conflicts.extend(widersprueche)
        if name in TRAILING_FIGURES:
            zwoelfmonate = _resolve_trailing(cik, us_gaap, name, tags)
            if zwoelfmonate is not None:
                trailing[name] = zwoelfmonate

    return ResolvedFacts(
        cik=cik,
        entity_name=entity_name,
        figures=figures,
        shares_outstanding=_resolve_shares_outstanding(cik, facts.get("dei")),
        conflicts=tuple(conflicts),
        trailing=trailing,
    )


def _resolve_trailing(
    cik: int, us_gaap: Mapping[str, Any], name: FigureName, tags: Sequence[str]
) -> ReportedFigure | None:
    """Der Zwoelfmonatswert, gebildet **innerhalb eines Tags**.

    Erst je Tag gerechnet (ADR 0033, Entscheidung 2). Andernfalls koennte die
    Subtraktion einen Vertragsumsatz von einem Gesamtumsatz abziehen -- der
    Berkshire-Fehler aus ADR 0032, nur als Differenz und damit mit groesserem
    Hebel.

    Ausgewaehlt wird dann **der juengste** Zwoelfmonatswert, nicht der des
    erstbesten Tags der Liste. Der Unterschied ist nicht theoretisch: Bei
    Honeywell endet ``Revenues`` im Jahr 2011, und die Tag-Reihenfolge allein
    lieferte einen Zwoelfmonatsumsatz per 2012-06-30 -- vierzehn Jahre alt,
    aus einem laengst aufgegebenen Tag, und damit das genaue Gegenteil
    dessen, wozu dieses ADR angetreten ist.

    Enden zwei Tags am selben Tag, entscheidet weiterhin die Reihenfolge der
    Liste: Dann geht es wieder um die Bedeutung, nicht um die Aktualitaet.
    Dieser Teil des Schluessels ist ausdruecklich hingeschrieben, obwohl
    ``max`` bei Gleichstand ohnehin den ersten Treffer liefert -- er haengt
    damit nicht an einem Implementierungsdetail. Eine Mutation dieser Stelle
    bleibt deshalb gruen; das ist bekannt und kein fehlender Test.
    """
    einheit = FIGURE_UNITS[name]
    kandidaten = [
        (fakt, rang, tag)
        for rang, tag in enumerate(tags)
        if (fakt := _trailing_fact(us_gaap.get(tag), einheit)) is not None
    ]
    if not kandidaten:
        return None
    fakt, _, tag = max(kandidaten, key=lambda eintrag: (eintrag[0].end, -eintrag[1]))
    return ReportedFigure(
        value=fakt.value,
        period_start=fakt.start,
        period_end=fakt.end,
        unit=einheit,
        source=SourceRef(
            cik=cik, accession=fakt.accession, form=fakt.form, filed=fakt.filed, tag=tag
        ),
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


def _parse_facts(tag_inhalt: Any, einheit: str) -> list[_RawFact]:
    """Alle lesbaren Fakten eines Tags in einer Einheit, ungefiltert."""
    if not isinstance(tag_inhalt, dict):
        return []
    units = tag_inhalt.get("units")
    if not isinstance(units, dict):
        return []
    return [fakt for eintrag in units.get(einheit, ()) if (fakt := _parse_fact(eintrag))]


def _juengste_je[S](
    fakten: Iterable[_RawFact], schluessel: Callable[[_RawFact], S]
) -> dict[S, _RawFact]:
    """Je Schluessel der zuletzt eingereichte Fakt.

    **Erst filtern, dann zusammenfassen** -- die Reihenfolge ist nicht
    beliebig. Wird zuerst ueber alle Formulare zusammengefasst, gewinnt fuer
    ein Geschaeftsjahr womoeglich ein 10-Q, das es als Vergleichszahl
    nachtraegt; ein anschliessender Filter auf Jahresabschluesse wirft den
    Zeitraum dann **ganz** heraus, statt den Jahreswert zu behalten. Beim
    Umbau auf ADR 0033 sind Apple auf diese Weise zwei Geschaeftsjahre
    abhandengekommen.
    """
    je_schluessel: dict[S, _RawFact] = {}
    for fakt in fakten:
        k = schluessel(fakt)
        vorheriger = je_schluessel.get(k)
        if vorheriger is None or _ist_juenger(fakt, vorheriger):
            je_schluessel[k] = fakt
    return je_schluessel


def _facts_by_period(tag_inhalt: Any, einheit: str) -> dict[tuple[date | None, date], _RawFact]:
    """Fakten nach Zeitraum, ueber **alle** Formulare.

    Grundlage der Zwoelfmonatsrechnung. Der Schluessel ist der ganze
    Zeitraum und nicht nur sein Ende, weil ein 10-Q zu demselben Enddatum
    ein Quartal *und* ein kumuliertes Neunmonatsstueck fuehren kann.
    """
    return _juengste_je(_parse_facts(tag_inhalt, einheit), lambda fakt: (fakt.start, fakt.end))


def _annual_facts(tag_inhalt: Any, einheit: str, instant: bool) -> dict[date, _RawFact]:
    """Die Reihe, auf der die Wachstumsraten rechnen -- Jahresabschluesse.

    Bestandsgroessen kommen dagegen aus **jedem** Formular: Eine Bilanz aus
    dem juengsten 10-Q ist der aus dem letzten 10-K ohne Einschraenkung
    vorzuziehen (ADR 0033, Entscheidung 3).
    """
    if instant:
        passend = [fakt for fakt in _parse_facts(tag_inhalt, einheit) if fakt.start is None]
    else:
        passend = [
            fakt
            for fakt in _parse_facts(tag_inhalt, einheit)
            if fakt.is_annual_duration and fakt.form in ANNUAL_FORMS
        ]
    return _juengste_je(passend, lambda fakt: fakt.end)


def _trailing_fact(tag_inhalt: Any, einheit: str) -> _RawFact | None:
    """Der Zwoelfmonatswert eines Tags (ADR 0033, Entscheidung 1).

    ``Geschaeftsjahr + laufendes Teilstueck - Vorjahresteilstueck gleicher
    Laenge``. Es werden nur Zeitraeume verrechnet, die der Emittent selbst so
    ausgewiesen hat -- nie zwei zu einem laengeren zusammengefasst. Das
    umgeht die Verwechslung von kumulierten und diskreten Quartalen, die in
    ``companyfacts`` nebeneinander stehen.
    """
    fakten = _facts_by_period(tag_inhalt, einheit)
    jahre = sorted(
        (schluessel for schluessel, fakt in fakten.items() if fakt.is_annual_duration),
        key=lambda schluessel: schluessel[1],
    )
    if not jahre:
        return None
    jahr_start, jahr_ende = jahre[-1]
    if jahr_start is None:
        return None

    laufend = sorted(
        (schluessel for schluessel in fakten if schluessel[0] == jahr_ende + timedelta(days=1)),
        key=lambda schluessel: schluessel[1],
    )
    if not laufend:
        return None
    teil_start, teil_ende = laufend[-1]
    if teil_start is None:
        return None
    tage = (teil_ende - teil_start).days

    vorjahr = [
        schluessel
        for schluessel in fakten
        if schluessel[0] == jahr_start
        and abs((schluessel[1] - jahr_start).days - tage) <= TEILSTUECK_TOLERANZ_TAGE
    ]
    if not vorjahr:
        return None

    jahr = fakten[(jahr_start, jahr_ende)]
    teil = fakten[(teil_start, teil_ende)]
    vor = fakten[vorjahr[0]]
    # Die Herkunft ist die juengste der drei Einreichungen: Sie bestimmt,
    # wie aktuell der Wert ist, und ist die einzige, die ein Leser braucht,
    # um ihn wiederzufinden.
    quelle = max((jahr, teil, vor), key=lambda fakt: (fakt.filed, fakt.accession))
    return _RawFact(
        value=jahr.value + teil.value - vor.value,
        start=teil_ende - timedelta(days=(jahr_ende - jahr_start).days),
        end=teil_ende,
        accession=quelle.accession,
        form=quelle.form,
        filed=quelle.filed,
    )


def _ist_juenger(fakt: _RawFact, vorheriger: _RawFact) -> bool:
    """Spaeteres Einreichungsdatum gewinnt, bei Gleichstand die hoehere
    Vorgangsnummer.

    Der zweite Teil ist heute ohne Wirkung -- ueber vier geprueften
    Emittenten gibt es keinen Zeitraum, in dem zwei Einreichungen desselben
    Tages verschiedene Werte tragen. Ohne ihn entschiede dort aber die
    Reihenfolge im JSON, und genau die auszuschliessen ist der Zweck dieser
    Regel.
    """
    return (fakt.filed, fakt.accession) > (vorheriger.filed, vorheriger.accession)


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
