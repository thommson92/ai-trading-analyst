"""Tests des Finnhub-Adapters fuer die Analystenempfehlungen (ADR 0043).

Wie beim Earnings-Adapter: Alles ohne echtes Netz laeuft ueber
``httpx.MockTransport`` -- die von ``httpx`` selbst vorgesehene
Teststrategie, kein Mock der Bibliothek. Der echte Netzwerkfehler wird gegen
einen tatsaechlich unbesetzten lokalen Port geprueft.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from ai_trading_analyst.domain.analysis import Stock
from ai_trading_analyst.domain.analysts import AnalystRecommendationStatus
from ai_trading_analyst.infrastructure.finnhub.recommendations import (
    FinnhubAnalystRecommendationsProvider,
    FinnhubAnalystRecommendationsProviderError,
    FinnhubRecommendationSettings,
)

SETTINGS = FinnhubRecommendationSettings(
    base_url="https://finnhub.io/api/v1",
    api_key="test-key",
    request_timeout_seconds=1.0,
    months=4,
    max_requests_per_second=1000.0,
)
JETZT = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
AAPL = Stock(id=uuid.uuid4(), symbol="AAPL", exchange="NASDAQ")


def _eintrag(period: str, **votes: int) -> dict[str, object]:
    """Ein Antworteintrag mit Finnhubs Feldnamen.

    Die Voreinstellungen sind bewusst **nicht** null: Ein Test, der eine
    Zuordnung prueft, kann eine Verwechslung zweier Nullen nicht bemerken.
    """
    grund: dict[str, object] = {
        "period": period,
        "strongBuy": 1,
        "buy": 2,
        "hold": 3,
        "sell": 4,
        "strongSell": 5,
        "symbol": "AAPL",
    }
    grund.update(votes)
    return grund


def _provider(transport: httpx.MockTransport) -> FinnhubAnalystRecommendationsProvider:
    return FinnhubAnalystRecommendationsProvider(SETTINGS, now=lambda: JETZT, transport=transport)


def _json_transport(payload: object, status_code: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    return httpx.MockTransport(handler)


class TestErfolgreicheAntwort:
    def test_die_fuenf_votenklassen_landen_an_der_richtigen_stelle(self) -> None:
        """Jede Klasse mit einem anderen Wert -- eine Vertauschung von
        ``buy`` und ``hold`` faellt sonst nicht auf."""
        provider = _provider(_json_transport([_eintrag("2026-08-01")]))

        ergebnis = provider.recommendations(AAPL)

        assert ergebnis.status is AnalystRecommendationStatus.COMPLETED
        (stand,) = ergebnis.periods
        assert stand.period == date(2026, 8, 1)
        assert stand.strong_buy == 1
        assert stand.buy == 2
        assert stand.hold == 3
        assert stand.sell == 4
        assert stand.strong_sell == 5
        assert stand.total == 15

    def test_quelle_und_abrufzeitpunkt_stehen_am_ergebnis(self) -> None:
        """Doc 10: Aussagen ueber Analystenmeinungen verweisen auf eine
        gespeicherte Quelle mit Abrufzeitpunkt."""
        ergebnis = _provider(_json_transport([_eintrag("2026-08-01")])).recommendations(AAPL)

        assert ergebnis.source == "finnhub"
        assert ergebnis.retrieved_at == JETZT
        assert ergebnis.analysis_version == "analysts-v1"

    def test_der_neueste_stand_kommt_zuerst(self) -> None:
        """Die Reihenfolge ist Teil der Zusage, nicht Darstellung -- und der
        Anbieter wird nicht darum gebeten, sie einzuhalten."""
        transport = _json_transport(
            [_eintrag("2026-06-01"), _eintrag("2026-08-01"), _eintrag("2026-07-01")]
        )

        ergebnis = _provider(transport).recommendations(AAPL)

        assert [stand.period for stand in ergebnis.periods] == [
            date(2026, 8, 1),
            date(2026, 7, 1),
            date(2026, 6, 1),
        ]
        assert ergebnis.latest is not None
        assert ergebnis.latest.period == date(2026, 8, 1)

    def test_mehr_monate_als_konfiguriert_werden_gekuerzt(self) -> None:
        """Der Endpunkt kennt keinen Zeitraumparameter -- begrenzt wird hier."""
        transport = _json_transport(
            [_eintrag(f"2026-{monat:02d}-01") for monat in range(1, 9)]
        )

        ergebnis = _provider(transport).recommendations(AAPL)

        assert len(ergebnis.periods) == 4
        # Gekuerzt wird am **alten** Ende, nicht am neuen.
        assert ergebnis.periods[0].period == date(2026, 8, 1)
        assert ergebnis.periods[-1].period == date(2026, 5, 1)


class TestFehlendeAbdeckung:
    def test_eine_leere_liste_ist_unbekannt_und_nicht_keine_meinung(self) -> None:
        """ADR 0043: Ein Anbieter ohne Abdeckung hat nichts gesagt."""
        ergebnis = _provider(_json_transport([])).recommendations(AAPL)

        assert ergebnis.status is AnalystRecommendationStatus.UNKNOWN
        assert ergebnis.reason == "no_coverage"
        assert ergebnis.periods == ()
        assert ergebnis.latest is None

    def test_auch_ohne_abdeckung_steht_die_quelle_am_ergebnis(self) -> None:
        """Sonst liesse sich spaeter nicht sagen, wer nichts wusste."""
        ergebnis = _provider(_json_transport([])).recommendations(AAPL)
        assert ergebnis.source == "finnhub"
        assert ergebnis.retrieved_at == JETZT


class TestUnbrauchbareAntwort:
    def test_ein_http_fehler_wird_zur_vertragsausnahme(self) -> None:
        provider = _provider(_json_transport({"error": "no"}, status_code=500))
        with pytest.raises(FinnhubAnalystRecommendationsProviderError):
            provider.recommendations(AAPL)

    def test_ein_objekt_statt_einer_liste_bricht_ab(self) -> None:
        provider = _provider(_json_transport({"recommendations": []}))
        with pytest.raises(FinnhubAnalystRecommendationsProviderError, match="Liste"):
            provider.recommendations(AAPL)

    def test_unplausibel_viele_monatsstaende_brechen_ab(self) -> None:
        """Muster ``_SUSPICIOUS_ENTRY_COUNT``: Lieber abbrechen als einer
        Antwort vertrauen, deren Format sich offenbar geaendert hat."""
        transport = _json_transport([_eintrag("2026-08-01")] * 121)
        with pytest.raises(FinnhubAnalystRecommendationsProviderError, match="unplausibel"):
            _provider(transport).recommendations(AAPL)

    def test_ein_fehlendes_feld_bricht_ab(self) -> None:
        unvollstaendig = {"period": "2026-08-01", "strongBuy": 1, "buy": 2, "hold": 3}
        with pytest.raises(FinnhubAnalystRecommendationsProviderError):
            _provider(_json_transport([unvollstaendig])).recommendations(AAPL)

    @pytest.mark.parametrize("wert", [3.7, "5", True, None, -1])
    def test_eine_votenzahl_die_keine_ganze_nichtnegative_zahl_ist_bricht_ab(
        self, wert: object
    ) -> None:
        """``int(wert)`` haette ``True`` als eine Stimme und ``3.7`` als drei
        durchgelassen -- eine erfundene Zahl an einer Stelle, die zaehlt."""
        with pytest.raises(FinnhubAnalystRecommendationsProviderError):
            _provider(_json_transport([_eintrag("2026-08-01", buy=wert)])).recommendations(  # type: ignore[arg-type]
                AAPL
            )

    def test_ein_unlesbares_datum_bricht_ab(self) -> None:
        with pytest.raises(FinnhubAnalystRecommendationsProviderError):
            _provider(_json_transport([_eintrag("August 2026")])).recommendations(AAPL)


class TestEchterNetzwerkfehler:
    def test_ein_unbesetzter_port_ergibt_die_vertragsausnahme(self) -> None:
        """Kein Mock: Was ``httpx`` bei einer verweigerten Verbindung wirft,
        ist eine Eigenschaft der Bibliothek und keine eigene Annahme."""
        provider = FinnhubAnalystRecommendationsProvider(
            FinnhubRecommendationSettings(
                base_url="http://127.0.0.1:1",
                api_key="test-key",
                request_timeout_seconds=1.0,
                months=4,
                max_requests_per_second=1000.0,
            ),
            now=lambda: JETZT,
        )
        with pytest.raises(FinnhubAnalystRecommendationsProviderError):
            provider.recommendations(AAPL)


class TestAnfrage:
    def test_symbol_geht_mit_und_der_schluessel_im_header(self) -> None:
        """Der Schluessel steht im Header (A2-M10) und damit nicht in der
        URL, die ``httpx`` in seine Fehlertexte schreibt."""
        gesehen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            gesehen.append(request)
            return httpx.Response(200, json=[])

        _provider(httpx.MockTransport(handler)).recommendations(AAPL)

        (anfrage,) = gesehen
        assert anfrage.url.path.endswith("/stock/recommendation")
        assert anfrage.url.params["symbol"] == "AAPL"
        assert anfrage.headers["X-Finnhub-Token"] == "test-key"
        assert "test-key" not in str(anfrage.url)


class TestSchluesselLandetNichtImFehlertext:
    """Der Schluessel steht seit A2-M10 im Header und damit nicht mehr in der
    URL, die ``httpx`` in seine Ausnahmetexte schreibt.

    Die Schwaerzung bleibt trotzdem geprueft: Sie ist die zweite Reihe. Wer
    kuenftig einen Parameter ergaenzt, soll nicht darauf angewiesen sein,
    diesen Wechsel zu kennen.
    """

    def test_ein_http_fehler_verraet_den_schluessel_nicht(self) -> None:
        provider = _provider(_json_transport({"error": "boom"}, status_code=500))

        with pytest.raises(FinnhubAnalystRecommendationsProviderError) as fehler:
            provider.recommendations(AAPL)

        assert "test-key" not in str(fehler.value)
        # Die Meldung bleibt brauchbar: Symbol und Statuscode stehen drin.
        assert "AAPL" in str(fehler.value)
        assert "500" in str(fehler.value)

    def test_auch_die_verkettete_ursache_wird_nicht_ausgegeben(self) -> None:
        """``raise ... from error`` haengt die Originalausnahme an. Sie
        enthaelt den Schluessel weiterhin -- das ist hingenommen, weil ein
        Traceback nur im Fehlerfall und nur lokal entsteht. Geprueft wird,
        dass die **Meldung**, die der Aufrufer ausgibt, sauber ist."""
        provider = _provider(_json_transport({"error": "boom"}, status_code=403))

        with pytest.raises(FinnhubAnalystRecommendationsProviderError) as fehler:
            provider.recommendations(AAPL)

        assert "test-key" not in fehler.value.args[0]


class TestDrosselung:
    """Finnhubs Gratis-Stufe deckelt bei 60 Anfragen je Minute.

    Der Messlauf ueber die Watchliste vom 2026-08-31 lief mit rund einer
    Anfrage je Sekunde und verlor vier von 192 Symbolen an ``429`` -- der
    Adapter hielt bis dahin keinen Abstand.
    """

    def test_zwischen_zwei_abrufen_wird_gewartet(self) -> None:
        gewartet: list[float] = []
        provider = FinnhubAnalystRecommendationsProvider(
            FinnhubRecommendationSettings(
                base_url="https://finnhub.io/api/v1",
                api_key="test-key",
                request_timeout_seconds=1.0,
                months=4,
                max_requests_per_second=2.0,
            ),
            now=lambda: JETZT,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])),
            sleep=gewartet.append,
        )

        provider.recommendations(AAPL)
        provider.recommendations(AAPL)

        assert len(gewartet) == 1
        assert gewartet[0] == pytest.approx(0.5, abs=0.05)

    def test_der_erste_abruf_wartet_nicht(self) -> None:
        """Eine Einzelprobe soll sofort antworten."""
        gewartet: list[float] = []
        provider = FinnhubAnalystRecommendationsProvider(
            SETTINGS,
            now=lambda: JETZT,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])),
            sleep=gewartet.append,
        )

        provider.recommendations(AAPL)

        assert gewartet == []


class TestEingefroreneAntwort:
    """Gegenprobe an der echten Antwort vom 2026-09-01 (A2-M7).

    Die Faelle oben schreiben ihre Antwort selbst hin und koennen deshalb
    keine Umbenennung auf Anbieterseite bemerken. Herkunft und
    Neuaufzeichnung stehen in ``data/HERKUNFT.md``.
    """

    def _payload(self) -> list[dict[str, object]]:
        pfad = Path(__file__).parent / "data" / "recommendation-AAPL.json"
        eintraege: list[dict[str, object]] = json.loads(pfad.read_text(encoding="utf-8"))
        return eintraege

    def test_die_echte_antwort_ergibt_vier_monatsstaende(self) -> None:
        ergebnis = _provider(_json_transport(self._payload())).recommendations(AAPL)

        assert ergebnis.status is AnalystRecommendationStatus.COMPLETED
        assert len(ergebnis.periods) == 4

    def test_der_neueste_stand_steht_vorn(self) -> None:
        """Die Antwort kommt bereits absteigend; verlassen wird sich darauf
        nicht -- die Reihenfolge ist eine Zusage des Wertobjekts, nicht des
        Anbieters."""
        ergebnis = _provider(_json_transport(self._payload())).recommendations(AAPL)

        assert [stand.period for stand in ergebnis.periods] == sorted(
            (stand.period for stand in ergebnis.periods), reverse=True
        )
        neuester = ergebnis.latest
        assert neuester is not None
        assert neuester.period == date(2026, 8, 1)

    def test_die_fuenf_klassen_kommen_unveraendert_an(self) -> None:
        """54 Voten in fuenf Klassen. Eine Vertauschung von ``buy`` und
        ``hold`` faellt an diesen Zahlen auf -- sie sind alle verschieden."""
        neuester = _provider(_json_transport(self._payload())).recommendations(AAPL).latest

        assert neuester is not None
        assert (neuester.strong_buy, neuester.buy, neuester.hold) == (13, 24, 14)
        assert (neuester.sell, neuester.strong_sell) == (3, 0)
        assert neuester.total == 54

    def test_eine_echte_null_bleibt_eine_null(self) -> None:
        """``strongSell`` ist in allen vier Staenden 0 -- und zwar
        **gemeldet**, nicht fehlend. Wuerde der Adapter fehlende Felder
        stillschweigend auf 0 setzen, waeren die beiden Faelle in der
        Auswertung nicht mehr zu trennen (CLAUDE.md: was fehlt, bleibt
        fehlend)."""
        ergebnis = _provider(_json_transport(self._payload())).recommendations(AAPL)

        assert all(stand.strong_sell == 0 for stand in ergebnis.periods)
        assert all("strongSell" in eintrag for eintrag in self._payload())
