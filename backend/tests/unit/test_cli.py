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
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from ai_trading_analyst import cli
from ai_trading_analyst.cli import build_parser, main, require_complete_enough
from ai_trading_analyst.config import AppConfig, MissingSecretError, NotificationsConfig, Secrets
from ai_trading_analyst.domain.analysis import (
    AnalysisRun,
    AnalysisRunSummary,
    EarningsProvider,
    MarketDataProviderError,
    ResearchProvider,
    RunStatus,
    Stock,
    StockProcessingError,
    StockScreeningOutcome,
)
from ai_trading_analyst.domain.earnings import NextEarningsDate
from ai_trading_analyst.domain.scheduling import Notifier
from ai_trading_analyst.domain.screening import (
    SIGNAL_RULE_VERSION,
    Candle,
    CandleSeries,
    IndicatorParameters,
    ScreeningResult,
    ScreeningStatus,
    compute_indicator_values,
)
from ai_trading_analyst.domain.technical import (
    TECHNICAL_ANALYSIS_VERSION,
    PriceZone,
    TechnicalAnalysisParameters,
    TechnicalSnapshot,
    TechnicalStatus,
    TrendDirection,
    ZoneKind,
    ZoneStrength,
)


def _outcome(lauf_id: uuid.UUID, symbol: str) -> StockScreeningOutcome:
    return StockScreeningOutcome(
        analysis_run_id=lauf_id,
        stock=Stock(id=uuid.uuid4(), symbol=symbol, exchange="NASDAQ"),
        result=ScreeningResult(status=ScreeningStatus.NOT_CANDIDATE),
        decision_candle_index=0,
        evaluated_at=datetime.now(ZoneInfo("UTC")),
        signal_rule_version=SIGNAL_RULE_VERSION,
    )

CONFIG_TEMPLATE = """
market_data:
  provider: {provider}
  # Diese Tests pruefen die Kommandozeile, nicht den Bestand: 'live' haelt
  # sie von einer Datenbank frei. Der ausgelieferte Standard ist 'stored'.
  source: {source}
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


def write_config(
    projekt: Path, provider: str, directory: str = "watchlists", source: str = "live"
) -> Path:
    path = projekt / "config" / "default.yaml"
    path.write_text(
        CONFIG_TEMPLATE.format(provider=provider, directory=directory, source=source),
        encoding="utf-8",
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


class TestTechnicalKommando:
    """Die Ausgabe ist der Zweck dieses Kommandos: An ihr werden die Zonen am
    echten Chart gegengeprueft (ADR 0025)."""

    @staticmethod
    def _snapshot(**overrides: object) -> TechnicalSnapshot:
        felder: dict[str, Any] = {
            "status": TechnicalStatus.COMPLETED,
            "evaluated_at": datetime(2026, 8, 22, 12, 0, tzinfo=ZoneInfo("UTC")),
            "candle_timestamp": datetime(2026, 8, 21, 20, 15, tzinfo=ZoneInfo("UTC")),
            "close": 100.0,
            "trend": TrendDirection.UP,
            "rsi": 61.5,
            "ema5": 99.0,
            "ema20": 96.0,
            "distance_to_ema5_pct": 0.0101,
            "distance_to_ema20_pct": 0.0417,
            "atr": 2.5,
            "atr_pct": 0.025,
            "recent_high": 107.0,
            "recent_high_at": datetime(2026, 8, 18, 20, 15, tzinfo=ZoneInfo("UTC")),
            "recent_low": 88.0,
            "recent_low_at": datetime(2026, 8, 11, 20, 15, tzinfo=ZoneInfo("UTC")),
        }
        felder.update(overrides)
        return TechnicalSnapshot(**felder)

    def test_zonen_erscheinen_mit_allen_geforderten_angaben(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Doc 10, Paragraph 6.8 verlangt je Zone sieben Angaben -- eine
        Ausgabe ohne sie waere am Chart nicht nachpruefbar."""
        zone = PriceZone(
            lower=104.0,
            upper=107.0,
            kind=ZoneKind.RESISTANCE,
            strength=ZoneStrength.MODERATE,
            touch_count=3,
            last_confirmed_at=datetime(2026, 8, 18, 20, 15, tzinfo=ZoneInfo("UTC")),
            distance_pct=0.04,
            pivot_count=2,
        )

        cli._print_technical_snapshot("AAPL", self._snapshot(zones=(zone,)))

        ausgabe = capsys.readouterr().out
        assert "RESISTANCE" in ausgabe
        assert "104.00 - 107.00" in ausgabe
        assert "MODERATE" in ausgabe
        assert "3 Beruehrungen" in ausgabe
        assert "2026-08-18" in ausgabe
        assert "4.00 %" in ausgabe

    def test_ohne_zonen_sagt_die_ausgabe_das_ausdruecklich(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Eine fehlende Zonenliste soll nicht wie ein vergessener Abschnitt
        aussehen."""
        cli._print_technical_snapshot("AAPL", self._snapshot())

        assert "keine mehrfach getestete Preisregion" in capsys.readouterr().out

    def test_fehlende_werte_erscheinen_als_strich_statt_als_null(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Der Unterschied zwischen 'nicht berechenbar' und 'null' darf in
        der Ausgabe nicht verschwinden (CLAUDE.md: keine erfundenen Werte)."""
        cli._print_technical_snapshot(
            "AAPL", self._snapshot(rsi=None, atr=None, atr_pct=None, trend=None)
        )

        ausgabe = capsys.readouterr().out
        assert "RSI: --" in ausgabe
        assert "ATR: --" in ausgabe
        assert "Trend: --" in ausgabe

    def test_unvollstaendige_auswertung_nennt_den_grund_und_hoert_auf(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cli._print_technical_snapshot(
            "AAPL",
            TechnicalSnapshot(
                status=TechnicalStatus.INSUFFICIENT_DATA,
                evaluated_at=datetime(2026, 8, 22, 12, 0, tzinfo=ZoneInfo("UTC")),
                reason="too_few_candles",
            ),
        )

        ausgabe = capsys.readouterr().out
        assert "INSUFFICIENT_DATA" in ausgabe
        assert "too_few_candles" in ausgabe
        assert "Schlusskurs" not in ausgabe

    def test_die_wirksamen_zonenparameter_stehen_in_der_ausgabe(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Wer sie nach Doc 14 nachzieht, soll in derselben Ausgabe sehen,
        welche gerade gewirkt haben."""
        cli._print_technical_snapshot(
            "AAPL",
            self._snapshot(
                parameters=TechnicalAnalysisParameters(zone_tolerance_pct=0.02).as_mapping()
            ),
        )

        ausgabe = capsys.readouterr().out
        assert "Toleranz 2.00 %" in ausgabe
        assert "min. 2 Beruehrungen" in ausgabe

    def test_die_verfahrensversion_steht_an_jeder_ausgabe(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cli._print_technical_snapshot("AAPL", self._snapshot())

        assert TECHNICAL_ANALYSIS_VERSION in capsys.readouterr().out

    def test_symbole_werden_eingelesen(self) -> None:
        args = build_parser().parse_args(["technical", "--symbols", "AAPL,MSFT"])

        assert args.symbols == "AAPL,MSFT"
        assert args.provider is None

    def test_verweigert_den_lauf_wenn_der_anbieter_nicht_ibkr_ist(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Der Fixture-Anbieter kennt nur seine Kunstsymbole. Ohne diese
        Pruefung meldete das Kommando fuer jedes echte Symbol 'Nicht in der
        Watchlist gefunden' -- eine Meldung, die auf die Watchlist zeigt,
        waehrend der Anbieter das Problem ist."""
        config = write_config(projekt, provider="fixture")

        exit_code = main(["--config", str(config), "technical", "--symbols", "AAPL"])

        assert exit_code == 2
        fehler = capsys.readouterr().err
        assert "'fixture'" in fehler
        assert "Nicht in der Watchlist gefunden" not in fehler

    def test_die_globale_konfigurationsdatei_kommt_im_kommando_an(self) -> None:
        """Ein eigenes ``--config`` am Unterkommando ueberschreibt den
        globalen Wert mit ``None``: argparse kopiert *alle* Schluessel des
        Unterkommandos in den Hauptnamensraum, auch die ungesetzten
        Voreinstellungen. Der Lauf rechnete dann stillschweigend gegen die
        ausgelieferte ``config/default.yaml`` -- mit anderen Zonenparametern
        als angegeben."""
        parser = build_parser()
        pfad = "/tmp/meine.yaml"

        technical = parser.parse_args(["--config", pfad, "technical", "--symbols", "AAPL"])
        backtest = parser.parse_args(["--config", pfad, "backtest"])

        assert str(technical.config) == pfad
        assert technical.config == backtest.config

    def test_der_anbieter_kann_fuer_einen_lauf_uebersteuert_werden(self) -> None:
        args = build_parser().parse_args(
            ["technical", "--symbols", "AAPL", "--provider", "ibkr"]
        )

        assert args.provider == "ibkr"


class TestResearchKommando:
    def test_budget_kann_fuer_einen_probelauf_gedrueckt_werden(self) -> None:
        """Ein echter Lauf kostet Geld -- mit '--max-searches 1' laesst sich
        die Kette fuer wenige Cent pruefen (ADR 0023, "Kostenkontrolle")."""
        args = build_parser().parse_args(
            [
                "research",
                "--symbol",
                "AAPL",
                "--provider",
                "anthropic",
                "--max-searches",
                "1",
                "--max-fetches",
                "1",
            ]
        )
        assert args.max_searches == 1
        assert args.max_fetches == 1

    def test_ohne_ueberschreibung_bleibt_die_konfiguration_massgeblich(self) -> None:
        args = build_parser().parse_args(["research", "--symbol", "AAPL"])
        assert args.provider is None
        assert args.max_searches is None
        assert args.max_fetches is None

    def test_der_fixture_anbieter_laeuft_ohne_anthropic_zugang_durch(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Standard bleibt 'fixture' -- kein Kommandozeilenaufruf loest
        versehentlich einen kostenpflichtigen API-Aufruf aus."""
        config = write_config(projekt, provider="fixture")

        exit_code = main(["--config", str(config), "research", "--symbol", "aapl"])

        assert exit_code == 0
        assert "AAPL" in capsys.readouterr().out


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
    def test_ohne_angabe_entscheidet_die_konfiguration(self) -> None:
        """Wie ``--provider``: Das Argument uebersteuert, es setzt nicht.

        Sonst haette die Kommandozeile eine eigene Vorgabe, die von der der
        Anwendung abweicht -- und der Lauf, den der Nutzer zur Kontrolle
        startet, arbeitete anders als der regulaere.
        """
        assert build_parser().parse_args(["screen"]).source is None

    def test_der_bestand_laesst_sich_waehlen(self) -> None:
        assert build_parser().parse_args(["screen", "--source", "stored"]).source == "stored"

    def test_der_direkte_abruf_laesst_sich_waehlen(self) -> None:
        assert build_parser().parse_args(["screen", "--source", "live"]).source == "live"

    def test_die_konfiguration_wird_uebersteuert(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Konfiguration 'stored', Aufruf 'live': Der Lauf geht zur TWS."""
        monkeypatch.delenv("ATA_DATABASE_URL", raising=False)
        config = write_config(projekt, provider="ibkr", source="stored")

        main(["--config", str(config), "screen", "--source", "live", "--symbols", "AAPL"])

        # Ohne die Uebersteuerung waere hier die Datenbank verlangt worden.
        assert "TWS 127.0.0.1" in capsys.readouterr().out


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


class TestVollstaendigkeitDesLaufs:
    """Wann ein Analyse-Lauf dem Dispatcher als erledigt gilt.

    Der Lauf isoliert Fehler je Aktie und wirft nicht -- ohne diese Schwelle
    haette ein Abend, an dem die Verbindung nach der ersten Aktie abriss, als
    erledigt gegolten. Ein erledigter Lauf wird weder wiederholt noch nach
    Fristablauf gemeldet; der Handelstag waere still verlorengegangen.
    """

    @staticmethod
    def _zusammenfassung(gerechnet: int, gescheitert: int) -> AnalysisRunSummary:
        lauf_id = uuid.uuid4()
        run = AnalysisRun(
            id=lauf_id, status=RunStatus.COMPLETED, started_at=datetime.now(ZoneInfo("UTC"))
        )
        return AnalysisRunSummary(
            run=run,
            outcomes=tuple(_outcome(lauf_id, f"OK{nummer}") for nummer in range(gerechnet)),
            errors=tuple(
                StockProcessingError(
                    analysis_run_id=lauf_id,
                    stock_symbol=f"FEHLT{nummer}",
                    message="Fuer diese Aktie fehlen die Daten des laufenden Handelstages.",
                    occurred_at=datetime.now(ZoneInfo("UTC")),
                )
                for nummer in range(gescheitert)
            ),
        )

    def test_ein_vollstaendiger_lauf_geht_durch(self) -> None:
        require_complete_enough(self._zusammenfassung(192, 0), 0.9)

    def test_einzelne_ausfaelle_blockieren_den_tag_nicht(self) -> None:
        """Eine dauerhaft stumme Aktie darf nicht jeden Abend alles aufhalten."""
        require_complete_enough(self._zusammenfassung(188, 4), 0.9)

    def test_ein_abriss_nach_der_ersten_aktie_gilt_nicht_als_erledigt(self) -> None:
        with pytest.raises(MarketDataProviderError, match="1 von 192"):
            require_complete_enough(self._zusammenfassung(1, 191), 0.9)

    def test_knapp_unter_der_schwelle_ebenfalls_nicht(self) -> None:
        with pytest.raises(MarketDataProviderError):
            require_complete_enough(self._zusammenfassung(89, 11), 0.9)

    def test_ein_lauf_ganz_ohne_aktien_ist_kein_vollstaendiger(self) -> None:
        """Sonst waere ein leerer Lauf die bequemste Art, als erledigt zu gelten."""
        with pytest.raises(MarketDataProviderError):
            require_complete_enough(self._zusammenfassung(0, 0), 0.9)


class TestDispatchAnbieterUebersteuerung:
    """Der taegliche Lauf schaltet Earnings-Filter und Research Agent ueber
    Argumente scharf, nicht ueber die ausgelieferte Konfiguration.

    Beide stehen in ``config/default.yaml`` bewusst auf ``fixture``, damit
    Start und Tests ohne Zugangsdaten auskommen. Den produktiven Schalter
    traegt deshalb der Eintrag in der Aufgabenplanung -- so findet ein
    ``git pull`` auf dem Server keinen lokalen Diff vor, dieselbe Begruendung
    wie bei ``--provider ibkr``.

    Geprueft wird an der Stelle, an der die Anbieter gebaut werden: Dort
    liegen die Uebersteuerungen bereits an, und der Lauf hat weder TWS noch
    Datenbank angefasst.
    """

    @staticmethod
    def _spione(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
        """Faengt Notifier und Anbieter ab und meldet, was sie sahen.

        ``build_notifier`` laeuft im Handler zuerst, danach Earnings und
        Research; der Research-Anbieter bricht mit ``MissingSecretError`` ab
        -- der Weg, auf dem ``command_dispatch`` ohne Datenbank mit
        Rueckgabewert 2 endet.
        """
        gesehen: dict[str, str] = {}

        class _StummerEarningsProvider:
            def next_earnings_date(self, stock: Stock) -> NextEarningsDate | None:
                return None

        class _StummerNotifier:
            def send(self, subject: str, body: str) -> None:
                pass

        def notifier(config: NotificationsConfig, secrets: Secrets) -> Notifier:
            gesehen["notification_channel"] = config.channel
            if config.telegram.chat_id is not None:
                gesehen["telegram_chat_id"] = config.telegram.chat_id
            return _StummerNotifier()

        def earnings(config: AppConfig, secrets: Secrets) -> EarningsProvider:
            gesehen["earnings"] = config.earnings_filter.provider
            return _StummerEarningsProvider()

        def research(config: AppConfig, secrets: Secrets) -> ResearchProvider:
            gesehen["research"] = config.research.provider
            raise MissingSecretError("Abbruch fuer den Test")

        monkeypatch.setattr(cli, "build_notifier", notifier)
        monkeypatch.setattr(cli, "build_earnings_provider", earnings)
        monkeypatch.setattr(cli, "build_research_provider", research)
        return gesehen

    def test_ohne_argumente_bleibt_die_konfiguration_unberuehrt(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gesehen = self._spione(monkeypatch)
        config = write_config(projekt, provider="ibkr")

        assert main(["--config", str(config), "dispatch"]) == 2

        assert gesehen == {
            "notification_channel": "dry_run",
            "earnings": "fixture",
            "research": "fixture",
        }

    def test_das_argument_uebersteuert_den_benachrichtigungskanal(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gesehen = self._spione(monkeypatch)
        config = write_config(projekt, provider="ibkr")

        assert (
            main(
                [
                    "--config",
                    str(config),
                    "dispatch",
                    "--notification-channel",
                    "telegram",
                    "--telegram-chat-id",
                    "12345",
                ]
            )
            == 2
        )

        assert gesehen["notification_channel"] == "telegram"
        assert gesehen["telegram_chat_id"] == "12345"

    def test_die_chat_id_wirkt_auch_ohne_kanalwechsel(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Die Konfiguration kann bereits auf 'telegram' stehen -- dann
        uebersteuert nur die Chat-ID, ohne den Kanal erneut zu nennen."""
        gesehen = self._spione(monkeypatch)
        config = write_config(projekt, provider="ibkr")

        assert (
            main(["--config", str(config), "dispatch", "--telegram-chat-id", "999"]) == 2
        )

        assert gesehen["notification_channel"] == "dry_run"
        assert gesehen["telegram_chat_id"] == "999"

    def test_ein_unbekannter_kanal_wird_abgewiesen(self, projekt: Path) -> None:
        config = write_config(projekt, provider="ibkr")

        with pytest.raises(SystemExit) as abbruch:
            main(["--config", str(config), "dispatch", "--notification-channel", "pushover"])

        assert abbruch.value.code == 2

    def test_die_argumente_uebersteuern_beide_anbieter(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gesehen = self._spione(monkeypatch)
        config = write_config(projekt, provider="ibkr")

        assert (
            main(
                [
                    "--config",
                    str(config),
                    "dispatch",
                    "--earnings-provider",
                    "finnhub",
                    "--research-provider",
                    "anthropic",
                ]
            )
            == 2
        )

        assert gesehen == {
            "notification_channel": "dry_run",
            "earnings": "finnhub",
            "research": "anthropic",
        }

    def test_jedes_argument_wirkt_fuer_sich(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Der stufenweise Weg: erst Finnhub scharf, Research noch nicht."""
        gesehen = self._spione(monkeypatch)
        config = write_config(projekt, provider="ibkr")

        assert (
            main(["--config", str(config), "dispatch", "--earnings-provider", "finnhub"]) == 2
        )

        assert gesehen == {
            "notification_channel": "dry_run",
            "earnings": "finnhub",
            "research": "fixture",
        }

    def test_ein_unbekannter_anbieter_wird_abgewiesen(self, projekt: Path) -> None:
        """``model_copy(update=...)`` umgeht die Pydantic-Pruefung -- die
        Argumentliste ist deshalb die einzige Stelle, die einen Tippfehler
        noch abfaengt."""
        config = write_config(projekt, provider="ibkr")

        with pytest.raises(SystemExit) as abbruch:
            main(["--config", str(config), "dispatch", "--research-provider", "openai"])

        assert abbruch.value.code == 2
