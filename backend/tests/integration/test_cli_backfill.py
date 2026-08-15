"""Das Backfill-Kommando von aussen -- gegen echte Datenbank, ohne TWS.

Bisher waren nur die Abbruchpfade geprueft: fehlende Datenbankadresse,
falscher Anbieter, leere Symbolliste. Was der Nutzer tatsaechlich zu sehen
bekommt, wenn es *funktioniert*, war ungeprueft -- ebenso die Rueckgabewerte,
an denen sich ein spaeterer Scheduler orientieren muss.

Ersetzt ist ausschliesslich die TWS. Konfiguration, Watchlist, Datenbank,
Migrationen und Ausgabe sind echt.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from ai_trading_analyst import cli
from ai_trading_analyst.cli import main
from ai_trading_analyst.domain.analysis import ContractSpec, MarketDataProviderError
from ai_trading_analyst.domain.screening import IntradayBar

CONFIG = """
market_data:
  provider: fixture
  ibkr:
    watchlist_directory: watchlists
    history_duration: 1 Y
    minimum_request_interval_seconds: 0
indicators:
  rsi_length: 14
  rsi_method: wilder
  rsi_ma_length: 14
  rsi_ma_type: sma
  fast_ema_length: 5
  slow_ema_length: 20
  warmup_candles: 200
"""


@pytest.fixture
def projekt(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "watchlists").mkdir()
    (tmp_path / "watchlists" / "test.txt").write_text("NASDAQ:AAPL,NASDAQ:MSFT", encoding="utf-8")
    (tmp_path / "config" / "default.yaml").write_text(CONFIG, encoding="utf-8")
    return tmp_path


@pytest.fixture
def konfiguriert(
    projekt: Path, database_url: str, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """Die Datenbank der Integrationstests als ATA_DATABASE_URL."""
    monkeypatch.setenv("ATA_DATABASE_URL", database_url)
    yield projekt / "config" / "default.yaml"


def bars(anzahl: int, ende: datetime | None = None) -> list[IntradayBar]:
    letzter = ende or datetime(2026, 8, 13, 19, 45, tzinfo=UTC)
    return [
        IntradayBar(
            start=letzter - timedelta(minutes=15 * (anzahl - 1 - index)),
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
            volume=1_000.0,
        )
        for index in range(anzahl)
    ]


class FakeTws:
    def __init__(self, lieferung: Sequence[IntradayBar] | BaseException) -> None:
        self._lieferung = lieferung
        self.angefragt: list[tuple[str, int | None]] = []
        self.geschlossen = False

    def fetch_intraday_bars(
        self, contract: ContractSpec, days: int | None = None
    ) -> Sequence[IntradayBar]:
        self.angefragt.append((contract.symbol, days))
        if isinstance(self._lieferung, BaseException):
            raise self._lieferung
        return self._lieferung

    def close(self) -> None:
        self.geschlossen = True


@pytest.fixture
def tws(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Sequence[IntradayBar] | BaseException], FakeTws]:
    def einsetzen(lieferung: Sequence[IntradayBar] | BaseException) -> FakeTws:
        doppel = FakeTws(lieferung)
        monkeypatch.setattr(cli, "build_ibkr_bar_source", lambda config: doppel)
        return doppel

    return einsetzen


Einsetzen = Callable[[Sequence[IntradayBar] | BaseException], FakeTws]


class TestErfolgreicherLauf:
    def test_der_bericht_nennt_empfangene_und_neue_bars(
        self, konfiguriert: Path, tws: Einsetzen, capsys: pytest.CaptureFixture[str]
    ) -> None:
        tws(bars(20))

        assert main(["--config", str(konfiguriert), "backfill", "--provider", "ibkr"]) == 0

        ausgabe = capsys.readouterr().out
        assert "20 Bars empfangen" in ausgabe
        assert "20 neu" in ausgabe
        assert "neue Bars                    40" in ausgabe  # zwei Aktien
        assert "Fehler                       0" in ausgabe

    def test_ein_zweiter_lauf_schreibt_nichts_und_meldet_das(
        self, konfiguriert: Path, tws: Einsetzen, capsys: pytest.CaptureFixture[str]
    ) -> None:
        tws(bars(20))
        main(["--config", str(konfiguriert), "backfill", "--provider", "ibkr"])
        capsys.readouterr()

        assert main(["--config", str(konfiguriert), "backfill", "--provider", "ibkr"]) == 0
        assert "neue Bars                    0" in capsys.readouterr().out

    def test_der_zweite_lauf_fragt_nur_noch_die_luecke(
        self, konfiguriert: Path, tws: Einsetzen
    ) -> None:
        doppel = tws(bars(20))
        main(["--config", str(konfiguriert), "backfill", "--provider", "ibkr"])
        main(["--config", str(konfiguriert), "backfill", "--provider", "ibkr"])

        erster_aufruf = doppel.angefragt[0]
        spaeterer_aufruf = doppel.angefragt[2]
        assert erster_aufruf[1] is None  # Standardzeitraum der Konfiguration
        assert spaeterer_aufruf[1] is not None

    def test_die_verbindung_wird_freigegeben(self, konfiguriert: Path, tws: Einsetzen) -> None:
        doppel = tws(bars(5))
        main(["--config", str(konfiguriert), "backfill", "--provider", "ibkr"])
        assert doppel.geschlossen

    def test_limit_beschraenkt_die_watchlist(
        self, konfiguriert: Path, tws: Einsetzen, capsys: pytest.CaptureFixture[str]
    ) -> None:
        tws(bars(5))
        main(["--config", str(konfiguriert), "backfill", "--provider", "ibkr", "--limit", "1"])
        assert "1 Aktien," in capsys.readouterr().out


class TestFehlerImLauf:
    def test_ein_ausfall_ergibt_rueckgabewert_1(
        self, konfiguriert: Path, tws: Einsetzen, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Ein Scheduler muss den Unterschied zu einem sauberen Lauf sehen."""
        tws(MarketDataProviderError("Keine Verbindung zur TWS"))

        assert main(["--config", str(konfiguriert), "backfill", "--provider", "ibkr"]) == 1

        ausgabe = capsys.readouterr().out
        assert "Fehler                       2" in ausgabe
        assert "Fehlgeschlagen: AAPL, MSFT" in ausgabe

    def test_eine_leere_lieferung_wird_ausgewiesen(
        self, konfiguriert: Path, tws: Einsetzen, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Weder Fehler noch Kuerzung -- ohne eigene Zeile unsichtbar."""
        tws([])

        assert main(["--config", str(konfiguriert), "backfill", "--provider", "ibkr"]) == 0
        assert "Keine Bars erhalten (2)" in capsys.readouterr().out

    def test_ein_abbruch_ergibt_rueckgabewert_130(
        self, konfiguriert: Path, tws: Einsetzen, capsys: pytest.CaptureFixture[str]
    ) -> None:
        tws(KeyboardInterrupt())

        assert main(["--config", str(konfiguriert), "backfill", "--provider", "ibkr"]) == 130
        assert "Abgebrochen" in capsys.readouterr().err


class TestFromDatum:
    def test_from_uebersteuert_den_bestand(self, konfiguriert: Path, tws: Einsetzen) -> None:
        doppel = tws(bars(20))
        main(["--config", str(konfiguriert), "backfill", "--provider", "ibkr"])
        vorher = len(doppel.angefragt)

        gestern = (datetime.now(UTC) - timedelta(days=30)).date().isoformat()
        main(["--config", str(konfiguriert), "backfill", "--provider", "ibkr", "--from", gestern])

        assert doppel.angefragt[vorher][1] == 30

    def test_ein_datum_in_der_zukunft_wird_abgelehnt(
        self, konfiguriert: Path, tws: Einsetzen, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Sonst wuerde daraus stillschweigend 'ein Tag' -- aus dem
        Reparaturlauf ein Leerlauf."""
        doppel = tws(bars(5))
        morgen = (datetime.now(UTC) + timedelta(days=1)).date().isoformat()

        code = main(
            ["--config", str(konfiguriert), "backfill", "--provider", "ibkr", "--from", morgen]
        )

        assert code == 2
        assert "Zukunft" in capsys.readouterr().err
        assert doppel.angefragt == []


class TestUnbrauchbareDatenbankadresse:
    def test_eine_unlesbare_adresse_ergibt_keinen_traceback(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("ATA_DATABASE_URL", "das ist keine adresse")
        config = projekt / "config" / "default.yaml"

        assert main(["--config", str(config), "backfill", "--provider", "ibkr"]) == 2
        assert "keine gueltige Adresse" in capsys.readouterr().err

    def test_ein_unbekannter_treiber_ebenfalls_nicht(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("ATA_DATABASE_URL", "quatsch+treiber://ata:geheim@localhost:5432/ata")
        config = projekt / "config" / "default.yaml"

        assert main(["--config", str(config), "backfill", "--provider", "ibkr"]) == 2
        fehler = capsys.readouterr().err
        assert "keine gueltige Adresse" in fehler
        assert "geheim" not in fehler  # die Adresse enthaelt das Passwort
