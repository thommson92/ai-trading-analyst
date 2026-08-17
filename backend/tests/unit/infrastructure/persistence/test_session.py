"""Der Anklopfversuch vor einem langen Lauf.

Ohne ihn faellt eine falsche Adresse erst beim Speichern des ersten Symbols
auf. Weil der Backfill je Aktie fehlerisoliert arbeitet, quittierten in der
Inbetriebnahme alle fuenf Symbole denselben Anmeldefehler -- bei der vollen
Watchlist waeren es 192 gewesen.
"""

from __future__ import annotations

import time

import pytest
from sqlalchemy.exc import OperationalError

from ai_trading_analyst.infrastructure.persistence.session import (
    CONNECT_TIMEOUT_SECONDS,
    DatabaseUnavailableError,
    build_engine,
    verify_connection,
)

# Port 1 nimmt nichts entgegen. Wie schnell das auffaellt, entscheidet aber
# nicht dieser Test, sondern das Betriebssystem: Linux und macOS weisen die
# Verbindung sofort ab, der Windows-Server verwirft das Paket stattdessen und
# liess den Aufbau minutenlang haengen. Verlassen wird sich deshalb allein auf
# die Frist aus ``build_engine``.
GESCHLOSSENER_PORT = "postgresql+psycopg://ata:geheim@127.0.0.1:1/ata"


def test_ein_nicht_erreichbarer_server_meldet_sich_als_solcher() -> None:
    with pytest.raises(DatabaseUnavailableError):
        verify_connection(build_engine(GESCHLOSSENER_PORT))


def test_die_meldung_bleibt_einzeilig() -> None:
    """psycopg wiederholt sie sonst je aufgeloester Adresse, IPv6 und IPv4."""
    with pytest.raises(DatabaseUnavailableError) as fehler:
        verify_connection(build_engine(GESCHLOSSENER_PORT))

    assert "\n" not in str(fehler.value)


def test_das_passwort_steht_nicht_in_der_meldung() -> None:
    """Die Adresse enthaelt es -- die Meldung landet im Log."""
    with pytest.raises(DatabaseUnavailableError) as fehler:
        verify_connection(build_engine(GESCHLOSSENER_PORT))

    assert "geheim" not in str(fehler.value)


def test_die_urspruengliche_ausnahme_bleibt_erhalten() -> None:
    """Fuer die Fehlersuche: Der Grund darf nicht verlorengehen."""
    with pytest.raises(DatabaseUnavailableError) as fehler:
        verify_connection(build_engine(GESCHLOSSENER_PORT))

    assert isinstance(fehler.value.__cause__, OperationalError)


def test_der_versuch_gibt_nach_der_vereinbarten_frist_auf() -> None:
    """Sonst haengt der taegliche Lauf, statt sich zu melden.

    Der Aufbau muss von sich aus aufgeben, auch wenn das Betriebssystem das
    Paket verwirft statt es abzuweisen -- ohne diese Frist hing der Aufruf auf
    dem Windows-Server minutenlang, und die Aufgabenplanung haette alle 15
    Minuten einen weiteren wartenden Prozess gestartet.
    """
    begonnen = time.monotonic()
    with pytest.raises(DatabaseUnavailableError):
        verify_connection(build_engine(GESCHLOSSENER_PORT))

    assert time.monotonic() - begonnen < CONNECT_TIMEOUT_SECONDS + 2
