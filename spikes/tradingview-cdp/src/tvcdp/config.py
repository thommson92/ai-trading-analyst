"""Laufzeitkonfiguration des Spikes -- ausschliesslich ueber Umgebungsvariablen
und CLI-Optionen, keine fest codierten Endpunkte oder Pfade.

Alle Werte sind bewusst konfigurierbar (Nutzervorgabe), damit dieselbe
Codebasis unveraendert auf macOS (Entwicklung/Exploration) und auf dem
Windows-Zielserver (Validierung) laeuft, ohne Windows-Annahmen im Kern.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_ENV_PREFIX = "TVCDP_"

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 9222
_DEFAULT_CONNECT_TIMEOUT_SECONDS = 5.0
_DEFAULT_REQUEST_TIMEOUT_SECONDS = 10.0
_DEFAULT_RESULTS_DIR = Path(__file__).resolve().parents[2] / "results"
_DEFAULT_TARGET_TITLE_PATTERN = "TradingView"
_DEFAULT_MULTI_SYMBOL_SWITCH_TIMEOUT_SECONDS = 8.0


def _env(name: str, default: str) -> str:
    return os.environ.get(f"{_ENV_PREFIX}{name}", default)


@dataclass(frozen=True, slots=True)
class CdpConfig:
    """Verbindungsparameter zum CDP-Endpunkt.

    ``host``/``port`` zeigen auf den Debug-Port der zu untersuchenden
    Electron-/Chromium-Anwendung (TradingView Desktop auf dem Zielsystem,
    oder waehrend der Entwicklung testweise ein beliebiger anderer
    Chromium-Prozess mit aktiviertem Remote-Debugging).
    """

    host: str = _DEFAULT_HOST
    port: int = _DEFAULT_PORT
    connect_timeout_seconds: float = _DEFAULT_CONNECT_TIMEOUT_SECONDS
    request_timeout_seconds: float = _DEFAULT_REQUEST_TIMEOUT_SECONDS

    @property
    def http_base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @classmethod
    def from_env(cls) -> CdpConfig:
        return cls(
            host=_env("HOST", _DEFAULT_HOST),
            port=int(_env("PORT", str(_DEFAULT_PORT))),
            connect_timeout_seconds=float(
                _env("CONNECT_TIMEOUT_SECONDS", str(_DEFAULT_CONNECT_TIMEOUT_SECONDS))
            ),
            request_timeout_seconds=float(
                _env("REQUEST_TIMEOUT_SECONDS", str(_DEFAULT_REQUEST_TIMEOUT_SECONDS))
            ),
        )


@dataclass(frozen=True, slots=True)
class SpikeConfig:
    """Uebergreifende Spike-Konfiguration jenseits der reinen CDP-Verbindung."""

    results_dir: Path = _DEFAULT_RESULTS_DIR
    target_title_pattern: str = _DEFAULT_TARGET_TITLE_PATTERN
    watchlist_probe_names: tuple[str, ...] = ()
    expected_layout: str | None = None
    """Referenzwert fuer C.10 ("ist wirklich das gewuenschte Layout aktiv").
    Ohne diesen Wert kann step_layout.run() nur erkennen, nie verifizieren."""
    multi_symbol_switch_timeout_seconds: float = _DEFAULT_MULTI_SYMBOL_SWITCH_TIMEOUT_SECONDS
    """Maximale Wartezeit, bis ein Symbolwechsel per ``get_symbol_js`` bestaetigt
    ist, bevor Werte gelesen werden (Schritt G). Ein fester Sleep reichte in
    einem 10-Symbol-Testlauf auf dem Windows-Zielserver *nicht* aus -- der
    Chart blieb bei mehreren Wechseln auf einem vorherigen Symbol haengen,
    ohne dass die Studies das als Fehler meldeten (siehe step_multi_symbol.py).
    Deshalb Poll-basiert statt ein fixer Sleep: es wird bis zu dieser Grenze
    wiederholt geprueft, ob der Wechsel wirklich stattgefunden hat."""

    @classmethod
    def from_env(cls) -> SpikeConfig:
        results_dir = Path(_env("RESULTS_DIR", str(_DEFAULT_RESULTS_DIR)))
        watchlist_names = _env("WATCHLIST_PROBE_NAMES", "")
        return cls(
            results_dir=results_dir,
            target_title_pattern=_env("TARGET_TITLE_PATTERN", _DEFAULT_TARGET_TITLE_PATTERN),
            watchlist_probe_names=tuple(
                name.strip() for name in watchlist_names.split(",") if name.strip()
            ),
            expected_layout=os.environ.get(f"{_ENV_PREFIX}EXPECTED_LAYOUT") or None,
            multi_symbol_switch_timeout_seconds=float(
                _env(
                    "MULTI_SYMBOL_SWITCH_TIMEOUT_SECONDS",
                    str(_DEFAULT_MULTI_SYMBOL_SWITCH_TIMEOUT_SECONDS),
                )
            ),
        )
