"""Der Weg nach draussen (ADR 0060, E4).

Geprueft wird gegen einen eingesetzten Prozessstarter -- ``wrangler`` selbst
laeuft hier nicht. Was es tut, ist am 2026-09-17 auf dem Server gemessen
worden (Doc 14, Stufe L); was dieser Code daraus macht, steht hier.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from ai_trading_analyst.domain.scheduling import (
    DashboardPreviewUrlError,
    DashboardUploadError,
)
from ai_trading_analyst.infrastructure.publishing.upload import (
    KOMPATIBILITAETSDATUM,
    Hochladeziel,
    WranglerHochlader,
)

WORKER = "nichtssagender-name"
KONTO = "0123456789abcdef0123456789abcdef"
TOKEN = "ein-token-das-in-keiner-befehlszeile-stehen-darf"

AUSGABE = f"""
 ⛅️ wrangler 4.135.0
───────────────────
🌀 Building list of assets...
✨ Read 804 files from the assets directory
🌀 Starting asset upload...
✨ Success! Uploaded 786 files (18 already uploaded) (12.34 sec)
Uploaded {WORKER} (5.05 sec)
Deployed {WORKER} triggers (0.61 sec)
  https://{WORKER}.konto-subdomain.workers.dev
Current Version ID: b2c2bdba-5e14-4208-b5aa-e4d92832a983
"""


class _Starter:
    """Merkt sich, womit er gerufen wurde, und liefert ein Wunschergebnis."""

    def __init__(
        self,
        *,
        rueckgabewert: int = 0,
        ausgabe: str = AUSGABE,
        fehler: Exception | None = None,
    ) -> None:
        self.rueckgabewert = rueckgabewert
        self.ausgabe = ausgabe
        self.fehler = fehler
        self.aufrufe: list[tuple[Sequence[str], Path, dict[str, str], int]] = []

    def __call__(
        self,
        befehl: Sequence[str],
        arbeitsverzeichnis: Path,
        umgebung: dict[str, str],
        zeitgrenze: int,
    ) -> subprocess.CompletedProcess[str]:
        self.aufrufe.append((befehl, arbeitsverzeichnis, umgebung, zeitgrenze))
        if self.fehler is not None:
            raise self.fehler
        return subprocess.CompletedProcess(
            args=list(befehl), returncode=self.rueckgabewert, stdout=self.ausgabe, stderr=""
        )


def baum(tmp_path: Path) -> Path:
    """Ein Verzeichnis, das aussieht wie ein fertiger Datenbaum."""
    wurzel = tmp_path / "dashboard"
    (wurzel / "data").mkdir(parents=True)
    (wurzel / "index.html").write_text("<html></html>", encoding="utf-8")
    (wurzel / "_headers").write_text("/*\n  X-Frame-Options: DENY\n", encoding="utf-8")
    return wurzel


def hochlader(tmp_path: Path, starter: _Starter, *, worker: str = WORKER) -> WranglerHochlader:
    return WranglerHochlader(
        Hochladeziel(
            worker=worker,
            konto=KONTO,
            token=TOKEN,
            baum=baum(tmp_path),
            arbeitsverzeichnis=tmp_path / "dashboard.upload",
            befehl=lambda: ["node", "/irgendwo/wrangler.js"],
            zeitgrenze=900,
        ),
        starter=starter,
    )


def ohne_kommentare(text: str) -> dict[str, object]:
    zeilen = [zeile for zeile in text.splitlines() if not zeile.strip().startswith("//")]
    geladen: dict[str, object] = json.loads("\n".join(zeilen))
    return geladen


class TestKonfigurationsdatei:
    def test_vorschauadressen_stehen_ausdruecklich_auf_falsch(self, tmp_path: Path) -> None:
        """Die eine Zeile, an der alles haengt.

        Ohne sie folgt ``preview_urls`` dem eingeschalteten ``workers_dev``
        und ist damit wahr -- und alte Fassungen, die wegen des stabilen
        Salts unter demselben Schluessel stehen, waeren wieder erreichbar.
        """
        pfad = hochlader(tmp_path, _Starter()).schreibe_konfiguration()

        assert ohne_kommentare(pfad.read_text(encoding="utf-8"))["preview_urls"] is False
        # Auch woertlich: Wer die Datei auf dem Server ansieht, soll die
        # Zeile finden, ohne sie parsen zu muessen.
        assert '"preview_urls": false' in pfad.read_text(encoding="utf-8")

    def test_nennt_worker_datum_und_zielverzeichnis(self, tmp_path: Path) -> None:
        pfad = hochlader(tmp_path, _Starter()).schreibe_konfiguration()

        inhalt = ohne_kommentare(pfad.read_text(encoding="utf-8"))
        assert inhalt["name"] == WORKER
        assert inhalt["compatibility_date"] == KOMPATIBILITAETSDATUM
        assert inhalt["workers_dev"] is True
        assert inhalt["assets"] == {"directory": "../dashboard"}

    def test_das_kompatibilitaetsdatum_wandert_nicht_mit(self) -> None:
        """Ein Datum, das dem Kalender folgt, aenderte das Verhalten des
        Workers irgendwann ohne Anlass."""
        assert KOMPATIBILITAETSDATUM == "2026-09-17"

    def test_liegt_neben_dem_baum_und_nicht_darin(self, tmp_path: Path) -> None:
        werkzeug = hochlader(tmp_path, _Starter())
        pfad = werkzeug.schreibe_konfiguration()

        assert not pfad.is_relative_to(tmp_path / "dashboard")

    def test_wird_bei_jedem_upload_neu_geschrieben(self, tmp_path: Path) -> None:
        """Von Hand geaenderte Werte gehen verloren -- das ist der Sinn."""
        werkzeug = hochlader(tmp_path, _Starter())
        pfad = werkzeug.schreibe_konfiguration()
        pfad.write_text('{"preview_urls": true}', encoding="utf-8")

        werkzeug.lade_hoch()

        assert '"preview_urls": false' in pfad.read_text(encoding="utf-8")


class TestDerAufruf:
    def test_das_token_steht_in_keiner_befehlszeile(self, tmp_path: Path) -> None:
        """Es geht ueber die Umgebung. Eine Befehlszeile steht unter Windows
        in der Prozessliste und in der Verlaufsdatei der Shell."""
        starter = _Starter()
        hochlader(tmp_path, starter).lade_hoch()

        befehl, _, umgebung, _ = starter.aufrufe[0]
        assert TOKEN not in " ".join(befehl)
        assert umgebung["CLOUDFLARE_API_TOKEN"] == TOKEN
        assert umgebung["CLOUDFLARE_ACCOUNT_ID"] == KONTO

    def test_der_unterprozess_sieht_keine_ata_geheimnisse(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """**Die Zusage dieses Moduls.** Ein fremdes Werkzeug hat die
        Passphrase des Datenbaums nicht zu sehen -- sie ist das einzige
        Schloss vor den Daten, und der Anbieter soll sie nie bekommen."""
        monkeypatch.setenv("ATA_DASHBOARD_EXPORT_PASSPHRASE", "das-schloss-vor-den-daten")
        monkeypatch.setenv("ATA_DATABASE_URL", "postgresql+psycopg://ata:geheim@localhost/db")
        monkeypatch.setenv("ATA_LLM_API_KEY", "ein-modellschluessel")
        starter = _Starter()

        hochlader(tmp_path, starter).lade_hoch()

        _, _, umgebung, _ = starter.aufrufe[0]
        assert not [name for name in umgebung if name.startswith("ATA_")]

    def test_kein_node_options_im_unterprozess(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ueber NODE_OPTIONS kaeme fremder Code in den Prozess."""
        monkeypatch.setenv("NODE_OPTIONS", "--require /tmp/boeses.js")
        starter = _Starter()

        hochlader(tmp_path, starter).lade_hoch()

        assert "NODE_OPTIONS" not in starter.aufrufe[0][2]

    def test_laeuft_im_verzeichnis_der_konfiguration(self, tmp_path: Path) -> None:
        """Der Zielpfad wird relativ zur Konfigurationsdatei aufgeloest.
        Aus deren Verzeichnis heraus stimmen beide Lesarten ueberein."""
        starter = _Starter()
        hochlader(tmp_path, starter).lade_hoch()

        befehl, arbeitsverzeichnis, _, zeitgrenze = starter.aufrufe[0]
        assert arbeitsverzeichnis == tmp_path / "dashboard.upload"
        assert list(befehl[:2]) == ["node", "/irgendwo/wrangler.js"]
        assert befehl[2] == "deploy"
        assert zeitgrenze == 900

    def test_meldet_zahlen_und_version_aus_der_ausgabe(self, tmp_path: Path) -> None:
        bericht = hochlader(tmp_path, _Starter()).lade_hoch()

        assert bericht.dateien_gesamt == 804
        assert bericht.dateien_gesendet == 786
        assert bericht.version == "b2c2bdba-5e14-4208-b5aa-e4d92832a983"

    def test_eine_unlesbare_ausgabe_laesst_den_upload_gelten(self, tmp_path: Path) -> None:
        """Die Zahlen stehen im Protokoll und sonst nirgends. Ein Werkzeug,
        das seine Ausgabe umformuliert, soll den Lauf nicht anhalten."""
        bericht = hochlader(tmp_path, _Starter(ausgabe="fertig.")).lade_hoch()

        assert bericht.dateien_gesamt is None
        assert bericht.version is None
        assert "unbekannt" in bericht.als_text()


class TestWennEtwasSchiefgeht:
    def test_rueckgabewert_ungleich_null(self, tmp_path: Path) -> None:
        starter = _Starter(rueckgabewert=1, ausgabe="Authentication error [code: 10000]")

        with pytest.raises(DashboardUploadError, match="Rueckgabewert 1"):
            hochlader(tmp_path, starter).lade_hoch()

    def test_zeitueberschreitung(self, tmp_path: Path) -> None:
        starter = _Starter(fehler=subprocess.TimeoutExpired(cmd="node", timeout=900))

        with pytest.raises(DashboardUploadError, match="900 s"):
            hochlader(tmp_path, starter).lade_hoch()

    def test_fehlendes_werkzeug_nennt_den_handgriff(self, tmp_path: Path) -> None:
        """Nicht ein nackter FileNotFoundError: Auf dem Server heisst dieser
        Fall fast immer 'npm ci nach dem git pull vergessen'."""
        starter = _Starter(fehler=FileNotFoundError(2, "No such file", "node"))

        with pytest.raises(DashboardUploadError, match="npm ci"):
            hochlader(tmp_path, starter).lade_hoch()

    @pytest.mark.parametrize("fehlend", ["index.html", "_headers"])
    def test_ohne_oberflaeche_geht_nichts_hinaus(self, tmp_path: Path, fehlend: str) -> None:
        """Ginge nur ``data/`` hinaus, laege draussen Chiffrat ohne etwas, das
        es anzeigt -- oder eine Seite ohne ihre Sicherheits-Header."""
        starter = _Starter()
        werkzeug = hochlader(tmp_path, starter)
        (tmp_path / "dashboard" / fehlend).unlink()

        with pytest.raises(DashboardUploadError, match=fehlend):
            werkzeug.lade_hoch()

        # **Vor dem Start**, nicht nach einem halben Upload.
        assert starter.aufrufe == []


class TestVorschauadressen:
    def test_die_produktivadresse_allein_ist_in_ordnung(self, tmp_path: Path) -> None:
        bericht = hochlader(tmp_path, _Starter()).lade_hoch()

        assert bericht.dateien_gesendet == 786

    def test_eine_versionsadresse_wird_gemeldet(self, tmp_path: Path) -> None:
        """Die Probe haengt an der Form: Bei der Produktivadresse ist das
        erste Namensglied der Worker-Name, bei einer Vorschau nicht."""
        starter = _Starter(
            ausgabe=(
                f"{AUSGABE}\n"
                f"  Preview URL: https://b2c2bdba-{WORKER}.konto-subdomain.workers.dev\n"
            )
        )

        with pytest.raises(DashboardPreviewUrlError, match=f"b2c2bdba-{WORKER}"):
            hochlader(tmp_path, starter).lade_hoch()

    def test_der_befund_haengt_nicht_am_wortlaut_des_werkzeugs(self, tmp_path: Path) -> None:
        """Ohne das Wort "Preview" und trotzdem erkannt -- eine
        Formulierungsaenderung der naechsten Fassung laesst die Probe kalt."""
        starter = _Starter(ausgabe=f"https://irgendwas-{WORKER}.konto-subdomain.workers.dev")

        with pytest.raises(DashboardPreviewUrlError):
            hochlader(tmp_path, starter).lade_hoch()

    def test_grossschreibung_macht_aus_der_produktivadresse_keine_vorschau(
        self, tmp_path: Path
    ) -> None:
        starter = _Starter(ausgabe=f"https://{WORKER.upper()}.konto-subdomain.workers.dev")

        hochlader(tmp_path, starter).lade_hoch()


class TestEinEchterUnterprozess:
    """Einmal ohne eingesetzten Starter -- sonst bliebe ``_starte_prozess``
    selbst ungeprueft, und genau dort sitzt die Umgebung.

    Die Attrappe ist ein Python-Skript und kein Node-Skript: Sie laeuft
    damit ueberall, wo die Tests laufen, auch auf dem Windows-Runner der
    CI ohne eingerichtetes Node.
    """

    def _attrappe(self, tmp_path: Path, quelltext: str) -> list[str]:
        import sys

        skript = tmp_path / "attrappe.py"
        skript.write_text(quelltext, encoding="utf-8")
        return [sys.executable, str(skript)]

    def test_der_ganze_weg_mit_einem_echten_prozess(self, tmp_path: Path) -> None:
        werkzeug = WranglerHochlader(
            Hochladeziel(
                worker=WORKER,
                konto=KONTO,
                token=TOKEN,
                baum=baum(tmp_path),
                arbeitsverzeichnis=tmp_path / "dashboard.upload",
                befehl=lambda: self._attrappe(
                    tmp_path,
                    "import json, os, pathlib, sys\n"
                    # Beweist zweierlei: Die Konfiguration liegt da, wo der
                    # Prozess arbeitet, und die Umgebung kam wirklich an.
                    "konfiguration = pathlib.Path('wrangler.jsonc')\n"
                    "assert konfiguration.is_file(), 'Konfiguration fehlt im Arbeitsverzeichnis'\n"
                    "assert os.environ['CLOUDFLARE_API_TOKEN']\n"
                    "assert not [n for n in os.environ if n.startswith('ATA_')]\n"
                    "print('Read 804 files from the assets directory')\n"
                    "print('Uploaded 786 files')\n"
                    f"print('  https://{WORKER}.konto-subdomain.workers.dev')\n"
                    "print('Current Version ID: b2c2bdba-5e14-4208-b5aa-e4d92832a983')\n",
                ),
                zeitgrenze=60,
            )
        )

        bericht = werkzeug.lade_hoch()

        assert bericht.dateien_gesamt == 804
        assert bericht.dateien_gesendet == 786
        assert bericht.version == "b2c2bdba-5e14-4208-b5aa-e4d92832a983"
        assert bericht.dauer_sekunden > 0

    def test_ein_echter_fehlschlag_wird_zum_uploadfehler(self, tmp_path: Path) -> None:
        werkzeug = WranglerHochlader(
            Hochladeziel(
                worker=WORKER,
                konto=KONTO,
                token=TOKEN,
                baum=baum(tmp_path),
                arbeitsverzeichnis=tmp_path / "dashboard.upload",
                befehl=lambda: self._attrappe(
                    tmp_path,
                    "import sys\n"
                    "print('Authentication error [code: 10000]', file=sys.stderr)\n"
                    "sys.exit(1)\n",
                ),
                zeitgrenze=60,
            )
        )

        with pytest.raises(DashboardUploadError, match="10000"):
            werkzeug.lade_hoch()

    def test_ein_haengender_prozess_wird_beendet(self, tmp_path: Path) -> None:
        """Ohne Zeitgrenze bliebe der Tageslauf daran haengen -- still."""
        werkzeug = WranglerHochlader(
            Hochladeziel(
                worker=WORKER,
                konto=KONTO,
                token=TOKEN,
                baum=baum(tmp_path),
                arbeitsverzeichnis=tmp_path / "dashboard.upload",
                befehl=lambda: self._attrappe(tmp_path, "import time\ntime.sleep(60)\n"),
                zeitgrenze=1,
            )
        )

        with pytest.raises(DashboardUploadError, match="nicht geantwortet"):
            werkzeug.lade_hoch()


class TestDieWerkzeugsuche:
    """Sie sitzt im Upload und nicht im Bau des Exportschritts.

    Der Bau laeuft im Tageslauf vor dem Backfill; ein Abbruch dort kostet
    Screening, Analyse und Ergebnismeldung. Ein vergessenes ``npm ci`` darf
    nur den Upload kosten -- deshalb wirft alles hier
    ``DashboardUploadError`` und keinen ``ValueError``.
    """

    def _paket(self, tmp_path: Path, beschreibung: str, *, mit_einstieg: bool = True) -> Path:
        paket = tmp_path / "wrangler"
        (paket / "wrangler-dist").mkdir(parents=True)
        if mit_einstieg:
            (paket / "wrangler-dist" / "cli.js").write_text("// Attrappe\n", encoding="utf-8")
        (paket / "package.json").write_text(beschreibung, encoding="utf-8")
        return paket

    def test_der_einstieg_kommt_aus_main(self, tmp_path: Path) -> None:
        """``main`` und nicht ``bin``: Der Starter in ``bin`` reicht an einen
        Enkelprozess weiter, der unsere Leitungen erbt -- eine Zeitgrenze
        liefe daran vorbei."""
        from ai_trading_analyst.infrastructure.publishing.upload import wrangler_befehl

        paket = self._paket(tmp_path, '{"main": "wrangler-dist/cli.js"}')

        befehl = wrangler_befehl(paket)

        assert befehl[0] == "node"
        assert Path(befehl[1]) == paket / "wrangler-dist" / "cli.js"

    def test_ein_fehlendes_paket_nennt_den_handgriff(self, tmp_path: Path) -> None:
        from ai_trading_analyst.infrastructure.publishing.upload import wrangler_befehl

        with pytest.raises(DashboardUploadError, match="npm ci"):
            wrangler_befehl(tmp_path / "gibt-es-nicht")

    def test_eine_kaputte_paketdatei(self, tmp_path: Path) -> None:
        """Ein Syntaxfehler ist **kein** ``OSError``."""
        from ai_trading_analyst.infrastructure.publishing.upload import wrangler_befehl

        paket = self._paket(tmp_path, "{kaputt")

        with pytest.raises(DashboardUploadError, match="nicht lesbar"):
            wrangler_befehl(paket)

    def test_eine_paketdatei_ohne_main(self, tmp_path: Path) -> None:
        from ai_trading_analyst.infrastructure.publishing.upload import wrangler_befehl

        paket = self._paket(tmp_path, '{"name": "wrangler"}')

        with pytest.raises(DashboardUploadError, match="Einstieg"):
            wrangler_befehl(paket)

    def test_ein_halb_ausgepacktes_node_modules(self, tmp_path: Path) -> None:
        """Die Paketdatei ist da, die Datei dahinter nicht."""
        from ai_trading_analyst.infrastructure.publishing.upload import wrangler_befehl

        paket = self._paket(
            tmp_path, '{"main": "wrangler-dist/cli.js"}', mit_einstieg=False
        )

        with pytest.raises(DashboardUploadError, match="fehlt"):
            wrangler_befehl(paket)


class TestWasDerUnterprozessNichtSehenDarf:
    def test_eine_env_neben_der_konfiguration_bricht_ab(self, tmp_path: Path) -> None:
        """**Die zweite Haelfte der Zusage.** Das Werkzeug liest eine ``.env``
        neben seiner Konfiguration ein. Laege das Arbeitsverzeichnis in der
        Projektwurzel, bekaeme es damit jedes ATA_-Geheimnis in die Hand --
        an der Erlaubnisliste vorbei, die genau das verhindern soll."""
        starter = _Starter()
        werkzeug = hochlader(tmp_path, starter)
        arbeit = tmp_path / "dashboard.upload"
        arbeit.mkdir()
        (arbeit / ".env").write_text("ATA_DASHBOARD_EXPORT_PASSPHRASE=geheim\n", encoding="utf-8")

        with pytest.raises(DashboardUploadError, match=r"\.env"):
            werkzeug.lade_hoch()

        assert starter.aufrufe == []

    def test_ein_unschreibbares_arbeitsverzeichnis(self, tmp_path: Path) -> None:
        """Ein ``OSError`` beim Schreiben der Konfiguration ist ein
        Upload-Fehler -- der Baum ist zu diesem Zeitpunkt geschrieben."""
        starter = _Starter()
        werkzeug = hochlader(tmp_path, starter)
        # Eine Datei, wo ein Verzeichnis hin soll.
        (tmp_path / "dashboard.upload").write_text("im Weg", encoding="utf-8")

        with pytest.raises(DashboardUploadError, match="nicht schreiben"):
            werkzeug.lade_hoch()


class TestDieAusgabeWirdAlsUtf8Gelesen:
    """Auf einem deutschen Windows nimmt Python sonst ``cp1252``.

    Wrangler gibt UTF-8 mit Emoji aus, und schon das Variationszeichen in
    ``⛅️`` enthaelt ein Byte, das cp1252 nicht kennt. Der Upload waere
    gelungen und der Schritt trotzdem gescheitert -- gemeldet als
    "Dashboard nicht aktualisiert", also als die Lage, die am wenigsten
    stimmt.
    """

    def test_emoji_in_der_ausgabe_stoeren_nicht(self, tmp_path: Path) -> None:
        import sys

        skript = tmp_path / "attrappe.py"
        skript.write_text(
            "import sys\n"
            "sys.stdout.buffer.write(' \\u26c5\\ufe0f wrangler 4.135.0\\n'.encode('utf-8'))\n"
            "sys.stdout.buffer.write(b'Read 804 files from the assets directory\\n')\n"
            "sys.stdout.buffer.write(b'Uploaded 786 files\\n')\n"
            "sys.stdout.buffer.write(b'Current Version ID: b2c2bdba-5e14-4208\\n')\n",
            encoding="utf-8",
        )
        werkzeug = WranglerHochlader(
            Hochladeziel(
                worker=WORKER,
                konto=KONTO,
                token=TOKEN,
                baum=baum(tmp_path),
                arbeitsverzeichnis=tmp_path / "dashboard.upload",
                befehl=lambda: [sys.executable, str(skript)],
                zeitgrenze=60,
            )
        )

        bericht = werkzeug.lade_hoch()

        assert bericht.dateien_gesamt == 804
        assert bericht.version == "b2c2bdba-5e14-4208"


class TestEinEnkelprozessHaeltDieLeitungen:
    """Der Fall, an dem ``subprocess.run`` unter Windows haengen bliebe.

    ``run`` sammelt nach dem Abschiessen **ohne Zeitgrenze** ein. Haelt ein
    Enkelprozess die Leitungen noch, wartet es ewig -- innerhalb der
    Exportsperre, im naechtlichen Lauf, still. Unter POSIX ginge es gut aus;
    der Zielserver ist Windows, und dort faehrt die CI diesen Test.
    """

    def test_die_zeitgrenze_greift_trotzdem(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import sys
        import time as zeitmodul

        from ai_trading_analyst.infrastructure.publishing import upload as modul

        monkeypatch.setattr(modul, "NACHFRIST_SEKUNDEN", 1)
        skript = tmp_path / "attrappe.py"
        skript.write_text(
            "import subprocess, sys, time\n"
            # Ein Kind, das unsere Leitungen erbt und weiterlebt.
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
            "time.sleep(30)\n",
            encoding="utf-8",
        )
        werkzeug = WranglerHochlader(
            Hochladeziel(
                worker=WORKER,
                konto=KONTO,
                token=TOKEN,
                baum=baum(tmp_path),
                arbeitsverzeichnis=tmp_path / "dashboard.upload",
                befehl=lambda: [sys.executable, str(skript)],
                zeitgrenze=1,
            )
        )

        begonnen = zeitmodul.monotonic()
        with pytest.raises(DashboardUploadError, match="nicht geantwortet"):
            werkzeug.lade_hoch()

        # Gebunden, nicht haengend -- das ist die ganze Aussage.
        assert zeitmodul.monotonic() - begonnen < 15
