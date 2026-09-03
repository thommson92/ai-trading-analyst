"""Tests der 3-aus-5-Kandidatenregel und des Sechs-Kerzen-Fensters.

Fachliche Grundlage: G1-Pruefvorlage Abschnitt 3 und 1.5. Die
Ereigniskriterien feuern auf Baseline-Kerzen nie (siehe conftest); jeder
Test ueberschreibt gezielt einzelne Kerzen, um genau ein Verhalten zu
isolieren.

``NO_RECENT_EMA_DOWNCROSS`` ist die Ausnahme: Es ist erfuellt, solange kein
Abwaertskreuz vorliegt, und steht deshalb in fast jeder Erwartung mit drin.
"""

from __future__ import annotations

import pytest

import ai_trading_analyst.domain.screening.candidate as candidate_module
from ai_trading_analyst.domain.screening import (
    CandidateRuleParameters,
    CandleSeries,
    DataIncompleteError,
    IndicatorValues,
    ScreeningStatus,
    SignalType,
    evaluate_candidate,
)
from tests.unit.domain.screening.conftest import (
    BASELINE_EMA,
    build_series,
    ema5_ema20_cross_fires,
    ema_downcross_fires,
    incomplete_indicators,
    price_ema20_breakout_candles_at,
    rsi_cross_fires,
    rsi_oversold_fires,
)

SERIES_LENGTH = 30
DECISION_INDEX = 20
PARAMS = CandidateRuleParameters(
    required_crossing_signals=2, signal_lookback_previous_candles=5, warmup_candles=10
)

OHNE_ABWAERTSKREUZ = frozenset({SignalType.NO_RECENT_EMA_DOWNCROSS})
"""Was in der ruhigen Baseline ohnehin erfuellt ist."""


class TestFensterGrenzen:
    def test_signal_auf_t_minus_5_zaehlt(self) -> None:
        """t-5 ist die aelteste noch zum Fenster gehoerende Kerze (Abschnitt 3.2)."""
        series = build_series(SERIES_LENGTH, indicator_overrides={15: rsi_cross_fires()})
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert SignalType.RSI_CROSS in result.fired_signal_types

    def test_signal_auf_t_minus_6_zaehlt_nicht(self) -> None:
        """t-6 liegt bereits ausserhalb des Sechs-Kerzen-Fensters."""
        series = build_series(SERIES_LENGTH, indicator_overrides={14: rsi_cross_fires()})
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert SignalType.RSI_CROSS not in result.fired_signal_types
        assert result.status != ScreeningStatus.UNKNOWN_DATA_INCOMPLETE

    def test_signal_auf_t_plus_1_wird_niemals_einbezogen(self) -> None:
        series = build_series(
            SERIES_LENGTH, indicator_overrides={DECISION_INDEX + 1: rsi_cross_fires()}
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert SignalType.RSI_CROSS not in result.fired_signal_types
        assert result.status != ScreeningStatus.UNKNOWN_DATA_INCOMPLETE


class TestZaehlungDerSignaltypen:
    def test_zwei_unterschiedliche_signale_auf_derselben_kerze(self) -> None:
        """Zusammen mit dem erfuellten Ausschlusskriterium sind das drei Typen."""
        series = build_series(
            SERIES_LENGTH,
            indicator_overrides={
                DECISION_INDEX: IndicatorValues(
                    rsi=60.0, rsi_ma=50.0, ema5=110.0, ema20=BASELINE_EMA
                )
            },
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.fired_signal_types == (
            frozenset({SignalType.RSI_CROSS, SignalType.EMA5_EMA20_CROSS}) | OHNE_ABWAERTSKREUZ
        )
        assert result.status == ScreeningStatus.CANDIDATE

    def test_zwei_unterschiedliche_signale_auf_verschiedenen_kerzen(self) -> None:
        """Beispiel aus der G1-Pruefvorlage, Abschnitt 3.5:
        RSI_CROSS auf t-4, PRICE_EMA20_BREAKOUT auf t-1."""
        series = build_series(
            SERIES_LENGTH,
            indicator_overrides={DECISION_INDEX - 4: rsi_cross_fires()},
            candle_overrides=price_ema20_breakout_candles_at(DECISION_INDEX - 1),
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.status == ScreeningStatus.CANDIDATE
        assert result.fired_signal_types == (
            frozenset({SignalType.RSI_CROSS, SignalType.PRICE_EMA20_BREAKOUT})
            | OHNE_ABWAERTSKREUZ
        )
        positions = {event.signal_type: event.candle_index for event in result.signal_events}
        assert positions[SignalType.RSI_CROSS] == DECISION_INDEX - 4
        assert positions[SignalType.PRICE_EMA20_BREAKOUT] == DECISION_INDEX - 1

    def test_zwei_typen_reichen_nicht(self) -> None:
        """Ein Ereignissignal plus das Ausschlusskriterium sind zwei von fuenf."""
        series = build_series(
            SERIES_LENGTH, indicator_overrides={DECISION_INDEX: rsi_cross_fires()}
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.fired_signal_types == frozenset({SignalType.RSI_CROSS}) | OHNE_ABWAERTSKREUZ
        assert result.status == ScreeningStatus.NOT_CANDIDATE

    def test_dreifaches_auftreten_desselben_signaltyps_zaehlt_nur_einmal(self) -> None:
        series = build_series(
            SERIES_LENGTH,
            indicator_overrides={
                DECISION_INDEX - 5: rsi_cross_fires(),
                DECISION_INDEX - 3: rsi_cross_fires(),
                DECISION_INDEX - 1: rsi_cross_fires(),
            },
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.fired_signal_types == frozenset({SignalType.RSI_CROSS}) | OHNE_ABWAERTSKREUZ
        assert result.status == ScreeningStatus.NOT_CANDIDATE
        rsi_ereignisse = [
            event
            for event in result.signal_events
            if event.signal_type is SignalType.RSI_CROSS
        ]
        assert len(rsi_ereignisse) == 1
        assert rsi_ereignisse[0].candle_index == DECISION_INDEX - 5


class TestUeberverkaufterRsi:
    """Signal D -- Fensterkriterium wie A bis C (G1-Pruefvorlage Abschnitt 2.4)."""

    def test_ein_ueberverkaufter_wert_im_fenster_genuegt(self) -> None:
        series = build_series(
            SERIES_LENGTH, indicator_overrides={DECISION_INDEX - 3: rsi_oversold_fires()}
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert SignalType.RSI_OVERSOLD in result.fired_signal_types
        positions = {event.signal_type: event.candle_index for event in result.signal_events}
        assert positions[SignalType.RSI_OVERSOLD] == DECISION_INDEX - 3

    def test_ausserhalb_des_fensters_zaehlt_er_nicht(self) -> None:
        series = build_series(
            SERIES_LENGTH, indicator_overrides={DECISION_INDEX - 6: rsi_oversold_fires()}
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert SignalType.RSI_OVERSOLD not in result.fired_signal_types

    def test_die_erholung_entwertet_das_kriterium_nicht(self) -> None:
        """Der Titel *war* im Fenster ueberverkauft -- an ``t`` muss er es nicht
        mehr sein. Genau der Fall, den ADR 0056 beschreibt: RSI dreht aus dem
        ueberverkauften Bereich nach oben."""
        series = build_series(
            SERIES_LENGTH,
            indicator_overrides={
                DECISION_INDEX - 4: rsi_oversold_fires(),
                DECISION_INDEX: rsi_cross_fires(),
            },
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.fired_signal_types == (
            frozenset({SignalType.RSI_OVERSOLD, SignalType.RSI_CROSS}) | OHNE_ABWAERTSKREUZ
        )

    def test_beide_zusatzkriterien_ersetzen_kein_zweites_kaufsignal(self) -> None:
        """Der Kern der Regel: Drei erfuellte Kriterien, aber nur **ein**
        Kaufsignal -- das genuegt nicht.

        Waeren alle fuenf gleichwertig ("drei aus fuenf"), waere dieser Fall
        ein Kandidat, und die Regel liesse mehr Titel durch als die fruehere
        Zwei-aus-drei-Regel. Gemessen am Golden Master waren das 15 Prozent
        mehr Kandidaten statt weniger (ADR 0056)."""
        series = build_series(
            SERIES_LENGTH,
            indicator_overrides={
                DECISION_INDEX - 4: rsi_oversold_fires(),
                DECISION_INDEX: rsi_cross_fires(),
            },
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert len(result.fired_signal_types) == 3
        assert result.status == ScreeningStatus.NOT_CANDIDATE

    def test_ein_zusatzkriterium_neben_zwei_kaufsignalen_genuegt(self) -> None:
        series = build_series(
            SERIES_LENGTH,
            indicator_overrides={
                DECISION_INDEX - 4: rsi_cross_fires(),
                # Ein Abwaertskreuz im Pruefbereich nimmt E weg; D traegt.
                DECISION_INDEX - 2: ema_downcross_fires(),
                DECISION_INDEX - 3: rsi_oversold_fires(),
            },
            candle_overrides=price_ema20_breakout_candles_at(DECISION_INDEX - 1),
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert SignalType.NO_RECENT_EMA_DOWNCROSS not in result.fired_signal_types
        assert SignalType.RSI_OVERSOLD in result.fired_signal_types
        assert result.status == ScreeningStatus.CANDIDATE

    def test_ohne_jedes_zusatzkriterium_reichen_zwei_kaufsignale_nicht(self) -> None:
        series = build_series(
            SERIES_LENGTH,
            indicator_overrides={
                DECISION_INDEX - 4: rsi_cross_fires(),
                DECISION_INDEX - 2: ema_downcross_fires(),
            },
            candle_overrides=price_ema20_breakout_candles_at(DECISION_INDEX - 1),
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.fired_signal_types == frozenset(
            {SignalType.RSI_CROSS, SignalType.PRICE_EMA20_BREAKOUT}
        )
        assert result.status == ScreeningStatus.NOT_CANDIDATE


class TestAusschlusskriterium:
    """Signal E -- einmal an der Entscheidungskerze (G1-Pruefvorlage Abschnitt 2.5)."""

    def test_ohne_abwaertskreuz_ist_es_erfuellt(self) -> None:
        series = build_series(SERIES_LENGTH)
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.fired_signal_types == OHNE_ABWAERTSKREUZ

    @pytest.mark.parametrize("abstand", [0, 1, 4])
    def test_ein_abwaertskreuz_im_pruefbereich_schliesst_aus(self, abstand: int) -> None:
        """t-4 bis t: die fuenf Kerzen, auf die sich ADR 0056 bezieht."""
        series = build_series(
            SERIES_LENGTH,
            indicator_overrides={DECISION_INDEX - abstand: ema_downcross_fires()},
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert SignalType.NO_RECENT_EMA_DOWNCROSS not in result.fired_signal_types

    def test_ein_aelteres_abwaertskreuz_schliesst_nicht_aus(self) -> None:
        """t-5 liegt eine Position vor dem Pruefbereich -- der Unterschied
        zwischen dem Sechs-Kerzen-Fenster der Ereigniskriterien und den fuenf
        Kerzen dieses Kriteriums."""
        series = build_series(
            SERIES_LENGTH,
            indicator_overrides={DECISION_INDEX - 5: ema_downcross_fires()},
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert SignalType.NO_RECENT_EMA_DOWNCROSS in result.fired_signal_types

    def test_sein_ereignis_steht_auf_der_entscheidungskerze(self) -> None:
        series = build_series(SERIES_LENGTH)
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        (event,) = result.signal_events
        assert event.signal_type is SignalType.NO_RECENT_EMA_DOWNCROSS
        assert event.candle_index == DECISION_INDEX

    def test_ein_frisches_abwaertskreuz_kippt_die_entscheidung(self) -> None:
        """Zwei Ereignissignale allein reichen nicht mehr -- das ist der Zweck
        des Kriteriums: Gezappel um die Linie ist kein Trendwechsel."""
        ohne_kreuz = build_series(
            SERIES_LENGTH,
            indicator_overrides={DECISION_INDEX - 4: rsi_cross_fires()},
            candle_overrides=price_ema20_breakout_candles_at(DECISION_INDEX - 1),
        )
        assert evaluate_candidate(ohne_kreuz, DECISION_INDEX, PARAMS).status == (
            ScreeningStatus.CANDIDATE
        )

        mit_kreuz = build_series(
            SERIES_LENGTH,
            indicator_overrides={
                DECISION_INDEX - 4: rsi_cross_fires(),
                DECISION_INDEX - 2: ema_downcross_fires(),
            },
            candle_overrides=price_ema20_breakout_candles_at(DECISION_INDEX - 1),
        )
        assert evaluate_candidate(mit_kreuz, DECISION_INDEX, PARAMS).status == (
            ScreeningStatus.NOT_CANDIDATE
        )


class TestRegisterDeckenAlleSignaltypen:
    def test_jeder_signaltyp_wird_genau_einmal_ausgewertet(self) -> None:
        """Sonst fiele ein neuer Enumwert still aus der Auswertung: Die
        Schleifen laufen ueber die Register, nicht ueber ``SignalType``."""
        fenster = set(candidate_module._WINDOW_SIGNAL_FUNCTIONS)
        entscheidungskerze = set(candidate_module._DECISION_CANDLE_FUNCTIONS)
        assert fenster | entscheidungskerze == set(SignalType)
        assert not fenster & entscheidungskerze


class TestFehlendeDaten:
    @pytest.mark.parametrize("missing_index", list(range(14, 21)))
    def test_fehlende_daten_an_jeder_relevanten_fensterposition(self, missing_index: int) -> None:
        """t-6 bis t: jede davon wird von mindestens einer Signalformel als
        Vor- oder aktuelle Kerze benoetigt (Abschnitt 1.5)."""
        series = build_series(
            SERIES_LENGTH, indicator_overrides={missing_index: incomplete_indicators()}
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.status == ScreeningStatus.UNKNOWN_DATA_INCOMPLETE
        assert result.affected_index == missing_index

    def test_fehlende_daten_ausserhalb_des_relevanten_bereichs_bleiben_ohne_wirkung(self) -> None:
        series = build_series(SERIES_LENGTH, indicator_overrides={13: incomplete_indicators()})
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.status != ScreeningStatus.UNKNOWN_DATA_INCOMPLETE

    def test_fehlende_daten_werden_nie_als_negatives_signal_gewertet(self) -> None:
        """Explizite Regel aus Abschnitt 1.5: keine stillschweigende Einstufung
        als Nicht-Kandidat bei Datenluecke."""
        series = build_series(
            SERIES_LENGTH, indicator_overrides={DECISION_INDEX: incomplete_indicators()}
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.status not in (ScreeningStatus.NOT_CANDIDATE, ScreeningStatus.CANDIDATE)


class TestVerteidigungGegenUnerwarteteDataIncomplete:
    @pytest.mark.parametrize(
        ("register", "signaltyp"),
        [
            ("_WINDOW_SIGNAL_FUNCTIONS", SignalType.RSI_CROSS),
            ("_DECISION_CANDLE_FUNCTIONS", SignalType.NO_RECENT_EMA_DOWNCROSS),
        ],
    )
    def test_evaluate_candidate_stuerzt_nicht_ab_wenn_signalfunktion_data_incomplete_meldet(
        self, monkeypatch: pytest.MonkeyPatch, register: str, signaltyp: SignalType
    ) -> None:
        """Zweite Verteidigungslinie (Abschnitt 1.5): meldet eine Signalfunktion
        trotz vorgelagerter Vollstaendigkeitspruefung eine Datenluecke, bricht
        evaluate_candidate nicht mit einer unbehandelten Exception ab, sondern
        liefert UNKNOWN_DATA_INCOMPLETE.

        Beide Register liegen im selben ``try`` -- der Test haelt fest, dass
        das so bleibt."""

        def _always_incomplete(series: object, t: int) -> bool:
            raise DataIncompleteError(candle_index=t, required=("TEST",))

        monkeypatch.setattr(candidate_module, register, {signaltyp: _always_incomplete})
        series = build_series(SERIES_LENGTH)
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.status == ScreeningStatus.UNKNOWN_DATA_INCOMPLETE


class TestWarmup:
    def test_kerze_vor_warmup_grenze_ist_unbestimmt(self) -> None:
        series = build_series(PARAMS.warmup_candles)
        result = evaluate_candidate(series, PARAMS.warmup_candles - 1, PARAMS)
        assert result.status == ScreeningStatus.UNKNOWN_DATA_INCOMPLETE
        assert result.reason == "warmup_insufficient"

    def test_erste_auswertbare_kerze_liegt_exakt_auf_der_warmup_grenze(self) -> None:
        series = build_series(SERIES_LENGTH)
        result = evaluate_candidate(series, PARAMS.warmup_candles, PARAMS)
        assert result.reason != "warmup_insufficient"


class TestParameterpruefung:
    @pytest.mark.parametrize("zahl", [0, 4])
    def test_unmoegliche_zahl_geforderter_kaufsignale_wird_abgelehnt(self, zahl: int) -> None:
        """Vier Kaufsignale gibt es nicht -- ein solcher Wert liefert dauerhaft
        null Kandidaten und saehe im Lauf wie ein ruhiger Markt aus."""
        with pytest.raises(ValueError, match="required_crossing_signals"):
            CandidateRuleParameters(
                required_crossing_signals=zahl,
                signal_lookback_previous_candles=5,
                warmup_candles=10,
            )

    @pytest.mark.parametrize("zahl", [1, 2, 3])
    def test_moegliche_zahlen_werden_angenommen(self, zahl: int) -> None:
        params = CandidateRuleParameters(
            required_crossing_signals=zahl,
            signal_lookback_previous_candles=5,
            warmup_candles=10,
        )
        assert params.required_crossing_signals == zahl


class TestTorbedingungen:
    """Frische und Bestaetigung an der Entscheidungskerze (Abschnitt 3.6)."""

    @staticmethod
    def _zwei_kaufsignale(juengstes_auf: int) -> CandleSeries:
        """Zwei Kaufsignale; das juengste feuert auf ``juengstes_auf``.

        Das RSI-Kreuz liegt bewusst weit hinten im Fenster, damit allein die
        Position des zweiten Signals ueber die Frische entscheidet.
        """
        return build_series(
            SERIES_LENGTH,
            indicator_overrides={
                DECISION_INDEX - 5: rsi_cross_fires(),
                juengstes_auf: ema5_ema20_cross_fires(),
            },
        )

    @pytest.mark.parametrize("abstand", [0, 1], ids=["feuert_auf_t", "feuert_auf_t_minus_1"])
    def test_ein_frisches_kaufsignal_laesst_die_regel_durch(self, abstand: int) -> None:
        result = evaluate_candidate(
            self._zwei_kaufsignale(DECISION_INDEX - abstand), DECISION_INDEX, PARAMS
        )
        assert result.status == ScreeningStatus.CANDIDATE
        assert result.reason is None

    def test_ohne_frisches_kaufsignal_wird_verworfen(self) -> None:
        """Alle Kaufsignale zwei Kerzen alt oder aelter -- der Fall aus
        ``docs/backtesting/Fraglich.png``."""
        result = evaluate_candidate(
            self._zwei_kaufsignale(DECISION_INDEX - 2), DECISION_INDEX, PARAMS
        )
        assert result.status == ScreeningStatus.NOT_CANDIDATE
        assert result.reason == "gate:stale_crossing_signals"

    def test_die_signale_bleiben_am_verworfenen_ergebnis(self) -> None:
        """Es soll nachlesbar sein, *was* erfuellt war und *woran* es scheiterte."""
        result = evaluate_candidate(
            self._zwei_kaufsignale(DECISION_INDEX - 2), DECISION_INDEX, PARAMS
        )
        assert result.fired_signal_types == (
            frozenset({SignalType.RSI_CROSS, SignalType.EMA5_EMA20_CROSS}) | OHNE_ABWAERTSKREUZ
        )
        assert len(result.signal_events) == 3

    def test_das_juengste_feuern_zaehlt_nicht_die_gespeicherte_position(self) -> None:
        """Ein Typ feuert auf t-5 **und erneut** auf t: Gespeichert wird t-5
        (Abschnitt 4.3), frisch ist er trotzdem."""
        series = build_series(
            SERIES_LENGTH,
            indicator_overrides={
                DECISION_INDEX - 5: ema5_ema20_cross_fires(),
                DECISION_INDEX - 3: rsi_cross_fires(),
                DECISION_INDEX: ema5_ema20_cross_fires(),
            },
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        positionen = {e.signal_type: e.candle_index for e in result.signal_events}
        assert positionen[SignalType.EMA5_EMA20_CROSS] == DECISION_INDEX - 5
        assert result.status == ScreeningStatus.CANDIDATE

    def test_ein_frisches_zusatzkriterium_rettet_die_frische_nicht(self) -> None:
        """Nur Kaufsignale zaehlen: Ein ueberverkaufter RSI an ``t`` beschreibt
        eine Lage, kein Ereignis."""
        series = build_series(
            SERIES_LENGTH,
            indicator_overrides={
                DECISION_INDEX - 4: rsi_cross_fires(),
                DECISION_INDEX - 3: ema5_ema20_cross_fires(),
                DECISION_INDEX: rsi_oversold_fires(),
            },
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert SignalType.RSI_OVERSOLD in result.fired_signal_types
        assert result.status == ScreeningStatus.NOT_CANDIDATE
        assert result.reason == "gate:stale_crossing_signals"

    def test_gleichstand_mit_dem_ema20_genuegt_nicht(self) -> None:
        series = build_series(
            SERIES_LENGTH,
            indicator_overrides={
                DECISION_INDEX - 5: rsi_cross_fires(),
                DECISION_INDEX: IndicatorValues(
                    rsi=50.0, rsi_ma=50.0, ema5=110.0, ema20=100.0
                ),
            },
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.status == ScreeningStatus.NOT_CANDIDATE
        assert result.reason == "gate:close_not_above_ema20"

    def test_beide_tore_scheitern_gemeinsam(self) -> None:
        series = build_series(
            SERIES_LENGTH,
            indicator_overrides={
                DECISION_INDEX - 5: rsi_cross_fires(),
                DECISION_INDEX - 2: ema5_ema20_cross_fires(),
                # Beide EMAs steigen gemeinsam ueber den Schlusskurs: T2
                # scheitert, ein Abwaertskreuz entsteht dabei aber nicht.
                DECISION_INDEX: IndicatorValues(
                    rsi=50.0, rsi_ma=50.0, ema5=105.0, ema20=105.0
                ),
            },
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.reason == "gate:stale_crossing_signals+close_not_above_ema20"

    def test_zu_wenige_signale_tragen_keinen_grund(self) -> None:
        """"Zu wenige Signale" ist keine verworfene Qualifikation."""
        series = build_series(
            SERIES_LENGTH, indicator_overrides={DECISION_INDEX: rsi_cross_fires()}
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.status == ScreeningStatus.NOT_CANDIDATE
        assert result.reason is None

    def test_unbestimmte_daten_haben_vorrang_vor_den_toren(self) -> None:
        series = build_series(
            SERIES_LENGTH, indicator_overrides={DECISION_INDEX: incomplete_indicators()}
        )
        result = evaluate_candidate(series, DECISION_INDEX, PARAMS)
        assert result.status == ScreeningStatus.UNKNOWN_DATA_INCOMPLETE
        assert result.reason == "missing_candle_or_indicator"
