"""Der EDGAR-Abruf (ADR 0032, Entscheidung 7).

Ohne Netz: ``httpx.MockTransport`` beantwortet die Anfragen, wie es die
uebrigen Adapter-Tests auch tun.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from ai_trading_analyst.domain.analysis import FundamentalDataProviderError, Stock
from ai_trading_analyst.domain.fundamentals import FundamentalStatus, MetricName
from ai_trading_analyst.infrastructure.edgar import (
    EdgarConnectionSettings,
    EdgarFundamentalDataProvider,
)
from ai_trading_analyst.infrastructure.edgar.provider import _Drossel

SETTINGS = EdgarConnectionSettings(
    base_url="https://data.example",
    index_base_url="https://www.example",
    contact="pruefer@example.org",
    request_timeout_seconds=5,
    max_requests_per_second=1000.0,
)

AKTIE = Stock(id=uuid4(), symbol="TEST", exchange="NASDAQ")

VERZEICHNIS = {"0": {"cik_str": 42, "ticker": "TEST", "title": "Test Inc."}}

FACTS = {
    "cik": 42,
    "entityName": "Test Inc.",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "units": {
                    "USD": [
                        {
                            "val": 1000.0,
                            "start": "2024-01-01",
                            "end": "2024-12-31",
                            "accn": "0000000042-25-000001",
                            "form": "10-K",
                            "filed": "2025-02-01",
                        }
                    ]
                }
            }
        }
    },
}


def _transport(
    aufgezeichnet: list[httpx.Request] | None = None,
    *,
    facts_status: int = 200,
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if aufgezeichnet is not None:
            aufgezeichnet.append(request)
        if request.url.path.endswith("company_tickers.json"):
            return httpx.Response(200, json=VERZEICHNIS)
        return httpx.Response(facts_status, json=FACTS if facts_status == 200 else {})

    return httpx.MockTransport(handler)


def _provider(transport: httpx.MockTransport, **kwargs: object) -> EdgarFundamentalDataProvider:
    return EdgarFundamentalDataProvider(
        SETTINGS,
        now=lambda: datetime(2026, 8, 24, tzinfo=UTC),
        transport=transport,
        sleep=lambda _: None,
        **kwargs,  # type: ignore[arg-type]
    )


class TestAbruf:
    def test_die_kennzahlen_entstehen_aus_den_einreichungen(self) -> None:
        snapshot = _provider(_transport()).fundamentals(AKTIE)
        assert snapshot.status is FundamentalStatus.COMPLETED
        assert snapshot.metrics[MetricName.REVENUE].value == 1000.0

    def test_der_user_agent_traegt_die_kontaktadresse(self) -> None:
        """Die SEC verlangt sie ausdruecklich und antwortet ohne sie mit 403."""
        anfragen: list[httpx.Request] = []
        _provider(_transport(anfragen)).fundamentals(AKTIE)
        assert anfragen
        for anfrage in anfragen:
            assert "pruefer@example.org" in anfrage.headers["User-Agent"]

    def test_die_cik_wird_mit_fuehrenden_nullen_angefragt(self) -> None:
        anfragen: list[httpx.Request] = []
        _provider(_transport(anfragen)).fundamentals(AKTIE)
        assert any("CIK0000000042.json" in str(anfrage.url) for anfrage in anfragen)

    def test_das_verzeichnis_wird_nur_einmal_geholt(self) -> None:
        """Bei rund 95 Titeln der Watchlist waere es sonst die mit Abstand
        teuerste Anfrage des Laufs."""
        anfragen: list[httpx.Request] = []
        provider = _provider(_transport(anfragen))
        provider.fundamentals(AKTIE)
        provider.fundamentals(AKTIE)
        verzeichnisanfragen = [a for a in anfragen if a.url.path.endswith("company_tickers.json")]
        assert len(verzeichnisanfragen) == 1


class TestFehler:
    def test_ein_unbekanntes_symbol_nennt_den_grund(self) -> None:
        provider = _provider(_transport())
        with pytest.raises(FundamentalDataProviderError, match="Kein SEC-Emittent"):
            provider.fundamentals(Stock(id=uuid4(), symbol="GIBTESNICHT", exchange="NASDAQ"))

    def test_ein_fehlschlag_wird_als_anbieterfehler_gemeldet(self) -> None:
        """Der Application-Layer isoliert ihn je Aktie -- ein Ausfall von
        EDGAR ist ein normaler Betriebszustand, kein Laufabbruch."""
        provider = _provider(_transport(facts_status=503))
        with pytest.raises(FundamentalDataProviderError, match="companyfacts"):
            provider.fundamentals(AKTIE)


class TestKursDurchreichen:
    def test_ohne_kurs_fehlen_die_bewertungskennzahlen(self) -> None:
        snapshot = _provider(_transport()).fundamentals(AKTIE)
        assert snapshot.price_used is None
        assert MetricName.PRICE_SALES_RATIO in snapshot.missing_metrics

    def test_der_adapter_beschafft_selbst_keinen_kurs(self) -> None:
        """CLAUDE.md, zweite gerichtete Kopplung: Er reicht durch, was er
        bekommt, und leitet nichts ab."""
        anfragen: list[httpx.Request] = []
        _provider(_transport(anfragen)).fundamentals(AKTIE)
        assert all("price" not in str(anfrage.url).lower() for anfrage in anfragen)


class TestDrossel:
    def test_sie_wartet_zwischen_zwei_anfragen(self) -> None:
        gewartet: list[float] = []
        drossel = _Drossel(2.0, sleep=gewartet.append)
        drossel.warte()
        drossel.warte()
        assert len(gewartet) == 1
        assert gewartet[0] == pytest.approx(0.5, abs=0.05)

    def test_eine_nichtpositive_rate_ist_ein_fehler(self) -> None:
        with pytest.raises(ValueError, match="positiv"):
            _Drossel(0.0)


class TestEchteEinreichung:
    """Gegenprobe an einem echten, eingefrorenen Ausschnitt.

    Die kuenstlichen Faelle oben pruefen je eine Regel. Dieser prueft, dass
    die Regeln zusammen an einer echten Antwort dasselbe ergeben wie beim
    Lauf gegen die SEC am 2026-08-24 -- ohne Netz und ohne dass jemand die
    Zahlen von Hand nachtraegt.
    """

    def test_der_eingefrorene_ausschnitt_ergibt_dieselben_kennzahlen(self) -> None:
        pfad = Path(__file__).parent / "data" / "companyfacts-ausschnitt.json"
        facts = json.loads(pfad.read_text())

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("company_tickers.json"):
                return httpx.Response(
                    200, json={"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}
                )
            return httpx.Response(200, json=facts)

        provider = _provider(httpx.MockTransport(handler))
        snapshot = provider.fundamentals(
            Stock(id=uuid4(), symbol="AAPL", exchange="NASDAQ"), price=232.14
        )
        assert snapshot.status is FundamentalStatus.COMPLETED
        assert snapshot.metrics[MetricName.REVENUE].value == pytest.approx(416_161_000_000)
        assert snapshot.metrics[MetricName.NET_MARGIN].value == pytest.approx(0.2692, abs=1e-4)
        assert snapshot.metrics[MetricName.SHARE_COUNT_GROWTH].value < 0
