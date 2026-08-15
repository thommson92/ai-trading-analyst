"""Gemeinsame Testvorbereitung.

Beide Fixtures isolieren globalen Zustand. Ohne sie haengt das Ergebnis der
Test-Suite davon ab, welche Umgebungsvariablen auf dem ausfuehrenden Rechner
gesetzt sind und in welcher Reihenfolge die Tests laufen -- beides sind
Fehlerquellen, die sich erfahrungsgemaess erst in der CI zeigen.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator

import pytest

from ai_trading_analyst.config import Secrets

_SECRET_ENV_PREFIX = "ATA_"


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Entfernt alle ATA_-Variablen aus der Umgebung -- und die lokale ``.env``.

    Ein Entwickler mit gesetztem ATA_DATABASE_URL wuerde sonst genau die Tests
    scheitern sehen, die das Fehlen eines Geheimnisses pruefen. Seit ``Secrets``
    ersatzweise die ``.env`` im Projektwurzelverzeichnis liest, gilt dasselbe
    fuer diese Datei: Wer sie fuer den eigenen Betrieb angelegt hat, soll
    deshalb keine anderen Testergebnisse bekommen.
    """
    for name in list(os.environ):
        if name.startswith(_SECRET_ENV_PREFIX):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setitem(Secrets.model_config, "env_file", None)


@pytest.fixture(autouse=True)
def restored_root_logger() -> Iterator[None]:
    """Stellt Handler und Level des Root-Loggers nach jedem Test wieder her.

    ``configure_logging`` ersetzt die Handler des Root-Loggers. Ohne
    Wiederherstellung wuerde ein Test, der auf WARNING stellt, die Ausgaben
    aller nachfolgenden Tests unterdruecken.
    """
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        yield
    finally:
        for handler in list(root.handlers):
            if handler not in original_handlers:
                root.removeHandler(handler)
                handler.close()
        for handler in original_handlers:
            if handler not in root.handlers:
                root.addHandler(handler)
        root.setLevel(original_level)
