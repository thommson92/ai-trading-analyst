"""Konfigurationsschema der Anwendung (Doc 10, Paragraph 17).

Aufgeteilt in zwei Quellen mit unterschiedlichem Vertrauensbereich:

* ``AppConfig`` -- fachliche Werte aus ``config/default.yaml``. Versionierbar,
  im Repository, ohne Geheimnisse.
* ``Secrets`` -- Zugangsdaten ausschliesslich aus Umgebungsvariablen. Nie in
  einer Datei im Repository (Doc 10, Paragraph 13).

Die Indikator-Parameter unterlagen Gate G1 und sind seit
docs/adr/0010-gate-g1-freigegeben.md fachlich freigegeben. Siehe
``IndicatorConfig``.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PositiveInt = Annotated[int, Field(gt=0)]


class GateNotClearedError(RuntimeError):
    """Ein fachliches Freigabe-Gate ist noch offen."""


class MissingSecretError(RuntimeError):
    """Ein benoetigtes Geheimnis ist nicht gesetzt."""


class _Section(BaseModel):
    """Basis fuer alle Konfigurationsabschnitte: unbekannte Schluessel sind Fehler.

    Ein Tippfehler in der YAML-Datei soll auffallen und nicht still zu einem
    Default-Wert fuehren.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class MarketConfig(_Section):
    """Handelssitzung und Zeitrahmen."""

    timezone: str = "America/New_York"
    regular_session_open: str = "09:30"
    regular_session_minutes: PositiveInt = 390
    timeframe_minutes: PositiveInt = 195
    daily_candle_index: PositiveInt = 1

    @model_validator(mode="after")
    def _timeframe_must_divide_session(self) -> MarketConfig:
        """Die Sitzung muss ohne Rest in Kerzen aufgehen.

        390 Minuten regulaere Sitzung ergeben genau zwei 195-Minuten-Kerzen.
        Eine Konfiguration, die das verletzt, waere fachlich sinnlos.
        """
        if self.regular_session_minutes % self.timeframe_minutes != 0:
            raise ValueError(
                f"regular_session_minutes ({self.regular_session_minutes}) muss ein "
                f"Vielfaches von timeframe_minutes ({self.timeframe_minutes}) sein"
            )
        candles_per_session = self.regular_session_minutes // self.timeframe_minutes
        if self.daily_candle_index > candles_per_session:
            raise ValueError(
                f"daily_candle_index ({self.daily_candle_index}) liegt ausserhalb der "
                f"{candles_per_session} Kerzen einer regulaeren Sitzung"
            )
        return self


class IndicatorConfig(_Section):
    """Indikator-Parameter -- GATE G1, fachlich freigegeben.

    Werte siehe docs/requirements/g1-pruefvorlage.md, Abschnitt 1.2 und 1.3,
    und docs/adr/0010-gate-g1-freigegeben.md. Alle Felder bleiben
    Pflichtfelder ohne Default: Eine Konfiguration ohne diesen Abschnitt soll
    weiterhin mit einem klaren Fehler abbrechen statt still mit geratenen
    Werten zu rechnen (Doc 10, Paragraph 6.4).
    """

    rsi_length: PositiveInt
    rsi_method: Literal["wilder", "sma", "ema"]
    rsi_ma_length: PositiveInt
    rsi_ma_type: Literal["sma", "ema", "wilder"]
    fast_ema_length: PositiveInt
    slow_ema_length: PositiveInt
    warmup_candles: PositiveInt


class IbkrWatchlistEntryConfig(_Section):
    """Eine ueberwachte Aktie mit ihrem IBKR-Kontraktzuschnitt.

    ``SMART`` ist IBKRs Smart-Routing-Ziel und fuer US-Aktien der Normalfall;
    beide Werte bleiben trotzdem konfigurierbar, damit eine Aktie an einer
    bestimmten Boerse angefordert werden kann.
    """

    symbol: str = Field(min_length=1)
    exchange: str = "SMART"
    currency: str = "USD"


class IbkrConfig(_Section):
    """Zugang zur TWS-API (ADR 0014).

    Enthaelt keine Geheimnisse: Die TWS-API kennt keinen Schluessel, die
    Berechtigung haengt an der angemeldeten TWS-Sitzung selbst.
    """

    host: str = "127.0.0.1"
    port: PositiveInt = 7496
    client_id: PositiveInt = 17
    """Muss sich von der Client-ID jeder anderen Anwendung an derselben
    TWS-Instanz unterscheiden (ADR 0013, Koexistenz mit der Trade Automation
    Toolbox: dort Client-ID 99)."""
    connect_timeout_seconds: PositiveInt = 15
    native_bar_minutes: PositiveInt = 15
    """Native Bar-Groesse, aus der die 195-Minuten-Kerzen gebildet werden."""
    history_duration: str = "10 D"
    """Zeitraum je Abruf in IBKR-Schreibweise. Der 5-Jahres-Backfill laeuft
    nicht ueber diesen Wert, sondern als eigener Batch-Job mit Chunking
    (ADR 0014, Einschraenkung E3)."""
    watchlist: tuple[IbkrWatchlistEntryConfig, ...] = ()


class MarketDataConfig(_Section):
    """Auswahl des Marktdatenanbieters.

    Der Standard bleibt bewusst ``fixture``: Ein Start ohne laufende TWS soll
    weiterhin funktionieren, und die produktive Anbindung wird ausdruecklich
    eingeschaltet, nicht stillschweigend vorausgesetzt.
    """

    provider: Literal["fixture", "ibkr"] = "fixture"
    ibkr: IbkrConfig = IbkrConfig()


class ScreeningConfig(_Section):
    """Kandidatenregel.

    Diese Werte haengen nicht von Gate G1 ab: Die Regel 'mindestens N der drei
    Signale innerhalb der letzten M abgeschlossenen Kerzen' ist unabhaengig von
    der mathematischen Definition der einzelnen Signale.
    """

    required_signal_count: PositiveInt = 2
    signal_lookback_previous_candles: PositiveInt = 5
    """Anzahl zusaetzlicher, vorheriger Kerzen. Die aktuelle Kerze kommt immer
    und unabhaengig davon hinzu -- das Fenster umfasst also insgesamt
    ``signal_lookback_previous_candles + 1`` Kerzen (G1-Pruefvorlage,
    Abschnitt 3.2)."""
    direction: Literal["LONG", "SHORT"] = "LONG"


class BacktestingConfig(_Section):
    """Historische Signalbewertung (Doc 10, Paragraph 6.6)."""

    history_years: PositiveInt = 5
    horizons: tuple[PositiveInt, ...] = (5, 10, 20)
    cooldown_candles: PositiveInt = 5
    minimum_sample_size: PositiveInt = 10
    normal_confidence_sample_size: PositiveInt = 30

    @model_validator(mode="after")
    def _thresholds_must_be_ordered(self) -> BacktestingConfig:
        if self.normal_confidence_sample_size < self.minimum_sample_size:
            raise ValueError(
                "normal_confidence_sample_size darf nicht kleiner als "
                "minimum_sample_size sein"
            )
        if not self.horizons:
            raise ValueError("horizons darf nicht leer sein")
        return self


class EarningsFilterConfig(_Section):
    """Ausschlussfenster vor Quartalszahlen (Doc 10, Paragraph 6.5)."""

    minimum_exclusion_candles: PositiveInt = 10
    maximum_exclusion_candles: PositiveInt = 20
    configured_exclusion_candles: PositiveInt = 20

    @model_validator(mode="after")
    def _configured_value_must_be_within_range(self) -> EarningsFilterConfig:
        if not (
            self.minimum_exclusion_candles
            <= self.configured_exclusion_candles
            <= self.maximum_exclusion_candles
        ):
            raise ValueError(
                f"configured_exclusion_candles ({self.configured_exclusion_candles}) muss "
                f"zwischen minimum_exclusion_candles ({self.minimum_exclusion_candles}) und "
                f"maximum_exclusion_candles ({self.maximum_exclusion_candles}) liegen"
            )
        return self


class DataAvailabilityConfig(_Section):
    """Wartelogik nach Kerzenschluss (Risiko R9 des Entwicklungsplans).

    Der Lauf startet ab dem Kerzenschluss, rechnet aber erst, wenn die
    geschlossene Kerze beim Anbieter nachweislich vollstaendig vorliegt.
    """

    grace_period_seconds: PositiveInt = 60
    poll_interval_seconds: PositiveInt = 30
    max_wait_seconds: PositiveInt = 1800

    @model_validator(mode="after")
    def _wait_budget_must_allow_polling(self) -> DataAvailabilityConfig:
        if self.max_wait_seconds <= self.grace_period_seconds:
            raise ValueError(
                "max_wait_seconds muss groesser als grace_period_seconds sein, "
                "sonst findet kein einziger Pollversuch statt"
            )
        return self


class NotificationsConfig(_Section):
    """Benachrichtigungsverhalten (Doc 10, Paragraph 6.13)."""

    send_when_no_candidates: bool = False
    channel: Literal["dry_run", "telegram", "pushover"] = "dry_run"


class ScoringConfig(_Section):
    """Versionierung der Bewertungslogik (Doc 10, Paragraph 6.11)."""

    swing_version: str = "1.0"
    long_term_version: str = "1.0"


class LoggingConfig(_Section):
    """Strukturiertes Logging (Doc 10, Paragraph 12)."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    format: Literal["json", "console"] = "json"


class AppConfig(_Section):
    """Wurzel der fachlichen Konfiguration."""

    market: MarketConfig = MarketConfig()
    market_data: MarketDataConfig = MarketDataConfig()
    screening: ScreeningConfig = ScreeningConfig()
    backtesting: BacktestingConfig = BacktestingConfig()
    earnings_filter: EarningsFilterConfig = EarningsFilterConfig()
    data_availability: DataAvailabilityConfig = DataAvailabilityConfig()
    notifications: NotificationsConfig = NotificationsConfig()
    scoring: ScoringConfig = ScoringConfig()
    logging: LoggingConfig = LoggingConfig()
    indicators: IndicatorConfig | None = None

    @model_validator(mode="after")
    def _native_bars_must_form_whole_candles(self) -> AppConfig:
        """Die native Bar-Groesse muss die Kerze ohne Rest fuellen.

        Sonst waere keine 195-Minuten-Kerze je vollstaendig, und der Screener
        haette dauerhaft keine einzige auswertbare Kerze -- ein Fehler, der
        erst im Betrieb auffiele.
        """
        native = self.market_data.ibkr.native_bar_minutes
        if self.market.timeframe_minutes % native != 0:
            raise ValueError(
                f"native_bar_minutes ({native}) muss timeframe_minutes "
                f"({self.market.timeframe_minutes}) ohne Rest teilen"
            )
        return self

    def require_indicators(self) -> IndicatorConfig:
        """Liefert die Indikator-Parameter oder bricht mit einem eindeutigen Hinweis ab.

        Gate G1 ist fachlich freigegeben (docs/adr/0010-gate-g1-freigegeben.md);
        ``config/default.yaml`` enthaelt den Abschnitt ``indicators`` bereits.
        Diese Methode bleibt trotzdem bestehen: Eine Konfiguration, die den
        Abschnitt dennoch nicht enthaelt (z. B. eine unvollstaendige eigene
        Config-Datei), soll weiterhin mit einem klaren Fehler abbrechen statt
        mit fehlenden Parametern zu rechnen.
        """
        if self.indicators is None:
            raise GateNotClearedError(
                "Der Abschnitt 'indicators' fehlt in dieser Konfiguration. Gate G1 ist "
                "fachlich freigegeben (RSI-Laenge und -Methode, RSI-Moving-Average, "
                "EMA-Laengen sind festgelegt, siehe docs/requirements/g1-pruefvorlage.md) "
                "-- die Werte muessen aber im Abschnitt 'indicators' dieser Konfiguration "
                "hinterlegt sein."
            )
        return self.indicators


class Secrets(BaseSettings):
    """Geheimnisse ausschliesslich aus Umgebungsvariablen (Doc 10, Paragraph 13).

    Alle Felder sind optional, weil in Sprint 0 noch kein externer Dienst
    angebunden ist. Sobald ein Adapter ein Geheimnis braucht, fordert er es
    ueber ``require`` an und erhaelt bei Fehlen einen klaren Fehler statt einer
    stillen ``None``.
    """

    model_config = SettingsConfigDict(
        env_prefix="ATA_",
        env_file=None,
        extra="ignore",
        frozen=True,
    )

    database_url: SecretStr | None = None
    session_secret: SecretStr | None = None
    llm_api_key: SecretStr | None = None
    market_data_api_key: SecretStr | None = None
    notification_token: SecretStr | None = None

    def require(self, field_name: str) -> str:
        """Liefert den Klartextwert eines Geheimnisses oder scheitert eindeutig."""
        if field_name not in type(self).model_fields:
            raise KeyError(f"Unbekanntes Secret-Feld: {field_name}")
        value: SecretStr | None = getattr(self, field_name)
        if value is None:
            env_name = f"{self.model_config.get('env_prefix', '')}{field_name}".upper()
            raise MissingSecretError(
                f"Das Secret '{field_name}' ist nicht gesetzt. Erwartet wird die "
                f"Umgebungsvariable {env_name}."
            )
        return value.get_secret_value()
