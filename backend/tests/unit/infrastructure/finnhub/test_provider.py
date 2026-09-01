"""Tests des Finnhub-Adapters.

Der echte Netzwerkfehler wird gegen einen tatsaechlich unbesetzten lokalen
Port geprueft, nicht gemockt -- ein Testdoppel fuer ``httpx`` wuerde nur die
eigene Annahme ueber die Bibliothek pruefen (gleiches Prinzip wie
``tests/unit/infrastructure/ibkr/test_bar_source.py``). Alles, was sich ohne
echtes Netzwerk pruefen laesst (Antwort-Parsing, Fehlerformate), laeuft ueber
``httpx.MockTransport`` -- das ist die von ``httpx`` selbst vorgesehene
Teststrategie, kein Mock der Bibliothek.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from ai_trading_analyst.domain.analysis import Stock
from ai_trading_analyst.infrastructure.finnhub.provider import (
    FinnhubConnectionSettings,
    FinnhubEarningsProvider,
    FinnhubEarningsProviderError,
)

SETTINGS = FinnhubConnectionSettings(
    base_url="https://finnhub.io/api/v1",
    api_key="test-key",
    request_timeout_seconds=1.0,
    lookahead_calendar_days=30,
    max_requests_per_second=1000.0,
)
TODAY = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
AAPL = Stock(id=uuid.uuid4(), symbol="AAPL", exchange="NASDAQ")


def _provider(handler: httpx.MockTransport) -> FinnhubEarningsProvider:
    return FinnhubEarningsProvider(SETTINGS, now=lambda: TODAY, transport=handler)


def _json_transport(payload: object, status_code: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    return httpx.MockTransport(handler)


class TestErfolgreicheAntwort:
    def test_einzelner_treffer(self) -> None:
        transport = _json_transport(
            {"earningsCalendar": [{"date": "2026-09-01", "symbol": "AAPL", "hour": "amc"}]}
        )
        termin = _provider(transport).next_earnings_date(AAPL)
        assert termin is not None
        assert termin.date == date(2026, 9, 1)
        assert termin.source == "finnhub"

    def test_mehrere_treffer_liefern_den_fruehesten(self) -> None:
        transport = _json_transport(
            {
                "earningsCalendar": [
                    {"date": "2026-09-15", "symbol": "AAPL", "hour": "bmo"},
                    {"date": "2026-09-01", "symbol": "AAPL", "hour": "amc"},
                ]
            }
        )
        termin = _provider(transport).next_earnings_date(AAPL)
        assert termin is not None
        assert termin.date == date(2026, 9, 1)

    def test_leere_liste_ergibt_keine_abdeckung(self) -> None:
        transport = _json_transport({"earningsCalendar": []})
        assert _provider(transport).next_earnings_date(AAPL) is None

    def test_anfrage_traegt_symbol_und_zeitfenster(self) -> None:
        gesehen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            gesehen.update(dict(request.url.params))
            return httpx.Response(200, json={"earningsCalendar": []})

        _provider(httpx.MockTransport(handler)).next_earnings_date(AAPL)
        assert gesehen["symbol"] == "AAPL"
        assert gesehen["from"] == "2026-08-17"
        assert gesehen["to"] == "2026-09-16"

    def test_der_schluessel_steht_im_header_und_nicht_in_der_url(self) -> None:
        """ADR 0044 hat den Weg benannt, A2-M10 geht ihn: Was nicht in der
        URL steht, kann auch nicht in einem Fehlertext auftauchen."""
        gesehen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            gesehen.append(request)
            return httpx.Response(200, json={"earningsCalendar": []})

        _provider(httpx.MockTransport(handler)).next_earnings_date(AAPL)

        (anfrage,) = gesehen
        assert anfrage.headers["X-Finnhub-Token"] == "test-key"
        assert "token" not in anfrage.url.params
        assert "test-key" not in str(anfrage.url)


class TestFehlerhafteAntwort:
    def test_fehlendes_feld_wirft_klaren_fehler(self) -> None:
        transport = _json_transport({"unerwartet": True})
        with pytest.raises(FinnhubEarningsProviderError, match="earningsCalendar"):
            _provider(transport).next_earnings_date(AAPL)

    def test_feld_ist_null_statt_liste_wirft_klaren_fehler(self) -> None:
        transport = _json_transport({"earningsCalendar": None})
        with pytest.raises(FinnhubEarningsProviderError, match="earningsCalendar"):
            _provider(transport).next_earnings_date(AAPL)

    def test_kaputtes_json_wirft_klaren_fehler(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"nicht-json")

        with pytest.raises(FinnhubEarningsProviderError):
            _provider(httpx.MockTransport(handler)).next_earnings_date(AAPL)

    def test_http_fehlerstatus_wirft_klaren_fehler(self) -> None:
        transport = _json_transport({"error": "unauthorized"}, status_code=401)
        with pytest.raises(FinnhubEarningsProviderError, match="AAPL"):
            _provider(transport).next_earnings_date(AAPL)

    def test_unplausibel_viele_treffer_loesen_die_kuerzungswache_aus(self) -> None:
        entries = [{"date": "2026-09-01", "symbol": "AAPL"} for _ in range(51)]
        transport = _json_transport({"earningsCalendar": entries})
        with pytest.raises(FinnhubEarningsProviderError, match="unplausibel"):
            _provider(transport).next_earnings_date(AAPL)

    def test_fehlendes_datumsfeld_in_einem_eintrag(self) -> None:
        transport = _json_transport({"earningsCalendar": [{"symbol": "AAPL"}]})
        with pytest.raises(FinnhubEarningsProviderError):
            _provider(transport).next_earnings_date(AAPL)


class TestEchterNetzwerkfehler:
    def test_ein_unbesetzter_port_meldet_sich_klar(self) -> None:
        settings = FinnhubConnectionSettings(
            base_url="http://127.0.0.1:1",
            api_key="test-key",
            request_timeout_seconds=1.0,
            lookahead_calendar_days=30,
            max_requests_per_second=1000.0,
        )
        provider = FinnhubEarningsProvider(settings, now=lambda: TODAY)
        with pytest.raises(FinnhubEarningsProviderError, match="AAPL"):
            provider.next_earnings_date(AAPL)


class TestSchluesselLandetNichtImFehlertext:
    """Derselbe Mangel bestand hier seit dem ersten Tag: ``httpx`` schreibt
    die vollstaendige URL in seine Ausnahmetexte, und der Schluessel stand
    darin als Query-Parameter.

    Seit A2-M10 steht er im Header. Die Schwaerzung bleibt als zweite Reihe
    geprueft -- der naechste ergaenzte Parameter soll nicht darauf angewiesen
    sein, dass jemand diesen Wechsel kennt.
    """

    def test_ein_http_fehler_verraet_den_schluessel_nicht(self) -> None:
        provider = _provider(_json_transport({"error": "boom"}, status_code=500))

        with pytest.raises(FinnhubEarningsProviderError) as fehler:
            provider.next_earnings_date(AAPL)

        assert "test-key" not in str(fehler.value)
        assert "AAPL" in str(fehler.value)


class TestEingefroreneAntwort:
    """Gegenprobe an der echten Antwort vom 2026-09-01 (A2-M7).

    Die Faelle oben pruefen je eine Regel an einer selbst geschriebenen
    Antwort -- und genau das ist ihre Grenze: Benennt Finnhub morgen ein Feld
    um, bleiben sie gruen, weil sie den alten Namen selbst hinschreiben. Erst
    eine **fremde** Antwort kann diese Aenderung melden. Herkunft und
    Neuaufzeichnung stehen in ``data/HERKUNFT.md``.
    """

    def test_die_echte_antwort_ergibt_denselben_termin(self) -> None:
        pfad = Path(__file__).parent / "data" / "calendar-earnings-AAPL.json"
        payload = json.loads(pfad.read_text(encoding="utf-8"))

        termin = _provider(_json_transport(payload)).next_earnings_date(AAPL)

        assert termin is not None
        assert termin.date == date(2026, 10, 28)
        assert termin.source == "finnhub"

    def test_die_felder_daneben_stoeren_nicht(self) -> None:
        """Finnhub liefert je Eintrag acht Felder; der Adapter liest eines.

        Der Test steht hier, weil die selbst geschriebenen Antworten oben nur
        ``date``, ``symbol`` und ``hour`` enthalten -- an ihnen laesst sich
        nicht sehen, ob Schaetzwerte und Nullwerte danebenliegen duerfen.
        """
        pfad = Path(__file__).parent / "data" / "calendar-earnings-AAPL.json"
        payload = json.loads(pfad.read_text(encoding="utf-8"))

        (eintrag,) = payload["earningsCalendar"]
        assert eintrag["epsActual"] is None, "ein zukuenftiger Termin, wie beabsichtigt"
        assert "epsEstimate" in eintrag and "revenueEstimate" in eintrag

        assert _provider(_json_transport(payload)).next_earnings_date(AAPL) is not None
