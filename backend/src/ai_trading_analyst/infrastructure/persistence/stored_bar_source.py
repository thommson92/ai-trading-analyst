"""Barquelle, die aus dem eigenen Bestand liest statt beim Anbieter zu fragen.

Damit zerfaellt der taegliche Ablauf in zwei Schritte, die einander nicht
brauchen:

1. Der **Backfill** holt beim Anbieter nur, was seit dem letzten Lauf
   hinzugekommen ist, und legt es ab.
2. Der **Screener** rechnet auf dem Bestand -- ohne Netzwerk, ohne TWS, ohne
   Pacing.

Der Gewinn ist nicht nur Geschwindigkeit. Der Screener wird dadurch
**wiederholbar**: Dieselbe Analyse laesst sich morgen erneut rechnen und
liefert dasselbe Ergebnis, weil die Rohdaten liegen bleiben. Bei einem Abruf
je Lauf war das nicht gegeben -- IBKRs Ein-Jahres-Fenster wandert mit der
Uhr, und schon zwei Laeufe desselben Tages ergaben unterschiedlich viele
Kerzen.

Technisch ist die Klasse eine ``HistoricalBarSource`` wie jede andere. Der
``IbkrMarketDataProvider`` merkt nicht, woher seine Bars kommen.
"""

from __future__ import annotations

from collections.abc import Sequence

from ai_trading_analyst.domain.analysis import (
    ContractSpec,
    IntradayBarRepository,
    MarketDataProviderError,
)
from ai_trading_analyst.domain.screening import IntradayBar


class StoredBarSource:
    """Liest die abgelegten Bars einer Aktie."""

    def __init__(self, repository: IntradayBarRepository) -> None:
        self._repository = repository

    def fetch_intraday_bars(
        self, contract: ContractSpec, days: int | None = None
    ) -> Sequence[IntradayBar]:
        """``days`` wird bewusst ignoriert.

        Der Bestand ist der Bestand -- ihn zu beschneiden waere eine zweite,
        stille Stelle, an der ueber den Betrachtungszeitraum entschieden wird.
        Diese Entscheidung trifft die Kerzenbildung.
        """
        bars = self._repository.list_for(contract.symbol)
        if not bars:
            # Ohne diesen Hinweis waere die Meldung "keine abgeschlossene
            # Kerze" -- richtig, aber irrefuehrend: Es fehlt nicht die Kerze,
            # es fehlt der Backfill.
            raise MarketDataProviderError(
                f"Fuer '{contract.symbol}' sind keine Bars gespeichert. "
                "Zuerst den Backfill laufen lassen."
            )
        return bars

    def close(self) -> None:
        """Es gibt keine Verbindung, die freizugeben waere."""
