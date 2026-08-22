"""Tests des Technical-Agent-Adapters (ADR 0026).

Kein echtes Netzwerk (Muster ``test_provider.py``): ``httpx.MockTransport``,
injiziert ueber den SDK-eigenen ``http_client``-Parameter. Das SDK selbst
laeuft echt, inklusive Serialisierung und Antwort-Parsing -- ersetzt ist nur
die Leitung.

Anders als der Research-Adapter hat dieser genau eine Phase: eine Anfrage,
ein erzwungener Werkzeugaufruf, fertig.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from ai_trading_analyst.domain.analysis import Stock, TechnicalInterpreterError
from ai_trading_analyst.domain.technical import (
    BreakoutQuality,
    FalseSignalRisk,
    MomentumState,
    PriceZone,
    RiskRewardRating,
    SwingEntryPlausibility,
    TechnicalAssessmentStatus,
    TechnicalSnapshot,
    TechnicalStatus,
    TrendStrength,
    ZoneKind,
    ZoneStrength,
)
from ai_trading_analyst.infrastructure.anthropic.technical_interpreter import (
    _SUBMIT_ASSESSMENT_TOOL,
    AnthropicTechnicalInterpreter,
    AnthropicTechnicalPricing,
    AnthropicTechnicalSettings,
    render_snapshot,
)

AAPL = Stock(id=uuid.uuid4(), symbol="AAPL", exchange="NASDAQ")
EVALUATED_AT = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


def snapshot(**overrides: object) -> TechnicalSnapshot:
    felder: dict[str, object] = {
        "status": TechnicalStatus.COMPLETED,
        "evaluated_at": EVALUATED_AT,
        "candle_timestamp": datetime(2026, 8, 21, 20, 15, tzinfo=UTC),
        "close": 100.0,
        "rsi": 61.5,
        "ema5": 99.0,
        "ema20": 96.0,
        "distance_to_ema5_pct": 0.0101,
        "distance_to_ema20_pct": 0.0417,
        "atr": 2.5,
        "atr_pct": 0.025,
        "recent_high": 107.0,
        "recent_low": 88.0,
        "downside_to_support_pct": 0.02,
        "upside_to_resistance_pct": 0.05,
        "chance_risk_ratio": 2.5,
    }
    felder.update(overrides)
    return TechnicalSnapshot(**felder)  # type: ignore[arg-type]


def _zone(kind: ZoneKind, lower: float, upper: float, distance: float) -> PriceZone:
    return PriceZone(
        lower=lower,
        upper=upper,
        kind=kind,
        strength=ZoneStrength.STRONG,
        touch_count=9,
        last_confirmed_at=datetime(2026, 8, 18, 20, 15, tzinfo=UTC),
        distance_pct=distance,
        pivot_count=7,
    )


def _submit_block(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "COMPLETED",
        "trend_strength": "MODERATE",
        "breakout_quality": "NO_BREAKOUT",
        "momentum_state": "NEUTRAL",
        "false_signal_risk": "MEDIUM",
        "risk_reward_rating": "BALANCED",
        "swing_entry_plausibility": "QUESTIONABLE",
        "summary": "Einordnung.",
        "false_signal_risks": ["Widerstand in Reichweite"],
        "confidence": 0.6,
    }
    payload.update(overrides)
    return {
        "type": "tool_use",
        "id": "toolu_1",
        "name": "submit_technical_assessment",
        "input": payload,
    }


def _message(
    content: list[dict[str, object]], stop_reason: str = "tool_use"
) -> dict[str, object]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-4-5-20251001",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 400, "output_tokens": 120},
    }


def _settings(**overrides: object) -> AnthropicTechnicalSettings:
    defaults: dict[str, object] = {
        "api_key": "test-key",
        "model": "claude-haiku-4-5-20251001",
        "max_output_tokens": 2000,
        "request_timeout_seconds": 60,
        "pricing": AnthropicTechnicalPricing(
            input_usd_per_million=1.0, output_usd_per_million=5.0
        ),
    }
    defaults.update(overrides)
    return AnthropicTechnicalSettings(**defaults)  # type: ignore[arg-type]


def _interpreter(
    handler: Callable[[httpx.Request], httpx.Response], **settings_overrides: object
) -> AnthropicTechnicalInterpreter:
    return AnthropicTechnicalInterpreter(
        _settings(**settings_overrides),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _antwortet(*bodies: dict[str, object]) -> Callable[[httpx.Request], httpx.Response]:
    """Antwortet der Reihe nach; die letzte Antwort gilt fuer alle weiteren."""
    folge = list(bodies)

    def handler(request: httpx.Request) -> httpx.Response:
        body = folge.pop(0) if len(folge) > 1 else folge[0]
        return httpx.Response(200, json=body)

    return handler


class TestErfolgsfall:
    def test_alle_sechs_einstufungen_werden_uebernommen(self) -> None:
        assessment = _interpreter(_antwortet(_message([_submit_block()]))).interpret(
            AAPL, snapshot()
        )

        assert assessment.status is TechnicalAssessmentStatus.COMPLETED
        assert assessment.trend_strength is TrendStrength.MODERATE
        assert assessment.breakout_quality is BreakoutQuality.NO_BREAKOUT
        assert assessment.momentum_state is MomentumState.NEUTRAL
        assert assessment.false_signal_risk is FalseSignalRisk.MEDIUM
        assert assessment.risk_reward_rating is RiskRewardRating.BALANCED
        assert assessment.swing_entry_plausibility is SwingEntryPlausibility.QUESTIONABLE
        assert assessment.false_signal_risks == ("Widerstand in Reichweite",)
        assert assessment.confidence == 0.6

    def test_modell_und_promptversion_stehen_am_ergebnis(self) -> None:
        """ADR 0021: Die verwendete Modellversion gehoert an jedes Ergebnis,
        nicht nur ins Log."""
        assessment = _interpreter(_antwortet(_message([_submit_block()]))).interpret(
            AAPL, snapshot()
        )

        assert assessment.model == "claude-haiku-4-5-20251001"
        assert assessment.prompt_version == "technical-agent-v1"

    def test_die_eingeordnete_verfahrensversion_wird_festgehalten(self) -> None:
        assessment = _interpreter(_antwortet(_message([_submit_block()]))).interpret(
            AAPL, snapshot()
        )

        assert assessment.interpreted_analysis_version == snapshot().analysis_version


class TestKeinAufrufOhneGrundlage:
    def test_unvollstaendiger_snapshot_loest_keine_anfrage_aus(self) -> None:
        """Es gibt nichts einzuordnen -- und ein Aufruf kostete nur Geld."""
        aufrufe = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal aufrufe
            aufrufe += 1
            return httpx.Response(200, json=_message([_submit_block()]))

        assessment = _interpreter(handler).interpret(
            AAPL, snapshot(status=TechnicalStatus.INSUFFICIENT_DATA, close=None)
        )

        assert aufrufe == 0
        assert assessment.status is TechnicalAssessmentStatus.INSUFFICIENT_DATA
        assert assessment.reason == "snapshot_insufficient"
        assert assessment.model is None


class TestSchemaDurchsetzung:
    def test_abgeschnittene_antwort_ergibt_kein_teilergebnis(self) -> None:
        """Ein abgeschnittener Werkzeugaufruf kann eine halbe Risikoliste
        enthalten, die vollstaendig aussieht."""
        with pytest.raises(TechnicalInterpreterError, match="max_tokens"):
            _interpreter(
                _antwortet(_message([_submit_block()], stop_reason="max_tokens"))
            ).interpret(AAPL, snapshot())

    def test_fehlender_werkzeugaufruf_ist_ein_fehler(self) -> None:
        with pytest.raises(TechnicalInterpreterError, match="nicht aufgerufen"):
            _interpreter(
                _antwortet(
                    _message(
                        [
                            {
                                "type": "text",
                                "text": "Ich denke, es sieht gut aus.",
                                "citations": None,
                            }
                        ],
                        stop_reason="end_turn",
                    )
                )
            ).interpret(AAPL, snapshot())

    def test_unbekannte_einstufung_ist_ein_fehler_kein_stilles_none(self) -> None:
        """Ein stilles ``None`` saehe im Bericht aus wie 'nicht eingeordnet'
        und verdeckte, dass das Modell etwas Unbekanntes geantwortet hat."""
        with pytest.raises(TechnicalInterpreterError, match="trend_strength"):
            _interpreter(
                _antwortet(_message([_submit_block(trend_strength="VERY_STRONG")]))
            ).interpret(AAPL, snapshot())

    def test_confidence_ausserhalb_des_bereichs_ist_ein_fehler(self) -> None:
        with pytest.raises(TechnicalInterpreterError, match=r"\[0, 1\]"):
            _interpreter(_antwortet(_message([_submit_block(confidence=1.5)]))).interpret(
                AAPL, snapshot()
            )

    def test_confidence_als_text_ist_ein_fehler(self) -> None:
        with pytest.raises(TechnicalInterpreterError, match="keine Zahl"):
            _interpreter(_antwortet(_message([_submit_block(confidence="hoch")]))).interpret(
                AAPL, snapshot()
            )

    def test_risikoliste_als_text_ist_ein_fehler(self) -> None:
        """``tuple("Text")`` ergaebe eine Liste von Einzelzeichen -- im
        Bericht saehe das wie eine sehr lange Risikoliste aus."""
        with pytest.raises(TechnicalInterpreterError, match="false_signal_risks"):
            _interpreter(
                _antwortet(_message([_submit_block(false_signal_risks="Ein Risiko")]))
            ).interpret(AAPL, snapshot())

    def test_completed_ohne_jede_einstufung_wird_herabgestuft(self) -> None:
        leer = {
            "status": "COMPLETED",
            "trend_strength": None,
            "breakout_quality": None,
            "momentum_state": None,
            "false_signal_risk": None,
            "risk_reward_rating": None,
            "swing_entry_plausibility": None,
        }
        assessment = _interpreter(_antwortet(_message([_submit_block(**leer)]))).interpret(
            AAPL, snapshot()
        )

        assert assessment.status is TechnicalAssessmentStatus.INSUFFICIENT_DATA
        assert assessment.reason == "no_ratings"

    def test_ein_vom_modell_gemeldetes_unavailable_wird_abgewiesen(self) -> None:
        """UNAVAILABLE beschreibt einen Anbieterausfall -- einen Zustand, den
        das System feststellt, nie das Modell. Ohne diese Pruefung fiele der
        Wert durch den INSUFFICIENT_DATA-Zweig hindurch und stuende als
        abgeschlossene Einordnung in der Datenbank."""
        with pytest.raises(TechnicalInterpreterError, match="UNAVAILABLE"):
            _interpreter(
                _antwortet(_message([_submit_block(status="UNAVAILABLE")]))
            ).interpret(AAPL, snapshot())

    def test_vom_modell_gemeldete_unzulaenglichkeit_wird_uebernommen(self) -> None:
        assessment = _interpreter(
            _antwortet(
                _message(
                    [
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "submit_technical_assessment",
                            "input": {"status": "INSUFFICIENT_DATA", "reason": "zu wenig"},
                        }
                    ]
                )
            )
        ).interpret(AAPL, snapshot())

        assert assessment.status is TechnicalAssessmentStatus.INSUFFICIENT_DATA
        assert assessment.reason == "zu wenig"


class TestChanceRisikoUebersteuerung:
    """Die harte Umsetzung von "Scores werden nie direkt aus LLM-Freitext
    uebernommen" (CLAUDE.md)."""

    def test_ohne_berechnetes_verhaeltnis_gilt_not_assessable(self) -> None:
        assessment = _interpreter(
            _antwortet(_message([_submit_block(risk_reward_rating="FAVOURABLE")]))
        ).interpret(AAPL, snapshot(chance_risk_ratio=None, downside_to_support_pct=None))

        assert assessment.risk_reward_rating is RiskRewardRating.NOT_ASSESSABLE

    def test_mit_berechnetem_verhaeltnis_gilt_die_modellantwort(self) -> None:
        assessment = _interpreter(
            _antwortet(_message([_submit_block(risk_reward_rating="FAVOURABLE")]))
        ).interpret(AAPL, snapshot())

        assert assessment.risk_reward_rating is RiskRewardRating.FAVOURABLE

    def test_keine_einstufung_ist_nicht_dasselbe_wie_nicht_einstufbar(self) -> None:
        """Laesst das Modell das Feld aus, obwohl eine Zahl vorliegt, bleibt
        es leer. NOT_ASSESSABLE waere hier falsch -- und erzeugte genau die
        Kombination, die Doc 14 als Fehlerzeichen nennt: "nicht beurteilbar",
        waehrend darueber eine Zahl steht."""
        assessment = _interpreter(
            _antwortet(_message([_submit_block(risk_reward_rating=None)]))
        ).interpret(AAPL, snapshot())

        assert assessment.risk_reward_rating is None


class TestAnfrage:
    @staticmethod
    def _body(handler_holder: list[dict[str, object]]) -> Callable[[httpx.Request], httpx.Response]:
        def handler(request: httpx.Request) -> httpx.Response:
            handler_holder.append(json.loads(request.content))
            return httpx.Response(200, json=_message([_submit_block()]))

        return handler

    def test_denken_ist_ausdruecklich_abgeschaltet(self) -> None:
        """ADR 0023, Punkt 21: ausdruecklich setzen. ``max_tokens`` deckelt
        Denken und Antworttext gemeinsam."""
        gesendet: list[dict[str, object]] = []
        _interpreter(self._body(gesendet)).interpret(AAPL, snapshot())

        assert gesendet[0]["thinking"] == {"type": "disabled"}

    def test_der_werkzeugaufruf_wird_erzwungen(self) -> None:
        gesendet: list[dict[str, object]] = []
        _interpreter(self._body(gesendet)).interpret(AAPL, snapshot())

        assert gesendet[0]["tool_choice"] == {
            "type": "tool",
            "name": "submit_technical_assessment",
        }

    def test_es_gibt_keine_webwerkzeuge(self) -> None:
        """Der Agent ordnet ein und recherchiert nicht -- er hat gar kein
        Werkzeug, mit dem er etwas anderes als den Snapshot heranziehen
        koennte."""
        gesendet: list[dict[str, object]] = []
        _interpreter(self._body(gesendet)).interpret(AAPL, snapshot())

        werkzeuge = gesendet[0]["tools"]
        assert isinstance(werkzeuge, list)
        assert [w["name"] for w in werkzeuge] == ["submit_technical_assessment"]

    def test_das_schema_ist_strikt(self) -> None:
        gesendet: list[dict[str, object]] = []
        _interpreter(self._body(gesendet)).interpret(AAPL, snapshot())

        werkzeug = gesendet[0]["tools"][0]  # type: ignore[index]
        assert werkzeug["strict"] is True
        assert werkzeug["input_schema"]["additionalProperties"] is False


class TestSchemaBleibtMitDerDomainImGleichschritt:
    """Waechter gegen Auseinanderlaufen.

    Die Enum-Werte stehen an drei Stellen: in der Domain, in der Datenbank und
    im Werkzeugschema. Wird einer ergaenzt und das Schema nicht, kann das
    Modell den Wert nie liefern -- und niemand merkt es.
    """

    @staticmethod
    def _schema_enum(feld: str) -> set[str]:
        return set(_SUBMIT_ASSESSMENT_TOOL["input_schema"]["properties"][feld]["enum"])

    def test_alle_sechs_felder_decken_sich_mit_der_domain(self) -> None:
        paare = (
            ("trend_strength", TrendStrength),
            ("breakout_quality", BreakoutQuality),
            ("momentum_state", MomentumState),
            ("false_signal_risk", FalseSignalRisk),
            ("risk_reward_rating", RiskRewardRating),
            ("swing_entry_plausibility", SwingEntryPlausibility),
        )
        for feld, enum_typ in paare:
            assert self._schema_enum(feld) == {m.value for m in enum_typ}, feld


class TestModelleingabe:
    def test_die_werte_des_snapshots_stehen_drin(self) -> None:
        text = render_snapshot(AAPL, snapshot(), EVALUATED_AT)

        assert "AAPL" in text
        assert "100.00" in text
        assert "61.5" in text
        assert "Chance-Risiko-Verhaeltnis: 2.50" in text

    def test_das_heutige_datum_steht_drin(self) -> None:
        """ADR 0023, Punkt 14: Ohne Stichtag hielt das Modell alte Meldungen
        fuer die Gegenwart."""
        assert "2026-08-22" in render_snapshot(AAPL, snapshot(), EVALUATED_AT)

    def test_fehlende_werte_erscheinen_als_nicht_verfuegbar(self) -> None:
        """Nicht als ``--`` und nicht als ``0``: Das Modell soll den
        Unterschied zwischen 'null' und 'unbekannt' nicht raten muessen."""
        text = render_snapshot(AAPL, snapshot(rsi=None, atr=None, atr_pct=None), EVALUATED_AT)

        assert "RSI: nicht verfuegbar" in text
        assert "ATR: nicht verfuegbar" in text

    def test_nicht_berechenbares_verhaeltnis_wird_begruendet(self) -> None:
        text = render_snapshot(
            AAPL,
            snapshot(chance_risk_ratio=None, downside_to_support_pct=None),
            EVALUATED_AT,
        )

        assert "nicht berechenbar" in text
        assert "keine Unterstuetzung unterhalb" in text

    def test_ein_kurs_in_einer_zone_wird_ausdruecklich_gekennzeichnet(self) -> None:
        """Sonst liest sich ein guenstiges Verhaeltnis harmlos, waehrend der
        Kurs mitten in einer starken Zone klemmt: Die beiden Wege zeigen dann
        auf die Zonen *jenseits* dieser Zone."""
        text = render_snapshot(
            AAPL,
            snapshot(zones=(_zone(ZoneKind.PRICE_INSIDE, 99.0, 102.0, 0.0),)),
            EVALUATED_AT,
        )

        assert "Der Kurs liegt in einer Zone" in text
        assert "nicht auf diese" in text

    def test_ohne_zone_im_kurs_gibt_es_keinen_hinweis(self) -> None:
        text = render_snapshot(
            AAPL,
            snapshot(zones=(_zone(ZoneKind.SUPPORT, 95.0, 96.0, 0.04),)),
            EVALUATED_AT,
        )

        assert "Der Kurs liegt in einer Zone" not in text

    def test_die_staerke_steht_neben_der_beruehrungszahl(self) -> None:
        """Der Prompt weist ausdruecklich darauf hin, dass die Staerke den
        Wendepunkten folgt -- dafuer muessen beide Zahlen sichtbar sein."""
        text = render_snapshot(
            AAPL,
            snapshot(zones=(_zone(ZoneKind.SUPPORT, 95.0, 96.0, 0.04),)),
            EVALUATED_AT,
        )

        assert "Staerke STRONG" in text
        assert "7 Wendepunkte" in text
        assert "9 Beruehrungen" in text

    def test_ein_einzelner_wendepunkt_steht_im_singular(self) -> None:
        """Genau der Fall, um den es geht: eine Zone mit einem Wendepunkt und
        vielen Beruehrungen. "1 Wendepunkte" waere ausgerechnet dort ein
        Stolperstein, wo das Modell genau hinsehen soll."""
        einzeln = PriceZone(
            lower=95.0,
            upper=95.0,
            kind=ZoneKind.SUPPORT,
            strength=ZoneStrength.WEAK,
            touch_count=12,
            last_confirmed_at=datetime(2026, 8, 18, 20, 15, tzinfo=UTC),
            distance_pct=0.05,
            pivot_count=1,
        )
        text = render_snapshot(AAPL, snapshot(zones=(einzeln,)), EVALUATED_AT)

        assert "1 Wendepunkt," in text
        assert "1 Wendepunkte" not in text

    def test_die_lage_zum_durchschnitt_wird_ausgeschrieben(self) -> None:
        """"Kurs -1.50 % davon entfernt" laesst sich als Betrag lesen."""
        text = render_snapshot(AAPL, snapshot(distance_to_ema20_pct=-0.015), EVALUATED_AT)

        assert "1.50 % darunter" in text
        assert "-1.50" not in text


def _fehler(status: int, typ: str) -> httpx.Response:
    return httpx.Response(status, json={"type": "error", "error": {"type": typ, "message": "x"}})


class TestAusweichmodell:
    """Bewusst mit einem 400 statt eines 529: Das SDK wiederholt
    ueberlastungsnahe Statuscodes von sich aus mit **demselben** Modell. Ein
    Test gegen 529 waere gruen, ohne dass der Ausweichpfad je durchlaufen
    wurde -- genau das ist beim Schreiben dieser Tests passiert.
    """

    def test_bei_einem_apifehler_wird_das_ausweichmodell_versucht(self) -> None:
        antworten = [
            _fehler(400, "invalid_request_error"),
            httpx.Response(200, json=_message([_submit_block()])),
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            return antworten.pop(0)

        assessment = AnthropicTechnicalInterpreter(
            _settings(fallback_model="claude-haiku-4-5"),
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        ).interpret(AAPL, snapshot())

        assert assessment.status is TechnicalAssessmentStatus.COMPLETED
        # Entscheidend ist, welches Modell geantwortet hat: Ohne diese
        # Zusicherung waere der Test auch dann gruen, wenn die zweite Antwort
        # nur eine SDK-interne Wiederholung mit dem *ersten* Modell war.
        assert assessment.model == "claude-haiku-4-5"

    def test_ohne_ausweichmodell_wird_der_fehler_durchgereicht(self) -> None:
        with pytest.raises(TechnicalInterpreterError):
            _interpreter(lambda request: _fehler(400, "invalid_request_error")).interpret(
                AAPL, snapshot()
            )

    def test_scheitern_beide_modelle_nennt_die_meldung_beide(self) -> None:
        with pytest.raises(TechnicalInterpreterError, match="noch ueber"):
            AnthropicTechnicalInterpreter(
                _settings(fallback_model="claude-haiku-4-5"),
                http_client=httpx.Client(
                    transport=httpx.MockTransport(
                        lambda request: _fehler(400, "invalid_request_error")
                    )
                ),
            ).interpret(AAPL, snapshot())
