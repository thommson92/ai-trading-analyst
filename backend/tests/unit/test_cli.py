"""Die Kommandozeile fuer den manuellen Lauf.

Geprueft wird alles, was ohne TWS pruefbar ist: das Einlesen der Watchlist,
die Argumentbehandlung und die Verweigerung, wenn die Konfiguration gar nicht
auf IBKR steht. Der Abruf selbst braucht eine laufende TWS und ist
ausdruecklich nicht Gegenstand dieser Tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_trading_analyst.cli import build_parser, main

CONFIG_TEMPLATE = """
market_data:
  provider: {provider}
  ibkr:
    watchlist_directory: {directory}
indicators:
  rsi_length: 14
  rsi_method: wilder
  rsi_ma_length: 14
  rsi_ma_type: sma
  fast_ema_length: 5
  slow_ema_length: 20
  warmup_candles: 250
"""


@pytest.fixture
def projekt(tmp_path: Path) -> Path:
    """Ein Miniaturprojekt mit config/ und watchlists/ wie im Repository."""
    (tmp_path / "config").mkdir()
    watchlists = tmp_path / "watchlists"
    watchlists.mkdir()
    (watchlists / "test.txt").write_text("NASDAQ:AAPL,NYSE:BRK.B,NASDAQ:AAPL", encoding="utf-8")
    return tmp_path


def write_config(projekt: Path, provider: str, directory: str = "watchlists") -> Path:
    path = projekt / "config" / "default.yaml"
    path.write_text(
        CONFIG_TEMPLATE.format(provider=provider, directory=directory), encoding="utf-8"
    )
    return path


class TestWatchlistKommando:
    def test_zeigt_die_symbole_ohne_verbindung_zur_tws(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = write_config(projekt, provider="ibkr")
        assert main(["--config", str(config), "watchlist"]) == 0

        ausgabe = capsys.readouterr().out
        assert "test.txt" in ausgabe
        assert "AAPL" in ausgabe
        assert "BRK B" in ausgabe  # in IBKR-Schreibweise, nicht BRK.B
        assert "2 (Mehrfachnennungen zusammengefasst)" in ausgabe

    def test_ein_fehlendes_verzeichnis_meldet_sich_verstaendlich(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = write_config(projekt, provider="ibkr", directory="gibtsnicht")
        assert main(["--config", str(config), "watchlist"]) == 2
        assert "existiert nicht" in capsys.readouterr().err

    def test_funktioniert_auch_wenn_der_anbieter_auf_fixture_steht(self, projekt: Path) -> None:
        # Das Kommando liest nur Dateien -- dafuer muss nichts umgestellt sein.
        config = write_config(projekt, provider="fixture")
        assert main(["--config", str(config), "watchlist"]) == 0


class TestScreenKommando:
    def test_verweigert_den_lauf_wenn_der_anbieter_nicht_ibkr_ist(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Sonst liefe ein "Lauf gegen die TWS" stillschweigend auf
        # Fixture-Daten und saehe erfolgreich aus.
        config = write_config(projekt, provider="fixture")
        assert main(["--config", str(config), "screen"]) == 2
        assert "'fixture'" in capsys.readouterr().err


    def test_der_lauf_gegen_die_tws_scheitert_ohne_erreichbare_tws_klar(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Kein Test-Doppel: Hier laeuft der echte Adapter gegen einen
        unbesetzten Port. Geprueft wird, dass ein Ausfall der TWS pro Aktie
        gemeldet wird und den Lauf nicht abbrechen laesst."""
        config = write_config(projekt, provider="ibkr")
        exit_code = main(
            [
                "--config",
                str(config),
                "screen",
                "--provider",
                "ibkr",
                "--symbols",
                "AAPL",
                "--no-pacing",
            ]
        )

        ausgabe = capsys.readouterr().out
        # Rueckgabewert 1: Ein Skript, das nur darauf schaut, soll den
        # Totalausfall der TWS nicht fuer einen erfolgreichen Lauf halten.
        assert exit_code == 1
        assert "FEHLER" in ausgabe
        assert "Keine Verbindung zur TWS" in ausgabe

    def test_provider_kann_fuer_einen_lauf_uebersteuert_werden(self, projekt: Path) -> None:
        config = write_config(projekt, provider="fixture")
        # Ohne TWS scheitert der Abruf (Rueckgabewert 1); entscheidend ist,
        # dass die Umstellung ueberhaupt angenommen wurde (kein 2).
        assert (
            main(
                [
                    "--config",
                    str(config),
                    "screen",
                    "--provider",
                    "ibkr",
                    "--symbols",
                    "AAPL",
                    "--no-pacing",
                ]
            )
            == 1
        )

    def test_eine_leere_symbolliste_wird_abgelehnt(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = write_config(projekt, provider="ibkr")
        assert main(["--config", str(config), "screen", "--symbols", ",", "--no-pacing"]) == 2
        assert "kein Symbol" in capsys.readouterr().err

    def test_ohne_abstand_und_mit_voller_watchlist_wird_der_lauf_verweigert(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Sonst laeuft genau die Sperre auf, gegen die der Abstand da ist --
        und sie traefe auch die Fremdanwendung an derselben TWS."""
        symbols = ",".join(f"NASDAQ:SYM{index}" for index in range(25))
        (projekt / "watchlists" / "test.txt").write_text(symbols, encoding="utf-8")
        config = write_config(projekt, provider="ibkr")

        assert main(["--config", str(config), "screen", "--no-pacing"]) == 2
        assert "--no-pacing ist fuer 25 Aktien nicht zulaessig" in capsys.readouterr().err


class TestArgumente:
    def test_ohne_kommando_beendet_sich_die_cli_mit_hinweis(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_symbole_und_limit_werden_eingelesen(self) -> None:
        args = build_parser().parse_args(
            ["screen", "--symbols", "AAPL,MSFT", "--limit", "5", "--no-pacing"]
        )
        assert args.symbols == "AAPL,MSFT"
        assert args.limit == 5
        assert args.no_pacing is True
