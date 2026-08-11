from __future__ import annotations

from typing import Any

_SENSITIVE_KEY_MARKERS = ("account", "accountid", "login", "username", "password", "token")


def redact_account_id(account_id: str) -> str:
    if len(account_id) <= 4:
        return "*" * len(account_id)
    return f"{account_id[0]}{'*' * (len(account_id) - 3)}{account_id[-2:]}"


def redact_value(key: str, value: Any) -> Any:
    if isinstance(value, str) and any(marker in key.lower() for marker in _SENSITIVE_KEY_MARKERS):
        return redact_account_id(value)
    return value


def redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            redacted[key] = redact_mapping(value)
        elif isinstance(value, list):
            redacted[key] = [
                redact_mapping(item)
                if isinstance(item, dict)
                else redact_value(key, item)
                for item in value
            ]
        else:
            redacted[key] = redact_value(key, value)
    return redacted
