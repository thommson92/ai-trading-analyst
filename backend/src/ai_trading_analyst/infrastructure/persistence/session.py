"""Engine- und Session-Konstruktion. Kennt die Datenbank-URL, sonst nichts."""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker


class DatabaseUnavailableError(RuntimeError):
    """Die Datenbank antwortet nicht oder weist die Anmeldung ab."""


def build_engine(database_url: str) -> Engine:
    return create_engine(database_url, future=True)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def verify_connection(engine: Engine) -> None:
    """Einmal anklopfen, bevor ein langer Lauf beginnt.

    ``create_engine`` baut keine Verbindung auf; die entsteht erst beim ersten
    Zugriff. Ohne diese Pruefung faellt eine falsche Adresse oder ein falsches
    Passwort erst beim Speichern des ersten Symbols auf -- und dann, weil der
    Backfill je Aktie fehlerisoliert arbeitet, gleich zweihundertmal
    hintereinander mit demselben Text. Ein nicht erreichbarer Server ist kein
    Problem einer einzelnen Aktie.

    Die Meldung wird auf ihre erste Zeile gekuerzt: psycopg wiederholt sie
    sonst je aufgeloester Adresse, IPv6 und IPv4, wortgleich.
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        ursache = getattr(error, "orig", None) or error
        erste_zeile = str(ursache).strip().splitlines()[0]
        raise DatabaseUnavailableError(erste_zeile) from error
