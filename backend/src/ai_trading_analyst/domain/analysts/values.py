"""Wertobjekte der Analystenempfehlungen (Doc 10, Paragraph 6.12 Punkt 9;
ADR 0043).

Reines Python -- keine Infrastruktur, kein Anbieter. Der Domain Layer kennt
Finnhub nicht (Doc 10, Paragraph 9), nur ``AnalystRecommendationsProvider``
als Port (``domain.analysis.ports``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

ANALYST_ANALYSIS_VERSION = "analysts-v1"
"""Fassung des Verfahrens (Doc 10, Paragraph 8).

``v1`` speichert die Verteilung roh. Sie steigt, sobald daraus etwas
abgeleitet wird -- und genau das tut dieses Modul bewusst **nicht**.
"""


class AnalystRecommendationStatus(StrEnum):
    """Ergebnisstatus des Abrufs (Muster ``EarningsFilterStatus``).

    Drei Werte und nicht zwei: Ein Anbieter, der das Symbol nicht fuehrt, hat
    nicht dasselbe gesagt wie einer, der nicht erreichbar war. Aus beidem
    ``None`` zu machen loeschte den Unterschied, auf den es beim Lesen des
    Berichts ankommt.
    """

    COMPLETED = "COMPLETED"
    UNKNOWN = "UNKNOWN"
    """Der Anbieter war erreichbar, fuehrt aber keine Empfehlungen fuer dieses
    Symbol. **Nicht** als "keine Meinung" zu lesen (ADR 0043)."""
    UNAVAILABLE = "UNAVAILABLE"
    """Der Anbieter war nicht erreichbar oder seine Antwort nicht auswertbar."""


@dataclass(frozen=True, slots=True)
class RecommendationPeriod:
    """Die Votenverteilung eines Monatsstands.

    Die fuenf Klassen bleiben getrennt. Sie zu einer Konsenszahl zu
    verrechnen sieht praezise aus, ohne es zu sein -- die Gewichte waeren
    frei gewaehlt (ADR 0043, dieselbe Ueberlegung wie bei ``ZoneStrength``).
    Wie aus der Verteilung ein Score-Teilwert wird, entscheidet die
    Scoring-Engine, nicht dieses Wertobjekt.
    """

    period: date
    strong_buy: int
    buy: int
    hold: int
    sell: int
    strong_sell: int

    @property
    def total(self) -> int:
        """Zahl der abgegebenen Voten in diesem Monatsstand."""
        return self.strong_buy + self.buy + self.hold + self.sell + self.strong_sell


@dataclass(frozen=True, slots=True)
class AnalystRecommendations:
    """Persistierbares Ergebnis samt Beleg.

    Deckt die Doc-10-Anforderungen "Quelle speichern" und "Datenqualitaet
    kennzeichnen" ab: ``source`` und ``retrieved_at`` belegen die Angabe,
    ``reason`` erklaert ein ``UNKNOWN`` oder ``UNAVAILABLE``.
    """

    status: AnalystRecommendationStatus
    evaluated_at: datetime
    periods: tuple[RecommendationPeriod, ...] = ()
    """Monatsstaende, **neuester zuerst**. Leer, wenn ``status`` nicht
    ``COMPLETED`` ist.

    Die Reihenfolge ist Teil der Zusage und nicht nur Darstellung: Die
    Veraenderung ueber mehrere Monate ist ein eigenstaendiges Signal
    (ADR 0043), und wer den ersten Eintrag liest, muss den aktuellen Stand
    bekommen.
    """
    source: str | None = None
    source_url: str | None = None
    """Die Adresse, unter der die Verteilung tatsaechlich herkam.

    Vom jeweiligen Anbieter gesetzt und **nicht** im Bericht fest verdrahtet:
    Ausgeliefert steht ``analyst_ratings.provider`` auf ``fixture``, und ein
    Bericht, der Fixture-Zahlen mit der echten Finnhub-Adresse belegte, waere
    eine falsche Quellenangabe im Normalfall -- genau das, was die
    Quellenbindung verhindern soll. Dieselbe Konvention wie beim
    Fixture-Research-Anbieter, der ``example.com`` vergibt.
    """
    retrieved_at: datetime | None = None
    reason: str | None = None
    """Nur gesetzt, wenn ``status`` nicht ``COMPLETED`` ist:
    ``"no_coverage"`` (Anbieter fuehrt das Symbol nicht),
    ``"provider_error"`` (Anbieter war nicht erreichbar) oder
    ``"invalid_data"`` (Antwort war nicht plausibel auswertbar)."""
    analysis_version: str = ANALYST_ANALYSIS_VERSION

    def __post_init__(self) -> None:
        """``COMPLETED`` ohne Monatsstaende gibt es nicht.

        Es waere genau die Aussage, die ADR 0043 ausschliesst: ein Abschnitt,
        der im Bericht als verfuegbar gilt und eine leere Verteilung traegt --
        also "keine Meinung" behauptet, wo "keine Abdeckung" gemeint ist.
        Dafuer gibt es ``UNKNOWN``.

        Geprueft im Wertobjekt und nicht im Anbieter, weil es sonst jeder
        kuenftige Anbieter erneut richtig machen muesste. Ein Datensatz, der
        diese Bedingung verletzt, ist beschaedigt und soll auffallen, statt
        gelesen zu werden.
        """
        if self.status is AnalystRecommendationStatus.COMPLETED and not self.periods:
            raise ValueError(
                "AnalystRecommendations mit Status COMPLETED braucht mindestens einen "
                "Monatsstand -- ohne Abdeckung ist der Status UNKNOWN."
            )
        if self.status is not AnalystRecommendationStatus.COMPLETED and self.periods:
            raise ValueError(
                f"AnalystRecommendations mit Status {self.status.value} darf keine "
                "Monatsstaende tragen -- sie waeren ein Ergebnis ohne Ergebnis."
            )

    @property
    def latest(self) -> RecommendationPeriod | None:
        """Der juengste Monatsstand, oder ``None`` ohne Empfehlungen."""
        return self.periods[0] if self.periods else None
