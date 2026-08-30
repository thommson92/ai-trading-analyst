"""Die Kennzahlenrechnung selbst (Doc 10, Paragraph 6.9; ADR 0032, ADR 0033).

Bekommt bereits aufgeloeste Werte -- welches XBRL-Tag sie geliefert hat,
welche Einreichung gewonnen hat und wie ein Zwoelfmonatswert entstanden ist,
ist zu diesem Zeitpunkt entschieden (``infrastructure.edgar``). Hier passiert
nur noch Arithmetik, ohne Netz, ohne Datenbank und ohne Sprachmodell.

Drei Regeln durchziehen das ganze Modul:

**Kein Ersatzwert.** Fehlt eine Rohgroesse, fehlt die Kennzahl. Es gibt
keinen Rueckfall auf ein aehnliches Jahr, keinen Branchendurchschnitt und
keine Null (CLAUDE.md: fehlende Werte bleiben fehlend).

**Keine Kennzahl aus zwei Zeitraeumen.** Eine Marge aus dem Gewinn des einen
und dem Umsatz des anderen Zeitraums saehe plausibel aus und waere falsch.
Beide Rohgroessen muessen denselben Stichtag tragen. Seit ADR 0033 schuetzt
dieselbe Regel zusaetzlich davor, einen Zwoelfmonatswert gegen einen
Jahreswert zu rechnen -- ohne dass sie dafuer erweitert werden musste.

**Zwei Arten von Kennzahl, zwei Zeitbezuege.** Niveauzahlen und Bewertung
stehen auf den letzten zwoelf Monaten, Wachstumsraten auf Geschaeftsjahren
(ADR 0033). Deshalb haelt der Rechner beide Sichten getrennt: die
Jahresreihe fuer das Wachstum, den jeweils aktuellen Wert fuer alles andere.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from .values import (
    FUNDAMENTAL_ANALYSIS_VERSION,
    FigureName,
    FundamentalSnapshot,
    FundamentalStatus,
    Metric,
    MetricBasis,
    MetricName,
    MetricUnit,
    ReportedFigure,
    TagConflict,
)

MAX_BEWERTUNGSALTER_TAGE = 455
"""Wie alt die Kennzahl sein darf, die gegen einen heutigen Kurs laeuft.

Ein Geschaeftsjahr (365 Tage) plus die laengste regulaere Frist der SEC fuer
ein 10-K (90 Tage). Wer fristgerecht einreicht, unterschreitet das immer:
Spaetestens wenn diese Spanne abgelaufen ist, liegt der naechste Abschluss
vor.

Die Schranke wird gebraucht, weil die uebrige Aktualitaetspruefung (ADR 0034,
``MAX_RUECKSTAND_TAGE``) **berichtsintern** misst -- sie vergleicht eine
Rohgroesse mit dem Rest desselben Berichts. Ein Emittent, der seit Jahren
nichts mehr einreicht, ist in sich vollkommen stimmig. Gegen einen heutigen
Kurs gerechnet ergab das ein Kurs-Gewinn-Verhaeltnis von 769.230 -- die
Marktkapitalisierung von heute geteilt durch den Gewinn von 2016, mit Status
COMPLETED und ohne Hinweis.

Betroffen sind ausschliesslich die vier kursabhaengigen Kennzahlen. Die
uebrigen bleiben: Sie mischen nichts, tragen ihren Zeitraum an sich und sind
alt, aber nicht falsch."""

MAX_RUECKSTAND_TAGE = 180
"""Ab welchem Rueckstand ein Zeitraumwert als ueberholt gilt (ADR 0034).

Bezugspunkt ist der juengste Zeitraumwert des ganzen Berichts. Ein halbes
Jahr ist die Grenze, weil darunter nur Kalenderartefakte liegen koennen --
ein Geschaeftsjahr mit 52 oder 53 Wochen verschiebt das Jahresende um Tage,
nicht um Monate. Ein Rueckstand von einem halben Jahr oder mehr heisst
dagegen, dass die juengste Einreichung diese Groesse nicht mehr getragen
hat."""


@dataclass(frozen=True, slots=True)
class FundamentalParameters:
    """Parameter der Kennzahlenrechnung (ADR 0032)."""

    growth_years: int = 3
    """Spanne der Wachstumsraten in Geschaeftsjahren.

    Die Spanne wird **vollstaendig verlangt**, nicht auf das gekuerzt, was
    vorliegt. Eine Wachstumsrate ueber zwei Jahre neben einer ueber drei
    saehe wie dieselbe Kennzahl aus und waere keine -- bei einem jungen
    Unternehmen fehlt sie deshalb lieber ganz."""

    def __post_init__(self) -> None:
        if self.growth_years < 1:
            raise ValueError(f"growth_years muss mindestens 1 sein, war {self.growth_years}")


def compound_annual_growth(start_value: float, end_value: float, years: int) -> float | None:
    """Jaehrliche Wachstumsrate als Bruchteil, oder ``None``.

    ``None`` bei einem Ausgangswert von null oder darunter. Das ist keine
    Vorsicht, sondern Arithmetik: Aus einem Verlust in einen Gewinn gibt es
    keine sinnvolle Wachstumsrate -- die Formel liefert dort je nach
    Vorzeichen eine komplexe Zahl oder eine, die das Gegenteil dessen
    aussagt, was passiert ist. Ein Verlust, der sich halbiert, saehe als
    "minus 50 Prozent Wachstum" aus wie eine Verschlechterung.
    """
    if start_value <= 0 or years < 1:
        return None
    if end_value <= 0:
        # Aus Gewinn wurde Verlust. Der Verlauf ist eine Aussage, aber keine
        # Rate -- eine negative Wurzel gaebe es hier ohnehin nicht.
        return None
    rate: float = (end_value / start_value) ** (1 / years) - 1
    return rate


def _basis_von(figure: ReportedFigure, *, zwoelfmonate: bool) -> MetricBasis:
    if zwoelfmonate:
        return MetricBasis.TRAILING_TWELVE_MONTHS
    if figure.period_start is None:
        return MetricBasis.POINT_IN_TIME
    return MetricBasis.FISCAL_YEAR


def _zusammengefasst(basen: Sequence[MetricBasis]) -> MetricBasis:
    """Die Basis einer Kennzahl aus den Basen ihrer Rohgroessen.

    Ein Zwoelfmonatswert faerbt ab: Eine Eigenkapitalrendite aus
    Zwoelfmonatsgewinn und Bilanzstichtag ist eine Zwoelfmonatskennzahl, und
    sie so zu nennen ist ehrlicher, als sie nach der Bilanz zu benennen.
    """
    if MetricBasis.TRAILING_TWELVE_MONTHS in basen:
        return MetricBasis.TRAILING_TWELVE_MONTHS
    if all(basis is MetricBasis.POINT_IN_TIME for basis in basen):
        return MetricBasis.POINT_IN_TIME
    return MetricBasis.FISCAL_YEAR


class _Rechner:
    """Sammelt die Kennzahlen eines Laufs.

    Eine Klasse und keine Funktionsfolge, weil jede Kennzahl dieselben vier
    Dinge braucht -- Stichtag, Basis, Abrufzeitpunkt und die Quellen der
    beteiligten Rohgroessen -- und diese Wiederholung sonst in jeder
    einzelnen Rechnung stuende.
    """

    def __init__(
        self,
        figures: Mapping[FigureName, Sequence[ReportedFigure]],
        trailing: Mapping[FigureName, ReportedFigure],
        *,
        retrieved_at: datetime,
        currency: str,
    ) -> None:
        self._jahre = {
            name: {figure.period_end: figure for figure in figures.get(name, ())}
            for name in FigureName
        }
        self._aktuell: dict[FigureName, ReportedFigure] = {}
        self._zwoelfmonate: set[FigureName] = set()
        # Bezugspunkt fuer die Aktualitaet ist der juengste Jahresabschluss
        # des **ganzen Berichts**, nicht der der einzelnen Rohgroesse. Der
        # Unterschied entscheidet: Hat ein Emittent ein Tag aufgegeben, ist
        # dessen eigene Jahresreihe genauso alt wie sein Zwoelfmonatswert,
        # und ein Vergleich gegen sie ginge immer aus. Gemessen: Netflix
        # traegt fuer den Rohertrag ein Fenster bis 2012-09-30, Berkshire
        # fuer das Betriebsergebnis eines bis 2013-03-31 -- beide haetten
        # die Pruefung gegen die eigene Reihe bestanden.
        # Nur Zeitraumgroessen: Bilanzstichtage stammen seit ADR 0033 aus dem
        # juengsten Quartalsbericht und liegen damit auf demselben Datum wie
        # das Ende des Zwoelfmonatsfensters. Zaehlte man sie mit, waere kein
        # Fenster je "juenger" -- die Pruefung verwarf dann alle.
        juengster_abschluss = max(
            (
                figure.period_end
                for reihe in self._jahre.values()
                for figure in reihe.values()
                if figure.period_start is not None
            ),
            default=None,
        )
        self._juengster_abschluss = juengster_abschluss
        for name in FigureName:
            zwoelf = trailing.get(name)
            if (
                zwoelf is not None
                and juengster_abschluss is not None
                and zwoelf.period_end <= juengster_abschluss
            ):
                # Ein Zwoelfmonatswert, der nicht juenger ist als der letzte
                # Jahresabschluss, bringt keine Aktualitaet -- er kostete nur
                # die Pruefungssicherheit des Abschlusses (ADR 0033 L1).
                zwoelf = None
            if zwoelf is not None:
                self._aktuell[name] = zwoelf
                self._zwoelfmonate.add(name)
            elif self._jahre[name]:
                # Rueckfall auf den juengsten Jahres- bzw. Stichtagswert
                # (ADR 0033, Entscheidung 5). Er ist nicht falsch, nur
                # aelter -- und die Basis am Ergebnis sagt, welcher es ist.
                juengster = self._jahre[name][max(self._jahre[name])]
                if self.ist_ueberholt(juengster):
                    continue
                self._aktuell[name] = juengster
        self._retrieved_at = retrieved_at
        self._currency = currency
        self.metrics: dict[MetricName, Metric] = {}

    def ist_ueberholt(self, figure: ReportedFigure) -> bool:
        """Liegt dieser Wert ein halbes Jahr oder mehr hinter dem Rest?

        Der Rueckfall auf die Jahresreihe nimmt den juengsten Wert **dieser
        einen** Rohgroesse. Hat der Emittent das Tag irgendwann aufgegeben,
        ist das der juengste eines laengst beendeten Zeitraums -- und stuende
        ungekennzeichnet neben lauter aktuellen Zahlen.

        Gemessen an Cummins: ``NetIncomeLoss`` endet dort 2010-12-31, der
        uebrige Bericht 2025-12-31. Der Jahresueberschuss von 1,04 Mrd stand
        als aktuell im Ergebnis, mit Status COMPLETED, waehrend der
        tatsaechliche bei rund 3,9 Mrd liegt -- und die Wachstumsrate darauf
        beschrieb die Jahre 2008 bis 2010.

        Bestandsgroessen werden mitgemessen, obwohl sie keinen Zeitraum
        tragen. Sie stammen im Normalfall aus dem juengsten Quartalsbericht
        und liegen damit **vor** dem Bezugspunkt -- die Schranke greift bei
        ihnen gar nicht. Wo sie doch greift, ist es derselbe Fall: eine
        Bilanzposition, die der Emittent irgendwann nicht mehr getaggt hat.
        Ein Liquiditaetsgrad aus Umlaufvermoegen von 2015 waere so falsch wie
        ein Jahresueberschuss von 2010.
        """
        if self._juengster_abschluss is None:
            return False
        return (self._juengster_abschluss - figure.period_end).days >= MAX_RUECKSTAND_TAGE

    def juengster_zeitraum(self) -> date | None:
        """Das Ende des juengsten aktuellen Zeitraumwerts.

        Ersatzanker fuer den Stichtag, wenn kein Umsatz vorliegt (ADR 0034).
        Bestandsgroessen zaehlen nicht mit: Sie stammen aus dem juengsten
        Quartalsbericht und lieferten sonst einen Stichtag, zu dem es gar
        keine Ergebnisrechnung gibt.
        """
        return max(
            (
                figure.period_end
                for figure in self._aktuell.values()
                if figure.period_start is not None
            ),
            default=None,
        )

    def aktuell(self, name: FigureName) -> ReportedFigure | None:
        return self._aktuell.get(name)

    def basis(self, name: FigureName) -> MetricBasis | None:
        figure = self._aktuell.get(name)
        if figure is None:
            return None
        return _basis_von(figure, zwoelfmonate=name in self._zwoelfmonate)

    def jahreswert(self, name: FigureName, stichtag: date) -> ReportedFigure | None:
        return self._jahre[name].get(stichtag)

    def stichtage(self, name: FigureName) -> list[date]:
        return sorted(self._jahre[name])

    def berichtsjahre(self) -> list[date]:
        """Die Geschaeftsjahre, auf denen der Bericht steht.

        Der Umsatz, wo er vorliegt; sonst der Jahresueberschuss. Ohne diesen
        Rueckfall stuende bei einem Emittenten ohne Umsatzzeile eine leere
        Jahresliste neben lauter gerechneten Kennzahlen.

        Auch hier gilt die Aktualitaetsschranke aus ADR 0034. Sie ist an
        dieser Stelle nicht kosmetisch: Ohne sie meldete ein Emittent mit
        aufgegebenem Umsatz-Tag die Geschaeftsjahre 2009 bis 2012, waehrend
        jede einzelne Kennzahl daneben auf 2025 steht -- die Ausgabe zeigt
        beides nebeneinander.
        """
        for name in (FigureName.REVENUE, FigureName.NET_INCOME):
            jahre = self.stichtage(name)
            if not jahre:
                continue
            # Geprueft wird der **juengste** Stichtag, nicht jeder einzelne:
            # Die Liste soll die Historie zeigen, auf der die Wachstumsraten
            # stehen. Jedes zurueckliegende Jahr einzeln zu verwerfen liesse
            # genau ein Jahr uebrig und machte aus einer Reihe eine Zahl.
            if self.ist_ueberholt(self._jahre[name][jahre[-1]]):
                continue
            return jahre
        return []

    def add(
        self,
        name: MetricName,
        value: float | None,
        *,
        unit: MetricUnit,
        basis: MetricBasis,
        period_end: date,
        quellen: Sequence[ReportedFigure],
        period_start: date | None = None,
    ) -> None:
        """Traegt eine Kennzahl ein -- oder eben nicht.

        ``None`` fuehrt zu keinem Eintrag und zu keinem Platzhalter. Was
        fehlt, taucht ueber ``missing_metrics`` auf, nicht als Null.
        """
        if value is None:
            return
        self.metrics[name] = Metric(
            name=name,
            value=value,
            unit=unit,
            basis=basis,
            period_start=period_start,
            period_end=period_end,
            currency=self._currency if unit is MetricUnit.CURRENCY else None,
            sources=tuple(figure.source for figure in quellen),
            retrieved_at=self._retrieved_at,
        )

    def betrag(self, name: MetricName, figure_name: FigureName) -> None:
        """Eine Rohgroesse unveraendert als Kennzahl."""
        figure = self.aktuell(figure_name)
        basis = self.basis(figure_name)
        if figure is None or basis is None:
            return
        self.add(
            name,
            figure.value,
            unit=MetricUnit.CURRENCY,
            basis=basis,
            period_start=figure.period_start,
            period_end=figure.period_end,
            quellen=[figure],
        )

    def verhaeltnis(
        self,
        name: MetricName,
        zaehler_name: FigureName,
        nenner_name: FigureName,
        *,
        unit: MetricUnit,
        stichtag: date,
    ) -> None:
        """Zwei Rohgroessen desselben Stichtags ins Verhaeltnis gesetzt.

        Der Stichtagsvergleich ist die Stelle, an der ADR 0033,
        Entscheidung 6 wirkt: Faellt eine der beiden Groessen auf den
        Jahreswert zurueck und die andere nicht, tragen sie verschiedene
        Stichtage, und die Kennzahl entsteht gar nicht erst.

        Ein nichtpositiver Nenner liefert ebenfalls keine Kennzahl: Ein
        negatives Eigenkapital macht das Verhaeltnis nicht klein, sondern
        bedeutungslos -- eine Eigenkapitalrendite dreht dort das Vorzeichen
        und behauptet das Gegenteil der Lage.
        """
        zaehler, nenner = self.aktuell(zaehler_name), self.aktuell(nenner_name)
        zaehler_basis, nenner_basis = self.basis(zaehler_name), self.basis(nenner_name)
        if zaehler is None or nenner is None or zaehler_basis is None or nenner_basis is None:
            return
        if zaehler.period_end != stichtag or nenner.period_end != stichtag:
            return
        if nenner.value <= 0:
            return
        self.add(
            name,
            zaehler.value / nenner.value,
            unit=unit,
            basis=_zusammengefasst([zaehler_basis, nenner_basis]),
            period_start=zaehler.period_start,
            period_end=stichtag,
            quellen=[zaehler, nenner],
        )


def _jahresspanne(
    rechner: _Rechner, name: FigureName, jahre: int
) -> tuple[ReportedFigure, ReportedFigure] | None:
    """Aeltester und juengster Wert einer Spanne von genau ``jahre`` Jahren.

    Gesucht wird der Stichtag, der ``jahre`` Geschaeftsjahre vor dem
    juengsten liegt -- nicht schlicht der aelteste vorhandene. Fehlt ein Jahr
    dazwischen, waere die Rate sonst ueber eine andere Spanne gerechnet, als
    sie behauptet.
    """
    stichtage = rechner.stichtage(name)
    if len(stichtage) <= jahre:
        return None
    juengster = stichtage[-1]
    aeltester = stichtage[-1 - jahre]
    if juengster.year - aeltester.year != jahre:
        return None
    frueh = rechner.jahreswert(name, aeltester)
    spaet = rechner.jahreswert(name, juengster)
    if frueh is None or spaet is None:
        return None
    if rechner.ist_ueberholt(spaet):
        # Dieselbe Schranke wie beim Niveauwert, und sie wird hier eigens
        # gebraucht: Die Wachstumsrate liest die Jahresreihe unmittelbar,
        # nicht den aktuellen Wert. Ohne sie beschriebe Cummins'
        # Gewinnwachstum die Jahre 2008 bis 2010 und stuende unbeschriftet
        # neben Umsatzwachstum bis 2025.
        return None
    return frueh, spaet


def _wachstum(rechner: _Rechner, metric: MetricName, figure: FigureName, jahre: int) -> None:
    """Wachstumsrate ueber Geschaeftsjahre, nicht ueber Zwoelfmonatsfenster.

    ADR 0033, Entscheidung 4: Hier war die Jahresbasis von Anfang an
    richtig. Eine Dreijahresrate aus rollierenden Fenstern waere nicht
    besser, nur schwerer zu pruefen.
    """
    spanne = _jahresspanne(rechner, figure, jahre)
    if spanne is None:
        return
    frueh, spaet = spanne
    rechner.add(
        metric,
        compound_annual_growth(frueh.value, spaet.value, jahre),
        unit=MetricUnit.FRACTION,
        basis=MetricBasis.FISCAL_YEAR,
        period_start=frueh.period_start or frueh.period_end,
        period_end=spaet.period_end,
        quellen=[frueh, spaet],
    )


def _verwaesserung(rechner: _Rechner) -> None:
    """Aenderung der Aktienzahl -- **nur innerhalb einer Einreichung**.

    Anders als bei allen uebrigen Wachstumsraten, und der Grund dafuer ist
    gemessen: Netflix weist im 10-K von 2011 rund 63 Millionen verwaesserte
    Aktien aus und im 10-K von 2017 rund 431 Millionen. Dazwischen liegen
    Aktiensplits. Ueber Einreichungen hinweg gerechnet ergab das eine
    "Verwaesserung" von 113 Prozent im Jahr -- eine Zahl, die nach massiver
    Kapitalerhoehung aussieht und in Wahrheit einen Split misst.

    Ein einzelnes 10-K weist die Aktienzahl fuer drei Geschaeftsjahre aus,
    und zwar durchgaengig auf dem Stand nach dem Split. Innerhalb einer
    Einreichung ist der Vergleich damit sauber. Der Preis ist die kuerzere
    Spanne -- zwei Jahre statt ``growth_years``. Sie steht am Ergebnis, weil
    jede Kennzahl ihren Bezugszeitraum traegt.
    """
    nach_einreichung: dict[str, list[ReportedFigure]] = {}
    for stichtag in rechner.stichtage(FigureName.DILUTED_SHARES):
        figure = rechner.jahreswert(FigureName.DILUTED_SHARES, stichtag)
        if figure is not None:
            nach_einreichung.setdefault(figure.source.accession, []).append(figure)

    brauchbar = [reihe for reihe in nach_einreichung.values() if len(reihe) >= 2]
    if not brauchbar:
        return
    reihe = max(brauchbar, key=lambda werte: werte[-1].period_end)
    frueh, spaet = reihe[0], reihe[-1]
    if rechner.ist_ueberholt(spaet):
        # Dieselbe Schranke wie ueberall (ADR 0034). Sie wird hier eigens
        # gebraucht, weil diese Rate ihre eigene Reihe bildet und weder ueber
        # ``aktuell`` noch ueber ``_jahresspanne`` laeuft. Gemessen an Exxon:
        # Die verwaesserte Aktienzahl endet dort 2013, der uebrige Bericht
        # 2025 -- und minus 4,8 Prozent im Jahr standen unbeschriftet neben
        # Kennzahlen per 2026-03-31.
        return
    jahre = spaet.period_end.year - frueh.period_end.year
    if jahre < 1:
        return
    rechner.add(
        MetricName.SHARE_COUNT_GROWTH,
        compound_annual_growth(frueh.value, spaet.value, jahre),
        unit=MetricUnit.FRACTION,
        basis=MetricBasis.FISCAL_YEAR,
        period_start=frueh.period_start or frueh.period_end,
        period_end=spaet.period_end,
        quellen=[frueh, spaet],
    )


@dataclass(frozen=True, slots=True)
class _FreierCashflow:
    value: float
    period_start: date | None
    basis: MetricBasis
    quellen: tuple[ReportedFigure, ...]


def _freier_cashflow(rechner: _Rechner, stichtag: date) -> _FreierCashflow | None:
    """Operativer Cashflow abzueglich Investitionen ins Anlagevermoegen.

    Die Investitionen stehen in XBRL als **Auszahlung**, also positiv. Sie
    werden abgezogen, nicht addiert -- ein Vorzeichenfehler hier verdoppelte
    den freien Cashflow, statt ihn zu halbieren, und faellt an einer
    plausiblen Zahl niemandem auf.
    """
    operativ = rechner.aktuell(FigureName.OPERATING_CASH_FLOW)
    investitionen = rechner.aktuell(FigureName.CAPITAL_EXPENDITURE)
    op_basis = rechner.basis(FigureName.OPERATING_CASH_FLOW)
    inv_basis = rechner.basis(FigureName.CAPITAL_EXPENDITURE)
    if operativ is None or investitionen is None or op_basis is None or inv_basis is None:
        return None
    if operativ.period_end != stichtag or investitionen.period_end != stichtag:
        return None
    return _FreierCashflow(
        value=operativ.value - abs(investitionen.value),
        period_start=operativ.period_start,
        basis=_zusammengefasst([op_basis, inv_basis]),
        quellen=(operativ, investitionen),
    )


def compute_fundamental_snapshot(
    *,
    symbol: str,
    figures: Mapping[FigureName, Sequence[ReportedFigure]],
    retrieved_at: datetime,
    company_name: str | None = None,
    evaluated_at: datetime,
    trailing: Mapping[FigureName, ReportedFigure] | None = None,
    shares_outstanding: ReportedFigure | None = None,
    price: float | None = None,
    currency: str = "USD",
    parameters: FundamentalParameters | None = None,
    tag_conflicts: Sequence[TagConflict] = (),
) -> FundamentalSnapshot:
    """Rechnet alle Kennzahlen, die die vorliegenden Werte hergeben.

    ``price`` ist die **optionale, nicht blockierende** Eingabe aus ADR 0032:
    Fehlt er, entstehen die vier bewertungsabhaengigen Kennzahlen nicht, alle
    uebrigen vollstaendig. Das Modul beschafft selbst keinen Kurs.

    ``trailing`` sind die Zwoelfmonatswerte aus ADR 0033. Fehlen sie, rechnet
    alles auf Geschaeftsjahren weiter -- das Verfahren bleibt vollstaendig,
    nur aelter.
    """
    params = parameters or FundamentalParameters()
    rechner = _Rechner(figures, trailing or {}, retrieved_at=retrieved_at, currency=currency)

    umsatz = rechner.aktuell(FigureName.REVENUE)
    # Der Umsatz gibt den Stichtag vor, wo es ihn gibt -- er ist die Groesse,
    # gegen die die meisten Kennzahlen laufen. Er ist aber **keine
    # Bedingung** mehr (ADR 0034): Goldman Sachs traegt seine Ertraege in
    # einem Tag, das keine Umsatzzeile im hiesigen Sinn ist, und verlor
    # dadurch Jahresueberschuss, Bilanz und Cashflow gleich mit -- Status
    # INSUFFICIENT_DATA bei vollstaendig vorliegender Einreichung.
    stichtag = umsatz.period_end if umsatz is not None else rechner.juengster_zeitraum()
    if stichtag is None:
        return FundamentalSnapshot(
            symbol=symbol,
            status=FundamentalStatus.INSUFFICIENT_DATA,
            evaluated_at=evaluated_at,
            analysis_version=FUNDAMENTAL_ANALYSIS_VERSION,
            company_name=company_name,
            reason="keine auswertbaren Zeitraumangaben in den Einreichungen",
            tag_conflicts=tuple(tag_conflicts),
        )

    rechner.betrag(MetricName.REVENUE, FigureName.REVENUE)
    rechner.betrag(MetricName.NET_INCOME, FigureName.NET_INCOME)

    freier_cashflow = _freier_cashflow(rechner, stichtag)
    if freier_cashflow is not None:
        rechner.add(
            MetricName.FREE_CASH_FLOW,
            freier_cashflow.value,
            unit=MetricUnit.CURRENCY,
            basis=freier_cashflow.basis,
            period_start=freier_cashflow.period_start,
            period_end=stichtag,
            quellen=freier_cashflow.quellen,
        )
    if freier_cashflow is not None and umsatz is not None:
        rechner.add(
            MetricName.FREE_CASH_FLOW_MARGIN,
            freier_cashflow.value / umsatz.value if umsatz.value > 0 else None,
            unit=MetricUnit.FRACTION,
            # Die Basis stammt aus dem Cashflow-Paar. Das genuegt, weil der
            # Umsatz den ``stichtag`` selbst definiert und der freie
            # Cashflow nur zustande kommt, wenn er an demselben Stichtag
            # endet -- eine Vermischung ist damit ausgeschlossen.
            basis=freier_cashflow.basis,
            period_start=freier_cashflow.period_start,
            period_end=stichtag,
            quellen=[*freier_cashflow.quellen, umsatz],
        )

    for metric, zaehler, unit in (
        (MetricName.GROSS_MARGIN, FigureName.GROSS_PROFIT, MetricUnit.FRACTION),
        (MetricName.OPERATING_MARGIN, FigureName.OPERATING_INCOME, MetricUnit.FRACTION),
        (MetricName.NET_MARGIN, FigureName.NET_INCOME, MetricUnit.FRACTION),
    ):
        rechner.verhaeltnis(metric, zaehler, FigureName.REVENUE, unit=unit, stichtag=stichtag)

    rechner.verhaeltnis(
        MetricName.RETURN_ON_EQUITY,
        FigureName.NET_INCOME,
        FigureName.EQUITY,
        unit=MetricUnit.FRACTION,
        stichtag=stichtag,
    )
    rechner.verhaeltnis(
        MetricName.RETURN_ON_ASSETS,
        FigureName.NET_INCOME,
        FigureName.ASSETS,
        unit=MetricUnit.FRACTION,
        stichtag=stichtag,
    )
    rechner.verhaeltnis(
        MetricName.DEBT_TO_EQUITY,
        FigureName.LIABILITIES,
        FigureName.EQUITY,
        unit=MetricUnit.RATIO,
        stichtag=stichtag,
    )
    rechner.verhaeltnis(
        MetricName.CURRENT_RATIO,
        FigureName.CURRENT_ASSETS,
        FigureName.CURRENT_LIABILITIES,
        unit=MetricUnit.RATIO,
        stichtag=stichtag,
    )

    _wachstum(rechner, MetricName.REVENUE_GROWTH, FigureName.REVENUE, params.growth_years)
    _wachstum(rechner, MetricName.NET_INCOME_GROWTH, FigureName.NET_INCOME, params.growth_years)
    _verwaesserung(rechner)

    _bewertung(
        rechner,
        stichtag=stichtag,
        retrieved_at=retrieved_at,
        price=price,
        shares_outstanding=shares_outstanding,
        umsatz=umsatz,
        freier_cashflow=freier_cashflow,
    )

    if not rechner.metrics:
        # Ein Stichtag allein ist keine Auswertung. Ohne diese Pruefung
        # meldete eine Einreichung, aus der sich nichts rechnen laesst --
        # etwa nur ein operativer Cashflow ohne Gegenstueck -- ``COMPLETED``
        # mit null Kennzahlen und null Abdeckung, und die Sammelausgabe
        # zaehlte sie als Erfolg.
        return FundamentalSnapshot(
            symbol=symbol,
            status=FundamentalStatus.INSUFFICIENT_DATA,
            evaluated_at=evaluated_at,
            analysis_version=FUNDAMENTAL_ANALYSIS_VERSION,
            company_name=company_name,
            reason="keine Kennzahl liess sich aus den Einreichungen rechnen",
            tag_conflicts=tuple(tag_conflicts),
        )

    return FundamentalSnapshot(
        symbol=symbol,
        status=FundamentalStatus.COMPLETED,
        evaluated_at=evaluated_at,
        analysis_version=FUNDAMENTAL_ANALYSIS_VERSION,
        company_name=company_name,
        metrics=rechner.metrics,
        fiscal_years=tuple(tag.year for tag in rechner.berichtsjahre()),
        price_used=price,
        tag_conflicts=tuple(tag_conflicts),
    )


def _bewertung(
    rechner: _Rechner,
    *,
    stichtag: date,
    retrieved_at: datetime,
    price: float | None,
    shares_outstanding: ReportedFigure | None,
    umsatz: ReportedFigure | None,
    freier_cashflow: _FreierCashflow | None,
) -> None:
    """Die vier kursabhaengigen Kennzahlen (ADR 0032, Entscheidung 4).

    Faellt vollstaendig aus, wenn Kurs oder Aktienzahl fehlen -- ohne
    Ersatzwert und ohne dass die uebrigen Kennzahlen davon beruehrt waeren.
    """
    if price is None or shares_outstanding is None or price <= 0:
        return
    if (retrieved_at.date() - stichtag).days > MAX_BEWERTUNGSALTER_TAGE:
        # Der Kurs ist von heute, die Kennzahl aus einem Bericht, auf den
        # kein neuerer gefolgt ist. Die berichtsinterne Schranke aus ADR 0034
        # kann das nicht sehen: Ein Emittent, der seit Jahren nichts mehr
        # einreicht, ist in sich stimmig.
        return
    if shares_outstanding.period_end < stichtag:
        # Der Deckblattwert ist aelter als der Zeitraum, zu dem er ins
        # Verhaeltnis gesetzt wird, und beschreibt damit nicht mehr dasselbe
        # Unternehmen. Gemessen an Berkshire Hathaway: Dort ist der letzte
        # ``dei``-Wert vom 2011-04-29 und nennt 941.481 Aktien -- die
        # A-Aktien allein, vor vierzehn Jahren. Die Marktkapitalisierung
        # daraus lag um den Faktor 2.400 daneben, bei Status COMPLETED und
        # ohne einen einzigen Hinweis.
        return
    marktkapitalisierung = price * shares_outstanding.value
    if marktkapitalisierung <= 0:
        return
    rechner.add(
        MetricName.MARKET_CAPITALIZATION,
        marktkapitalisierung,
        unit=MetricUnit.CURRENCY,
        basis=MetricBasis.POINT_IN_TIME,
        period_end=shares_outstanding.period_end,
        quellen=[shares_outstanding],
    )

    def teile_durch(
        name: MetricName, nenner: float, basis: MetricBasis, quellen: Sequence[ReportedFigure]
    ) -> None:
        if nenner <= 0:
            # Ein KGV bei Verlust ist negativ und wird mit wachsendem Verlust
            # groesser -- es saehe aus wie eine guenstige Bewertung.
            return
        rechner.add(
            name,
            marktkapitalisierung / nenner,
            unit=MetricUnit.RATIO,
            basis=basis,
            period_end=stichtag,
            quellen=[shares_outstanding, *quellen],
        )

    gewinn = rechner.aktuell(FigureName.NET_INCOME)
    gewinn_basis = rechner.basis(FigureName.NET_INCOME)
    if gewinn is not None and gewinn_basis is not None and gewinn.period_end == stichtag:
        teile_durch(MetricName.PRICE_EARNINGS_RATIO, gewinn.value, gewinn_basis, [gewinn])

    umsatz_basis = rechner.basis(FigureName.REVENUE)
    if umsatz is not None and umsatz_basis is not None:
        teile_durch(MetricName.PRICE_SALES_RATIO, umsatz.value, umsatz_basis, [umsatz])

    if freier_cashflow is not None:
        teile_durch(
            MetricName.PRICE_FREE_CASH_FLOW_RATIO,
            freier_cashflow.value,
            freier_cashflow.basis,
            freier_cashflow.quellen,
        )


__all__ = [
    "FundamentalParameters",
    "compound_annual_growth",
    "compute_fundamental_snapshot",
]
