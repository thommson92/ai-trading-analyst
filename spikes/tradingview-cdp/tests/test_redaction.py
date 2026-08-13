from __future__ import annotations

from tvcdp.redaction import redact


class TestRedactionNachSchluessel:
    def test_cookie_schluessel_wird_vollstaendig_entfernt(self) -> None:
        result = redact({"cookie": "sessionid=abc123; other=1"})
        assert result == {"cookie": "***REDACTED***"}

    def test_verschachtelter_token_schluessel_wird_entfernt(self) -> None:
        result = redact({"auth": {"api_key": "sk-live-12345", "harmless": "ok"}})
        assert result == {"auth": {"api_key": "***REDACTED***", "harmless": "ok"}}

    def test_schluesselname_ist_case_insensitive(self) -> None:
        result = redact({"Authorization": "geheim", "SESSION_ID": "xyz"})
        assert result == {"Authorization": "***REDACTED***", "SESSION_ID": "***REDACTED***"}

    def test_harmlose_schluessel_bleiben_unveraendert(self) -> None:
        result = redact({"symbol": "AAPL", "exchange": "NASDAQ", "rsi": 61.4})
        assert result == {"symbol": "AAPL", "exchange": "NASDAQ", "rsi": 61.4}


class TestRedactionNachWertmuster:
    def test_bearer_token_in_freitext_wird_entfernt(self) -> None:
        result = redact({"error": "Anfrage schlug fehl: Bearer abc.def-123 ungueltig"})
        assert "abc.def-123" not in result["error"]
        assert "***REDACTED***" in result["error"]

    def test_jwt_aehnliche_zeichenkette_wird_entfernt(self) -> None:
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dGVzdHNpZ25hdHVyZXZhbHVl"
        result = redact({"note": f"token war {jwt}"})
        assert jwt not in result["note"]

    def test_sessionid_in_query_string_wird_entfernt(self) -> None:
        result = redact({"url": "https://example.com/x?sessionid=deadbeef&foo=1"})
        assert "deadbeef" not in result["url"]
        assert "foo=1" in result["url"]


class TestRedactionRekursionUndTypen:
    def test_listen_werden_rekursiv_verarbeitet(self) -> None:
        result = redact([{"token": "geheim"}, {"symbol": "MSFT"}])
        assert result == [{"token": "***REDACTED***"}, {"symbol": "MSFT"}]

    def test_tupel_bleibt_ein_tupel(self) -> None:
        result = redact(("token", "MSFT"))
        assert isinstance(result, tuple)

    def test_primitive_werte_ohne_schluesselkontext_bleiben_unveraendert(self) -> None:
        assert redact(42) == 42
        assert redact(None) is None
        assert redact(True) is True
