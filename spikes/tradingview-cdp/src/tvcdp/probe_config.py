"""Konfigurierbare JavaScript-Sonden fuer TradingView-spezifische Fragen.

Der wichtigste Designentscheid dieses Spikes: **keine geratenen
DOM-Selektoren oder internen JS-Pfade fest im Code verdrahten.** Ohne
jemals selbst Zugriff auf TradingView Desktop gehabt zu haben, waere jeder
fest codierte Selektor eine unbelegte Annahme -- genau das Risiko, das der
Projektplan unter R1 als "hohes Wartungsrisiko" markiert.

Stattdessen sind alle TradingView-spezifischen Ausdruecke ausschliesslich
ueber Umgebungsvariablen konfigurierbar. Ist eine Sonde nicht gesetzt,
melden die betroffenen Schritte ehrlich INCONCLUSIVE statt eine
Placebo-Antwort zu liefern. Die Person, die den Windows-Testlauf
durchfuehrt, ermittelt die tatsaechlich funktionierenden Ausdruecke zuerst
manuell (siehe WINDOWS_VALIDATION.md, Abschnitt "Sonden ermitteln") und
setzt sie dann als Umgebungsvariablen -- der Code aendert sich dafuer nicht.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_ENV_PREFIX = "TVCDP_PROBE_"


def _probe_env(name: str) -> str | None:
    value = os.environ.get(f"{_ENV_PREFIX}{name}")
    return value if value else None


@dataclass(frozen=True, slots=True)
class ProbeConfig:
    """Eine Sonde je offener Frage. ``None`` heisst: noch nicht ermittelt."""

    session_authenticated_js: str | None
    watchlist_js: str | None
    layout_name_js: str | None
    timeframe_minutes_js: str | None
    last_closed_candle_js: str | None
    indicator_rsi_js: str | None
    indicator_rsi_ma_js: str | None
    indicator_ema5_js: str | None
    indicator_ema20_js: str | None
    change_symbol_js_template: str | None
    """Erwartet einen Platzhalter ``{symbol}``, siehe step_multi_symbol.py."""

    @classmethod
    def from_env(cls) -> ProbeConfig:
        return cls(
            session_authenticated_js=_probe_env("SESSION_AUTHENTICATED_JS"),
            watchlist_js=_probe_env("WATCHLIST_JS"),
            layout_name_js=_probe_env("LAYOUT_NAME_JS"),
            timeframe_minutes_js=_probe_env("TIMEFRAME_MINUTES_JS"),
            last_closed_candle_js=_probe_env("LAST_CLOSED_CANDLE_JS"),
            indicator_rsi_js=_probe_env("INDICATOR_RSI_JS"),
            indicator_rsi_ma_js=_probe_env("INDICATOR_RSI_MA_JS"),
            indicator_ema5_js=_probe_env("INDICATOR_EMA5_JS"),
            indicator_ema20_js=_probe_env("INDICATOR_EMA20_JS"),
            change_symbol_js_template=_probe_env("CHANGE_SYMBOL_JS_TEMPLATE"),
        )
