"""Der Technical Agent ueber die Anthropic Messages API (ADR 0021, ADR 0026).

Deutlich einfacher als der Research-Adapter nebenan: **eine** Anfrage, keine
Web-Werkzeuge, keine Zitate, keine ``pause_turn``-Fortsetzung. Der zentrale
Konflikt aus ADR 0023 -- Zitatbloecke vertragen sich nicht mit einem strikten
Schema -- entsteht hier gar nicht erst, weil die einzige Quelle die eigene
Rechenausgabe ist.

Die Antwort kommt ausschliesslich ueber den erzwungenen Aufruf eines
Client-Werkzeugs mit striktem JSON-Schema (Doc 10, Paragraph 10: "Jede
KI-Komponente muss gegen ein festes Schema validiert werden").

**Das Modell hat kein Feld, in das es eine Zahl schreiben koennte.** Alle
sechs Einordnungen sind Enums, die uebrigen Felder Text. Ein erfundenes
Chance-Risiko-Verhaeltnis ist im Schema nicht ausdrueckbar -- das ist die
strukturelle Umsetzung von CLAUDE.md ("Scores werden nie direkt aus
LLM-Freitext uebernommen"), nicht bloss eine Bitte im Prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

import anthropic
import httpx
from anthropic.types import Message

from ai_trading_analyst.domain.analysis import (
    Stock,
    TechnicalInterpreter,
    TechnicalInterpreterError,
)
from ai_trading_analyst.domain.technical import (
    BreakoutQuality,
    FalseSignalRisk,
    MomentumState,
    PriceZone,
    RiskRewardRating,
    SwingEntryPlausibility,
    TechnicalAssessment,
    TechnicalAssessmentStatus,
    TechnicalSnapshot,
    TechnicalStatus,
    TrendStrength,
    ZoneKind,
)
from ai_trading_analyst.observability.logging_setup import get_logger

_logger = get_logger(__name__)

_MARKET_TIMEZONE = ZoneInfo("America/New_York")

_PROMPT_VERSION = "technical-agent-v3"
"""``v3`` gegenueber ``v2``: Die sechs Einstufungen und die Zusammenfassung
sind jetzt Pflichtfelder des Werkzeugschemas, und die Temperatur steht auf 0.
``v2`` hatte den Prompt geschaerft und damit nur die Haelfte erreicht -- ein
Titel lieferte alle sechs Felder, der andere weiterhin vier.

``v2`` gegenueber ``v1``: Der erste Lauf gegen echte Kurse lieferte bei
beiden Titeln nur vier der sechs Einstufungen -- es fehlten ausgerechnet
Chance/Risiko und die Plausibilitaet des Swing-Einstiegs. Ursache waren zwei
zu scharf formulierte Verbote ("Du stufst diesen Wert ein, mehr nicht" und
"Du triffst keine Handelsentscheidung"), die das Modell vom Einordnen ganz
abhielten, in Verbindung damit, dass im Schema nur ``status`` Pflicht ist.
``v2`` verlangt die sechs Felder ausdruecklich und formuliert beide Stellen
positiv (ADR 0026, Revisionsabschnitt).

Bewusst nicht ``technical-v1``: Die Verfahrensversion der
deterministischen Auswertung heisst ``technical-v3`` und steht in derselben
Zeile der Datenbank. Zwei aehnlich benannte Versionsangaben nebeneinander
waeren eine Verwechslung mit Ansage."""

_SUBMIT_TOOL_NAME = "submit_technical_assessment"

_NICHT_VERFUEGBAR = "nicht verfuegbar"
"""Einheitliche Kennzeichnung fehlender Werte in der Modelleingabe.

Nicht ``--`` und nicht ``0``: Das Modell soll den Unterschied zwischen "null"
und "unbekannt" nicht raten muessen (CLAUDE.md: fehlt eine Kennzahl, bleibt
sie fehlend)."""


@dataclass(frozen=True, slots=True)
class AnthropicTechnicalPricing:
    """Preise fuer die Kostenschaetzung im Log -- von Hand gepflegt, keine
    abgefragte Preisliste (Muster ``AnthropicResearchPricing``)."""

    input_usd_per_million: float
    output_usd_per_million: float


@dataclass(slots=True)
class _UsageTotals:
    """Tokens einer einzelnen Anfrage.

    Viel einfacher als das Gegenstueck im Research-Adapter: Es gibt nur eine
    Runde, keine Websuche und keinen wiederholt verrechneten Kontext, also
    auch keine Cache-Arithmetik. Bewusst nur Logging und kein Feld am
    Ergebnis -- ein persistierter Kostenwert braucht eine eigene Entscheidung.
    """

    pricing: AnthropicTechnicalPricing
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, usage: Any) -> None:
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens

    def estimated_usd(self) -> float:
        return (
            self.input_tokens / 1_000_000 * self.pricing.input_usd_per_million
            + self.output_tokens / 1_000_000 * self.pricing.output_usd_per_million
        )

    def log(self, symbol: str, model: str) -> None:
        _logger.info(
            "Technical-Agent-Nutzung %s (%s): %d Eingabe-Token, %d Ausgabe-Token, "
            "geschaetzt %.4f USD",
            symbol,
            model,
            self.input_tokens,
            self.output_tokens,
            self.estimated_usd(),
        )


@dataclass(frozen=True, slots=True)
class AnthropicTechnicalSettings:
    """Verbindungs- und Budgetparameter des Technical-Agent-Adapters."""

    api_key: str = field(repr=False)
    """``repr=False``: Der Schluessel soll nicht ueber eine beilaeufig
    geloggte Settings-Instanz in einer Logdatei landen."""
    model: str
    max_output_tokens: int
    request_timeout_seconds: int
    pricing: AnthropicTechnicalPricing
    fallback_model: str | None = None


_SYSTEM_PROMPT = """\
Du bist der Technical Agent eines Aktienanalyse-Systems. Du bekommst eine \
bereits fertig gerechnete, deterministische Chartauswertung und ordnest sie \
ein. Mehr nicht.

Die vorgelegten Werte sind Messwerte, keine Vorschlaege. Widerspricht dein \
Eindruck einem Wert, gilt der Wert.

Was du nicht tust:
- Du rechnest keine Zahl nach, korrigierst keine und leitest keine neue ab.
- Du erfindest keine Kennzahl, die dir nicht vorgelegt wurde. Steht dort \
"nicht verfuegbar", dann fehlt der Wert -- schreibe nicht "vermutlich".
- Du nennst in deinem Text keine Zahl, die nicht in den vorgelegten Daten \
steht.
- Du veraenderst kein technisches Signal. Ob die Aktie ueberhaupt ein \
Kandidat ist, ist bereits entschieden, und du kannst daran nichts aendern. \
Deine Einstufungen sind Beschreibungen der Lage, keine Auftraege -- sie \
einzuordnen ist deine Aufgabe und keine Grenzueberschreitung.

Deine Einordnung deckt genau sechs Punkte ab: Staerke des Trends, Qualitaet \
des Breakouts, ueberkaufte oder ueberverkaufte Situation, Fehlsignalrisiko, \
Verhaeltnis von Chance und Risiko, Plausibilitaet eines Swing-Einstiegs. Es \
geht durchgaengig um einen Einstieg auf der Long-Seite mit einem Horizont von \
einigen Tagen bis Wochen.

**Antwortest du mit status=COMPLETED, fuellst du alle sechs Felder aus.** \
Eine Einordnung, die eines davon auslaesst, ist unbrauchbar -- sie sieht aus \
wie ein fehlender Wert, obwohl du bloss nichts gesagt hast. Kannst du einen \
Punkt nicht beurteilen, gibt es dafuer in jedem Feld einen zurueckhaltenden \
Wert (ABSENT, NO_BREAKOUT, NEUTRAL, NOT_ASSESSABLE, QUESTIONABLE). Nutze ihn, \
statt das Feld leer zu lassen.

So liest du die Zonen:
- Die Staerke einer Zone folgt der Zahl der Wendepunkte, nicht der Zahl der \
Beruehrungen. Eine Zone mit vielen Beruehrungen und nur einem Wendepunkt ist \
eine Preisregion, die der Kurs durchlaeuft -- sie traegt nicht, und sie ist \
als WEAK gekennzeichnet. Lies die Beruehrungszahl nie als Staerke.
- Zonen sind nach Abstand zum Kurs sortiert, die naechstgelegene zuerst.

Zum Chance-Risiko-Verhaeltnis: Es ist bereits berechnet und wird dir genannt \
-- du sollst es also **nicht** ausrechnen, sondern einordnen. Genau das wird \
von dir erwartet: Ein Wert von 1.0 heisst gleich weit nach oben wie nach \
unten, deutlich ueber 1 spricht fuer die Long-Seite, deutlich darunter \
dagegen. Nur wenn dort "nicht berechenbar" steht, lautet deine Einstufung \
NOT_ASSESSABLE.

Zur Qualitaet des Breakouts: Liegt kein Ausbruch vor, ist NO_BREAKOUT die \
richtige Antwort und keine Verlegenheitsloesung.

Zur Plausibilitaet des Swing-Einstiegs: Das ist **keine** Handelsempfehlung, \
sondern die Frage, ob die vorliegende Chartlage zu einem Einstieg auf der \
Long-Seite passt. Du entscheidest damit nichts -- du beschreibst die Lage. \
IMPLAUSIBLE ist eine ebenso gueltige Antwort wie PLAUSIBLE.

Reichen die vorgelegten Werte fuer eine Einordnung nicht aus, antworte mit \
status=INSUFFICIENT_DATA und einer kurzen Begruendung in reason, statt zu \
raten.

Antworte ausschliesslich durch genau einen Aufruf von \
submit_technical_assessment. Schreibe keinen Fliesstext daneben.
"""

_SUBMIT_ASSESSMENT_TOOL: dict[str, Any] = {
    "name": _SUBMIT_TOOL_NAME,
    "description": (
        "Schliesst die charttechnische Einordnung ab und uebermittelt sie "
        "strukturiert. Muss genau einmal aufgerufen werden, als einzige Aktion."
    ),
    # strict laesst die API die Ausgabe am Schema entlang erzwingen
    # (grammar-constrained sampling) statt es nur zu beschreiben -- dieselbe
    # Begruendung wie bei _SUBMIT_REPORT_TOOL im Research-Adapter, wo eine
    # Faktorliste ohne strict als interne XML-Syntax durchgereicht wurde.
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["COMPLETED", "INSUFFICIENT_DATA"],
                "description": (
                    "INSUFFICIENT_DATA, wenn die vorgelegten Werte fuer eine "
                    "Einordnung nicht ausreichen."
                ),
            },
            "trend_strength": {
                "type": "string",
                "enum": [m.value for m in TrendStrength],
                "description": (
                    "Staerke des Trends. ABSENT, wenn kein tragfaehiger Trend erkennbar ist."
                ),
            },
            "breakout_quality": {
                "type": "string",
                "enum": [m.value for m in BreakoutQuality],
                "description": (
                    "Qualitaet des Breakouts. NO_BREAKOUT, wenn kein Ausbruch "
                    "vorliegt -- das ist keine schlechte Bewertung, sondern die "
                    "Feststellung, dass die Frage sich nicht stellt."
                ),
            },
            "momentum_state": {
                "type": "string",
                "enum": [m.value for m in MomentumState],
                "description": "Ueberkaufte oder ueberverkaufte Situation.",
            },
            "false_signal_risk": {
                "type": "string",
                "enum": [m.value for m in FalseSignalRisk],
                "description": "Wie gross das Risiko eines Fehlsignals ist.",
            },
            "risk_reward_rating": {
                "type": "string",
                "enum": [m.value for m in RiskRewardRating],
                "description": (
                    "Einstufung des bereits berechneten "
                    "Chance-Risiko-Verhaeltnisses. NOT_ASSESSABLE, wenn es als "
                    "nicht berechenbar ausgewiesen ist. Rechne nichts selbst aus."
                ),
            },
            "swing_entry_plausibility": {
                "type": "string",
                "enum": [m.value for m in SwingEntryPlausibility],
                "description": "Plausibilitaet eines Swing-Einstiegs auf der Long-Seite.",
            },
            "summary": {
                "type": "string",
                "description": (
                    "Kurze Einordnung in zusammenhaengendem Fliesstext, hoechstens fuenf Saetze."
                ),
            },
            "false_signal_risks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Die konkreten Fehlsignalrisiken, je Eintrag eines.",
            },
            # Der strict-Schemasubset kennt "minimum"/"maximum" bei "number"
            # nicht (400: "For 'number' type, properties maximum, minimum are
            # not supported"). Die Grenze steht deshalb in der Beschreibung --
            # durchgesetzt wird sie im Adapter, nicht vom Schema.
            "confidence": {
                "type": "number",
                "description": "Wert zwischen 0 und 1 (einschliesslich).",
            },
            "reason": {
                "type": "string",
                "description": "Nur bei status=INSUFFICIENT_DATA: kurze Begruendung.",
            },
        },
        # Alle sieben inhaltlichen Felder sind Pflicht -- durchgesetzt vom
        # Schema, nicht erbeten vom Prompt.
        #
        # Zwei Prompt-Fassungen haben es nicht geschafft: v1 liess bei beiden
        # Titeln zwei Einstufungen aus, v2 bei einem von zweien (ADR 0026,
        # Revisionsabschnitt). Eine Bitte, die in der Haelfte der Faelle
        # befolgt wird, ist keine Zusicherung. Mit ``strict`` erzwingt die API
        # die Felder beim Sampling -- eine unvollstaendige Antwort ist damit
        # nicht mehr formulierbar.
        #
        # Bei ``status=INSUFFICIENT_DATA`` verwirft ``_build_assessment`` die
        # Einstufungen ungelesen; gespeichert wird dann nichts davon. Fuer den
        # Zweifelsfall traegt ausserdem jedes Feld einen zurueckhaltenden Wert
        # (ABSENT, NO_BREAKOUT, NEUTRAL, NOT_ASSESSABLE, QUESTIONABLE), sodass
        # die Pflicht niemanden zu einer Aussage zwingt, die er nicht meint.
        "required": [
            "status",
            "trend_strength",
            "breakout_quality",
            "momentum_state",
            "false_signal_risk",
            "risk_reward_rating",
            "swing_entry_plausibility",
            "summary",
        ],
        "additionalProperties": False,
    },
    "input_examples": [
        {
            "status": "COMPLETED",
            "trend_strength": "MODERATE",
            "breakout_quality": "NO_BREAKOUT",
            "momentum_state": "NEUTRAL",
            "false_signal_risk": "MEDIUM",
            "risk_reward_rating": "BALANCED",
            "swing_entry_plausibility": "QUESTIONABLE",
            "summary": (
                "Der Kurs steht ueber beiden Durchschnitten, der Abstand zum "
                "EMA20 ist jedoch gering."
            ),
            "false_signal_risks": [
                "Naechster Widerstand liegt dicht ueber dem Kurs",
            ],
            "confidence": 0.6,
        }
    ],
}


def _format_number(value: float | None, digits: int = 2) -> str:
    return _NICHT_VERFUEGBAR if value is None else f"{value:.{digits}f}"


def _format_percent(value: float | None) -> str:
    return _NICHT_VERFUEGBAR if value is None else f"{value * 100:.2f} %"


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _lage_zum_durchschnitt(distance: float | None) -> str:
    """Positiv heisst oberhalb -- ausgeschrieben statt als Vorzeichen.

    "Kurs -1.50 % davon entfernt" laesst sich als Betrag lesen; "1.50 %
    darunter" nicht.
    """
    if distance is None:
        return _NICHT_VERFUEGBAR
    lage = "darueber" if distance >= 0 else "darunter"
    return f"Kurs {abs(distance) * 100:.2f} % {lage}"


def _format_zone(zone: PriceZone) -> str:
    spanne = (
        f"{zone.lower:.2f}"
        if zone.lower == zone.upper
        else f"{zone.lower:.2f} bis {zone.upper:.2f}"
    )
    return (
        f"  {zone.kind.value}: {spanne}, Staerke {zone.strength.value}, "
        f"{_plural(zone.pivot_count, 'Wendepunkt', 'Wendepunkte')}, "
        f"{_plural(zone.touch_count, 'Beruehrung', 'Beruehrungen')}, "
        f"zuletzt bestaetigt {zone.last_confirmed_at.date().isoformat()}, "
        f"Abstand {zone.distance_pct * 100:.2f} %"
    )


def market_today() -> date:
    """Das heutige Datum an der Boerse, nicht in UTC.

    Der Scheduler rechnet durchgehend in ``America/New_York`` (CLAUDE.md).
    Ein Lauf nach 20:00 Ortszeit liegt bereits im UTC-Folgetag -- dem Modell
    dann "morgen" als heutiges Datum zu nennen, waere derselbe Fehler wie der
    in ADR 0023, Punkt 14, nur andersherum.
    """
    return datetime.now(_MARKET_TIMEZONE).date()


def render_snapshot(stock: Stock, snapshot: TechnicalSnapshot, today: date | None = None) -> str:
    """Die vollstaendige Modelleingabe als Text.

    Eine reine Funktion und oeffentlich, damit die CLI genau das anzeigen
    kann, was das Modell gesehen hat (``technical --interpret
    --show-prompt``). Ohne diese Moeglichkeit liesse sich die Zusage "das
    Modell sieht nur den Snapshot" nicht nachpruefen, sondern nur behaupten.

    Enthaelt bewusst **keine** Rohkerzen, keine Signalliste und kein Ergebnis
    des Earnings-Filters oder des Research Agent: Das Modell soll nichts
    einordnen koennen, was nicht deterministisch gerechnet wurde
    (Modulentkopplung, CLAUDE.md).
    """
    kerze = (
        _NICHT_VERFUEGBAR
        if snapshot.candle_timestamp is None
        else snapshot.candle_timestamp.isoformat()
    )
    zeilen = [
        f"Entscheidungskerze: {kerze}",
        f"Schlusskurs: {_format_number(snapshot.close)}",
        f"Trend: {_NICHT_VERFUEGBAR if snapshot.trend is None else snapshot.trend.value}",
        f"RSI: {_format_number(snapshot.rsi, digits=1)}",
        f"EMA5: {_format_number(snapshot.ema5)} "
        f"({_lage_zum_durchschnitt(snapshot.distance_to_ema5_pct)})",
        f"EMA20: {_format_number(snapshot.ema20)} "
        f"({_lage_zum_durchschnitt(snapshot.distance_to_ema20_pct)})",
        f"ATR: {_format_number(snapshot.atr)} ({_format_percent(snapshot.atr_pct)} vom Kurs)",
        f"Juengstes Hoch: {_format_number(snapshot.recent_high)}",
        f"Juengstes Tief: {_format_number(snapshot.recent_low)}",
        "",
        f"Weg bis zur naechsten Unterstuetzung: "
        f"{_format_percent(snapshot.downside_to_support_pct)}",
        f"Weg bis zum naechsten Widerstand: {_format_percent(snapshot.upside_to_resistance_pct)}",
    ]

    if snapshot.chance_risk_ratio is None:
        fehlend = (
            "keine Unterstuetzung unterhalb des Kurses gefunden"
            if snapshot.downside_to_support_pct is None
            else "kein Widerstand oberhalb des Kurses gefunden"
        )
        zeilen.append(f"Chance-Risiko-Verhaeltnis: nicht berechenbar ({fehlend})")
    else:
        zeilen.append(
            f"Chance-Risiko-Verhaeltnis: {snapshot.chance_risk_ratio:.2f} "
            "(Weg nach oben geteilt durch Weg nach unten)"
        )

    # Der Fallstrick, den das Modell sonst nicht sehen kann: Liegt der Kurs
    # in einer Zone, zeigen die beiden Wege oben auf die Zonen *jenseits*
    # dieser Zone. Ohne den Hinweis liest sich ein guenstiges Verhaeltnis
    # harmlos, waehrend der Kurs mitten in einer starken Zone klemmt.
    inside = next((z for z in snapshot.zones if z.kind is ZoneKind.PRICE_INSIDE), None)
    if inside is not None:
        zeilen.append(
            f"Achtung: Der Kurs liegt in einer Zone ({inside.lower:.2f} bis "
            f"{inside.upper:.2f}, Staerke {inside.strength.value}). Die beiden "
            "Wege oben beziehen sich auf die naechste Zone darunter "
            "beziehungsweise darueber, nicht auf diese."
        )

    zeilen.append("")
    if snapshot.zones:
        zeilen.append("Zonen, nach Abstand zum Kurs:")
        zeilen.extend(_format_zone(zone) for zone in snapshot.zones)
    else:
        zeilen.append("Zonen: keine mehrfach getestete Preisregion im Fenster.")

    daten = "\n".join(zeilen)
    return (
        f"Ordne die folgende Chartauswertung fuer {stock.symbol} "
        f"({stock.exchange}) ein.\n"
        f"Heutiges Datum: {(today or market_today()).isoformat()}.\n\n"
        f"<chartauswertung>\n{daten}\n</chartauswertung>"
    )


class AnthropicTechnicalInterpreter(TechnicalInterpreter):
    """Implementiert ``TechnicalInterpreter`` gegen die Anthropic Messages API."""

    def __init__(
        self,
        settings: AnthropicTechnicalSettings,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._client = anthropic.Anthropic(
            api_key=settings.api_key,
            http_client=http_client,
            timeout=float(settings.request_timeout_seconds),
        )
        self._model = settings.model
        self._fallback_model = settings.fallback_model
        self._max_output_tokens = settings.max_output_tokens
        self._pricing = settings.pricing

    def interpret(self, stock: Stock, snapshot: TechnicalSnapshot) -> TechnicalAssessment:
        evaluated_at = datetime.now(UTC)
        if snapshot.status is not TechnicalStatus.COMPLETED:
            # Kein Modellaufruf: Es gibt nichts einzuordnen, und der Aufruf
            # kostete nur. Der Application Layer prueft dasselbe noch einmal --
            # hier steht es, damit die Zusicherung am Vertrag haengt und nicht
            # am Aufrufer.
            return TechnicalAssessment(
                status=TechnicalAssessmentStatus.INSUFFICIENT_DATA,
                evaluated_at=evaluated_at,
                model=None,
                prompt_version=None,
                interpreted_analysis_version=snapshot.analysis_version,
                reason="snapshot_insufficient",
            )

        try:
            return self._attempt(stock, snapshot, self._model, evaluated_at)
        except anthropic.APIError as error:
            if self._fallback_model is None:
                raise TechnicalInterpreterError(
                    f"'{stock.symbol}': Einordnung konnte ueber '{self._model}' nicht "
                    f"abgerufen werden: {error}"
                ) from error
            _logger.warning(
                "Einordnung fuer %s ueber '%s' gescheitert (%s) -- "
                "Versuch mit Ausweichmodell %s (ModelProfile.fallback_model)",
                stock.symbol,
                self._model,
                error,
                self._fallback_model,
            )
            try:
                return self._attempt(stock, snapshot, self._fallback_model, evaluated_at)
            except anthropic.APIError as fallback_error:
                raise TechnicalInterpreterError(
                    f"'{stock.symbol}': Einordnung konnte weder ueber '{self._model}' "
                    f"noch ueber '{self._fallback_model}' abgerufen werden: {fallback_error}"
                ) from fallback_error

    def _attempt(
        self, stock: Stock, snapshot: TechnicalSnapshot, model: str, evaluated_at: datetime
    ) -> TechnicalAssessment:
        try:
            return self._run(stock, snapshot, model, evaluated_at)
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            # Der Vertrag kennt genau eine Ausnahme. Eine rohe Exception
            # verschoebe die ganze Aktie in StockProcessingError -- genau die
            # Kopplung, die CLAUDE.md ausschliesst (ADR 0023).
            raise TechnicalInterpreterError(
                f"'{stock.symbol}': Antwort des Modells '{model}' war nicht auswertbar: {error}"
            ) from error

    def _run(
        self, stock: Stock, snapshot: TechnicalSnapshot, model: str, evaluated_at: datetime
    ) -> TechnicalAssessment:
        usage = _UsageTotals(pricing=self._pricing)
        try:
            # ``type: ignore``: Das Werkzeugschema ist ein einfaches ``dict``
            # und passt nicht auf die ``ToolParam``-Ueberladung des SDK --
            # dasselbe Vorgehen wie im Research-Adapter nebenan.
            response: Message = self._client.messages.create(  # type: ignore[call-overload]
                model=model,
                max_tokens=self._max_output_tokens,
                system=_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": render_snapshot(stock, snapshot),
                    }
                ],
                tools=[_SUBMIT_ASSESSMENT_TOOL],
                tool_choice={"type": "tool", "name": _SUBMIT_TOOL_NAME},
                # Ausdruecklich gesetzt und nicht dem Standard ueberlassen:
                # max_tokens deckelt Denken und Antworttext gemeinsam (ADR
                # 0023, Punkt 21). Fuer eine einstufige Einordnung auf einer
                # Handvoll Zahlen ist Denken nicht der Hebel -- und ein
                # angeschnittener Werkzeugaufruf waere teurer als er nuetzt.
                thinking={"type": "disabled"},
                # Zwei Laeufe auf exakt derselben Eingabe lieferten fuer AAPL
                # einmal MEDIUM und einmal HIGH als Fehlsignalrisiko, bei
                # Konfidenz 0.55 und 0.65 (ADR 0026, Revisionsabschnitt). Fuer
                # eine Einstufung ist Streuung kein Gewinn, und dieses System
                # speichert seine Ergebnisse unveraenderlich und versioniert --
                # zwei verschiedene Antworten auf dieselben Zahlen liessen sich
                # spaeter nicht von einer Marktveraenderung unterscheiden.
                temperature=0.0,
            )
            usage.add(response.usage)

            if response.stop_reason == "max_tokens":
                # Kein Teilergebnis: Ein abgeschnittener Werkzeugaufruf kann
                # eine halbe Risikoliste enthalten, die vollstaendig aussieht.
                raise TechnicalInterpreterError(
                    f"'{stock.symbol}': Die Antwort wurde von max_tokens abgeschnitten "
                    f"({self._max_output_tokens}) -- es wird keine Einordnung gebaut."
                )

            submit_input = self._find_submit_call(response)
            if submit_input is None:
                raise TechnicalInterpreterError(
                    f"'{stock.symbol}': Das Modell '{model}' hat '{_SUBMIT_TOOL_NAME}' "
                    f"nicht aufgerufen (stop_reason={response.stop_reason})"
                )
            return self._build_assessment(stock, snapshot, submit_input, model, evaluated_at)
        finally:
            usage.log(stock.symbol, model)

    def _find_submit_call(self, response: Message) -> dict[str, Any] | None:
        for block in response.content:
            if block.type == "tool_use" and block.name == _SUBMIT_TOOL_NAME:
                if not isinstance(block.input, dict):
                    raise TechnicalInterpreterError(
                        f"'{_SUBMIT_TOOL_NAME}' lieferte {type(block.input).__name__} "
                        "statt eines Objekts"
                    )
                return block.input
        return None

    def _build_assessment(
        self,
        stock: Stock,
        snapshot: TechnicalSnapshot,
        submit_input: dict[str, Any],
        model: str,
        evaluated_at: datetime,
    ) -> TechnicalAssessment:
        symbol = stock.symbol
        status = _require_status(symbol, submit_input.get("status"))

        if status is TechnicalAssessmentStatus.INSUFFICIENT_DATA:
            return TechnicalAssessment(
                status=status,
                evaluated_at=evaluated_at,
                model=model,
                prompt_version=_PROMPT_VERSION,
                interpreted_analysis_version=snapshot.analysis_version,
                reason=_require_optional_text(symbol, "reason", submit_input.get("reason"))
                or "model_reported_insufficient",
            )

        trend_strength = _require_optional_enum(
            symbol, "trend_strength", TrendStrength, submit_input.get("trend_strength")
        )
        breakout_quality = _require_optional_enum(
            symbol, "breakout_quality", BreakoutQuality, submit_input.get("breakout_quality")
        )
        momentum_state = _require_optional_enum(
            symbol, "momentum_state", MomentumState, submit_input.get("momentum_state")
        )
        false_signal_risk = _require_optional_enum(
            symbol, "false_signal_risk", FalseSignalRisk, submit_input.get("false_signal_risk")
        )
        risk_reward_rating = _require_optional_enum(
            symbol, "risk_reward_rating", RiskRewardRating, submit_input.get("risk_reward_rating")
        )
        swing_entry_plausibility = _require_optional_enum(
            symbol,
            "swing_entry_plausibility",
            SwingEntryPlausibility,
            submit_input.get("swing_entry_plausibility"),
        )

        if not any(
            (
                trend_strength,
                breakout_quality,
                momentum_state,
                false_signal_risk,
                risk_reward_rating,
                swing_entry_plausibility,
            )
        ):
            # Ein COMPLETED ohne eine einzige Einstufung ist kein Ergebnis,
            # sondern eine leere Huelle (Muster: Research-Bericht ohne Beleg).
            _logger.warning(
                "Einordnung fuer %s meldet COMPLETED ohne eine einzige Einstufung -- "
                "wird auf INSUFFICIENT_DATA herabgestuft",
                symbol,
            )
            return TechnicalAssessment(
                status=TechnicalAssessmentStatus.INSUFFICIENT_DATA,
                evaluated_at=evaluated_at,
                model=model,
                prompt_version=_PROMPT_VERSION,
                interpreted_analysis_version=snapshot.analysis_version,
                reason="no_ratings",
            )

        risk_reward_rating = self._enforce_risk_reward(symbol, snapshot, risk_reward_rating)

        fehlend = [
            name
            for name, wert in (
                ("trend_strength", trend_strength),
                ("breakout_quality", breakout_quality),
                ("momentum_state", momentum_state),
                ("false_signal_risk", false_signal_risk),
                ("risk_reward_rating", risk_reward_rating),
                ("swing_entry_plausibility", swing_entry_plausibility),
            )
            if wert is None
        ]
        if fehlend:
            # Kein Fehler: Vier von sechs Einstufungen sind mehr wert als
            # keine, und die fehlenden bleiben als fehlend gekennzeichnet.
            # Aber es ist ein Prompt-Problem und gehoert gesehen -- der erste
            # Lauf gegen echte Kurse lieferte genau so ein Ergebnis (ADR 0026,
            # Revisionsabschnitt).
            _logger.warning(
                "Einordnung fuer %s laesst %d von 6 Einstufungen aus: %s",
                symbol,
                len(fehlend),
                ", ".join(fehlend),
            )

        return TechnicalAssessment(
            status=TechnicalAssessmentStatus.COMPLETED,
            evaluated_at=evaluated_at,
            model=model,
            prompt_version=_PROMPT_VERSION,
            interpreted_analysis_version=snapshot.analysis_version,
            summary=_require_optional_text(symbol, "summary", submit_input.get("summary")),
            trend_strength=trend_strength,
            breakout_quality=breakout_quality,
            momentum_state=momentum_state,
            false_signal_risk=false_signal_risk,
            risk_reward_rating=risk_reward_rating,
            swing_entry_plausibility=swing_entry_plausibility,
            false_signal_risks=_require_string_list(
                symbol, "false_signal_risks", submit_input.get("false_signal_risks", ())
            ),
            confidence=_require_optional_confidence(symbol, submit_input.get("confidence")),
        )

    def _enforce_risk_reward(
        self,
        symbol: str,
        snapshot: TechnicalSnapshot,
        gemeldet: RiskRewardRating | None,
    ) -> RiskRewardRating | None:
        """Erzwingt ``NOT_ASSESSABLE``, wenn nichts zu bewerten war.

        Der Kern von CLAUDE.mds Regel, dass Bewertungen nie ungeprueft aus
        LLM-Freitext uebernommen werden: Konnte das Verhaeltnis gar nicht
        berechnet werden, darf keine Einstufung dazu im Bericht stehen -- egal
        wie ueberzeugt das Modell antwortet.

        Umgekehrt bleibt eine ausgelassene Antwort ``None`` und wird **nicht**
        zu ``NOT_ASSESSABLE``: "niemand hat eingestuft" ist etwas anderes als
        "war nicht einstufbar". Die beiden zu verwechseln erzeugte genau die
        Kombination, die Doc 14 als Fehlerzeichen nennt -- NOT_ASSESSABLE,
        waehrend darueber eine Zahl steht.
        """
        if snapshot.chance_risk_ratio is not None:
            return gemeldet
        if gemeldet is not None and gemeldet is not RiskRewardRating.NOT_ASSESSABLE:
            _logger.warning(
                "Einordnung fuer %s stuft das Chance-Risiko-Verhaeltnis als %s ein, "
                "obwohl es nicht berechnet werden konnte -- auf NOT_ASSESSABLE gesetzt",
                symbol,
                gemeldet.value,
            )
        return RiskRewardRating.NOT_ASSESSABLE


_STATUS_VOM_MODELL = frozenset(
    {TechnicalAssessmentStatus.COMPLETED, TechnicalAssessmentStatus.INSUFFICIENT_DATA}
)
"""Die einzigen beiden Status, die aus einer Modellantwort stammen duerfen --
dieselben zwei, die das Werkzeugschema zulaesst.

``UNAVAILABLE`` beschreibt einen Anbieterausfall: einen Zustand, den das
System feststellt, nie das Modell. Ohne diese Einschraenkung fiele ein vom
Modell gemeldetes ``UNAVAILABLE`` durch den INSUFFICIENT_DATA-Zweig hindurch
und stuende am Ende als abgeschlossene Einordnung in der Datenbank."""


def _require_status(symbol: str, value: object) -> TechnicalAssessmentStatus:
    try:
        status = TechnicalAssessmentStatus(str(value))
    except ValueError as error:
        raise TechnicalInterpreterError(
            f"'{symbol}': '{_SUBMIT_TOOL_NAME}' lieferte einen unerwarteten status: {value!r}"
        ) from error
    if status not in _STATUS_VOM_MODELL:
        raise TechnicalInterpreterError(
            f"'{symbol}': '{_SUBMIT_TOOL_NAME}' lieferte den status '{status.value}', "
            "den ausschliesslich der Application Layer setzen darf"
        )
    return status


def _require_optional_enum[E: StrEnum](
    symbol: str, field_name: str, enum_type: type[E], value: object
) -> E | None:
    """Ein unbekannter Wert ist ein Fehler, kein stilles ``None``.

    Ein stilles ``None`` saehe im Bericht aus wie "nicht eingeordnet" und
    verdeckte, dass das Modell etwas geantwortet hat, das die Domain nicht
    kennt.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise TechnicalInterpreterError(
            f"'{symbol}': '{field_name}' aus '{_SUBMIT_TOOL_NAME}' ist kein Text, "
            f"sondern {type(value).__name__}"
        )
    try:
        return enum_type(value)
    except ValueError as error:
        raise TechnicalInterpreterError(
            f"'{symbol}': '{field_name}' aus '{_SUBMIT_TOOL_NAME}' ist kein "
            f"gueltiger Wert: {value!r}"
        ) from error


def _require_optional_text(symbol: str, field_name: str, value: object) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise TechnicalInterpreterError(
        f"'{symbol}': '{field_name}' aus '{_SUBMIT_TOOL_NAME}' ist kein Text, "
        f"sondern {type(value).__name__}"
    )


def _require_string_list(symbol: str, field_name: str, value: object) -> tuple[str, ...]:
    """``tuple(...)`` auf einen String ergaebe eine Liste von Einzelzeichen --
    ein Fehler, der im Bericht wie eine sehr lange Risikoliste aussaehe."""
    if isinstance(value, list | tuple) and all(isinstance(item, str) for item in value):
        return tuple(value)
    raise TechnicalInterpreterError(
        f"'{symbol}': '{field_name}' aus '{_SUBMIT_TOOL_NAME}' ist keine Liste von "
        f"Texten, sondern {type(value).__name__} ({value!r:.120})"
    )


def _require_optional_confidence(symbol: str, value: object) -> float | None:
    if value is None:
        return None
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise TechnicalInterpreterError(
            f"'{symbol}': confidence aus '{_SUBMIT_TOOL_NAME}' ist keine Zahl, "
            f"sondern {type(value).__name__}"
        )
    if not 0.0 <= float(value) <= 1.0:
        raise TechnicalInterpreterError(
            f"'{symbol}': confidence aus '{_SUBMIT_TOOL_NAME}' liegt ausserhalb von [0, 1]: {value}"
        )
    return float(value)
