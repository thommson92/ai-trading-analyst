from ibkrspike.redaction import redact_account_id, redact_mapping


def test_redact_account_id_behaelt_ersten_und_letzte_zwei_zeichen() -> None:
    assert redact_account_id("U1234567") == "U*****67"


def test_redact_account_id_kurzer_wert_wird_vollstaendig_maskiert() -> None:
    assert redact_account_id("U12") == "***"


def test_redact_mapping_maskiert_nur_sensible_schluessel() -> None:
    data = {
        "server_version": 176,
        "managed_accounts": ["U1234567", "U7654321"],
        "nested": {"account_id": "U1234567", "status": "ok"},
    }

    redacted = redact_mapping(data)

    assert redacted["server_version"] == 176
    assert redacted["managed_accounts"] == ["U*****67", "U*****21"]
    assert redacted["nested"] == {"account_id": "U*****67", "status": "ok"}
