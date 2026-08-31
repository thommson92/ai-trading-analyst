"""Die Schwaerzung wirkt an der Senke -- fuer fremde Zeilen genauso.

Diese Tests gehen bewusst durch den **echten** Logging-Aufbau und den echten
``httpx``-Client. Ein Test gegen ``redact_registered`` allein bewiese nur,
dass die Funktion ersetzt, was man ihr gibt. Die Frage war eine andere: ob
das Geheimnis ueberhaupt an dieser Funktion vorbeikommt.

Beide hier geprueften Kanaele waren offen, obwohl die Fehlermeldung des
Adapters bereits geschwaerzt war.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

from ai_trading_analyst.config.settings import LoggingConfig, Secrets
from ai_trading_analyst.observability.logging_setup import configure_logging, get_logger
from ai_trading_analyst.observability.secret_redaction import (
    forget_secrets,
    redact_registered,
    register_secret,
)

GEHEIM = "geheimer-finnhub-schluessel-12345"


@pytest.fixture(autouse=True)
def _angemeldetes_geheimnis() -> Iterator[None]:
    forget_secrets()
    register_secret(GEHEIM)
    yield
    forget_secrets()


@pytest.fixture(params=["console", "json"])
def format_name(request: pytest.FixtureRequest) -> str:
    """Beide Ausgabeformen. Der Server laeuft auf ``json``, die Entwicklung
    auf ``console`` -- ein Leck in nur einer Form faende niemand."""
    return str(request.param)


class TestErfolgreicheAnfragen:
    """Der schwerwiegendere der beiden Kanaele.

    ``httpx`` protokolliert jede Anfrage selbst, auf ``INFO``, mit der
    vollstaendigen URL. ``config/default.yaml`` steht auf ``level: INFO``.
    Der Schluessel stand damit nicht im Ausnahmefall im Protokoll, sondern
    bei **jedem** Abruf -- rund zweihundert Zeilen je Tageslauf.
    """

    def test_die_anfragezeile_von_httpx_enthaelt_den_schluessel_nicht(
        self, format_name: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging(LoggingConfig(level="INFO", format=format_name))

        transport = httpx.MockTransport(lambda request: httpx.Response(200, json=[]))
        with httpx.Client(transport=transport) as client:
            client.get(
                "https://finnhub.io/api/v1/stock/recommendation",
                params={"symbol": "AAPL", "token": GEHEIM},
            )

        ausgabe = capsys.readouterr().out
        assert "HTTP Request" in ausgabe, "ohne die Zeile prueft der Test nichts"
        assert GEHEIM not in ausgabe

    def test_die_zeile_bleibt_im_uebrigen_brauchbar(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Geschwaerzt heisst nicht unleserlich: Wer ein Problem sucht, muss
        Endpunkt und Symbol weiterhin sehen."""
        configure_logging(LoggingConfig(level="INFO", format="console"))

        transport = httpx.MockTransport(lambda request: httpx.Response(200, json=[]))
        with httpx.Client(transport=transport) as client:
            client.get(
                "https://finnhub.io/api/v1/stock/recommendation",
                params={"symbol": "AAPL", "token": GEHEIM},
            )

        ausgabe = capsys.readouterr().out
        assert "stock/recommendation" in ausgabe
        assert "AAPL" in ausgabe


class TestAusnahmekette:
    """Der Kanal, den eine geschwaerzte Fehlermeldung gerade **nicht** schliesst.

    ``raise ... from error`` haelt die ausloesende Ausnahme als ``__cause__``
    fest. ``_logger.exception`` formatiert die ganze Kette -- und die Ursache
    traegt die unveraenderte URL. ``run_analysis`` protokolliert an fuenf
    Stellen so.
    """

    def test_der_traceback_der_ursache_enthaelt_den_schluessel_nicht(
        self, format_name: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging(LoggingConfig(level="INFO", format=format_name))
        logger = get_logger("test")

        try:
            with httpx.Client(
                transport=httpx.MockTransport(lambda request: httpx.Response(500, text="boom"))
            ) as client:
                antwort = client.get(
                    "https://finnhub.io/api/v1/stock/recommendation",
                    params={"symbol": "AAPL", "token": GEHEIM},
                )
                antwort.raise_for_status()
        except httpx.HTTPError as ursache:
            try:
                # Genau das Muster beider Finnhub-Adapter: aeussere Meldung
                # geschwaerzt, Ursache angehaengt.
                raise RuntimeError("Abruf fehlgeschlagen: ***") from ursache
            except RuntimeError:
                logger.exception("Anbieter hat eine Ausnahme geworfen")

        ausgabe = capsys.readouterr().out
        assert "HTTPStatusError" in ausgabe, "ohne Traceback prueft der Test nichts"
        assert GEHEIM not in ausgabe


class TestDieAnmeldungHaengtAmModellNichtAmLadeweg:
    """Der Fehler, den die Serverprobe am 2026-08-31 gefunden hat.

    Die Anmeldung sass zuerst in ``load_secrets``. Das CLI baut ``Secrets()``
    an sechs Stellen selbst und ging daran vorbei -- der Finnhub-Schluessel
    stand unveraendert in der Anfragezeile von ``httpx``, obwohl die
    Schwaerzung als erledigt galt.

    Der Test prueft deshalb nicht ``load_secrets``, sondern die **direkte**
    Konstruktion: genau den Weg, den das CLI nimmt.
    """

    def test_ein_direkt_gebautes_secrets_meldet_an(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        forget_secrets()
        monkeypatch.setenv("ATA_FINNHUB_API_KEY", "direkt-gebauter-schluessel")

        Secrets(_env_file=None)

        assert "direkt-gebauter-schluessel" not in redact_registered(
            "token=direkt-gebauter-schluessel"
        )

    def test_der_weg_des_cli_schwaerzt_die_anfragezeile(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Die Serverprobe als Test: Logging aufsetzen, ``Secrets()`` bauen,
        abrufen -- in genau dieser Reihenfolge, wie ``command_ratings`` es tut."""
        forget_secrets()
        monkeypatch.setenv("ATA_FINNHUB_API_KEY", GEHEIM)
        configure_logging(LoggingConfig(level="INFO", format="console"))

        schluessel = Secrets(_env_file=None).require("finnhub_api_key")
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json=[]))
        with httpx.Client(transport=transport) as client:
            client.get(
                "https://finnhub.io/api/v1/stock/recommendation",
                params={"symbol": "AAPL", "token": schluessel},
            )

        ausgabe = capsys.readouterr().out
        assert "HTTP Request" in ausgabe, "ohne die Zeile prueft der Test nichts"
        assert GEHEIM not in ausgabe
