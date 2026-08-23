"""Wie weit reicht die Historie beim Anbieter tatsaechlich zurueck?

Hintergrund ist die offene Entscheidung E2 aus dem Repository-Audit vom
2026-08-23: ``backtesting.history_years`` verspricht fuenf Jahre, geholt wird
seit jeher ``history_duration: 1 Y``. Jede Backtest-Kennzahl steht damit real
auf rund einem Jahr. Der in
[ADR 0014](../../../../docs/adr/0014-ibkr-produktivintegration-freigegeben.md)
unter E3 vorgesehene Chunking-Batch wurde nie gebaut -- **und ob fuenf Jahre in
15-Minuten-Aufloesung ueberhaupt zu bekommen sind, ist unbelegt.**

Deshalb zuerst die Messung und erst danach die Entscheidung. Dieser Job holt
nichts in den Bestand; er stellt eine einzige Frage und beantwortet sie mit
dem, was ankam:

    Wie alt ist der aelteste Bar, den der Anbieter fuer diese Aktie in der
    konfigurierten Bar-Groesse noch herausgibt?

Das Verfahren ist der Rueckwaertsgang des spaeteren Batches: Fenster fuer
Fenster weiter in die Vergangenheit, bis nichts mehr kommt. Faellt die
Entscheidung auf Option (a), ist derselbe Weg zu gehen -- dann mit Ablage.

**Gemessen wird, nicht geschaetzt.** Der Bericht nennt den aeltesten
tatsaechlich empfangenen Bar und den Grund, aus dem die Messung endete. Bleibt
sie an einer selbstgesetzten Obergrenze haengen, sagt sie genau das und nicht
"fuenf Jahre erreicht".
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum

from ai_trading_analyst.domain.analysis import ContractSpec, HistoricalBarWindowSource
from ai_trading_analyst.observability.logging_setup import get_logger

_logger = get_logger(__name__)

FENSTERGROESSE_TAGE = 365
"""Wieviel je Anfrage angefragt wird.

Ein Jahr ist der Zeitraum, den der taegliche Backfill seit jeher gegen
dieselbe Schnittstelle stellt (``history_duration: 1 Y``) -- er ist damit als
funktionierende Fenstergroesse belegt. Groessere Fenster waeren zu erproben,
kleinere kosten unter dem Pacing-Limit von 60 Anfragen je zehn Minuten
unnoetig Laufzeit.
"""

HOECHSTZAHL_FENSTER = 12
"""Obergrenze, damit die Messung unter allen Umstaenden endet.

Zwoelf Jahresfenster liegen weit ueber dem Anspruch von fuenf Jahren. Die
Grenze ist kein erwartetes Ergebnis, sondern eine Reissleine: Ohne sie liefe
die Messung bei einem Anbieter, der immer wieder irgendetwas zurueckgibt,
endlos -- unter Pacing mit elf Sekunden Abstand je Anfrage waere das ein
stundenlanger Leerlauf.
"""


class DepthLimit(Enum):
    """Woran die Messung geendet hat -- die eigentliche Aussage des Berichts."""

    PROVIDER_EXHAUSTED = "provider_exhausted"
    """Der Anbieter gab fuer das naechste Fenster nichts mehr her.

    Das ist das gesuchte Ergebnis: die tatsaechliche Tiefe.
    """

    NO_PROGRESS = "no_progress"
    """Der Anbieter antwortete, kam aber nicht weiter zurueck.

    Beobachtbar, wenn er ein Fenster am unteren Rand seiner Historie
    wiederholt statt es leer zu lassen. Fuer die Auswertung gilt das wie
    ``PROVIDER_EXHAUSTED`` -- weiter geht es nicht --, wird aber getrennt
    ausgewiesen, weil es etwas anderes ueber die Gegenstelle aussagt.
    """

    WINDOW_LIMIT = "window_limit"
    """Die Reissleine hat gegriffen. Die gemessene Tiefe ist eine **Untergrenze**."""

    ERROR = "error"
    """Der Abruf ist gescheitert. Die bis dahin erreichte Tiefe ist eine Untergrenze."""


@dataclass(frozen=True, slots=True)
class SymbolDepth:
    """Das Messergebnis einer Aktie."""

    symbol: str
    limit: DepthLimit
    windows: int = 0
    received_bars: int = 0
    earliest: datetime | None = None
    latest: datetime | None = None
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.limit is DepthLimit.ERROR

    @property
    def is_lower_bound(self) -> bool:
        """Ist die gemessene Tiefe nur eine Untergrenze?

        Bei ``WINDOW_LIMIT`` und ``ERROR`` wurde die Messung von aussen
        beendet -- der Anbieter haette moeglicherweise mehr hergegeben. Diese
        Unterscheidung darf im Bericht nicht verlorengehen: Sonst laese sich
        eine abgebrochene Messung als gemessene Tiefe.
        """
        return self.limit in (DepthLimit.WINDOW_LIMIT, DepthLimit.ERROR)

    def depth_days(self, now: datetime) -> int | None:
        """Wieviele Kalendertage der aelteste Bar zurueckliegt."""
        if self.earliest is None:
            return None
        return max((now - self.earliest).days, 0)


@dataclass(frozen=True, slots=True)
class HistoryDepthReport:
    measured_at: datetime
    bar_minutes: int
    window_days: int
    results: tuple[SymbolDepth, ...] = field(default_factory=tuple)

    @property
    def failures(self) -> tuple[SymbolDepth, ...]:
        return tuple(result for result in self.results if result.failed)

    @property
    def shallowest(self) -> SymbolDepth | None:
        """Die Aktie mit der kuerzesten gemessenen Historie.

        Massgeblich fuer den Anspruch ist nicht die tiefste Aktie, sondern die
        flachste: Sie bestimmt, ab wann eine Kennzahl ueber die Watchlist
        hinweg vergleichbar ist.
        """
        gemessen = [
            (result.earliest, result) for result in self.results if result.earliest is not None
        ]
        if not gemessen:
            return None
        return max(gemessen, key=lambda paar: paar[0])[1]


class MeasureHistoryDepthUseCase:
    """Arbeitet sich je Aktie Fenster fuer Fenster in die Vergangenheit.

    Legt bewusst **nichts** ab. Die Messung beantwortet eine offene Frage; sie
    ist kein halber Backfill. Wuerde sie nebenbei speichern, entstuende ein
    Bestand, dessen Zustandekommen in keiner Entscheidung steht -- und der
    naechste Backfill saehe einen juengsten Bar, der ihn glauben liesse, alles
    dazwischen sei geholt.
    """

    def __init__(
        self,
        window_source: HistoricalBarWindowSource,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        window_days: int = FENSTERGROESSE_TAGE,
        maximum_windows: int = HOECHSTZAHL_FENSTER,
    ) -> None:
        self._window_source = window_source
        self._now = now
        self._window_days = window_days
        self._maximum_windows = maximum_windows

    def execute(
        self,
        watchlist: Sequence[ContractSpec],
        bar_minutes: int,
        on_progress: Callable[[int, int, SymbolDepth], None] | None = None,
    ) -> HistoryDepthReport:
        ergebnisse: list[SymbolDepth] = []
        for index, contract in enumerate(watchlist, start=1):
            ergebnis = self._measure_one(contract)
            ergebnisse.append(ergebnis)
            if on_progress is not None:
                on_progress(index, len(watchlist), ergebnis)
        return HistoryDepthReport(
            measured_at=self._now(),
            bar_minutes=bar_minutes,
            window_days=self._window_days,
            results=tuple(ergebnisse),
        )

    def _measure_one(self, contract: ContractSpec) -> SymbolDepth:
        symbol = contract.symbol
        rand: datetime | None = None
        aeltester: datetime | None = None
        juengster: datetime | None = None
        bars_gesamt = 0
        fenster = 0

        while fenster < self._maximum_windows:
            try:
                bars = self._window_source.fetch_window(contract, rand, self._window_days)
            except Exception as error:  # Systemgrenze: eine Aktie, nicht der Lauf
                _logger.warning("%s: %s -- %s", symbol, type(error).__name__, error)
                return SymbolDepth(
                    symbol=symbol,
                    limit=DepthLimit.ERROR,
                    windows=fenster,
                    received_bars=bars_gesamt,
                    earliest=aeltester,
                    latest=juengster,
                    error=f"{type(error).__name__}: {error}",
                )

            fenster += 1
            if not bars:
                return SymbolDepth(
                    symbol=symbol,
                    limit=DepthLimit.PROVIDER_EXHAUSTED,
                    windows=fenster,
                    received_bars=bars_gesamt,
                    earliest=aeltester,
                    latest=juengster,
                )

            bars_gesamt += len(bars)
            fenster_aeltester = min(bar.start for bar in bars)
            fenster_juengster = max(bar.start for bar in bars)
            if juengster is None or fenster_juengster > juengster:
                juengster = fenster_juengster

            if aeltester is not None and fenster_aeltester >= aeltester:
                # Der Anbieter hat geantwortet, aber dasselbe oder ein
                # spaeteres Fenster geliefert. Weiterzufragen hiesse, dieselbe
                # Antwort noch einmal zu holen.
                return SymbolDepth(
                    symbol=symbol,
                    limit=DepthLimit.NO_PROGRESS,
                    windows=fenster,
                    received_bars=bars_gesamt,
                    earliest=aeltester,
                    latest=juengster,
                )

            aeltester = fenster_aeltester
            # Eine Sekunde vor den aeltesten Bar: 'end' ist ausschliessend
            # gemeint, aber die Gegenstelle behandelt den Rand nicht
            # nachweislich so. Der Abstand kostet nichts -- ein Bar an genau
            # dieser Sekunde existiert auf dem Raster nicht.
            rand = aeltester - timedelta(seconds=1)

        return SymbolDepth(
            symbol=symbol,
            limit=DepthLimit.WINDOW_LIMIT,
            windows=fenster,
            received_bars=bars_gesamt,
            earliest=aeltester,
            latest=juengster,
        )
