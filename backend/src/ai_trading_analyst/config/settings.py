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

from datetime import time
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeFloat = Annotated[float, Field(ge=0)]


def _parse_time(value: str) -> time:
    hours, minutes = (int(part) for part in value.split(":"))
    return time(hours, minutes)


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
    early_session_close: str = "13:00"
    """Uhrzeit, zu der die Boerse an verkuerzten Handelstagen schliesst.

    Kein Kalender, sondern eine feste Konvention der US-Aktienmaerkte: Am Tag
    nach Thanksgiving, am 24.12. und am 3.7. wird um 13:00 Ortszeit
    geschlossen. Nur mit dieser Uhrzeit laesst sich ein regulaer verkuerzter
    Handelstag von einem Datenabriss unterscheiden -- beide liefern eine
    unvollstaendige letzte Kerze, aber nur der verkuerzte Tag endet genau
    hier.
    """

    def session_open_time(self) -> time:
        """Der Sitzungsbeginn als Uhrzeit.

        Die Gueltigkeit ist bereits beim Laden geprueft, dieser Aufruf kann
        deshalb nicht mehr scheitern.
        """
        return _parse_time(self.regular_session_open)

    def early_close_time(self) -> time:
        return _parse_time(self.early_session_close)

    @field_validator("regular_session_open", "early_session_close")
    @classmethod
    def _must_be_a_time(cls, value: str, info: ValidationInfo) -> str:
        """Prueft das Format sofort beim Laden.

        Ein "09:30:00" oder "9.30" wuerde sonst erst spaeter und an einer
        Stelle auffallen, die den Konfigurationsschluessel nicht mehr kennt.
        """
        try:
            _parse_time(value)
        except ValueError as error:
            raise ValueError(
                f"{info.field_name} muss die Form 'HH:MM' haben, ist aber '{value}'"
            ) from error
        return value

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
    history_duration: str = "1 Y"
    """Zeitraum je Abruf in IBKR-Schreibweise.

    Der Wert muss den Warm-up von ``indicators.warmup_candles`` abdecken: Bei
    250 Kerzen und zwei Kerzen je Handelstag sind das 125 Handelstage, also
    rund ein halbes Jahr allein fuer den Vorlauf. Ein zu kurzer Zeitraum
    fuehrt nicht zu einem Fehler, sondern dazu, dass jede Aktie dauerhaft als
    ``UNKNOWN_DATA_INCOMPLETE`` mit dem Grund ``warmup_insufficient``
    zurueckkommt -- der Standard ist deshalb bewusst grosszuegig.

    Der 5-Jahres-Backfill laeuft nicht ueber diesen Wert, sondern als eigener
    Batch-Job mit Chunking (ADR 0014, Einschraenkung E3)."""
    watchlist_directory: str = "watchlists"
    """Verzeichnis mit den exportierten Watchlisten (``*.txt``), relativ zum
    Projektwurzelverzeichnis. Alle Dateien darin werden eingelesen und
    Mehrfachnennungen zusammengefasst."""
    minimum_request_interval_seconds: NonNegativeFloat = 11.0
    """Mindestabstand zwischen zwei Historienanfragen.

    IBKR laesst 60 Anfragen je zehn Minuten zu und sperrt bei Ueberschreitung
    die Verbindung, nicht nur die einzelne Anfrage. 11 Sekunden bleiben mit
    Sicherheitsabstand darunter. Bei einer dreistelligen Symbolzahl bestimmt
    dieser Wert die Laufzeit -- 0 schaltet die Bremse ab und ist nur fuer
    kurze Einzelabfragen sinnvoll."""


class MarketDataConfig(_Section):
    """Auswahl des Marktdatenanbieters.

    Der Standard bleibt bewusst ``fixture``: Ein Start ohne laufende TWS soll
    weiterhin funktionieren, und die produktive Anbindung wird ausdruecklich
    eingeschaltet, nicht stillschweigend vorausgesetzt.
    """

    provider: Literal["fixture", "ibkr"] = "fixture"
    source: Literal["live", "stored"] = "stored"
    """Woher die nativen Bars kommen -- vom Anbieter oder aus dem Bestand.

    ``stored`` ist der Standard, weil er die Eigenschaft mitbringt, auf die
    es beim regulaeren Lauf ankommt: Dieselbe Analyse laesst sich morgen
    erneut rechnen und liefert dasselbe Ergebnis. IBKRs Ein-Jahres-Fenster
    wandert mit der Uhr; schon zwei Laeufe desselben Tages ergaben
    unterschiedlich viele Kerzen. Ausserdem braucht der Lauf dann keine
    angemeldete TWS -- nur der Backfill braucht sie (ADR 0014, E2).

    Voraussetzung ist ein gefuellter Bestand. Fehlt er, nennt die Meldung den
    Backfill beim Namen, statt in einer Ersatzerklaerung zu enden.

    ``live`` fragt bei jedem Lauf den Anbieter. Fuer ``fixture`` ohne
    Bedeutung -- dort liefert der Anbieter fertige Kerzen.
    """
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


class FinnhubConfig(_Section):
    """Zugang zum Earnings-Kalender (ADR 0017, ADR 0020).

    Kein Geheimnis hier -- der Schluessel kommt ausschliesslich aus
    ``Secrets.finnhub_api_key``.
    """

    base_url: str = "https://finnhub.io/api/v1"
    request_timeout_seconds: PositiveInt = 10
    lookahead_calendar_days: PositiveInt = 30
    """Kalendertage je Anfrage -- grosszuegig ueber dem groessten
    konfigurierbaren Kerzenfenster (20 Kerzen / 2 je Tag = 10 Handelstage),
    um Wochenenden abzudecken. Bleibt weit unter der 1500-Treffer-Kuerzung
    aus ADR 0017 L4, da je Symbol angefragt wird."""


class EarningsFilterConfig(_Section):
    """Ausschlussfenster vor Quartalszahlen (Doc 10, Paragraph 6.5)."""

    minimum_exclusion_candles: PositiveInt = 10
    maximum_exclusion_candles: PositiveInt = 20
    configured_exclusion_candles: PositiveInt = 20
    provider: Literal["fixture", "finnhub"] = "fixture"
    """Wie ``market_data.provider``: ``fixture`` bleibt Standard, damit Start
    und Tests ohne ``ATA_FINNHUB_API_KEY`` funktionieren."""
    finnhub: FinnhubConfig = FinnhubConfig()

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


class ModelProfile(_Section):
    """Modell fuer eine Analyseaufgabe, mit Ausweichmodell (ADR 0021).

    Der Fallback greift nur bei technischem Versagen (Timeout, Ratenlimit,
    Providerfehler) -- nie als stille Qualitaetsminderung ohne Kennzeichnung.
    Welches Modell tatsaechlich geantwortet hat, gehoert an jedes KI-Ergebnis,
    nicht nur ins Log (Doc 10, Paragraph 12).
    """

    model: str
    fallback_model: str | None = None


class LlmConfig(_Section):
    """Modellprofile je Analyseaufgabe (CLAUDE.md "KI-Anbindung", ADR 0021).

    ``provider`` ist heute immer ``anthropic`` -- als Literal statt als freies
    Feld, damit ein Tippfehler beim Start auffaellt statt still zu einem
    falschen Adapter zu fuehren (Muster wie ``MarketDataConfig.provider``).
    """

    provider: Literal["anthropic"] = "anthropic"
    research: ModelProfile = ModelProfile(model="claude-sonnet-5")
    technical: ModelProfile = ModelProfile(model="claude-haiku-4-5-20251001")
    fundamental: ModelProfile = ModelProfile(model="claude-haiku-4-5-20251001")
    report: ModelProfile = ModelProfile(model="claude-haiku-4-5-20251001")


class ResearchPricingConfig(_Section):
    """Preise fuer die Kostenschaetzung im Log (ADR 0021 Budget).

    Rein informativ und **von Hand gepflegt** -- die Anwendung fragt keine
    Preisliste ab. Vorbelegt mit den Sonnet-5-Einfuehrungspreisen; die
    Websuche kostet zusaetzlich zu den Token (10 USD je 1000 Suchen).
    Token allein beantworten die eigentliche Betreiberfrage nicht ("was
    kostet mich ein Lauf"), ein Schaetzwert schon.
    """

    input_usd_per_million: NonNegativeFloat = 2.0
    output_usd_per_million: NonNegativeFloat = 10.0
    usd_per_search: NonNegativeFloat = 0.01


class ResearchConfig(_Section):
    """Recherchequellen und Kostenbudget des Research Agent (ADR 0023).

    ``fixture`` bleibt Standard, damit Start und Tests ohne
    ``ATA_LLM_API_KEY`` funktionieren (Muster wie
    ``earnings_filter.provider``).

    Die Budgetwerte sind nicht kosmetisch: ``web_search``/``web_fetch`` sind
    serverseitige Werkzeuge, deren Schleife bis zu zehn Iterationen *innerhalb
    einer einzigen Anfrage* laeuft, und der angesammelte Kontext wird bei
    jeder Iteration erneut als Eingabe verrechnet. Ein ungebremster Abruf
    eines SEC-Filings (~125.000 Token) schlaegt deshalb vielfach zu Buche.
    ``max_fetch_content_tokens`` ist der wirksamste Hebel dagegen;
    ``max_fetches`` mal dieser Wert ist das eigentliche Kostenbudget.

    ``fetch_allowed_domains`` gilt **nur fuer den Abruf**, nicht fuer die
    Suche: Eine Allowlist auf der Suche laesst kaum Treffer uebrig, das Modell
    verbrennt sein Suchkontingent, und ``web_fetch`` darf danach nichts mehr
    holen (es erreicht ausschliesslich URLs, die vorher im Kontext standen).
    Breit suchen, eng vertiefen -- ADR 0023, Abschnitt "Kostenkontrolle und
    Reichweite der Allowlist".

    Eine Domain, die Anthropics Crawler aussperrt, laesst die *gesamte*
    Anfrage mit einem 400 scheitern -- nicht nur den einzelnen Abruf. Reuters
    und AP sind deshalb nicht in der Voreinstellung; eine neue Domain gehoert
    vor der Aufnahme einmal durch einen echten Lauf.
    """

    provider: Literal["fixture", "anthropic"] = "fixture"
    max_searches: PositiveInt = 5
    max_fetches: PositiveInt = 3
    max_fetch_content_tokens: PositiveInt = 8000
    max_input_tokens_per_symbol: PositiveInt = 150_000
    max_output_tokens: PositiveInt = 16_000
    """Deckelt Denken **und** Antworttext gemeinsam: Auf Sonnet 5 laeuft ein
    Aufruf ohne ``thinking``-Feld mit adaptivem Denken, und beides teilt sich
    dasselbe Budget. Zu knapp bemessen schneidet es den Werkzeugaufruf ab,
    statt Kosten zu sparen."""
    request_timeout_seconds: PositiveInt = 300
    """Ohne eigenen Wert gilt der SDK-Standard von 600 Sekunden Lesezeit mal
    zwei Wiederholungen -- eine haengende Anfrage blockierte damit einen der
    nebenlaeufigen Arbeiter fast eine Stunde (Muster
    ``FinnhubConfig.request_timeout_seconds``)."""
    fetch_allowed_domains: tuple[str, ...] = (
        "sec.gov",
        "prnewswire.com",
        "businesswire.com",
        "globenewswire.com",
        "nasdaq.com",
    )
    pricing: ResearchPricingConfig = ResearchPricingConfig()


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


class SchedulerConfig(_Section):
    """Zeitsteuerung des taeglichen Laufs (ADR 0019).

    Die Aufgabenplanung startet den Dispatcher alle 15 Minuten in einem
    Abendfenster; entschieden wird hier, in der Zeitzone der Boerse.
    """

    safety_buffer_seconds: PositiveInt = 300
    """Wartezeit nach Kerzenschluss, bevor ueberhaupt gefragt wird.

    Die Kerze ist um 12:45 New Yorker Zeit zu, beim Anbieter aber nicht
    zwingend im selben Augenblick vollstaendig. 300 Sekunden ergeben einen
    fruehesten Start um 12:50.

    Nicht zu verwechseln mit ``data_availability.grace_period_seconds``: Jener
    Abschnitt beschreibt ein Polling waehrend eines laufenden Abrufs und wird
    vom Dispatcher nicht verwendet -- bei ihm uebernimmt der 15-Minuten-Takt
    das Wiederholen.
    """
    max_catch_up_seconds: PositiveInt = 2 * 3600
    """Wie lange ein verpasster Lauf noch nachgeholt werden darf.

    Danach gilt er als ausgefallen. Zwei Stunden ab dem fruehesten Start um
    12:50 ergeben eine Frist um 14:50 New Yorker Zeit; eine Analyse noch
    spaeter am Tag bildete den Handelstag kaum noch ab.

    Der Wert muss **innerhalb** des Zeitfensters liegen, in dem die
    Aufgabenplanung startet (README, Abschnitt "Der automatische Tageslauf").
    Mit einer Frist jenseits des letzten Starts bliebe ein ausgefallener Lauf
    am selben Abend unbemerkt -- er wird zwar am naechsten Start noch
    gemeldet, aber erst Stunden spaeter.
    """


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
    llm: LlmConfig = LlmConfig()
    research: ResearchConfig = ResearchConfig()
    data_availability: DataAvailabilityConfig = DataAvailabilityConfig()
    scheduler: SchedulerConfig = SchedulerConfig()
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


def project_env_file() -> Path:
    """Pfad zur ``.env`` im Projektwurzelverzeichnis.

    Absolut, nicht relativ: Die Kommandos werden aus ``backend/`` gestartet,
    die Datei liegt eine Ebene darueber. Ein relativer Name haette je nach
    Arbeitsverzeichnis mal gegriffen und mal nicht.
    """
    # settings.py -> config -> ai_trading_analyst -> src -> backend -> Wurzel
    return Path(__file__).resolve().parents[4] / ".env"


class Secrets(BaseSettings):
    """Geheimnisse aus der Umgebung, ersatzweise aus einer lokalen ``.env``.

    Doc 10, Paragraph 13 verlangt, dass Geheimnisse nicht im Repository
    stehen. Eine ``.env`` erfuellt das: Sie ist ueber ``.gitignore``
    ausgeschlossen, ``.env.example`` enthaelt nur Platzhalter. Ohne sie muesste
    auf dem Windows-Server vor jedem Lauf von Hand
    ``$env:ATA_DATABASE_URL`` gesetzt werden -- eine Fehlerquelle bei einem
    Betrieb, der nach jedem Neustart ohnehin von Hand angestossen wird
    (ADR 0018).

    Eine gesetzte echte Umgebungsvariable gewinnt gegenueber der Datei. Alle
    Felder sind optional; benoetigt ein Adapter ein Geheimnis, fordert er es
    ueber ``require`` an und erhaelt bei Fehlen einen klaren Fehler statt einer
    stillen ``None``.
    """

    model_config = SettingsConfigDict(
        env_prefix="ATA_",
        env_file=project_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    database_url: SecretStr | None = None
    session_secret: SecretStr | None = None
    llm_api_key: SecretStr | None = None
    market_data_api_key: SecretStr | None = None
    notification_token: SecretStr | None = None
    finnhub_api_key: SecretStr | None = None

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
