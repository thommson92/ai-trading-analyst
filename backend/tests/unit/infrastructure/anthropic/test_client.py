"""Tests des gemeinsamen Clientaufbaus beider Anthropic-Adapter.

Beide hatten dieselbe Luecke: ``max_retries`` dem SDK ueberlassen und
``timeout`` als Skalar gesetzt. Der Lauf vom 2026-08-24 hat sie sichtbar
gemacht -- 921 Sekunden zwischen zwei Protokollzeilen, was auf zwei stille,
trotzdem berechnete Wiederholungen passt.
"""

from __future__ import annotations

import httpx
import pytest

from ai_trading_analyst.infrastructure.anthropic.client import (
    VERBINDUNGSAUFBAU_SEKUNDEN,
    build_client,
)


def _client(**overrides: object) -> object:
    argumente: dict[str, object] = {
        "api_key": "test-key",
        "http_client": None,
        "read_timeout_seconds": 900.0,
        "max_retries": 1,
    }
    argumente.update(overrides)
    return build_client(**argumente)  # type: ignore[arg-type]


def test_der_verbindungsaufbau_wartet_nicht_so_lange_wie_das_lesen() -> None:
    """Der eigentliche Punkt der Aenderung.

    Ein Skalar-Timeout legt denselben Wert auf beides. Wer den Lesetimeout
    gross genug fuer eine echte Recherche waehlt, macht damit unbemerkt auch
    den Verbindungsaufbau minutenlang geduldig -- eine unerreichbare
    Gegenstelle blockiert dann einen der vier Arbeiter.
    """
    timeout = _client().timeout  # type: ignore[attr-defined]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read == 900.0
    assert timeout.connect == VERBINDUNGSAUFBAU_SEKUNDEN
    assert timeout.connect < timeout.read


def test_die_wiederholungszahl_wird_gesetzt_und_nicht_geerbt() -> None:
    """Ohne diese Zusicherung faellt der Wert still auf den SDK-Standard
    zurueck, sobald jemand das Argument entfernt -- und genau das war der
    Ausgangszustand."""
    assert _client(max_retries=0).max_retries == 0  # type: ignore[attr-defined]
    assert _client(max_retries=3).max_retries == 3  # type: ignore[attr-defined]


def test_eine_negative_wiederholungszahl_ist_ein_konfigurationsfehler() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        _client(max_retries=-1)
