"""Tiefen-Backfill: die Historie rueckwaerts auf den Anspruch auffuellen.

Der Batch aus
[ADR 0014](../../../../docs/adr/0014-ibkr-produktivintegration-freigegeben.md)
(E3), beschlossen mit
[ADR 0028](../../../../docs/adr/0028-historientiefe-gemessen.md) nach der
Messung aus
[ADR 0027](../../../../docs/adr/0027-historientiefe-messen-vor-anspruch.md).

Abgrenzung zu ``BackfillHistoryUseCase`` -- die beiden laufen in
entgegengesetzte Richtungen und kommen sich nicht ins Gehege:

============  ===========================  ==========================
              taeglicher Backfill          Tiefen-Backfill
============  ===========================  ==========================
Frage         Was fehlt **seit** dem       Wie weit reicht es
              letzten Lauf?                **zurueck**?
Ansatzpunkt   ``latest_start``             ``earliest_start``
Richtung      vorwaerts bis heute          rueckwaerts in die
                                           Vergangenheit
Haeufigkeit   jeden Handelstag             einmalig, danach nie
                                           wieder noetig
============  ===========================  ==========================

Drei Eigenschaften machen den Lauf betriebstauglich -- er dauert fuer eine
volle Watchlist Stunden, und keine davon ist Beiwerk:

* **Fortsetzbar.** Jedes Fenster wird sofort abgelegt, nicht erst am Ende.
  Weil der Ansatzpunkt der aelteste gespeicherte Bar ist, wandert er mit
  jedem Fenster weiter zurueck: Ein abgebrochener Lauf wird schlicht erneut
  gestartet und setzt dort an, wo er aufgehoert hat. Aufzuraeumen gibt es
  nichts.
* **Fehlerisoliert.** Faellt eine Aktie aus -- oder die TWS beim naechtlichen
  Neustart --, laeuft der Rest weiter. Bei rund 190 Symbolen waere ein
  Abbruch beim ersten Ausfall die schlechteste aller Antworten.
* **Idempotent.** Das Speichern ist ueber ``(symbol, start)`` eindeutig.
  Ueberlappende Fenster kosten nichts.

**Der Zielwert ist erreicht, wenn er erreicht ist -- nicht, wenn er
ungefaehr erreicht ist.** Bleibt eine Aktie darunter, sagt der Bericht das
und nennt den Grund. Eine kurze Boersenhistorie ist ein legitimer Grund und
kein Fehler; die Kennzahlen der Aktie tragen dann von sich aus ihren
tatsaechlichen ``history_start``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum

from ai_trading_analyst.domain.analysis import (
    ContractSpec,
    HistoricalBarWindowSource,
    UnitOfWork,
)
from ai_trading_analyst.observability.logging_setup import get_logger

_logger = get_logger(__name__)

HANDELSTAGE_JE_JAHR = 252
"""Handelstage eines US-Boersenjahres.

Gebraucht, weil ``history_years`` in Kalenderjahren zaehlt, die Fenstergroesse
der IBKR-API aber in **Handelstagen** (ADR 0028). Der Wert ist die uebliche
Konvention; er bestimmt nur, wieviele Fenster angefragt werden, nicht, was
davon ankommt. Zu grosszuegig gerechnet kostet ein ueberzaehliges Fenster,
zu knapp bliebe der Anspruch unerfuellt -- deshalb lieber eines zu viel.
"""

FENSTERGROESSE_HANDELSTAGE = 365
"""Wieviel je Anfrage angefragt wird, in Handelstagen.

Derselbe Wert wie beim taeglichen Backfill (``history_duration: 1 Y``) und
damit als funktionierende Anfragegroesse belegt -- die Messung aus ADR 0027
hat ihn zwoelfmal je Aktie ohne Kuerzung durchlaufen.
"""

SICHERHEITSFENSTER = 1
"""Ein Fenster mehr als rechnerisch noetig.

Feiertage, Handelsunterbrechungen und der Rundungsrest zwischen Kalender-
und Handelstagen gehen sonst zu Lasten des letzten Jahres. Ein zusaetzliches
Fenster kostet je Aktie eine Anfrage; ein um Wochen verfehlter Anspruch
kostete einen zweiten Lauf ueber die ganze Watchlist.
"""


def erforderliche_fenster(
    history_years: int,
    window_trading_days: int = FENSTERGROESSE_HANDELSTAGE,
    trading_days_per_year: int = HANDELSTAGE_JE_JAHR,
) -> int:
    """Wieviele Fenster je Aktie fuer ``history_years`` Jahre noetig sind."""
    if history_years < 1:
        raise ValueError(f"history_years muss mindestens 1 sein, ist aber {history_years}")
    handelstage = history_years * trading_days_per_year
    return -(-handelstage // window_trading_days) + SICHERHEITSFENSTER


class DeepenOutcome(Enum):
    """Womit der Lauf fuer eine Aktie geendet hat."""

    TARGET_REACHED = "target_reached"
    """Der Bestand deckt den Zielzeitraum ab. Der Regelfall."""

    ALREADY_DEEP_ENOUGH = "already_deep_enough"
    """Nichts zu tun -- der Bestand war schon tief genug.

    Der Fall beim zweiten Lauf. Er kostet keine einzige Anfrage an die TWS
    und ist der Grund, warum ein Wiederholen des Batches unbedenklich ist.
    """

    PROVIDER_EXHAUSTED = "provider_exhausted"
    """IBKR gab nichts mehr her, bevor das Ziel erreicht war.

    Bei einer Neuemission der Normalfall und **kein Fehler**: Eine Aktie, die
    es erst seit zwei Jahren gibt, hat keine fuenfjaehrige Historie. Die
    Kennzahlen tragen ihren tatsaechlichen ``history_start``.
    """

    WINDOW_LIMIT = "window_limit"
    """Die Reissleine hat gegriffen, bevor das Ziel erreicht war."""

    ERROR = "error"
    """Der Abruf oder das Speichern ist gescheitert."""


@dataclass(frozen=True, slots=True)
class SymbolDeepening:
    """Was der Lauf fuer eine Aktie erreicht hat."""

    symbol: str
    outcome: DeepenOutcome
    windows: int = 0
    received_bars: int = 0
    stored_bars: int = 0
    earliest_before: datetime | None = None
    earliest_after: datetime | None = None
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.outcome is DeepenOutcome.ERROR

    @property
    def short_of_target(self) -> bool:
        """Blieb die Aktie unter dem Zielzeitraum?

        ``ALREADY_DEEP_ENOUGH`` und ``TARGET_REACHED`` sind die beiden
        Ergebnisse, bei denen der Anspruch steht. Alles andere ist ein
        Ergebnis mit Vorbehalt -- und das gehoert in den Bericht, nicht in
        eine Fussnote.
        """
        return self.outcome not in (
            DeepenOutcome.TARGET_REACHED,
            DeepenOutcome.ALREADY_DEEP_ENOUGH,
        )

    def depth_days(self, now: datetime) -> int | None:
        if self.earliest_after is None:
            return None
        return max((now - self.earliest_after).days, 0)


@dataclass(frozen=True, slots=True)
class DeepeningReport:
    target_years: int
    results: tuple[SymbolDeepening, ...] = field(default_factory=tuple)

    @property
    def stored_bars(self) -> int:
        return sum(result.stored_bars for result in self.results)

    @property
    def failures(self) -> tuple[SymbolDeepening, ...]:
        return tuple(result for result in self.results if result.failed)

    @property
    def short_of_target(self) -> tuple[SymbolDeepening, ...]:
        return tuple(result for result in self.results if result.short_of_target)

    @property
    def untouched(self) -> tuple[SymbolDeepening, ...]:
        """Aktien, die bereits tief genug waren."""
        return tuple(
            result for result in self.results if result.outcome is DeepenOutcome.ALREADY_DEEP_ENOUGH
        )


class DeepenHistoryUseCase:
    """Fuellt je Aktie rueckwaerts, bis der Zielzeitraum abgedeckt ist."""

    def __init__(
        self,
        window_source: HistoricalBarWindowSource,
        uow_factory: Callable[[], UnitOfWork],
        target_years: int,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        window_trading_days: int = FENSTERGROESSE_HANDELSTAGE,
        maximum_windows: int | None = None,
    ) -> None:
        self._window_source = window_source
        self._uow_factory = uow_factory
        self._target_years = target_years
        self._now = now
        self._window_days = window_trading_days
        self._maximum_windows = (
            maximum_windows
            if maximum_windows is not None
            else erforderliche_fenster(target_years, window_trading_days)
        )

    @property
    def maximum_windows(self) -> int:
        """Wieviele Anfragen eine Aktie hoechstens kostet -- fuer die Vorschau."""
        return self._maximum_windows

    def execute(
        self,
        watchlist: Sequence[ContractSpec],
        on_progress: Callable[[int, int, SymbolDeepening], None] | None = None,
    ) -> DeepeningReport:
        ergebnisse: list[SymbolDeepening] = []
        for index, contract in enumerate(watchlist, start=1):
            ergebnis = self._deepen_one(contract)
            ergebnisse.append(ergebnis)
            if on_progress is not None:
                on_progress(index, len(watchlist), ergebnis)
        return DeepeningReport(target_years=self._target_years, results=tuple(ergebnisse))

    def _ziel(self) -> datetime:
        """Bis wohin zurueck der Bestand reichen soll."""
        return self._now() - timedelta(days=self._target_years * 365)

    def _deepen_one(self, contract: ContractSpec) -> SymbolDeepening:
        """Eine Aktie -- und zwar so, dass nichts davon den Lauf beenden kann.

        Die Isolation umfasst ausdruecklich **beide** Seiten, wie beim
        taeglichen Backfill: Ein Ausfall der TWS ist der erwartete Fall, aber
        auch ein Fehler beim Speichern darf den Lauf nicht mitsamt allen noch
        offenen Symbolen beenden.
        """
        symbol = contract.symbol
        ziel = self._ziel()
        bars_gesamt = 0
        neu_gesamt = 0
        fenster = 0
        vorher: datetime | None = None

        try:
            with self._uow_factory() as uow:
                vorher = uow.intraday_bars.earliest_start(symbol)
        except Exception as error:  # Systemgrenze: eine Aktie, nicht der Lauf
            _logger.warning("%s: %s -- %s", symbol, type(error).__name__, error)
            return SymbolDeepening(
                symbol=symbol,
                outcome=DeepenOutcome.ERROR,
                error=f"{type(error).__name__}: {error}",
            )

        if vorher is not None and vorher <= ziel:
            # Kein Abruf. Der Fall beim zweiten Lauf -- und der Grund, warum
            # ein Wiederholen des Batches nichts kostet.
            return SymbolDeepening(
                symbol=symbol,
                outcome=DeepenOutcome.ALREADY_DEEP_ENOUGH,
                earliest_before=vorher,
                earliest_after=vorher,
            )

        rand = vorher
        aeltester = vorher
        while fenster < self._maximum_windows:
            try:
                bars = self._window_source.fetch_window(contract, rand, self._window_days)
                fenster += 1
                if bars:
                    with self._uow_factory() as uow:
                        neu = uow.intraday_bars.add_all(symbol, bars)
                        uow.commit()
                    # Erst **nach** dem Commit gezaehlt, und beide Zahlen an
                    # derselben Stelle. Scheitert der Commit, rollt die
                    # Transaktion zurueck -- ein vorher hochgezaehlter Wert
                    # meldete dann Bars als gespeichert, die keine Zeile in
                    # der Datenbank haben.
                    neu_gesamt += neu
                    bars_gesamt += len(bars)
            except Exception as error:  # Systemgrenze: eine Aktie, nicht der Lauf
                _logger.warning("%s: %s -- %s", symbol, type(error).__name__, error)
                return SymbolDeepening(
                    symbol=symbol,
                    outcome=DeepenOutcome.ERROR,
                    windows=fenster,
                    received_bars=bars_gesamt,
                    stored_bars=neu_gesamt,
                    earliest_before=vorher,
                    earliest_after=aeltester,
                    error=f"{type(error).__name__}: {error}",
                )

            if not bars:
                return SymbolDeepening(
                    symbol=symbol,
                    outcome=DeepenOutcome.PROVIDER_EXHAUSTED,
                    windows=fenster,
                    received_bars=bars_gesamt,
                    stored_bars=neu_gesamt,
                    earliest_before=vorher,
                    earliest_after=aeltester,
                )

            fenster_aeltester = min(bar.start for bar in bars)
            if aeltester is not None and fenster_aeltester >= aeltester:
                # Der Anbieter antwortet, kommt aber nicht weiter zurueck.
                # Weiterzufragen holte dieselben Bars noch einmal.
                return SymbolDeepening(
                    symbol=symbol,
                    outcome=DeepenOutcome.PROVIDER_EXHAUSTED,
                    windows=fenster,
                    received_bars=bars_gesamt,
                    stored_bars=neu_gesamt,
                    earliest_before=vorher,
                    earliest_after=aeltester,
                )

            aeltester = fenster_aeltester
            if aeltester <= ziel:
                return SymbolDeepening(
                    symbol=symbol,
                    outcome=DeepenOutcome.TARGET_REACHED,
                    windows=fenster,
                    received_bars=bars_gesamt,
                    stored_bars=neu_gesamt,
                    earliest_before=vorher,
                    earliest_after=aeltester,
                )
            # Eine Sekunde vor den aeltesten Bar -- wie bei der Messung:
            # 'end' ist ausschliessend gemeint, aber die Gegenstelle behandelt
            # den Rand nicht nachweislich so.
            rand = aeltester - timedelta(seconds=1)

        return SymbolDeepening(
            symbol=symbol,
            outcome=DeepenOutcome.WINDOW_LIMIT,
            windows=fenster,
            received_bars=bars_gesamt,
            stored_bars=neu_gesamt,
            earliest_before=vorher,
            earliest_after=aeltester,
        )
