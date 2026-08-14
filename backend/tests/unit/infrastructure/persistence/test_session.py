"""Der Anklopfversuch vor einem langen Lauf.

Ohne ihn faellt eine falsche Adresse erst beim Speichern des ersten Symbols
auf. Weil der Backfill je Aktie fehlerisoliert arbeitet, quittierten in der
Inbetriebnahme alle fuenf Symbole denselben Anmeldefehler -- bei der vollen
Watchlist waeren es 192 gewesen.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import OperationalError

from ai_trading_analyst.infrastructure.persistence.session import (
    DatabaseUnavailableError,
    build_engine,
    verify_connection,
)

# Port 1 nimmt nichts entgegen: Die Verbindung wird sofort abgewiesen, ohne
# Zeitueberschreitung und ohne Namensaufloesung.
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
