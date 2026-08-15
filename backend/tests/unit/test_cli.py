"""Die Kommandozeile fuer den manuellen Lauf.

Geprueft wird alles, was ohne TWS pruefbar ist: das Einlesen der Watchlist,
die Argumentbehandlung und die Verweigerung, wenn die Konfiguration gar nicht
auf IBKR steht. Der Abruf selbst braucht eine laufende TWS und ist
ausdruecklich nicht Gegenstand dieser Tests.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from ai_trading_analyst.cli import build_parser, main
from ai_trading_analyst.domain.analysis import Stock
from ai_trading_analyst.domain.screening import (
    Candle,
    CandleSeries,
    IndicatorParameters,
    compute_indicator_values,
)

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


NEW_YORK = ZoneInfo("America/New_York")
INDIKATOREN = IndicatorParameters(
    rsi_length=14,
    rsi_method="wilder",
    rsi_ma_length=14,
    rsi_ma_type="sma",
    fast_ema_length=5,
    slow_ema_length=20,
)


def steigende_preise(count: int) -> list[float]:
    return [100.0 + index * 0.5 for index in range(count)]


def wendepreise() -> list[float]:
    """Lange fallend, am Ende steil steigend -- so kreuzen EMA5 und EMA20, der
    Kurs durchbricht die EMA20 und der RSI kreuzt seine Glaettung, alles
    innerhalb der letzten sechs Kerzen. Das ergibt einen Kandidaten."""
    return [300.0 - index for index in range(254)] + [50.0 + index * 25.0 for index in range(6)]


def kerzenreihe(preise: Sequence[float]) -> CandleSeries:
    beginn = datetime(2026, 1, 5, 9, 30, tzinfo=NEW_YORK)
    candles = []
    for index, preis in enumerate(preise):
        tag, position = divmod(index, 2)
        candles.append(
            Candle(
                timestamp=beginn + timedelta(days=tag, minutes=195 * position),
                daily_candle_index=position + 1,
                open=preis,
                high=preis + 1.0,
                low=preis - 1.0,
                close=preis,
                volume=1_000.0,
            )
        )
    return CandleSeries(
        candles=tuple(candles),
        indicators=compute_indicator_values([candle.close for candle in candles], INDIKATOREN),
    )


class FakeProvider:
    """Steht an der Stelle des IBKR-Adapters -- ohne TWS, ohne Netzwerk."""

    def __init__(
        self,
        series: CandleSeries,
        symbole: Sequence[str] = ("AAPL",),
        abbruch_bei: int | None = None,
    ) -> None:
        self._series = series
        self._symbole = symbole
        self._abbruch_bei = abbruch_bei
        self.abgefragt: list[str] = []

    def list_stocks(self) -> Sequence[Stock]:
        return tuple(
            Stock(id=uuid.uuid4(), symbol=symbol, exchange="NASDAQ")
            for symbol in self._symbole
        )

    def get_candle_series(self, stock: Stock) -> CandleSeries:
        self.abgefragt.append(stock.symbol)
        if self._abbruch_bei is not None and len(self.abgefragt) == self._abbruch_bei:
            raise KeyboardInterrupt
        return self._series


class TestAusgabeEinesErfolgreichenLaufs:
    """Der Weg, den die TWS-Tests nicht erreichen: eine Aktie laeuft durch.

    Ohne diese Tests waere die einzige Probe der Ausgabe der Live-Lauf auf dem
    Windows-Server gewesen -- und ein Formatfehler waere erst dort aufgefallen.
    """

    @staticmethod
    def lauf(
        projekt: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        candles: int = 260,
        preise: Sequence[float] | None = None,
        provider: FakeProvider | None = None,
        weitere_argumente: Sequence[str] = (),
    ) -> int:
        config = write_config(projekt, provider="ibkr")
        eingesetzt = provider or FakeProvider(
            kerzenreihe(preise if preise is not None else steigende_preise(candles))
        )
        monkeypatch.setattr(
            "ai_trading_analyst.cli.build_market_data_provider",
            lambda *args, **kwargs: eingesetzt,
        )
        return main(
            [
                "--config",
                str(config),
                "screen",
                "--no-pacing",
                *weitere_argumente,
            ]
        )

    def test_eine_durchgelaufene_aktie_ergibt_rueckgabewert_null(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert self.lauf(projekt, monkeypatch) == 0

        ausgabe = capsys.readouterr().out
        assert "AAPL" in ausgabe
        assert "Kerzen=260" in ausgabe
        assert "FEHLER" not in ausgabe

    def test_ohne_details_stehen_keine_indikatorwerte_in_der_ausgabe(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self.lauf(projekt, monkeypatch)
        assert "RSI=" not in capsys.readouterr().out

    def test_mit_details_stehen_schlusskurs_und_alle_vier_indikatoren_da(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self.lauf(projekt, monkeypatch, weitere_argumente=["--details"])

        ausgabe = capsys.readouterr().out
        assert "Schluss=229.5000" in ausgabe  # 100.0 + 259 * 0.5
        for kennzahl in ("RSI=", "RSI-MA=", "EMA5=", "EMA20="):
            assert kennzahl in ausgabe

    def test_indikatorwerte_erscheinen_ungerundet_mit_vier_stellen(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """G1-Pruefvorlage 1.4: gerechnet wird ungerundet. Zwei Nachkommastellen
        wuerden einen Abgleich mit dem Chart unmoeglich machen."""
        self.lauf(projekt, monkeypatch, weitere_argumente=["--details"])
        werte = [
            teil for teil in capsys.readouterr().out.split() if teil.startswith("EMA20=")
        ]
        assert werte and len(werte[0].split("=")[1].split(".")[1]) == 4

    def test_eine_zu_kurze_historie_wird_als_unbekannt_ausgewiesen(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Der Fall SPCX: 81 Kerzen reichen fuer den Warm-up nicht. Es wird
        keine Kandidatenentscheidung getroffen, und der Grund steht dabei."""
        assert self.lauf(projekt, monkeypatch, candles=81) == 0

        ausgabe = capsys.readouterr().out
        assert "UNKNOWN_DATA_INCOMPLETE" in ausgabe
        assert "warmup_insufficient" in ausgabe

    def test_fehlende_indikatorwerte_erscheinen_als_strich_statt_als_null(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Am Anfang einer Reihe gibt es noch keinen RSI. Eine 0 an dieser
        Stelle waere ein erfundener Wert."""
        self.lauf(projekt, monkeypatch, candles=3, weitere_argumente=["--details"])
        assert "RSI=-" in capsys.readouterr().out

    def test_die_zusammenfassung_zaehlt_und_nennt_die_kandidaten(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self.lauf(projekt, monkeypatch)

        ausgabe = capsys.readouterr().out
        assert "1 Aktien in" in ausgabe
        # Gleichmaessig steigend: EMA5 ueber EMA20, kein Kreuzen, kein
        # Durchbruch -- hoechstens ein Signaltyp, also kein Kandidat.
        assert "NOT_CANDIDATE" in ausgabe
        assert "Kandidaten:" not in ausgabe

    def test_ein_kandidat_wird_am_ende_namentlich_aufgefuehrt(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Die Kandidatenliste ist das Ergebnis des Laufs -- bei knapp 200
        Aktien ist sie die einzige Zeile, die man wirklich liest."""
        self.lauf(projekt, monkeypatch, preise=wendepreise())

        ausgabe = capsys.readouterr().out
        assert "CANDIDATE" in ausgabe
        assert "Kandidaten: AAPL" in ausgabe

    def test_limit_kuerzt_die_liste_vor_dem_ersten_abruf(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Wichtig fuer den Probelauf: Die Begrenzung muss greifen, bevor
        Anfragen an die TWS gehen, nicht erst bei der Ausgabe."""
        provider = FakeProvider(
            kerzenreihe(steigende_preise(260)), symbole=("AAPL", "MSFT", "NVDA")
        )
        exit_code = self.lauf(
            projekt, monkeypatch, provider=provider, weitere_argumente=["--limit", "2"]
        )

        assert exit_code == 0
        assert provider.abgefragt == ["AAPL", "MSFT"]

    def test_abbruch_per_strg_c_behaelt_die_bisherigen_ergebnisse(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Ein Lauf ueber die volle Watchlist dauert ueber eine Stunde. Wer
        ihn abbricht, soll die bis dahin geprueften Aktien behalten und am
        Rueckgabewert erkennen, dass der Lauf nicht vollstaendig war."""
        provider = FakeProvider(
            kerzenreihe(steigende_preise(260)),
            symbole=("AAPL", "MSFT", "NVDA"),
            abbruch_bei=2,
        )
        assert self.lauf(projekt, monkeypatch, provider=provider) == 130

        ausgabe = capsys.readouterr()
        assert "1 Aktien in" in ausgabe.out  # die erste Aktie steht in der Bilanz
        assert "Abgebrochen" in ausgabe.err


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


class TestBackfillKommando:
    """Das einzige Kommando, das etwas dauerhaft ablegt -- und damit als
    einziges eine Datenbank braucht."""

    def test_ohne_datenbankadresse_meldet_es_sich_verstaendlich(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("ATA_DATABASE_URL", raising=False)
        config = write_config(projekt, provider="ibkr")

        assert main(["--config", str(config), "backfill", "--symbols", "AAPL"]) == 2
        assert "Datenbank" in capsys.readouterr().err

    def test_eine_unerreichbare_datenbank_beendet_den_lauf_vor_der_ersten_aktie(
        self,
        projekt: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Sonst quittiert jede Aktie einzeln denselben Anmeldefehler."""
        monkeypatch.setenv("ATA_DATABASE_URL", "postgresql+psycopg://ata:geheim@127.0.0.1:1/ata")
        config = write_config(projekt, provider="ibkr")

        assert main(["--config", str(config), "backfill", "--symbols", "AAPL"]) == 2
        ausgabe = capsys.readouterr().err
        assert "nicht erreichbar" in ausgabe
        assert "ATA_DATABASE_URL" in ausgabe
        assert "geheim" not in ausgabe  # die Adresse enthaelt das Passwort

    def test_eine_leere_symbolliste_wird_abgelehnt(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = write_config(projekt, provider="ibkr")
        assert main(["--config", str(config), "backfill", "--symbols", ","]) == 2
        assert "kein Symbol" in capsys.readouterr().err

    def test_ohne_abstand_und_mit_voller_watchlist_wird_der_lauf_verweigert(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        symbols = ",".join(f"NASDAQ:SYM{index}" for index in range(25))
        (projekt / "watchlists" / "test.txt").write_text(symbols, encoding="utf-8")
        config = write_config(projekt, provider="ibkr")

        assert main(["--config", str(config), "backfill", "--no-pacing"]) == 2
        assert "nicht zulaessig" in capsys.readouterr().err

    def test_die_argumente_werden_eingelesen(self) -> None:
        args = build_parser().parse_args(
            ["backfill", "--symbols", "AAPL,MSFT", "--limit", "5", "--no-pacing"]
        )
        assert args.symbols == "AAPL,MSFT"
        assert args.limit == 5
        assert args.no_pacing is True

    def test_ohne_provider_meldet_es_die_ausgelieferte_einstellung(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Der Standard 'fixture' darf nie stillschweigend zur TWS greifen."""
        config = write_config(projekt, provider="fixture")

        assert main(["--config", str(config), "backfill", "--symbols", "AAPL"]) == 2
        assert "--provider ibkr" in capsys.readouterr().err

    def test_der_provider_laesst_sich_je_lauf_uebersteuern(
        self,
        projekt: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Wie bei ``screen``: Die Konfiguration im Repository bleibt auf
        'fixture', damit ein 'git pull' auf dem Server keinen lokalen Diff
        vorfindet."""
        monkeypatch.delenv("ATA_DATABASE_URL", raising=False)
        config = write_config(projekt, provider="fixture")

        code = main(
            ["--config", str(config), "backfill", "--provider", "ibkr", "--symbols", "AAPL"]
        )

        # Bis zur Datenbank kommt der Lauf -- die Provider-Sperre ist passiert.
        assert code == 2
        assert "Datenbank" in capsys.readouterr().err


class TestBarquelleFuerDasScreening:
    def test_standard_ist_der_direkte_abruf(self) -> None:
        assert build_parser().parse_args(["screen"]).source == "live"

    def test_der_bestand_laesst_sich_waehlen(self) -> None:
        assert build_parser().parse_args(["screen", "--source", "stored"]).source == "stored"


    def test_aus_dem_bestand_greift_die_pacing_sperre_nicht(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Ohne Anfrage an die TWS gibt es nichts zu drosseln -- die Sperre
        waere hier nur im Weg. Sie darf den Lauf nicht mit 2 abweisen."""
        symbols = ",".join(f"NASDAQ:SYM{index}" for index in range(25))
        (projekt / "watchlists" / "test.txt").write_text(symbols, encoding="utf-8")
        monkeypatch.delenv("ATA_DATABASE_URL", raising=False)
        config = write_config(projekt, provider="ibkr")

        exit_code = main(
            ["--config", str(config), "screen", "--source", "stored", "--no-pacing"]
        )

        # 2 kommt hier nur noch von der fehlenden Datenbankadresse, nicht vom
        # Pacing -- erkennbar an der Meldung.
        assert exit_code == 2
        assert "nicht zulaessig" not in capsys.readouterr().err

    def test_ohne_datenbankadresse_meldet_sich_der_bestand_verstaendlich(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("ATA_DATABASE_URL", raising=False)
        config = write_config(projekt, provider="ibkr")

        exit_code = main(
            ["--config", str(config), "screen", "--source", "stored", "--symbols", "AAPL"]
        )

        assert exit_code == 2
        assert "Datenbank" in capsys.readouterr().err
