"""Historischer Backfill: den Bestand an nativen Bars auffuellen.

Der Job holt beim Anbieter **nur, was fehlt**. Er kennt dafuer keinen festen
Zeitraum, sondern fragt den Bestand: Bis wann liegen fuer diese Aktie schon
Bars vor? Daraus ergibt sich die Anfrage — ein Tag nach einem gewoehnlichen
Lauf, drei Wochen nach einem Serverausfall, der volle Standardzeitraum beim
allerersten Mal.

Das ist die Anforderung aus [ADR 0018](../../../docs/adr/0018-kein-windows-autologon.md):
Weil nach dem sonntaeglichen Neustart erst am Montag von Hand gestartet wird,
muss der Backfill **beliebig grosse Luecken** schliessen koennen. Ein
verlaengertes Wochenende darf kein Sonderfall sein.

Zwei Eigenschaften machen den Lauf betriebstauglich (ADR 0014, E3):

* **Wiederholbar.** Das Speichern ist ueber ``(symbol, start)`` idempotent.
  Ein abgebrochener Lauf wird schlicht erneut gestartet; aufzuraeumen gibt es
  nichts.
* **Fehlerisoliert.** Faellt eine Aktie aus, laeuft der Rest weiter. Bei rund
  200 Symbolen und einer Stunde Laufzeit waere ein Abbruch beim ersten
  unbekannten Symbol die schlechteste aller Antworten.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from ai_trading_analyst.domain.analysis import (
    ContractSpec,
    HistoricalBarSource,
    UnitOfWork,
)
from ai_trading_analyst.domain.screening import IntradayBar
from ai_trading_analyst.observability.logging_setup import get_logger

_logger = get_logger(__name__)

UEBERLAPPUNG_TAGE = 1
"""Wieviel ueber den letzten bekannten Bar hinaus zurueckgefragt wird.

Ein Tag Ueberlappung kostet nichts -- doppelte Bars werden beim Speichern
uebergangen -- und verhindert den Fall, in dem ein Lauf mitten in einem
Handelstag abbricht und der naechste genau diesen Rest ueberspringt.
"""

STANDARDZEITRAUM_TAGE = 365
"""Was ``market_data.ibkr.history_duration`` ausliefert, in Tagen.

Der Backfill schickt beim ersten Lauf weiterhin den konfigurierten Zeitraum in
IBKR-Schreibweise. Fuer die Kuerzungspruefung braucht es daneben eine Zahl --
ohne sie bliebe ausgerechnet der lange erste Abruf ungeprueft, also der Fall,
fuer den die Pruefung geschrieben wurde. Die CLI reicht den tatsaechlich
konfigurierten Wert durch.
"""

MINDESTZEITRAUM_FUER_KUERZUNGSPRUEFUNG = 10
"""Ab wievielen angefragten Tagen die Kuerzungspruefung ueberhaupt greift.

Siehe ``SymbolBackfill.truncated``: Bei einem oder zwei Tagen ist eine kurze
Antwort der Normalfall und keine Kuerzung.
"""


@dataclass(frozen=True, slots=True)
class SymbolBackfill:
    """Was der Lauf fuer eine Aktie erreicht hat."""

    symbol: str
    requested_days: int | None
    received_bars: int = 0
    stored_bars: int = 0
    covered_days: int | None = None
    error: str | None = None
    earliest_received: datetime | None = None
    latest_stored_before: datetime | None = None

    @property
    def failed(self) -> bool:
        return self.error is not None

    @property
    def gap_to_stored(self) -> bool:
        """Setzt die Antwort am vorhandenen Bestand an -- oder klafft dazwischen?

        Der genaue Gegenpart zur naeherungsweisen ``truncated``: Hier gibt es
        nichts zu schaetzen. Lag im Bestand bereits ein Bar und beginnt die
        Antwort **spaeter** als dieser, fehlt der Zeitraum dazwischen
        zweifelsfrei -- und er wird nie von allein nachgeholt, weil der naechste
        Lauf wieder nur den juengsten Bar kennt.

        Der gewoehnliche Lauf loest das nicht aus: Die Anfrage reicht ueber die
        Ueberlappung hinaus zurueck, die Antwort beginnt also vor dem letzten
        gespeicherten Bar.
        """
        if self.earliest_received is None or self.latest_stored_before is None:
            return False
        return self.earliest_received > self.latest_stored_before

    @property
    def truncated(self) -> bool:
        """Deckt die Antwort den angefragten Zeitraum nur zum Teil ab?

        IBKR kuerzt lange Antworten stillschweigend -- beim Earnings-Kalender
        war es dieselbe Bauart, dort fehlten die naechsten sechs Wochen ohne
        jeden Hinweis. Beim Abruf je Lauf heilte sich das von selbst; im
        Bestand bliebe die Luecke dauerhaft, und die Kerzenbildung kann einen
        **vollstaendig** fehlenden Handelstag nicht erkennen.

        Deshalb wird hier verglichen, was angefragt und was geliefert wurde.
        Ein legitimer Grund ist eine kurze Boersenhistorie (Neuemission) --
        deshalb ein Hinweis und kein Fehler.

        Kurze Zeitraeume bleiben ausgenommen. Eine Anfrage ueber einen Tag
        beantwortet IBKR mit den Bars des laufenden Handelstages; die reichen
        keine 24 Stunden zurueck, und der Vergleich meldete jeden
        gewoehnlichen taeglichen Lauf als gekuerzt. Erst ueber mehrere Tage
        traegt er.
        """
        if self.requested_days is None or self.covered_days is None:
            return False
        if self.requested_days < MINDESTZEITRAUM_FUER_KUERZUNGSPRUEFUNG:
            return False
        return self.covered_days * 2 < self.requested_days


@dataclass(frozen=True, slots=True)
class BackfillReport:
    results: tuple[SymbolBackfill, ...] = field(default_factory=tuple)

    @property
    def stored_bars(self) -> int:
        return sum(result.stored_bars for result in self.results)

    @property
    def failures(self) -> tuple[SymbolBackfill, ...]:
        return tuple(result for result in self.results if result.failed)

    @property
    def truncated(self) -> tuple[SymbolBackfill, ...]:
        return tuple(result for result in self.results if result.truncated)

    @property
    def gaps(self) -> tuple[SymbolBackfill, ...]:
        return tuple(result for result in self.results if result.gap_to_stored)

    @property
    def empty(self) -> tuple[SymbolBackfill, ...]:
        """Aktien, fuer die ueberhaupt nichts kam.

        Weder Fehler noch Kuerzung -- und deshalb bisher in keiner Zeile der
        Bilanz sichtbar. Bei knapp 200 Symbolen ist das genau die Sorte
        Ergebnis, die untergeht.
        """
        return tuple(
            result for result in self.results if not result.failed and result.received_bars == 0
        )


def missing_days(
    latest_start: datetime | None, now: datetime, overlap_days: int = UEBERLAPPUNG_TAGE
) -> int | None:
    """Wieviele Tage muessen nachgeholt werden?

    ``None`` heisst: Es liegt noch nichts vor, also der konfigurierte
    Standardzeitraum. Sonst der Abstand zum juengsten Bar, um die Ueberlappung
    erweitert -- mindestens aber ein Tag, damit auch ein Lauf kurz nach dem
    letzten Bar noch die laufende Sitzung nachzieht.

    Gezaehlt werden **Kalendertage**, nicht verstrichene 24-Stunden-Zeitraeume.
    Der Unterschied entscheidet nach einem Abbruch mitten in der Sitzung: Bricht
    ein Lauf gestern um 11:00 ab und startet der naechste heute um 09:52, sind
    keine 24 Stunden vergangen. Nach Stunden gerechnet waere das "ein Tag" --
    und die Anfrage deckte nur den heutigen Handelstag ab, waehrend der Rest
    von gestern dauerhaft fehlte. Der Bestand kennt danach nur seinen juengsten
    Bar und fragte diesen Zeitraum nie wieder an; die Luecke bliebe bis zu
    einem Lauf mit ``--from`` bestehen. Das widerspraeche der Zusage, dass ein
    abgebrochener Lauf schlicht erneut gestartet werden kann.

    Die Kalendertage werden in UTC gezaehlt. Fuer regulaere US-Handelszeiten
    ist das eindeutig: 09:30 bis 16:00 New Yorker Zeit liegen ganzjaehrig
    zwischen 13:30 und 21:00 UTC, also immer am selben UTC-Datum.
    """
    if latest_start is None:
        return None
    abstand = (now.date() - latest_start.date()).days
    return max(abstand + overlap_days, 1)


def _covered_days(bars: Sequence[IntradayBar], now: datetime) -> int | None:
    """Wie weit zurueck reicht die Antwort tatsaechlich?"""
    if not bars:
        return None
    return max((now - min(bar.start for bar in bars)).days, 0)


class BackfillHistoryUseCase:
    def __init__(
        self,
        bar_source: HistoricalBarSource,
        uow_factory: Callable[[], UnitOfWork],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        from_date: date | None = None,
        default_days: int = STANDARDZEITRAUM_TAGE,
    ) -> None:
        self._bar_source = bar_source
        self._uow_factory = uow_factory
        self._now = now
        self._from_date = from_date
        self._default_days = default_days

    def execute(
        self,
        watchlist: Sequence[ContractSpec],
        on_progress: Callable[[int, int, SymbolBackfill], None] | None = None,
    ) -> BackfillReport:
        ergebnisse: list[SymbolBackfill] = []
        for index, contract in enumerate(watchlist, start=1):
            ergebnis = self._backfill_one(contract)
            ergebnisse.append(ergebnis)
            if on_progress is not None:
                on_progress(index, len(watchlist), ergebnis)
        return BackfillReport(results=tuple(ergebnisse))

    def _backfill_one(self, contract: ContractSpec) -> SymbolBackfill:
        """Eine Aktie -- und zwar so, dass nichts davon den Lauf beenden kann.

        Die Isolation umfasst ausdruecklich **beide** Seiten. Ein Ausfall der
        TWS ist der erwartete Fall, aber ein Fehler beim Speichern -- eine zu
        grosse Lieferung, eine abgerissene Datenbankverbindung -- wuerde den
        Lauf sonst mitsamt allen noch nicht geholten Symbolen beenden. Bei 200
        Symbolen und einer Stunde Laufzeit waere das die schlechteste aller
        Antworten, und der Nutzer saehe einen Traceback statt eines Berichts.
        """
        symbol = contract.symbol
        angefragt: int | None = None
        bestand_vorher: datetime | None = None
        try:
            with self._uow_factory() as uow:
                bestand_vorher = uow.intraday_bars.latest_start(symbol)
            # ``None`` heisst hier: der in IBKR-Schreibweise konfigurierte
            # Standardzeitraum. So bleibt die Anfrage an die TWS unveraendert;
            # nur der Bericht rechnet ihn zum Vergleichen in Tage um.
            angefragt = self._request_days(bestand_vorher)
            bars = self._bar_source.fetch_intraday_bars(contract, angefragt)
            with self._uow_factory() as uow:
                neu = uow.intraday_bars.add_all(symbol, bars)
                uow.commit()
        except Exception as error:  # Systemgrenze: eine Aktie, nicht der Lauf
            _logger.warning("%s: %s -- %s", symbol, type(error).__name__, error)
            return SymbolBackfill(
                symbol=symbol, requested_days=angefragt, error=f"{type(error).__name__}: {error}"
            )

        return SymbolBackfill(
            symbol=symbol,
            requested_days=angefragt if angefragt is not None else self._default_days,
            received_bars=len(bars),
            stored_bars=neu,
            covered_days=_covered_days(bars, self._now()),
            earliest_received=min((bar.start for bar in bars), default=None),
            latest_stored_before=bestand_vorher,
        )

    def _request_days(self, latest_stored: datetime | None) -> int | None:
        """Wie weit zurueck gefragt wird.

        ``--from`` uebersteuert den Bestand. Das ist der Weg, einen Zeitraum
        erneut zu holen, den der Bestand von sich aus nie wieder anfragen
        wuerde -- er kennt nur seinen juengsten Bar, ein fehlender innerer Tag
        bleibt ihm verborgen.

        Was ``--from`` **nicht** kann: bereits gespeicherte Bars berichtigen.
        Die Ablage laesst Dubletten fallen, damit ein wiederholter Lauf nichts
        anrichtet; ein vorhandener Bar bleibt deshalb stehen, wie er ist.
        Fuellen laesst sich damit nur, was fehlt.
        """
        if self._from_date is not None:
            return max((self._now().date() - self._from_date).days, 1)
        return missing_days(latest_stored, self._now())
