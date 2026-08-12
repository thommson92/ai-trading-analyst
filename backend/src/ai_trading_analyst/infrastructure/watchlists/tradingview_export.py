"""Einlesen der aus TradingView exportierten Watchlisten.

TradingView ist als *Datenquelle* ausgeschieden (ADR 0012). Die dort
gepflegten **Listen** bleiben davon unberuehrt: Sie sind eine Aufzaehlung von
Tickersymbolen, die der Nutzer selbst exportiert -- keine Kurs- oder
Indikatordaten und damit nicht von den Nutzungsbedingungen erfasst, an denen
Gate G3 gescheitert ist. Die Kurse kommen ausschliesslich von IBKR.

Format einer Exportdatei (eine Zeile, kommagetrennt)::

    ###PJM SONSTIGE,NYSE:ABT,NASDAQ:ADSK,...,###VALUE LINE,NYSE:A,...

* ``BOERSE:SYMBOL`` ist ein Eintrag.
* ``###NAME`` ist eine Abschnittsueberschrift und kein Symbol.
* Ein Symbol ohne Boersenpraefix ist zulaessig; dann bleibt die Heimatboerse
  offen und IBKR loest ueber Smart Routing auf.

Zwei Uebersetzungen sind noetig, weil TradingView und IBKR dieselben Papiere
unterschiedlich schreiben:

* Anteilsklassen: TradingView ``BRK.B``, IBKR ``BRK B``.
* Heimatboerse: ``NASDAQ``/``NYSE`` werden als ``primaryExchange`` gesetzt,
  nicht als Handelsweg -- gehandelt bzw. abgefragt wird ueber ``SMART``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from ai_trading_analyst.infrastructure.ibkr import ContractSpec

SECTION_PREFIX = "###"
WATCHLIST_FILE_SUFFIX = ".txt"

_PRIMARY_EXCHANGES = {
    "NASDAQ": "NASDAQ",
    "NYSE": "NYSE",
    "AMEX": "AMEX",
    "ARCA": "ARCA",
    "BATS": "BATS",
}


class WatchlistError(RuntimeError):
    """Eine Watchlist-Datei oder ein Verzeichnis war nicht verwertbar."""


def _to_contract(entry: str) -> ContractSpec | None:
    """Uebersetzt einen Eintrag; ``None`` fuer Ueberschriften und Leerstellen."""
    entry = entry.strip()
    if not entry or entry.startswith(SECTION_PREFIX):
        return None

    exchange_prefix, separator, symbol = entry.partition(":")
    if not separator:
        exchange_prefix, symbol = "", entry

    symbol = symbol.strip().replace(".", " ")
    if not symbol:
        return None

    return ContractSpec(
        symbol=symbol,
        primary_exchange=_PRIMARY_EXCHANGES.get(exchange_prefix.strip().upper()),
    )


def parse_watchlist(text: str) -> tuple[ContractSpec, ...]:
    """Liest eine einzelne Exportdatei.

    Zeilenumbrueche sind zugelassen, auch wenn TradingView alles in eine Zeile
    schreibt -- eine von Hand nachbearbeitete Datei soll nicht scheitern.
    """
    entries = (part for line in text.splitlines() for part in line.split(","))
    contracts = (_to_contract(entry) for entry in entries)
    return tuple(contract for contract in contracts if contract is not None)


def deduplicate(contracts: Iterable[ContractSpec]) -> tuple[ContractSpec, ...]:
    """Entfernt Mehrfachnennungen; das erste Vorkommen gewinnt.

    Dieselbe Aktie steht haeufig auf mehreren Listen. Sie zweimal abzufragen
    waere doppelte Laufzeit an einer Schnittstelle mit Anfragelimits und
    zusaetzlich ein doppelter Screening-Eintrag pro Lauf.
    """
    seen: dict[str, ContractSpec] = {}
    for contract in contracts:
        seen.setdefault(contract.symbol, contract)
    return tuple(seen.values())


def load_watchlist_directory(directory: Path) -> tuple[ContractSpec, ...]:
    """Liest alle ``*.txt`` eines Verzeichnisses in alphabetischer Reihenfolge.

    Raises:
        WatchlistError: wenn das Verzeichnis fehlt, keines ist, keine Datei
            enthaelt oder eine Datei nicht lesbar ist. Eine stillschweigend
            leere Watchlist wuerde einen Lauf ohne einen einzigen geprueften
            Titel als Erfolg aussehen lassen.
    """
    if not directory.is_dir():
        raise WatchlistError(f"Watchlist-Verzeichnis existiert nicht: {directory}")

    files = sorted(path for path in directory.iterdir() if path.suffix == WATCHLIST_FILE_SUFFIX)
    if not files:
        raise WatchlistError(
            f"Im Watchlist-Verzeichnis {directory} liegt keine {WATCHLIST_FILE_SUFFIX}-Datei"
        )

    collected: list[ContractSpec] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError as error:
            raise WatchlistError(f"Watchlist-Datei nicht lesbar: {path}") from error
        collected.extend(parse_watchlist(text))

    contracts = deduplicate(collected)
    if not contracts:
        raise WatchlistError(
            f"Die Watchlist-Dateien in {directory} enthalten kein einziges Symbol"
        )
    return contracts


def describe_sources(directory: Path) -> Sequence[str]:
    """Namen der eingelesenen Dateien -- fuer Protokoll und Bericht."""
    return tuple(
        path.name for path in sorted(directory.iterdir()) if path.suffix == WATCHLIST_FILE_SUFFIX
    )
