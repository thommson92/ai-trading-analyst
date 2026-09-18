"""Die Verdrahtung des Exportschritts in der Composition Root (ADR 0060).

Hier steht keine Verschluesselung und kein Dateisystem, sondern die Kette
von Entscheidungen davor: Ist der Schritt eingeschaltet? Liegt ein Ziel vor?
Ist die Passphrase da, wenn verschluesselt werden soll? Liegt der
Zustandsvermerk ausserhalb dessen, was hinausgeht?

**Die wichtigste Zusage dieser Datei** ist die dritte: Wer ``encrypt`` sagt
und die Passphrase vergisst, bekommt einen Abbruch und keinen Klartextbaum.
Ein Tippfehler im Namen der Umgebungsvariablen wuerde sonst stillschweigend
Berichte, Kurse und Symbole beim Anbieter ablegen -- das ist die Lage, die
ADR 0049 mit "solange nichts das eigene Netz verlaesst" bewusst vermieden
hat.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from ai_trading_analyst import bootstrap
from ai_trading_analyst.bootstrap import (
    build_chart_market_data,
    build_dashboard_publisher,
    project_root,
)
from ai_trading_analyst.config.loader import load_config
from ai_trading_analyst.config.settings import (
    AppConfig,
    DashboardExportConfig,
    MissingSecretError,
    Secrets,
)
from ai_trading_analyst.domain.analysis import MarketDataUnavailableError, UnitOfWork
from ai_trading_analyst.infrastructure.ibkr import IbkrMarketDataProvider
from ai_trading_analyst.infrastructure.persistence.stored_bar_source import StoredBarSource
from ai_trading_analyst.infrastructure.publishing import MINDEST_ITERATIONEN


def uow_factory() -> Callable[[], UnitOfWork]:
    def fabrik() -> UnitOfWork:  # pragma: no cover -- wird hier nie gerufen
        raise AssertionError("Die Verdrahtung darf keine Datenbank oeffnen.")

    return fabrik


def konfiguration(**felder: object) -> AppConfig:
    basis = load_config().config
    return basis.model_copy(update={"dashboard_export": DashboardExportConfig(**felder)})


def baue(config: AppConfig, secrets: Secrets, root: Path) -> object:
    return build_dashboard_publisher(config, secrets, root, uow_factory=uow_factory())


class TestAbgeschaltet:
    def test_ausgeliefert_entsteht_kein_exportschritt(self, tmp_path: Path) -> None:
        """Ein frisch aufgesetzter Server exportiert nichts."""
        assert baue(konfiguration(), Secrets(), tmp_path) is None

    def test_ohne_verzeichnis_bricht_es_ab(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="directory"):
            baue(konfiguration(target="directory"), Secrets(), tmp_path)


class TestKeinRueckfallAufKlartext:
    def test_ohne_passphrase_bricht_der_verschluesselte_export_ab(self, tmp_path: Path) -> None:
        """Kein stiller Rueckfall -- der Kern der Stufe-2-Zusage."""
        with pytest.raises(MissingSecretError, match="ATA_DASHBOARD_EXPORT_PASSPHRASE"):
            baue(
                konfiguration(target="directory", directory="var/dashboard"),
                Secrets(),
                tmp_path,
            )

    def test_mit_passphrase_entsteht_er(self, tmp_path: Path) -> None:
        secrets = Secrets(dashboard_export_passphrase="eine-lange-passphrase")
        assert (
            baue(
                konfiguration(target="directory", directory="var/dashboard"),
                secrets,
                tmp_path,
            )
            is not None
        )

    def test_ohne_verschluesselung_braucht_es_keine_passphrase(self, tmp_path: Path) -> None:
        """Stufe 1 ist erlaubt -- sie muss nur ausdruecklich gewaehlt sein."""
        assert (
            baue(
                konfiguration(target="directory", directory="var/dashboard", encrypt=False),
                Secrets(),
                tmp_path,
            )
            is not None
        )


class TestFruehePruefungen:
    """Alles, was hier abbricht, bricht **vor** dem halbstuendigen Backfill ab."""

    def test_zu_wenige_runden_brechen_frueh_ab(self, tmp_path: Path) -> None:
        secrets = Secrets(dashboard_export_passphrase="eine-lange-passphrase")
        with pytest.raises(ValueError, match=str(MINDEST_ITERATIONEN)):
            baue(
                konfiguration(
                    target="directory", directory="var/dashboard", pbkdf2_iterations=1000
                ),
                secrets,
                tmp_path,
            )

    def test_zustandsdatei_im_datenbaum_wird_abgelehnt(self, tmp_path: Path) -> None:
        """Sie traegt die Zuordnung von Pfad zu opakem Namen.

        Laege sie im veroeffentlichten Verzeichnis, ginge sie beim naechsten
        Upload mit hinaus -- und die Verschluesselung der Dateinamen waere
        umsonst gewesen.
        """
        secrets = Secrets(dashboard_export_passphrase="eine-lange-passphrase")
        with pytest.raises(ValueError, match="veroeffentlichten Verzeichnis"):
            baue(
                konfiguration(
                    target="directory",
                    directory="var/dashboard",
                    state_file="var/dashboard/zustand.json",
                ),
                secrets,
                tmp_path,
            )

    def test_der_standardort_liegt_neben_dem_baum(self, tmp_path: Path) -> None:
        secrets = Secrets(dashboard_export_passphrase="eine-lange-passphrase")
        veroeffentlicher = baue(
            konfiguration(target="directory", directory="var/dashboard"), secrets, tmp_path
        )
        assert veroeffentlicher is not None
        ziel = veroeffentlicher._ziel  # type: ignore[attr-defined]
        assert not ziel.zustandsdatei.is_relative_to(ziel.wurzel)


class TestGeheimnisse:
    def test_die_passphrase_wird_zur_schwaerzung_angemeldet(self) -> None:
        """ADR 0044: Was in ``Secrets`` steht, darf nicht ins Protokoll.

        Der Exportschritt protokolliert Ziel, Umfang und Dauer -- und im
        Fehlerfall die Meldung der Bibliothek. Eine Passphrase, die dabei
        durchschluepft, stuende in einer Datei auf dem Handelsrechner.
        """
        from ai_trading_analyst.observability.secret_redaction import redact_registered

        Secrets(dashboard_export_passphrase="streng-geheime-passphrase")

        assert "streng-geheime-passphrase" not in redact_registered(
            "Fehler mit streng-geheime-passphrase im Text"
        )


class TestKommandozeile:
    def test_publish_meldet_den_abgeschalteten_export_ohne_datenbank(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Rueckgabewert 2 und eine Meldung -- **vor** dem Verbindungsversuch.

        Ausgeliefert steht der Export auf ``none``. Ein Aufruf soll das sagen
        und nicht hinter einem Datenbankfehler verschwinden, der mit der Sache
        nichts zu tun hat.
        """
        from ai_trading_analyst import cli

        code = cli.main(["publish"])

        assert code == 2
        assert "abgeschaltet" in capsys.readouterr().err

    def _publish(
        self, monkeypatch: pytest.MonkeyPatch, ziel: str, *argumente: str
    ) -> tuple[AppConfig, dict[str, object]]:
        """Ruft ``cli publish`` ohne Datenbank und ohne Dateisystem.

        Festgehalten wird, welche Konfiguration im Composition Root ankommt
        und womit der Baum geschrieben werden soll.
        """
        from types import SimpleNamespace

        from ai_trading_analyst import cli

        geladen = load_config()
        vorgabe = SimpleNamespace(
            config=konfiguration(target=ziel, directory="var/vorgabe"),
            source_path=geladen.source_path,
        )
        gesehen: dict[str, object] = {}

        class _Veroeffentlicher:
            def schreibe_baum(self, **argumente: object) -> object:
                gesehen.update(argumente)
                return SimpleNamespace(als_text=lambda: "nichts passiert")

        def _gemerkt(config: AppConfig, *_: object, **__: object) -> object:
            gesehen["config"] = config
            return _Veroeffentlicher()

        monkeypatch.setattr(cli, "load_config", lambda *_: vorgabe)
        monkeypatch.setattr(cli, "_open_database", lambda: object())
        monkeypatch.setattr(cli, "build_session_factory", lambda _: None)
        monkeypatch.setattr(cli, "build_dashboard_publisher", _gemerkt)

        assert cli.main(["publish", *argumente]) == 0
        config = gesehen.pop("config")
        assert isinstance(config, AppConfig)
        return config, gesehen

    def test_directory_schaltet_den_upload_nicht_ab(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """**Frueher tat es das, und zwar still.** Der Schalter setzte hart
        'directory' -- auf einem Server, der auf 'cloudflare' steht, waere
        ein Handgriff mit --directory damit ein Export gewesen, der nie
        hinausging, ohne dass jemand es gesagt haette."""
        config, _ = self._publish(monkeypatch, "cloudflare", "--directory", "var/anders")

        assert config.dashboard_export.target == "cloudflare"
        assert config.dashboard_export.directory == "var/anders"

    def test_directory_schaltet_einen_abgeschalteten_export_ein(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config, _ = self._publish(monkeypatch, "none", "--directory", "var/anders")

        assert config.dashboard_export.target == "directory"

    def test_ohne_schalter_wird_gesendet(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _, argumente = self._publish(monkeypatch, "cloudflare")

        assert argumente == {"voll": False, "senden": True}

    def test_no_upload_laesst_den_baum_liegen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _, argumente = self._publish(monkeypatch, "cloudflare", "--no-upload")

        assert argumente["senden"] is False


class TestChartquelle:
    """Woher die Kerzen fuer den Chart kommen -- und woher ausdruecklich nicht.

    Auf dem Server steht ``market_data.provider`` bewusst auf ``fixture``,
    damit ``git pull`` keinen lokalen Diff vorfindet; die produktive Quelle
    wird je Lauf ueber die Kommandozeile eingeschaltet. Ein Export, der
    diesen Wert erbte, baute den Chart aus **erfundenen** Kursen -- und
    stellte sie neben echte Analyseergebnisse, ohne sie als erfunden
    kenntlich zu machen.

    Beim ersten Export auf dem Server ist genau das passiert. Die Symbole der
    Watchlist stehen zufaellig in keiner Fixture, deshalb blieb der Baum
    chartlos statt falsch.

    **Zwei Ebenen, und die zweite ist die wichtigere.** Der Fehler sass nicht
    in ``build_chart_market_data`` -- die Funktion gab es nicht --, sondern
    an den beiden Aufrufstellen. Ein Test, der nur die Funktion prueft,
    bliebe gruen, wenn dort wieder die geerbte Konfiguration einzoege.
    """

    def test_der_fixture_anbieter_wird_nicht_uebernommen(self) -> None:
        geladen = load_config()
        basis = geladen.config
        assert basis.market_data.provider == "fixture", (
            "Die Voreinstellung hat sich geaendert -- dieser Test prueft dann nichts mehr."
        )

        quelle = build_chart_market_data(
            basis, basis.require_indicators(), project_root(geladen.source_path), uow_factory()
        )
        assert isinstance(quelle(), IbkrMarketDataProvider)

    def test_die_kerzen_kommen_aus_dem_bestand_und_nicht_von_der_tws(self) -> None:
        """Kein Chart darf eine TWS-Verbindung aufbauen (ADR 0052)."""
        geladen = load_config()
        auf_live = geladen.config.model_copy(
            update={
                "market_data": geladen.config.market_data.model_copy(update={"source": "live"})
            }
        )
        quelle = build_chart_market_data(
            auf_live,
            auf_live.require_indicators(),
            project_root(geladen.source_path),
            uow_factory(),
        )
        anbieter = quelle()
        assert isinstance(anbieter, IbkrMarketDataProvider)
        assert isinstance(anbieter._bar_source, StoredBarSource)

    def test_eine_fehlende_watchlist_kostet_den_chart_und_nicht_den_dienst(
        self, tmp_path: Path
    ) -> None:
        """Sie wird zum Ausfall uebersetzt, damit der Endpunkt 503 sagen kann.

        Ungefangen waere ``WatchlistError`` ein ``500`` aus einer
        FastAPI-Abhaengigkeit heraus -- ein Fehler des Dienstes, obwohl der
        Dienst in Ordnung ist und nur eine Datei fehlt.
        """
        geladen = load_config()
        quelle = build_chart_market_data(
            geladen.config, geladen.config.require_indicators(), tmp_path, uow_factory()
        )
        with pytest.raises(MarketDataUnavailableError, match="Watchlist"):
            quelle()


class TestDieAufrufstellenBenutzenSie:
    """Der Regressionsschutz fuer den Fehler, der tatsaechlich auftrat.

    Beide Aufrufstellen muessen ueber ``build_chart_market_data`` gehen und
    ihm die **unveraenderte** Konfiguration reichen. Wer dort wieder selbst
    eine Konfiguration umschreibt, faellt hier auf.
    """

    def test_der_export_baut_die_chartquelle_ueber_die_gemeinsame_funktion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gesehen: list[AppConfig] = []

        def spion(
            config: AppConfig, indicators: object, root: Path, uow: object
        ) -> Callable[[], object]:
            gesehen.append(config)
            return lambda: object()

        monkeypatch.setattr(bootstrap, "build_chart_market_data", spion)
        config = konfiguration(target="directory", directory="var/dashboard")
        baue(config, Secrets(dashboard_export_passphrase="x" * 40), tmp_path)

        assert len(gesehen) == 1
        assert gesehen[0].market_data == config.market_data


def mit_wrangler(root: Path) -> Path:
    """Legt ein Werkzeugverzeichnis an, wie ``npm ci`` es hinterliesse."""
    paket = root / "frontend" / "node_modules" / "wrangler"
    (paket / "bin").mkdir(parents=True)
    (paket / "bin" / "wrangler.js").write_text("// Attrappe\n", encoding="utf-8")
    (paket / "package.json").write_text(
        '{"name": "wrangler", "version": "4.135.0", '
        '"bin": {"wrangler": "./bin/wrangler.js"}}',
        encoding="utf-8",
    )
    return paket


def geheimnisse() -> Secrets:
    return Secrets(
        dashboard_export_passphrase="eine-lange-zufaellige-passphrase",
        dashboard_publish_token="ein-token-mit-genau-einem-recht",
        dashboard_publish_account="0123456789abcdef0123456789abcdef",
        dashboard_publish_worker="nichtssagender-name",
    )


def cloudflare(**felder: object) -> AppConfig:
    return konfiguration(target="cloudflare", directory="var/dashboard", **felder)


class TestDerWegNachDraussen:
    """``target: cloudflare`` (ADR 0060, E4).

    **Alles hier faellt vor dem Backfill auf.** Der Tageslauf baut diesen
    Schritt, bevor er eine halbe Stunde rechnet -- eine Fehlkonfiguration
    soll nicht erst am Ende auffallen, wenn der Lauf fertig ist.
    """

    def test_der_schritt_entsteht(self, tmp_path: Path) -> None:
        mit_wrangler(tmp_path)
        assert baue(cloudflare(), geheimnisse(), tmp_path) is not None

    @pytest.mark.parametrize(
        ("fehlend", "secrets"),
        [
            (
                "dashboard_publish_token",
                Secrets(
                    dashboard_export_passphrase="eine-lange-zufaellige-passphrase",
                    dashboard_publish_token="",
                    dashboard_publish_account="0123456789abcdef0123456789abcdef",
                    dashboard_publish_worker="nichtssagender-name",
                ),
            ),
            (
                "dashboard_publish_account",
                Secrets(
                    dashboard_export_passphrase="eine-lange-zufaellige-passphrase",
                    dashboard_publish_token="ein-token-mit-genau-einem-recht",
                    dashboard_publish_account="",
                    dashboard_publish_worker="nichtssagender-name",
                ),
            ),
            (
                "dashboard_publish_worker",
                Secrets(
                    dashboard_export_passphrase="eine-lange-zufaellige-passphrase",
                    dashboard_publish_token="ein-token-mit-genau-einem-recht",
                    dashboard_publish_account="0123456789abcdef0123456789abcdef",
                    dashboard_publish_worker="",
                ),
            ),
        ],
    )
    def test_ohne_geheimnis_bricht_es_ab(
        self, tmp_path: Path, fehlend: str, secrets: Secrets
    ) -> None:
        """Ein leerer Wert zaehlt als nicht gesetzt -- sonst liefe ein Upload
        mit leerem Token bis zur Absage des Anbieters."""
        mit_wrangler(tmp_path)

        with pytest.raises(MissingSecretError, match=fehlend.upper()):
            baue(cloudflare(), secrets, tmp_path)

    def test_ohne_werkzeug_nennt_der_abbruch_den_handgriff(self, tmp_path: Path) -> None:
        """Auf dem Server heisst dieser Fall fast immer: nach dem ``git pull``
        das ``npm ci`` im Frontend vergessen."""
        with pytest.raises(ValueError, match="npm ci"):
            baue(cloudflare(), geheimnisse(), tmp_path)

    def test_ein_werkzeug_ohne_einstiegspunkt_bricht_ab(self, tmp_path: Path) -> None:
        paket = mit_wrangler(tmp_path)
        (paket / "package.json").write_text('{"name": "wrangler"}', encoding="utf-8")

        with pytest.raises(ValueError, match="Einstiegspunkt"):
            baue(cloudflare(), geheimnisse(), tmp_path)

    def test_die_konfiguration_darf_nicht_im_datenbaum_liegen(self, tmp_path: Path) -> None:
        """Dieselbe Begruendung wie beim Zustandsvermerk: Sie nennt den
        Worker beim Namen, und was im Verzeichnis liegt, geht mit hinauf."""
        mit_wrangler(tmp_path)

        with pytest.raises(ValueError, match="upload_directory"):
            baue(
                cloudflare(upload_directory="var/dashboard/intern"),
                geheimnisse(),
                tmp_path,
            )

    def test_ohne_angabe_liegt_sie_neben_dem_baum(self, tmp_path: Path) -> None:
        mit_wrangler(tmp_path)
        veroeffentlicher = baue(cloudflare(), geheimnisse(), tmp_path)

        hochlader = veroeffentlicher._hochlader  # type: ignore[attr-defined]
        assert hochlader._ziel.arbeitsverzeichnis == (tmp_path / "var" / "dashboard.upload")
        assert hochlader._ziel.befehl[0] == "node"

    def test_directory_verdrahtet_keinen_upload(self, tmp_path: Path) -> None:
        """Die Rueckfallstufe: schreiben, ohne zu senden -- und ohne dass
        Token oder Werkzeug ueberhaupt gebraucht wuerden."""
        veroeffentlicher = baue(
            konfiguration(
                target="directory",
                directory="var/dashboard",
            ),
            Secrets(dashboard_export_passphrase="eine-lange-zufaellige-passphrase"),
            tmp_path,
        )

        assert veroeffentlicher._hochlader is None  # type: ignore[attr-defined]
