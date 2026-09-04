"""Wertobjekte der Optionsanalyse (Doc 10, Paragraph 6.10; ADR 0048).

Reine Rechnung ohne Infrastruktur und ohne Sprachmodell. Bewertet werden
ausschliesslich **Cash Secured Puts** (Doc 08); andere Strategien sind nicht
vorgesehen und werden hier auch nicht vorbereitet.

Zwei Dinge, die dieses Modul bewusst **nicht** tut:

* Es leitet **keine** eigenen Unterstuetzungszonen ab. Die Zonen kommen
  fertig aus der Chartauswertung und sind eine optionale, nicht blockierende
  Eingabe (CLAUDE.md, erste gerichtete Kopplung -- hier zum ersten Mal
  tatsaechlich ausgefuehrt).
* Es beschafft **keinen** Kurs. Der Aktienkurs ist der Schluss der letzten
  abgeschlossenen Kerze und wird hereingereicht.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .spread import PutSpread

OPTIONS_ANALYSIS_VERSION = "options-v1"
"""Version des Bewertungsverfahrens, an jedem Ergebnis gespeichert
(CLAUDE.md: Versionierung).

Aendert sich eine Auswahlregel -- die Wahl des Verfallstermins, das
Strike-Band, die Herkunft der Praemie --, steigt diese Nummer. Eine
annualisierte Rendite aus dem Mittelwert ist eine **andere Zahl** als eine
aus dem Geldkurs, und man muss einem gespeicherten Ergebnis ansehen koennen,
welche von beiden es ist.

``v1`` rechnet mit dem **Mittelwert**. Waehrend der Entwicklung stand hier
kurzzeitig der Geldkurs; da nie ein Ergebnis gespeichert wurde, bleibt es
bei ``v1``."""


class OptionsStatus(StrEnum):
    """Muster ``FundamentalStatus`` -- kein stilles Fehlen."""

    COMPLETED = "COMPLETED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    """Die Kette kam an, aber es blieb kein einziger Vorschlag uebrig: kein
    Verfallstermin im Zielfenster, kein Strike im Moneyness-Band, kein
    Kontrakt mit Delta im Band, oder keine Notierung mit beidseitigem Kurs.

    Es gibt hier bewusst **kein** ``UNAVAILABLE``: Ein Ausfall der Quelle
    verlaesst diesen Weg als ``OptionsDataProviderError``, den der
    Application-Layer je Aktie isoliert (Muster ``FundamentalDataProvider``).
    Ein Statuswert, den nichts erzeugt, saehe wie eine Zusicherung aus, die
    niemand einloest."""


class LiquidityGrade(StrEnum):
    """Ordinale Liquiditaetsbewertung eines einzelnen Kontrakts.

    Abgeleitet allein aus der **Zahl** der verletzten Bedingungen -- Spread,
    Open Interest, Volumen --, nicht aus einer gewichteten Summe. Die
    Gewichte waeren frei gewaehlt, und die Rohgroessen stehen ohnehin an
    jedem Vorschlag (dasselbe Argument wie bei ``ZoneStrength``).

    Bedingungen, die der Anbieter nicht beliefert hat, zaehlen **nicht** als
    verletzt: Fehlende Werte bestrafen nicht (CLAUDE.md). Sie fehlen dafuer
    sichtbar im Bericht.
    """

    GOOD = "GOOD"
    """Keine Bedingung verletzt."""
    ACCEPTABLE = "ACCEPTABLE"
    """Genau eine Bedingung verletzt."""
    POOR = "POOR"
    """Mindestens zwei Bedingungen verletzt. Ein solcher Vorschlag steht nie
    an erster Stelle (Doc 10, Paragraph 6.10: unzureichende Liquiditaet wird
    nicht als bevorzugte Empfehlung dargestellt) -- er wird aber auch nicht
    verschwiegen."""


@dataclass(frozen=True, slots=True)
class OptionQuote:
    """Die Notierung eines einzelnen Put-Kontrakts, wie der Anbieter sie liefert.

    Rohdaten, keine Bewertung. Alles ausser Verfallstermin und Strike darf
    fehlen: Nach Boersenschluss und bei duenn gehandelten Kontrakten liefert
    IBKR regelmaessig einzelne Felder nicht (ADR 0048). Was fehlt, bleibt
    fehlend -- an keiner Stelle tritt ein Ersatzwert an seine Stelle.
    """

    expiration: date
    strike: float
    bid: float | None = None
    ask: float | None = None
    delta: float | None = None
    """Vorzeichenbehaftet, wie der Anbieter es liefert -- fuer einen Put also
    negativ. Gefiltert und ausgewiesen wird der Betrag."""
    implied_volatility: float | None = None
    open_interest: int | None = None
    volume: int | None = None

    @property
    def mid(self) -> float | None:
        """Der Mittelwert aus Geld- und Briefkurs -- **die Praemie**, mit der
        gerechnet wird (ADR 0048, Festlegung 6).

        ``None``, wenn eine der beiden Seiten fehlt: Ein halber Mittelwert
        waere kein Mittelwert."""
        if self.bid is None or self.ask is None:
            return None
        return (self.bid + self.ask) / 2


@dataclass(frozen=True, slots=True)
class PutStrategy:
    """Ein bewerteter Cash-Secured-Put-Vorschlag.

    Enthaelt die Ausgabegroessen aus Doc 10, Paragraph 6.10. Alle abgeleiteten
    Werte stehen neben ihren Rohgroessen: Wer ``annualized_return`` nicht
    glaubt, findet ``premium``, ``strike`` und ``days_to_expiration``
    daneben und kann nachrechnen.
    """

    expiration: date
    days_to_expiration: int
    strike: float
    distance_to_price_pct: float
    """Relativer Abstand des Strikes zum Aktienkurs, ``(kurs - strike) / kurs``.
    Bei einem Put aus dem Geld positiv."""
    premium: float
    """**Der Mittelwert aus Geld- und Briefkurs** (ADR 0048, Festlegung 6) --
    die "angenommene realistische Praemie" aus Doc 10, Paragraph 6.10.

    Nicht der Geldkurs: Bei liquiden Optionen fuellt ein Limit in der Regel
    nahe der Mitte, und der Geldkurs untertriebe die Rendite dann spuerbar --
    bei einem weiten Spread um zweistellige Prozentsaetze. Wo die Spanne
    tatsaechlich weit ist, sagt das die Liquiditaetsbewertung, statt es in
    einer stillschweigend konservativen Praemie zu verstecken.

    ``bid`` und ``ask`` stehen daneben; wer den vorsichtigeren Wert will,
    findet ihn dort."""
    break_even: float
    capital_at_risk: float
    """``strike * 100`` -- der Betrag, der bei einem Cash Secured Put
    hinterlegt wird. Ein Kontrakt umfasst 100 Aktien."""
    simple_return: float
    annualized_return: float
    liquidity: LiquidityGrade
    liquidity_warnings: tuple[str, ...] = ()
    bid: float | None = None
    ask: float | None = None
    mid: float | None = None
    """Derselbe Wert wie ``premium`` -- und trotzdem ein eigenes Feld.

    Doc 10, Paragraph 6.10 verlangt Geld, Brief, Mitte **und** eine
    angenommene realistische Praemie als getrennte Angaben. Dass die
    Entscheidung heute beide gleichsetzt (ADR 0048, Festlegung 5), ist eine
    Festlegung und keine Eigenschaft der Groessen: Faellt sie einmal anders
    aus -- ein Abschlag auf die Mitte etwa --, aendert sich ``premium``, und
    ``mid`` bleibt, was der Markt stellte. Ein Feld, das die beiden
    zusammenzoege, machte diese Aenderung zu einer Schemaaenderung."""
    delta: float | None = None
    """Der **Betrag** des vom Anbieter gelieferten Delta. Er dient zugleich
    als Naeherung der Andienungswahrscheinlichkeit -- als solche
    gekennzeichnet und nicht als eigenes Feld gefuehrt, weil es dieselbe Zahl
    waere."""
    implied_volatility: float | None = None
    open_interest: int | None = None
    volume: int | None = None
    distance_to_support_pct: float | None = None
    """Vorzeichenbehafteter Abstand des Strikes zur naechstgelegenen
    Unterstuetzungszone; positiv, wenn der Strike **ueber** der Zone liegt,
    negativ darunter, ``0.0`` innerhalb.

    ``None``, wenn die Chartauswertung keine belastbare Zone geliefert hat.
    Die Kopplung ist nicht blockierend: Alle uebrigen Felder bleiben
    vollstaendig (CLAUDE.md)."""
    earnings_within_term: bool | None = None
    """Ob der naechste Berichtstermin vor dem Verfall liegt -- die dritte
    gerichtete Kopplung (ADR 0048, Festlegung 7).

    ``None`` heisst "kein Termin bekannt" und ist ausdruecklich nicht
    dasselbe wie ``False``. Ein unbekannter Termin ist kein belegter
    Nichttermin."""


@dataclass(frozen=True, slots=True)
class OptionsAnalysis:
    """Das Ergebnis der Optionsanalyse fuer eine Aktie zu einem Zeitpunkt.

    Bei ``INSUFFICIENT_DATA`` ist ``strategies`` leer und ``reason`` gesetzt;
    ``underlying_price`` bleibt erhalten, weil er auch dann belegt, worauf
    gerechnet wurde.
    """

    status: OptionsStatus
    evaluated_at: datetime
    analysis_version: str = OPTIONS_ANALYSIS_VERSION
    underlying_price: float | None = None
    expiration: date | None = None
    """Der ausgewaehlte Verfallstermin. Alle Vorschlaege teilen ihn -- je
    Kandidat wird genau einer ausgewertet (ADR 0048, Festlegung 4)."""
    strategies: tuple[PutStrategy, ...] = ()
    """Absteigend nach annualisierter Rendite, Vorschlaege mit ``POOR``
    dahinter."""
    reason: str | None = None
    """Nur bei ``INSUFFICIENT_DATA`` gesetzt: warum kein Vorschlag entstand."""
    quotes: tuple[OptionQuote, ...] = ()
    """**Jede** abgerufene Notierung, nicht nur die bewerteten Vorschlaege
    (ADR 0058, Festlegung 1).

    Das ist die Grundlage, nicht das Ergebnis: Wo ``strategies`` sagt, was
    empfohlen wird, sagt ``quotes``, was der Markt in diesem Augenblick
    ueberhaupt stellte. Der Abruf holt bis zu ``max_strikes`` Kontrakte und
    behaelt hoechstens ``max_suggestions``; die uebrigen verschwanden bisher
    nach der Auswertung. Genau sie tragen die Auskunft, die ADR 0058 fuer die
    Kalibrierung des Bewertungsmodells braucht -- vor allem die Notierungen
    **ausserhalb** des Delta-Bandes, die als einzige etwas ueber die Form der
    Volatilitaetskurve sagen.

    Auch bei ``INSUFFICIENT_DATA`` gefuellt, sofern der Abruf ueberhaupt
    stattfand. Gerade dann ist die Menge interessant: Ein Lauf, in dem keine
    einzige Notierung brauchbar war, sagt ueber den Anbieter mehr aus als
    einer, in dem alles glattging.

    Leer, wenn vor dem Abruf abgebrochen wurde -- kein Verfallstermin im
    Fenster, kein Strike im Moneyness-Band. Leer ist hier also "nicht
    abgerufen" und nicht "nichts gestellt"; welcher Fall vorliegt, sagt
    ``reason``.

    **Wird nicht zurueckgelesen.** Die Persistenz schreibt diese Menge in eine
    eigene Tabelle; ein aus der Datenbank geladenes ``OptionsAnalysis`` traegt
    hier ein leeres Tupel. Die Kalibrierung fragt die Tabelle, nicht dieses
    Feld."""
    spread: PutSpread | None = None
    """Der Put-Spread zum bestbewerteten Vorschlag (ADR 0058, Festlegung 11),
    oder ``None``.

    Der Import steht unter ``TYPE_CHECKING``: ``spread.py`` braucht
    ``PutStrategy`` von hier, zur Laufzeit schloesse eine Angabe in die
    Gegenrichtung den Kreis. Mit ``from __future__ import annotations`` wird
    die Annotation nicht ausgewertet, ``mypy`` sieht sie trotzdem -- ein
    ``object`` an dieser Stelle schaltete die Pruefung ab, und eine
    Zeichenkette liesse sich unbemerkt hineinlegen.

    ``None`` heisst **nicht** "kein Spread moeglich", sondern "nicht
    gerechnet oder nicht zustande gekommen"; warum, sagt ``spread_reason``."""
    spread_reason: str | None = None
    """Warum kein Spread entstand -- im Klartext, nie stillschweigend.

    Der Vergleich ist eine **zusaetzliche** Auskunft: Faellt er aus, bleibt
    der Put-Vorschlag vollstaendig. Ein Cash Secured Put ist auch ohne
    Alternative ein Vorschlag."""
    parameters: Mapping[str, float] = field(
        default_factory=lambda: MappingProxyType({}),
    )
    """Die Parameter, mit denen ausgewaehlt wurde -- zusammen mit
    ``analysis_version`` die vollstaendige Auskunft darueber, wie dieses
    Ergebnis zustande kam (Muster ``TechnicalSnapshot.parameters``)."""


@dataclass(frozen=True, slots=True)
class OptionsParameters:
    """Auswahl- und Bewertungsparameter (ADR 0048).

    Aus ``AppConfig`` gebaut (bootstrap.py) -- die Domain bleibt config-frei.
    """

    min_days_to_expiration: int = 21
    max_days_to_expiration: int = 60
    """Zielfenster der Restlaufzeit in **Kalendertagen**.

    Die Obergrenze ist **gerechnet, nicht gewaehlt**: Zwei aufeinander
    folgende dritte Freitage liegen 28 oder 35 Tage auseinander. Ein Fenster
    schmaler als 35 Tage kann deshalb zwischen zwei Monatsverfaelle fallen --
    beim Messlauf am 2026-08-31 traf das 77 von 192 Titeln, weil der
    Septemberverfall 18 und der Oktoberverfall 46 Tage entfernt lag. Ab
    Breite 35, also ``21`` bis ``56``, kann das nicht mehr passieren; ``60``
    laesst Reserve."""
    target_days_to_expiration: int = 35
    """Die bevorzugte Restlaufzeit **innerhalb** des Fensters.

    Getrennt von den Grenzen, und zwar aus einem gemessenen Grund: Solange
    die Auswahl an der Fenstermitte hing, verschob jede Verbreiterung des
    Fensters zugleich die uebliche Wahl. Das Fenster sagt, was zulaessig ist;
    dieser Wert sagt, was bevorzugt wird. Mit 35 Tagen faellt die Wahl fuer
    Titel mit Wochenoptionen genauso aus wie zuvor -- am 2026-08-31 auf den
    2. Oktober --, waehrend Titel mit reinen Monatsverfaellen den
    Oktobertermin bekommen statt gar keinen."""
    min_delta: float = 0.10
    max_delta: float = 0.40
    """Zielband des Delta-**Betrags**. Es wird erst **nach** dem Abruf
    angewandt: Vor der Notierung ist das Delta nicht bekannt, und ein
    geschaetztes waere ein erfundener Wert."""
    min_moneyness: float = 0.80
    max_moneyness: float = 0.99
    """Vorauswahl der Strikes als Anteil des Aktienkurses. Sie ersetzt das
    Delta-Band nicht, sondern begrenzt nur, wie viele Kontrakte ueberhaupt
    abgefragt werden -- das Band aus ``min_delta``/``max_delta`` entscheidet
    danach."""
    max_strikes: int = 12
    """Obergrenze der abgefragten Kontrakte je Kandidat. Jede Notierung
    kostet eine Marktdatenanfrage."""
    max_suggestions: int = 3
    max_relative_spread: float = 0.10
    """Geld-Brief-Spanne im Verhaeltnis zum Mittelwert, ab der gewarnt wird."""
    min_open_interest: int = 100
    min_volume: int = 10
    hedge_width_pct: float = 0.065
    """Zielabstand des Absicherungs-Strikes unter dem Verkauf, als Anteil des
    **Aktienkurses** (ADR 0058, Festlegung 11).

    Anteil des Kurses und nicht des Strikes, damit die Breite ueber Titel
    hinweg dasselbe bedeutet -- ein Kursrutsch misst sich am Kurs.

    6,5 Prozent sind **gewaehlt, nicht gemessen**: Bei einem Titel um 230
    Dollar treffen sie das uebliche Strike-Raster drei Stufen unter dem
    Verkauf und liegen damit in der Spannweite, in der ein Put-Spread ueblich
    gehandelt wird. Was er tatsaechlich kostet, misst der Lauf."""

    def as_mapping(self) -> Mapping[str, float]:
        """Die Parameter zum Mitspeichern am Ergebnis."""
        return MappingProxyType(
            {
                "min_days_to_expiration": float(self.min_days_to_expiration),
                "max_days_to_expiration": float(self.max_days_to_expiration),
                "target_days_to_expiration": float(self.target_days_to_expiration),
                "min_delta": self.min_delta,
                "max_delta": self.max_delta,
                "min_moneyness": self.min_moneyness,
                "max_moneyness": self.max_moneyness,
                "max_strikes": float(self.max_strikes),
                "max_suggestions": float(self.max_suggestions),
                "max_relative_spread": self.max_relative_spread,
                "min_open_interest": float(self.min_open_interest),
                "min_volume": float(self.min_volume),
                "hedge_width_pct": self.hedge_width_pct,
            }
        )
