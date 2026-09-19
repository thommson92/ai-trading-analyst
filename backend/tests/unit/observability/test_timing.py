"""Tests der Dauermessung.

Die Uhr wird eingespeist statt abgewartet: Ein Test, der eine Sekunde
schlaeft, um eine Sekunde zu messen, prueft vor allem die Geduld dessen, der
ihn laufen laesst.
"""

from __future__ import annotations

import json
import logging

import pytest

from ai_trading_analyst.config import LoggingConfig
from ai_trading_analyst.observability import configure_logging, gemessen, get_logger


class Uhr:
    """Eine monotone Uhr, die nur auf Zuruf weiterlaeuft."""

    def __init__(self) -> None:
        self.stand = 100.0

    def __call__(self) -> float:
        return self.stand


def test_eine_zeile_mit_dauer_ereignis_und_eigenen_feldern(
    capsys: pytest.CaptureFixture[str],
) -> None:
    uhr = Uhr()
    configure_logging(LoggingConfig(level="INFO", format="json"))

    with gemessen(get_logger("ata.test"), "phase_1", monotonic=uhr, aktien=192) as messwerte:
        uhr.stand += 2.5
        messwerte["kandidaten"] = 36

    zeilen = [zeile for zeile in capsys.readouterr().out.splitlines() if zeile.strip()]

    assert len(zeilen) == 1
    payload = json.loads(zeilen[0])
    assert payload["event"] == "phase_1"
    assert payload["duration_ms"] == 2500.0
    assert payload["ausgang"] == "ok"
    assert payload["aktien"] == 192
    assert payload["kandidaten"] == 36


def test_ein_gescheiterter_abschnitt_wird_trotzdem_gemessen(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Gerade der interessiert: Ein Abbruch nach vierzig Minuten hat vierzig
    Minuten gekostet. Die Ausnahme laeuft dabei unveraendert weiter."""
    uhr = Uhr()
    configure_logging(LoggingConfig(level="INFO", format="json"))

    with pytest.raises(ValueError, match="kaputt"):
        with gemessen(get_logger("ata.test"), "phase_1", monotonic=uhr):
            uhr.stand += 7.0
            raise ValueError("kaputt")

    payload = json.loads(capsys.readouterr().out.strip())

    assert payload["duration_ms"] == 7000.0
    assert payload["ausgang"] == "fehler"


def test_die_dauer_ist_ein_eigenes_feld_und_kein_fliesstext(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Der Zweck der ganzen Uebung: auswertbar statt lesbar.

    Stuende ``duration_ms`` weiterhin in der Reservierungsliste des
    Formatters, hiesse das Feld hier ``extra_duration_ms`` -- und jede
    Auswertung, die dem Modulkopf von ``logging_setup`` glaubt, fande nichts.
    """
    uhr = Uhr()
    configure_logging(LoggingConfig(level="INFO", format="json"))

    with gemessen(get_logger("ata.test"), "backfill", monotonic=uhr):
        uhr.stand += 2100.0

    payload = json.loads(capsys.readouterr().out.strip())

    assert payload["duration_ms"] == 2100000.0
    assert "extra_duration_ms" not in payload


def test_ohne_eingespeiste_uhr_wird_wirklich_gemessen(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Die Voreinstellung ist ``time.monotonic`` -- und die laeuft nie rueckwaerts."""
    configure_logging(LoggingConfig(level="INFO", format="json"))

    with gemessen(get_logger("ata.test"), "kurz"):
        pass

    payload = json.loads(capsys.readouterr().out.strip())

    assert isinstance(payload["duration_ms"], float)
    assert payload["duration_ms"] >= 0.0


def test_die_stufe_laesst_sich_absenken(capsys: pytest.CaptureFixture[str]) -> None:
    """Nicht jede Messung gehoert auf INFO -- eine je Aktie waere bei 192
    Titeln sonst die lauteste Zeile des Laufs."""
    configure_logging(LoggingConfig(level="INFO", format="json"))

    with gemessen(get_logger("ata.test"), "je_aktie", level=logging.DEBUG):
        pass

    assert capsys.readouterr().out == ""
