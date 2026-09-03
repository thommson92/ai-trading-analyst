"""Die Kommandozeile fuer den manuellen Lauf.

Geprueft wird alles, was ohne TWS pruefbar ist: das Einlesen der Watchlist,
die Argumentbehandlung und die Verweigerung, wenn die Konfiguration gar nicht
auf IBKR steht. Der Abruf selbst braucht eine laufende TWS und ist
ausdruecklich nicht Gegenstand dieser Tests.
"""

from __future__ import annotations

import argparse
import csv
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest

from ai_trading_analyst import cli
from ai_trading_analyst.application.deepen_history import (
    DeepeningReport,
    DeepenOutcome,
    SymbolDeepening,
)
from ai_trading_analyst.cli import (
    _print_calendar_reach,
    _print_research_report,
    boersentag,
    build_parser,
    erforderliche_handelstage,
    export_bars_to_csv,
    main,
    require_complete_enough,
)
from ai_trading_analyst.config import AppConfig, MissingSecretError, NotificationsConfig, Secrets
from ai_trading_analyst.config.loader import LoadedConfig, load_config
from ai_trading_analyst.config.settings import IndicatorConfig
from ai_trading_analyst.domain.analysis import (
    AnalysisRun,
    AnalysisRunSummary,
    AnalystRecommendationsProvider,
    ContractSpec,
    EarningsProvider,
    FundamentalDataProvider,
    FundamentalDataProviderError,
    MarketDataProviderError,
    ResearchProvider,
    RunStatus,
    Stock,
    StockProcessingError,
    StockScreeningOutcome,
    TechnicalInterpreter,
)
from ai_trading_analyst.domain.earnings import NextEarningsDate
from ai_trading_analyst.domain.fundamentals import (
    FUNDAMENTAL_ANALYSIS_VERSION,
    FigureName,
    FundamentalSnapshot,
    FundamentalStatus,
    Metric,
    MetricBasis,
    MetricName,
    MetricUnit,
    SourceRef,
    TagConflict,
)
from ai_trading_analyst.domain.research import (
    Citation,
    ResearchCoverage,
    ResearchEvidence,
    ResearchReport,
    ResearchStatus,
    SourceLicenseClass,
    SourceRank,
)
from ai_trading_analyst.domain.scheduling import Notifier, TradingSession
from ai_trading_analyst.domain.screening import (
    SIGNAL_RULE_VERSION,
    Candle,
    CandleSeries,
    IndicatorParameters,
    IntradayBar,
    ScreeningResult,
    ScreeningStatus,
    compute_indicator_values,
)
from ai_trading_analyst.domain.technical import (
    TECHNICAL_ANALYSIS_VERSION,
    PriceZone,
    RiskRewardRating,
    TechnicalAnalysisParameters,
    TechnicalAssessment,
    TechnicalAssessmentStatus,
    TechnicalSnapshot,
    TechnicalStatus,
    TrendDirection,
    TrendStrength,
    ZoneKind,
    ZoneStrength,
)
from ai_trading_analyst.infrastructure.ibkr.calendar import parse_liquid_hours


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
    innerhalb der letzten sechs Kerzen. Das ergibt einen Kandidaten.

    Die Wende liegt bewusst **kurz** vor dem Ende: Seit ADR 0057 verlangt die
    Torbedingung der Frische ein Kaufsignal auf ``t`` oder ``t-1``. Bei einer
    laengeren Aufwaertsphase waeren die Kreuzungen am Entscheidungspunkt
    bereits abgelaufen.
    """
    return [300.0 - index for index in range(256)] + [50.0 + index * 25.0 for index in range(3)]


class _FakeEngine:
    """Haelt fest, ob die Verbindung freigegeben wurde.

    Der Kurslauf haengt vor einem minutenlangen EDGAR-Abruf; ein offener
    Pool ueberdauerte ihn ohne Grund.
    """

    def __init__(self) -> None:
        self.freigegeben = False

    def dispose(self) -> None:
        self.freigegeben = True


def _config_mit_ibkr_bestand() -> AppConfig:
    """Eine Konfiguration, die ``--price-from-bars`` durchlaesst.

    Ausgeliefert steht ``market_data.provider`` auf ``fixture``; der Schalter
    verlangt aber den ueber IBKR gefuellten Bestand.
    """
    basis = AppConfig(
        indicators=IndicatorConfig(
            rsi_length=14,
            rsi_method="wilder",
            rsi_ma_length=14,
            rsi_ma_type="sma",
            fast_ema_length=5,
            slow_ema_length=20,
            warmup_candles=250,
        )
    )
    return basis.model_copy(
        update={"market_data": basis.market_data.model_copy(update={"provider": "ibkr"})}
    )


def _loaded(config: AppConfig) -> LoadedConfig:
    return LoadedConfig(
        config=config, source_path=Path("config/default.yaml"), fingerprint="test"
    )


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
            Stock(id=uuid.uuid4(), symbol=symbol, exchange="NASDAQ") for symbol in self._symbole
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
        werte = [teil for teil in capsys.readouterr().out.split() if teil.startswith("EMA20=")]
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

    def test_chance_risiko_steht_in_der_ausgabe(self, capsys: pytest.CaptureFixture[str]) -> None:
        cli._print_technical_snapshot(
            "AAPL",
            self._snapshot(
                downside_to_support_pct=0.05,
                upside_to_resistance_pct=0.10,
                chance_risk_ratio=2.0,
            ),
        )

        ausgabe = capsys.readouterr().out
        assert "Bis zur naechsten Unterstuetzung: 5.00 %" in ausgabe
        assert "Bis zum naechsten Widerstand:     10.00 %" in ausgabe
        assert "Chance/Risiko:                   2.00" in ausgabe

    def test_fehlendes_chance_risiko_wird_nicht_als_null_ausgegeben(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Fehlt eine Seite, gibt es kein Verhaeltnis. Eine 0.00 an dieser
        Stelle laese sich als besonders schlechtes Setup lesen."""
        cli._print_technical_snapshot(
            "AAPL", self._snapshot(downside_to_support_pct=0.05, upside_to_resistance_pct=None)
        )

        ausgabe = capsys.readouterr().out
        assert "Chance/Risiko:                   -- (eine Seite ohne Zone)" in ausgabe
        assert "0.00" not in ausgabe.split("Chance/Risiko")[1]

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
        # Ueber ``Path`` gebildet statt als Literal: Windows normalisiert
        # Trennzeichen, ein fester POSIX-Pfad waere dort nie deckungsgleich.
        pfad = Path("tmp") / "meine.yaml"

        technical = parser.parse_args(["--config", str(pfad), "technical", "--symbols", "AAPL"])
        backtest = parser.parse_args(["--config", str(pfad), "backtest"])

        assert technical.config == pfad
        assert technical.config == backtest.config

    def test_ohne_interpret_bleibt_das_kommando_kostenfrei(self) -> None:
        args = build_parser().parse_args(["technical", "--symbols", "AAPL"])

        assert args.interpret is False
        assert args.agent_provider is None
        assert args.show_prompt is False

    def test_none_wird_als_agentenanbieter_angenommen(self) -> None:
        """'none' ist der ehrliche Aus-Schalter der beiden LLM-Agenten --
        auch in den Einzelproben, sonst liesse sich der abgeschaltete
        Zustand nicht pruefen."""
        technical = build_parser().parse_args(
            ["technical", "--symbols", "AAPL", "--interpret", "--agent-provider", "none"]
        )
        research = build_parser().parse_args(
            ["research", "--symbol", "AAPL", "--provider", "none"]
        )

        assert technical.agent_provider == "none"
        assert research.provider == "none"

    def test_der_agentenanbieter_ist_von_den_marktdaten_getrennt(self) -> None:
        """Zwei Bedeutungen an einem Flag waeren ein Bedienfehler mit
        Kostenfolge: '--provider' steuert die Marktdaten, '--agent-provider'
        das Sprachmodell."""
        args = build_parser().parse_args(
            [
                "technical",
                "--symbols",
                "AAPL",
                "--provider",
                "ibkr",
                "--interpret",
                "--agent-provider",
                "anthropic",
            ]
        )

        assert args.provider == "ibkr"
        assert args.agent_provider == "anthropic"
        assert args.interpret is True

    def test_die_einordnung_wird_ausgegeben(self, capsys: pytest.CaptureFixture[str]) -> None:
        cli._print_technical_assessment(
            "AAPL",
            TechnicalAssessment(
                status=TechnicalAssessmentStatus.COMPLETED,
                evaluated_at=datetime(2026, 8, 22, 12, 0, tzinfo=ZoneInfo("UTC")),
                model="claude-haiku-4-5-20251001",
                prompt_version="technical-agent-v1",
                trend_strength=TrendStrength.MODERATE,
                risk_reward_rating=RiskRewardRating.BALANCED,
                summary="Aufwaertstrend, Widerstand in Reichweite.",
                false_signal_risks=("Kurs dicht unter einer starken Zone",),
                confidence=0.6,
            ),
        )

        ausgabe = capsys.readouterr().out
        assert "COMPLETED" in ausgabe
        assert "claude-haiku-4-5-20251001" in ausgabe
        assert "MODERATE" in ausgabe
        assert "BALANCED" in ausgabe
        assert "Kurs dicht unter einer starken Zone" in ausgabe

    def test_die_berechnete_zahl_steht_neben_der_einstufung(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Ohne sie liesse sich nicht unterscheiden, ob das Verhaeltnis
        fehlte oder ob das Modell nichts dazu gesagt hat -- beim ersten Lauf
        gegen echte Kurse war Letzteres der Fall."""
        cli._print_technical_assessment(
            "AAPL",
            TechnicalAssessment(
                status=TechnicalAssessmentStatus.COMPLETED,
                evaluated_at=datetime(2026, 8, 22, 12, 0, tzinfo=ZoneInfo("UTC")),
                model="fixture",
                prompt_version="fixture-v1",
                trend_strength=TrendStrength.MODERATE,
                risk_reward_rating=None,
            ),
            self._snapshot(chance_risk_ratio=1.05),
        )

        ausgabe = capsys.readouterr().out
        assert "Chance/Risiko:           --  (berechnet: 1.05)" in ausgabe

    def test_die_verfahrensversion_steht_neben_der_promptversion(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Die eingeordneten Zahlen stammen aus einem bestimmten Stand der
        deterministischen Auswertung. Ohne ihn laesst sich eine Einordnung
        spaeter nicht dem Verfahren zuordnen, auf dem sie beruht -- derselbe
        Grund wie beim Research-Bericht."""
        cli._print_technical_assessment(
            "AAPL",
            TechnicalAssessment(
                status=TechnicalAssessmentStatus.COMPLETED,
                evaluated_at=datetime(2026, 8, 24, 12, 0, tzinfo=ZoneInfo("UTC")),
                model="claude-haiku-4-5-20251001",
                prompt_version="technical-agent-v3",
                interpreted_analysis_version="technical-analysis-v1",
                trend_strength=TrendStrength.MODERATE,
                risk_reward_rating=RiskRewardRating.BALANCED,
            ),
        )

        assert (
            "Prompt technical-agent-v3, Verfahren technical-analysis-v1"
        ) in capsys.readouterr().out

    def test_eine_einordnung_ohne_verfahrensversion_luegt_nicht(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Die Spalte ist nullable und wird nicht zurueckgerechnet.
        "unbekannt" ist die ehrliche Antwort, nicht die aktuelle Version."""
        cli._print_technical_assessment(
            "AAPL",
            TechnicalAssessment(
                status=TechnicalAssessmentStatus.COMPLETED,
                evaluated_at=datetime(2026, 8, 24, 12, 0, tzinfo=ZoneInfo("UTC")),
                model="claude-haiku-4-5-20251001",
                prompt_version="technical-agent-v1",
                trend_strength=TrendStrength.MODERATE,
                risk_reward_rating=RiskRewardRating.BALANCED,
            ),
        )

        assert "Verfahren unbekannt" in capsys.readouterr().out

    def test_ein_ausfall_zeigt_keine_leeren_stufen(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Bei UNAVAILABLE gibt es nichts zu zeigen -- eine Liste aus lauter
        '--' laese sich als Einordnung missverstehen."""
        cli._print_technical_assessment(
            "AAPL",
            TechnicalAssessment(
                status=TechnicalAssessmentStatus.UNAVAILABLE,
                evaluated_at=datetime(2026, 8, 22, 12, 0, tzinfo=ZoneInfo("UTC")),
                model=None,
                prompt_version=None,
                reason="provider_error",
            ),
        )

        ausgabe = capsys.readouterr().out
        assert "UNAVAILABLE" in ausgabe
        assert "provider_error" in ausgabe
        assert "Trendstaerke" not in ausgabe

    def test_der_anbieter_kann_fuer_einen_lauf_uebersteuert_werden(self) -> None:
        args = build_parser().parse_args(["technical", "--symbols", "AAPL", "--provider", "ibkr"])

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

        exit_code = main(["--config", str(config), "screen", "--source", "stored", "--no-pacing"])

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

        assert main(["--config", str(config), "dispatch", "--telegram-chat-id", "999"]) == 2

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

        assert main(["--config", str(config), "dispatch", "--earnings-provider", "finnhub"]) == 2

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

    @staticmethod
    def _spione_alle_sechs(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
        """Wie ``_spione``, aber der Abbruch liegt am **letzten** Anbieter,
        der vor dem Lauf gebaut wird.

        Nur so werden alle sichtbar: ``command_dispatch`` baut sie in fester
        Reihenfolge, und ``_spione`` steigt bereits beim Research Agent aus --
        die danach kaemen dort nie an. Kommt ein weiterer Anbieter hinzu, muss
        der Abbruch mitwandern, sonst prueft dieser Helfer den neuen
        stillschweigend nicht mit.

        Der Optionsanbieter ist die Ausnahme: Er entsteht erst im Lauf, weil
        er die bereits offene TWS-Anbindung braucht. Geprueft wird er
        deshalb an derselben Konfiguration, aus der auch die uebrigen fuenf
        gebaut werden -- das ist genau, was die Schleife der Uebersteuerungen
        zu leisten hat.
        """
        gesehen: dict[str, str] = {}

        class _StummerNotifier:
            def send(self, subject: str, body: str) -> None:
                pass

        class _StummerEarningsProvider:
            def next_earnings_date(self, stock: Stock) -> NextEarningsDate | None:
                return None

        def earnings(config: AppConfig, secrets: Secrets) -> EarningsProvider:
            gesehen["earnings"] = config.earnings_filter.provider
            return _StummerEarningsProvider()

        def research(config: AppConfig, secrets: Secrets) -> ResearchProvider:
            gesehen["research"] = config.research.provider
            return cast(ResearchProvider, object())

        def technical(config: AppConfig, secrets: Secrets) -> TechnicalInterpreter:
            gesehen["technical_agent"] = config.technical_agent.provider
            return cast(TechnicalInterpreter, object())

        def fundamental(config: AppConfig, secrets: Secrets) -> FundamentalDataProvider:
            gesehen["fundamentals"] = config.fundamentals.provider
            return cast(FundamentalDataProvider, object())

        def ratings(config: AppConfig, secrets: Secrets) -> AnalystRecommendationsProvider:
            gesehen["analyst_ratings"] = config.analyst_ratings.provider
            gesehen["options"] = config.options.provider
            raise MissingSecretError("Abbruch fuer den Test")

        monkeypatch.setattr(
            cli, "build_notifier", lambda _config, _secrets: _StummerNotifier()
        )
        monkeypatch.setattr(cli, "build_earnings_provider", earnings)
        monkeypatch.setattr(cli, "build_research_provider", research)
        monkeypatch.setattr(cli, "build_technical_interpreter", technical)
        monkeypatch.setattr(cli, "build_fundamental_data_provider", fundamental)
        monkeypatch.setattr(cli, "build_analyst_recommendations_provider", ratings)
        return gesehen

    def test_ohne_argumente_bleiben_alle_fuenf_auf_fixture(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Der ausgelieferte Zustand: kein Zugangsdatum noetig, nichts kostet
        Geld -- und nichts davon ist ein Ergebnis."""
        gesehen = self._spione_alle_sechs(monkeypatch)
        config = write_config(projekt, provider="ibkr")

        assert main(["--config", str(config), "dispatch"]) == 2

        assert gesehen == {
            "earnings": "fixture",
            "research": "fixture",
            "technical_agent": "fixture",
            "fundamentals": "fixture",
            "analyst_ratings": "fixture",
            "options": "fixture",
        }

    def test_die_argumente_uebersteuern_alle_anbieter(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ohne einen Schalter je Anbieter bliebe sein Abschnitt im Bericht auf
        den Fixture-Werten stehen -- und die sehen dort wie ein Ergebnis aus,
        nicht wie eine Luecke. Der Ausweg waere, config/default.yaml auf dem
        Server zu editieren; genau das schliesst Doc 14 aus."""
        gesehen = self._spione_alle_sechs(monkeypatch)
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
                    "--fundamentals-provider",
                    "edgar",
                    "--technical-agent-provider",
                    "anthropic",
                    "--ratings-provider",
                    "finnhub",
                    "--options-provider",
                    "ibkr",
                ]
            )
            == 2
        )

        assert gesehen == {
            "earnings": "finnhub",
            "research": "anthropic",
            "technical_agent": "anthropic",
            "fundamentals": "edgar",
            "analyst_ratings": "finnhub",
            "options": "ibkr",
        }

    @pytest.mark.parametrize(
        ("schalter", "wert", "abschnitt"),
        [
            ("--earnings-provider", "finnhub", "earnings"),
            ("--research-provider", "anthropic", "research"),
            ("--research-provider", "none", "research"),
            ("--technical-agent-provider", "anthropic", "technical_agent"),
            ("--technical-agent-provider", "none", "technical_agent"),
            ("--fundamentals-provider", "edgar", "fundamentals"),
            ("--ratings-provider", "finnhub", "analyst_ratings"),
            ("--options-provider", "ibkr", "options"),
        ],
    )
    def test_jeder_schalter_wirkt_fuer_sich(
        self,
        projekt: Path,
        monkeypatch: pytest.MonkeyPatch,
        schalter: str,
        wert: str,
        abschnitt: str,
    ) -> None:
        """Ein Schalter darf die uebrigen Abschnitte nicht mitverstellen --
        ``model_copy`` je Abschnitt, nicht ein gemeinsames Update."""
        gesehen = self._spione_alle_sechs(monkeypatch)
        config = write_config(projekt, provider="ibkr")

        assert main(["--config", str(config), "dispatch", schalter, wert]) == 2

        erwartet = dict.fromkeys(
            (
                "earnings",
                "research",
                "technical_agent",
                "fundamentals",
                "analyst_ratings",
                "options",
            ),
            "fixture",
        )
        erwartet[abschnitt] = wert
        assert gesehen == erwartet

    @pytest.mark.parametrize(
        ("schalter", "wert"),
        [
            ("--fundamentals-provider", "anthropic"),
            ("--technical-agent-provider", "edgar"),
            ("--ratings-provider", "edgar"),
            ("--earnings-provider", "anthropic"),
            ("--options-provider", "finnhub"),
            ("--earnings-provider", "none"),
            ("--fundamentals-provider", "none"),
            ("--ratings-provider", "none"),
            ("--options-provider", "none"),
        ],
    )
    def test_ein_anbieter_aus_dem_falschen_abschnitt_wird_abgewiesen(
        self, projekt: Path, schalter: str, wert: str
    ) -> None:
        """Sechs Schalter mit ueberlappenden Wertemengen -- 'finnhub' passt zu
        zweien, 'anthropic' zu zweien, 'ibkr' zu keinem anderen. Ein
        Vertauschen faellt beim Argument auf, nicht erst am Anbieter.
        'none' gibt es nur bei den zwei LLM-Agenten: Fuer die uebrigen vier
        waere ein abgeschalteter Anbieter ein Lauf ohne seine Pflichtdaten."""
        config = write_config(projekt, provider="ibkr")

        with pytest.raises(SystemExit) as abbruch:
            main(["--config", str(config), "dispatch", schalter, wert])

        assert abbruch.value.code == 2


class TestDispatchFruehabbruch:
    """Ein fehlendes Geheimnis muss **vor** dem Backfill auffallen.

    Der Backfill laeuft rund eine halbe Stunde ueber die volle Watchliste.
    Dahinter bemerkt, haette der Abbruch all das weggeworfen -- und der Lauf
    saehe nach "die TWS laeuft nicht" aus statt nach einem
    Konfigurationsfehler. ``command_dispatch`` baut die Anbieter deshalb
    vorher; diese Klasse haelt fest, dass der Fundamentalanbieter dazugehoert.
    """

    @staticmethod
    def _anbieter_ohne_abbruch(monkeypatch: pytest.MonkeyPatch) -> None:
        """Alle Anbieter ausser dem fundamentalen kommen durch."""

        class _StummerEarningsProvider:
            def next_earnings_date(self, stock: Stock) -> NextEarningsDate | None:
                return None

        class _StummerNotifier:
            def send(self, subject: str, body: str) -> None:
                pass

        monkeypatch.setattr(
            cli, "build_notifier", lambda _config, _secrets: _StummerNotifier()
        )
        monkeypatch.setattr(
            cli, "build_earnings_provider", lambda _config, _secrets: _StummerEarningsProvider()
        )
        monkeypatch.setattr(cli, "build_research_provider", lambda _config, _secrets: object())
        monkeypatch.setattr(cli, "build_technical_interpreter", lambda _config, _secrets: object())

    def test_die_fehlende_edgar_kontaktadresse_faellt_vor_dem_backfill_auf(
        self,
        projekt: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._anbieter_ohne_abbruch(monkeypatch)
        # Leer zaehlt als nicht gesetzt -- und uebersteuert zugleich eine
        # etwaige .env des Entwicklungsrechners.
        monkeypatch.setenv("ATA_EDGAR_CONTACT", "")

        def nie() -> None:
            raise AssertionError("Der Lauf ist zu weit gekommen: Datenbank geoeffnet")

        monkeypatch.setattr(cli, "_open_database", nie)

        config = write_config(projekt, provider="ibkr")
        config.write_text(
            config.read_text(encoding="utf-8") + "\nfundamentals:\n  provider: edgar\n",
            encoding="utf-8",
        )

        assert main(["--config", str(config), "dispatch"]) == 2
        assert "ATA_EDGAR_CONTACT" in capsys.readouterr().err


class TestHistoryDepthKommando:
    """Die Tiefenmessung fuer E2 ([ADR 0027]).

    Das einzige Kommando gegen die TWS, das **nichts** ablegt -- und deshalb
    als einziges ohne Datenbank auskommt. Der Abruf selbst braucht eine
    laufende TWS und ist hier nicht Gegenstand; geprueft wird der Rahmen.
    """

    def test_ohne_provider_meldet_es_die_ausgelieferte_einstellung(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = write_config(projekt, provider="fixture")

        assert main(["--config", str(config), "history-depth", "--symbols", "AAPL"]) == 2
        assert "--provider ibkr" in capsys.readouterr().err

    def test_es_braucht_keine_datenbank(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Ohne ``ATA_DATABASE_URL`` scheitert ``backfill`` mit 2.

        Die Messung laeuft weiter bis zur TWS -- die hier nicht erreichbar
        ist, weshalb der Fehler von dort kommt und nicht von der Datenbank.
        """
        monkeypatch.delenv("ATA_DATABASE_URL", raising=False)
        config = write_config(projekt, provider="ibkr")

        code = main(
            [
                "--config",
                str(config),
                "history-depth",
                "--symbols",
                "AAPL",
                "--max-windows",
                "1",
                "--no-pacing",
            ]
        )

        ausgabe = capsys.readouterr()
        assert code == 1
        assert "Datenbank" not in ausgabe.err
        assert "Keine Verbindung zur TWS" in ausgabe.out

    def test_ein_ausfall_wird_als_untergrenze_ausgewiesen(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Ohne TWS gibt es kein Ergebnis -- und der Bericht behauptet keines."""
        config = write_config(projekt, provider="ibkr")

        main(
            [
                "--config",
                str(config),
                "history-depth",
                "--symbols",
                "AAPL",
                "--max-windows",
                "1",
                "--no-pacing",
            ]
        )

        ausgabe = capsys.readouterr().out
        assert "Keine einzige Aktie hat Bars geliefert" in ausgabe
        assert "Jahre" not in ausgabe.split("Keine einzige Aktie")[1]

    def test_ohne_abstand_begrenzt_die_zahl_der_anfragen_den_lauf(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Nicht die Zahl der Symbole entscheidet, sondern Symbole mal Fenster.

        Drei Aktien sind harmlos -- drei Aktien mal zwoelf Fenster sind 36
        Anfragen und damit ueber der Grenze, ab der IBKR sperrt.
        """
        config = write_config(projekt, provider="ibkr")

        code = main(["--config", str(config), "history-depth", "--no-pacing"])

        assert code == 2
        assert "bis zu" in capsys.readouterr().err

    def test_die_argumente_werden_eingelesen(self) -> None:
        args = build_parser().parse_args(
            ["history-depth", "--symbols", "AAPL,MSFT", "--window-days", "90", "--max-windows", "4"]
        )
        assert args.symbols == "AAPL,MSFT"
        assert args.window_days == 90
        assert args.max_windows == 4

    def test_ohne_angabe_kuerzt_das_kommando_selbst(self) -> None:
        """Die Kuerzung auf drei Titel liegt bewusst **nicht** im Argument.

        Als Argumentstandard traefe sie auch ausdruecklich genannte Symbole
        -- ``--symbols A,B,C,D`` maesse dann stillschweigend nur drei. Die
        Watchlist zu kuerzen ist Sache des Kommandos, das beides
        unterscheiden kann.
        """
        assert build_parser().parse_args(["history-depth"]).limit is None
        assert cli.STANDARD_TITEL_TIEFENMESSUNG == 3


class TestExportBarsKommando:
    """Zieht einen echten Datenausschnitt aus dem Bestand (Golden Master, M5).

    Liest nur. Der Bestand selbst braucht eine Datenbank und ist Gegenstand
    der Integrationstests; hier geht es um den Rahmen.
    """

    def test_ohne_datenbankadresse_meldet_es_sich_verstaendlich(
        self,
        projekt: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("ATA_DATABASE_URL", raising=False)
        config = write_config(projekt, provider="ibkr")

        code = main(
            [
                "--config",
                str(config),
                "export-bars",
                "--symbols",
                "AAPL",
                "--output",
                str(tmp_path),
            ]
        )

        assert code == 2
        assert "Datenbank" in capsys.readouterr().err

    def test_ein_fehlendes_zielverzeichnis_faellt_vor_der_datenbank_auf(
        self, projekt: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Sonst faende der Nutzer den Fehler erst nach dem Abruf."""
        config = write_config(projekt, provider="ibkr")

        code = main(
            [
                "--config",
                str(config),
                "export-bars",
                "--symbols",
                "AAPL",
                "--output",
                str(tmp_path / "gibtesnicht"),
            ]
        )

        assert code == 2
        assert "kein Verzeichnis" in capsys.readouterr().err

    def test_eine_leere_symbolliste_wird_abgelehnt(
        self, projekt: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = write_config(projekt, provider="ibkr")

        code = main(
            ["--config", str(config), "export-bars", "--symbols", ",", "--output", str(tmp_path)]
        )

        assert code == 2
        assert "kein Symbol" in capsys.readouterr().err

    def test_die_argumente_werden_eingelesen(self) -> None:
        args = build_parser().parse_args(
            ["export-bars", "--symbols", "AAPL", "--output", ".", "--since", "2025-01-02"]
        )
        assert args.symbols == "AAPL"
        assert args.since is not None and args.since.isoformat() == "2025-01-02"


class TestTiefenmessungNachDerReview:
    """Zwei Punkte aus der unabhaengigen Review zu diesem Zweig."""

    def test_ausdruecklich_genannte_symbole_werden_nicht_gekuerzt(self) -> None:
        """Sonst entschiede eine stille Kuerzung mit, welche Aktie am Ende
        die 'flachste Historie' des Berichts stellt -- und ADR 0027 macht
        genau die zur massgeblichen Groesse fuer E2."""
        args = build_parser().parse_args(["history-depth", "--symbols", "A,B,C,D"])

        assert args.limit is None

    def test_limit_bleibt_angebbar(self) -> None:
        args = build_parser().parse_args(["history-depth", "--limit", "2"])

        assert args.limit == 2

    def test_ohne_symbole_wird_die_watchlist_gekuerzt(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Die volle Watchlist kostete unter Pacing Stunden."""
        symbols = ",".join(f"NASDAQ:SYM{index}" for index in range(25))
        (projekt / "watchlists" / "test.txt").write_text(symbols, encoding="utf-8")
        config = write_config(projekt, provider="ibkr")

        main(["--config", str(config), "history-depth", "--max-windows", "1"])

        assert "3 Aktien" in capsys.readouterr().out


class TestExportBarsSchreiben:
    """``export_bars_to_csv`` -- erst filtern, dann auf Leere pruefen.

    Andersherum entstuende bei einem Zeitraum ohne Bars eine Datei mit
    nichts als der Kopfzeile. Der Golden Master naehme sie als Fall an und
    scheiterte an der leeren Kerzenreihe.
    """

    @staticmethod
    def _bar(start: datetime) -> IntradayBar:
        return IntradayBar(start=start, open=1.0, high=2.0, low=0.5, close=1.5, volume=100.0)

    def _bars(self) -> list[IntradayBar]:
        basis = datetime(2025, 6, 2, 13, 30, tzinfo=ZoneInfo("UTC"))
        return [self._bar(basis + timedelta(minutes=15 * index)) for index in range(4)]

    def test_ein_leerer_zeitraum_legt_keine_datei_an(self, tmp_path: Path) -> None:
        ergebnis = export_bars_to_csv(tmp_path, "AAPL", self._bars(), date(2026, 1, 1))

        assert ergebnis is None
        assert list(tmp_path.iterdir()) == []

    def test_ein_leerer_bestand_legt_keine_datei_an(self, tmp_path: Path) -> None:
        assert export_bars_to_csv(tmp_path, "AAPL", [], None) is None
        assert list(tmp_path.iterdir()) == []

    def test_die_datei_traegt_kopfzeile_und_alle_bars(self, tmp_path: Path) -> None:
        datei = export_bars_to_csv(tmp_path, "AAPL", self._bars(), None)

        assert datei is not None and datei.name == "aapl.bars.csv"
        zeilen = datei.read_text(encoding="utf-8").splitlines()
        assert zeilen[0] == "start,open,high,low,close,volume"
        assert len(zeilen) == 5

    def test_since_schneidet_aeltere_bars_ab(self, tmp_path: Path) -> None:
        datei = export_bars_to_csv(tmp_path, "AAPL", self._bars(), date(2025, 6, 2))

        assert datei is not None
        assert len(datei.read_text(encoding="utf-8").splitlines()) == 5

    def test_das_format_liest_der_golden_master_wieder_ein(self, tmp_path: Path) -> None:
        """Sonst waere der Weg 'Server-Ausschnitt in den Golden Master' offen
        beschrieben, aber nirgends belegt."""
        from tests.golden.pipeline import read_bars

        datei = export_bars_to_csv(tmp_path, "AAPL", self._bars(), None)

        assert datei is not None
        assert read_bars(datei) == tuple(self._bars())


class TestDeepenHistoryKommando:
    """Der einmalige Tiefen-Backfill (ADR 0028).

    Legt ab und braucht deshalb eine Datenbank. Der Abruf selbst braucht die
    TWS und ist hier nicht Gegenstand.
    """

    def test_ohne_provider_meldet_es_die_ausgelieferte_einstellung(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = write_config(projekt, provider="fixture")

        assert main(["--config", str(config), "deepen-history", "--symbols", "AAPL"]) == 2
        assert "--provider ibkr" in capsys.readouterr().err

    def test_ohne_datenbankadresse_meldet_es_sich_verstaendlich(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("ATA_DATABASE_URL", raising=False)
        config = write_config(projekt, provider="ibkr")

        assert main(["--config", str(config), "deepen-history", "--symbols", "AAPL"]) == 2
        assert "Datenbank" in capsys.readouterr().err

    def test_eine_leere_symbolliste_wird_abgelehnt(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = write_config(projekt, provider="ibkr")

        assert main(["--config", str(config), "deepen-history", "--symbols", ","]) == 2
        assert "kein Symbol" in capsys.readouterr().err

    def test_die_argumente_werden_eingelesen(self) -> None:
        args = build_parser().parse_args(
            ["deepen-history", "--symbols", "AAPL", "--years", "3", "--window-days", "200"]
        )
        assert args.symbols == "AAPL"
        assert args.years == 3
        assert args.window_days == 200

    def test_ohne_years_entscheidet_die_konfiguration(self) -> None:
        """Wie ``--provider``: Das Argument uebersteuert, es setzt nicht.

        Sonst haette die Kommandozeile eine eigene Zieltiefe, die von
        backtesting.history_years abweichen koennte -- und der Bestand
        entspraeche nicht dem, was die Kennzahlen unterstellen.
        """
        assert build_parser().parse_args(["deepen-history"]).years is None

    def test_das_fenster_zaehlt_in_handelstagen(self) -> None:
        assert build_parser().parse_args(["deepen-history"]).window_days == 365


class TestLaufzeitschaetzung:
    """Die erste Fassung zaehlte nur die Pacing-Pausen und versprach sieben
    Minuten fuer einen Lauf, der zwanzig brauchte."""

    def test_die_uebertragung_zaehlt_mit(self) -> None:
        nur_pacing = 36 * 11 / 60

        text = cli._laufzeitschaetzung(36, 11.0)

        gemeldet = float(text.split("grob ")[1].split(" ")[0])
        assert gemeldet > nur_pacing * 2

    def test_lange_laeufe_erscheinen_in_stunden(self) -> None:
        """760 Anfragen in Minuten waeren eine unlesbare Zahl."""
        text = cli._laufzeitschaetzung(760, 11.0)

        assert "Stunden" in text

    def test_kurze_laeufe_bleiben_in_minuten(self) -> None:
        assert "Minuten" in cli._laufzeitschaetzung(5, 11.0)


class TestBilanzDesTiefenBackfills:
    """Die Schlusszeile darf nicht mehr behaupten, als der Lauf weiss."""

    @staticmethod
    def _ergebnis(symbol: str, outcome: DeepenOutcome, **kwargs: object) -> SymbolDeepening:
        return SymbolDeepening(symbol=symbol, outcome=outcome, **kwargs)  # type: ignore[arg-type]

    def _bilanz(self, *ergebnisse: SymbolDeepening) -> str:
        import io
        from contextlib import redirect_stdout

        puffer = io.StringIO()
        with redirect_stdout(puffer):
            cli._print_deepen_report(
                DeepeningReport(target_years=5, results=ergebnisse),
                datetime(2026, 8, 23, tzinfo=ZoneInfo("UTC")),
                dauer=60.0,
            )
        return puffer.getvalue()

    def test_ohne_fehler_und_ohne_kurze_meldet_sie_vollstaendigkeit(self) -> None:
        ausgabe = self._bilanz(
            self._ergebnis("AAPL", DeepenOutcome.TARGET_REACHED),
            self._ergebnis("MSFT", DeepenOutcome.ALREADY_DEEP_ENOUGH),
        )

        assert "Alle Aktien decken 5 Jahre ab." in ausgabe

    def test_ein_ausfall_verhindert_die_vollstaendigkeitsaussage(self) -> None:
        """Steht die TWS still, ist ueber die betroffenen Aktien nichts
        bekannt -- ein 'alle decken ab' stuende unmittelbar unter der Liste
        der Fehlschlaege und widerspraeche ihr."""
        ausgabe = self._bilanz(
            self._ergebnis("AAPL", DeepenOutcome.TARGET_REACHED),
            self._ergebnis("MSFT", DeepenOutcome.ERROR, error="RuntimeError: TWS weg"),
        )

        assert "Alle Aktien decken" not in ausgabe
        assert "durchgelaufenen" in ausgabe
        assert "sagt der Lauf nichts" in ausgabe

    def test_auch_wenn_jede_einzelne_aktie_ausfaellt(self) -> None:
        ausgabe = self._bilanz(
            self._ergebnis("AAPL", DeepenOutcome.ERROR, error="RuntimeError: TWS weg"),
            self._ergebnis("MSFT", DeepenOutcome.ERROR, error="RuntimeError: TWS weg"),
        )

        assert "Alle Aktien decken" not in ausgabe

    def test_eine_zu_kurze_aktie_erscheint_namentlich(self) -> None:
        ausgabe = self._bilanz(
            self._ergebnis("AAPL", DeepenOutcome.TARGET_REACHED),
            self._ergebnis(
                "NEU",
                DeepenOutcome.PROVIDER_EXHAUSTED,
                earliest_after=datetime(2025, 8, 23, tzinfo=ZoneInfo("UTC")),
            ),
        )

        assert "Unter dem Zielzeitraum (1)" in ausgabe
        assert "NEU" in ausgabe
        assert "Neuemission" in ausgabe
        assert "Alle Aktien decken" not in ausgabe


class TestResearchAusgabe:
    """Die neuen Zeilen aus ADR 0029 waren bisher nur ausgefuehrt, nicht
    geprueft -- ein Smoke-Test, der nur das Symbol sucht, laesst sie
    stillschweigend verschwinden."""

    def test_abdeckung_belege_und_rang_stehen_in_der_ausgabe(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        report = ResearchReport(
            status=ResearchStatus.COMPLETED,
            evaluated_at=datetime(2026, 8, 23, tzinfo=UTC),
            model="claude-sonnet-5",
            prompt_version="research-v2",
            analysis_version="research-analysis-v1",
            summary="Zusammenfassung",
            confidence=0.6,
            coverage=ResearchCoverage.LIMITED,
            evidence=ResearchEvidence(
                distinct_sources=2,
                successful_fetches=1,
                rejected_tool_calls=3,
                dropped_citations=4,
            ),
            citations=(
                Citation(
                    url="https://sec.gov/filing",
                    title="10-Q",
                    retrieved_at=datetime(2026, 8, 23, tzinfo=UTC),
                    cited_text=None,
                    license_class=SourceLicenseClass.PRIMARY_SOURCE,
                    transformation="zusammengefasst",
                    source_rank=SourceRank.REGULATORY,
                    source_age="3 days ago",
                ),
            ),
        )

        _print_research_report("AAPL", report)

        ausgabe = capsys.readouterr().out
        assert "Abdeckung: LIMITED" in ausgabe
        assert "2 Quellen" in ausgabe
        assert "1 Abrufe" in ausgabe
        assert "3 abgelehnte Werkzeugaufrufe" in ausgabe
        assert "4 verworfene Zitate" in ausgabe
        assert "[REGULATORY / PRIMARY_SOURCE]" in ausgabe
        assert "Alter laut Anbieter: 3 days ago" in ausgabe

    def test_beide_versionen_stehen_in_der_ausgabe(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Prompt- und Verfahrensversion aendern sich unabhaengig voneinander.

        Die Abdeckungsstufe entsteht aus der Verfahrensversion; ohne sie
        laesst sich ein gemeldetes BROAD nicht der Regel zuordnen, unter der
        es entstanden ist. Ein Serverlauf zeigte genau diese Luecke: Er meldete
        research-v2, aber nichts darueber, nach welcher Abdeckungsregel
        gerechnet wurde.
        """
        report = ResearchReport(
            status=ResearchStatus.COMPLETED,
            evaluated_at=datetime(2026, 8, 24, tzinfo=UTC),
            model="claude-sonnet-5",
            prompt_version="research-v2",
            analysis_version="research-analysis-v2",
            summary="Zusammenfassung",
        )

        _print_research_report("AAPL", report)

        assert (
            "Modell: claude-sonnet-5 (Prompt-Version research-v2, "
            "Verfahren research-analysis-v2)"
        ) in capsys.readouterr().out

    def test_ein_bericht_ohne_verfahrensversion_luegt_nicht(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Alte Berichte werden nicht zurueckgerechnet und haben keine.
        "unbekannt" ist die ehrliche Antwort, nicht die aktuelle Version."""
        report = ResearchReport(
            status=ResearchStatus.COMPLETED,
            evaluated_at=datetime(2026, 8, 24, tzinfo=UTC),
            model="claude-sonnet-5",
            prompt_version="research-v1",
            summary="Zusammenfassung",
        )

        _print_research_report("AAPL", report)

        assert "Verfahren unbekannt" in capsys.readouterr().out


def _wirft_oserror(*_args: object, **_kwargs: object) -> None:
    raise OSError(13, "Zugriff verweigert")


class _KeinAbrufProvider:
    """Meldet fuer jedes Symbol einen Ausfall -- ohne Netz."""

    def fundamentals(self, stock: object, price: float | None = None) -> object:
        raise FundamentalDataProviderError(f"kein Netz im Test ({stock!r}, {price!r})")


def _kein_provider(_config: object, _secrets: object) -> _KeinAbrufProvider:
    return _KeinAbrufProvider()


class TestFundamentalKommando:
    """Ausgabe der deterministischen Fundamentalanalyse (ADR 0032)."""

    def _snapshot(self, **kwargs: object) -> FundamentalSnapshot:
        quelle = SourceRef(
            cik=42, accession="0000000042-25-000001", form="10-K",
            filed=date(2025, 2, 1), tag="Revenues",
        )
        metric = Metric(
            name=MetricName.NET_MARGIN, value=0.25, unit=MetricUnit.FRACTION,
            basis=MetricBasis.TRAILING_TWELVE_MONTHS,
            period_end=date(2024, 12, 31), sources=(quelle,),
            retrieved_at=datetime(2026, 8, 24, tzinfo=UTC),
        )
        vorgabe: dict[str, object] = {
            "symbol": "TEST",
            "status": FundamentalStatus.COMPLETED,
            "evaluated_at": datetime(2026, 8, 24, tzinfo=UTC),
            "metrics": {MetricName.NET_MARGIN: metric},
            "fiscal_years": (2022, 2023, 2024),
        }
        return FundamentalSnapshot(**(vorgabe | kwargs))  # type: ignore[arg-type]

    def test_der_anteil_wird_als_prozent_gezeigt(self, capsys: pytest.CaptureFixture[str]) -> None:
        """FRACTION und RATIO sind getrennte Einheiten: Eine Marge von 0,25
        heisst 25 Prozent, ein KGV von 0,25 heisst 0,25."""
        cli._print_fundamental_snapshot(self._snapshot())
        assert "25.00%" in capsys.readouterr().out

    def test_fehlende_kennzahlen_werden_aufgezaehlt(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Ein Bericht, aus dem eine Kennzahl still verschwindet, sieht aus
        wie einer, in dem sie nie vorgesehen war (CLAUDE.md)."""
        cli._print_fundamental_snapshot(self._snapshot())
        ausgabe = capsys.readouterr().out
        assert "Nicht verfuegbar:" in ausgabe
        assert MetricName.REVENUE.value in ausgabe

    def test_ohne_kurs_sagt_die_ausgabe_warum_die_bewertung_fehlt(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cli._print_fundamental_snapshot(self._snapshot())
        assert "Kurs: nicht uebergeben" in capsys.readouterr().out

    def test_mit_kurs_steht_er_in_der_ausgabe(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Ohne ihn liesse sich eine Bewertungskennzahl spaeter nicht mehr
        nachrechnen."""
        cli._print_fundamental_snapshot(self._snapshot(price_used=232.14))
        assert "Kurs: 232.14" in capsys.readouterr().out

    def test_ein_widerspruch_wird_gezeigt_statt_verschwiegen(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        konflikt = TagConflict(
            figure=FigureName.REVENUE, period_end=date(2024, 12, 31),
            chosen_tag="Revenues", chosen_value=1000.0,
            other_tag="RevenueFromContractWithCustomerExcludingAssessedTax", other_value=560.0,
        )
        cli._print_fundamental_snapshot(self._snapshot(tag_conflicts=(konflikt,)))
        ausgabe = capsys.readouterr().out
        assert "WIDERSPRUCH REVENUE" in ausgabe
        assert "44.0%" in ausgabe

    def test_die_verfahrensversion_steht_in_der_ausgabe(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cli._print_fundamental_snapshot(self._snapshot())
        assert FUNDAMENTAL_ANALYSIS_VERSION in capsys.readouterr().out

    def test_der_unterbefehl_kennt_den_optionalen_kurs(self) -> None:
        args = build_parser().parse_args(
            ["fundamental", "--symbols", "AAPL", "--price", "232.14", "--provider", "edgar"]
        )
        assert args.symbols == "AAPL"
        assert args.price == pytest.approx(232.14)
        assert args.provider == "edgar"

    def test_ein_kurs_fuer_mehrere_symbole_wird_abgelehnt(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Er bewertete sonst jedes Papier zum Kurs des ersten -- und das
        Kommando existiert gerade zum Gegenpruefen."""
        args = build_parser().parse_args(
            ["fundamental", "--symbols", "AAPL,NVDA", "--price", "232.14"]
        )
        assert cli.command_fundamental(args) == 2
        assert "--price gilt fuer ein Symbol" in capsys.readouterr().err

    def test_kurs_von_hand_und_kurs_aus_dem_bestand_schliessen_sich_aus(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        args = build_parser().parse_args(
            ["fundamental", "--symbols", "AAPL", "--price", "232.14", "--price-from-bars"]
        )
        assert cli.command_fundamental(args) == 2
        assert "schliessen sich aus" in capsys.readouterr().err

    def test_der_marktdatenschalter_macht_den_bestand_erreichbar(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Auf dem Server bleibt ``config/default.yaml`` unveraendert, damit
        ``git pull`` keinen lokalen Diff vorfindet -- produktive Quellen
        werden ueber Schalter gesetzt. Ohne diesen Weg waere
        ``--price-from-bars`` dort nicht benutzbar.

        Der Schalter heisst ``--market-data-provider``, weil ``--provider``
        bei diesem Unterbefehl schon die Fundamentalquelle uebersteuert.
        """
        gesehen: dict[str, str] = {}

        def merken(loaded: object, config: AppConfig, wanted: object) -> None:
            gesehen["provider"] = config.market_data.provider
            return None

        monkeypatch.setattr(cli, "_kurse_aus_dem_bestand", merken)
        args = build_parser().parse_args(
            [
                "fundamental", "--symbols", "AAPL", "--price-from-bars",
                "--market-data-provider", "ibkr",
            ]
        )
        cli.command_fundamental(args)

        assert gesehen["provider"] == "ibkr"

    def test_ohne_den_marktdatenschalter_bleibt_die_konfiguration_stehen(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Der Schalter uebersteuert nur, wenn er gesetzt ist -- sonst
        stuende die Quelle des Laufs nicht mehr in der Konfiguration."""
        gesehen: dict[str, str] = {}

        def merken(loaded: object, config: AppConfig, wanted: object) -> None:
            gesehen["provider"] = config.market_data.provider
            return None

        monkeypatch.setattr(cli, "_kurse_aus_dem_bestand", merken)
        args = build_parser().parse_args(
            ["fundamental", "--symbols", "AAPL", "--price-from-bars"]
        )
        cli.command_fundamental(args)

        assert gesehen["provider"] == "fixture"

    def test_kurse_aus_dem_bestand_brauchen_den_ibkr_bestand(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Muster 'technical': Ohne diese Pruefung meldete das Kommando fuer
        jedes echte Symbol "keine Kerzen im Bestand" -- eine Meldung, die auf
        den Bestand zeigt, waehrend der Anbieter das Problem ist.

        Ausgeliefert steht ``market_data.provider`` auf ``fixture``; das ist
        also der Normalfall, nicht der Ausnahmefall.
        """
        args = build_parser().parse_args(
            ["fundamental", "--symbols", "AAPL", "--price-from-bars"]
        )
        assert cli.command_fundamental(args) == 2
        fehler = capsys.readouterr().err
        assert "aus dem ueber IBKR gefuellten Bestand" in fehler
        # Der Hinweis nennt den Schalter **dieses** Befehls -- dieselbe
        # Funktion bedient auch 'options', und dort hiesse er anders.
        assert "'--provider' uebersteuert bei diesem Unterbefehl die Fundamentalquelle" in (
            fehler
        )

    def test_ohne_den_schalter_wird_der_bestand_nicht_angefasst(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Der Bestand wird nicht heimlich angezapft.

        Geprueft wird, dass ``_kurse_aus_dem_bestand`` **ungerufen** bleibt --
        ein Test auf den argparse-Default sagte darueber nichts.
        """
        gerufen: list[object] = []

        def merken(
            *args: object, **kwargs: object
        ) -> tuple[dict[str, float], dict[str, object], list[object]]:
            gerufen.append(args)
            return {}, {}, []

        monkeypatch.setattr(cli, "_kurse_aus_dem_bestand", merken)
        args = build_parser().parse_args(
            ["fundamental", "--symbols", "AAPL", "--provider", "fixture"]
        )
        cli.command_fundamental(args)
        assert gerufen == []

    def test_der_kurs_aus_dem_bestand_erreicht_den_anbieter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Die Verdrahtung, nicht nur die Ermittlung.

        Waere das dict nach ``stock.id`` statt nach Symbol verschluesselt,
        bliebe jeder andere Test gruen und der Anbieter bekaeme ``None``.
        """
        gesehen: dict[str, float | None] = {}

        class Anbieter:
            def fundamentals(self, stock: Stock, price: float | None = None) -> object:
                gesehen[stock.symbol] = price
                raise FundamentalDataProviderError("reicht -- der Kurs ist geprueft")

        monkeypatch.setattr(cli, "build_fundamental_data_provider", lambda *a, **k: Anbieter())
        monkeypatch.setattr(
            cli,
            "_kurse_aus_dem_bestand",
            lambda *a, **k: ({"AAPL": 232.14}, {"AAPL": datetime(2026, 8, 31, tzinfo=UTC)}, []),
        )

        args = build_parser().parse_args(
            ["fundamental", "--symbols", "AAPL,NVDA", "--price-from-bars"]
        )
        cli.command_fundamental(args)

        assert gesehen["AAPL"] == pytest.approx(232.14)
        # NVDA hatte keinen Kurs -- kein Ersatzwert, kein Kurs des Nachbarn.
        assert gesehen["NVDA"] is None

    def test_der_grund_fuer_einen_fehlenden_kurs_wird_genannt(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Eine weggebrochene Datenbank und eine lueckenhafte Historie
        melden sich beide beim Laden der Kerzen. Unter einer Sammelmeldung
        "nicht im Bestand" saehen sie aus wie ein fehlender Backfill -- und
        der Leser suchte an der falschen Stelle.
        """
        monkeypatch.setattr(
            cli,
            "_kurse_aus_dem_bestand",
            lambda *a, **k: ({}, {}, [("AAPL", "lueckenhafte Historie: zur Kerze fehlen Bars")]),
        )
        args = build_parser().parse_args(
            ["fundamental", "--symbols", "AAPL", "--provider", "fixture", "--price-from-bars"]
        )
        cli.command_fundamental(args)

        assert "lueckenhafte Historie" in capsys.readouterr().err

    def test_der_anbieterfehler_wird_nicht_zu_nicht_im_bestand(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Derselbe Befund an der Quelle: ``_kurse_aus_dem_bestand`` selbst
        darf die Ursache nicht verschlucken."""

        class Kaputt:
            def list_stocks(self) -> Sequence[Stock]:
                return (Stock(id=uuid.uuid4(), symbol="AAPL", exchange="NASDAQ"),)

            def get_candle_series(self, stock: Stock) -> CandleSeries:
                raise MarketDataProviderError("Der Bestand von 'AAPL' ist nicht lesbar")

        monkeypatch.setattr(cli, "_open_database", lambda: _FakeEngine())
        monkeypatch.setattr(cli, "build_session_factory", lambda engine: None)
        monkeypatch.setattr(cli, "build_market_data_provider", lambda *a, **k: Kaputt())

        config = _config_mit_ibkr_bestand()
        ergebnis = cli._kurse_aus_dem_bestand(_loaded(config), config, ["AAPL"])

        assert ergebnis is not None
        _, _, ohne = ergebnis
        assert ohne == [("AAPL", "Der Bestand von 'AAPL' ist nicht lesbar")]

    def test_die_kursherkunft_steht_auch_ohne_summary_da(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Ohne --summary laeuft die Auswertung gar nicht. Stuende das Alter
        nur dort, waere ein Lauf mit --output blind fuer einen drei Wochen
        alten Bestand."""
        cli._print_kursherkunft({"AAPL": datetime(2026, 8, 28, tzinfo=UTC)}, gesamt=190)
        ausgabe = capsys.readouterr().out
        assert "1 von 190" in ausgabe
        assert "2026-08-28" in ausgabe

    def test_ohne_einen_einzigen_kurs_sagt_die_herkunft_das_auch(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cli._print_kursherkunft({}, gesamt=190)
        assert "Kein einziger Kurs" in capsys.readouterr().out

    def test_teilweise_kurse_unterdruecken_den_hinweis_nicht(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Bei einem von zwei Titeln gilt der Hinweis fuer den anderen weiter.

        Der Test laeuft durch ``command_fundamental``, damit er die
        **Berechnung** von ``mit_kurs`` prueft. Ein direkter Aufruf der
        Auswertung mit ``mit_kurs=False`` bewiese nur, dass die Funktion
        ausgibt, was man ihr sagt.
        """
        snapshot = self._snapshot()

        class Anbieter:
            def fundamentals(self, stock: Stock, price: float | None = None) -> object:
                return snapshot

        monkeypatch.setattr(cli, "build_fundamental_data_provider", lambda *a, **k: Anbieter())
        monkeypatch.setattr(
            cli,
            "_kurse_aus_dem_bestand",
            lambda *a, **k: (
                {"AAPL": 232.14},
                {"AAPL": datetime(2026, 8, 31, tzinfo=UTC)},
                [("NVDA", "nicht im Bestand")],
            ),
        )

        args = build_parser().parse_args(
            ["fundamental", "--symbols", "AAPL,NVDA", "--price-from-bars", "--summary"]
        )
        cli.command_fundamental(args)

        assert "Ohne Kurs" in capsys.readouterr().out

    def test_vollstaendige_kurse_unterdruecken_den_hinweis(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Die Gegenrichtung -- sonst bestuende der Test auch, wenn der
        Hinweis immer erschiene."""
        snapshot = self._snapshot()

        class Anbieter:
            def fundamentals(self, stock: Stock, price: float | None = None) -> object:
                return snapshot

        monkeypatch.setattr(cli, "build_fundamental_data_provider", lambda *a, **k: Anbieter())
        monkeypatch.setattr(
            cli,
            "_kurse_aus_dem_bestand",
            lambda *a, **k: (
                {"AAPL": 232.14, "NVDA": 180.0},
                {
                    "AAPL": datetime(2026, 8, 31, tzinfo=UTC),
                    "NVDA": datetime(2026, 8, 31, tzinfo=UTC),
                },
                [],
            ),
        )

        args = build_parser().parse_args(
            ["fundamental", "--symbols", "AAPL,NVDA", "--price-from-bars", "--summary"]
        )
        cli.command_fundamental(args)

        assert "Ohne Kurs" not in capsys.readouterr().out

    def test_der_kurs_ist_der_schluss_der_letzten_abgeschlossenen_kerze(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dieselbe Regel wie im Tageslauf (ADR 0035, Entscheidung 2).

        Der Test prueft den **Wert**, nicht nur dass irgendein Kurs ankommt:
        Eine Serie mit unterschiedlichen Schlusskursen deckt auf, wenn statt
        der letzten die erste Kerze genommen wird -- bei gleichen Werten
        faende man das nie.
        """
        series = kerzenreihe([100.0, 232.14])
        monkeypatch.setattr(cli, "_open_database", lambda: _FakeEngine())
        monkeypatch.setattr(cli, "build_session_factory", lambda engine: None)
        monkeypatch.setattr(
            cli, "build_market_data_provider", lambda *a, **k: FakeProvider(series)
        )

        config = _config_mit_ibkr_bestand()
        ergebnis = cli._kurse_aus_dem_bestand(_loaded(config), config, ["AAPL"])
        assert ergebnis is not None
        kurse, stempel, ohne = ergebnis

        assert kurse == {"AAPL": pytest.approx(232.14)}
        assert stempel["AAPL"] == series.candles[-1].timestamp
        assert ohne == []

    def test_die_datenbankverbindung_wird_freigegeben(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Danach folgt ein minutenlanger EDGAR-Abruf. Ein offener Pool
        ueberdauerte ihn ohne Grund."""
        engine = _FakeEngine()
        series = kerzenreihe([100.0, 232.14])
        monkeypatch.setattr(cli, "_open_database", lambda: engine)
        monkeypatch.setattr(cli, "build_session_factory", lambda e: None)
        monkeypatch.setattr(
            cli, "build_market_data_provider", lambda *a, **k: FakeProvider(series)
        )

        config = _config_mit_ibkr_bestand()
        cli._kurse_aus_dem_bestand(_loaded(config), config, ["AAPL"])

        assert engine.freigegeben is True

    def test_der_bestand_wird_als_gespeicherte_quelle_gelesen(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Nicht live: Das Kommando soll ohne TWS laufen. Der Anbieter wird
        mit ``source="stored"`` gebaut, auch wenn die Konfiguration etwas
        anderes sagt."""
        gesehen: dict[str, str] = {}

        def bauer(config: AppConfig, *a: object, **k: object) -> object:
            gesehen["source"] = config.market_data.source
            return FakeProvider(kerzenreihe([100.0, 232.14]))

        monkeypatch.setattr(cli, "_open_database", lambda: _FakeEngine())
        monkeypatch.setattr(cli, "build_session_factory", lambda e: None)
        monkeypatch.setattr(cli, "build_market_data_provider", bauer)

        basis = _config_mit_ibkr_bestand()
        config = basis.model_copy(
            update={"market_data": basis.market_data.model_copy(update={"source": "live"})}
        )
        cli._kurse_aus_dem_bestand(_loaded(config), config, ["AAPL"])

        assert gesehen["source"] == "stored"

    def test_eine_aktie_ohne_bestand_rechnet_ohne_kurs_statt_zu_scheitern(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Kein Ersatzwert und kein Abbruch des ganzen Laufs: Die Aktie wird
        ausgewertet, nur ohne die vier bewertungsabhaengigen Kennzahlen --
        genau wie ein Lauf ohne Kurs (ADR 0032, nicht blockierende Eingabe).
        """
        series = kerzenreihe([100.0, 232.14])
        monkeypatch.setattr(cli, "_open_database", lambda: _FakeEngine())
        monkeypatch.setattr(cli, "build_session_factory", lambda engine: None)
        monkeypatch.setattr(
            cli, "build_market_data_provider", lambda *a, **k: FakeProvider(series)
        )

        config = _config_mit_ibkr_bestand()
        ergebnis = cli._kurse_aus_dem_bestand(_loaded(config), config, ["AAPL", "NIEGEHOERT"])
        assert ergebnis is not None
        kurse, _, ohne = ergebnis

        assert "AAPL" in kurse
        assert ohne == [("NIEGEHOERT", "nicht im Bestand")]

    def test_symbole_und_watchlist_schliessen_sich_aus(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        args = build_parser().parse_args(["fundamental", "--symbols", "AAPL", "--watchlist"])
        assert cli.command_fundamental(args) == 2
        assert "nicht beides" in capsys.readouterr().err

    def test_ohne_symbole_und_ohne_watchlist_passiert_nichts(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        args = build_parser().parse_args(["fundamental"])
        assert cli.command_fundamental(args) == 2
        assert "nicht keines" in capsys.readouterr().err

    @pytest.mark.parametrize("scheitert_an", ["mkdir", "touch"])
    def test_ein_unbeschreibbares_ziel_faellt_vor_dem_ersten_abruf_auf(
        self,
        scheitert_an: str,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Der Lauf ueber die Watchliste laedt rund 800 MB und dauert Minuten.

        Das fehlende Verzeichnis erst beim Schreiben zu bemerken, warf den
        ganzen Lauf weg -- gemessen am 2026-08-26 an einem Lauf ueber 191
        Aktien, dessen Einzelwerte danach verloren waren.
        """

        class _VerbotenerProvider:
            def fundamentals(self, stock: object, price: float | None = None) -> object:
                raise AssertionError(f"Es darf kein Abruf beginnen ({stock!r}, {price!r})")

        monkeypatch.setattr(
            cli,
            "build_fundamental_data_provider",
            lambda _config, _secrets: _VerbotenerProvider(),
        )
        datei = tmp_path / "nicht" / "vorhanden"
        args = build_parser().parse_args(
            ["fundamental", "--symbols", "AAPL", "--output", str(datei)]
        )
        # Beide Wege muessen greifen: ein fehlendes Verzeichnis faellt beim
        # Anlegen auf, ein schreibgeschuetztes erst beim Anfassen der Datei.
        monkeypatch.setattr(Path, scheitert_an, _wirft_oserror)
        assert cli.command_fundamental(args) == 2
        assert "--output nicht beschreibbar" in capsys.readouterr().err

    def test_ein_fehlendes_verzeichnis_wird_angelegt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ein Tippfehler im Pfad soll auffallen, ein noch nicht angelegtes
        Ausgabeverzeichnis nicht stoeren."""
        monkeypatch.setattr(cli, "build_fundamental_data_provider", _kein_provider)
        datei = tmp_path / "artifacts" / "abdeckung.csv"
        args = build_parser().parse_args(
            ["fundamental", "--symbols", "AAPL", "--output", str(datei)]
        )
        cli.command_fundamental(args)
        assert datei.parent.is_dir()

    def test_die_sammelzeile_nennt_abdeckung_und_fehlendes(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Der volle Block laeuft bei hundert Titeln aus dem Terminalpuffer."""
        cli._print_fundamental_summary_line(self._snapshot())
        ausgabe = capsys.readouterr().out
        assert "TEST" in ausgabe
        assert "6%" in ausgabe
        assert MetricName.REVENUE.value in ausgabe

    def test_die_auswertung_zaehlt_je_kennzahl_wie_oft_sie_fehlt(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Die Frage des Watchlist-Laufs ist nicht, wie eine einzelne Aktie
        aussieht, sondern wie oft eine Kennzahl fehlt (ADR 0032 L1)."""
        cli._print_fundamental_aggregate([self._snapshot()], [], mit_kurs=False)
        ausgabe = capsys.readouterr().out
        assert "1 Aktien ausgewertet" in ausgabe
        assert "Je Kennzahl, wie oft sie fehlt" in ausgabe
        assert f"{MetricName.GROSS_MARGIN.value:28}   1 von 1" in ausgabe

    def test_die_auswertung_weist_auf_den_fehlenden_kurs_hin(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Sonst saehe eine um 22 Punkte gedrueckte Abdeckung wie ein Mangel
        der Tag-Listen aus.

        Der Hinweis nennt seit ``--price-from-bars`` keinen Schalter mehr:
        Es gibt zwei Wege zu einem Kurs, und der Hinweis gilt fuer beide.
        """
        cli._print_fundamental_aggregate([self._snapshot()], [], mit_kurs=False)
        assert "Ohne Kurs" in capsys.readouterr().out
        cli._print_fundamental_aggregate([self._snapshot()], [], mit_kurs=True)
        assert "Ohne Kurs" not in capsys.readouterr().out

    def test_fehlschlaege_stehen_am_ende_noch_einmal(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Bei zweihundert Titeln ist die Fehlerzeile laengst
        weggescrollt."""
        cli._print_fundamental_aggregate(
            [self._snapshot()], [("BRK B", "Kein SEC-Emittent")], mit_kurs=True
        )
        ausgabe = capsys.readouterr().out
        assert "1 Fehlschlaege" in ausgabe
        assert "BRK B" in ausgabe

    def test_die_csv_traegt_basis_und_zeitraum_an_jedem_wert(self, tmp_path: Path) -> None:
        """Nicht in der Kopfzeile: Zwei Kennzahlen desselben Berichts koennen
        verschiedene Zeitbezuege haben (ADR 0033 L2)."""
        ziel = tmp_path / "kennzahlen.csv"
        cli._write_fundamental_csv(ziel, [self._snapshot()])
        zeilen = ziel.read_text(encoding="utf-8").splitlines()
        assert zeilen[0].startswith("symbol,status,abdeckung,kennzahl")
        assert "TRAILING_TWELVE_MONTHS" in zeilen[1]
        assert "2024-12-31" in zeilen[1]

    def test_die_csv_nennt_alle_quellen_einer_kennzahl(self, tmp_path: Path) -> None:
        """Eine Marge steht auf zwei Tags, der freie Cashflow ebenfalls.

        Die Datei entsteht, um die Tag-Abdeckung auszuwerten -- mit nur der
        ersten Quelle je Kennzahl fehlte darin jeder Nenner und jeder
        Investitionstag, also genau das, was gemessen werden soll.
        """
        zweite = SourceRef(
            cik=42, accession="0000000042-25-000002", form="10-Q",
            filed=date(2025, 5, 1), tag="NetIncomeLoss",
        )
        metric = Metric(
            name=MetricName.NET_MARGIN, value=0.25, unit=MetricUnit.FRACTION,
            basis=MetricBasis.TRAILING_TWELVE_MONTHS, period_end=date(2024, 12, 31),
            sources=(
                SourceRef(cik=42, accession="0000000042-25-000001", form="10-K",
                          filed=date(2025, 2, 1), tag="Revenues"),
                zweite,
            ),
            retrieved_at=datetime(2026, 8, 24, tzinfo=UTC),
        )
        ziel = tmp_path / "kennzahlen.csv"
        cli._write_fundamental_csv(ziel, [self._snapshot(metrics={MetricName.NET_MARGIN: metric})])
        zeile = ziel.read_text(encoding="utf-8").splitlines()[1]
        assert "Revenues NetIncomeLoss" in zeile
        # Das juengste Einreichungsdatum, weil es die Aktualitaet des Werts
        # bestimmt -- nicht das der zufaellig ersten Quelle.
        assert "2025-05-01" in zeile

    def test_eine_aktie_ohne_kennzahlen_verschwindet_nicht_aus_der_csv(
        self, tmp_path: Path
    ) -> None:
        ziel = tmp_path / "kennzahlen.csv"
        cli._write_fundamental_csv(
            ziel, [self._snapshot(metrics={}, status=FundamentalStatus.INSUFFICIENT_DATA)]
        )
        zeilen = ziel.read_text(encoding="utf-8").splitlines()
        assert len(zeilen) == 2
        assert "INSUFFICIENT_DATA" in zeilen[1]

    def test_ohne_kurs_bleibt_das_argument_leer(self) -> None:
        """Nicht 0.0: Ein Kurs von null waere eine Angabe, keine fehlende."""
        args = build_parser().parse_args(["fundamental", "--symbols", "AAPL"])
        assert args.price is None


class TestRatingsKommando:
    """Die Einzelprobe der Analystenempfehlungen (ADR 0043).

    Muster ``TestResearchAusgabe`` -- mit einem Unterschied, der ausdruecklich
    geprueft wird: Fehlende Abdeckung ist **kein Fehler**. Doc 14, Schritt 1b
    sagt das dem Betreiber zu; ein Rueckgabewert 1 machte daraus eine
    Stoerungsmeldung.
    """

    def test_der_fixture_anbieter_laeuft_ohne_zugangsschluessel_durch(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = write_config(projekt, provider="fixture")

        exit_code = main(["--config", str(config), "ratings", "--symbol", "fixcand"])

        assert exit_code == 0
        ausgabe = capsys.readouterr().out
        # Kleinschreibung im Argument, Grossschreibung in der Ausgabe.
        assert "FIXCAND" in ausgabe
        assert "COMPLETED" in ausgabe

    def test_die_vier_monatsstaende_stehen_in_der_ausgabe(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = write_config(projekt, provider="fixture")

        main(["--config", str(config), "ratings", "--symbol", "FIXCAND"])

        ausgabe = capsys.readouterr().out
        assert ausgabe.count("2026-") >= 4 or ausgabe.count("-01") >= 4
        assert "S-Sell" in ausgabe

    def test_kursziele_werden_ausdruecklich_als_zurueckgestellt_genannt(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Sonst sucht jemand nach ihnen und haelt ihr Fehlen fuer einen Fehler."""
        config = write_config(projekt, provider="fixture")

        main(["--config", str(config), "ratings", "--symbol", "FIXCAND"])

        assert "Kursziele" in capsys.readouterr().out

    def test_fehlende_abdeckung_ist_kein_fehler(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Der Anbieter hat sauber geantwortet, dass es nichts gibt."""
        config = write_config(projekt, provider="fixture")

        exit_code = main(["--config", str(config), "ratings", "--symbol", "NIEGEHOERT"])

        assert exit_code == 0
        ausgabe = capsys.readouterr().out
        assert "UNKNOWN" in ausgabe
        assert "no_coverage" in ausgabe

    def test_ein_anbieterfehler_ergibt_rueckgabewert_zwei(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = write_config(projekt, provider="fixture")

        exit_code = main(["--config", str(config), "ratings", "--symbol", "RATINGERROR"])

        assert exit_code == 2
        assert "RATINGERROR" in capsys.readouterr().err

    def test_die_konfiguration_vor_dem_unterbefehl_wird_gelesen(self, projekt: Path) -> None:
        """``ratings`` und ``calendar-reach`` erklaerten ``--config`` ein
        zweites Mal, mit ``default=None`` -- und ueberschrieben damit still
        den Wert des Hauptparsers. Gemerkt hat es niemand, solange kein
        Verhalten an der Datei hing; mit ``--watchlist`` haengt es daran.
        """
        config = write_config(projekt, provider="fixture")

        args = build_parser().parse_args(["--config", str(config), "ratings", "--symbol", "A"])

        assert args.config == config

    def test_die_watchliste_liefert_eine_zeile_je_aktie(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (projekt / "watchlists" / "test.txt").write_text(
            "NASDAQ:FIXCAND,NASDAQ:NIEGEHOERT", encoding="utf-8"
        )
        config = write_config(projekt, provider="fixture")

        exit_code = main(["--config", str(config), "ratings", "--watchlist"])

        assert exit_code == 0
        ausgabe = capsys.readouterr().out
        assert "FIXCAND" in ausgabe
        assert "NIEGEHOERT" in ausgabe
        assert "2 Aktien, 1 mit Kauf-Anteil" in ausgabe
        # Ausdruecklich aufgezaehlt und nicht bloss weggelassen: Wer die
        # Verteilung auswertet, muss den Nenner kennen.
        assert "Ohne Anteil: 1 (NIEGEHOERT)" in ausgabe

    def test_die_csv_traegt_den_kauf_anteil_und_seinen_beleg(
        self, projekt: Path, tmp_path: Path
    ) -> None:
        (projekt / "watchlists" / "test.txt").write_text(
            "NASDAQ:FIXCAND,NASDAQ:NIEGEHOERT", encoding="utf-8"
        )
        config = write_config(projekt, provider="fixture")
        ziel = tmp_path / "ratings.csv"

        main(["--config", str(config), "ratings", "--watchlist", "--output", str(ziel)])

        zeilen = list(csv.DictReader(ziel.read_text(encoding="utf-8").splitlines()))
        nach_symbol = {zeile["symbol"]: zeile for zeile in zeilen}
        assert set(nach_symbol) == {"FIXCAND", "NIEGEHOERT"}

        mit = nach_symbol["FIXCAND"]
        assert mit["kennzahl"] == "ANALYST_BUY_SHARE"
        assert 0.0 <= float(mit["wert"]) <= 1.0
        # Ohne Monatsstand und Votenzahl liesse sich ein Anteil von 1,0 aus
        # drei Voten nicht von einem aus vierzig unterscheiden.
        assert mit["monatsstand"]
        assert int(mit["voten"]) > 0

        ohne = nach_symbol["NIEGEHOERT"]
        assert ohne["status"] == "UNKNOWN"
        assert ohne["kennzahl"] == ""
        assert ohne["wert"] == ""

    def test_die_datei_laesst_sich_ohne_umweg_kalibrieren(
        self, projekt: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Der eigentliche Zweck des Schalters: Die Messung geht direkt in
        'calibrate-scores'. Ein abweichender Spaltenname faellt sonst erst auf
        dem Server auf, nach zweihundert Abrufen."""
        (projekt / "watchlists" / "test.txt").write_text(
            "NASDAQ:FIXCAND,NASDAQ:EARNCLEAR,NASDAQ:EARNEXCLUDED", encoding="utf-8"
        )
        config = write_config(projekt, provider="fixture")
        ziel = tmp_path / "ratings.csv"
        main(["--config", str(config), "ratings", "--watchlist", "--output", str(ziel)])
        capsys.readouterr()

        exit_code = main(["--config", str(config), "calibrate-scores", "--input", str(ziel)])

        assert exit_code == 0
        ausgabe = capsys.readouterr().out
        assert "ANALYST_BUY_SHARE" in ausgabe
        assert "Verteilung ueber 3 Aktien" in ausgabe

    def test_ein_ausfall_bei_einer_aktie_kostet_nicht_den_messlauf(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Bei zweihundert Symbolen waere der Abbruch die teuerste denkbare
        Reaktion auf den haeufigsten Fehler."""
        (projekt / "watchlists" / "test.txt").write_text(
            "NASDAQ:FIXCAND,NASDAQ:RATINGERROR", encoding="utf-8"
        )
        config = write_config(projekt, provider="fixture")

        exit_code = main(["--config", str(config), "ratings", "--watchlist"])

        assert exit_code == 0
        assert "RATINGERROR" in capsys.readouterr().err

    def test_ein_unbeschreibbares_ziel_faellt_vor_dem_ersten_abruf_auf(
        self, projekt: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Muster 'fundamental': Ein Lauf ueber zweihundert Symbole dauert
        Minuten; ein fehlendes Verzeichnis erst beim Schreiben zu bemerken
        warf ihn weg."""
        config = write_config(projekt, provider="fixture")
        ziel = tmp_path / "datei" / "ratings.csv"
        ziel.parent.write_text("keine Datei, ein Verzeichnisname", encoding="utf-8")

        exit_code = main(
            ["--config", str(config), "ratings", "--symbol", "FIXCAND", "--output", str(ziel)]
        )

        assert exit_code == 2
        assert "--output nicht beschreibbar" in capsys.readouterr().err

    def test_symbol_und_watchlist_schliessen_sich_aus(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = write_config(projekt, provider="fixture")

        exit_code = main(
            ["--config", str(config), "ratings", "--symbol", "AAPL", "--watchlist"]
        )

        assert exit_code == 2
        assert "nicht beides" in capsys.readouterr().err

    def test_ohne_symbol_und_ohne_watchlist_passiert_nichts(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Frueher war ``--symbol`` Pflicht. Seit es das nicht mehr ist, muss
        der Befehl selbst sagen, dass er ohne Ziel nichts tut."""
        config = write_config(projekt, provider="fixture")

        exit_code = main(["--config", str(config), "ratings"])

        assert exit_code == 2
        assert "nicht keines" in capsys.readouterr().err

    def test_ein_fehlendes_geheimnis_ergibt_rueckgabewert_zwei(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """'finnhub' braucht den Zugangsschluessel. Ohne ihn ist das ein
        Konfigurationsfehler, kein voruebergehender Ausfall."""
        monkeypatch.setenv("ATA_FINNHUB_API_KEY", "")
        config = write_config(projekt, provider="fixture")

        exit_code = main(
            ["--config", str(config), "ratings", "--symbol", "AAPL", "--provider", "finnhub"]
        )

        assert exit_code == 2
        assert "Analystenempfehlungen" in capsys.readouterr().err

    def test_der_schalter_uebersteuert_nur_diesen_aufruf(
        self, projekt: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Derselbe ``model_copy``-Pfad wie beim Dispatch-Schalter -- dort
        eigens getestet, hier bis zur Review ungeprueft."""
        gesehen: dict[str, str] = {}

        def bauen(config: AppConfig, secrets: Secrets) -> AnalystRecommendationsProvider:
            gesehen["provider"] = config.analyst_ratings.provider
            raise MissingSecretError("Abbruch fuer den Test")

        monkeypatch.setattr(cli, "build_analyst_recommendations_provider", bauen)
        config = write_config(projekt, provider="fixture")

        main(["--config", str(config), "ratings", "--symbol", "AAPL", "--provider", "finnhub"])

        assert gesehen == {"provider": "finnhub"}

    def test_ohne_schalter_bleibt_die_konfiguration_massgeblich(self) -> None:
        args = build_parser().parse_args(["ratings", "--symbol", "AAPL"])
        assert args.provider is None

    def test_ein_unbekannter_anbieter_wird_abgewiesen(self, projekt: Path) -> None:
        config = write_config(projekt, provider="fixture")

        with pytest.raises(SystemExit) as abbruch:
            main(["--config", str(config), "ratings", "--symbol", "AAPL", "--provider", "edgar"])

        assert abbruch.value.code == 2


class TestReportKommando:
    """``cli report`` liest nur (ADR 0039). Geprueft werden die Wege, die ohne
    Datenbank erreichbar sind -- Argumentpruefung und Ausgabeform."""

    def test_eine_kaputte_lauf_id_bricht_vor_der_datenbank_ab(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def nie(*args: object, **kwargs: object) -> None:
            raise AssertionError("Die Datenbank wurde entgegen der Erwartung geoeffnet")

        monkeypatch.setattr(cli, "_open_database", nie)

        code = cli.command_report(
            argparse.Namespace(run="keine-uuid", symbol=None, format="text", output=None)
        )

        assert code == 2
        assert "keine Lauf-ID" in capsys.readouterr().err

    def test_ein_nicht_beschreibbares_ziel_bricht_vor_der_datenbank_ab(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Derselbe Fehler hat bei ``cli fundamental`` schon einmal einen
        vollstaendigen Watchlist-Lauf gekostet -- geprueft wird deshalb, dass
        die Pruefung wirklich vorher greift.

        Das Ziel liegt **unterhalb einer regulaeren Datei**. Das scheitert auf
        jedem Betriebssystem, weil eine Datei kein Verzeichnis sein kann --
        anders als ein angeblich unschreibbarer absoluter Pfad: Der
        Windows-Job der CI laeuft als Administrator und legte ``C:\\...``
        anstandslos an, womit die Probe durchging und der Test dort fiel.
        """

        def nie(*args: object, **kwargs: object) -> None:
            raise AssertionError("Die Datenbank wurde entgegen der Erwartung geoeffnet")

        monkeypatch.setattr(cli, "_open_database", nie)

        keine_datei = tmp_path / "datei.txt"
        keine_datei.write_text("kein Verzeichnis", encoding="utf-8")

        code = cli.command_report(
            argparse.Namespace(
                run=str(uuid.uuid4()),
                symbol=None,
                format="text",
                output=str(keine_datei / "bericht.txt"),
            )
        )

        assert code == 2
        assert "nicht beschreibbar" in capsys.readouterr().err

    def test_der_unterbefehl_haengt_am_richtigen_handler(self) -> None:
        args = cli.build_parser().parse_args(["report", "--run", "abc"])
        assert args.handler is cli.command_report
        assert args.format == "text"
        assert args.symbol is None
        assert args.output is None

    def test_json_ist_waehlbar(self) -> None:
        args = cli.build_parser().parse_args(
            ["report", "--run", "abc", "--format", "json", "--symbol", "aapl"]
        )
        assert args.format == "json"
        assert args.symbol == "aapl"


class TestBoersentag:
    """Der Bezugstag der Messung folgt der Marktzeitzone, nicht UTC.

    Als eigene Funktion geprueft, weil der Unterschied sich am ganzen
    Kommando nur zu bestimmten Tageszeiten zeigt -- ein Test dort waere je
    nach Stunde gruen und saehe die Verwechslung nicht.
    """

    def test_am_abend_gilt_noch_der_laufende_handelstag(self) -> None:
        """22:30 New Yorker Zeit ist bereits der naechste UTC-Tag. Mit
        ``.date()`` auf dem UTC-Zeitpunkt fiele ein kuenftiger Handelstag aus
        der Zaehlung."""
        jetzt = datetime(2026, 11, 26, 3, 30, tzinfo=UTC)  # 25.11., 22:30 ET
        assert boersentag(jetzt, "America/New_York") == date(2026, 11, 25)
        assert jetzt.date() == date(2026, 11, 26)

    def test_tagsueber_stimmen_beide_ueberein(self) -> None:
        """Genau deshalb faellt der Fehler im Alltag nicht auf."""
        jetzt = datetime(2026, 11, 25, 18, 0, tzinfo=UTC)  # 13:00 ET
        assert boersentag(jetzt, "America/New_York") == jetzt.date()


class TestErforderlicheHandelstage:
    """Die Umrechnung Kerzen -> Handelstage, fuer sich geprueft.

    Sie stand erst inline im Kommando und war dort um eins zu klein: Der
    Filter schliesst aus bei ``kerzen <= fenster``, "nicht ausgeschlossen"
    beginnt also erst einen Handelstag spaeter. ``ceil`` faellt nur bei
    ungeraden Fenstern zufaellig richtig aus -- und alle konfigurierbaren
    Fenster (10, 20) sind bei zwei Kerzen je Tag gerade.
    """

    @pytest.mark.parametrize(
        ("fenster", "je_tag", "erwartet"),
        [
            # Der Vorgabefall: 20 Kerzen, 2 je Tag. ceil haette 10 gesagt.
            (20, 2, 11),
            (10, 2, 6),
            # Ungerade -- hier stimmte auch ceil, was den Fehler tarnte.
            (21, 2, 11),
            (1, 1, 2),
            (20, 3, 7),
        ],
    )
    def test_eine_stelle_ueber_dem_fenster(self, fenster: int, je_tag: int, erwartet: int) -> None:
        assert erforderliche_handelstage(fenster, je_tag) == erwartet

    def test_der_grenzfall_stimmt_mit_dem_filter_ueberein(self) -> None:
        """Die eigentliche Zusicherung: Bei genau so vielen Handelstagen muss
        der Filter ``EARNINGS_CLEAR`` sagen, einen weniger noch nicht."""
        fenster, je_tag = 20, 2
        benoetigt = erforderliche_handelstage(fenster, je_tag)

        assert (benoetigt - 1) * je_tag <= fenster
        assert benoetigt * je_tag > fenster

    def test_null_kerzen_je_tag_ist_ein_konfigurationsfehler(self) -> None:
        with pytest.raises(ValueError, match="kerzen_je_tag"):
            erforderliche_handelstage(20, 0)


class TestKalenderreichweite:
    """Die Ausgabe von ``calendar-reach`` -- ohne TWS.

    Das Kommando beantwortet die offene Frage hinter E4: Reicht IBKRs
    ``liquidHours`` so weit voraus wie das Ausschlussfenster des
    Earnings-Filters? Es entscheidet sie nicht; das tut ein ADR. Genau
    deshalb muss die Ausgabe beide Antworten unmissverstaendlich geben.
    """

    THANKSGIVING = (
        "20261125:0930-20261125:1600;20261126:CLOSED;"
        "20261127:0930-20261127:1300;20261130:0930-20261130:1600"
    )

    @classmethod
    def _sitzungen(cls) -> Mapping[date, TradingSession | None]:
        return parse_liquid_hours(cls.THANKSGIVING, "America/New_York")

    def _ausgabe(
        self,
        capsys: pytest.CaptureFixture[str],
        *,
        fenster_kerzen: int,
        heute: date = date(2026, 11, 24),
        vorlauf_kalendertage: int = 3,
    ) -> str:
        _print_calendar_reach(
            self._sitzungen(),
            symbol="AAPL",
            fenster_kerzen=fenster_kerzen,
            kerzen_je_tag=2,
            vorlauf_kalendertage=vorlauf_kalendertage,
            heute=heute,
        )
        return capsys.readouterr().out

    def test_ein_reichender_kalender_wird_als_solcher_benannt(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Drei kuenftige Handelstage (der 26. ist Feiertag), gebraucht
        werden bei 4 Kerzen / 2 je Tag drei."""
        ausgabe = self._ausgabe(capsys, fenster_kerzen=4)
        assert "reicht fuer die Ausschlussentscheidung" in ausgabe
        assert "NICHT weit genug" not in ausgabe

    def test_das_fenster_braucht_eine_stelle_mehr_als_es_breit_ist(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Der Off-by-one, den die Review gefunden hat: Bei 6 Kerzen / 2 je
        Tag deckt der Kalender mit drei Handelstagen das Fenster ab -- den
        Grenzfall entscheiden kann er damit trotzdem nicht."""
        ausgabe = self._ausgabe(capsys, fenster_kerzen=6)
        assert "Gebraucht werden 4 Handelstage" in ausgabe
        assert "NICHT weit genug" in ausgabe
        assert "3 von 4" in ausgabe

    def test_ein_zu_kurzer_kalender_wird_als_solcher_benannt(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Der Fall, der E4 auf Weg (b) festlegt -- er muss beim Lesen
        genauso eindeutig sein wie der andere."""
        ausgabe = self._ausgabe(capsys, fenster_kerzen=20)
        assert "NICHT weit genug" in ausgabe
        assert "3 von 11" in ausgabe

    def test_der_feiertag_zaehlt_nicht_als_handelstag(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Der ganze Zweck der Messung: Die Wochentagsnaeherung zaehlt den
        26.11. mit, der echte Kalender nicht."""
        ausgabe = self._ausgabe(capsys, fenster_kerzen=4)
        assert "Kuenftige Handelstage:  3" in ausgabe
        assert "2026-11-26" in ausgabe

    def test_vergangene_tage_zaehlen_nicht_mit(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Sonst meldete das Kommando Reichweite, die schon verstrichen ist."""
        ausgabe = self._ausgabe(capsys, fenster_kerzen=4, heute=date(2026, 11, 27))
        assert "Kuenftige Handelstage:  1" in ausgabe
        assert "NICHT weit genug" in ausgabe

    def test_der_bezugstag_steht_in_der_ausgabe(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Er ist der Boersentag, nicht der UTC-Tag. Ohne ihn im Bericht
        laesst sich ein ueberraschendes Ergebnis nicht nachvollziehen."""
        ausgabe = self._ausgabe(capsys, fenster_kerzen=4, heute=date(2026, 11, 24))
        assert "Bezugstag (Boerse):     2026-11-24" in ausgabe

    def test_ein_reichender_kalender_nennt_trotzdem_seine_grenze(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Das gespeicherte Feld ``candles_until_earnings`` gilt auch fuer
        nicht ausgeschlossene Titel, und Termine kommen bis 30 Kalendertage
        voraus. Reicht der Kalender nur bis zur Fenstergrenze, ist E4 nur
        halb beantwortet -- das darf die Ausgabe nicht verschweigen."""
        ausgabe = self._ausgabe(capsys, fenster_kerzen=4, vorlauf_kalendertage=30)
        assert "reicht fuer die Ausschlussentscheidung" in ausgabe
        assert "ABER" in ausgabe
        assert "30 Kalendertage" in ausgabe


class TestKalenderreichweiteVerdrahtung:
    """Dass das Kommando ueberhaupt aufrufbar ist.

    Ohne diesen Test blieb ein ``AttributeError`` unbemerkt: Der Subparser
    kannte ``--symbols`` nicht, ``_watchlist_from`` liest es aber -- jeder
    Aufruf brach ab, auch der in Doc 14 empfohlene.
    """

    def test_der_befehl_laeuft_ohne_tws_bis_zur_anbieterpruefung(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["calendar-reach"])
        assert code == 2
        assert "market_data.provider steht auf" in capsys.readouterr().err

    def test_symbole_lassen_sich_angeben(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = main(["calendar-reach", "--symbols", "AAPL"])
        assert code == 2
        assert "market_data.provider steht auf" in capsys.readouterr().err

    def test_der_bezugstag_ist_der_boersentag(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Nicht der UTC-Tag. Ein Lauf um 22:30 New Yorker Zeit liegt bereits
        im naechsten UTC-Datum -- ein kuenftiger Handelstag fiele aus der
        Zaehlung, und genau an der Grenze kippt das Ergebnis.

        Dieser Test laeuft als einziger durch das ganze Kommando; ohne ihn
        bliebe die Zeile, die den Bezugstag bestimmt, ungeprueft.
        """
        heute_ny = datetime.now(ZoneInfo("America/New_York")).date()
        morgen = heute_ny + timedelta(days=1)

        class FakeBarSource:
            geschlossen = False

            def liquid_hours(self, contract: ContractSpec) -> tuple[str, str]:
                tag = morgen.strftime("%Y%m%d")
                return f"{tag}:0930-{tag}:1600", "America/New_York"

            def close(self) -> None:
                FakeBarSource.geschlossen = True

        monkeypatch.setattr(cli, "build_ibkr_bar_source", lambda config: FakeBarSource())

        code = main(["calendar-reach", "--provider", "ibkr", "--symbols", "AAPL"])

        assert code == 0
        ausgabe = capsys.readouterr().out
        assert f"Bezugstag (Boerse):     {heute_ny.isoformat()}" in ausgabe
        assert "Kuenftige Handelstage:  1" in ausgabe
        assert FakeBarSource.geschlossen, "die TWS-Verbindung muss geschlossen werden"

    def test_die_zeitzone_kommt_aus_der_konfiguration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ob ``market.timezone`` beim Bezugstag ankommt, laesst sich an der
        Ausgabe nicht deterministisch pruefen: Zwei Zeitzonen unterscheiden
        sich nur einen Teil des Tages, ein solcher Test waere je nach Stunde
        gruen. Geprueft wird deshalb die Weitergabe selbst -- Muster der
        Durchreiche-Tests in ``test_bootstrap``.
        """
        gesehen: list[str] = []

        def merker(jetzt: datetime, timezone: str) -> date:
            gesehen.append(timezone)
            return boersentag(jetzt, timezone)

        class FakeBarSource:
            def liquid_hours(self, contract: ContractSpec) -> tuple[str, str]:
                tag = (
                    datetime.now(ZoneInfo("America/New_York")).date() + timedelta(days=1)
                ).strftime("%Y%m%d")
                return f"{tag}:0930-{tag}:1600", "America/New_York"

            def close(self) -> None:
                return None

        monkeypatch.setattr(cli, "build_ibkr_bar_source", lambda config: FakeBarSource())
        monkeypatch.setattr(cli, "boersentag", merker)

        main(["calendar-reach", "--provider", "ibkr", "--symbols", "AAPL"])

        erwartet = load_config(None).config.market.timezone
        assert gesehen == [erwartet]
        assert erwartet == "America/New_York", "CLAUDE.md: der Scheduler rechnet in New York"


class TestKalibrierung:
    """Die Messung, auf der die Score-Schwellen stehen (ADR 0041).

    Muster 'history-depth': messen, ausgeben, nichts ablegen. Die Schwellen
    selbst entscheidet ein ADR -- hier entstehen nur die Zahlen.
    """

    def _csv(self, tmp_path: Path, zeilen: Sequence[str]) -> Path:
        kopf = "symbol,status,abdeckung,kennzahl,wert,einheit,basis,zeitraum_ende"
        ziel = tmp_path / "kalibrierung.csv"
        ziel.write_text("\n".join([kopf, *zeilen]), encoding="utf-8")
        return ziel

    def test_die_fuenftelgrenzen_teilen_die_watchliste(self) -> None:
        """Bei zehn Werten 1..10 liegen die Grenzen zwischen den Paaren.

        Geprueft werden **konkrete Zahlen**, nicht nur "vier Grenzen kommen
        zurueck": Eine Verwechslung von Quintilen und Quartilen lieferte
        ebenfalls vier Werte.
        """
        grenzen = cli.quintilgrenzen([float(n) for n in range(1, 11)])

        assert grenzen == pytest.approx((2.8, 4.6, 6.4, 8.2))

    def test_die_reihenfolge_der_eingabe_ist_egal(self) -> None:
        werte = [5.0, 1.0, 9.0, 3.0, 7.0, 2.0, 8.0, 4.0, 10.0, 6.0]
        assert cli.quintilgrenzen(werte) == pytest.approx((2.8, 4.6, 6.4, 8.2))

    def test_ein_ausreisser_verschiebt_die_grenzen_kaum(self) -> None:
        """Der Grund fuer Quantile statt Mittelwert: GDDY hat eine
        Eigenkapitalrendite von 13587 % (Eigenkapital nahe null), CRWD ein KGV
        von 4368. Ein Mittelwert waere davon unbrauchbar, die Rangfolge nicht.
        """
        normal = [float(n) for n in range(1, 11)]
        mit_ausreisser = [*normal[:-1], 10_000.0]

        ohne = cli.quintilgrenzen(normal)
        mit = cli.quintilgrenzen(mit_ausreisser)

        assert mit[0] == pytest.approx(ohne[0])
        assert mit[1] == pytest.approx(ohne[1])
        assert abs(mit[2] - ohne[2]) < 0.5

    def test_unter_fuenf_werten_gibt_es_keine_fuenftel(self) -> None:
        """Kein Ersatzwert: Die Kennzahl bekommt in diesem Lauf keine
        Schwellen, statt aus vier Werten Fuenftel zu erfinden."""
        with pytest.raises(ValueError, match="mindestens fuenf"):
            cli.quintilgrenzen([1.0, 2.0, 3.0, 4.0])

    def test_die_kennzahlen_werden_aus_der_csv_gesammelt(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        zeilen = [
            f"SYM{n},COMPLETED,1.0,RETURN_ON_EQUITY,{n / 10},FRACTION,TTM,2026-06-30"
            for n in range(1, 11)
        ]
        args = build_parser().parse_args(
            ["calibrate-scores", "--input", str(self._csv(tmp_path, zeilen))]
        )

        assert cli.command_calibrate_scores(args) == 0

        ausgabe = capsys.readouterr().out
        assert "ueber 10 Aktien" in ausgabe
        assert "RETURN_ON_EQUITY" in ausgabe
        assert "0.2800" in ausgabe

    def test_eine_aktie_ohne_kennzahlen_wird_genannt(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """INSUFFICIENT_DATA steht mit leeren Feldern in der CSV. Sie zaehlt
        bei der Abdeckung mit -- verschwiegen saehe die Watchliste kleiner
        aus, als sie ist."""
        zeilen = [
            f"SYM{n},COMPLETED,1.0,RETURN_ON_EQUITY,{n / 10},FRACTION,TTM,2026-06-30"
            for n in range(1, 11)
        ]
        zeilen.append("XOM,INSUFFICIENT_DATA,0.0,,,,,")
        args = build_parser().parse_args(
            ["calibrate-scores", "--input", str(self._csv(tmp_path, zeilen))]
        )
        cli.command_calibrate_scores(args)

        ausgabe = capsys.readouterr().out
        assert "ueber 11 Aktien" in ausgabe
        assert "Ohne jede Kennzahl: 1 (XOM)" in ausgabe

    def test_eine_unlesbare_datei_bricht_ab(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        args = build_parser().parse_args(
            ["calibrate-scores", "--input", str(tmp_path / "gibtsnicht.csv")]
        )
        assert cli.command_calibrate_scores(args) == 2
        assert "nicht lesbar" in capsys.readouterr().err

    def test_eine_csv_ohne_kennzahlen_bricht_ab(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Sonst entstuende eine leere Tabelle, die wie ein Ergebnis aussieht."""
        leer = self._csv(tmp_path, ["XOM,INSUFFICIENT_DATA,0.0,,,,,"])
        args = build_parser().parse_args(["calibrate-scores", "--input", str(leer)])
        assert cli.command_calibrate_scores(args) == 2
        assert "keine auswertbaren Kennzahlen" in capsys.readouterr().err

    def test_die_spannweite_steht_neben_den_grenzen(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Sie zeigt, warum die Grenzen aus Quantilen kommen."""
        zeilen = [
            f"SYM{n},COMPLETED,1.0,PRICE_EARNINGS_RATIO,{n},RATIO,TTM,2026-06-30"
            for n in range(1, 10)
        ]
        zeilen.append("CRWD,COMPLETED,1.0,PRICE_EARNINGS_RATIO,4368.0,RATIO,TTM,2026-06-30")
        args = build_parser().parse_args(
            ["calibrate-scores", "--input", str(self._csv(tmp_path, zeilen))]
        )
        cli.command_calibrate_scores(args)

        ausgabe = capsys.readouterr().out
        assert "kleinster" in ausgabe
        assert "4368.0000" in ausgabe


class TestOptionsKommando:
    """``cli options`` -- Einzelprobe und Messlauf (ADR 0048).

    Die Einzelprobe ist der Grund, warum es diesen Befehl gibt: Ob IBKR nach
    Boersenschluss noch modellierte Greeks liefert, laesst sich nicht
    herleiten, nur messen. Sie muss deshalb auch ohne gefuellten Bestand
    laufen -- daher ``--price``.
    """

    def test_die_einzelprobe_laeuft_ohne_datenbank(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = write_config(projekt, provider="fixture")

        exit_code = main(
            ["--config", str(config), "options", "--symbol", "AAPL", "--price", "200"]
        )

        assert exit_code == 0
        ausgabe = capsys.readouterr().out
        assert "COMPLETED" in ausgabe
        # Delta und implizite Volatilitaet gehoeren in die Ausgabe: Genau sie
        # sind das Ergebnis der Probe.
        assert "Delta" in ausgabe
        assert "annualisiert" in ausgabe

    def test_symbol_und_watchlist_schliessen_sich_aus(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = write_config(projekt, provider="fixture")

        exit_code = main(
            ["--config", str(config), "options", "--symbol", "AAPL", "--watchlist"]
        )

        assert exit_code == 2
        assert "nicht beides" in capsys.readouterr().err

    def test_ein_kurs_von_hand_gilt_nur_fuer_ein_symbol(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Auf zweihundert Titel angewandt bewertete er jeden zum Kurs des
        ersten -- und der Befehl existiert gerade zum Gegenpruefen."""
        config = write_config(projekt, provider="fixture")

        exit_code = main(
            ["--config", str(config), "options", "--watchlist", "--price", "200"]
        )

        assert exit_code == 2
        assert "--price gilt fuer ein Symbol" in capsys.readouterr().err

    def test_ohne_bestand_zeigt_der_hinweis_auf_die_marktdatenquelle(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Der Hinweis stammt aus einer Funktion, die auch 'fundamental'
        benutzt -- er darf deshalb nicht auf deren Schalter zeigen."""
        config = write_config(projekt, provider="fixture")

        exit_code = main(["--config", str(config), "options", "--watchlist"])

        assert exit_code == 2
        fehler = capsys.readouterr().err
        assert "--market-data-provider ibkr" in fehler
        assert "--price-from-bars" not in fehler, "der Hinweis stammt vom falschen Befehl"

    def test_die_csv_traegt_die_spalten_die_calibrate_scores_liest(
        self, projekt: Path, tmp_path: Path
    ) -> None:
        config = write_config(projekt, provider="fixture")
        ziel = tmp_path / "optionen.messlauf.csv"

        main(
            [
                "--config",
                str(config),
                "options",
                "--symbol",
                "AAPL",
                "--price",
                "200",
                "--output",
                str(ziel),
            ]
        )

        (zeile,) = list(csv.DictReader(ziel.read_text(encoding="utf-8").splitlines()))
        assert zeile["symbol"] == "AAPL"
        assert zeile["kennzahl"] == "OPTIONS_ANNUALIZED_RETURN"
        assert float(zeile["wert"]) > 0
        # Strike und Laufzeit stehen daneben, damit sich ein auffaelliger Wert
        # nachvollziehen laesst, ohne den Lauf zu wiederholen.
        assert zeile["strike"]
        assert zeile["verfall"]

    def test_der_mitschnitt_braucht_eine_echte_tws(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Der Fixture-Anbieter erzeugt seine Kette selbst. Sie aufzuzeichnen
        ergaebe einen Contract-Test gegen den eigenen Code (A2-M7)."""
        config = write_config(projekt, provider="fixture")

        exit_code = main(
            [
                "--config",
                str(config),
                "options",
                "--symbol",
                "AAPL",
                "--price",
                "200",
                "--record",
                str(projekt / "kette.json"),
            ]
        )

        assert exit_code == 2
        assert "--provider ibkr" in capsys.readouterr().err

    def test_der_mitschnitt_gilt_nicht_fuer_die_watchliste(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = write_config(projekt, provider="fixture")

        exit_code = main(
            [
                "--config",
                str(config),
                "options",
                "--watchlist",
                "--record",
                str(projekt / "kette.json"),
            ]
        )

        assert exit_code == 2
        assert "--symbol" in capsys.readouterr().err

    def test_die_datei_laesst_sich_ohne_umweg_kalibrieren(
        self, projekt: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Derselbe Zweck wie bei 'ratings': Die Messung geht direkt in
        'calibrate-scores'. Ein abweichender Spaltenname faellt sonst erst auf
        dem Server auf, nach zweihundert Abrufen."""
        config = write_config(projekt, provider="fixture")
        ziel = tmp_path / "optionen.messlauf.csv"
        main(
            [
                "--config",
                str(config),
                "options",
                "--symbol",
                "AAPL",
                "--price",
                "200",
                "--output",
                str(ziel),
            ]
        )
        capsys.readouterr()

        exit_code = main(["--config", str(config), "calibrate-scores", "--input", str(ziel)])

        assert exit_code == 0
        assert "OPTIONS_ANNUALIZED_RETURN" in capsys.readouterr().out


class TestChartKommando:
    def test_symbole_und_ziel_werden_eingelesen(self) -> None:
        args = build_parser().parse_args(
            ["chart", "--symbols", "AAPL,MSFT", "--output", "/tmp/charts"]
        )

        assert args.symbols == "AAPL,MSFT"
        assert args.output == "/tmp/charts"
        assert args.handler is cli.command_chart

    def test_ohne_symbole_bricht_der_parser_ab(self) -> None:
        """Ein Chart ueber die ganze Watchlist waere kein Werkzeug zum
        Hinsehen, sondern ein Verzeichnis voller Dateien."""
        with pytest.raises(SystemExit):
            build_parser().parse_args(["chart"])

    def test_das_ziel_hat_eine_vorgabe(self) -> None:
        args = build_parser().parse_args(["chart", "--symbols", "AAPL"])
        assert args.output == "charts"

    def test_verweigert_den_lauf_wenn_der_anbieter_nicht_ibkr_ist(
        self, projekt: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Wie beim Backtest: Der Fixture-Anbieter kennt nur Kunstsymbole.
        Ohne diese Pruefung meldete das Kommando fuer jedes echte Symbol
        'Nicht in der Watchlist gefunden' und schoebe die Schuld auf die
        Watchlist statt auf den Anbieter."""
        config = write_config(projekt, provider="fixture")

        exit_code = main(
            ["--config", str(config), "chart", "--symbols", "AAPL",
             "--output", str(projekt / "charts")]
        )

        assert exit_code == 2
        fehler = capsys.readouterr().err
        assert "'fixture'" in fehler
        assert "Nicht in der Watchlist gefunden" not in fehler
        # Kein Verzeichnis anlegen, bevor der Lauf ueberhaupt moeglich ist.
        assert not (projekt / "charts").exists()
