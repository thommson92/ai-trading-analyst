from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from ..config import IbkrSpikeConfig
from ..timeframe import EXCHANGE_TZ
from .base import StepStatus

STEP_ID = "supplementary_data"
TITLE = "Zusatzdaten: Earnings, Fundamentaldaten, Optionsketten mit Greeks (F9)"

# Firmenkalender ueber reqFundamentalData(reportType='CalendarReport') deckt
# u. a. den naechsten Earnings-Termin ab; 'RESC' liefert Analystenschaetzungen
# (siehe ib_async.IB.reqFundamentalData-Docstring, offizielle IBKR-API).
_CALENDAR_REPORT_TYPE = "CalendarReport"
_ANALYST_ESTIMATES_REPORT_TYPE = "RESC"


class SupplementaryDataClient(Protocol):
    def connect(self, host: str, port: int, client_id: int, timeout_seconds: float) -> None: ...

    def is_connected(self) -> bool: ...

    def qualify_stock(self, symbol: str) -> Any: ...

    def fundamental_data(self, contract: Any, report_type: str) -> str: ...

    def option_chain_params(
        self,
        underlying_symbol: str,
        underlying_sec_type: str,
        underlying_con_id: int,
        fut_fop_exchange: str = "",
    ) -> list[dict[str, Any]]: ...

    def option_snapshot(
        self, symbol: str, expiration: str, strike: float, right: str, exchange: str = "SMART"
    ) -> dict[str, Any]: ...

    def disconnect(self) -> None: ...


def default_client_factory() -> SupplementaryDataClient:
    from ..ibkr_client import IbAsyncClient

    return IbAsyncClient()


def run(
    config: IbkrSpikeConfig,
    symbol: str,
    client_factory: Any = default_client_factory,
) -> dict[str, Any]:
    """Prueft, ob IBKR neben Kursdaten auch Earnings-Termine,
    Analystenschaetzungen und Optionsketten mit modellierten Greeks liefert
    (F9) -- oder ob dafuer weiterhin separate Anbieter noetig sind. Jede
    Teilanfrage wird unabhaengig ausgewertet: schlaegt eine fehl (z. B. wegen
    fehlender Zusatzabo-Berechtigung), blockiert das nicht die uebrigen.
    """
    client = client_factory()
    try:
        client.connect(config.host, config.port, config.client_id, config.timeout_seconds)
    except Exception as exc:
        return {
            "_status": StepStatus.FAILED.value,
            "symbol": symbol,
            "error": f"{type(exc).__name__}: {exc}",
        }

    try:
        if not client.is_connected():
            return {
                "_status": StepStatus.FAILED.value,
                "symbol": symbol,
                "error": "Verbindung nicht hergestellt (is_connected() == False)",
            }

        try:
            contract = client.qualify_stock(symbol)
        except Exception as exc:
            return {
                "_status": StepStatus.FAILED.value,
                "symbol": symbol,
                "error": f"Kontrakt-Aufloesung fehlgeschlagen: {type(exc).__name__}: {exc}",
            }

        return {
            "_status": StepStatus.OK.value,
            "symbol": symbol,
            "earnings_calendar": _probe_fundamental(client, contract, _CALENDAR_REPORT_TYPE),
            "analyst_estimates": _probe_fundamental(
                client, contract, _ANALYST_ESTIMATES_REPORT_TYPE
            ),
            "option_chain": _probe_option_chain(client, contract, symbol),
        }
    finally:
        client.disconnect()


def _probe_fundamental(
    client: SupplementaryDataClient, contract: Any, report_type: str
) -> dict[str, Any]:
    try:
        xml = client.fundamental_data(contract, report_type)
    except Exception as exc:
        return {
            "report_type": report_type,
            "status": StepStatus.FAILED.value,
            "error": f"{type(exc).__name__}: {exc}",
        }

    if not xml.strip():
        return {
            "report_type": report_type,
            "status": StepStatus.INCONCLUSIVE.value,
            "reason": "Leere oder inhaltslose Antwort (nur Whitespace) -- vermutlich keine "
            "Berechtigung oder keine Daten fuer diesen Report-Typ",
        }

    return {
        "report_type": report_type,
        "status": StepStatus.OK.value,
        # Nur die Laenge, nicht der volle XML-Inhalt -- der Inhalt selbst ist
        # oeffentliche Unternehmensdaten, aber fuer diesen Machbarkeitsnachweis
        # reicht der Beleg, dass ueberhaupt eine Antwort zurueckkommt.
        "xml_length": len(xml),
    }


def _probe_option_chain(
    client: SupplementaryDataClient, contract: Any, symbol: str
) -> dict[str, Any]:
    try:
        chains = client.option_chain_params(symbol, contract.secType, contract.conId)
    except Exception as exc:
        return {
            "status": StepStatus.FAILED.value,
            "error": f"{type(exc).__name__}: {exc}",
        }

    if not chains:
        return {
            "status": StepStatus.INCONCLUSIVE.value,
            "reason": "Keine Optionsketten-Parameter zurueckgegeben",
        }

    chain = chains[0]
    today = datetime.now(tz=EXCHANGE_TZ).strftime("%Y%m%d")
    future_expirations = sorted(e for e in chain["expirations"] if e >= today)
    if not future_expirations or not chain["strikes"]:
        return {
            "status": StepStatus.INCONCLUSIVE.value,
            "reason": "Kette ohne zukuenftige Verfallstermine oder ohne Strikes",
            "chain_count": len(chains),
        }

    nearest_expiration = future_expirations[0]
    strikes = sorted(chain["strikes"])
    # Grobe Naeherung an ATM ohne aktuellen Kurs abzufragen -- der Median der
    # gelisteten Strikes reicht fuer diesen Machbarkeitstest (es geht darum,
    # OB Greeks fliessen, nicht um einen realistischen Handelskandidaten.
    approx_atm_strike = strikes[len(strikes) // 2]

    result: dict[str, Any] = {
        "status": StepStatus.OK.value,
        "chain_count": len(chains),
        "exchange": chain["exchange"],
        "expiration_count": len(chain["expirations"]),
        "strike_count": len(chain["strikes"]),
        "nearest_expiration": nearest_expiration,
        "greeks_probe": _probe_option_greeks(
            client, symbol, nearest_expiration, approx_atm_strike, chain["exchange"]
        ),
    }
    return result


def _probe_option_greeks(
    client: SupplementaryDataClient,
    symbol: str,
    expiration: str,
    strike: float,
    exchange: str,
) -> dict[str, Any]:
    try:
        snapshot = client.option_snapshot(symbol, expiration, strike, "C", exchange)
    except Exception as exc:
        return {
            "status": StepStatus.FAILED.value,
            "error": f"{type(exc).__name__}: {exc}",
        }

    if not snapshot.get("greeks_available"):
        return {
            "status": StepStatus.INCONCLUSIVE.value,
            "reason": "Snapshot ohne modellierte Greeks -- vermutlich fehlende "
            "Optionsmarktdaten-Berechtigung",
        }

    return {
        "status": StepStatus.OK.value,
        "implied_vol": snapshot["implied_vol"],
        "delta": snapshot["delta"],
        "gamma": snapshot["gamma"],
        "vega": snapshot["vega"],
        "theta": snapshot["theta"],
    }
