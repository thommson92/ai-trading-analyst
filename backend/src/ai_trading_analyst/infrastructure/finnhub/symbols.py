"""Uebersetzung der Symbolschreibweise fuer Finnhub.

Klassenaktien schreibt jede Quelle anders: IBKR fuehrt Berkshire als
``BRK B``, Finnhub als ``BRK.B``. Die Watchlist uebernimmt die
IBKR-Schreibweise (``infrastructure/watchlists/tradingview_export.py``), und
genau so kam das Symbol bislang bei Finnhub an -- der Kalender fand nichts,
und der Lauf meldete ``no_coverage``, wo nur die Schreibweise abwich
(ADR 0017 L3).

Bewusst keine Suche und keine Aehnlichkeit (Muster ``_schreibweisen`` im
EDGAR-Adapter): nur das eine Trennzeichen, das tatsaechlich vorkommt. Ein
Symbol, das Finnhub nicht kennt, soll weiterhin leer ausgehen und nicht auf
ein aehnliches umgebogen werden.

Ein gemeinsames Modul fuer beide Finnhub-Endpunkte: Sie teilen Konto,
Schluessel und Host -- und damit auch die Symbolik.
"""

from __future__ import annotations


def finnhub_symbol(symbol: str) -> str:
    """IBKR-Schreibweise nach Finnhub uebersetzen: ``BRK B`` wird ``BRK.B``."""
    return symbol.strip().upper().replace(" ", ".")
