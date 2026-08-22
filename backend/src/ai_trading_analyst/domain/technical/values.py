"""Wertobjekte der deterministischen Chartauswertung (Doc 10, Paragraph 6.8).

Reine Berechnung ohne Infrastruktur und ohne Sprachmodell. Doc 10 verlangt
ausdruecklich, dass deterministische Berechnung und KI-Interpretation getrennt
gespeichert werden -- dieses Modul ist die deterministische Haelfte. Der
Technical Agent bekommt diese Werte spaeter als Eingabe und darf sie
ausschliesslich einordnen, nie veraendern (CLAUDE.md, zentrale Regel).

Abgegrenzt von ``domain.screening``: Dort liegen die unter Gate G1
freigegebenen Signalformeln, die ueber Kandidat oder Nichtkandidat
entscheiden. Hier entsteht nichts, was diese Entscheidung beeinflusst -- nur
die Beschreibung der Lage, in der die Entscheidung gefallen ist.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import datetime
from enum import StrEnum

TECHNICAL_ANALYSIS_VERSION = "technical-v1"
"""Version des Auswertungsverfahrens, an jedem Ergebnis gespeichert
(CLAUDE.md: Versionierung). Aendert sich das Zonenverfahren oder die
Trenddefinition, steigt diese Nummer -- alte Ergebnisse bleiben dadurch als
nach altem Verfahren gerechnet erkennbar, statt still uminterpretiert zu
werden."""


class TechnicalStatus(StrEnum):
    """Muster ``EarningsFilterStatus``/``ResearchStatus`` -- kein stilles Fehlen.

    Es gibt hier bewusst kein ``UNAVAILABLE``: Die Auswertung rechnet
    ausschliesslich auf der bereits geholten Kerzenserie und haengt an keinem
    externen Anbieter, der ausfallen koennte.
    """

    COMPLETED = "COMPLETED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    """Zu wenige Kerzen fuer eine belastbare Auswertung (CLAUDE.md: ohne
    belastbare Grundlage lautet das Ergebnis INSUFFICIENT_DATA) -- niemals
    ersatzweise auf einem zu kurzen Fenster gerechnet."""


class TrendDirection(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    SIDEWAYS = "SIDEWAYS"
    """Weder Lage noch Steigung eindeutig -- ein eigener Wert und nicht
    ``None``: 'kein erkennbarer Trend' ist ein Befund, 'nicht berechenbar'
    ist keiner. Fehlt die Grundlage, bleibt ``TechnicalSnapshot.trend``
    stattdessen ``None``."""


class ZoneKind(StrEnum):
    """Art der Zone, bezogen auf den aktuellen Kurs (Doc 10, Paragraph 6.8).

    Bewusst nicht als dauerhafte Eigenschaft der Preiszone gefuehrt: Dieselbe
    Zone ist Unterstuetzung, solange der Kurs darueber liegt, und wird zum
    Widerstand, sobald er darunter faellt.
    """

    SUPPORT = "SUPPORT"
    RESISTANCE = "RESISTANCE"
    PRICE_INSIDE = "PRICE_INSIDE"
    """Der Kurs liegt in der Zone selbst -- weder Halt darunter noch Deckel
    darueber. Ein eigener Wert, weil die willkuerliche Zuordnung zu einer der
    beiden Seiten genau in dem Moment falsch waere, in dem sie am meisten
    zaehlt."""


class ZoneStrength(StrEnum):
    """Ordinale Staerke, abgeleitet allein aus der Zahl der Beruehrungen.

    Bewusst eine Stufe und keine Kommazahl: Eine Formel mit gewichteten
    Summanden sieht praezise aus, ohne es zu sein -- die Gewichte waeren
    frei gewaehlt. Die Rohgroessen (``touch_count``, ``last_confirmed_at``)
    stehen ohnehin an jeder Zone und lassen sich spaeter im Scoring anders
    verrechnen, ohne dass hier ein Zahlenwert vorgibt, wie.
    """

    WEAK = "WEAK"
    MODERATE = "MODERATE"
    STRONG = "STRONG"


@dataclass(frozen=True, slots=True)
class TechnicalAnalysisParameters:
    """Parameter der Chartauswertung (ADR 0025).

    Nicht Teil von Gate G1: Diese Werte beeinflussen keine Signalformel und
    keine Kandidatenentscheidung, sondern nur die Beschreibung der Lage.
    """

    pivot_reach: int = 3
    """Kerzen links und rechts eines Swing-Punktes. Ein Hoch gilt erst als
    Swing-Hoch, wenn es von so vielen Kerzen auf beiden Seiten nicht
    uebertroffen wird. Die juengsten ``pivot_reach`` Kerzen koennen deshalb
    noch kein Pivot bilden -- ein noch nicht bestaetigter Wendepunkt ist
    keiner."""
    zone_tolerance_pct: float = 0.015
    """Halbe Breite einer Zone als **Bruchteil** ihres Mittelwerts -- 0.015
    sind 1,5 %, nicht 1,5. Bestimmt zugleich, welche Swing-Punkte noch zu
    derselben Zone gehoeren."""
    min_touches: int = 2
    """Eine einmal beruehrte Preisregion ist noch keine Zone."""
    moderate_touch_count: int = 3
    strong_touch_count: int = 5
    max_zones_per_side: int = 3
    """Obergrenze je Seite, nach Naehe zum Kurs. Ohne sie meldet eine lange
    Historie zwei Dutzend Zonen, von denen die entfernten fuer die
    Einstiegsfrage nichts beitragen."""
    history_candles: int = 250
    """Fenster der Zonensuche, in Kerzen. Bei zwei Kerzen je Handelstag rund
    ein halbes Jahr -- der Horizont, um den es bei Swing-Trades geht."""
    atr_length: int = 14
    trend_lookback: int = 10
    """Kerzen, ueber die die Steigung des EMA20 gemessen wird."""
    trend_flat_pct: float = 0.005
    """Aenderung des EMA20 ueber ``trend_lookback`` Kerzen als **Bruchteil**,
    unterhalb derer der Trend als seitwaerts gilt -- 0.005 sind 0,5 %."""
    extremes_lookback: int = 40
    """Fenster fuer die juengsten Hoch- und Tiefpunkte (Doc 10, Paragraph 6.8)."""

    def __post_init__(self) -> None:
        if self.pivot_reach < 1:
            raise ValueError(f"pivot_reach muss mindestens 1 sein, war {self.pivot_reach}")
        if not 0 < self.zone_tolerance_pct < 1:
            # Die obere Grenze ist nicht kosmetisch: Ab 1 wird die untere
            # Zonenkante negativ, alle Swing-Punkte fallen in ein einziges
            # Buendel, und ``build_zones`` liefert am Ende eine leere Liste.
            # Das Ergebnis saehe aus wie eine Aktie ohne mehrfach getestete
            # Preisregionen -- ein Zahlendreher gaebe also ein plausibles
            # falsches Ergebnis statt eines Fehlers. Der Wert ist ein
            # Bruchteil (0.015 = 1,5 %), die Verwechslung mit 1.5 liegt nahe.
            raise ValueError(
                "zone_tolerance_pct muss ein Bruchteil zwischen 0 und 1 sein "
                f"(0.015 entspricht 1,5 %), war {self.zone_tolerance_pct}"
            )
        if self.min_touches < 1:
            raise ValueError(f"min_touches muss mindestens 1 sein, war {self.min_touches}")
        if not self.min_touches <= self.moderate_touch_count <= self.strong_touch_count:
            raise ValueError(
                f"min_touches ({self.min_touches}) <= moderate_touch_count "
                f"({self.moderate_touch_count}) <= strong_touch_count "
                f"({self.strong_touch_count}) ist verletzt"
            )
        if self.max_zones_per_side < 1:
            raise ValueError(
                f"max_zones_per_side muss mindestens 1 sein, war {self.max_zones_per_side}"
            )
        if self.atr_length < 1:
            raise ValueError(f"atr_length muss mindestens 1 sein, war {self.atr_length}")
        if self.trend_lookback < 1:
            raise ValueError(f"trend_lookback muss mindestens 1 sein, war {self.trend_lookback}")
        if not 0 <= self.trend_flat_pct < 1:
            # Ab 1 gilt jede erreichbare EMA20-Aenderung als flach, und der
            # Trend waere dauerhaft SIDEWAYS -- wieder ein plausibel
            # aussehendes Ergebnis statt eines Fehlers.
            raise ValueError(
                "trend_flat_pct muss ein Bruchteil zwischen 0 und 1 sein "
                f"(0.005 entspricht 0,5 %), war {self.trend_flat_pct}"
            )
        if self.extremes_lookback < 1:
            raise ValueError(
                f"extremes_lookback muss mindestens 1 sein, war {self.extremes_lookback}"
            )
        if self.history_candles < self.minimum_candles:
            raise ValueError(
                f"history_candles ({self.history_candles}) ist kleiner als das laengste "
                f"benoetigte Fenster ({self.minimum_candles})"
            )

    def as_mapping(self) -> dict[str, float]:
        """Die Parameter als flache Abbildung, zum Speichern am Ergebnis.

        Ein einfaches ``dict`` und keine eigene Serialisierungsklasse: Es
        wird nur geschrieben und gelesen, nie gerechnet.
        """
        return {field.name: getattr(self, field.name) for field in fields(self)}

    @property
    def minimum_candles(self) -> int:
        """Kuerzeste Serie, auf der ueberhaupt alle Groessen berechenbar sind.

        Darunter ist das Ergebnis ``INSUFFICIENT_DATA`` -- nicht eine auf
        weniger Kerzen gerechnete Auswertung, der man das nicht ansieht.
        """
        return max(
            2 * self.pivot_reach + 1,
            self.atr_length + 1,
            self.trend_lookback + 1,
            self.extremes_lookback,
        )


@dataclass(frozen=True, slots=True)
class SwingPoint:
    """Ein bestaetigter lokaler Wendepunkt.

    Zwischenergebnis der Zonenbildung, aber Teil der oeffentlichen
    Schnittstelle: Ohne die Punkte, aus denen eine Zone entstanden ist, waere
    die von Doc 10 geforderte Nachvollziehbarkeit der Berechnung nicht
    gegeben.
    """

    index: int
    timestamp: datetime
    price: float
    is_high: bool


@dataclass(frozen=True, slots=True)
class PriceZone:
    """Eine Unterstuetzungs- oder Widerstandszone.

    Enthaelt die sieben von Doc 10, Paragraph 6.8 geforderten Angaben:
    unterer und oberer Wert, Art, Staerke, Zahl der Beruehrungen, letzte
    Bestaetigung und Abstand zum aktuellen Kurs.
    """

    lower: float
    upper: float
    kind: ZoneKind
    strength: ZoneStrength
    touch_count: int
    """Zahl der getrennten Beruehrungen. Aufeinanderfolgende Kerzen innerhalb
    der Zone zaehlen als **eine** Beruehrung -- eine mehrwoechige Seitwaerts-
    bewegung in der Zone ist ein Test, nicht dreissig."""
    last_confirmed_at: datetime
    """Beginn der juengsten Kerze, die die Zone beruehrt hat."""
    distance_pct: float
    """Relativer Abstand vom Schlusskurs zur naechsten Zonenkante. ``0.0``,
    wenn der Kurs in der Zone liegt."""
    pivot_count: int
    """Zahl der Swing-Punkte, aus denen die Zone gebildet wurde -- die
    Herkunft der Zone, getrennt von der Zahl ihrer spaeteren Tests."""

    @property
    def midpoint(self) -> float:
        return (self.lower + self.upper) / 2


@dataclass(frozen=True, slots=True)
class TechnicalSnapshot:
    """Die deterministische Chartauswertung einer Aktie zu einer Kerze.

    Alle Felder ausser ``status``, ``evaluated_at`` und ``analysis_version``
    sind bei ``INSUFFICIENT_DATA`` leer beziehungsweise ``None``. Ein
    fehlender Wert bleibt fehlend (CLAUDE.md) -- kein Ersatzwert, der sich im
    Bericht wie ein gerechneter liest.
    """

    status: TechnicalStatus
    evaluated_at: datetime
    analysis_version: str = TECHNICAL_ANALYSIS_VERSION
    parameters: Mapping[str, float] | None = None
    """Die Parameter, mit denen gerechnet wurde -- zusammen mit
    ``analysis_version`` die vollstaendige Auskunft darueber, wie dieses
    Ergebnis zustande kam (CLAUDE.md: Versionierung an jedem Ergebnis).

    Ohne sie waere die Versionsnummer eine leere Zusage: Doc 14 fordert den
    Betreiber ausdruecklich auf, Zonenbreite und Beruehrungsschwellen an
    echten Charts nachzuziehen. Zwei Ergebnisse traegen dann dieselbe
    ``technical-v1`` und waeren doch nach verschiedenen Massstaeben
    gerechnet -- ein Unterschied, den man spaeter nicht mehr von einer
    Marktveraenderung unterscheiden koennte.

    Bewusst eine Abbildung und nicht ``TechnicalAnalysisParameters``:
    Abgeschlossene Analysen werden nicht ueberschrieben (CLAUDE.md). Ein
    kuenftig umbenannter oder entfallener Parameter darf ein altes Ergebnis
    nicht unlesbar machen.
    """
    reason: str | None = None
    """Nur bei ``INSUFFICIENT_DATA``: ``"too_few_candles"``."""

    candle_timestamp: datetime | None = None
    close: float | None = None

    trend: TrendDirection | None = None
    """``None`` heisst nicht berechenbar (EMA-Werte fehlen), nicht
    ``SIDEWAYS`` -- die Unterscheidung geht sonst genau dort verloren, wo sie
    zaehlt."""
    rsi: float | None = None
    ema5: float | None = None
    ema20: float | None = None
    distance_to_ema5_pct: float | None = None
    distance_to_ema20_pct: float | None = None
    """Relative Lage des Schlusskurses zum gleitenden Durchschnitt, positiv
    oberhalb."""

    atr: float | None = None
    atr_pct: float | None = None
    """ATR im Verhaeltnis zum Schlusskurs -- erst das macht die Volatilitaet
    zwischen Aktien unterschiedlicher Preisklassen vergleichbar."""

    recent_high: float | None = None
    recent_high_at: datetime | None = None
    recent_low: float | None = None
    recent_low_at: datetime | None = None

    zones: tuple[PriceZone, ...] = ()
    """Nach Abstand zum Kurs aufsteigend. Leer ist ein zulaessiges Ergebnis:
    Nicht jede Aktie hat mehrfach getestete Preisregionen."""
