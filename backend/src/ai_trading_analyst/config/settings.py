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
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveFloat = Annotated[float, Field(gt=0)]
NonNegativeFloat = Annotated[float, Field(ge=0)]


def _parse_time(value: str) -> time:
    hours, minutes = (int(part) for part in value.split(":"))
    return time(hours, minutes)


def _pruefe_gewichtssumme(section: BaseModel, name: str) -> None:
    """Komponentengewichte muessen sich auf 1 summieren.

    Sonst waere die ausgewiesene Datenabdeckung eine andere Zahl als die
    tatsaechliche: Der Aggregator normiert auf die Summe der vorhandenen
    Gewichte, und ein Gesamtgewicht von 0,9 machte aus einer vollstaendigen
    Rechnung eine, die vollstaendig aussieht und es nicht ist.
    """
    summe = sum(float(wert) for wert in section.model_dump().values())
    if abs(summe - 1.0) > 1e-9:
        raise ValueError(f"{name}: die Gewichte summieren sich auf {summe}, noetig ist 1.0")


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
                "normal_confidence_sample_size darf nicht kleiner als minimum_sample_size sein"
            )
        if not self.horizons:
            raise ValueError("horizons darf nicht leer sein")
        return self


class FinnhubConfig(_Section):
    """Zugang zum Finnhub-Konto (ADR 0017, ADR 0043).

    **Ein eigener Abschnitt und nicht mehr unter ``earnings_filter``:** Seit
    ADR 0043 werden zwei Endpunkte desselben Kontos genutzt -- der
    Earnings-Kalender und die Analystenempfehlungen. Host und Zeitgrenze
    gehoeren beiden; sie unter einem der beiden Nutzer zu fuehren hiesse, den
    anderen dort mitlesen zu lassen.

    Was **nicht** hierher gehoert, ist alles Endpunktspezifische: Das
    Kalenderfenster steht bei ``earnings_filter``, die Zahl der Monatsstaende
    bei ``analyst_ratings``.

    Kein Geheimnis hier -- der Schluessel kommt ausschliesslich aus
    ``Secrets.finnhub_api_key``.
    """

    base_url: str = "https://finnhub.io/api/v1"
    request_timeout_seconds: PositiveInt = 10
    max_requests_per_second: PositiveFloat = 0.8
    """Gemessen, nicht geraten: Der Messlauf ueber die Watchliste vom
    2026-08-31 lief mit rund einer Anfrage je Sekunde und verlor vier von
    192 Symbolen an ``429 Too Many Requests``. Die Gratis-Stufe deckelt bei
    60 je Minute, also genau eine je Sekunde -- 0,8 haelt Abstand, aus
    demselben Grund wie bei EDGAR: Eine Drossel, die genau auf der Grenze
    liegt, ueberschreitet sie bei jeder Ungenauigkeit der Uhr.

    Gilt fuer **beide** Endpunkte desselben Kontos, denn das Limit gilt fuer
    das Konto und nicht fuer den Endpunkt."""


class EdgarConfig(_Section):
    """Zugang zu den SEC-Einreichungen (ADR 0022, ADR 0032).

    EDGAR verlangt keinen Schluessel. Die von der SEC im ``User-Agent``
    geforderte Kontaktadresse steht trotzdem **nicht hier**, sondern als
    ``ATA_EDGAR_CONTACT`` bei den Geheimnissen -- siehe ``Secrets``.
    """

    base_url: str = "https://data.sec.gov"
    index_base_url: str = "https://www.sec.gov"
    """Getrennt vom Datenendpunkt, weil das Symbolverzeichnis unter
    ``www.sec.gov`` liegt und die Fakten unter ``data.sec.gov``."""
    request_timeout_seconds: PositiveInt = 60
    """Grosszuegig: ``companyfacts`` ist je Aktie mehrere Megabyte gross
    (ADR 0032 L6)."""
    max_requests_per_second: PositiveFloat = 8.0
    """Unter der von der SEC genannten Obergrenze von zehn. Der Abstand ist
    Absicht -- eine Drossel, die genau auf der Grenze liegt, ueberschreitet
    sie bei jeder Ungenauigkeit der Uhr."""

    @model_validator(mode="after")
    def _rate_must_respect_sec_limit(self) -> EdgarConfig:
        if self.max_requests_per_second > 10:
            raise ValueError(
                "max_requests_per_second ueber 10 verstoesst gegen die Vorgabe der SEC"
            )
        return self


class FundamentalsConfig(_Section):
    """Deterministische Fundamentalanalyse (ADR 0032)."""

    provider: Literal["fixture", "edgar"] = "fixture"
    """Wie ``market_data.provider``: ``fixture`` bleibt Standard, damit Start
    und Tests ohne Netzzugriff funktionieren."""
    edgar: EdgarConfig = EdgarConfig()
    growth_years: PositiveInt = 3
    """Spanne der Wachstumsraten in Geschaeftsjahren. Wird vollstaendig
    verlangt; ein Unternehmen mit kuerzerer Historie liefert die
    Wachstumsraten nicht, statt sie ueber eine andere Spanne zu rechnen."""


class OptionsConfig(_Section):
    """Optionsanalyse: Cash Secured Puts (Doc 10, Paragraph 6.10; ADR 0048)."""

    provider: Literal["fixture", "ibkr"] = "fixture"
    """Wie ``fundamentals.provider``: ``fixture`` bleibt Standard, damit Start
    und Tests ohne laufende TWS und ohne Optionsmarktdaten-Abo funktionieren."""
    market_data_type: Literal[1, 2, 3, 4] = 2
    """IBKRs Marktdatenmodus: ``1`` live, ``2`` "frozen", ``3`` verzoegert,
    ``4`` verzoegert und "frozen".

    Der Tageslauf steht auf der **ersten** 195-Minuten-Kerze
    (``market.daily_candle_index``), die um 12:45 New Yorker Zeit schliesst.
    Der Optionsmarkt ist waehrend des gesamten Laufzeitfensters offen --
    einschliesslich der zweistuendigen Nachholfrist.

    Vorgabe ``2`` trotzdem: "frozen" verhaelt sich bei offener Boerse wie
    live und liefert bei geschlossener den letzten festgestellten Stand statt
    nichts. Das kostet im Regelfall nichts und macht eine Einzelprobe am
    Abend brauchbar."""
    min_days_to_expiration: PositiveInt = 21
    max_days_to_expiration: PositiveInt = 45
    """Zielfenster der Restlaufzeit in Kalendertagen (Entscheidung des
    Projektinhabers, 2026-08-31). Ausgewaehlt wird der Verfallstermin, der
    der Mitte des Fensters am naechsten liegt."""
    min_delta: NonNegativeFloat = 0.10
    max_delta: NonNegativeFloat = 0.40
    """Zielband des Delta-**Betrags**, angewandt erst **nach** dem Abruf: Vor
    der Notierung ist das Delta nicht bekannt."""
    min_moneyness: NonNegativeFloat = 0.80
    max_moneyness: NonNegativeFloat = 0.99
    """Vorauswahl der Strikes als Anteil des Kurses. Begrenzt nur, wie viele
    Kontrakte ueberhaupt notiert werden -- entschieden wird ueber das
    Delta-Band."""
    max_strikes: PositiveInt = 12
    max_suggestions: PositiveInt = 3
    max_relative_spread: NonNegativeFloat = 0.10
    min_open_interest: PositiveInt = 100
    min_volume: PositiveInt = 10
    """Liquiditaetsschwellen. **Gesetzt, nicht gemessen** (ADR 0048): Sie
    tragen keinen Teilwert, sondern erzeugen Warnungen. Doc 10 verlangt
    genau das -- unzureichende Liquiditaet wird nicht verschwiegen, steht
    aber nie an erster Stelle."""

    @model_validator(mode="after")
    def _baender_muessen_aufsteigen(self) -> OptionsConfig:
        if self.min_days_to_expiration > self.max_days_to_expiration:
            raise ValueError(
                f"min_days_to_expiration ({self.min_days_to_expiration}) darf nicht groesser "
                f"als max_days_to_expiration ({self.max_days_to_expiration}) sein"
            )
        if self.min_delta > self.max_delta:
            raise ValueError(
                f"min_delta ({self.min_delta}) darf nicht groesser als max_delta "
                f"({self.max_delta}) sein"
            )
        if self.min_moneyness > self.max_moneyness:
            raise ValueError(
                f"min_moneyness ({self.min_moneyness}) darf nicht groesser als max_moneyness "
                f"({self.max_moneyness}) sein"
            )
        if self.max_moneyness > 1.0:
            raise ValueError(
                "max_moneyness ueber 1.0 waere ein Put im Geld -- die Optionsanalyse "
                "bewertet ausschliesslich Cash Secured Puts aus dem Geld (Doc 08)"
            )
        return self


class EarningsFilterConfig(_Section):
    """Ausschlussfenster vor Quartalszahlen (Doc 10, Paragraph 6.5)."""

    minimum_exclusion_candles: PositiveInt = 10
    maximum_exclusion_candles: PositiveInt = 20
    configured_exclusion_candles: PositiveInt = 20
    provider: Literal["fixture", "finnhub"] = "fixture"
    """Wie ``market_data.provider``: ``fixture`` bleibt Standard, damit Start
    und Tests ohne ``ATA_FINNHUB_API_KEY`` funktionieren."""
    lookahead_calendar_days: PositiveInt = 30
    """Kalendertage je Anfrage -- grosszuegig ueber dem groessten
    konfigurierbaren Kerzenfenster (20 Kerzen / 2 je Tag = 10 Handelstage),
    um Wochenenden abzudecken. Bleibt weit unter der 1500-Treffer-Kuerzung
    aus ADR 0017 L4, da je Symbol angefragt wird.

    Stand bis ADR 0043 unter ``earnings_filter.finnhub``. Der Wert beschreibt
    den Kalenderendpunkt, nicht den Zugang -- er bleibt deshalb hier, waehrend
    Host und Zeitgrenze in den Abschnitt ``finnhub`` gewandert sind."""

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


class AnalystRatingsConfig(_Section):
    """Analystenempfehlungen (Doc 10, Paragraph 6.12 Punkt 9; ADR 0043)."""

    provider: Literal["fixture", "finnhub"] = "fixture"
    """Wie ``earnings_filter.provider``: ``fixture`` bleibt Standard, damit
    Start und Tests ohne ``ATA_FINNHUB_API_KEY`` funktionieren."""
    months: PositiveInt = 4
    """Wie viele Monatsstaende hoechstens uebernommen werden.

    Vier, weil der Endpunkt sie ohne Zusatzkosten mitliefert und die
    **Veraenderung** der Analystenmeinung ein eigenstaendiges Signal ist
    (ADR 0043) -- ein einzelner Momentanstand sagt weniger als eine
    Verschiebung von ``hold`` nach ``buy``. Der Endpunkt selbst kennt keinen
    Zeitraumparameter; begrenzt wird im Adapter."""


class TechnicalAnalysisConfig(_Section):
    """Deterministische Chartauswertung (Doc 10, Paragraph 6.8; ADR 0025).

    Nicht Teil von Gate G1: Diese Werte beeinflussen weder eine Signalformel
    noch die Kandidatenentscheidung. Sie bestimmen ausschliesslich, wie die
    Lage beschrieben wird, in der eine bereits gefallene Entscheidung
    zustande kam.

    Die Voreinstellungen sind Konventionen, keine gemessenen Optima -- ADR
    0025 nennt die Ueberlegung hinter jeder einzelnen. Sie sind bewusst
    konfigurierbar, damit sie sich an echten Charts nachziehen lassen, ohne
    dass Code geaendert werden muss.
    """

    pivot_reach: PositiveInt = 3
    zone_tolerance_pct: float = 0.015
    min_touches: PositiveInt = 2
    moderate_pivot_count: PositiveInt = 3
    strong_pivot_count: PositiveInt = 5
    max_zones_per_side: PositiveInt = 3
    history_candles: PositiveInt = 250
    atr_length: PositiveInt = 14
    trend_lookback: PositiveInt = 10
    trend_flat_pct: float = 0.005
    extremes_lookback: PositiveInt = 40

    @model_validator(mode="after")
    def _ranges_must_be_usable(self) -> TechnicalAnalysisConfig:
        """Prueft, was Pydantic ueber ``PositiveInt`` hinaus nicht sieht.

        Die Domain-Parameter pruefen dasselbe noch einmal. Doppelt und
        absichtlich: Hier faellt eine unbrauchbare Konfigurationsdatei beim
        Start auf, dort auch ein Programmierfehler beim direkten Aufruf des
        Domain-Kerns.
        """
        # Bruchteile, keine Prozentwerte: 0.015 sind 1,5 %. Die obere
        # Grenze faengt genau diese Verwechslung ab -- ohne sie ergaebe ein
        # Zahlendreher keine Fehlermeldung, sondern ein plausibel aussehendes
        # Ergebnis ohne Zonen beziehungsweise mit dauerhaftem Seitwaertstrend.
        if not 0 < self.zone_tolerance_pct < 1:
            raise ValueError(
                "zone_tolerance_pct muss ein Bruchteil zwischen 0 und 1 sein "
                f"(0.015 entspricht 1,5 %), war {self.zone_tolerance_pct}"
            )
        if not 0 <= self.trend_flat_pct < 1:
            raise ValueError(
                "trend_flat_pct muss ein Bruchteil zwischen 0 und 1 sein "
                f"(0.005 entspricht 0,5 %), war {self.trend_flat_pct}"
            )
        if not 1 <= self.moderate_pivot_count <= self.strong_pivot_count:
            raise ValueError("1 <= moderate_pivot_count <= strong_pivot_count ist verletzt")
        laengstes_fenster = max(
            2 * self.pivot_reach + 1,
            self.atr_length + 1,
            self.trend_lookback + 1,
            self.extremes_lookback,
        )
        if self.history_candles < laengstes_fenster:
            raise ValueError(
                f"history_candles ({self.history_candles}) ist kleiner als das laengste "
                f"benoetigte Fenster ({laengstes_fenster})"
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
    Preisliste ab. Vorbelegt mit den regulaeren Sonnet-5-Preisen; die
    Websuche kostet zusaetzlich zu den Token (10 USD je 1000 Suchen).
    Token allein beantworten die eigentliche Betreiberfrage nicht ("was
    kostet mich ein Lauf"), ein Schaetzwert schon.

    Die Werte spiegeln ``config/default.yaml`` und werden mit ihm zusammen
    gepflegt: Eine Konfiguration, die ``research.pricing`` weglaesst, soll
    nicht anders schaetzen als die ausgelieferte.
    """

    input_usd_per_million: NonNegativeFloat = 3.0
    output_usd_per_million: NonNegativeFloat = 15.0
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
    max_concurrent_calls: PositiveInt = 2
    """Gleichzeitige Recherche-Aufrufe. **Eigener Pool**, getrennt vom
    Technical Agent (ADR 0037, Risiko R9).

    Bewusst klein: Ein realer Aufruf dauert rund 15 Minuten und kostet
    ~0,58 USD; mehr Nebenlaeufigkeit verkuerzt nicht die Wartezeit je Aufruf,
    sondern erhoeht nur, wie viele teure Gespraeche gleichzeitig offen sind.
    Jeder Aufruf ist unabhaengig -- kein gemeinsamer veraenderlicher Zustand
    ausser dem laut Anthropic-SDK threadsicheren HTTP-Client."""
    request_timeout_seconds: PositiveInt = 900
    """Lesezeit je Anfrage. Gilt **nicht** fuer den Verbindungsaufbau, der
    steht bei ``VERBINDUNGSAUFBAU_SEKUNDEN``.

    Frueher 300. Der Lauf vom 2026-08-24 zeigte 921 Sekunden zwischen zwei
    Protokollzeilen -- 300 + 300 + ~320, also zwei abgelaufene Versuche und
    ein erfolgreicher. Genau die teuerste denkbare Form des Fehlschlags: Eine
    abgelaufene Anfrage erzeugt clientseitig keine Protokollzeile, aber
    serverseitig sind die Token angefallen. Der Wert liegt jetzt oberhalb
    dessen, was eine echte Recherche mit fuenf Websuchen braucht."""
    max_retries: NonNegativeInt = 0
    """Keine Wiederholung. Ausdruecklich statt SDK-Standard (2).

    Ein erster Entwurf liess eine Wiederholung stehen, mit der Begruendung,
    sie fange kurzlebige Fehler (429, 529) ab. Das SDK unterscheidet aber
    nicht: ``_should_retry_exception`` behandelt ``APITimeoutError`` und
    ``APIConnectionError`` bedingungslos als wiederholbar. Eine Wiederholung
    traefe damit **genau den Fall**, gegen den der lange Lesetimeout gebaut
    ist -- und zwar doppelt so teuer wie vorher: 900 s mal zwei Versuche sind
    1800 s Blockade eines von vier Plaetzen, gegen 900 s beim alten Stand
    (300 s mal drei). Der zweite Versuch startet ausserdem die serverseitige
    Werkzeugschleife von vorn, also genau die unsichtbaren Token, die die
    Protokollierung je Anfrage sichtbar machen soll.

    Ein ausgefallener Bericht kostet dagegen wenig: Er wird ``UNAVAILABLE``
    und blockiert die technische Analyse nie (CLAUDE.md)."""
    fetch_allowed_domains: tuple[str, ...] = (
        "sec.gov",
        "prnewswire.com",
        "businesswire.com",
        "globenewswire.com",
        "nasdaq.com",
    )
    max_citations: PositiveInt = 25
    """Obergrenze der gespeicherten Belege je Bericht (ADR 0029).

    An einem echten Lauf bemessen, nicht geschaetzt: Der AAPL-Lauf vom
    2026-08-24 brachte **38 Zitate aus 19 verschiedenen Quellen**. Bei 15
    haette die Deckelung vier Quellen ganz verloren, obwohl sie gerade die
    Vielfalt schuetzen soll; ab 20 ueberleben alle. 25 laesst Luft nach oben
    und halbiert die Zeilenzahl trotzdem.

    Wie viele Zitate weggefallen sind, steht am Bericht
    (``ResearchEvidence.dropped_citations``) -- die Auslassung bleibt damit
    nicht still."""
    pricing: ResearchPricingConfig = ResearchPricingConfig()


class TechnicalAgentPricingConfig(_Section):
    """Preise fuer die Kostenschaetzung im Log (Muster
    ``ResearchPricingConfig``) -- rein informativ und **von Hand gepflegt**.

    Vorbelegt mit den Preisen des voreingestellten Haiku-Profils. Sie aendern
    sich unabhaengig von diesem Projekt und sind vor dem ersten produktiven
    Lauf gegen den dann aktuellen Katalog zu pruefen.
    """

    input_usd_per_million: NonNegativeFloat = 1.0
    output_usd_per_million: NonNegativeFloat = 5.0


class TechnicalAgentConfig(_Section):
    """Der Technical Agent: KI-Einordnung der Chartauswertung (ADR 0026).

    Getrennt von ``technical_analysis``: Dort stehen die Verfahrensparameter,
    die der Betreiber nach Doc 14 am echten Chart nachzieht, hier reine
    Anbieter- und Budgetwerte. Das Modellprofil steht in ``llm.technical``.

    ``fixture`` bleibt Standard, damit Start und Tests ohne
    ``ATA_LLM_API_KEY`` funktionieren (Muster ``research.provider``).

    Kein ``max_input_tokens_per_symbol`` wie bei ``research``: Es gibt keine
    Werkzeugschleife und keine Fortsetzung, die Eingabe ist durch den Snapshot
    nach oben begrenzt. Ein Regler, der nichts regelt, waere irrefuehrend.
    """

    provider: Literal["fixture", "anthropic"] = "fixture"
    max_output_tokens: PositiveInt = 2000
    """Ein Werkzeugaufruf mit sechs Einstufungen und einem kurzen Text. Zu
    knapp bemessen schneidet es den Aufruf ab -- und ein abgeschnittener
    Aufruf wird verworfen, nicht halb verwertet."""
    max_concurrent_calls: PositiveInt = 4
    """Gleichzeitige Einordnungen. **Eigener Pool**, getrennt von ``research``
    (ADR 0037, Risiko R9).

    Groesser als dort, weil eine Einordnung Sekunden dauert und Bruchteile
    eines Cents kostet. Vor ADR 0037 teilten sich beide Agenten vier Plaetze;
    eine haengende Recherche belegte bis zu 900 s einen davon, waehrend die
    kurzen Einordnungen warteten."""
    request_timeout_seconds: PositiveInt = 60
    """Deutlich kuerzer als bei ``research`` (900 s): Dort laufen
    serverseitige Werkzeuge, hier ist es eine einzelne Anfrage ohne sie."""
    max_retries: NonNegativeInt = 2
    """Ausdruecklich statt SDK-Standard -- hier zufaellig derselbe Wert.

    Anders als bei ``research`` ist eine Wiederholung billig und die
    Blockade kurz: eine einzelne Anfrage ohne Werkzeugschleife, gedeckelt
    durch ``max_output_tokens``, schlimmstenfalls 60 s mal drei Versuche."""
    pricing: TechnicalAgentPricingConfig = TechnicalAgentPricingConfig()


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
    minimum_completion_ratio: float = Field(default=0.9, gt=0.0, le=1.0)
    """Ab welchem Anteil gerechneter Aktien der Lauf als erledigt gilt.

    Der Analyse-Lauf isoliert Fehler je Aktie und bricht deshalb nicht ab.
    Ohne diese Schwelle haette der Dispatcher auch einen Lauf als erledigt
    verbucht, bei dem die Verbindung nach der ersten Aktie abriss und die
    uebrigen 191 an fehlenden Daten scheiterten -- der Handelstag waere still
    uebersprungen worden, denn ein erledigter Lauf wird nicht wiederholt und
    nicht gemeldet.

    Nicht 1.0: Eine einzelne dauerhaft stumme Aktie -- ausgesetzt, vom Handel
    genommen, im Kuerzel veraltet -- wuerde den Tageslauf sonst jeden Abend
    bis zum Fristablauf blockieren und dabei jedes Mal Bestand und
    KI-Auswertung erneut anstossen.
    """


class TelegramConfig(_Section):
    """Adresse des Telegram-Bots (ADR 0024).

    Hier steht **kein** Geheimnis: Der Bot-Token kommt ausschliesslich aus
    ``ATA_NOTIFICATION_TOKEN``. Die Chat-ID ist demgegenueber nur eine
    Adresse -- wer sie kennt, kann ohne Token nichts damit anfangen.
    """

    chat_id: str | None = None
    base_url: str = "https://api.telegram.org"
    request_timeout_seconds: PositiveInt = 10


class NotificationsConfig(_Section):
    """Benachrichtigungsverhalten (Doc 10, Paragraph 6.13)."""

    send_when_no_candidates: bool = False
    channel: Literal["dry_run", "telegram", "pushover"] = "dry_run"
    telegram: TelegramConfig = TelegramConfig()


class SwingWeightsConfig(_Section):
    """Gewichte der sechs Swing-Komponenten (ADR 0041).

    Die Haelfte des Gewichts liegt auf den beiden nachrechenbaren
    Komponenten: Signale und Signalstatistik sind das Einzige am
    Swing-Score, was sich gegen die gespeicherten Kerzen pruefen laesst.
    """

    technical_signals: NonNegativeFloat = 0.25
    signal_statistics: NonNegativeFloat = 0.25
    chart_setup: NonNegativeFloat = 0.15
    chance_risk: NonNegativeFloat = 0.15
    news_and_events: NonNegativeFloat = 0.10
    options_attractiveness: NonNegativeFloat = 0.10

    @model_validator(mode="after")
    def _weights_must_sum_to_one(self) -> SwingWeightsConfig:
        _pruefe_gewichtssumme(self, "scoring.swing_weights")
        return self


class LongTermWeightsConfig(_Section):
    """Gewichte der vier Investment-Komponenten (ADR 0041)."""

    profitability: NonNegativeFloat = 0.30
    growth: NonNegativeFloat = 0.25
    valuation: NonNegativeFloat = 0.25
    balance_sheet_quality: NonNegativeFloat = 0.20

    @model_validator(mode="after")
    def _weights_must_sum_to_one(self) -> LongTermWeightsConfig:
        _pruefe_gewichtssumme(self, "scoring.long_term_weights")
        return self


class MetricThresholdConfig(_Section):
    """Die vier Fuenftelgrenzen einer Kennzahl (ADR 0045).

    Gemessen an einem Lauf ueber die volle Watchliste, nicht gesetzt. Sie
    werden neu gemessen, wenn sich die Watchliste wesentlich aendert oder
    eine Berichtssaison durch ist -- und heben dann
    ``scoring.long_term_version``.
    """

    boundaries: tuple[float, float, float, float]
    higher_is_better: bool
    """Pflichtfeld ohne Default: Bei KGV, KUV, Kurs/FCF, Verschuldungsgrad
    und Verwaesserung ist **niedriger** besser, und ein vergessener Schalter
    kehrte die Bewertung stillschweigend um."""

    @model_validator(mode="after")
    def _boundaries_must_be_ordered(self) -> MetricThresholdConfig:
        if list(self.boundaries) != sorted(self.boundaries):
            raise ValueError(f"Fuenftelgrenzen muessen aufsteigen, gegeben sind {self.boundaries}")
        return self


class RecommendationConfig(_Section):
    """Die Ableitung der Empfehlungsstufe (ADR 0046).

    **Gesetzt, nicht gemessen.** Eine Empfehlung liesse sich erst an
    realisierten Ausgaengen kalibrieren, und die gibt es nicht. Die
    Stufengrenzen sind immerhin von der Skala abgelesen, aus der der
    Swing-Score gebaut ist (2/4/6/8/10, ADR 0045), und nicht gegriffen.
    """

    strong_candidate: NonNegativeFloat = 8.0
    candidate: NonNegativeFloat = 6.0
    watch: NonNegativeFloat = 4.0
    investment_strong: NonNegativeFloat = 8.0
    investment_weak: NonNegativeFloat = 4.0
    cap_false_signal_high: Literal["STRONG_CANDIDATE", "CANDIDATE", "WATCH", "AVOID_FOR_NOW"] = (
        "WATCH"
    )
    """Haelt die KI-Einordnung das Signal fuer unzuverlaessig, ist mehr als
    Beobachten nicht zu rechtfertigen -- der ganze Lauf steht auf dem
    Signal."""
    cap_earnings_unknown: Literal[
        "STRONG_CANDIDATE", "CANDIDATE", "WATCH", "AVOID_FOR_NOW"
    ] = "CANDIDATE"
    """Ein unbekannter Termin ist ein Datenrisiko, kein schlechter Befund
    (Doc 10, Paragraph 6.5). Er schliesst die hoechste Stufe aus, mehr
    nicht."""
    version: str = "1.0"

    @model_validator(mode="after")
    def _thresholds_must_fall(self) -> RecommendationConfig:
        if not self.strong_candidate > self.candidate > self.watch:
            raise ValueError(
                "scoring.recommendation: die Stufengrenzen muessen fallen "
                "(strong_candidate > candidate > watch)"
            )
        if self.investment_weak >= self.investment_strong:
            raise ValueError(
                "scoring.recommendation: investment_weak muss unter investment_strong liegen"
            )
        return self


class ScoringConfig(_Section):
    """Die beiden Scores (Doc 09; Doc 10, Paragraph 6.11).

    Die Versionsnummern steigen, wenn sich Komponenten, Gewichte **oder
    Schwellen** aendern -- alle drei stehen deshalb in diesem Abschnitt.
    """

    swing_version: str = "1.1"
    """``1.1`` gegenueber ``1.0``: Die News- und Ereignislage rechnet mit
    (ADR 0046). Der Score steht damit auf 90 statt 80 Prozent Abdeckung --
    dieselbe Zahl bedeutet vorher und nachher etwas anderes, und genau
    deshalb steigt die Nummer."""
    long_term_version: str = "1.0"
    minimum_coverage: NonNegativeFloat = 0.6
    """Unterhalb dieser Datenabdeckung entsteht kein Score, sondern
    ``INSUFFICIENT_DATA`` (Doc 09). Gesetzt, nicht gemessen."""
    normal_confidence_coverage: NonNegativeFloat = 0.8
    """Ab hier gilt der Score als ``NORMAL`` belastbar, darunter als
    ``LOW_COVERAGE``. Muster ``backtesting.normal_confidence_sample_size``."""
    recommendation: RecommendationConfig = RecommendationConfig()
    swing_weights: SwingWeightsConfig = SwingWeightsConfig()
    long_term_weights: LongTermWeightsConfig = LongTermWeightsConfig()
    analyst_max_age_days: PositiveInt = 62
    """Aelter darf der juengste Monatsstand der Analystenvoten nicht sein.

    **Gesetzt, nicht gemessen** (ADR 0046): Die Voten erscheinen monatlich;
    62 Tage lassen einen ausgefallenen Stand durchgehen, zwei nicht mehr. Der
    Endpunkt selbst kennt keine Schranke -- er liefert den juengsten Stand,
    den er hat, auch wenn der zwei Jahre alt ist."""
    analyst_buy_share: MetricThresholdConfig = MetricThresholdConfig(
        boundaries=(0.4362, 0.5758, 0.6988, 0.8182), higher_is_better=True
    )
    """Die Schwellen der News-Komponente (ADR 0046) -- an 187 Titeln der
    Watchliste gemessen. Ein eigenes Feld und kein Eintrag in ``thresholds``:
    Der Kauf-Anteil ist keine Kennzahl aus einer SEC-Einreichung."""
    options_annualized_return: MetricThresholdConfig | None = None
    """Die Schwellen der Optionsattraktivitaet (ADR 0048) -- die annualisierte
    Praemienrendite des bestbewerteten Put-Vorschlags.

    **Ohne Eintrag entfaellt die Komponente** mit benanntem Grund, und der
    Swing-Score bleibt bei der Abdeckung ohne sie. Das ist Absicht: Ein
    vorlaeufiger Satz Schwellen truege eine Zahl in den Score, die aussieht
    wie die gemessenen daneben. Gefuellt wird das Feld nach dem Messlauf
    ueber die Watchliste (``cli options --watchlist --output``), und dann
    steigt ``swing_version``."""
    thresholds: dict[str, MetricThresholdConfig] = {}
    """Die Schwellen je Kennzahl, Schluessel ist der Name aus ``MetricName``.

    Eine Abbildung und keine vierzehn Felder: Die Kennzahlenliste gehoert der
    Domain, und sie hier ein zweites Mal zu fuehren hiesse, zwei Listen
    synchron halten zu muessen. Dass die Schluessel gueltig **und
    vollstaendig** sind, prueft ``bootstrap`` -- an der einen Stelle, die
    beide Seiten kennt."""

    @model_validator(mode="after")
    def _coverage_thresholds_must_be_ordered(self) -> ScoringConfig:
        if self.normal_confidence_coverage < self.minimum_coverage:
            raise ValueError(
                "normal_confidence_coverage darf nicht kleiner als minimum_coverage sein"
            )
        if self.minimum_coverage > 1.0 or self.normal_confidence_coverage > 1.0:
            raise ValueError("Abdeckungsgrenzen sind Anteile und liegen zwischen 0 und 1")
        return self


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
    analyst_ratings: AnalystRatingsConfig = AnalystRatingsConfig()
    finnhub: FinnhubConfig = FinnhubConfig()
    technical_analysis: TechnicalAnalysisConfig = TechnicalAnalysisConfig()
    llm: LlmConfig = LlmConfig()
    research: ResearchConfig = ResearchConfig()
    technical_agent: TechnicalAgentConfig = TechnicalAgentConfig()
    fundamentals: FundamentalsConfig = FundamentalsConfig()
    options: OptionsConfig = OptionsConfig()
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
    edgar_contact: SecretStr | None = None
    """Die Kontaktadresse, die die SEC im ``User-Agent`` verlangt, damit sie
    bei auffaelligem Abrufverhalten jemanden erreichen kann.

    **Kein Geheimnis im Wortsinn** -- und trotzdem hier und nicht in
    ``config/default.yaml``: Das Repository ist oeffentlich. Eine
    Kontaktadresse ist typischerweise eine private Mailadresse, und
    committet stuende sie fuer jeden Besucher und jeden Crawler da. "Kein
    Zugangsdatum" heisst nicht "darf veroeffentlicht werden".

    Der Unterschied zur Telegram-``chat_id``, die in der Konfiguration
    bleiben darf: Ohne den Bot-Token kann mit ihr niemand etwas anfangen.
    Bei einer Mailadresse gibt es kein solches zweites Schloss.
    """

    @field_validator("*", mode="before")
    @classmethod
    def _leer_ist_nicht_gesetzt(cls, value: object) -> object:
        """Ein leerer Wert zaehlt als nicht gesetzt.

        ``.env.example`` liefert die noch nicht gebrauchten Schluessel als
        ``ATA_FINNHUB_API_KEY=`` aus, also leer. Ohne diese Normalisierung
        kaeme dort eine leere Zeichenkette an, ``require`` liefe glatt durch
        und der Fehler faende erst beim Anbieter statt.

        Das waere die teuerste Stelle dafuer: Der Frueh-Abbruch in
        ``command_dispatch`` sitzt bewusst **vor** dem halbstuendigen
        Backfill. Uebersprungen, laeuft der ganze Abend durch, jeder Kandidat
        faellt einzeln auf einen Anbieterfehler zurueck -- und der Lauf endet
        mit Rueckgabewert 0. Er saehe aus wie ein gelungener Tag.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value

    def model_post_init(self, __context: object) -> None:
        """Meldet jeden gesetzten Wert zur Schwaerzung an (ADR 0044).

        **Warum hier und nicht in** ``load_secrets``: Genau dort stand es
        zuerst -- und griff nicht. Das CLI baut ``Secrets()`` an sechs
        Stellen selbst und ging daran vorbei. Die Probe auf dem Server hat
        das gefunden: Der Finnhub-Schluessel stand unveraendert in der
        Anfragezeile von ``httpx``, obwohl die Schwaerzung angeblich stand.

        Am Modell haengt die Anmeldung an der **Entstehung** des
        Geheimnisses statt an einem von mehreren Ladewegen. Wer ein
        ``Secrets`` in der Hand haelt, hat es damit auch angemeldet -- es
        gibt keinen zweiten Weg, an dem jemand vorbeibauen kann.
        """
        # Lokaler Import: ``secret_redaction`` selbst ist ein Blatt ohne
        # eigene Abhaengigkeiten, aber ``observability/__init__`` zieht das
        # Logging nach -- und das importiert ``LoggingConfig`` von hier.
        from ai_trading_analyst.observability.secret_redaction import register_secret

        for field_name in type(self).model_fields:
            value: SecretStr | None = getattr(self, field_name)
            if value is not None:
                register_secret(value.get_secret_value())

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
