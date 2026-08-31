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

OPTIONS_ANALYSIS_VERSION = "options-v1"
"""Version des Bewertungsverfahrens, an jedem Ergebnis gespeichert
(CLAUDE.md: Versionierung).

Aendert sich eine Auswahlregel -- die Wahl des Verfallstermins, das
Strike-Band, die Herkunft der Praemie --, steigt diese Nummer. Eine
annualisierte Rendite aus dem Mid ist eine **andere Zahl** als eine aus dem
Bid, und man muss einem gespeicherten Ergebnis ansehen koennen, welche von
beiden es ist."""


class OptionsStatus(StrEnum):
    """Muster ``FundamentalStatus`` -- kein stilles Fehlen."""

    COMPLETED = "COMPLETED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    """Die Kette kam an, aber es blieb kein einziger Vorschlag uebrig: kein
    Verfallstermin im Zielfenster, kein Strike im Moneyness-Band, kein
    Kontrakt mit Delta im Band, oder keine Notierung mit einem Geldkurs.

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
        """Der Mittelwert aus Geld- und Briefkurs, sofern beide vorliegen.

        Nicht die Praemie, mit der gerechnet wird -- siehe ``PutStrategy``."""
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
    """**Der Geldkurs**, nicht der Mittelwert (ADR 0048, Festlegung 6): der
    Preis, den ein Verkauf zum Markt sofort einbraechte. Die "angenommene
    realistische Praemie" aus Doc 10 ist damit die konservative Annahme --
    ``mid`` steht daneben und ist in der Regel hoeher."""
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
    max_days_to_expiration: int = 45
    """Zielfenster der Restlaufzeit in **Kalendertagen** (Entscheidung des
    Projektinhabers, 2026-08-31). Ausgewaehlt wird der Verfallstermin, der
    der Mitte des Fensters am naechsten liegt."""
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

    def as_mapping(self) -> Mapping[str, float]:
        """Die Parameter zum Mitspeichern am Ergebnis."""
        return MappingProxyType(
            {
                "min_days_to_expiration": float(self.min_days_to_expiration),
                "max_days_to_expiration": float(self.max_days_to_expiration),
                "min_delta": self.min_delta,
                "max_delta": self.max_delta,
                "min_moneyness": self.min_moneyness,
                "max_moneyness": self.max_moneyness,
                "max_strikes": float(self.max_strikes),
                "max_suggestions": float(self.max_suggestions),
                "max_relative_spread": self.max_relative_spread,
                "min_open_interest": float(self.min_open_interest),
                "min_volume": float(self.min_volume),
            }
        )
