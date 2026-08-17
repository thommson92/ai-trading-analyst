"""Tests des Anthropic-Research-Providers -- Werkzeugzyklus, Zitate,
Fehlerbehandlung.

Kein echtes Netzwerk (Muster Finnhub-Tests): ``httpx.MockTransport``,
injiziert ueber den SDK-eigenen ``http_client``-Parameter.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable

import httpx
import pytest

from ai_trading_analyst.domain.analysis import ResearchProviderError, Stock
from ai_trading_analyst.domain.research import ResearchStatus, SourceLicenseClass
from ai_trading_analyst.infrastructure.anthropic.provider import (
    _SUBMIT_REPORT_TOOL,
    AnthropicResearchPricing,
    AnthropicResearchProvider,
    AnthropicResearchSettings,
    _UsageTotals,
)

AAPL = Stock(id=uuid.uuid4(), symbol="AAPL", exchange="NASDAQ")


def _message(
    content: list[dict[str, object]],
    stop_reason: str = "tool_use",
    input_tokens: int = 10,
) -> dict[str, object]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": input_tokens, "output_tokens": 20},
    }


def _submit_block(**input_overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "COMPLETED",
        "summary": "Zusammenfassung",
        "confidence": 0.6,
    }
    payload.update(input_overrides)
    return {
        "type": "tool_use",
        "id": "tool_1",
        "name": "submit_research_report",
        "input": payload,
    }


def _text_with_citation(
    url: str, title: str = "Titel", cited_text: str = "Ausschnitt"
) -> dict[str, object]:
    return {
        "type": "text",
        "text": "...",
        "citations": [
            {
                "type": "web_search_result_location",
                "url": url,
                "title": title,
                "cited_text": cited_text,
                "encrypted_index": "idx",
            }
        ],
    }


def _text_with_char_location_citation(document_title: str) -> dict[str, object]:
    return {
        "type": "text",
        "text": "...",
        "citations": [
            {
                "type": "char_location",
                "document_index": 0,
                "document_title": document_title,
                "cited_text": "Ausschnitt aus dem Dokument",
                "start_char_index": 0,
                "end_char_index": 10,
            }
        ],
    }


def _web_fetch_result(url: str, title: str) -> dict[str, object]:
    return {
        "type": "web_fetch_tool_result",
        "tool_use_id": "srv_2",
        "content": {
            "type": "web_fetch_result",
            "url": url,
            "content": {
                "type": "document",
                "source": {"type": "text", "media_type": "text/plain", "data": "Inhalt..."},
                "title": title,
            },
            "retrieved_at": "2026-08-16T10:00:00Z",
        },
    }


def _settings(**overrides: object) -> AnthropicResearchSettings:
    defaults: dict[str, object] = {
        "api_key": "test-key",
        "model": "claude-sonnet-5",
        "max_searches": 5,
        "max_fetches": 3,
        "max_fetch_content_tokens": 8000,
        "max_input_tokens_per_symbol": 150_000,
        "fetch_allowed_domains": ("sec.gov",),
        "pricing": AnthropicResearchPricing(
            input_usd_per_million=2.0,
            output_usd_per_million=10.0,
            usd_per_search=0.01,
        ),
    }
    defaults.update(overrides)
    return AnthropicResearchSettings(**defaults)  # type: ignore[arg-type]


def _provider(
    handler: Callable[[httpx.Request], httpx.Response],
) -> AnthropicResearchProvider:
    return AnthropicResearchProvider(
        _settings(), http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def _json_response(body: dict[str, object], status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=body)


class TestErfolgreicherZyklus:
    def test_direkter_abschluss_mit_zitat(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(
                _message([_text_with_citation("https://sec.gov/filing"), _submit_block()])
            )

        report = _provider(handler).research(AAPL)

        assert report.status is ResearchStatus.COMPLETED
        assert report.model == "claude-sonnet-5"
        assert report.summary == "Zusammenfassung"
        assert report.confidence == 0.6
        assert len(report.citations) == 1
        assert report.citations[0].url == "https://sec.gov/filing"
        assert report.citations[0].license_class is SourceLicenseClass.PRIMARY_SOURCE

    def test_unbekannte_domain_wird_als_unknown_eingestuft(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(
                _message([_text_with_citation("https://example.com/news"), _submit_block()])
            )

        report = _provider(handler).research(AAPL)
        assert report.citations[0].license_class is SourceLicenseClass.UNKNOWN

    def test_nachrichtenagentur_wird_von_der_primaerquelle_unterschieden(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(
                _message(
                    [
                        _text_with_citation("https://www.reuters.com/markets/apple", "Agentur"),
                        _text_with_citation("https://sec.gov/filing", "Filing"),
                        _submit_block(),
                    ]
                )
            )

        report = _provider(handler).research(AAPL)
        klassen = [citation.license_class for citation in report.citations]
        assert klassen == [SourceLicenseClass.NEWS_MEDIA, SourceLicenseClass.PRIMARY_SOURCE]

    def test_faktorlisten_werden_unveraendert_uebernommen(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(
                _message(
                    [
                        _submit_block(
                            positive_factors=["Rekordumsatz im letzten Quartal"],
                            negative_factors=["Laufendes Kartellverfahren"],
                            risks=["Zollrisiken"],
                        )
                    ]
                )
            )

        report = _provider(handler).research(AAPL)
        assert report.positive_factors == ("Rekordumsatz im letzten Quartal",)
        assert report.negative_factors == ("Laufendes Kartellverfahren",)
        assert report.risks == ("Zollrisiken",)

    def test_insufficient_data_ohne_erfundene_werte(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(
                _message(
                    [
                        _submit_block(
                            status="INSUFFICIENT_DATA",
                            reason="keine Quellen gefunden",
                            confidence=None,
                        )
                    ]
                )
            )

        report = _provider(handler).research(AAPL)
        assert report.status is ResearchStatus.INSUFFICIENT_DATA
        assert report.reason == "keine Quellen gefunden"
        assert report.confidence is None

    def test_dasselbe_zitat_taucht_nur_einmal_im_bericht_auf(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(
                _message(
                    [
                        _text_with_citation("https://sec.gov/filing"),
                        _text_with_citation("https://sec.gov/filing"),
                        _submit_block(),
                    ]
                )
            )

        report = _provider(handler).research(AAPL)
        assert len(report.citations) == 1


class TestWebFetchZitate:
    def test_char_location_zitat_wird_ueber_den_dokumenttitel_aufgeloest(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(
                _message(
                    [
                        _web_fetch_result("https://sec.gov/doc.htm", "Ein Dokument"),
                        _text_with_char_location_citation("Ein Dokument"),
                        _submit_block(),
                    ]
                )
            )

        report = _provider(handler).research(AAPL)
        assert len(report.citations) == 1
        assert report.citations[0].url == "https://sec.gov/doc.htm"
        assert report.citations[0].license_class is SourceLicenseClass.PRIMARY_SOURCE

    def test_unaufloesbares_zitat_wird_ausgelassen_statt_erfunden(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(
                _message(
                    [_text_with_char_location_citation("Unbekanntes Dokument"), _submit_block()]
                )
            )

        report = _provider(handler).research(AAPL)
        assert report.citations == ()


class TestPauseTurn:
    def test_pausierte_antwort_wird_unveraendert_zurueckgeschickt_und_fortgesetzt(self) -> None:
        calls: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            calls.append(body)
            if len(calls) == 1:
                return _json_response(_message([], stop_reason="pause_turn"))
            return _json_response(_message([_submit_block()]))

        report = _provider(handler).research(AAPL)

        assert report.status is ResearchStatus.COMPLETED
        assert len(calls) == 2
        second_request_messages = calls[1]["messages"]
        assert isinstance(second_request_messages, list)
        assert len(second_request_messages) == 2
        assert second_request_messages[1]["role"] == "assistant"

    def test_zu_viele_pausierte_runden_werden_abgebrochen(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(_message([], stop_reason="pause_turn"))

        with pytest.raises(ResearchProviderError, match="pausierte Runden"):
            _provider(handler).research(AAPL)


class TestFehlerfaelle:
    def test_http_fehler_wird_zu_research_provider_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401,
                json={
                    "type": "error",
                    "error": {"type": "authentication_error", "message": "invalid x-api-key"},
                },
            )

        with pytest.raises(ResearchProviderError, match="AAPL"):
            _provider(handler).research(AAPL)

    def test_ohne_abschliessenden_tool_aufruf_wird_ein_fehler_geworfen(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(
                _message([{"type": "text", "text": "fertig"}], stop_reason="end_turn")
            )

        with pytest.raises(ResearchProviderError, match="submit_research_report"):
            _provider(handler).research(AAPL)

    def test_unbekannter_status_wert_wird_abgelehnt(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(_message([_submit_block(status="MAYBE")]))

        with pytest.raises(ResearchProviderError, match="status"):
            _provider(handler).research(AAPL)

    def test_confidence_ausserhalb_des_gueltigen_bereichs(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(_message([_submit_block(confidence=1.5)]))

        with pytest.raises(ResearchProviderError, match="confidence"):
            _provider(handler).research(AAPL)

    def test_unerwartete_antwortform_wird_nicht_als_rohe_exception_durchgereicht(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(_message([_submit_block()]))

        provider = _provider(handler)

        def _boom(content: object, fetched_documents: object) -> dict[str, object] | None:
            raise AttributeError("'NoneType' object has no attribute 'title'")

        provider._scan_turn = _boom  # type: ignore[method-assign]

        with pytest.raises(ResearchProviderError, match="AAPL"):
            provider.research(AAPL)


class TestFalschTypisierteWerkzeugantwort:
    """Regression zum Vorfall vom 2026-08-17: Das Modell hat die Faktorlisten
    in seiner internen XML-Werkzeugsyntax geschrieben, die API hat den Wert als
    einfachen String durchgereicht, und ``tuple(...)`` hat ihn klaglos in
    Einzelzeichen zerlegt -- der Bericht hatte einen Eintrag je Buchstabe."""

    VORFALLWERT = '\n<parameter name="item">Drei aufeinanderfolgende Rekordquartale'

    def test_string_statt_liste_wird_abgelehnt_statt_in_zeichen_zerlegt(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(_message([_submit_block(positive_factors=self.VORFALLWERT)]))

        with pytest.raises(ResearchProviderError, match="positive_factors"):
            _provider(handler).research(AAPL)

    def test_liste_mit_nicht_text_eintrag_wird_abgelehnt(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(_message([_submit_block(risks=["Zollrisiko", {"a": 1}])]))

        with pytest.raises(ResearchProviderError, match="risks"):
            _provider(handler).research(AAPL)

    def test_summary_als_liste_wird_abgelehnt(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(_message([_submit_block(summary=["a", "b"])]))

        with pytest.raises(ResearchProviderError, match="summary"):
            _provider(handler).research(AAPL)

    def test_confidence_als_text_wird_abgelehnt(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(_message([_submit_block(confidence="hoch")]))

        with pytest.raises(ResearchProviderError, match="confidence"):
            _provider(handler).research(AAPL)

    def test_werkzeugschema_erzwingt_die_form_serverseitig(self) -> None:
        """Zweite Verteidigungslinie ist der Adapter -- die erste ist das
        Schema selbst. Ohne ``strict`` waere die Validierung oben nur
        Symptombehandlung."""
        gesendete_werkzeuge: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            gesendete_werkzeuge.extend(body["tools"])
            return _json_response(_message([_submit_block()]))

        _provider(handler).research(AAPL)

        submit = next(
            tool for tool in gesendete_werkzeuge if tool["name"] == "submit_research_report"
        )
        assert submit["strict"] is True
        schema = submit["input_schema"]
        assert isinstance(schema, dict)
        assert schema["additionalProperties"] is False

    def test_schema_verwendet_nur_den_strict_teilmengen_wortschatz(self) -> None:
        """Der strict-Subset lehnt einige JSON-Schema-Schluesselwoerter mit
        einem 400 ab -- ``minimum``/``maximum`` haben genau das ausgeloest.
        Wertebereiche gehoeren in die Beschreibung, durchgesetzt werden sie
        im Adapter."""
        nicht_unterstuetzt = {"minimum", "maximum", "minLength", "maxLength", "maxItems", "pattern"}
        schema = _SUBMIT_REPORT_TOOL["input_schema"]
        assert isinstance(schema, dict)
        for name, definition in schema["properties"].items():
            assert not nicht_unterstuetzt & set(definition), (
                f"'{name}' verwendet ein im strict-Subset unzulaessiges Schluesselwort"
            )


class TestWerkzeugbudget:
    """Der Lauf vom 2026-08-17 hat 256.000 Eingabe-Token und ~0,62 USD
    gekostet, ohne einen Bericht zu liefern (ADR 0022, "Kostenkontrolle")."""

    def _gesendete_werkzeuge(
        self, provider: AnthropicResearchProvider, aufzeichnung: list[dict[str, object]]
    ) -> dict[str, dict[str, object]]:
        provider.research(AAPL)
        return {str(tool["name"]): tool for tool in aufzeichnung}

    def test_abruf_ist_gedeckelt_und_auf_die_allowlist_beschraenkt(self) -> None:
        aufzeichnung: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            aufzeichnung.extend(json.loads(request.content)["tools"])
            return _json_response(_message([_submit_block()]))

        werkzeuge = self._gesendete_werkzeuge(_provider(handler), aufzeichnung)

        web_fetch = werkzeuge["web_fetch"]
        assert web_fetch["max_content_tokens"] == 8000
        assert web_fetch["allowed_domains"] == ["sec.gov"]

    def test_die_suche_laeuft_bewusst_ohne_allowlist(self) -> None:
        """Eine Allowlist auf der Suche laesst kaum Treffer uebrig, das Modell
        verbrennt sein Kontingent, und web_fetch erreicht danach nichts mehr --
        genau daran ist der Lauf gescheitert."""
        aufzeichnung: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            aufzeichnung.extend(json.loads(request.content)["tools"])
            return _json_response(_message([_submit_block()]))

        werkzeuge = self._gesendete_werkzeuge(_provider(handler), aufzeichnung)

        assert "allowed_domains" not in werkzeuge["web_search"]

    def test_erschoepftes_token_budget_bricht_die_fortsetzung_ab(self) -> None:
        aufrufe: list[None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            aufrufe.append(None)
            return _json_response(
                _message([], stop_reason="pause_turn", input_tokens=90_000),
            )

        provider = AnthropicResearchProvider(
            _settings(max_input_tokens_per_symbol=150_000),
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

        with pytest.raises(ResearchProviderError, match="Token-Budget"):
            provider.research(AAPL)

        # Erste Anfrage 90k, zweite 180k -- danach wird nicht mehr fortgesetzt.
        assert len(aufrufe) == 2

    def test_kostenschaetzung_rechnet_token_und_suchen_zusammen(self) -> None:
        totals = _UsageTotals(
            pricing=AnthropicResearchPricing(
                input_usd_per_million=2.0,
                output_usd_per_million=10.0,
                usd_per_search=0.01,
            ),
            input_tokens=250_000,
            output_tokens=6_000,
            web_searches=5,
        )

        # 0,50 USD Eingabe + 0,06 USD Ausgabe + 0,05 USD Suchen
        assert totals.estimated_usd() == pytest.approx(0.61)


class TestWerkzeugfehler:
    """Werkzeugfehler kommen als 200er-Antwort mit Fehlerblock an. Wurden sie
    verschluckt, blieb fuer die Diagnose nur die Selbstbeschreibung des
    Modells."""

    def test_suchfehler_wird_geloggt_und_bricht_den_lauf_nicht_ab(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(
                _message(
                    [
                        {
                            "type": "web_search_tool_result",
                            "tool_use_id": "srv_1",
                            "content": {
                                "type": "web_search_tool_result_error",
                                "error_code": "max_uses_exceeded",
                            },
                        },
                        _submit_block(),
                    ]
                )
            )

        with caplog.at_level("WARNING"):
            report = _provider(handler).research(AAPL)

        assert report.status is ResearchStatus.COMPLETED
        assert "max_uses_exceeded" in caplog.text

    def test_abruffehler_wird_geloggt(self, caplog: pytest.LogCaptureFixture) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(
                _message(
                    [
                        {
                            "type": "web_fetch_tool_result",
                            "tool_use_id": "srv_2",
                            "content": {
                                "type": "web_fetch_tool_result_error",
                                "error_code": "url_not_in_prior_context",
                            },
                        },
                        _submit_block(),
                    ]
                )
            )

        with caplog.at_level("WARNING"):
            report = _provider(handler).research(AAPL)

        assert report.status is ResearchStatus.COMPLETED
        assert "url_not_in_prior_context" in caplog.text


class TestAbgeschnitteneAntwort:
    def test_max_tokens_erzeugt_keinen_teilbericht(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(
                _message([_submit_block(positive_factors=["Rekord"])], stop_reason="max_tokens")
            )

        with pytest.raises(ResearchProviderError, match="max_tokens"):
            _provider(handler).research(AAPL)


class TestUnbekannteZitatTypen:
    def test_unbekannter_zitat_typ_wird_uebersprungen_statt_zu_crashen(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(
                _message(
                    [
                        {
                            "type": "text",
                            "text": "...",
                            "citations": [
                                {
                                    "type": "page_location",
                                    "document_index": 0,
                                    "document_title": "Ein PDF-Filing",
                                    "cited_text": "Ausschnitt",
                                    "start_page_number": 1,
                                    "end_page_number": 2,
                                }
                            ],
                        },
                        _submit_block(),
                    ]
                )
            )

        report = _provider(handler).research(AAPL)
        assert report.status is ResearchStatus.COMPLETED
        assert report.citations == ()


class TestAusweichmodell:
    def test_bei_anbieterfehler_wird_das_ausweichmodell_versucht(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            calls.append(str(body["model"]))
            if len(calls) == 1:
                return httpx.Response(
                    401,
                    json={
                        "type": "error",
                        "error": {"type": "authentication_error", "message": "invalid x-api-key"},
                    },
                )
            return _json_response(_message([_submit_block()]))

        provider = AnthropicResearchProvider(
            _settings(fallback_model="claude-haiku-4-5-20251001"),
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

        report = provider.research(AAPL)

        assert report.status is ResearchStatus.COMPLETED
        assert report.model == "claude-haiku-4-5-20251001"
        assert calls == ["claude-sonnet-5", "claude-haiku-4-5-20251001"]

    def test_ohne_konfiguriertes_ausweichmodell_wird_direkt_ein_fehler_geworfen(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401,
                json={
                    "type": "error",
                    "error": {"type": "authentication_error", "message": "invalid x-api-key"},
                },
            )

        with pytest.raises(ResearchProviderError, match="AAPL"):
            _provider(handler).research(AAPL)

    def test_scheitert_auch_das_ausweichmodell_wird_ein_fehler_geworfen(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401,
                json={
                    "type": "error",
                    "error": {"type": "authentication_error", "message": "invalid x-api-key"},
                },
            )

        provider = AnthropicResearchProvider(
            _settings(fallback_model="claude-haiku-4-5-20251001"),
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        with pytest.raises(ResearchProviderError, match="Ausweichmodell"):
            provider.research(AAPL)


class TestDokumentTitelKollision:
    def test_erstes_dokument_gewinnt_bei_gleichem_titel(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(
                _message(
                    [
                        _web_fetch_result("https://sec.gov/erstes-filing", "10-Q"),
                        _web_fetch_result("https://sec.gov/zweites-filing", "10-Q"),
                        _text_with_char_location_citation("10-Q"),
                        _submit_block(),
                    ]
                )
            )

        report = _provider(handler).research(AAPL)
        assert len(report.citations) == 1
        assert report.citations[0].url == "https://sec.gov/erstes-filing"
