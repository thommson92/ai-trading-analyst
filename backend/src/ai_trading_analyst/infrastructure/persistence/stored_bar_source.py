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

from collections.abc import Callable, Sequence

from sqlalchemy.exc import SQLAlchemyError

from ai_trading_analyst.domain.analysis import (
    ContractSpec,
    MarketDataProviderError,
    MarketDataUnavailableError,
    UnitOfWork,
)
from ai_trading_analyst.domain.screening import IntradayBar


class StoredBarSource:
    """Liest die abgelegten Bars einer Aktie.

    Je Abruf eine eigene Arbeitseinheit statt einer Sitzung fuer die gesamte
    Laufzeit. Hinter der API laeuft dieselbe Quelle ueber Stunden und viele
    Anfragen hinweg; eine dauerhaft offene Transaktion saehe dort nicht nur
    im Datenbankprotokoll schlecht aus, sie zeigte auch einen mit der Zeit
    veraltenden Ausschnitt -- der Backfill schreibt waehrenddessen weiter.
    """

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def fetch_intraday_bars(
        self, contract: ContractSpec, days: int | None = None
    ) -> Sequence[IntradayBar]:
        """``days`` wird bewusst ignoriert.

        Der Bestand ist der Bestand -- ihn zu beschneiden waere eine zweite,
        stille Stelle, an der ueber den Betrachtungszeitraum entschieden wird.
        Diese Entscheidung trifft die Kerzenbildung.
        """
        try:
            with self._uow_factory() as uow:
                bars = uow.intraday_bars.list_for(contract.symbol)
        except SQLAlchemyError as error:
            # Systemgrenze: Ohne diese Uebersetzung reisst ein
            # Datenbankproblem -- abgerissene Verbindung, Neustart des
            # Servers -- den gesamten Screening-Lauf mitsamt aller bis dahin
            # geprueften Aktien ab. Der Live-Pfad hat dieses Loch nicht, weil
            # dort jede Bibliotheksausnahme als IbkrBarSourceError ankommt.
            # Als Unterklasse, damit jede bestehende Isolation weiterhin
            # greift -- aber unterscheidbar: Dass die Datenbank nicht
            # antwortet, ist kein Befund ueber diese Aktie.
            raise MarketDataUnavailableError(
                f"Der Bestand von '{contract.symbol}' ist nicht lesbar: {error}"
            ) from error

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
