"""Wertobjekte der deterministischen Fundamentalanalyse (Doc 10, Paragraph 6.9).

Reine Berechnung ohne Infrastruktur und ohne Sprachmodell -- die
deterministische Haelfte des Fundamental Analysis Module (ADR 0032). Die
KI-Einordnung entsteht getrennt und bekommt diese Werte ausschliesslich zur
Einordnung, nie zur Veraenderung (CLAUDE.md, zentrale Regel).

Doc 10, Paragraph 6.9 verlangt an **jeder** Kennzahl Bezugszeitraum,
Einheit, Waehrung, Quelle und Abrufzeitpunkt. Das ist hier kein Beiwerk,
sondern Teil des Wertobjekts: ``Metric`` laesst sich ohne diese Angaben
nicht bilden.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from types import MappingProxyType

FUNDAMENTAL_ANALYSIS_VERSION = "fundamental-v2"
"""Version des Auswertungsverfahrens, an jedem Ergebnis gespeichert
(CLAUDE.md: Versionierung).

Aendert sich eine Tag-Liste oder eine Aufloesungsregel, steigt diese Nummer.
Eine Umsatzwachstumsrate nach geaenderter Tag-Liste ist eine **andere Zahl**,
und man muss einem gespeicherten Ergebnis ansehen koennen, nach welcher Regel
sie entstanden ist -- ADR 0032 zeigt an Honeywell, dass zwei vertretbare
Tag-Listen um 22 Prozent auseinanderliegen koennen.

``v2`` gegenueber ``v1``: Niveauzahlen und Bewertung stehen auf den letzten
zwoelf Monaten statt auf dem letzten Geschaeftsjahr (ADR 0033). Bei Apple
sind das 466,8 statt 416,2 Milliarden Umsatz -- dieselbe Kennzahl, ein
anderer Zeitraum. Wachstumsraten bleiben auf Geschaeftsjahren."""


class FundamentalStatus(StrEnum):
    """Muster ``ResearchStatus``/``TechnicalStatus`` -- kein stilles Fehlen."""

    COMPLETED = "COMPLETED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    """Die Einreichungen reichen fuer keine einzige Kennzahl (CLAUDE.md: ohne
    belastbare Grundlage lautet das Ergebnis INSUFFICIENT_DATA).

    Es gibt hier bewusst **kein** ``UNAVAILABLE``: Ein Ausfall der Quelle
    verlaesst diesen Weg als ``FundamentalDataProviderError``, den der
    Application-Layer je Aktie isoliert. Ein Statuswert, den nichts erzeugt,
    saehe wie eine Zusicherung aus, die niemand einloest."""


class FigureName(StrEnum):
    """Die Rohgroessen, aus denen die Kennzahlen entstehen.

    Getrennt von ``MetricName``: Eine Rohgroesse ist etwas, das in einer
    Einreichung **steht**; eine Kennzahl ist etwas, das daraus **folgt**. Die
    Zuordnung zu XBRL-Tags liegt in der Infrastruktur, nicht hier -- die
    Domain kennt keinen Anbieter (Doc 10, Paragraph 9).
    """

    REVENUE = "REVENUE"
    NET_INCOME = "NET_INCOME"
    GROSS_PROFIT = "GROSS_PROFIT"
    OPERATING_INCOME = "OPERATING_INCOME"
    ASSETS = "ASSETS"
    LIABILITIES = "LIABILITIES"
    EQUITY = "EQUITY"
    CURRENT_ASSETS = "CURRENT_ASSETS"
    CURRENT_LIABILITIES = "CURRENT_LIABILITIES"
    OPERATING_CASH_FLOW = "OPERATING_CASH_FLOW"
    CAPITAL_EXPENDITURE = "CAPITAL_EXPENDITURE"
    DILUTED_SHARES = "DILUTED_SHARES"


class MetricName(StrEnum):
    """Die Kennzahlen, die dieses Modul rechnet.

    Abgeleitet aus den fuenfzehn Analysebereichen in Doc 10, Paragraph 6.9.
    Nicht enthalten sind die sechs, die keine Rechenaufgabe sind -- vier
    Urteile fuer die KI-Haelfte und der Wettbewerbsvergleich, dem die
    Vergleichsgruppe fehlt (ADR 0032, L5).
    """

    REVENUE = "REVENUE"
    REVENUE_GROWTH = "REVENUE_GROWTH"
    NET_INCOME = "NET_INCOME"
    NET_INCOME_GROWTH = "NET_INCOME_GROWTH"
    FREE_CASH_FLOW = "FREE_CASH_FLOW"
    GROSS_MARGIN = "GROSS_MARGIN"
    OPERATING_MARGIN = "OPERATING_MARGIN"
    NET_MARGIN = "NET_MARGIN"
    FREE_CASH_FLOW_MARGIN = "FREE_CASH_FLOW_MARGIN"
    RETURN_ON_EQUITY = "RETURN_ON_EQUITY"
    RETURN_ON_ASSETS = "RETURN_ON_ASSETS"
    DEBT_TO_EQUITY = "DEBT_TO_EQUITY"
    CURRENT_RATIO = "CURRENT_RATIO"
    SHARE_COUNT_GROWTH = "SHARE_COUNT_GROWTH"
    """Verwaesserung. Ein **positiver** Wert heisst mehr Aktien, also
    Verwaesserung; ein negativer heisst Rueckkauf. Die Richtung steht hier,
    weil sie sich aus dem Namen nicht ergibt."""
    MARKET_CAPITALIZATION = "MARKET_CAPITALIZATION"
    PRICE_EARNINGS_RATIO = "PRICE_EARNINGS_RATIO"
    PRICE_SALES_RATIO = "PRICE_SALES_RATIO"
    PRICE_FREE_CASH_FLOW_RATIO = "PRICE_FREE_CASH_FLOW_RATIO"


class MetricBasis(StrEnum):
    """Worauf sich eine Kennzahl zeitlich stuetzt (ADR 0033).

    Ein eigenes Feld und keine Ableitung aus dem Zeitraum: Ein
    Zwoelfmonatsfenster und ein Geschaeftsjahr sind **beide** rund 365 Tage
    lang und am Zeitraum allein nicht zu unterscheiden. Ohne dieses Feld
    liesse sich Einschraenkung L2 aus ADR 0033 im Bericht nicht aufloesen.
    """

    TRAILING_TWELVE_MONTHS = "TRAILING_TWELVE_MONTHS"
    FISCAL_YEAR = "FISCAL_YEAR"
    """Rueckfall, wenn sich kein Zwoelfmonatswert bilden liess -- oder der
    Regelfall bei den Wachstumsraten, die bewusst auf Geschaeftsjahren
    rechnen."""
    POINT_IN_TIME = "POINT_IN_TIME"
    """Bestandsgroessen und alles, was daraus folgt: Sie gelten zu einem
    Stichtag, nicht ueber einen Zeitraum."""


class MetricUnit(StrEnum):
    """Einheit einer Kennzahl (Doc 10, Paragraph 6.9).

    ``RATIO`` ist ein dimensionsloses Verhaeltnis (KGV, Verschuldungsgrad),
    ``FRACTION`` ein Anteil als Bruchteil -- 0,25 sind 25 Prozent. Getrennt,
    weil eine Marge von 0,25 und ein KGV von 0,25 voellig Verschiedenes
    heissen und eine gemeinsame Einheit die Verwechslung einlaedte.
    """

    CURRENCY = "CURRENCY"
    FRACTION = "FRACTION"
    RATIO = "RATIO"
    SHARES = "SHARES"


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Die Einreichung, aus der ein Rohwert stammt (Doc 10: Quelle).

    ``accession`` ist die Vorgangsnummer der Einreichung bei der SEC. Sie
    identifiziert das Dokument eindeutig und laesst sich in eine Adresse
    uebersetzen -- eine gespeicherte URL waere dagegen bei jeder Aenderung
    der EDGAR-Adressstruktur still falsch.
    """

    cik: int
    accession: str
    form: str
    filed: date
    tag: str

    @property
    def url(self) -> str:
        """Adresse der Einreichung im EDGAR-Archiv."""
        ohne_striche = self.accession.replace("-", "")
        return (
            f"https://www.sec.gov/Archives/edgar/data/{self.cik}/"
            f"{ohne_striche}/{self.accession}-index.htm"
        )


@dataclass(frozen=True, slots=True)
class ReportedFigure:
    """Ein einzelner, bereits aufgeloester Rohwert aus einer Einreichung.

    "Aufgeloest" heisst: Tag-Liste und Einreichungsdatum sind bereits
    angewendet (ADR 0032, Entscheidungen 2 und 3). Was hier ankommt, ist
    genau ein Wert je Zeitraum.

    ``period_start`` ist ``None`` bei Bestandsgroessen -- eine Bilanzposition
    gilt zu einem Stichtag, nicht ueber einen Zeitraum. Das unterscheidet
    "Zeitraum beginnt unbekannt" nicht von "hat keinen Anfang"; es gibt
    keinen zweiten Fall, XBRL kennt zu jedem Zeitraumwert den Beginn.
    """

    value: float
    period_start: date | None
    period_end: date
    unit: str
    source: SourceRef

    @property
    def fiscal_year(self) -> int:
        """Das Jahr, dem der Wert zugerechnet wird -- das des Endes.

        Nicht das des Beginns: Ein Geschaeftsjahr, das im Oktober 2023
        beginnt und im September 2024 endet, ist das Geschaeftsjahr 2024.
        """
        return self.period_end.year


@dataclass(frozen=True, slots=True)
class Metric:
    """Eine gerechnete Kennzahl samt vollstaendiger Herkunft.

    Die fuenf von Doc 10, Paragraph 6.9 geforderten Angaben sind Pflichtfelder
    und keine Zusatzinformation: ``period_start``/``period_end``
    (Bezugszeitraum), ``unit`` (Einheit), ``currency`` (Waehrung),
    ``sources`` (Quelle) und ``retrieved_at`` (Abrufzeitpunkt).
    """

    name: MetricName
    value: float
    unit: MetricUnit
    basis: MetricBasis
    period_end: date
    sources: tuple[SourceRef, ...]
    retrieved_at: datetime
    period_start: date | None = None
    currency: str | None = None
    """Nur bei ``MetricUnit.CURRENCY`` gesetzt. Ein Verhaeltnis hat keine
    Waehrung, und ein Pflichtfeld haette dort eine erfunden."""

    def __post_init__(self) -> None:
        if not self.sources:
            raise ValueError(
                f"Kennzahl {self.name} ohne Quelle -- Doc 10, Paragraph 6.9 "
                "verlangt sie an jeder Kennzahl"
            )
        if (self.unit is MetricUnit.CURRENCY) != (self.currency is not None):
            raise ValueError(
                f"Kennzahl {self.name}: Waehrung und Einheit passen nicht zusammen "
                f"(unit={self.unit}, currency={self.currency})"
            )


@dataclass(frozen=True, slots=True)
class TagConflict:
    """Zwei Tags derselben Liste widersprechen sich fuer denselben Zeitraum.

    Der Befund, der ADR 0032 zugrunde liegt: Bei Honeywell liefern zwei
    vertretbare Umsatz-Tags fuer dasselbe Geschaeftsjahr 32,350 gegen 25,242
    Milliarden. Ein solcher Widerspruch ist ein Hinweis darauf, dass die
    Tag-Liste fuer diesen Emittenten nicht passt -- er wird deshalb
    ausgewiesen und nicht stillschweigend zugunsten des ersten Tags
    aufgeloest.

    Gefuehrt wird die **Rohgroesse**, nicht die Kennzahl: Der erste Lauf
    gegen echte Apple-Daten meldete einen Widerspruch zwischen zwei
    Cashflow-Tags als Umsatzwiderspruch, weil es zu einigen Rohgroessen
    keine gleichnamige Kennzahl gibt. Eine Zuordnung, die im Zweifel
    irgendwohin zeigt, ist schlechter als keine.
    """

    figure: FigureName
    period_end: date
    chosen_tag: str
    chosen_value: float
    other_tag: str
    other_value: float

    @property
    def relative_deviation(self) -> float | None:
        """Abweichung als Bruchteil des gewaehlten Wertes.

        ``None``, wenn der gewaehlte Wert null ist -- ein Verhaeltnis waere
        dort nicht gebildet, sondern erfunden.
        """
        if self.chosen_value == 0:
            return None
        return abs(self.other_value - self.chosen_value) / abs(self.chosen_value)


@dataclass(frozen=True, slots=True)
class FundamentalSnapshot:
    """Das Ergebnis der deterministischen Fundamentalanalyse einer Aktie."""

    symbol: str
    status: FundamentalStatus
    evaluated_at: datetime
    analysis_version: str = FUNDAMENTAL_ANALYSIS_VERSION
    metrics: Mapping[MetricName, Metric] = field(default_factory=dict)
    fiscal_years: tuple[int, ...] = ()
    """Die Geschaeftsjahre, fuer die Jahreszahlen vorlagen -- aufsteigend."""
    price_used: float | None = None
    """Der Kurs, mit dem die Bewertungskennzahlen gerechnet wurden, oder
    ``None``, wenn keiner hineingereicht wurde (ADR 0032, Entscheidung 4).
    Gespeichert, weil sich eine Bewertungskennzahl sonst spaeter nicht mehr
    nachrechnen laesst."""
    tag_conflicts: tuple[TagConflict, ...] = ()
    reason: str | None = None
    """Warum es nichts zu rechnen gab -- nur bei ``INSUFFICIENT_DATA``
    gesetzt."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))

    @property
    def missing_metrics(self) -> tuple[MetricName, ...]:
        """Was nicht gerechnet werden konnte -- ausdruecklich, nicht durch
        Abwesenheit. CLAUDE.md: keine stille Auslassung."""
        return tuple(name for name in MetricName if name not in self.metrics)

    @property
    def coverage(self) -> float:
        """Anteil der gerechneten an allen vorgesehenen Kennzahlen.

        Bewusst eine Zahl und keine Stufe: Anders als bei der Zonenstaerke
        gibt es hier nichts zu gewichten -- der Anteil ist gezaehlt, nicht
        geschaetzt.
        """
        return len(self.metrics) / len(MetricName)
