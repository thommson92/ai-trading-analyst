from __future__ import annotations

from typing import Any


def _ensure_event_loop_exists() -> None:
    """Arbeitet um einen Python-3.14-Fund herum (siehe REPORT.md, "Frage 1"):

    ``ib_async``s Abhaengigkeit ``eventkit`` ruft beim Import
    ``asyncio.get_event_loop()`` auf. Seit Python 3.14 wirft das ohne
    laufenden Event-Loop im Hauptthread ``RuntimeError`` statt stillschweigend
    einen neuen zu erzeugen (frueheres Verhalten, auf dem ``eventkit``
    aufbaut). Ohne diesen Workaround schlaegt bereits der Import fehl.
    """
    import asyncio

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


class IbAsyncClient:
    """Duenner Adapter um ib_async.IB fuer alle Spike-Schritte.

    ib_async wird bewusst erst hier importiert, nicht auf Modulebene, damit
    die Unit-Tests ohne installierte Abhaengigkeit und ohne echte
    TWS/Gateway-Verbindung laufen (siehe test_step_*.py, Fake-Clients).
    """

    def __init__(self) -> None:
        _ensure_event_loop_exists()
        from ib_async import IB

        # ib_async.IB.__init__ ist unannotiert.
        self._ib: Any = IB()  # type: ignore[no-untyped-call]

    def connect(self, host: str, port: int, client_id: int, timeout_seconds: float) -> None:
        self._ib.connect(host, port, clientId=client_id, timeout=timeout_seconds)

    def is_connected(self) -> bool:
        return bool(self._ib.isConnected())

    def managed_accounts(self) -> list[str]:
        return list(self._ib.managedAccounts())

    def server_version(self) -> int:
        return int(self._ib.client.serverVersion())

    def connection_stats(self) -> dict[str, Any]:
        stats = self._ib.client.connectionStats()
        return {
            "start_time": stats.startTime,
            "duration_seconds": stats.duration,
            "num_bytes_recv": stats.numBytesRecv,
            "num_bytes_sent": stats.numBytesSent,
            "num_msg_recv": stats.numMsgRecv,
            "num_msg_sent": stats.numMsgSent,
        }

    def qualify_stock(self, symbol: str, exchange: str = "SMART", currency: str = "USD") -> Any:
        from ib_async import Stock

        contracts = self._ib.qualifyContracts(Stock(symbol, exchange, currency))
        if not contracts:
            raise ValueError(f"Kontrakt fuer Symbol '{symbol}' konnte nicht aufgeloest werden")
        return contracts[0]

    def fundamental_data(self, contract: Any, report_type: str) -> str:
        """Liefert Fundamentaldaten als XML-String (``reqFundamentalData``,
        offizielle IBKR-API, siehe
        https://interactivebrokers.github.io/tws-api/fundamentals.html).

        Gueltige ``report_type``-Werte laut ``ib_async``: 'ReportsFinSummary',
        'ReportsOwnership', 'ReportSnapshot', 'ReportsFinStatements', 'RESC'
        (Analystenschaetzungen), 'CalendarReport' (Firmenkalender inkl.
        Earnings-Terminen).
        """
        return str(self._ib.reqFundamentalData(contract, report_type))

    def option_chain_params(
        self,
        underlying_symbol: str,
        underlying_sec_type: str,
        underlying_con_id: int,
        fut_fop_exchange: str = "",
    ) -> list[dict[str, Any]]:
        """Liefert verfuegbare Optionsketten-Parameter (``reqSecDefOptParams``)
        -- Verfallstermine und Strikes, ohne Marktdaten oder Greeks."""
        chains = self._ib.reqSecDefOptParams(
            underlying_symbol, fut_fop_exchange, underlying_sec_type, underlying_con_id
        )
        return [
            {
                "exchange": chain.exchange,
                "trading_class": chain.tradingClass,
                "multiplier": chain.multiplier,
                "expirations": sorted(chain.expirations),
                "strikes": sorted(chain.strikes),
            }
            for chain in chains
        ]

    def option_snapshot(
        self, symbol: str, expiration: str, strike: float, right: str, exchange: str = "SMART"
    ) -> dict[str, Any]:
        """Fragt einen Options-Snapshot ab (``reqTickers``, blockierend) und
        meldet, ob IBKR modellierte Greeks (Delta/Gamma/Vega/Theta/IV)
        mitliefert -- das haengt von einer gesonderten
        Optionsmarktdaten-Berechtigung ab, nicht nur vom Aktien-Abo."""
        from ib_async import Option

        contract = Option(symbol, expiration, strike, right, exchange)
        qualified = self._ib.qualifyContracts(contract)
        if not qualified:
            raise ValueError(
                f"Optionskontrakt {symbol} {expiration} {strike}{right} "
                "konnte nicht aufgeloest werden"
            )
        tickers = self._ib.reqTickers(qualified[0])
        if not tickers:
            raise ValueError("Kein Ticker-Snapshot zurueckgegeben")
        ticker = tickers[0]
        greeks = ticker.modelGreeks
        return {
            "contract_symbol": ticker.contract.localSymbol if ticker.contract else None,
            "greeks_available": greeks is not None,
            "implied_vol": greeks.impliedVol if greeks else None,
            "delta": greeks.delta if greeks else None,
            "gamma": greeks.gamma if greeks else None,
            "vega": greeks.vega if greeks else None,
            "theta": greeks.theta if greeks else None,
        }

    def historical_bars(
        self,
        contract: Any,
        duration_str: str,
        bar_size: str,
        use_rth: bool,
    ) -> list[dict[str, Any]]:
        bars = self._ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=duration_str,
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=use_rth,
            formatDate=2,
        )
        return [
            {
                "timestamp": bar.date,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in bars
        ]

    def disconnect(self) -> None:
        self._ib.disconnect()
