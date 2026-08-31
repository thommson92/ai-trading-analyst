"""Der EDGAR-Abruf (ADR 0032, Entscheidung 7).

Ohne Netz: ``httpx.MockTransport`` beantwortet die Anfragen, wie es die
uebrigen Adapter-Tests auch tun.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from ai_trading_analyst.domain.analysis import FundamentalDataProviderError, Stock
from ai_trading_analyst.domain.fundamentals import (
    FundamentalStatus,
    MetricBasis,
    MetricName,
)
from ai_trading_analyst.infrastructure.edgar import (
    EdgarConnectionSettings,
    EdgarFundamentalDataProvider,
)

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

    def test_klassenaktien_werden_in_die_schreibweise_der_sec_uebersetzt(self) -> None:
        """Die Watchlist fuehrt Berkshire als ``BRK.B``, IBKR als ``BRK B``,
        die SEC als ``BRK-B``. Ohne Uebersetzung zaehlte eine Messung der
        Tag-Abdeckung einen Fehlschlag, der mit Tags nichts zu tun hat."""
        verzeichnis = {"0": {"cik_str": 42, "ticker": "BRK-B", "title": "Berkshire"}}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("company_tickers.json"):
                return httpx.Response(200, json=verzeichnis)
            return httpx.Response(200, json=FACTS)

        for geschrieben in ("BRK.B", "BRK B", "BRK-B"):
            anbieter = _provider(httpx.MockTransport(handler))
            snapshot = anbieter.fundamentals(
                Stock(id=uuid4(), symbol=geschrieben, exchange="NYSE")
            )
            assert snapshot.status is FundamentalStatus.COMPLETED

    def test_ein_unbekanntes_symbol_wird_nicht_umgebogen(self) -> None:
        """Nur die beiden Trennzeichen, keine Aehnlichkeitssuche."""
        provider = _provider(_transport())
        with pytest.raises(FundamentalDataProviderError):
            provider.fundamentals(Stock(id=uuid4(), symbol="TES", exchange="NASDAQ"))

    def test_ein_fehlschlag_wird_als_anbieterfehler_gemeldet(self) -> None:
        """Der Application-Layer isoliert ihn je Aktie -- ein Ausfall von
        EDGAR ist ein normaler Betriebszustand, kein Laufabbruch."""
        provider = _provider(_transport(facts_status=503))
        with pytest.raises(FundamentalDataProviderError, match="companyfacts"):
            provider.fundamentals(AKTIE)


class TestAntwortgroesse:
    def test_eine_unplausibel_grosse_antwort_wird_abgelehnt(self) -> None:
        """companyfacts ist je Aktie einige Megabyte gross (Honeywell 4,6 MB
        gemessen). Eine Antwort weit darueber deutet auf etwas anderes hin
        als auf Fundamentaldaten."""
        from ai_trading_analyst.infrastructure.edgar import provider as modul

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("company_tickers.json"):
                return httpx.Response(200, json=VERZEICHNIS)
            return httpx.Response(200, content=b'{"x": "' + b"y" * 2048 + b'"}')

        anbieter = _provider(httpx.MockTransport(handler))
        with pytest.raises(FundamentalDataProviderError, match="unplausibel"):
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(modul, "MAX_ANTWORT_BYTES", 1024)
                anbieter.fundamentals(AKTIE)

    def test_abgebrochen_wird_beim_lesen_nicht_danach(self) -> None:
        """Eine Grenze, die erst den fertig gepufferten Rumpf misst, kommt zu
        spaet -- der Speicher ist dann schon belegt, und genau davor soll sie
        schuetzen. Geprueft wird deshalb, dass der Rest gar nicht mehr vom
        Netz gelesen wird."""
        from ai_trading_analyst.infrastructure.edgar import provider as modul

        gelesen: list[int] = []

        def stuecke() -> Iterator[bytes]:
            for nummer in range(100):
                gelesen.append(nummer)
                yield b"y" * 512

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("company_tickers.json"):
                return httpx.Response(200, json=VERZEICHNIS)
            return httpx.Response(200, content=stuecke())

        anbieter = _provider(httpx.MockTransport(handler))
        with pytest.raises(FundamentalDataProviderError, match="unplausibel"):
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(modul, "MAX_ANTWORT_BYTES", 1024)
                anbieter.fundamentals(AKTIE)
        assert len(gelesen) < 100

    def test_einer_umleitung_wird_nicht_gefolgt(self) -> None:
        """Bei einer festen, konfigurierten Adresse ist eine Umleitung kein
        normaler Zustand -- ihr zu folgen hiesse, eine fremde Antwort als die
        der SEC zu verarbeiten."""
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("company_tickers.json"):
                return httpx.Response(301, headers={"Location": "https://woanders.example/x"})
            return httpx.Response(200, json=FACTS)

        with pytest.raises(FundamentalDataProviderError):
            _provider(httpx.MockTransport(handler)).fundamentals(AKTIE)


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

        # Niveauzahlen auf den letzten zwoelf Monaten (ADR 0033): Der
        # Jahresabschluss per 2025-09-27 nennt 416,2 Mrd, die zwoelf Monate
        # bis 2026-06-27 nennen 466,8 Mrd.
        umsatz = snapshot.metrics[MetricName.REVENUE]
        assert umsatz.value == pytest.approx(466_823_000_000)
        assert umsatz.basis is MetricBasis.TRAILING_TWELVE_MONTHS
        assert umsatz.period_end == date(2026, 6, 27)
        assert snapshot.metrics[MetricName.NET_MARGIN].value == pytest.approx(0.2762, abs=1e-4)

        # ... die Wachstumsraten dagegen auf Geschaeftsjahren
        wachstum = snapshot.metrics[MetricName.REVENUE_GROWTH]
        assert wachstum.basis is MetricBasis.FISCAL_YEAR
        assert wachstum.period_end == date(2025, 9, 27)
        assert snapshot.metrics[MetricName.SHARE_COUNT_GROWTH].value < 0

        # Das KGV faellt dadurch deutlich niedriger aus als auf Jahresbasis
        # (26,3 statt 30,3) -- die Aktie sah 15 Prozent teurer aus, als sie ist.
        assert snapshot.metrics[MetricName.PRICE_EARNINGS_RATIO].value == pytest.approx(
            26.28, abs=0.05
        )

    def test_ohne_quartalsmeldungen_faellt_alles_auf_jahreswerte_zurueck(self) -> None:
        """ADR 0033, Entscheidung 5. Geprueft an demselben echten Ausschnitt,
        nur ohne die 10-Q -- so laesst sich der Rueckfall nicht mit einem
        kuenstlichen Sonderfall verwechseln."""
        pfad = Path(__file__).parent / "data" / "companyfacts-ausschnitt.json"
        facts = json.loads(pfad.read_text())
        for inhalt in facts["facts"]["us-gaap"].values():
            for einheit, fakten in inhalt["units"].items():
                inhalt["units"][einheit] = [e for e in fakten if e.get("form") != "10-Q"]

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("company_tickers.json"):
                return httpx.Response(
                    200, json={"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}
                )
            return httpx.Response(200, json=facts)

        snapshot = _provider(httpx.MockTransport(handler)).fundamentals(
            Stock(id=uuid4(), symbol="AAPL", exchange="NASDAQ")
        )
        umsatz = snapshot.metrics[MetricName.REVENUE]
        assert umsatz.value == pytest.approx(416_161_000_000)
        assert umsatz.basis is MetricBasis.FISCAL_YEAR
        assert umsatz.period_end == date(2025, 9, 27)
